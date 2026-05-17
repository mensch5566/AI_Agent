"""Unit-aware tolerance: combine absolute + relative thresholds.

Source: design §6 Tolerance.

Two-band classification:
  within: max(abs_tol_by_unit, 0.1% relative) covers the diff
  warn:   inside hard band but outside within band
  hard:   > 0.5% relative AND > abs_tol_by_unit  → candidate skip + conflict report
"""
from __future__ import annotations

ABS_TOL_BY_UNIT: dict[str, float] = {
    "USD_thousands":     1.0,
    "USD_millions":      1.0,
    "USD":               1.0,
    "USD_per_share":     0.01,
    "millions_shares":   0.1,
    "thousands_shares":  1.0,
    "Pure":              0.0001,
}
WARN_REL_PCT = 0.1   # 0.1%
HARD_REL_PCT = 0.5   # 0.5%


def diff_classification(facts_value: float, derived_value: float, unit: str) -> dict:
    abs_diff = abs(facts_value - derived_value)
    base = max(abs(facts_value), 1e-9)
    rel_pct = (abs_diff / base) * 100.0
    abs_tol = ABS_TOL_BY_UNIT.get(unit, 1.0)
    warn_thresh = max(abs_tol, base * (WARN_REL_PCT / 100.0))
    hard_thresh = max(abs_tol, base * (HARD_REL_PCT / 100.0))
    if abs_diff <= warn_thresh:
        level = "within"
    elif abs_diff <= hard_thresh:
        level = "warn"
    else:
        level = "hard"
    return {"level": level, "abs": abs_diff, "rel_pct": rel_pct, "unit": unit}
