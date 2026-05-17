"""Canonical output row + intermediate candidate types for derive-base.

DerivedMetricRow is the JSON-output shape AND the Supabase
sec_financial_metrics upsert shape — they must stay aligned.
Candidate is internal: produced by rules, resolved by engine, then
turned into DerivedMetricRow.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from _shared.sec_json_adapter import FactRow  # noqa: F401


@dataclass
class DerivedMetricRow:
    cell_id: str
    ticker: str
    period: str
    period_kind: str           # quarter_duration / ytd_duration / fy_annual_duration / instant_period_end / derived_q4
    period_start: str | None
    period_end: str
    statement: str             # IS / BS / CF / RATIO
    version: str               # GAAP / NON_GAAP
    uni_account: str
    value: float
    unit: str
    status: str                # DERIVED_FROM_DISCLOSED | EXCLUDED_FROM_NONGAAP
    provenance: dict


@dataclass
class Candidate:
    """Internal: one possible derived value before resolution."""
    ticker: str
    period: str
    period_kind: str
    period_start: str | None
    period_end: str
    statement: str
    version: str
    uni_account: str
    value: float
    unit: str
    rule_id: str               # Q4_FY_MINUS_9M | Q4_FY_MINUS_Q1Q2Q3 | CALC_LINKBASE | STATIC_ALLOWLIST | NG_ALLOWLIST
    rule_priority: int         # lower = preferred
    chain_depth: int
    chained: bool
    inputs: list[dict]         # [{cell_id, uni_account, period, value, status}, ...]
    extras: dict = field(default_factory=dict)   # role_uri, formula text, etc.


def input_dict_from_fact(f: "FactRow") -> dict:
    """Compact dict of a FactRow's identity + value, suitable for storing
    in Candidate.inputs / DerivedMetricRow.provenance.inputs."""
    return {
        "cell_id": f.cell_id,
        "uni_account": f.uni_account,
        "period": f.period,
        "value": f.value,
        "status": f.status,
    }
