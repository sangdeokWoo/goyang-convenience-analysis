"""
기존 HTML 파일에서 데이터를 파싱해
goyang_brand_map.html 과 goyang_demand_map.html 을 생성합니다.
별도 CSV 파일 없이 실행 가능합니다.
"""

import re
import json
import numpy as np
import folium
from folium.plugins import HeatMap
from scipy.spatial import Voronoi, cKDTree
from sklearn.cluster import KMeans
from shapely.geometry import Polygon as ShapelyPolygon, box

BASE = r'C:\Users\woosd\OneDrive\바탕 화면\작업\goyang-convenience-analysis'

# ════════════════════════════════════════════════════════════════════════════════
# 1. 데이터 파싱
# ════════════════════════════════════════════════════════════════════════════════

# ── 1-A: satellite_map.html → 편의점 좌표 + 브랜드 ─────────────────────────────
print("satellite_map.html 파싱 중...")

sat_html = open(f'{BASE}/goyang_satellite_map.html', encoding='utf-8').read()

# circleMarker 좌표 추출
coord_pattern = re.compile(
    r'L\.circleMarker\(\s*\[([0-9.]+),\s*([0-9.]+)\].*?fillColor":\s*"(#[0-9a-fA-F]+)".*?'
    r'bindTooltip\(\s*`<div>\s*(.*?)\s*\(`',
    re.DOTALL,
)

# 좀 더 간단한 방식으로 순서대로 파싱
coord_pat   = re.compile(r'L\.circleMarker\(\s*\[([0-9.]+),\s*([0-9.]+)\]')
color_pat   = re.compile(r'"fillColor":\s*"(#[0-9a-fA-F]+)"')
tooltip_pat = re.compile(r'bindTooltip\(\s*`<div>\s*(.*?)\s*</div>`', re.DOTALL)

coords_raw   = coord_pat.findall(sat_html)
colors_raw   = color_pat.findall(sat_html)
tooltips_raw = tooltip_pat.findall(sat_html)

# 색상 → 브랜드 매핑
COLOR_BRAND = {
    '#00a0e9': 'CU',
    '#00dd66': 'GS25',
    '#ff4500': '세븐일레븐',
    '#ffcc00': '이마트24',
}

stores = []
# tooltip이 가장 정확한 출처 — name (BRAND) 형식
name_brand_pat = re.compile(r'(.+?)\s*\((.+?)\)')

for i, tt in enumerate(tooltips_raw):
    tt = tt.strip()
    m  = name_brand_pat.match(tt)
    if not m:
        continue
    if i >= len(coords_raw):
        break
    name  = m.group(1).strip()
    brand = m.group(2).strip()
    lat   = float(coords_raw[i][0])
    lng   = float(coords_raw[i][1])
    # 고양시 범위 필터
    if not (37.57 <= lat <= 37.73 and 126.74 <= lng <= 126.97):
        continue
    stores.append({'name': name, 'brand': brand, 'lat': lat, 'lng': lng})

print(f"  편의점: {len(stores)}개")
from collections import Counter
brand_counts_raw = Counter(s['brand'] for s in stores)
print(f"  {dict(brand_counts_raw)}")

# ── 1-B: voronoi_map.html → 편의점별 담당 세대수 ────────────────────────────────
print("\nvoronoi_map.html 파싱 중...")

vor_html = open(f'{BASE}/goyang_voronoi_map.html', encoding='utf-8').read()

# <b>NAME</b><br>브랜드: BRAND<br>담당 아파트: N단지<br>담당 세대수: N,NNN세대
unit_pat = re.compile(
    r'<b>(.+?)</b><br>브랜드:\s*(.+?)<br>담당 아파트:\s*(\d+)단지<br>담당 세대수:\s*([\d,]+)세대'
)
unit_data = {}
for m in unit_pat.finditer(vor_html):
    name  = m.group(1).strip()
    units = int(m.group(4).replace(',', ''))
    unit_data[name] = units

