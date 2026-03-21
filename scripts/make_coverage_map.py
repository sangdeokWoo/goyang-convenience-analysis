"""
분석: 서비스 권역(400m) + 행정동 경계 오버레이 지도
- 각 편의점 반경 400m 서비스 권역 시각화
- Overpass API로 고양시 행정동 경계 + 동 이름 표시
- 커버리지 공백 지역 직관적 파악 가능
"""

import re
import json
import requests
import numpy as np
import folium
from folium.plugins import FeatureGroupSubGroup
from collections import Counter

BASE = r'C:\Users\woosd\OneDrive\바탕 화면\작업\goyang-convenience-analysis'

# ── 1. 편의점 데이터 파싱 (satellite_map.html) ─────────────────────────────────
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

# ── 2. 행정동 경계 (Overpass API) ─────────────────────────────────────────────
print("\n행정동 경계 로드 중 (Overpass API)...")
dong_geojson = None
try:
    query = """[out:json][timeout:120];
area["name"="고양시"]["admin_level"="6"]->.goyang;
(
  relation["admin_level"="8"]["boundary"="administrative"](area.goyang);
);
out body geom;
"""
    r = requests.post("https://overpass-api.de/api/interpreter",
                      data={'data': query}, timeout=150)
    r.raise_for_status()
    osm = r.json()

    # OSM relation → GeoJSON 변환
    features = []
    for el in osm.get('elements', []):
        if el.get('type') != 'relation': continue
        name = el.get('tags', {}).get('name', '알 수 없음')
        # outer way 멤버의 geometry로 폴리곤 구성
        outer_coords = []
        for member in el.get('members', []):
            if member.get('role') == 'outer' and 'geometry' in member:
                ring = [[g['lon'], g['lat']] for g in member['geometry']]
                if ring: outer_coords.extend(ring)
        if len(outer_coords) < 3: continue
        features.append({
            "type": "Feature",
            "properties": {"name": name},
            "geometry": {"type": "Polygon", "coordinates": [outer_coords]}
        })

    dong_geojson = {"type": "FeatureCollection", "features": features}
    print(f"  행정동 {len(features)}개 로드 완료")
except Exception as e:
    print(f"  Overpass API 실패: {e}\n  (동 경계 없이 진행)")

# ── 3. 지도 생성 ─────────────────────────────────────────────────────────────
print("\n지도 생성 중...")

BRAND_COLOR = {
    'CU': '#2563eb', 'GS25': '#16a34a',
    '세븐일레븐': '#dc2626', '이마트24': '#d97706',
}
DEFAULT_COLOR = '#6b7280'

m = folium.Map(location=[37.655, 126.835], zoom_start=12, tiles='CartoDB dark_matter')

# ── 3-A. 행정동 경계 레이어 ───────────────────────────────────────────────────
dong_group = folium.FeatureGroup(name='행정동 경계', show=True)
if dong_geojson and dong_geojson['features']:
    folium.GeoJson(
        dong_geojson,
        name='행정동 경계',
        style_function=lambda x: {
            'fillOpacity': 0,
            'color': 'rgba(255,255,255,0.25)',
            'weight': 1.2,
            'dashArray': '4 3',
        },
        tooltip=folium.GeoJsonTooltip(
            fields=['name'],
            aliases=['행정동:'],
            style="font-family:-apple-system,sans-serif;font-size:13px;background:#1e293b;color:#e2e8f0;border:none;border-radius:6px;padding:6px 10px;",
        ),
    ).add_to(dong_group)

    # 동 이름 레이블 (중심점에 DivIcon)
    for feat in dong_geojson['features']:
        coords = feat['geometry']['coordinates'][0]
        if not coords: continue
        lats = [c[1] for c in coords]
        lngs = [c[0] for c in coords]
        clat, clng = np.mean(lats), np.mean(lngs)
        name = feat['properties'].get('name', '')
        short = name.replace('행정동', '').replace('제', '')
        folium.Marker(
            location=[clat, clng],
            icon=folium.DivIcon(
                html=f'<div style="font-size:10px;font-weight:600;color:rgba(255,255,255,0.55);white-space:nowrap;font-family:-apple-system,sans-serif;text-shadow:0 1px 3px #000">{short}</div>',
                icon_size=(80, 20),
                icon_anchor=(40, 10),
            )
        ).add_to(dong_group)
dong_group.add_to(m)

