"""select_sites 회귀 테스트: python -m pytest tests"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
from gap_analysis import select_sites  # noqa: E402

FAR_STORE = np.array([[100_000.0, 100_000.0]])


def test_larger_demand_wins():
    """같은 경쟁 조건이면 세대가 많은 후보가 먼저 뽑혀야 한다 (예전 모형은 둘 다 약 521세대)."""
    cand = np.array([[0.0, 0.0], [5_000.0, 0.0]])
    apts = np.array([[0.0, 10.0], [5_000.0, 10.0]])
    units = np.array([1_394.0, 6_185.0])
    picks = select_sites(cand, apts, units, np.array([1, 1]), FAR_STORE, n_sites=1, radius=400, min_dist=200)
    assert picks[0]['cand_idx'] == 1
    assert picks[0]['capture'] == 6_185 / 2


def test_competition_splits_demand():
    """세대수가 같으면 도보권 편의점이 적은 곳을 고른다."""
    cand = np.array([[0.0, 0.0], [5_000.0, 0.0]])
    apts = np.array([[0.0, 10.0], [5_000.0, 10.0]])
    units = np.array([1_000.0, 1_000.0])
    picks = select_sites(cand, apts, units, np.array([9, 1]), FAR_STORE, n_sites=1, radius=400, min_dist=200)
    assert picks[0]['cand_idx'] == 1


def test_min_distance_from_existing_store():
    cand = np.array([[0.0, 0.0], [300.0, 0.0]])
    apts = np.array([[0.0, 10.0]])
    picks = select_sites(cand, apts, np.array([1_000.0]), np.array([1]), np.array([[50.0, 0.0]]),
                         n_sites=1, radius=400, min_dist=200)
    assert picks[0]['cand_idx'] == 1


def test_sites_keep_distance_and_do_not_double_count():
    cand = np.array([[0.0, 0.0], [50.0, 0.0], [600.0, 0.0]])
    apts = np.array([[0.0, 10.0]])
    picks = select_sites(cand, apts, np.array([1_000.0]), np.array([0]), FAR_STORE,
                         n_sites=3, radius=400, min_dist=200)
    assert [p['cand_idx'] for p in picks] == [0]     # 600m 후보는 단지가 400m 밖, 50m 후보는 거리 제한
    assert picks[0]['new_units'] == 1_000


def test_new_units_counts_only_uncovered_apartments():
    cand = np.array([[0.0, 0.0]])
    apts = np.array([[0.0, 10.0], [0.0, 20.0]])
    picks = select_sites(cand, apts, np.array([500.0, 300.0]), np.array([0, 2]), FAR_STORE,
                         n_sites=1, radius=400, min_dist=200)
    assert picks[0]['new_units'] == 500
    assert picks[0]['capture'] == 500 + 100
