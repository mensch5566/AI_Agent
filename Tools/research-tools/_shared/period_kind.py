"""period_kind enum + inference + supplement vocab mapping.

Spec: tmp/financials-viewer-redesign-plan.md §16.2 (v3) + §20 (v5.1).

Canonical period_kind enum:
    quarter_duration       — single-quarter IS / CF / RATIO
    fy_annual_duration     — full-year IS / CF / RATIO
    ytd_duration           — 10-Q YTD cumulative (6M / 9M)
    instant_period_end     — any period-end BS instant
    derived_q4             — metrics-only: FY - Q1 - Q2 - Q3 reconstruction
"""
from __future__ import annotations

import re

VALID_KINDS = {
    "quarter_duration",
    "fy_annual_duration",
    "ytd_duration",
    "instant_period_end",
    "derived_q4",
}

# Supplement JSON (parse-SEC-supplement v3) -> canonical
SUPPLEMENT_PERIOD_KIND_MAP = {
    "single_quarter": "quarter_duration",
    "fy_annual": "fy_annual_duration",
    "cumulative_ytd": "ytd_duration",
    "instant": "instant_period_end",
    # Passthrough (in case future supplement starts using canonical names)
    "quarter_duration": "quarter_duration",
    "fy_annual_duration": "fy_annual_duration",
    "ytd_duration": "ytd_duration",
    "instant_period_end": "instant_period_end",
}

_YTD_PERIOD_RE = re.compile(r"^\d+M_FY\d{4}$")  # e.g. 6M_FY2025, 9M_FY2025
_QUARTER_PERIOD_RE = re.compile(r"^Q[1-4]_FY\d{4}$")
_FY_PERIOD_RE = re.compile(r"^FY\d{4}$")


def normalize_supplement_period_kind(raw: str) -> str:
    """Map supplement v3 period_kind vocab to canonical enum.

    Raises ValueError on unknown vocab so adapter writes validation error
    instead of silently passing through.
    """
    if raw not in SUPPLEMENT_PERIOD_KIND_MAP:
        raise ValueError(f"Unknown supplement period_kind: {raw!r}")
    return SUPPLEMENT_PERIOD_KIND_MAP[raw]


def infer_period_kind(statement: str, period: str) -> str:
    """Infer period_kind from (statement, period) for GAAP / Non-GAAP facts.

    Used when source JSON doesn't carry period_kind explicitly (GAAP /
    Non-GAAP parsers don't, as of 2026-05-16).

    Rules:
      - BS  -> instant_period_end (always)
      - IS / CF / RATIO + Qx_FYyyyy -> quarter_duration
      - IS / CF / RATIO + FYyyyy    -> fy_annual_duration
      - IS / CF / RATIO + NM_FYyyyy -> ytd_duration
    """
    if statement == "BS":
        return "instant_period_end"
    if statement not in ("IS", "CF", "RATIO"):
        raise ValueError(f"Unsupported statement for period_kind inference: {statement!r}")
    if _QUARTER_PERIOD_RE.match(period):
        return "quarter_duration"
    if _FY_PERIOD_RE.match(period):
        return "fy_annual_duration"
    if _YTD_PERIOD_RE.match(period):
        return "ytd_duration"
    raise ValueError(f"Cannot infer period_kind for statement={statement!r} period={period!r}")
