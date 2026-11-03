"""
분석 2: 세대수 가중 수요압력 지도
────────────────────────────────
'편의점 하나가 너무 많은 세대를 담당하는 구역'을 더 정밀하게 찾습니다.
  수요압력 점수 = Σ(아파트 세대수 / 해당 아파트→편의점 거리)

가까운 편의점이 없는데 세대수는 많을수록 점수가 폭발적으로 증가합니다.
히트맵으로 시각화하고, K-means로 최적 신규 입점 10곳을 추천합니다.

실행: Google Colab에서 기존 노트북 실행 후
      goyang_convenience_stores.csv, goyang_apt_kakao.csv 가 있는 상태에서 실행하세요.
"""

import pandas as pd
import numpy as np
import folium
from folium.plugins import HeatMap
from scipy.spatial import cKDTree
from sklearn.cluster import KMeans

# ── 데이터 로드 ────────────────────────────────────────────────────────────────
stores = pd.read_csv('goyang_convenience_stores.csv')
stores = stores[
    (stores['lat'].between(37.57, 37.73)) &
    (stores['lng'].between(126.74, 126.97))
].reset_index(drop=True)

apt = pd.read_csv('goyang_apt_kakao.csv').dropna(subset=['lat', 'lng'])
apt = apt[
    (apt['lat'].between(37.57, 37.73)) &
    (apt['lng'].between(126.74, 126.97))
].reset_index(drop=True)

print(f"편의점: {len(stores)}개 | 아파트 단지: {len(apt)}개 / {apt['세대수'].sum():,.0f}세대")

# ── 아파트 → 최근접 편의점 거리 계산 (미터) ────────────────────────────────────
def haversine_m(lat1, lng1, lat2, lng2):
    """두 지점 간 거리(미터) 계산"""
    R = 6_371_000
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi  = np.radians(lat2 - lat1)
    dlam  = np.radians(lng2 - lng1)
    a = np.sin(dphi/2)**2 + np.cos(phi1)*np.cos(phi2)*np.sin(dlam/2)**2
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))

store_coords = stores[['lat', 'lng']].values
apt_coords   = apt[['lat', 'lng']].values

# KD-Tree (평면 근사 – 고양시 범위 내에서 오차 미미)
tree = cKDTree(store_coords * [111000, 88000])  # 위도 111km, 경도 88km
dists_flat, idxs = tree.query(apt_coords * [111000, 88000])

apt = apt.copy()
apt['nearest_m']   = dists_flat
apt['store_idx']   = idxs
apt['store_name']  = apt['store_idx'].apply(lambda i: stores.iloc[i]['name'])
apt['store_brand'] = apt['store_idx'].apply(lambda i: stores.iloc[i]['brand'])

# ── 수요압력 점수 계산 ─────────────────────────────────────────────────────────
# 분모에 최소값(50m)을 더해 0 나누기 방지
apt['pressure'] = apt['세대수'] / (apt['nearest_m'] + 50)

print(f"\n수요압력 상위 아파트 단지 TOP 10:")
top_apt = apt.nlargest(10, 'pressure')[['단지명', '세대수', 'nearest_m', 'store_name', 'pressure']]
top_apt.columns = ['단지명', '세대수', '거리(m)', '담당편의점', '압력점수']
top_apt['거리(m)'] = top_apt['거리(m)'].round(0).astype(int)
top_apt['압력점수'] = top_apt['압력점수'].round(2)
print(top_apt.to_string(index=False))

# ── 히트맵 데이터 ─────────────────────────────────────────────────────────────
# pressure를 0~1 정규화
p_max = apt['pressure'].quantile(0.99)   # 상위 1% 클리핑으로 이상치 제거
heat_data = []
for _, row in apt.iterrows():
    w = min(row['pressure'] / p_max, 1.0)
    heat_data.append([row['lat'], row['lng'], w])

