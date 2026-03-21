# 🏪 고양시 편의점 최적 입지 분석

> 공공데이터 기반 편의점 공백 지역 탐지 및 신규 입지 추천 프로젝트

**분석 결과 웹사이트:** https://sangdeokwoo.github.io/goyang-convenience-analysis/

---

## 📌 프로젝트 개요

경기도 고양시의 편의점 분포 데이터와 공동주택 세대수 데이터를 결합하여,
편의점이 부족한 공백 지역을 탐지하고 신규 입지를 추천하는 데이터 분석 프로젝트입니다.

제주도 렌터카 체류 데이터를 활용한 주차장 입지 분석 프로젝트(BDP)의 방법론을
편의점 도메인에 적용하였습니다.

---

## 📊 데이터 출처

| 데이터 | 출처 | 비고 |
|--------|------|------|
| 전국 상가업소 정보 | 소상공인시장진흥공단 공공데이터포털 | 편의점 위치 추출 |
| 공동주택 단지 목록 | 국토교통부 공공데이터포털 | 아파트 세대수 |
| 주소 → 좌표 변환 | 카카오 지도 REST API | 지오코딩 (키는 환경변수로 관리) |
| 행정구역 경계 | 국가공간정보포털 | 고양시 필터링 |

---

## 🔢 분석 결과 요약

- 분석 대상 편의점: **951개** (CU 290 / GS25 288 / 세븐일레븐 217 / 이마트24 78)
- 분석 대상 아파트: **325개 단지 / 약 25.3만 세대**
- 공백 심각 행정동: **TOP 10 도출**
- 편의점 최대 담당 세대수: **4,320세대** (세븐일레븐일산동구)

---

## 🗺️ 분석 지도

### 공백 심각도 TOP 10

| 순위 | 행정동 | 구 | 편의점 수 | 평균 최근접 거리 |
|------|--------|-----|-----------|----------------|
| 1 | 탄현2동 | 일산서구 | 5개 | 262m |
| 2 | 성사2동 | 덕양구 | 4개 | 202m |
| 3 | 능곡동 | 덕양구 | 13개 | 473m |
| 4 | 원신동 | 덕양구 | 14개 | 462m |
| 5 | 행신3동 | 덕양구 | 9개 | 176m |
| 6 | 덕이동 | 일산서구 | 15개 | 285m |
| 7 | 효자동 | 덕양구 | 18개 | 340m |
| 8 | 중산2동 | 일산동구 | 12개 | 203m |
| 9 | 장항1동 | 일산동구 | 16개 | 250m |
| 10 | 주교동 | 덕양구 | 13개 | 189m |

---

## ⚙️ 분석 파이프라인
```
공공데이터 수집
    │
    ├── 소상공인 상가업소 데이터 (650,081행)
    │       └── 고양시 필터링 → 편의점 추출 → 951개
    │
    └── 공동주택 단지 목록 (21,499행)
            └── 고양시 필터링 → 300세대 이상 → 345개
                    └── 카카오 API 지오코딩 → 325개

전처리
    ├── 브랜드 분류 (상호명 기반 정규화)
    ├── 좌표 정제 (고양시 bbox 필터)
    └── 시군구명 정규화 (덕양구 / 일산동구 / 일산서구)

공백 분석
    ├── 고양시 500m 격자 생성
    ├── 각 격자점 → 가장 가까운 편의점 거리 계산
    ├── 행정동별 편의점 간 평균 최근접 거리 계산
    └── 공백 심각도 점수화 → TOP 10 도출

보로노이 분석
    ├── 편의점 좌표 기반 보로노이 다이어그램 생성
    ├── Shapely로 고양시 경계 클리핑
    ├── KD-Tree로 아파트 → 최근접 편의점 매핑
    └── 편의점별 담당 세대수 합산 → 색상 인코딩

시각화
    ├── Folium 기반 인터랙티브 지도 3종
    └── GitHub Pages 배포
```

---

## 🛠️ 기술 스택

| 분류 | 사용 기술 |
|------|----------|
| 언어 | Python 3.12 |
| 데이터 처리 | pandas, numpy |
| 공간 분석 | scipy (KD-Tree, Voronoi), shapely |
| 지오코딩 | 카카오 지도 REST API |
| 시각화 | Folium, Leaflet.js |
| 실행 환경 | Google Colab |
| 배포 | GitHub Pages |

---

## 💻 전체 코드

### 0. 라이브러리 설치
```python
!pip install folium scipy shapely -q
import pandas as pd
import numpy as np
import folium
from scipy.spatial import Voronoi, cKDTree
from scipy.spatial.distance import cdist
from shapely.geometry import Polygon
```

