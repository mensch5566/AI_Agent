from tolerance import diff_classification, ABS_TOL_BY_UNIT


def test_below_warn():
    # USD_thousands: abs_tol=1.0, warn=0.1% relative
    # 65200 vs 65200.4 → diff=0.4 < 1.0 → within
    out = diff_classification(65200.0, 65200.4, "USD_thousands")
    assert out["level"] == "within"


def test_warn_band():
    # 65200 vs 65300 → diff=100, rel=0.15% > warn 0.1%, < hard 0.5%
    out = diff_classification(65200.0, 65300.0, "USD_thousands")
    assert out["level"] == "warn"
    assert out["abs"] == 100.0


def test_hard_band():
    # 65200 vs 67000 → diff=1800, rel=2.76% > 0.5%
    out = diff_classification(65200.0, 67000.0, "USD_thousands")
    assert out["level"] == "hard"


def test_zero_facts_value_uses_abs():
    out = diff_classification(0.0, 0.5, "USD_thousands")
    assert out["level"] == "within"   # abs_tol=1.0
    out2 = diff_classification(0.0, 2.0, "USD_thousands")
    assert out2["level"] in ("warn", "hard")
