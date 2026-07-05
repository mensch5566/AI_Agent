"""TWSE as-reported facts → FactRow storage adapter (Phase E).

The DB `sec_financial_facts` layer must be AS-REPORTED (capex kept negative, cash
balances present) — mirroring how compose uses emit_canonical_facts and how US
facts come straight from parse. This is DISTINCT from `adapt_twse_facts`
(twse_json_adapter) which applies derive-only transforms (capex→positive,
cash-balance exclusion) for the derive engine.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Tools" / "research-tools"))
from _shared.twse_canonical_facts import adapt_twse_canonical_facts


def _fx(period, facts, period_end="2025-06-30", cat="ir"):
    return {"ticker": "3081", "report_category": cat, "unit": "TWD_thousands",
            "periods": [period],
            "facts_by_period": {period: {"period_end": period_end,
                                         "report_category": cat, "facts": facts}}}


def _fact(value, stmt, sort=1000, kind="ytd", concept="ifrs-full:X"):
    return {"value": value, "statement": stmt, "sort_order": sort,
            "period_kind": kind, "xbrl_concept": concept}


def _one(rows, uni, period=None):
    hits = [r for r in rows if r.uni_account == uni and (period is None or r.period == period)]
    assert len(hits) == 1, (uni, period, [(r.uni_account, r.period) for r in rows])
    return hits[0]


def test_capex_kept_negative_as_reported():
    # As-reported: capex is an outflow, stays negative (NOT flipped to positive).
    rows = adapt_twse_canonical_facts(_fx("Q1_FY2025",
        {"capital_expenditures": _fact(-7237.0, "cash_flow_investing")}, "2025-03-31"))
    r = _one(rows, "capital_expenditures")
    assert r.value == -7237.0, "as-reported capex must stay negative"
    assert r.statement == "CF" and r.status == "SOURCE_OF_TRUTH" and r.version == "GAAP"


def test_cash_balances_present():
    # Beginning/ending cash are balances — kept in the as-reported facts layer.
    rows = adapt_twse_canonical_facts(_fx("Q1_FY2025", {
        "beginning_cash": _fact(580648.0, "cash_flow_summary"),
        "ending_cash":    _fact(525916.0, "cash_flow_summary"),
    }, "2025-03-31"))
    assert _one(rows, "beginning_cash").value == 580648.0
    assert _one(rows, "ending_cash").value == 525916.0


def test_period_kind_inferred_for_db():
    # period_kind must be the DB enum (quarter_duration / instant_period_end), not raw.
    rows = adapt_twse_canonical_facts(_fx("Q1_FY2025", {
        "revenue":      _fact(100.0, "income_statement"),
        "total_assets": _fact(999.0, "balance_sheet_assets", kind="instant"),
    }, "2025-03-31"))
    assert _one(rows, "revenue").period_kind == "quarter_duration"
    assert _one(rows, "total_assets").period_kind == "instant_period_end"


def test_eps_unit_and_money_unit():
    rows = adapt_twse_canonical_facts(_fx("Q1_FY2025", {
        "eps_basic": _fact(3.44, "income_statement"),
        "revenue":   _fact(100.0, "income_statement"),
    }, "2025-03-31"))
    assert _one(rows, "eps_basic").unit == "TWD_per_share"
    assert _one(rows, "revenue").unit == "TWD_thousands"


def test_q2_ytd_relabel_and_disclosed_single_quarter():
    rows = adapt_twse_canonical_facts(_fx("Q2_FY2025", {
        "revenue":    _fact(220.0, "income_statement"),
        "revenue__q": _fact(120.0, "income_statement", kind="quarter"),
    }))
    ytd = _one(rows, "revenue", "6M_FY2025")
    assert ytd.period_kind == "ytd_duration"
    dq = _one(rows, "revenue", "Q2_FY2025")
    assert dq.period_kind == "quarter_duration" and dq.value == 120.0


def test_provenance_market_tw_asreported():
    rows = adapt_twse_canonical_facts(_fx("Q1_FY2025",
        {"revenue": _fact(100.0, "income_statement")}, "2025-03-31"))
    p = _one(rows, "revenue").provenance
    assert p["market"] == "TW" and p.get("as_reported") is True


def test_unique_cell_ids():
    rows = adapt_twse_canonical_facts(_fx("Q1_FY2025", {
        "revenue": _fact(100.0, "income_statement"),
        "cost_of_goods_sold": _fact(40.0, "income_statement"),
        "total_assets": _fact(999.0, "balance_sheet_assets", kind="instant"),
        "capital_expenditures": _fact(-5.0, "cash_flow_investing"),
    }, "2025-03-31"))
    ids = [r.cell_id for r in rows]
    assert len(ids) == len(set(ids)), "cell_ids must be unique"


def test_fail_closed_on_non_twd_unit():
    import pytest
    with pytest.raises(ValueError):
        adapt_twse_canonical_facts({"ticker": "3081", "unit": "USD_thousands",
                                    "facts_by_period": {}})
