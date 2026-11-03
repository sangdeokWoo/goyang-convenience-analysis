"""
고양시 편의점 공백 분석 v2
════════════════════════════════════════════════════════════════════════════════
기존 분석(노트북)의 한계를 보완한 재분석입니다.

  기존                                           v2
  ───────────────────────────────────────────   ───────────────────────────────────────────
  위경도 사각형 전체에 500m 격자                 → 고양시 실제 경계 안 100m 격자,
  (산·농지·한강까지 '미커버'로 집계)                OSM 주거지역(landuse=residential)만 평가
  위경도에 111000을 곱해 거리 근사               → EPSG:5179(미터 좌표계)로 투영 후 계산
  공백 점수 = 동 안 '편의점끼리' 평균 거리 ÷ 개수 → 주민(아파트·주거지) 기준 접근성
  (수요 미반영, 편의점 간격을 측정)                 + 2SFCA(수요 대비 공급) 지표
  K-means 군집 중심을 추천 부지로 사용           → 최대 커버리지 입지 모형(탐욕법)
  (산·공원 위로 찍히기도 함)                        주거지 주변 후보 중 개선 효과가 큰 곳부터 선정

▸ 수요 두 가지
  ① 아파트 세대수 (300세대 이상 325단지, data/apartments.csv)
  ② OSM 주거지역 면적 — 빌라·단독주택처럼 아파트 데이터에 없는 주거지 보완

▸ 접근성 지표: 2SFCA (Two-Step Floating Catchment Area, Luo & Wang 2003)
  1단계  편의점 j의 공급비 R_j = 1 / (j 반경 400m 안 아파트 세대수 합)
  2단계  아파트 i의 접근성 A_i = Σ (i 반경 400m 안 편의점의 R_j)
  → A_i × 1000 = '걸어갈 수 있는 편의점 수 / 1천 세대' (주변 경쟁 수요까지 반영)
  고양시 세대 가중 중앙값을 기준(A_ref)으로, 기준보다 낮은 만큼을 '공급 부족 세대'로 봅니다.
     부족 세대 u_i = 세대수 × max(0, 1 − A_i / A_ref)    (반경 안 편의점 0개면 세대수 전부)

▸ 공백 점수 (행정동, 합계 100)
     50 × (동의 부족 세대 / 시 전체 부족 세대) + 50 × (동의 미커버 주거면적 / 시 전체 미커버 주거면적)

▸ 신규 입지 추천: 위 두 항을 목적함수로 하는 탐욕 최대 커버리지 모형.
  한 곳을 고를 때마다 그 자리에 편의점을 추가하고 2SFCA를 다시 계산하므로,
  같은 수요를 두 번 세지 않습니다.

▸ 한계
  - 거리는 직선거리(도보 400m ≈ 5분). 도로망·단지 출입구는 반영하지 않음.
  - 아파트는 단지 대표 좌표 1점. 큰 단지는 실제 동별 거리가 다를 수 있음.
  - 원본 노트북이 편의점·아파트를 위도 37.57~37.73 / 경도 126.74~126.97 사각형으로 걸러 저장해서
    그 밖(일산서구 가좌·송포 서쪽, 덕양구 북쪽 끝 등)은 데이터가 없습니다. 이 구역을 '편의점 0개'로
    오판하지 않도록 분석 영역을 '고양시 경계 ∩ (데이터 수집 범위에서 400m 안쪽)'으로 제한합니다.
  - 고양시 밖(서울 은평·파주·김포) 편의점은 데이터에 없어 시 경계 부근 접근성은 다소 낮게 나올 수 있음.

입력  data/stores.csv, data/apartments.csv, data/goyang_dong.geojson, data/goyang_residential.geojson
출력  results/summary.json, results/dong_gap_ranking.csv, results/recommended_sites.csv,
      results/apartments_access.csv, results/uncovered_residential_cells.csv

실행  python scripts/extract_data.py && python scripts/fetch_osm.py && python scripts/gap_analysis.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer
from scipy.spatial import cKDTree
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent.parent
DATA, RESULTS = ROOT / 'data', ROOT / 'results'

RADIUS = 400          # 서비스 반경 (m)
CELL = 100            # 격자 크기 (m)
N_SITES = 10          # 추천 부지 수
DEMAND_WEIGHT = 0.5   # 공급 부족 세대 비중 (나머지는 미커버 주거면적 비중)
CAND_BUFFER = 100     # 추천 후보: 주거지 + 주변 100m (주거지 앞 도로·상가 포함)
DATA_BBOX = (126.74, 37.57, 126.97, 37.73)  # 원본 데이터 수집 범위 (lng0, lat0, lng1, lat1)

TO_M = Transformer.from_crs(4326, 5179, always_xy=True)
TO_LL = Transformer.from_crs(5179, 4326, always_xy=True)


def to_m(lng, lat):
    x, y = TO_M.transform(np.asarray(lng, float), np.asarray(lat, float))
    return np.column_stack([np.atleast_1d(x), np.atleast_1d(y)])


def to_ll(xy):
    lng, lat = TO_LL.transform(xy[:, 0], xy[:, 1])
    return np.round(lat, 6), np.round(lng, 6)


def load_polys(name):
    fc = json.loads((DATA / name).read_text(encoding='utf-8'))
    geoms = [shapely.transform(shape(f['geometry']), lambda c: to_m(c[:, 0], c[:, 1]))
             for f in fc['features']]
    return geoms, [f['properties'] for f in fc['features']]


def two_step_fca(store_xy, apt_xy, units):
    """2SFCA 접근성 A_i (세대당 편의점 수)."""
    pairs = cKDTree(store_xy).query_ball_point(apt_xy, RADIUS)   # 아파트 i → 반경 안 편의점들
    demand = np.zeros(len(store_xy))
    for i, js in enumerate(pairs):
        demand[js] += units[i]
    R = np.divide(1.0, demand, out=np.zeros_like(demand), where=demand > 0)
    return np.array([R[js].sum() for js in pairs]), np.array([len(js) for js in pairs])


def main():
    RESULTS.mkdir(exist_ok=True)

    # ── 1. 데이터 로드 (미터 좌표계) ──────────────────────────────────────────
    stores = pd.read_csv(DATA / 'stores.csv')
    apts = pd.read_csv(DATA / 'apartments.csv')
    S = to_m(stores.lng, stores.lat)
    A = to_m(apts.lng, apts.lat)
    units = apts.units.to_numpy(float)

    dong_geoms, dong_props = load_polys('goyang_dong.geojson')
    res_geoms, _ = load_polys('goyang_residential.geojson')
    city_full = shapely.union_all(dong_geoms)
    res_full = shapely.union_all(res_geoms).intersection(city_full)
    b = DATA_BBOX
    data_area = shapely.Polygon(to_m([b[0], b[2], b[2], b[0]], [b[1], b[1], b[3], b[3]]))
    # 수집 범위 경계에서 400m 안쪽까지만 판정 (경계 밖 편의점이 데이터에 없어 공백으로 오판되는 것 방지)
    data_inner = data_area.buffer(-RADIUS, join_style='mitre')
    city = city_full.intersection(data_inner)
    residential = res_full.intersection(data_inner)
    cand_area = residential.buffer(CAND_BUFFER).intersection(city)

    # ── 2. 100m 격자 (분석 영역 안) ───────────────────────────────────────────
    x0, y0, x1, y1 = city.bounds
    gx, gy = np.meshgrid(np.arange(x0 + CELL / 2, x1, CELL), np.arange(y0 + CELL / 2, y1, CELL))
    G = np.column_stack([gx.ravel(), gy.ravel()])
    pts = shapely.points(G)
    for g in (city, residential, cand_area):
        shapely.prepare(g)
    keep = shapely.contains(city, pts)
    G, pts = G[keep], pts[keep]
    is_res = shapely.contains(residential, pts)
    is_cand = shapely.contains(cand_area, pts)
    cell_km2 = CELL * CELL / 1e6

    # ── 3. 거리·커버리지 ──────────────────────────────────────────────────────
    tree = cKDTree(S)
    g_dist, _ = tree.query(G)
    a_dist, _ = tree.query(A)
    g_cov, a_cov = g_dist <= RADIUS, a_dist <= RADIUS
    a_in = shapely.contains(data_inner, shapely.points(A))   # 판정 대상 아파트

    # ── 4. 2SFCA 접근성 → 공급 부족 세대 ──────────────────────────────────────
    # 편의점의 수요(R_j 분모)에는 모든 아파트를 쓰고, 판정은 분석 영역 안 아파트만 한다.
    access, n_near = two_step_fca(S, A, units)
    order = np.argsort(access[a_in])
    cum = np.cumsum(units[a_in][order])
    A_ref = access[a_in][order][np.searchsorted(cum, cum[-1] / 2)]   # 세대 가중 중앙값
    short = np.where(a_in, units * np.clip(1 - access / A_ref, 0, None), 0)
    apts['in_scope'] = a_in
    apts['nearest_m'] = a_dist.round()
    apts['stores_400m'] = n_near
    apts['stores_per_1k_units'] = (access * 1000).round(2)
    apts['short_units'] = short.round()

    # ── 5. 행정동 집계 ────────────────────────────────────────────────────────
    def assign(points):
        out = np.full(len(points), -1)
        for i, g in enumerate(dong_geoms):
            shapely.prepare(g)
            out[(out < 0) & shapely.contains(g, points)] = i
        return out
    g_dong, a_dong, s_dong = assign(pts), assign(shapely.points(A)), assign(shapely.points(S))
    a_dong = np.where(a_in, a_dong, -1)

    unc_res_cell = is_res & ~g_cov
    U0, R0 = short.sum(), unc_res_cell.sum()

    rows = []
    for i, p in enumerate(dong_props):
        gm, am = g_dong == i, a_dong == i
        rm = gm & is_res
        hh = units[am].sum()
        n_store = int((s_dong == i).sum())
        g_full = dong_geoms[i]
        rows.append({
            'gu': p['gu'], 'dong': p['name'],
            'data_area_pct': round(100 * g_full.intersection(data_inner).area / g_full.area, 1),
            'store_count': n_store,
            'residential_km2': round(rm.sum() * cell_km2, 2),
            'apt_units': int(hh),
            'units_per_store': round(hh / n_store) if n_store else None,
            'stores_per_1k_units': round(1000 * np.average(access[am], weights=units[am]), 2) if hh else None,
            'res_mean_dist_m': round(g_dist[rm].mean()) if rm.any() else None,
            'res_coverage_pct': round(100 * g_cov[rm].mean(), 1) if rm.any() else None,
            'apt_coverage_pct': round(100 * units[am & a_cov].sum() / hh, 1) if hh else None,
            'short_units': int(short[am].sum()),
            'uncovered_res_km2': round((rm & ~g_cov).sum() * cell_km2, 2),
            'gap_score': round(100 * (DEMAND_WEIGHT * short[am].sum() / U0
                                      + (1 - DEMAND_WEIGHT) * (rm & ~g_cov).sum() / R0), 2),
        })
    dong = pd.DataFrame(rows).sort_values('gap_score', ascending=False).reset_index(drop=True)
    dong.insert(0, 'rank', dong.index + 1)

    # ── 6. 신규 입지 추천 (탐욕 최대 커버리지) ────────────────────────────────
    cand = G[is_cand]
    cand_a = cKDTree(A).query_ball_point(cand, RADIUS)
    unc_pts = G[unc_res_cell]
    cand_r = cKDTree(unc_pts).query_ball_point(cand, RADIUS)
    res_w = np.ones(len(unc_pts))
    cand_dong = assign(shapely.points(cand))
    # 2SFCA에서 편의점 j의 공급비 R_j는 j 주변 수요로만 정해진다.
    # 따라서 후보 c에 편의점을 추가하면 c 반경 안 아파트의 A_i만 R_c = 1/D_c 만큼 오른다 (정확한 증분).
    cand_a = [np.array(a, dtype=int) for a in cand_a]
    R_c = np.array([1 / units[a].sum() if len(a) else 0 for a in cand_a])
    acc_now = access.copy()

    def short_of(acc, idx):
        return (units[idx] * np.clip(1 - acc / A_ref, 0, None)).sum()

    sites = []
    for k in range(N_SITES):
        d_short = np.array([short_of(acc_now[a], a) - short_of(acc_now[a] + R_c[c], a)
                            for c, a in enumerate(cand_a)])
        d_res = np.array([res_w[r].sum() for r in cand_r])
        gains = DEMAND_WEIGHT * d_short / U0 + (1 - DEMAND_WEIGHT) * d_res / R0
        j = int(gains.argmax())
        if gains[j] <= 0:
            break
        new_res = d_res[j] * cell_km2
        res_w[cand_r[j]] = 0
        acc_now[cand_a[j]] += R_c[j]
        lat, lng = to_ll(cand[j:j + 1])
        near = sorted(cand_a[j], key=lambda i: -short[i])
        d = cand_dong[j]
        sites.append({
            'rank': k + 1, 'lat': lat[0], 'lng': lng[0],
            'gu': dong_props[d]['gu'] if d >= 0 else '',
            'dong': dong_props[d]['name'] if d >= 0 else '',
            'nearest_store_m': round(tree.query(cand[j])[0]),
            'apt_units_400m': int(units[cand_a[j]].sum()),
            'short_units_reduced': int(round(d_short[j])),
            'new_covered_res_km2': round(new_res, 2),
            'score_gain': round(100 * gains[j], 2),
            'nearby_apts': ', '.join(apts.name[i] for i in near[:3] if short[i] > 0),
        })
    sites = pd.DataFrame(sites)

    # ── 7. 비교: 기존 방식(사각형 500m 격자, 위경도 근사) 커버리지 재현 ─────────
    old = np.array([[la, ln] for la in np.arange(37.57, 37.73, 0.0045)
                    for ln in np.arange(126.74, 126.97, 0.0045)])
    old_d, _ = cKDTree(stores[['lat', 'lng']].values * [111000, 88000]).query(old * [111000, 88000])

    summary = {
        'stores': len(stores), 'apartments': len(apts), 'apt_units': int(units.sum()),
        'radius_m': RADIUS,
        'city_km2': round(city_full.area / 1e6, 1),
        'analysis_area_km2': round(city.area / 1e6, 1),
        'apartments_in_scope': int(a_in.sum()),
        'apt_units_in_scope': int(units[a_in].sum()),
        'residential_km2': round(is_res.sum() * cell_km2, 1),
        'residential_outside_data_km2': round((res_full.area - residential.area) / 1e6, 2),
        'coverage_old_method_pct': round(100 * (old_d <= RADIUS).mean(), 1),
        'coverage_city_area_pct': round(100 * g_cov.mean(), 1),
        'coverage_residential_pct': round(100 * g_cov[is_res].mean(), 1),
        'coverage_apt_units_pct': round(100 * units[a_cov & a_in].sum() / units[a_in].sum(), 1),
        'res_mean_dist_m': round(g_dist[is_res].mean()),
        'stores_per_1k_units_median': round(A_ref * 1000, 2),
        'short_units': int(round(U0)),
        'uncovered_res_km2': round(R0 * cell_km2, 2),
        'after_sites_short_units': int(round(short_of(acc_now, np.arange(len(A))))),
        'after_sites_uncovered_res_km2': round(res_w.sum() * cell_km2, 2),
    }

    # ── 8. 저장 ───────────────────────────────────────────────────────────────
    (RESULTS / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                          encoding='utf-8')
    dong.to_csv(RESULTS / 'dong_gap_ranking.csv', index=False, encoding='utf-8-sig')
    sites.to_csv(RESULTS / 'recommended_sites.csv', index=False, encoding='utf-8-sig')
    apts.to_csv(RESULTS / 'apartments_access.csv', index=False, encoding='utf-8-sig')
    area_ll = shapely.transform(city, lambda c: np.column_stack(TO_LL.transform(c[:, 0], c[:, 1])))
    (RESULTS / 'analysis_area.geojson').write_text(json.dumps(
        {'type': 'Feature', 'properties': {}, 'geometry': shapely.geometry.mapping(area_ll)}),
        encoding='utf-8')
    lat, lng = to_ll(G[unc_res_cell])
    pd.DataFrame({'lat': lat, 'lng': lng, 'dist_m': g_dist[unc_res_cell].round()}) \
        .to_csv(RESULTS / 'uncovered_residential_cells.csv', index=False)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    pd.set_option('display.width', 250)
    print('\n=== 공백 심각 행정동 TOP 10 ===')
    print(dong.head(10)[['rank', 'gu', 'dong', 'store_count', 'apt_units', 'units_per_store',
                         'stores_per_1k_units', 'res_coverage_pct', 'short_units',
                         'uncovered_res_km2', 'gap_score']].to_string(index=False))
    print('\n=== 신규 입지 추천 TOP 10 ===')
    print(sites.drop(columns=['lat', 'lng']).to_string(index=False))


if __name__ == '__main__':
    main()
