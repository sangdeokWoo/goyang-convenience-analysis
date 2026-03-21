"""
분석: 행정동별 편의점 밀도 코로플레스 지도
- 44개 행정동별 편의점 수 / 면적(km²) = 공급 밀도
- Overpass API로 행정동 GeoJSON 취득
- Shapely point-in-polygon으로 편의점을 동에 배정
- Folium Choropleth으로 시각화
"""

import re
import json
import requests
import numpy as np
import folium
from folium import Choropleth, GeoJson, GeoJsonTooltip
from collections import defaultdict

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

# ── 2. 행정동 경계 (Overpass API) ─────────────────────────────────────────────
print("\n행정동 경계 로드 중...")
query = """[out:json][timeout:120];
area["name"="고양시"]["admin_level"="6"]->.goyang;
(
  relation["admin_level"="8"]["boundary"="administrative"](area.goyang);
);
out body geom;
"""
r = requests.post("https://overpass-api.de/api/interpreter", data={'data': query}, timeout=150)
r.raise_for_status()
osm = r.json()

features = []
for el in osm.get('elements', []):
    if el.get('type') != 'relation': continue
    name = el.get('tags', {}).get('name', '알 수 없음')
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
print(f"  행정동 {len(features)}개")

# ── 3. Point-in-Polygon으로 편의점을 행정동에 배정 ───────────────────────────
print("\nPoint-in-Polygon 분석 중...")
try:
    from shapely.geometry import shape, Point

    dong_shapes = []
    for feat in features:
        try:
            poly = shape(feat['geometry'])
            dong_shapes.append((feat['properties']['name'], poly, feat))
        except Exception:
            continue

    dong_store_count = defaultdict(int)
    assigned = 0
    for s in stores:
        pt = Point(s['lng'], s['lat'])
        for name, poly, _ in dong_shapes:
            if poly.contains(pt):
                dong_store_count[name] += 1
                assigned += 1
                break

    print(f"  배정 완료: {assigned}/{len(stores)}개")

    # 면적 계산 (km²)
    def poly_area_km2(poly):
        coords = list(poly.exterior.coords)
        lat_c  = np.mean([c[1] for c in coords])
        lat_m  = 111000
        lng_m  = 111000 * np.cos(np.radians(lat_c))
        area = 0
        for i in range(len(coords) - 1):
            x1, y1 = coords[i][0] * lng_m,   coords[i][1] * lat_m
            x2, y2 = coords[i+1][0] * lng_m, coords[i+1][1] * lat_m
            area += x1 * y2 - x2 * y1
        return abs(area) / 2 / 1e6

    for name, poly, feat in dong_shapes:
        cnt  = dong_store_count.get(name, 0)
        area = poly_area_km2(poly)
        density = cnt / area if area > 0 else 0
        feat['properties']['store_count'] = cnt
        feat['properties']['area_km2']    = round(area, 2)
        feat['properties']['density']     = round(density, 2)

except ImportError:
    print("  [!] shapely 미설치 → 근사 배정 사용 (pip install shapely)")
    # fallback: 경계 bbox 기반 근사
    for feat in features:
        coords = feat['geometry']['coordinates'][0]
        lngs   = [c[0] for c in coords]
        lats   = [c[1] for c in coords]
        min_lng, max_lng = min(lngs), max(lngs)
        min_lat, max_lat = min(lats), max(lats)
        cnt = sum(1 for s in stores
                  if min_lng <= s['lng'] <= max_lng and min_lat <= s['lat'] <= max_lat)
        area = (max_lat - min_lat) * 111 * (max_lng - min_lng) * 88
        feat['properties']['store_count'] = cnt
        feat['properties']['area_km2']    = round(area, 2)
        feat['properties']['density']     = round(cnt / area if area > 0 else 0, 2)

dong_geojson = {"type": "FeatureCollection", "features": features}

# ── 4. 통계 ──────────────────────────────────────────────────────────────────
densities = [f['properties']['density'] for f in features if f['properties']['density'] > 0]
print(f"\n  밀도 평균 {np.mean(densities):.2f} / 최대 {max(densities):.2f} / 최소 {min(densities):.2f} (개/km²)")

# ── 5. 지도 생성 ──────────────────────────────────────────────────────────────
print("\n지도 생성 중...")
m = folium.Map(location=[37.655, 126.835], zoom_start=12, tiles='CartoDB dark_matter')

# Choropleth
Choropleth(
    geo_data=dong_geojson,
    data={f['properties']['name']: f['properties']['density'] for f in features},
    columns=['name', 'density'],
    key_on='feature.properties.name',
    fill_color='YlOrRd',
    fill_opacity=0.75,
    line_opacity=0.4,
    line_color='rgba(255,255,255,0.2)',
    legend_name='편의점 밀도 (개/km²)',
    nan_fill_color='rgba(30,41,59,0.5)',
    name='편의점 밀도 (개/km²)',
).add_to(m)

