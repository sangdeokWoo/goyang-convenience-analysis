"""
공백 분석 v2 지도 생성 → goyang_gap_v2_map.html

레이어
  - 행정동 공백 점수 코로플레스 (툴팁: 편의점 수·세대수·접근성·커버리지)
  - 데이터 수집 범위 밖 구역 (회색 빗금: 판단 보류)
  - 400m 밖 주거지 격자 (빨간 사각형)
  - 아파트 단지 (원 크기 = 세대수, 색 = 1천 세대당 도보권 편의점 수)
  - 기존 편의점
  - 신규 입지 추천 TOP 10 (번호 + 400m 반경)

실행: python scripts/gap_analysis.py && python scripts/make_gap_v2_map.py
"""
import json
from pathlib import Path

import folium
import pandas as pd
from branca.colormap import LinearColormap
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

from gap_analysis import RADIUS

ROOT = Path(__file__).resolve().parent.parent
DATA, RESULTS = ROOT / 'data', ROOT / 'results'
FONT = "'Noto Sans KR', -apple-system, 'Segoe UI', sans-serif"
TT_STYLE = (f"font-family:{FONT};font-size:12px;background:#1e293b;color:#e2e8f0;"
            "border:none;border-radius:6px;padding:8px 12px;")


def fmt(v, suffix=''):
    return '-' if pd.isna(v) else f'{v:,.0f}{suffix}' if isinstance(v, (int, float)) and float(v).is_integer() else f'{v}{suffix}'


