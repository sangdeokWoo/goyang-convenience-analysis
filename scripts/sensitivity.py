"""
신규 입지 추천 민감도 분석 → results/sensitivity_sites.csv

기준 설정의 추천 입지가 반경·최소 거리·같은 좌표 점포 정리에 따라 얼마나 유지되는지 봅니다.
유지 = 시나리오의 추천 입지 중 기준 입지와 400m 안에 있는 곳이 있음.

실행: python scripts/gap_analysis.py && python scripts/sensitivity.py
"""
import contextlib
import io
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

import gap_analysis as ga

ROOT = Path(__file__).resolve().parent.parent


def run(tmp, tag, data=None, **overrides):
    out = tmp / tag
    out.mkdir()
    saved = {k: getattr(ga, k) for k in overrides}
    ga.RESULTS, ga.DATA = out, data or ROOT / 'data'
    for k, v in overrides.items():
        setattr(ga, k, v)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            ga.main()
    finally:
        for k, v in saved.items():
            setattr(ga, k, v)
        ga.RESULTS, ga.DATA = ROOT / 'results', ROOT / 'data'
    return pd.read_csv(out / 'recommended_sites.csv', encoding='utf-8-sig')


def main():
    base = pd.read_csv(ROOT / 'results' / 'recommended_sites.csv', encoding='utf-8-sig')
    bxy = ga.to_m(base.lng, base.lat)
    rows = []
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        dedup = tmp / 'data_dedup'
        shutil.copytree(ROOT / 'data', dedup)
        st = pd.read_csv(dedup / 'stores.csv', encoding='utf-8-sig')
        st.drop_duplicates(['lat', 'lng']).to_csv(dedup / 'stores.csv', index=False, encoding='utf-8-sig')
        scenarios = [('기준', {}), ('반경 300m', {'RADIUS': 300}), ('반경 500m', {'RADIUS': 500}),
                     ('최소 거리 100m', {'MIN_STORE_DIST': 100}), ('최소 거리 300m', {'MIN_STORE_DIST': 300}),
                     ('같은 좌표 점포 1개로', {'data': dedup})]
        for i, (name, kw) in enumerate(scenarios):
            sites = run(tmp, f's{i}', **kw)
            sxy = ga.to_m(sites.lng, sites.lat)
            d = np.hypot(bxy[:, None, 0] - sxy[None, :, 0], bxy[:, None, 1] - sxy[None, :, 1])
            kept = d.min(axis=1) <= 400
            rows.append({'scenario': name, 'sites': len(sites), 'kept_of_base': int(kept.sum()),
                         'kept_base_ranks': ' '.join(str(r) for r in base['rank'][kept]),
                         'top3': ', '.join(sites.dong[:3])})
    out = pd.DataFrame(rows)
    out.to_csv(ROOT / 'results' / 'sensitivity_sites.csv', index=False, encoding='utf-8-sig')
    print(out.to_string(index=False))


if __name__ == '__main__':
    main()