### 1. 편의점 데이터 수집 및 전처리
```python
# 소상공인 상가업소 데이터 로드
df = pd.read_csv("상가(상권)정보.csv", encoding='cp949', low_memory=False)

# 고양시 필터링 (시군구명이 구 단위로 분리되어 있음)
goyang = df[df['시군구명'].str.contains('고양시')]

# 편의점만 추출
convenience = goyang[
    goyang['상권업종소분류명'].str.contains('편의점', na=False)
].copy()

# 브랜드 분류
def classify_brand(name):
    name = str(name).upper()
    if '씨유' in name or 'CU' in name:       return 'CU'
    elif '지에스' in name or 'GS' in name:   return 'GS25'
    elif '세븐' in name or '7-' in name:     return '세븐일레븐'
    elif '이마트' in name:                   return '이마트24'
    else:                                    return '기타'

convenience['브랜드'] = convenience['상호명'].apply(classify_brand)

# 좌표 정제 (고양시 bbox)
convenience = convenience.dropna(subset=['경도','위도'])
convenience = convenience[
    (convenience['위도'].between(37.57, 37.73)) &
    (convenience['경도'].between(126.74, 126.97))
]

# 저장
result = convenience[['상호명','브랜드','도로명주소','경도','위도','행정동명']].copy()
result.columns = ['name','brand','address','lng','lat','dong']
result.to_csv('goyang_convenience_stores.csv', index=False, encoding='utf-8-sig')
# 결과: 951개 (CU 290 / GS25 288 / 세븐일레븐 217 / 이마트24 78 / 기타 78)
```

### 2. 아파트 데이터 지오코딩 (카카오 API)
```python
import requests, time

# 카카오 REST API 키는 환경변수로 관리
# KAKAO_API_KEY = os.environ.get("KAKAO_API_KEY")

def kakao_geocode(address, api_key):
    url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {"Authorization": f"KakaoAK {api_key}"}
    params = {"query": address}
    try:
        res = requests.get(url, headers=headers, params=params)
        docs = res.json().get('documents', [])
        if docs:
            return float(docs[0]['y']), float(docs[0]['x'])
    except:
        pass
    return None, None

apt = pd.read_csv('공동주택단지목록.csv', encoding='cp949')
goyang_apt = apt[apt['시군구'].str.contains('고양', na=False)]
large_apt = goyang_apt[goyang_apt['세대수'] >= 300].copy().reset_index(drop=True)

lats, lngs = [], []
for i, row in large_apt.iterrows():
    lat, lng = kakao_geocode(str(row['도로명주소']), KAKAO_API_KEY)
    lats.append(lat)
    lngs.append(lng)
    time.sleep(0.05)

large_apt['lat'] = lats
large_apt['lng'] = lngs
large_apt.to_csv('goyang_apt_kakao.csv', index=False, encoding='utf-8-sig')
# 결과: 345개 중 325개 지오코딩 성공 (약 25.3만 세대)
```

### 3. 공백 지역 분석
```python
result = pd.read_csv('goyang_convenience_stores.csv')

# 500m 격자 생성
lat_steps = np.arange(37.57, 37.73, 0.0045)
lng_steps = np.arange(126.74, 126.97, 0.0045)
grid = pd.DataFrame(
    [(lat, lng) for lat in lat_steps for lng in lng_steps],
    columns=['lat','lng']
)

# 편의점까지 거리 계산 (도 → 미터)
store_coords = result[['lat','lng']].values
grid_coords  = grid[['lat','lng']].values

def dist_meters(a, b):
    dlat = (a[:,0:1] - b[:,0]) * 111000
    dlng = (a[:,1:2] - b[:,1]) * 88000
    return np.sqrt(dlat**2 + dlng**2)

distances = dist_meters(grid_coords, store_coords)
grid['nearest_store_m'] = distances.min(axis=1).round()

# 행정동별 편의점 간 최근접 거리 기반 공백 심각도 분석
dong_analysis = []
for (gu, dong), group in convenience2.groupby(['시군구명','행정동명']):
    coords = group[['위도','경도']].values
    n = len(coords)
    if n >= 2:
        d = cdist(coords, coords)
        np.fill_diagonal(d, np.inf)
        avg_nn_m = (d.min(axis=1).mean() * 111000).round()
    else:
        avg_nn_m = 9999
    dong_analysis.append({
        'gu': gu.strip(), 'dong': dong.strip(),
        'store_count': n, 'avg_nn_m': int(avg_nn_m)
    })

da = pd.DataFrame(dong_analysis)
da['score'] = (da['avg_nn_m'] * (1 / da['store_count'])).round(1)
da = da.sort_values('score', ascending=False).reset_index(drop=True)
```