def main():
    summary = json.loads((RESULTS / 'summary.json').read_text(encoding='utf-8'))
    dong = pd.read_csv(RESULTS / 'dong_gap_ranking.csv')
    sites = pd.read_csv(RESULTS / 'recommended_sites.csv')
    apts = pd.read_csv(RESULTS / 'apartments_access.csv')
    cells = pd.read_csv(RESULTS / 'uncovered_residential_cells.csv')
    stores = pd.read_csv(DATA / 'stores.csv')
    dong_fc = json.loads((DATA / 'goyang_dong.geojson').read_text(encoding='utf-8'))

    # CartoDB 타일은 API 키가 없으면 워터마크가 표시되어 Esri 다크 그레이 타일 사용
    m = folium.Map(location=[37.655, 126.835], zoom_start=12, tiles=None, control_scale=True)
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/'
              'World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}',
        attr='Tiles &copy; Esri', name='Esri Dark Gray', max_zoom=16, control=False,
    ).add_to(m)
    m.get_root().header.add_child(folium.Element(
        '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap" rel="stylesheet">'))

    # ── 행정동 공백 점수 ──────────────────────────────────────────────────────
    stats = dong.set_index('dong')
    vmax = max(dong.gap_score.max(), 1)
    cmap = LinearColormap(['#1e293b', '#7c2d12', '#ea580c', '#fbbf24'], vmin=0, vmax=vmax,
                          caption='공백 점수 (합계 100)')
    for f in dong_fc['features']:
        r = stats.loc[f['properties']['name']]
        f['properties'].update({
            'rank': f"{int(r['rank'])}위", 'score': fmt(r.gap_score),
            'stores': fmt(r.store_count, '개'), 'units': fmt(r.apt_units, '세대'),
            'ups': fmt(r.units_per_store, '세대'),
            'acc': fmt(r.stores_per_1k_units, '개'),
            'cov': fmt(r.res_coverage_pct, '%'),
            'short': fmt(r.short_units, '세대'),
            'unc': fmt(r.uncovered_res_km2, 'km²'),
            'data': fmt(r.data_area_pct, '%'),
            '_v': float(r.gap_score),
        })
    folium.GeoJson(
        dong_fc, name='행정동 공백 점수',
        style_function=lambda f: {'fillColor': cmap(f['properties']['_v']), 'fillOpacity': 0.55,
                                  'color': 'rgba(255,255,255,0.25)', 'weight': 1},
        highlight_function=lambda f: {'weight': 2.5, 'color': '#38bdf8'},
        tooltip=folium.GeoJsonTooltip(
            fields=['name', 'gu', 'rank', 'score', 'stores', 'units', 'ups', 'acc', 'cov',
                    'short', 'unc', 'data'],
            aliases=['행정동', '구', '공백 순위', '공백 점수', '편의점', '아파트 세대(300+)',
                     '편의점 1곳당 세대', '1천 세대당 도보권 편의점', '주거지 400m 커버율',
                     '공급 부족 세대', '400m 밖 주거지', '데이터 수집 범위'],
            style=TT_STYLE),
    ).add_to(m)
    cmap.add_to(m)

    # ── 데이터 수집 범위 밖 ───────────────────────────────────────────────────
    city = unary_union([shape(f['geometry']) for f in dong_fc['features']])
    area = shape(json.loads((RESULTS / 'analysis_area.geojson').read_text(encoding='utf-8'))['geometry'])
    outside = city.difference(area)
    folium.GeoJson(
        {'type': 'Feature', 'geometry': mapping(outside), 'properties': {}},
        name='데이터 수집 범위 밖 (판단 보류)',
        style_function=lambda f: {'fillColor': '#64748b', 'fillOpacity': 0.45, 'color': '#94a3b8',
                                  'weight': 1, 'dashArray': '4 4'},
        tooltip='원본 데이터 수집 범위 밖(또는 경계 400m 이내)이라 판단을 보류합니다',
    ).add_to(m)

    # ── 400m 밖 주거지 격자 ───────────────────────────────────────────────────
    half_lat, half_lng = 50 / 111_000, 50 / 88_000
    cell_fc = {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'properties': {'d': f'최근접 편의점 {int(c.dist_m):,}m'},
         'geometry': mapping(box(c.lng - half_lng, c.lat - half_lat, c.lng + half_lng, c.lat + half_lat))}
        for c in cells.itertuples()]}
    folium.GeoJson(
        cell_fc, name=f'편의점 {RADIUS}m 밖 주거지',
        style_function=lambda f: {'fillColor': '#ef4444', 'fillOpacity': 0.7, 'weight': 0},
        tooltip=folium.GeoJsonTooltip(fields=['d'], labels=False, style=TT_STYLE),
    ).add_to(m)

    # ── 기존 편의점 ───────────────────────────────────────────────────────────
    g_store = folium.FeatureGroup(name='기존 편의점', show=True)
    for s in stores.itertuples():
        folium.CircleMarker([s.lat, s.lng], radius=2, weight=0, fill=True,
                            fill_color='#94a3b8', fill_opacity=0.8,
                            tooltip=f'{s.name} ({s.brand})').add_to(g_store)
    g_store.add_to(m)

    # ── 아파트 (접근성) ───────────────────────────────────────────────────────
    ref = summary['stores_per_1k_units_median']
    acc_cmap = LinearColormap(['#ef4444', '#fbbf24', '#22c55e'], vmin=0, vmax=ref * 2)
    g_apt = folium.FeatureGroup(name='아파트 접근성 (1천 세대당 도보권 편의점)', show=True)
    for a in apts.itertuples():
        folium.CircleMarker(
            [a.lat, a.lng], radius=3 + (a.units ** 0.5) / 12, weight=1, color='#0f172a',
            fill=True, fill_color=acc_cmap(min(a.stores_per_1k_units, ref * 2)), fill_opacity=0.9,
            tooltip=(f'<b>{a.name}</b><br>{a.units:,}세대 · 최근접 편의점 {int(a.nearest_m):,}m<br>'
                     f'400m 안 편의점 {a.stores_400m}개 · 1천 세대당 {a.stores_per_1k_units:.2f}개'
                     f'<br>(고양시 중앙값 {ref:.2f}개)'),
        ).add_to(g_apt)
    g_apt.add_to(m)

    # ── 추천 입지 ─────────────────────────────────────────────────────────────
    g_site = folium.FeatureGroup(name='신규 입지 추천 TOP 10', show=True)
    for s in sites.itertuples():
        folium.Circle([s.lat, s.lng], radius=RADIUS, color='#38bdf8', weight=1.5,
                      dash_array='5 5', fill=True, fill_opacity=0.06).add_to(g_site)
        apts_txt = s.nearby_apts if isinstance(s.nearby_apts, str) and s.nearby_apts else '아파트 외 주거지'
        folium.Marker(
            [s.lat, s.lng],
            icon=folium.DivIcon(html=(
                f'<div style="width:26px;height:26px;border-radius:50%;background:#38bdf8;'
                f'color:#0f172a;font:700 13px {FONT};display:flex;align-items:center;'
                f'justify-content:center;border:2px solid #fff;transform:translate(-13px,-13px)">'
                f'{s.rank}</div>')),
            tooltip=(f'<b>추천 #{s.rank}</b> {s.gu} {s.dong}<br>'
                     f'최근접 기존 편의점 {s.nearest_store_m:,}m<br>'
                     f'공급 부족 해소 {s.short_units_reduced:,}세대 · 새로 커버하는 주거지 {s.new_covered_res_km2}km²<br>'
                     f'주변: {apts_txt}<br>'
                     f'<a href="https://map.kakao.com/link/map/추천{s.rank},{s.lat},{s.lng}" target="_blank">카카오맵</a>'),
        ).add_to(g_site)
    g_site.add_to(m)

    folium.LayerControl(collapsed=True).add_to(m)
    minx, miny, maxx, maxy = city.bounds
    m.fit_bounds([[miny, minx], [maxy, maxx]], padding_top_left=(330, 10))

    # ── 설명 패널 ─────────────────────────────────────────────────────────────
    top5 = ''.join(
        f'<div style="display:flex;justify-content:space-between;margin-bottom:3px">'
        f'<span>{int(r["rank"])}. {r.dong} <span style="color:#64748b">{r.gu}</span></span>'
        f'<span style="color:#fbbf24">{r.gap_score:.1f}</span></div>'
        for _, r in dong.head(5).iterrows())
    panel = f"""
<div style="position:fixed;top:12px;left:56px;z-index:1000;width:300px;
  background:rgba(10,14,20,0.95);border:1px solid rgba(255,255,255,0.08);border-radius:12px;
  padding:16px 18px;font-family:{FONT};color:#e2e8f0;font-size:12px;line-height:1.55;
  box-shadow:0 8px 32px rgba(0,0,0,0.6)">
  <div style="font-size:10px;letter-spacing:2px;color:#38bdf8;margin-bottom:6px">GAP ANALYSIS v2</div>
  <div style="font-size:16px;font-weight:700;margin-bottom:8px">고양시 편의점 공백 재분석</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:10px">
    <div><div style="color:#64748b;font-size:10px">주거지 400m 커버율</div>
         <div style="font-size:17px;font-weight:700">{summary['coverage_residential_pct']}%</div></div>
    <div><div style="color:#64748b;font-size:10px">아파트 세대 커버율</div>
         <div style="font-size:17px;font-weight:700">{summary['coverage_apt_units_pct']}%</div></div>
    <div><div style="color:#64748b;font-size:10px">주거지→편의점 평균</div>
         <div style="font-size:17px;font-weight:700">{summary['res_mean_dist_m']}m</div></div>
    <div><div style="color:#64748b;font-size:10px">기존 방식 커버율</div>
         <div style="font-size:17px;font-weight:700;color:#64748b">{summary['coverage_old_method_pct']}%</div></div>
  </div>
  <div style="font-size:10px;color:#fbbf24;letter-spacing:1px;margin-bottom:4px">공백 점수 TOP 5</div>
  {top5}
  <div style="border-top:1px solid rgba(255,255,255,0.08);margin-top:8px;padding-top:8px;color:#94a3b8;font-size:11px">
    공백 점수 = 50 × 공급 부족 세대 비중(2SFCA) + 50 × 400m 밖 주거지 비중<br>
    기존 방식 28.4%는 산·농지·한강까지 포함한 사각형 격자 기준이었습니다.<br>
    <span style="color:#ef4444">■</span> 400m 밖 주거지 &nbsp;
    <span style="color:#38bdf8">●</span> 추천 입지 &nbsp;
    <span style="color:#64748b">▨</span> 데이터 범위 밖
  </div>
</div>"""
    m.get_root().html.add_child(folium.Element(panel))

    out = ROOT / 'goyang_gap_v2_map.html'
    m.save(out)
    print(f'[OK] {out.name} ({out.stat().st_size / 1e6:.1f} MB)')


if __name__ == '__main__':
    main()
