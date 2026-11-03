"""
분석: 서비스 권역(400m) + 행정동 경계 오버레이 지도
- 각 편의점 반경 400m 서비스 권역 시각화
- 행정동 경계: data/goyang_dong.geojson (scripts/fetch_osm.py) + 동 이름 표시
- 커버리지 공백 지역 직관적 파악 가능
"""

import json
from collections import Counter
from pathlib import Path

import folium
import pandas as pd
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent.parent
DATA, RESULTS = ROOT / 'data', ROOT / 'results'

# ── 1. 데이터 로드 (scripts/extract_data.py, fetch_osm.py, gap_analysis.py 결과) ──
stores = pd.read_csv(DATA / 'stores.csv').to_dict('records')
print(f"  편의점 {len(stores)}개")

# ── 2. 행정동 경계 ────────────────────────────────────────────────────────────
# ※ 이전 버전은 Overpass outer 웨이 좌표를 순서 없이 이어 붙여 경계선이 꼬였습니다.
dong_geojson = json.loads((DATA / 'goyang_dong.geojson').read_text(encoding='utf-8'))
print(f"  행정동 {len(dong_geojson['features'])}개")

# ── 3. 지도 생성 ─────────────────────────────────────────────────────────────
print("\n지도 생성 중...")

BRAND_COLOR = {
    'CU': '#2563eb', 'GS25': '#16a34a',
    '세븐일레븐': '#dc2626', '이마트24': '#d97706',
}
DEFAULT_COLOR = '#6b7280'

# CartoDB 타일은 API 키가 없으면 워터마크가 표시되어 Esri 다크 그레이 타일 사용
m = folium.Map(location=[37.655, 126.835], zoom_start=12, tiles=None)
folium.TileLayer(
    tiles='https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/'
          'World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}',
    attr='Tiles &copy; Esri', name='Esri Dark Gray', max_zoom=16, control=False,
).add_to(m)

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
        pt = shape(feat['geometry']).representative_point()   # 폴리곤 내부 보장
        clat, clng = pt.y, pt.x
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

# ── 4. 커버리지 통계 (scripts/gap_analysis.py 결과) ─────────────────────────────
# 이전 버전의 28.4%는 위경도 사각형 전체(산·농지·한강 포함) 500m 격자 기준이었습니다.
summary = json.loads((RESULTS / 'summary.json').read_text(encoding='utf-8'))
coverage_pct = summary['coverage_residential_pct']

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
    <div style="font-size:11px;color:#64748b;margin-top:2px">주거지역 기준 400m 내 커버 (100m 격자)</div>
    <div style="font-size:11px;color:#94a3b8;margin-top:6px">아파트 세대 기준 {summary['coverage_apt_units_pct']}%<br>
      시 전체 면적 기준 {summary['coverage_city_area_pct']}% · 이전 방식 {summary['coverage_old_method_pct']}%</div>
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

out = ROOT / 'goyang_coverage_map.html'
m.save(out)
print(f"\n[OK] 저장: {out}")
print(f"  주거지 커버리지: {coverage_pct:.1f}%")
