"""
분석: 브랜드별 공백 지도
- 각 브랜드(CU/GS25/세븐일레븐/이마트24)까지의 거리를 히트맵으로
- 거리 멀수록 = 해당 브랜드의 공백/사각지대
- 레이어 컨트롤로 브랜드 전환
"""

import re
import numpy as np
import folium
from folium.plugins import HeatMap
from scipy.spatial import cKDTree
from collections import Counter

BASE = r'C:\Users\woosd\OneDrive\바탕 화면\작업\goyang-convenience-analysis'

# ── 1. 편의점 데이터 파싱 ─────────────────────────────────────────────────────
print("편의점 데이터 파싱 중...")
sat_html = open(f'{BASE}/goyang_satellite_map.html', encoding='utf-8').read()

coord_pat   = re.compile(r'L\.circleMarker\(\s*\[([0-9.]+),\s*([0-9.]+)\]')
tooltip_pat = re.compile(r'bindTooltip\(\s*`<div>\s*(.*?)\s*</div>`', re.DOTALL)
coords_raw   = coord_pat.findall(sat_html)
tooltips_raw = tooltip_pat.findall(sat_html)

name_brand_pat = re.compile(r'(.+?)\s*\((.+?)\)')
stores = []
for i, tt in enumerate(tooltips_raw):
    m = name_brand_pat.match(tt.strip())
    if not m or i >= len(coords_raw): continue
    lat, lng = float(coords_raw[i][0]), float(coords_raw[i][1])
    if not (37.57 <= lat <= 37.73 and 126.74 <= lng <= 126.97): continue
    stores.append({'name': m.group(1).strip(), 'brand': m.group(2).strip(), 'lat': lat, 'lng': lng})

print(f"  편의점 {len(stores)}개")
brand_counts = Counter(s['brand'] for s in stores)
print(f"  {dict(brand_counts)}")

# ── 2. 분석 그리드 생성 ───────────────────────────────────────────────────────
print("\n브랜드별 공백 분석 중...")
grid_lats = np.arange(37.57, 37.73, 0.003)   # ~330m 간격
grid_lngs = np.arange(126.74, 126.97, 0.003)
grid = np.array([(lat, lng) for lat in grid_lats for lng in grid_lngs])
print(f"  격자점: {len(grid)}개")

BRANDS = {
    'CU':       {'color': '#2563eb', 'fill': '#1d4ed8'},
    'GS25':     {'color': '#16a34a', 'fill': '#14532d'},
    '세븐일레븐': {'color': '#dc2626', 'fill': '#991b1b'},
    '이마트24':  {'color': '#d97706', 'fill': '#92400e'},
}

# 브랜드별: 가장 가까운 해당 브랜드 편의점까지의 거리 계산
brand_data = {}  # brand → (grid, dists)

for brand in BRANDS:
    brand_stores = [(s['lat'], s['lng']) for s in stores if s['brand'] == brand]
    if not brand_stores:
        continue
    tree = cKDTree(np.array(brand_stores) * [111000, 88000])
    dists, _ = tree.query(grid * [111000, 88000])
    brand_data[brand] = dists
    # 통계
    print(f"  {brand}: 평균 {dists.mean():.0f}m, 최대 {dists.max():.0f}m, "
          f"1km+ 격자 {(dists > 1000).sum()}개 ({(dists>1000).mean()*100:.1f}%)")

# ── 3. 히트맵 데이터 준비 ─────────────────────────────────────────────────────
# 거리를 0~1 가중치로 변환 (멀수록 1에 가까움 → 히트맵에서 뜨겁게)
CLIP_DIST = 2500  # 2.5km까지 선형 스케일 → 거리 변화 충분히 표현

def dist_to_heat(dists, clip=CLIP_DIST):
    """거리 → 히트맵 가중치 (멀수록 높음, 제곱근으로 중간 영역 강조)"""
    w = np.clip(dists / clip, 0, 1)
    return np.sqrt(w)  # 제곱근 스케일: 가까운 쪽 변화를 더 뚜렷하게

heat_by_brand = {}
for brand, dists in brand_data.items():
    w = dist_to_heat(dists)
    heat_by_brand[brand] = [
        [float(grid[i, 0]), float(grid[i, 1]), float(w[i])]
        for i in range(len(grid)) if w[i] > 0.08
    ]

# ── 4. 지도 생성 ─────────────────────────────────────────────────────────────
print("\n지도 생성 중...")

m = folium.Map(location=[37.655, 126.835], zoom_start=12, tiles='https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', attr='Tiles &copy; Esri')