### 4. 보로노이 다이어그램 + 세대수 분석
```python
from scipy.spatial import Voronoi, cKDTree
from shapely.geometry import Polygon as ShapelyPolygon

apt = pd.read_csv('goyang_apt_kakao.csv').dropna(subset=['lat','lng'])
apt = apt[
    (apt['lat'].between(37.57, 37.73)) &
    (apt['lng'].between(126.74, 126.97))
].copy()

stores = pd.read_csv('goyang_convenience_stores.csv')
store_coords = stores[['lat','lng']].values

# 편의점별 담당 세대수 계산 (KD-Tree)
tree = cKDTree(store_coords)
_, store_idx = tree.query(apt[['lat','lng']].values)
apt['store_idx'] = store_idx

store_coverage = apt.groupby('store_idx').agg(
    total_units=('세대수', 'sum'),
    apt_count=('단지명', 'count')
).reset_index()

stores_r = stores.copy().reset_index()
stores_r = stores_r.merge(store_coverage, left_on='index', right_on='store_idx', how='left')
stores_r['total_units'] = stores_r['total_units'].fillna(0).astype(int)

# 위경도 → 평면 좌표 변환
def to_xy(lat, lng, lat0=37.65, lng0=126.83):
    return (lng - lng0) * 88000, (lat - lat0) * 111000

def to_latlng(x, y, lat0=37.65, lng0=126.83):
    return lat0 + y/111000, lng0 + x/88000

pts_xy = np.array([to_xy(r['lat'], r['lng']) for _, r in stores_r.iterrows()])

# 경계 더미 포인트 추가 후 보로노이 계산
dummy = np.array([
    [-15000,-12000],[-15000,12000],[15000,-12000],[15000,12000],
    [-15000,0],[15000,0],[0,-12000],[0,12000],
])
vor = Voronoi(np.vstack([pts_xy, dummy]))

# 고양시 경계로 클리핑
clip_box = ShapelyPolygon([
    (126.74,37.57),(126.97,37.57),(126.97,37.73),(126.74,37.73)
])

# 세대수 → 색상 인코딩
def units_to_color(units):
    if units == 0:   return '#cccccc', 0.15
    ratio = min(units / 2000, 1.0)
    if ratio < 0.33: return '#41b6c4', 0.4
    elif ratio < 0.66: return '#fd8d3c', 0.5
    else:            return '#bd0026', 0.6
```

### 5. Folium 지도 생성 및 저장
```python
m = folium.Map(location=[37.65, 126.83], zoom_start=12, tiles='CartoDB positron')

# 보로노이 셀
for i, region_idx in enumerate(vor.point_region[:len(stores_r)]):
    region = vor.regions[region_idx]
    if -1 in region or len(region) == 0: continue
    try:
        poly_xy = vor.vertices[region]
        poly_latlng = [to_latlng(x, y) for x, y in poly_xy]
        poly_shapely = ShapelyPolygon([(lng, lat) for lat, lng in poly_latlng])
        clipped = poly_shapely.intersection(clip_box)
        if clipped.is_empty: continue
        coords = [[lat, lng] for lng, lat in clipped.exterior.coords]
        row = stores_r.iloc[i]
        color, opacity = units_to_color(row['total_units'])
        folium.Polygon(
            locations=coords,
            color='white', weight=0.5, fill=True,
            fill_color=color, fill_opacity=opacity,
            tooltip=f"{row['name']} | 담당 세대수: {int(row['total_units']):,}세대"
        ).add_to(m)
    except: continue

# 편의점 마커
brand_colors = {'CU':'#00a0e9','GS25':'#009d4e','세븐일레븐':'#ff6600','이마트24':'#e11400','기타':'#aaaaaa'}
for _, row in stores_r.iterrows():
    folium.CircleMarker(
        location=[row['lat'], row['lng']], radius=3,
        color=brand_colors.get(row['brand'],'#aaaaaa'),
        fill=True, fill_opacity=0.9,
        tooltip=f"{row['name']} ({row['brand']})"
    ).add_to(m)

folium.LayerControl(collapsed=False).add_to(m)
m.save('goyang_voronoi_map.html')
```

---

## 📁 파일 구조
```
goyang-convenience-analysis/
├── index.html                  # 메인 페이지
├── goyang_final_map.html       # 공백 지역 분석 지도
├── goyang_satellite_map.html   # 위성지도 뷰
└── goyang_voronoi_map.html     # 보로노이 세대수 분석 지도
```

---

## 💡 인사이트

1. **탄현2동·성사2동** — 편의점 수가 각각 5개·4개로 고양시 내 최저 수준이며 거주 인구 대비 공급 부족
2. **능곡동·원신동** — 편의점 수는 있으나 평균 거리가 460m 이상으로 넓게 분산되어 실질적 접근성 낮음
3. **세븐일레븐일산동구** — 보로노이 분석 결과 단일 편의점이 4,320세대를 담당하는 극단적 과부하 사례

---

## 🔗 참고

- 본 프로젝트는 제주도 렌터카 주차장 입지 분석(BDP, 2022)의 방법론을 계승합니다
- 유동인구 데이터(KT/SKT) 연동 시 수요 기반 분석으로 고도화 가능
- 동일 파이프라인으로 타 도시 확장 적용 가능
