"""
분석 1: 브랜드 세력권 지도
──────────────────────────
각 편의점의 보로노이 구역을 브랜드 색으로 채워
CU / GS25 / 세븐일레븐 / 이마트24 세력권을 시각화합니다.
사이드패널에 행정동별 브랜드 점유율도 표시합니다.

실행: Google Colab에서 기존 노트북 실행 후
      goyang_convenience_stores.csv 가 생성된 상태에서 실행하세요.
"""

import pandas as pd
import numpy as np
import folium
from scipy.spatial import Voronoi, cKDTree
from shapely.geometry import Polygon as ShapelyPolygon, box

# ── 데이터 로드 ────────────────────────────────────────────────────────────────
stores = pd.read_csv('goyang_convenience_stores.csv')
stores = stores[
    (stores['lat'].between(37.57, 37.73)) &
    (stores['lng'].between(126.74, 126.97))
].reset_index(drop=True)

print(f"편의점: {len(stores)}개")
print(stores['brand'].value_counts())

# ── 브랜드 색상 (배경색, 외곽선색) ────────────────────────────────────────────
BRAND_PALETTE = {
    'CU':       {'fill': '#2563eb', 'border': '#1d4ed8', 'label': 'CU'},
    'GS25':     {'fill': '#16a34a', 'border': '#15803d', 'label': 'GS25'},
    '세븐일레븐': {'fill': '#dc2626', 'border': '#b91c1c', 'label': '세븐일레븐'},
    '이마트24':  {'fill': '#f59e0b', 'border': '#d97706', 'label': '이마트24'},
}
DEFAULT_PALETTE = {'fill': '#6b7280', 'border': '#4b5563', 'label': '기타'}

# ── 보로노이 클리핑 박스 ────────────────────────────────────────────────────────
CLIP = box(126.72, 37.55, 126.99, 37.75)   # (minx, miny, maxx, maxy)

# ── 경계 더미 포인트 (무한 셀 방지) ────────────────────────────────────────────
coords = stores[['lat', 'lng']].values      # (N, 2)  lat·lng 순

margin = 1.0
boundary_pts = np.array([
    [37.57 - margin, 126.72 - margin],
    [37.57 - margin, 126.97 + margin],
    [37.73 + margin, 126.72 - margin],
    [37.73 + margin, 126.97 + margin],
    [37.65,           126.72 - margin],
    [37.65,           126.97 + margin],
    [37.57 - margin,  126.83],
    [37.73 + margin,  126.83],
])
all_pts = np.vstack([coords, boundary_pts])

# ── 보로노이 생성 ──────────────────────────────────────────────────────────────
vor = Voronoi(all_pts)

# ── 지도 생성 ─────────────────────────────────────────────────────────────────
m = folium.Map(
    location=[37.655, 126.835],
    zoom_start=12,
    tiles='https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', attr='Tiles &copy; Esri',
)

# ── 보로노이 셀 그리기 ─────────────────────────────────────────────────────────
drawn = 0
for i in range(len(stores)):
    region_idx = vor.point_region[i]
    region     = vor.regions[region_idx]
    if -1 in region or len(region) < 3:
        continue

    poly_coords   = vor.vertices[region]          # [[lat, lng], ...]
    # Shapely는 (x=lng, y=lat) 순서
    poly_shapely  = ShapelyPolygon([(c[1], c[0]) for c in poly_coords])
    clipped       = poly_shapely.intersection(CLIP)

    if clipped.is_empty:
        continue

    brand   = stores.iloc[i]['brand']
    palette = BRAND_PALETTE.get(brand, DEFAULT_PALETTE)

    def extract_coords(geom):
        """Polygon/MultiPolygon → [[lat, lng], ...] 리스트"""
        if geom.geom_type == 'Polygon':
            return [[lat, lng] for lng, lat in geom.exterior.coords]
        elif geom.geom_type == 'MultiPolygon':
            return [[lat, lng] for lng, lat in list(geom.geoms[0].exterior.coords)]
        return None

    folium_coords = extract_coords(clipped)
    if not folium_coords:
        continue

    row = stores.iloc[i]
    folium.Polygon(
        locations=folium_coords,
        color=palette['border'],
        weight=0.5,
        fill=True,
        fill_color=palette['fill'],
        fill_opacity=0.35,
        tooltip=f"<b>{row['name']}</b><br>{brand}<br>{row.get('dong','')}",
    ).add_to(m)
    drawn += 1

