"""
OpenStreetMap(Overpass API)에서 고양시 경계 데이터를 받아 GeoJSON으로 저장합니다.

  data/goyang_dong.geojson         행정동 44개 경계 (name, gu)
  data/goyang_residential.geojson  주거지역(landuse=residential) 폴리곤

※ 기존 스크립트는 outer 웨이 좌표를 순서 없이 이어 붙여 폴리곤이 꼬이는 문제가 있어
  shapely polygonize로 링을 올바르게 조립합니다.
※ OSM에서 고양시의 한국어 name이 바뀌는 경우가 있어 name:en="Goyang-si"로 검색합니다.

실행: python scripts/fetch_osm.py   (이미 파일이 있으면 건너뜀, --force 로 재다운로드)
"""
import json
import sys
import time
from pathlib import Path

import requests
from shapely.geometry import LineString, Polygon, MultiPolygon, mapping
from shapely.ops import polygonize, unary_union

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
DATA.mkdir(exist_ok=True)

ENDPOINTS = ['https://overpass-api.de/api/interpreter',
             'https://overpass.kumi.systems/api/interpreter']
HEADERS = {'User-Agent': 'goyang-convenience-analysis/1.0'}
AREA = 'area["name:en"="Goyang-si"]["admin_level"="6"]->.g;'


def overpass(query: str) -> dict:
    last = None
    for ep in ENDPOINTS:
        for _ in range(2):
            try:
                r = requests.post(ep, data={'data': query}, headers=HEADERS, timeout=300)
                if r.status_code == 200:
                    return r.json()
                last = f'{ep} HTTP {r.status_code}'
            except requests.RequestException as e:
                last = f'{ep} {e}'
            time.sleep(5)
    raise RuntimeError(f'Overpass 요청 실패: {last}')


def relation_geom(el):
    """relation의 outer/inner 멤버 웨이를 조립해 (Multi)Polygon 반환"""
    def rings(role):
        lines = [LineString([(p['lon'], p['lat']) for p in m['geometry']])
                 for m in el.get('members', [])
                 if m.get('type') == 'way' and m.get('role', 'outer') == role
                 and len(m.get('geometry', [])) >= 2]
        return list(polygonize(unary_union(lines))) if lines else []
    outer, inner = rings('outer'), rings('inner')
    if not outer:
        return None
    geom = unary_union(outer)
    if inner:
        geom = geom.difference(unary_union(inner))
    return geom


def way_geom(el):
    pts = [(p['lon'], p['lat']) for p in el.get('geometry', [])]
    return Polygon(pts) if len(pts) >= 4 and pts[0] == pts[-1] else None


def save(features, name):
    fc = {'type': 'FeatureCollection', 'features': features}
    (DATA / name).write_text(json.dumps(fc, ensure_ascii=False), encoding='utf-8')
    print(f'  → data/{name} ({len(features)}개)')


def fetch_dong():
    print('행정동 경계 다운로드...')
    q = f'[out:json][timeout:180];{AREA}' \
        'relation["boundary"="administrative"]["admin_level"~"^(7|8)$"](area.g);out body geom;'
    els = overpass(q)['elements']
    gus = [(e['tags']['name'], relation_geom(e)) for e in els if e['tags'].get('admin_level') == '7']
    feats = []
    for e in els:
        if e['tags'].get('admin_level') != '8':
            continue
        g = relation_geom(e)
        if g is None or g.is_empty:
            continue
        c = g.representative_point()
        gu = next((n for n, gg in gus if gg is not None and gg.contains(c)), '')
        feats.append({'type': 'Feature', 'geometry': mapping(g),
                      'properties': {'name': e['tags']['name'], 'gu': gu}})
    save(sorted(feats, key=lambda f: (f['properties']['gu'], f['properties']['name'])),
         'goyang_dong.geojson')


def fetch_residential():
    print('주거지역(landuse=residential) 다운로드...')
    q = f'[out:json][timeout:240];{AREA}' \
        '(way["landuse"="residential"](area.g);relation["landuse"="residential"](area.g););' \
        'out body geom;'
    feats = []
    for e in overpass(q)['elements']:
        g = way_geom(e) if e['type'] == 'way' else relation_geom(e)
        if g is None or g.is_empty:
            continue
        if not g.is_valid:
            g = g.buffer(0)
        feats.append({'type': 'Feature', 'geometry': mapping(g), 'properties': {}})
    save(feats, 'goyang_residential.geojson')


if __name__ == '__main__':
    force = '--force' in sys.argv
    for fname, fn in [('goyang_dong.geojson', fetch_dong),
                      ('goyang_residential.geojson', fetch_residential)]:
        if force or not (DATA / fname).exists():
            fn()
        else:
            print(f'data/{fname} 이미 있음 — 건너뜀')