print(f"  세대수 보유 편의점: {len(unit_data)}개")
print(f"  최대 세대수: {max(unit_data.values()):,}세대")

# 편의점 dict에 세대수 합치기
for s in stores:
    s['units'] = unit_data.get(s['name'], 0)

import pandas as pd
stores_df = pd.DataFrame(stores)
print(f"\n  stores_df 컬럼: {list(stores_df.columns)}")
print(f"  total stores: {len(stores_df)}")

# ════════════════════════════════════════════════════════════════════════════════
# 2. 브랜드 세력권 지도
# ════════════════════════════════════════════════════════════════════════════════
print("\n\n[ 브랜드 세력권 지도 생성 중... ]")

BRAND_PALETTE = {
    'CU':       {'fill': '#2563eb', 'border': '#1e40af'},
    'GS25':     {'fill': '#16a34a', 'border': '#14532d'},
    '세븐일레븐': {'fill': '#dc2626', 'border': '#991b1b'},
    '이마트24':  {'fill': '#d97706', 'border': '#92400e'},
}
DEFAULT_PAL = {'fill': '#6b7280', 'border': '#374151'}

CLIP = box(126.72, 37.55, 126.99, 37.75)
margin = 1.0

coords = stores_df[['lat', 'lng']].values
boundary_pts = np.array([
    [37.57 - margin, 126.72 - margin],
    [37.57 - margin, 126.97 + margin],
    [37.73 + margin, 126.72 - margin],
    [37.73 + margin, 126.97 + margin],
    [37.65,          126.72 - margin],
    [37.65,          126.97 + margin],
    [37.57 - margin, 126.835],
    [37.73 + margin, 126.835],
])
all_pts = np.vstack([coords, boundary_pts])
vor = Voronoi(all_pts)

m_brand = folium.Map(
    location=[37.655, 126.835],
    zoom_start=12,
    tiles='https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', attr='Tiles &copy; Esri',
)

drawn = 0
for i in range(len(stores_df)):
    region_idx = vor.point_region[i]
    region     = vor.regions[region_idx]
    if -1 in region or len(region) < 3:
        continue
    poly_coords  = vor.vertices[region]
    poly_shapely = ShapelyPolygon([(c[1], c[0]) for c in poly_coords])
    clipped      = poly_shapely.intersection(CLIP)
    if clipped.is_empty:
        continue

    def to_folium(geom):
        if geom.geom_type == 'Polygon':
            return [[lat, lng] for lng, lat in geom.exterior.coords]
        elif geom.geom_type == 'MultiPolygon':
            return [[lat, lng] for lng, lat in list(geom.geoms[0].exterior.coords)]
        return None

    fc = to_folium(clipped)
    if not fc:
        continue

    row     = stores_df.iloc[i]
    palette = BRAND_PALETTE.get(row['brand'], DEFAULT_PAL)
    units   = int(row['units'])

    folium.Polygon(
        locations=fc,
        color=palette['border'],
        weight=0.6,
        fill=True,
        fill_color=palette['fill'],
        fill_opacity=0.32,
        tooltip=f"<b>{row['name']}</b><br>{row['brand']}<br>담당: {units:,}세대",
    ).add_to(m_brand)
    drawn += 1

print(f"  폴리곤 {drawn}개 그림")

for _, row in stores_df.iterrows():
    palette = BRAND_PALETTE.get(row['brand'], DEFAULT_PAL)
    folium.CircleMarker(
        location=[row['lat'], row['lng']],
        radius=4,
        color='white', weight=1,
        fill=True, fill_color=palette['fill'], fill_opacity=1.0,
        tooltip=f"{row['name']} ({row['brand']})",
    ).add_to(m_brand)