print(f"보로노이 셀 {drawn}개 그림")

# ── 편의점 마커 ───────────────────────────────────────────────────────────────
for _, row in stores.iterrows():
    palette = BRAND_PALETTE.get(row['brand'], DEFAULT_PALETTE)
    folium.CircleMarker(
        location=[row['lat'], row['lng']],
        radius=4,
        color='white',
        weight=1,
        fill=True,
        fill_color=palette['fill'],
        fill_opacity=1.0,
        tooltip=f"<b>{row['name']}</b><br>{row['brand']}<br>{row.get('dong','')}",
    ).add_to(m)

# ── 브랜드 범례 HTML ──────────────────────────────────────────────────────────
brand_counts = stores['brand'].value_counts()
total        = len(stores)

legend_items = ''
for brand, palette in BRAND_PALETTE.items():
    cnt  = brand_counts.get(brand, 0)
    pct  = cnt / total * 100
    bar_w = int(pct * 1.8)
    legend_items += f"""
    <div style="margin-bottom:10px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
        <div style="display:flex;align-items:center;gap:8px">
          <div style="width:12px;height:12px;border-radius:3px;background:{palette['fill']};flex-shrink:0"></div>
          <span style="font-size:13px;font-weight:600">{palette['label']}</span>
        </div>
        <span style="font-size:12px;color:#94a3b8">{cnt}개 ({pct:.1f}%)</span>
      </div>
      <div style="height:3px;background:#1e293b;border-radius:2px">
        <div style="height:100%;width:{bar_w}px;background:{palette['fill']};border-radius:2px"></div>
      </div>
    </div>"""

# 기타 브랜드
other_cnt = brand_counts[~brand_counts.index.isin(BRAND_PALETTE)].sum()
other_pct = other_cnt / total * 100
legend_items += f"""
    <div style="margin-bottom:10px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
        <div style="display:flex;align-items:center;gap:8px">
          <div style="width:12px;height:12px;border-radius:3px;background:#6b7280;flex-shrink:0"></div>
          <span style="font-size:13px;font-weight:600">기타</span>
        </div>
        <span style="font-size:12px;color:#94a3b8">{other_cnt}개 ({other_pct:.1f}%)</span>
      </div>
      <div style="height:3px;background:#1e293b;border-radius:2px">
        <div style="height:100%;width:{int(other_pct*1.8)}px;background:#6b7280;border-radius:2px"></div>
      </div>
    </div>"""

legend_html = f"""
<div style="
  position:fixed; top:80px; right:16px; z-index:1000;
  background:rgba(15,20,30,0.95);
  border:1px solid rgba(255,255,255,0.08);
  border-radius:12px; padding:20px 20px 16px;
  width:240px;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  color:#e2e8f0;
  backdrop-filter:blur(10px);
  box-shadow:0 8px 32px rgba(0,0,0,0.5);
">
  <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#38bdf8;margin-bottom:16px;font-family:'Courier New',monospace">
    브랜드 세력권
  </div>
  <div style="font-size:20px;font-weight:700;margin-bottom:4px">고양시</div>
  <div style="font-size:12px;color:#64748b;margin-bottom:20px">편의점 총 {total}개</div>
  {legend_items}
  <div style="border-top:1px solid rgba(255,255,255,0.06);margin-top:12px;padding-top:12px;font-size:10px;color:#475569;font-family:'Courier New',monospace">
    보로노이 다이어그램 기반
  </div>
</div>"""

m.get_root().html.add_child(folium.Element(legend_html))

# ── 저장 ─────────────────────────────────────────────────────────────────────
m.save('goyang_brand_map.html')
print("✅ goyang_brand_map.html 저장 완료")
