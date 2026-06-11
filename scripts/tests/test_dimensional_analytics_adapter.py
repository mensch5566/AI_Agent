"""TDD — adapt_dimensional_analytics_facts (segment operating margin → DimensionalRow).

The derived segment margin rides into sec_financial_dimensional_facts on its own
delete-scope (provenance.derived=true, rule_id). CRITICAL: the margin value is a
raw fraction and must be stored verbatim — it must NOT pass through
normalize_pct_value (a segment with |margin| > 1, e.g. a small-revenue / big-loss
unit, would be corrupted by the >1 -> /100 heuristic).

Run: uv run --with pytest python3 -m pytest scripts/tests/test_dimensional_analytics_adapter.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "Tools" / "research-tools"))

from _shared.sec_json_adapter import adapt_dimensional_analytics_facts, DimensionalRow


def _margin(member, value, period="FY2025", period_kind="fy_annual",
            qname=None, other=None):
    return {
        "axis": "business_segment",
        "axis_qname": "us-gaap:StatementBusinessSegmentsAxis",
        "source_account": member,
        "source_account_qname": qname or f"ext:{member.replace(' ', '')}Member",
        "uni_account": "operating_margin_pct",
        "value": value,
        "unit": "pct",
        "period": period,
        "period_end": "2025-12-31",
        "period_kind": period_kind,
        "type": "GAAP_SEGMENT",
        "other_dimensions": other or [],
        "provenance": {
            "derived": True,
            "rule_id": "DIM_SEGMENT_OPERATING_MARGIN_PCT",
            "formula": "operating_income / revenue",
            "inputs": [
                {"uni_account": "operating_income", "value": 9317e6, "unit": "usd"},
                {"uni_account": "revenue", "value": 32228e6, "unit": "usd"},
            ],
        },
    }


def _doc(metrics):
    return {"metadata": {"ticker": "INTC"}, "dimensional_metrics": metrics}


def test_basic_margin_row():
    rows, rej = adapt_dimensional_analytics_facts(_doc([_margin("Client Computing", 0.289)]))
    assert rej == []
    assert len(rows) == 1
    r = rows[0]
    assert isinstance(r, DimensionalRow)
    assert r.uni_account == "operating_margin_pct"
    assert r.axis == "business_segment"
    assert r.member == "Client Computing"
    assert abs(r.value - 0.289) < 1e-12
    assert r.unit == "Pure"
    assert r.period == "FY2025"
    assert r.period_kind == "fy_annual_duration"   # normalized from fy_annual
    assert r.provenance["derived"] is True
    assert r.provenance["rule_id"] == "DIM_SEGMENT_OPERATING_MARGIN_PCT"
    assert isinstance(r.cell_id, str) and len(r.cell_id) > 0


def test_margin_over_100pct_not_corrupted():
    """A segment losing more than its revenue → margin < -1. Must store -1.5
    verbatim, NOT -0.015 (the normalize_pct_value >1 -> /100 trap)."""
    rows, rej = adapt_dimensional_analytics_facts(_doc([_margin("Startup Unit", -1.5)]))
    assert rej == []
    assert len(rows) == 1
    assert abs(rows[0].value - (-1.5)) < 1e-12   # NOT -0.015


def test_margin_over_100pct_positive_not_corrupted():
    rows, _ = adapt_dimensional_analytics_facts(_doc([_margin("X", 1.2)]))
    assert abs(rows[0].value - 1.2) < 1e-12       # NOT 0.012


def test_single_quarter_period_kind_normalized():
    rows, _ = adapt_dimensional_analytics_facts(
        _doc([_margin("A", 0.2, period="Q1_FY2026", period_kind="single_quarter")]))
    assert rows[0].period_kind == "quarter_duration"


def test_cell_id_distinct_per_member():
    rows, _ = adapt_dimensional_analytics_facts(_doc([
        _margin("A", 0.2), _margin("B", 0.3),
    ]))
    assert rows[0].cell_id != rows[1].cell_id


def test_empty_metrics():
    rows, rej = adapt_dimensional_analytics_facts(_doc([]))
    assert rows == [] and rej == []


def test_unknown_period_kind_rejected_not_crash():
    rows, rej = adapt_dimensional_analytics_facts(
        _doc([_margin("A", 0.2, period_kind="weird_kind")]))
    assert rows == []
    assert len(rej) == 1 and "period_kind" in rej[0]["reason"]