# 범례
total = len(stores_df)
bc    = stores_df['brand'].value_counts()
items = ''
for brand, pal in BRAND_PALETTE.items():
    cnt = int(bc.get(brand, 0))
    pct = cnt / total * 100
    items += f"""
    <div style="margin-bottom:10px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:5px">
        <div style="display:flex;align-items:center;gap:8px">
          <div style="width:11px;height:11px;border-radius:2px;background:{pal['fill']}"></div>
          <span style="font-size:13px;font-weight:600">{brand}</span>
        </div>
        <span style="font-size:11px;color:#94a3b8">{cnt}개 {pct:.1f}%</span>
      </div>
      <div style="height:3px;background:#1e293b;border-radius:2px">
        <div style="height:100%;width:{min(int(pct*2),180)}px;background:{pal['fill']};border-radius:2px;max-width:180px"></div>
      </div>
    </div>"""
other_cnt = total - sum(bc.get(b, 0) for b in BRAND_PALETTE)
other_pct = other_cnt / total * 100
items += f"""
    <div style="margin-top:4px;display:flex;justify-content:space-between;align-items:center">
      <div style="display:flex;align-items:center;gap:8px">
        <div style="width:11px;height:11px;border-radius:2px;background:#6b7280"></div>
        <span style="font-size:13px;font-weight:600">기타</span>
      </div>
      <span style="font-size:11px;color:#94a3b8">{other_cnt}개 {other_pct:.1f}%</span>
    </div>"""

legend = f"""
<div style="position:fixed;top:80px;right:16px;z-index:1000;
  background:rgba(10,14,20,0.96);border:1px solid rgba(255,255,255,0.07);
  border-radius:12px;padding:20px;width:240px;
  font-family:-apple-system,'Segoe UI',sans-serif;color:#e2e8f0;
  backdrop-filter:blur(16px);box-shadow:0 8px 32px rgba(0,0,0,0.6)">
  <div style="font-size:10px;letter-spacing:2px;color:#38bdf8;margin-bottom:14px;font-family:'Courier New',monospace">브랜드 세력권</div>
  <div style="font-size:19px;font-weight:700;margin-bottom:3px">고양시</div>
  <div style="font-size:12px;color:#64748b;margin-bottom:18px">편의점 {total}개 · 보로노이 기반</div>
  {items}
  <div style="border-top:1px solid rgba(255,255,255,0.05);margin-top:14px;padding-top:10px;font-size:10px;color:#475569;font-family:'Courier New',monospace">각 구역 = 가장 가까운 편의점 담당 영역</div>
</div>"""
m_brand.get_root().html.add_child(folium.Element(legend))

out1 = f'{BASE}/goyang_brand_map.html'
m_brand.save(out1)
print(f"  [OK] 저장: {out1}")

# ════════════════════════════════════════════════════════════════════════════════
# 3. 세대수 가중 수요압력 지도
# ════════════════════════════════════════════════════════════════════════════════
print("\n\n[ 세대수 가중 수요압력 지도 생성 중... ]")

# 세대수가 있는 편의점만 사용
stores_with_units = stores_df[stores_df['units'] > 0].reset_index(drop=True)
print(f"  세대수 > 0 편의점: {len(stores_with_units)}개")

# 보로노이 재계산 (전체 951개로 클리핑된 다각형의 '면적'을 이용)
# 수요압력 = 세대수 / sqrt(보로노이 면적) — 면적이 작고 세대수 많을수록 고압력
coords2       = stores_df[['lat', 'lng']].values
all_pts2      = np.vstack([coords2, boundary_pts])
vor2          = Voronoi(all_pts2)

CLIP2 = box(126.72, 37.55, 126.99, 37.75)

# 각 편의점의 Voronoi 셀 면적(도 단위 근사) 계산
areas = []
for i in range(len(stores_df)):
    region_idx = vor2.point_region[i]
    region     = vor2.regions[region_idx]
    if -1 in region or len(region) < 3:
        areas.append(None); continue
    poly_coords  = vor2.vertices[region]
    poly_shapely = ShapelyPolygon([(c[1], c[0]) for c in poly_coords])
    clipped      = poly_shapely.intersection(CLIP2)
    areas.append(clipped.area if not clipped.is_empty else None)

