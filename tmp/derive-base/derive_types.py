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
    inputs: list[dict]         # [{cell_id, uni_account, period, value, status, ...}, ...]
    # Source concept identity carried from the primary input fact so Pass 3
    # calc-linkbase identity can match this derived value as a child of a
    # parent calc rule. Empty string when unknown (e.g. allowlist outputs).
    source_account: str = ""
    xbrl_tag: str = ""
    extras: dict = field(default_factory=dict)   # role_uri, formula text, etc.


def input_dict_from_fact(f: "FactRow") -> dict:
    """Compact dict of a FactRow's identity + value + audit trail, suitable
    for storing in Candidate.inputs / DerivedMetricRow.provenance.inputs.

    Includes restatement-relevant lineage fields (accession_number,
    source_filing, period_end, source_account, xbrl_tag, decimals) when the
    underlying FactRow carries them — see Codex round-2 finding F6.

    Phase 3.4 (schema §8.1): also carries audit lineage so that derived
    rows can claim `has_audited_inputs` and trace back to source cell_ids:
      - audit_source       (canonical, normalized)
      - audit_source_raw   (forensic raw legacy enum)
      - audit_evidence     (whatever audit_evidence dict was set)
    Does NOT include classification_source — that's row metadata, not
    value provenance, and isn't relevant for derived value lineage.
    """
    base = {
        "cell_id": f.cell_id,
        "uni_account": f.uni_account,
        "period": f.period,
        "period_end": getattr(f, "period_end", None),
        "value": f.value,
        "unit": getattr(f, "unit", None),
        "status": f.status,
        "source_account": getattr(f, "source_account", None),
        "xbrl_tag": getattr(f, "xbrl_tag", None),
    }
    # Optional restatement-trace fields — present on production FactRow.provenance
    # after io_loader._backfill_filing_provenance() runs. Read via provenance
    # dict when not a direct attribute. R4-F4: include form/filing_date/
    # primary_doc and mark precision_unknown when decimals absent so the
    # output honestly reflects what audit lineage is and isn't available.
    prov = getattr(f, "provenance", {}) or {}
    for key in ("accession_number", "source_filing", "form", "filing_date",
                "primary_doc", "decimals"):
        val = getattr(f, key, None) or prov.get(key)
        if val is not None:
            base[key] = val
    if base.get("decimals") is None:
        base["precision_unknown"] = True
    # Phase 3.4: audit lineage (schema §8.1)
    for key in ("audit_source", "audit_source_raw", "audit_evidence"):
        val = prov.get(key)
        if val is not None:
            base[key] = val
    return base
