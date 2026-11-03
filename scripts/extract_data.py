"""
기존 Folium HTML 지도에서 원본 데이터를 복원해 CSV로 저장합니다.
(원본 CSV가 저장소에 없어서, 이후 분석은 이 CSV를 기준으로 재현 가능하게 합니다.)

  data/stores.csv      편의점 921개 (name, brand, lat, lng)   ← goyang_satellite_map.html
  data/apartments.csv  300세대 이상 아파트 단지 (name, units, lat, lng) ← goyang_voronoi_map.html

실행: python scripts/extract_data.py
"""
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
DATA.mkdir(exist_ok=True)

# var circle_marker_xxx = L.circleMarker([lat, lng], ...)
MARKER = re.compile(
    r'var (circle_marker_\w+) = L\.circleMarker\(\s*\[\s*([0-9.]+),\s*([0-9.]+)\s*\]')
# circle_marker_xxx.bindTooltip(`<div> ... </div>`
TOOLTIP = re.compile(
    r'(circle_marker_\w+)\.bindTooltip\(\s*`<div>\s*(.*?)\s*</div>`', re.DOTALL)


def markers_with_tooltips(html: str):
    coords = {m.group(1): (float(m.group(2)), float(m.group(3)))
              for m in MARKER.finditer(html)}
    for m in TOOLTIP.finditer(html):
        var, text = m.group(1), ' '.join(m.group(2).split())
        if var in coords:
            yield text, coords[var]


def extract_stores():
    html = (ROOT / 'goyang_satellite_map.html').read_text(encoding='utf-8')
    pat = re.compile(r'^(.+?)\s*\((CU|GS25|세븐일레븐|이마트24|기타)\)$')
    rows = []
    for text, (lat, lng) in markers_with_tooltips(html):
        m = pat.match(text)
        if m:
            rows.append({'name': m.group(1), 'brand': m.group(2), 'lat': lat, 'lng': lng})
    # 같은 이름·좌표가 겹치는 8건(킨텍스·휴게소·스타필드 등)은 원본 상가 데이터에
    # 별도 업소로 등록된 것이므로 그대로 둔다 (최근접 거리 계산에는 영향 없음).
    df = pd.DataFrame(rows)
    df.to_csv(DATA / 'stores.csv', index=False, encoding='utf-8-sig')
    print(f'편의점 {len(df)}개 → data/stores.csv')
    print(df['brand'].value_counts().to_string())
    return df


def extract_apartments():
    html = (ROOT / 'goyang_voronoi_map.html').read_text(encoding='utf-8')
    pat = re.compile(r'^(.+?)\s+([\d,]+)세대$')
    rows = []
    for text, (lat, lng) in markers_with_tooltips(html):
        m = pat.match(text)
        if m:
            rows.append({'name': m.group(1), 'units': int(m.group(2).replace(',', '')),
                         'lat': lat, 'lng': lng})
    df = pd.DataFrame(rows).drop_duplicates(subset=['name', 'lat', 'lng'])
    df.to_csv(DATA / 'apartments.csv', index=False, encoding='utf-8-sig')
    print(f'\n아파트 {len(df)}개 단지 / {df["units"].sum():,}세대 → data/apartments.csv')
    return df


if __name__ == '__main__':
    extract_stores()
    extract_apartments()