# ── K-means: 고압력 구역 클러스터링 → 신규 입점 추천 ──────────────────────────
# 압력 점수가 전체 중앙값 이상인 아파트만 대상
threshold = apt['pressure'].median()
high_pressure = apt[apt['pressure'] > threshold].copy()
print(f"\n고압력 단지 수: {len(high_pressure)}개 (중앙값 {threshold:.2f} 초과)")

N_CLUSTERS = 10
km = KMeans(n_clusters=N_CLUSTERS, random_state=42, n_init=10)
km.fit(high_pressure[['lat', 'lng']], sample_weight=high_pressure['pressure'])

high_pressure = high_pressure.copy()
high_pressure['cluster'] = km.labels_

# 클러스터별 통계
centroids = high_pressure.groupby('cluster').agg(
    lat=('lat', 'mean'),
    lng=('lng', 'mean'),
    total_units=('세대수', 'sum'),
    avg_dist=('nearest_m', 'mean'),
    score=('pressure', 'sum'),
    apt_count=('단지명', 'count'),
).reset_index()

# K-means centroid 좌표 사용 (세대수 가중 평균 대신)
centroids['lat'] = km.cluster_centers_[:, 0]
centroids['lng'] = km.cluster_centers_[:, 1]
centroids = centroids.sort_values('score', ascending=False).reset_index(drop=True)
centroids['rank'] = range(1, len(centroids) + 1)

print(f"\n신규 입점 추천 TOP {N_CLUSTERS}:")
print(centroids[['rank','lat','lng','total_units','avg_dist','apt_count','score']].to_string(index=False))

# ── 지도 생성 ─────────────────────────────────────────────────────────────────
m = folium.Map(
    location=[37.655, 126.835],
    zoom_start=12,
    tiles='https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', attr='Tiles &copy; Esri',
)

# 히트맵 레이어
HeatMap(
    heat_data,
    radius=28,
    blur=22,
    min_opacity=0.2,
    gradient={0.0: '#0ea5e9', 0.3: '#8b5cf6', 0.6: '#f59e0b', 0.85: '#ef4444', 1.0: '#fff'},
    name='수요압력 히트맵',
).add_to(m)

# 기존 편의점 마커 (작게)
for _, row in stores.iterrows():
    folium.CircleMarker(
        location=[row['lat'], row['lng']],
        radius=3,
        color='rgba(255,255,255,0.4)',
        weight=1,
        fill=True,
        fill_color='#ffffff',
        fill_opacity=0.3,
        tooltip=f"{row['name']} ({row['brand']})",
    ).add_to(m)

# 신규 추천 입지 마커
rank_colors = {1: '#ff4444', 2: '#ff6b35', 3: '#f59e0b',
               4: '#10d9a0', 5: '#10d9a0',
               6: '#38bdf8', 7: '#38bdf8', 8: '#38bdf8', 9: '#38bdf8', 10: '#38bdf8'}