# ── 3-B. 서비스 권역 (400m 반경) ────────────────────────────────────────────
circle_group = folium.FeatureGroup(name='서비스 권역 (반경 400m)', show=True)
for s in stores:
    color = BRAND_COLOR.get(s['brand'], DEFAULT_COLOR)
    folium.Circle(
        location=[s['lat'], s['lng']],
        radius=400,
        color=color,
        weight=0.6,
        fill=True,
        fill_color=color,
        fill_opacity=0.08,
    ).add_to(circle_group)
circle_group.add_to(m)

# ── 3-C. 편의점 마커 ──────────────────────────────────────────────────────────
marker_group = folium.FeatureGroup(name='편의점 위치', show=True)
for s in stores:
    color = BRAND_COLOR.get(s['brand'], DEFAULT_COLOR)
    folium.CircleMarker(
        location=[s['lat'], s['lng']],
        radius=4,
        color='white', weight=1,
        fill=True, fill_color=color, fill_opacity=1.0,
        tooltip=f"<b>{s['name']}</b><br>{s['brand']}",
    ).add_to(marker_group)
marker_group.add_to(m)

folium.LayerControl(collapsed=False).add_to(m)

# ── 4. 커버리지 통계 계산 ────────────────────────────────────────────────────
# 500m 격자로 커버리지 비율 추정
grid_lats = np.arange(37.57, 37.73, 0.0045)
grid_lngs = np.arange(126.74, 126.97, 0.0045)
grid = [(lat, lng) for lat in grid_lats for lng in grid_lngs]
store_coords = np.array([[s['lat'], s['lng']] for s in stores])
from scipy.spatial import cKDTree
tree = cKDTree(store_coords * [111000, 88000])
grid_np = np.array(grid) * [111000, 88000]
dists, _ = tree.query(grid_np)
covered = (dists <= 400).sum()
total_pts = len(grid)
coverage_pct = covered / total_pts * 100

brand_counts = Counter(s['brand'] for s in stores)

# ── 5. 범례 HTML ────────────────────────────────────────────────────────────
legend_html = f"""
<div style="position:fixed;top:80px;right:16px;z-index:1000;
  background:rgba(10,14,20,0.96);border:1px solid rgba(255,255,255,0.07);
  border-radius:12px;padding:20px;width:248px;
  font-family:-apple-system,'Segoe UI',sans-serif;color:#e2e8f0;
  backdrop-filter:blur(16px);box-shadow:0 8px 32px rgba(0,0,0,0.6)">
  <div style="font-size:10px;letter-spacing:2px;color:#38bdf8;margin-bottom:14px;font-family:'Courier New',monospace">서비스 권역 분석</div>
  <div style="font-size:19px;font-weight:700;margin-bottom:16px">400m 커버리지</div>

  <div style="background:rgba(16,217,160,0.1);border:1px solid rgba(16,217,160,0.2);border-radius:8px;padding:12px;margin-bottom:16px">
    <div style="font-size:28px;font-weight:700;color:#10d9a0">{coverage_pct:.1f}%</div>
    <div style="font-size:11px;color:#64748b;margin-top:2px">격자점 기준 400m 내 커버</div>
  </div>

  <div style="margin-bottom:16px">
    <div style="font-size:11px;color:#94a3b8;margin-bottom:8px">브랜드별 편의점 수</div>
"""
for brand, color in BRAND_COLOR.items():
    cnt = brand_counts.get(brand, 0)
    legend_html += f"""
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
      <div style="display:flex;align-items:center;gap:7px">
        <div style="width:10px;height:10px;border-radius:2px;background:{color}"></div>
        <span style="font-size:12px">{brand}</span>
      </div>
      <span style="font-size:12px;color:#94a3b8">{cnt}개</span>
    </div>"""

legend_html += f"""
  </div>
  <div style="border-top:1px solid rgba(255,255,255,0.06);padding-top:10px;font-size:10px;color:#475569;font-family:'Courier New',monospace">
    원 반경 = 도보 5분 (400m)<br>점선 = 행정동 경계
  </div>
</div>"""

m.get_root().html.add_child(folium.Element(legend_html))

out = f'{BASE}/goyang_coverage_map.html'
m.save(out)
print(f"\n[OK] 저장: {out}")
print(f"  커버리지: {coverage_pct:.1f}% (격자 {total_pts}개 기준 400m 내)")