stores_df2 = stores_df.copy()
stores_df2['area_deg2'] = areas
# 면적 → km² 변환 (1도 ≈ 111km lat, 88km lng → 1 deg² ≈ 9768 km²)
stores_df2['area_km2'] = stores_df2['area_deg2'].apply(
    lambda a: a * 111 * 88 if a else None
)
# 수요압력 = 세대수 / sqrt(면적_km²)  —  0면적 방지
stores_df2['pressure'] = stores_df2.apply(
    lambda r: r['units'] / (np.sqrt(max(r['area_km2'], 0.001))) if r['area_km2'] else 0,
    axis=1
)

print(f"  수요압력 최고 10개:")
top10 = stores_df2.nlargest(10, 'pressure')[['name','brand','units','area_km2','pressure']]
top10['area_km2'] = top10['area_km2'].round(3)
top10['pressure'] = top10['pressure'].round(1)
print(top10.to_string(index=False))

# ── 히트맵 데이터 ─────────────────────────────────────────────────────────────
p_max = stores_df2['pressure'].quantile(0.97)
heat_data = []
for _, r in stores_df2.iterrows():
    if r['units'] > 0:
        w = min(r['pressure'] / p_max, 1.0)
        heat_data.append([r['lat'], r['lng'], w])

# ── K-means: 고압력 편의점 클러스터링 ────────────────────────────────────────
threshold = stores_df2['pressure'].median()
high_p    = stores_df2[stores_df2['pressure'] > threshold].copy().reset_index(drop=True)
N_CLUSTERS = 10
km = KMeans(n_clusters=N_CLUSTERS, random_state=42, n_init=10)
km.fit(high_p[['lat', 'lng']], sample_weight=high_p['pressure'])
high_p['cluster'] = km.labels_

centroids = high_p.groupby('cluster').agg(
    total_units=('units', 'sum'),
    avg_area=('area_km2', 'mean'),
    score=('pressure', 'sum'),
    count=('name', 'count'),
).reset_index()
centroids['lat'] = km.cluster_centers_[:, 0]
centroids['lng'] = km.cluster_centers_[:, 1]
centroids = centroids.sort_values('score', ascending=False).reset_index(drop=True)
centroids['rank'] = range(1, len(centroids) + 1)

print(f"\n  추천 입지 TOP {N_CLUSTERS}:")
print(centroids[['rank','lat','lng','total_units','score']].to_string(index=False))

# ── 지도 생성 ─────────────────────────────────────────────────────────────────
m_demand = folium.Map(
    location=[37.655, 126.835],
    zoom_start=12,
    tiles='https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', attr='Tiles &copy; Esri',
)

HeatMap(
    heat_data,
    radius=30, blur=24, min_opacity=0.15,
    gradient={0.0: '#0ea5e9', 0.35: '#8b5cf6', 0.65: '#f59e0b', 0.88: '#ef4444', 1.0: '#ffffff'},
).add_to(m_demand)

# 기존 편의점 (흰 점)
for _, r in stores_df.iterrows():
    folium.CircleMarker(
        location=[r['lat'], r['lng']], radius=3,
        color='rgba(255,255,255,0.3)', weight=1,
        fill=True, fill_color='white', fill_opacity=0.25,
        tooltip=f"{r['name']} ({r['brand']})",
    ).add_to(m_demand)

# 추천 입지
rank_color = {1:'#ff3333', 2:'#ff5500', 3:'#ff8800',
              4:'#ffbb00', 5:'#ffbb00', 6:'#22d3ee',
              7:'#22d3ee', 8:'#22d3ee', 9:'#22d3ee', 10:'#22d3ee'}

