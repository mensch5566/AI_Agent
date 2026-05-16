"""Unit canonicalization + pct value scale normalization.

Spec: tmp/financials-viewer-redesign-plan.md §18.3.4 (v5) + §20.3 (v5.1).

Canonical units:
    USD_thousands     — money in thousands of USD (small/mid caps default)
    USD_millions      — money in millions of USD (large caps default)
    USD               — raw USD with no scale rescale
    USD_per_share     — per-share values (EPS)
    millions_shares   — share counts in millions
    thousands_shares  — share counts in thousands
    Pure              — ratios / percentages stored as decimal (0..1)

adapter contract:
  - canonicalize_unit() returns canonical unit + scale factor for value.
  - Supplement raw "USD" with decimals=-3 -> USD_thousands + value/1000.
  - Non-GAAP EPS context "USD" -> USD_per_share + no rescale.
  - normalize_pct_value() handles 39.2 vs 0.392 disambiguation.

Anything unmapped is rejected (caller writes validation error).
"""
from __future__ import annotations

from typing import Literal

PCT_UNITS = {"pct", "percent", "Percent", "Pure", "number"}
# Note: "number" is non-standard XBRL unit used by some filers (e.g. INTC) for
# unitless ratios where the value is already in decimal form (0.19 for 19%).

CanonicalUnit = Literal[
    "USD_thousands",
    "USD_millions",
    "USD",
    "USD_per_share",
    "millions_shares",
    "thousands_shares",
    "Pure",
]


class UnitNormalizationError(ValueError):
    pass


def canonicalize_unit(
    raw_unit: str,
    *,
    decimals: int | None = None,
    eps_context: bool = False,
) -> tuple[CanonicalUnit, float]:
    """Return (canonical_unit, scale_factor).

    Caller multiplies value by scale_factor to get the value in canonical unit.

    Args:
        raw_unit: unit string as found in source JSON.
        decimals: XBRL decimals attribute (e.g. -3 means thousands).
        eps_context: True when uni_account is eps_* (lets bare "USD" map to
            USD_per_share instead of plain USD).
    """
    if raw_unit is None:
        raise UnitNormalizationError("raw_unit is None")
    u_raw = raw_unit.strip()
    u = u_raw.lower()  # case-insensitive match; INTC supplement uses 'usd'

    # --- USD money ---
    if u in ("usd_thousands", "thousands of usd"):
        return "USD_thousands", 1.0
    if u in ("usd_millions", "millions of usd"):
        return "USD_millions", 1.0
    if u == "usd":
        if eps_context:
            return "USD_per_share", 1.0
        # All raw USD values from XBRL canonicalize to USD_thousands.
        # XBRL `decimals` attribute indicates rounding precision (smaller /
        # more negative = more precise), NOT the unit scale — the value
        # field is always in raw dollars. So /1000 to express in thousands.
        # Sub-dollar precision (decimals >= 0) is unusual for line items;
        # keep as raw USD in that case (caller may reject).
        if decimals is not None and decimals < 0:
            return "USD_thousands", 1e-3
        return "USD", 1.0

    # --- Per-share ---
    if u in ("usd_per_share", "usd/share", "usd per share"):
        return "USD_per_share", 1.0

    # --- Shares ---
    if u in ("millions_shares", "shares (millions)"):
        return "millions_shares", 1.0
    if u in ("thousands_shares", "shares (thousands)"):
        return "thousands_shares", 1.0
    if u == "shares":
        if decimals == -6:
            return "millions_shares", 1e-6
        if decimals == -3:
            return "thousands_shares", 1e-3
        # No scale info — keep raw shares; caller may reject
        raise UnitNormalizationError(
            f"Bare 'shares' unit with no decimals; cannot canonicalize"
        )

    # --- Pct / Pure ---
    if u_raw in PCT_UNITS or u in {x.lower() for x in PCT_UNITS}:
        return "Pure", 1.0

    raise UnitNormalizationError(f"Unknown unit: {raw_unit!r}")


def normalize_pct_value(value: float, canonical_unit: str) -> float:
    """For Pure unit: ensure value is decimal (0..1), not percent points (0..100).

    Rule: abs(value) > 1 implies the source stored percent points (e.g. 39.2
    for 39.2%); divide by 100. abs(value) <= 1 already decimal (e.g. 0.392).

    Edge case: ratios that genuinely exceed 100% (e.g. revenue_yoy_growth_pct
    in turn-around quarter) will be misclassified. For now only metrics
    listed as `*_margin_pct` or concentration% are routed through Pure unit;
    growth metrics use a different uni_account and unit.
    """
    if canonical_unit != "Pure":
        return value
    if abs(value) > 1:
        return value / 100.0
    return value
