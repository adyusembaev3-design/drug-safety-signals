from src.definitions import GROUPS, TARGETS, ror


def test_ror_matches_cross_product():
    est, lo, hi = ror(200, 800, 1000, 98000)
    assert abs(est - (200 * 98000) / (800 * 1000)) / est < 0.01
    assert lo < est < hi


def test_ror_independent_table_is_near_one():
    est, lo, hi = ror(100, 900, 1000, 9000)
    assert 0.95 < est < 1.05
    assert lo < 1 < hi


def test_ror_interval_narrows_with_more_data():
    _, lo_small, hi_small = ror(20, 80, 100, 900)
    _, lo_big, hi_big = ror(2000, 8000, 10000, 90000)
    assert (hi_big - lo_big) < (hi_small - lo_small)


def test_definitions():
    assert len(GROUPS) == 6
    assert list(TARGETS) == ["TOFACITINIB", "UPADACITINIB", "BARICITINIB"]