# 행정동 경계 + 툴팁
GeoJson(
    dong_geojson,
    style_function=lambda x: {
        'fillOpacity': 0,
        'color': 'rgba(255,255,255,0.15)',
        'weight': 1,
    },
    tooltip=GeoJsonTooltip(
        fields=['name', 'store_count', 'area_km2', 'density'],
        aliases=['행정동', '편의점 수', '면적 (km²)', '밀도 (개/km²)'],
        style="font-family:-apple-system,sans-serif;font-size:13px;"
              "background:#1e293b;color:#e2e8f0;border:none;border-radius:6px;padding:8px 12px;",
    ),
    name='행정동 경계',
).add_to(m)

# 편의점 마커
BRAND_COLOR = {
    'CU': '#2563eb', 'GS25': '#16a34a',
    '세븐일레븐': '#dc2626', '이마트24': '#d97706',
}
marker_grp = folium.FeatureGroup(name='편의점 위치', show=True)
for s in stores:
    color = BRAND_COLOR.get(s['brand'], '#6b7280')
    folium.CircleMarker(
        location=[s['lat'], s['lng']],
        radius=3,
        color='white', weight=0.5,
        fill=True, fill_color=color, fill_opacity=0.9,
        tooltip=f"<b>{s['name']}</b><br>{s['brand']}",
    ).add_to(marker_grp)
marker_grp.add_to(m)

folium.LayerControl(collapsed=False).add_to(m)

# ── 6. 범례 패널 ─────────────────────────────────────────────────────────────
# 밀도 TOP 5, BOTTOM 5
sorted_dongs = sorted(
    [f['properties'] for f in features if f['properties'].get('density', 0) > 0],
    key=lambda x: x['density'], reverse=True
)
top5_rows = ''.join(
    f'<div style="display:flex;justify-content:space-between;margin-bottom:4px">'
    f'<span style="font-size:11px">{d["name"]}</span>'
    f'<span style="font-size:11px;color:#fbbf24">{d["density"]:.1f}</span></div>'
    for d in sorted_dongs[:5]
)
bot5_rows = ''.join(
    f'<div style="display:flex;justify-content:space-between;margin-bottom:4px">'
    f'<span style="font-size:11px">{d["name"]}</span>'
    f'<span style="font-size:11px;color:#60a5fa">{d["density"]:.1f}</span></div>'
    for d in sorted_dongs[-5:]
)

legend_html = f"""
<div style="position:fixed;top:80px;right:16px;z-index:1000;
  background:rgba(10,14,20,0.96);border:1px solid rgba(255,255,255,0.07);
  border-radius:12px;padding:20px;width:256px;
  font-family:-apple-system,'Segoe UI',sans-serif;color:#e2e8f0;
  backdrop-filter:blur(16px);box-shadow:0 8px 32px rgba(0,0,0,0.6)">
  <div style="font-size:10px;letter-spacing:2px;color:#38bdf8;margin-bottom:14px;font-family:'Courier New',monospace">밀도 분석</div>
  <div style="font-size:18px;font-weight:700;margin-bottom:4px">편의점 공급 밀도</div>
  <div style="font-size:11px;color:#64748b;margin-bottom:18px">편의점 수 ÷ 행정동 면적(km²)</div>

  <div style="margin-bottom:14px">
    <div style="font-size:10px;color:#fbbf24;letter-spacing:1px;margin-bottom:6px;font-family:'Courier New',monospace">▲ HIGH DENSITY TOP 5</div>
    {top5_rows}
  </div>
  <div>
    <div style="font-size:10px;color:#60a5fa;letter-spacing:1px;margin-bottom:6px;font-family:'Courier New',monospace">▼ LOW DENSITY BOTTOM 5</div>
    {bot5_rows}
  </div>
  <div style="border-top:1px solid rgba(255,255,255,0.06);margin-top:10px;padding-top:8px;font-size:10px;color:#475569;font-family:'Courier New',monospace">
    단위: 개/km² · 마우스오버로 상세
  </div>
</div>"""

m.get_root().html.add_child(folium.Element(legend_html))

out = f'{BASE}/goyang_dong_density_map.html'
m.save(out)
print(f"\n[OK] 저장: {out}")
print("밀도 TOP 5:")
for d in sorted_dongs[:5]:
    print(f"  {d['name']}: {d['density']:.2f}개/km² ({d['store_count']}개, {d['area_km2']}km²)")