for _, r in centroids.iterrows():
    rank  = int(r['rank'])
    color = rank_color.get(rank, '#22d3ee')
    units = int(r['total_units'])
    score = float(r['score'])

    folium.CircleMarker(
        location=[r['lat'], r['lng']],
        radius=18, color=color, weight=2.5,
        fill=True, fill_color='#00000099', fill_opacity=0.75,
        tooltip=f"추천 #{rank} | 영향 {units:,}세대",
        popup=folium.Popup(f"""
        <div style="font-family:-apple-system,sans-serif;padding:4px;min-width:180px">
          <div style="font-size:10px;color:#64748b;margin-bottom:4px">신규 입점 추천</div>
          <div style="font-size:24px;font-weight:700;color:{color}">#{rank}</div>
          <div style="font-size:12px;margin-top:8px">영향 세대수: <b>{units:,}세대</b></div>
          <div style="font-size:12px">수요압력 점수: <b>{score:.0f}</b></div>
          <div style="font-size:11px;color:#94a3b8;margin-top:4px">{r['lat']:.5f}, {r['lng']:.5f}</div>
        </div>""", max_width=220),
    ).add_to(m_demand)

    folium.Marker(
        location=[r['lat'], r['lng']],
        icon=folium.DivIcon(
            html=f'<div style="color:#fff;font-weight:700;font-size:11px;text-align:center;line-height:36px;width:36px;margin-top:-18px;margin-left:-18px">{rank}</div>',
            icon_size=(36,36), icon_anchor=(18,18),
        )
    ).add_to(m_demand)

legend2 = f"""
<div style="position:fixed;top:80px;right:16px;z-index:1000;
  background:rgba(10,14,20,0.96);border:1px solid rgba(255,255,255,0.07);
  border-radius:12px;padding:20px;width:248px;
  font-family:-apple-system,'Segoe UI',sans-serif;color:#e2e8f0;
  backdrop-filter:blur(16px);box-shadow:0 8px 32px rgba(0,0,0,0.6)">
  <div style="font-size:10px;letter-spacing:2px;color:#38bdf8;margin-bottom:14px;font-family:'Courier New',monospace">수요압력 분석</div>
  <div style="font-size:19px;font-weight:700;margin-bottom:3px">신규 입점 추천</div>
  <div style="font-size:12px;color:#64748b;margin-bottom:18px">세대수 ÷ √담당면적 가중 점수</div>
  <div style="margin-bottom:14px">
    <div style="font-size:11px;color:#94a3b8;margin-bottom:6px">히트맵 강도</div>
    <div style="height:7px;border-radius:4px;background:linear-gradient(90deg,#0ea5e9,#8b5cf6,#f59e0b,#ef4444,#fff)"></div>
    <div style="display:flex;justify-content:space-between;font-size:10px;color:#475569;margin-top:3px"><span>낮음</span><span>높음</span></div>
  </div>
  <div style="border-top:1px solid rgba(255,255,255,0.06);padding-top:12px">
    <div style="font-size:11px;color:#94a3b8;margin-bottom:8px">추천 순위</div>
    <div style="display:flex;flex-wrap:wrap;gap:6px">
      <span style="background:#ff3333;color:#fff;padding:2px 9px;border-radius:20px;font-size:11px;font-weight:700">1위</span>
      <span style="background:#ff5500;color:#fff;padding:2px 9px;border-radius:20px;font-size:11px;font-weight:700">2위</span>
      <span style="background:#ff8800;color:#fff;padding:2px 9px;border-radius:20px;font-size:11px;font-weight:700">3위</span>
      <span style="background:#ffbb00;color:#000;padding:2px 9px;border-radius:20px;font-size:11px;font-weight:700">4–5위</span>
      <span style="background:#22d3ee;color:#000;padding:2px 9px;border-radius:20px;font-size:11px;font-weight:700">6–10위</span>
    </div>
  </div>
  <div style="border-top:1px solid rgba(255,255,255,0.06);margin-top:12px;padding-top:10px;font-size:10px;color:#475569;font-family:'Courier New',monospace">흰 점 = 기존 편의점 · 번호 클릭 시 상세</div>
</div>"""
m_demand.get_root().html.add_child(folium.Element(legend2))

out2 = f'{BASE}/goyang_demand_map.html'
m_demand.save(out2)
print(f"  [OK] 저장: {out2}")

print("\n\n=== 완료 ===")
print(f"  goyang_brand_map.html")
print(f"  goyang_demand_map.html")