for _, row in centroids.iterrows():
    rank  = int(row['rank'])
    color = rank_colors.get(rank, '#38bdf8')
    score = int(row['score'])
    units = int(row['total_units'])
    dist  = int(row['avg_dist'])
    cnt   = int(row['apt_count'])

    popup_html = f"""
    <div style="font-family:-apple-system,sans-serif;min-width:200px;padding:4px">
      <div style="font-size:10px;letter-spacing:1px;color:#94a3b8;margin-bottom:6px">신규 추천 입지</div>
      <div style="font-size:22px;font-weight:700;color:{color};margin-bottom:8px">#{rank}</div>
      <table style="font-size:12px;color:#334155;width:100%;border-collapse:collapse">
        <tr><td style="padding:3px 0;color:#64748b">담당 세대수</td><td style="text-align:right;font-weight:600">{units:,}세대</td></tr>
        <tr><td style="padding:3px 0;color:#64748b">평균 거리</td><td style="text-align:right;font-weight:600">{dist}m</td></tr>
        <tr><td style="padding:3px 0;color:#64748b">인근 단지 수</td><td style="text-align:right;font-weight:600">{cnt}개</td></tr>
        <tr><td style="padding:3px 0;color:#64748b">수요압력 점수</td><td style="text-align:right;font-weight:600">{score:.0f}</td></tr>
      </table>
    </div>"""

    folium.CircleMarker(
        location=[row['lat'], row['lng']],
        radius=16,
        color=color,
        weight=2.5,
        fill=True,
        fill_color='rgba(0,0,0,0.6)',
        fill_opacity=0.7,
        tooltip=f"추천 #{rank} | {units:,}세대 담당 구역",
        popup=folium.Popup(popup_html, max_width=240),
    ).add_to(m)

    folium.Marker(
        location=[row['lat'], row['lng']],
        icon=folium.DivIcon(
            html=f'<div style="color:white;font-weight:700;font-size:11px;text-align:center;line-height:32px;width:32px;margin-top:-16px;margin-left:-16px;font-family:-apple-system,sans-serif">{rank}</div>',
            icon_size=(32, 32),
            icon_anchor=(16, 16),
        )
    ).add_to(m)

# ── 범례 HTML ────────────────────────────────────────────────────────────────
legend_html = f"""
<div style="
  position:fixed; top:80px; right:16px; z-index:1000;
  background:rgba(15,20,30,0.95);
  border:1px solid rgba(255,255,255,0.08);
  border-radius:12px; padding:20px;
  width:240px;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  color:#e2e8f0;
  backdrop-filter:blur(10px);
  box-shadow:0 8px 32px rgba(0,0,0,0.5);
">
  <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#38bdf8;margin-bottom:16px;font-family:'Courier New',monospace">
    수요압력 분석
  </div>
  <div style="font-size:18px;font-weight:700;margin-bottom:4px">신규 입점 추천</div>
  <div style="font-size:12px;color:#64748b;margin-bottom:20px">세대수 × 거리 가중 점수</div>

  <div style="margin-bottom:16px">
    <div style="font-size:11px;color:#94a3b8;margin-bottom:8px">히트맵 강도</div>
    <div style="height:8px;border-radius:4px;background:linear-gradient(90deg,#0ea5e9,#8b5cf6,#f59e0b,#ef4444,#fff)"></div>
    <div style="display:flex;justify-content:space-between;font-size:10px;color:#475569;margin-top:4px">
      <span>낮음</span><span>높음</span>
    </div>
  </div>

  <div style="border-top:1px solid rgba(255,255,255,0.06);padding-top:14px">
    <div style="font-size:11px;color:#94a3b8;margin-bottom:10px">추천 순위</div>
    <div style="display:flex;gap:6px;flex-wrap:wrap">
      <span style="background:#ff4444;color:white;padding:3px 9px;border-radius:20px;font-size:11px;font-weight:700">1위</span>
      <span style="background:#ff6b35;color:white;padding:3px 9px;border-radius:20px;font-size:11px;font-weight:700">2위</span>
      <span style="background:#f59e0b;color:white;padding:3px 9px;border-radius:20px;font-size:11px;font-weight:700">3위</span>
      <span style="background:#10d9a0;color:white;padding:3px 9px;border-radius:20px;font-size:11px;font-weight:700">4–5위</span>
      <span style="background:#38bdf8;color:white;padding:3px 9px;border-radius:20px;font-size:11px;font-weight:700">6–10위</span>
    </div>
  </div>

  <div style="border-top:1px solid rgba(255,255,255,0.06);margin-top:14px;padding-top:12px;font-size:10px;color:#475569;font-family:'Courier New',monospace">
    흰 점 = 기존 편의점
  </div>
</div>"""

m.get_root().html.add_child(folium.Element(legend_html))

# ── 저장 ─────────────────────────────────────────────────────────────────────
m.save('goyang_demand_map.html')
print("\n✅ goyang_demand_map.html 저장 완료")
