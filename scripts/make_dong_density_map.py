"""
분석: 행정동별 편의점 밀도 코로플레스 지도
- 44개 행정동별 편의점 수 / 면적(km²) = 공급 밀도
- 행정동 경계: data/goyang_dong.geojson (scripts/fetch_osm.py)
- Shapely point-in-polygon으로 편의점을 동에 배정
- Folium Choropleth으로 시각화
"""

import json
from pathlib import Path

import folium
import numpy as np
import pandas as pd
import shapely
from folium import Choropleth, GeoJson, GeoJsonTooltip
from pyproj import Transformer
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
TO_M = Transformer.from_crs(4326, 5179, always_xy=True)

# ── 1. 데이터 로드 (scripts/extract_data.py, scripts/fetch_osm.py 결과) ────────
stores = pd.read_csv(DATA / 'stores.csv').to_dict('records')
dong_geojson = json.loads((DATA / 'goyang_dong.geojson').read_text(encoding='utf-8'))
features = dong_geojson['features']
print(f"편의점 {len(stores)}개 / 행정동 {len(features)}개")

# ── 2. Point-in-Polygon + 면적(EPSG:5179 투영 후 계산) ────────────────────────
# ※ 이전 버전은 Overpass outer 웨이 좌표를 순서 없이 이어 붙여 경계가 꼬였고,
#   그 결과 면적이 틀려 '일산2동 5,575개/km²' 같은 값이 나왔습니다.
store_pts = shapely.points([[s['lng'], s['lat']] for s in stores])
for feat in features:
    poly = shape(feat['geometry'])
    cnt = int(shapely.contains(poly, store_pts).sum())
    area = shapely.transform(poly, lambda c: np.column_stack(TO_M.transform(c[:, 0], c[:, 1]))).area / 1e6
    feat['properties']['store_count'] = cnt
    feat['properties']['area_km2'] = round(area, 2)
    feat['properties']['density'] = round(cnt / area, 2)
print(f"  배정 완료: {sum(f['properties']['store_count'] for f in features)}/{len(stores)}개")

# ── 4. 통계 ──────────────────────────────────────────────────────────────────
densities = [f['properties']['density'] for f in features if f['properties']['density'] > 0]
print(f"\n  밀도 평균 {np.mean(densities):.2f} / 최대 {max(densities):.2f} / 최소 {min(densities):.2f} (개/km²)")

# ── 5. 지도 생성 ──────────────────────────────────────────────────────────────
print("\n지도 생성 중...")
# CartoDB 타일은 API 키가 없으면 워터마크가 표시되어 Esri 다크 그레이 타일 사용
m = folium.Map(location=[37.655, 126.835], zoom_start=12, tiles=None)
folium.TileLayer(
    tiles='https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/'
          'World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}',
    attr='Tiles &copy; Esri', name='Esri Dark Gray', max_zoom=16, control=False,
).add_to(m)

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
    단위: 개/km² · 마우스오버로 상세<br>
    ※ 가좌·송포동 등 서쪽·북쪽 끝은 원본 데이터 수집 범위 밖이라 실제보다 낮게 표시될 수 있음
  </div>
</div>"""

m.get_root().html.add_child(folium.Element(legend_html))

out = ROOT / 'goyang_dong_density_map.html'
m.save(out)
print(f"\n[OK] 저장: {out}")
print("밀도 TOP 5:")
for d in sorted_dongs[:5]:
    print(f"  {d['name']}: {d['density']:.2f}개/km² ({d['store_count']}개, {d['area_km2']}km²)")