# 브랜드별 히트맵 레이어 — 흰색 없이 채도 높은 색으로만 구성
GRADIENTS = {
    'CU':        {0.0: 'rgba(0,0,0,0)', 0.25: '#1e3a8a', 0.55: '#2563eb', 0.8: '#60a5fa', 1.0: '#bfdbfe'},
    'GS25':      {0.0: 'rgba(0,0,0,0)', 0.25: '#14532d', 0.55: '#16a34a', 0.8: '#4ade80', 1.0: '#bbf7d0'},
    '세븐일레븐': {0.0: 'rgba(0,0,0,0)', 0.25: '#7f1d1d', 0.55: '#dc2626', 0.8: '#f87171', 1.0: '#fecaca'},
    '이마트24':  {0.0: 'rgba(0,0,0,0)', 0.25: '#78350f', 0.55: '#d97706', 0.8: '#fbbf24', 1.0: '#fde68a'},
}

for brand, heat_data in heat_by_brand.items():
    pal = BRANDS[brand]
    HeatMap(
        heat_data,
        name=f'{brand} 공백 강도',
        radius=18, blur=14, min_opacity=0.05, max_val=1.0,
        gradient=GRADIENTS.get(brand, {0:'rgba(0,0,0,0)', 1:'#fff'}),
        show=(brand == 'CU'),  # CU만 기본 표시
    ).add_to(m)

# 편의점 마커 (브랜드별 레이어)
for brand, pal in BRANDS.items():
    grp = folium.FeatureGroup(name=f'{brand} 매장 위치', show=(brand=='CU'))
    brand_stores = [s for s in stores if s['brand'] == brand]
    for s in brand_stores:
        folium.CircleMarker(
            location=[s['lat'], s['lng']],
            radius=4,
            color='white', weight=1,
            fill=True, fill_color=pal['fill'], fill_opacity=1.0,
            tooltip=f"<b>{s['name']}</b>",
        ).add_to(grp)
    grp.add_to(m)

# LayerControl
folium.LayerControl(collapsed=False).add_to(m)

# ── 5. 브랜드 요약 패널 ──────────────────────────────────────────────────────
# 각 브랜드의 "공백 비율" (1km+ 격자 비율)
brand_gap_pct = {}
for brand, dists in brand_data.items():
    brand_gap_pct[brand] = (dists > 1000).mean() * 100

rows = ''
for brand, pal in BRANDS.items():
    cnt  = brand_counts.get(brand, 0)
    gap  = brand_gap_pct.get(brand, 0)
    bar  = min(int(gap * 2), 200)
    rows += f"""
    <div style="margin-bottom:12px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
        <div style="display:flex;align-items:center;gap:7px">
          <div style="width:10px;height:10px;border-radius:2px;background:{pal['color']}"></div>
          <span style="font-size:12px;font-weight:600">{brand}</span>
          <span style="font-size:10px;color:#64748b">{cnt}개</span>
        </div>
        <span style="font-size:11px;color:#94a3b8">공백 {gap:.0f}%</span>
      </div>
      <div style="height:3px;background:#1e293b;border-radius:2px">
        <div style="height:100%;width:{bar}px;max-width:100%;background:{pal['color']};border-radius:2px"></div>
      </div>
    </div>"""

legend_html = f"""
<div style="position:fixed;top:80px;right:16px;z-index:1000;
  background:rgba(10,14,20,0.96);border:1px solid rgba(255,255,255,0.07);
  border-radius:12px;padding:20px;width:252px;
  font-family:-apple-system,'Segoe UI',sans-serif;color:#e2e8f0;
  backdrop-filter:blur(16px);box-shadow:0 8px 32px rgba(0,0,0,0.6)">
  <div style="font-size:10px;letter-spacing:2px;color:#38bdf8;margin-bottom:14px;font-family:'Courier New',monospace">브랜드별 공백 분석</div>
  <div style="font-size:19px;font-weight:700;margin-bottom:4px">브랜드 사각지대</div>
  <div style="font-size:12px;color:#64748b;margin-bottom:18px">히트맵 강도 = 해당 브랜드와의 거리</div>
  {rows}
  <div style="border-top:1px solid rgba(255,255,255,0.06);margin-top:8px;padding-top:10px;font-size:10px;color:#475569;font-family:'Courier New',monospace">
    공백 % = 격자점 중 1km 초과 비율<br>레이어 컨트롤로 브랜드 전환
  </div>
</div>"""

m.get_root().html.add_child(folium.Element(legend_html))

out = f'{BASE}/goyang_brand_gap_map.html'
m.save(out)
print(f"\n[OK] 저장: {out}")
for brand, gap in brand_gap_pct.items():
    print(f"  {brand}: 1km+ 공백 {gap:.1f}%")
