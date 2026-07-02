"""TWSE facts → FactRow adapter (derive-A spec §4). Fixture-driven, covers the
eight conversion rules + __q reconciliation + Argue-mandated guards."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Tools" / "research-tools"))
from _shared.twse_json_adapter import (
    adapt_company_twse, adapt_twse_facts, reconcile_disclosed_quarters,
)


def _fx(period, facts, period_end="2025-06-30", cat="ir"):
    return {"ticker": "3081", "report_category": cat, "unit": "TWD_thousands",
            "periods": [period],
            "facts_by_period": {period: {"period_end": period_end,
                                         "report_category": cat, "facts": facts}}}


def _fact(value, stmt, sort, kind, concept="ifrs-full:X"):
    return {"value": value, "statement": stmt, "sort_order": sort,
            "period_kind": kind, "xbrl_concept": concept}


def _one(rows, uni, period=None):
    hits = [r for r in rows if r.uni_account == uni and (period is None or r.period == period)]
    assert len(hits) == 1, (uni, period, [(r.uni_account, r.period) for r in rows])
    return hits[0]


def test_company_row_twd():
    c = adapt_company_twse(_fx("Q1_FY2025", {}))
    assert c.currency == "TWD" and c.exchange == "TWSE" and c.fiscal_year_end_month == 12


def test_q1_ytd_is_single_quarter():
    rows = adapt_twse_facts(_fx("Q1_FY2025",
        {"revenue": _fact(100.0, "income_statement", 4000, "ytd")}, "2025-03-31"))
    r = _one(rows, "revenue")
    assert r.period == "Q1_FY2025" and r.period_kind == "quarter_duration"
    assert r.unit == "TWD_thousands" and r.status == "SOURCE_OF_TRUTH"
    assert r.version == "GAAP" and r.statement == "IS" and r.weight == 1


def test_q2_ytd_relabels_6m_and_dq_promotes():
    rows = adapt_twse_facts(_fx("Q2_FY2025", {
        "revenue":     _fact(220.0, "income_statement", 4000, "ytd"),
        "revenue__q":  _fact(120.0, "income_statement", 4000, "quarter"),
    }))
    ytd = _one(rows, "revenue", "6M_FY2025")
    assert ytd.period_kind == "ytd_duration"
    dq = _one(rows, "revenue", "Q2_FY2025")
    assert dq.period_kind == "quarter_duration" and dq.status == "SOURCE_OF_TRUTH"
    assert dq.provenance["disclosed_single_quarter"] is True


def test_annual_is_cf_fy_but_bs_q4():
    rows = adapt_twse_facts(_fx("Q4_FY2024", {
        "revenue":      _fact(500.0, "income_statement", 4000, "ytd"),
        "net_cash_from_operating": _fact(80.0, "cash_flow_operating", 8010, "ytd"),
        "total_assets": _fact(999.0, "balance_sheet_assets", 1900, "instant"),
    }, "2024-12-31"))
    assert _one(rows, "revenue").period == "FY2024"
    assert _one(rows, "revenue").period_kind == "fy_annual_duration"
    assert _one(rows, "net_cash_from_operating").period == "FY2024"
    bs = _one(rows, "total_assets")
    assert bs.period == "Q4_FY2024" and bs.period_kind == "instant_period_end"  # Argue: 年末 BS=Q4_FY


def test_quarterly_bs_keeps_q_label():
    rows = adapt_twse_facts(_fx("Q2_FY2025",
        {"total_assets": _fact(900.0, "balance_sheet_assets", 1900, "instant")}))
    assert _one(rows, "total_assets").period == "Q2_FY2025"


def test_eps_unit_twd_per_share():
    rows = adapt_twse_facts(_fx("Q1_FY2025",
        {"eps_basic": _fact(1.23, "income_statement", 9710, "ytd")}, "2025-03-31"))
    assert _one(rows, "eps_basic").unit == "TWD_per_share"


def test_capex_sign_flips_to_positive_outflow():
    # Argue 關鍵刀:台股揭 -502002(帶號流出);共用 FCF 規則 coef=-1 期望正支出
    rows = adapt_twse_facts(_fx("Q1_FY2025",
        {"capital_expenditures": _fact(-502002.0, "cash_flow_investing", 8021, "ytd")},
        "2025-03-31"))
    assert _one(rows, "capital_expenditures").value == 502002.0


def test_net_flows_keep_signed_values():
    rows = adapt_twse_facts(_fx("Q1_FY2025",
        {"net_cash_from_investing": _fact(-511174.0, "cash_flow_investing", 8020, "ytd")},
        "2025-03-31"))
    assert _one(rows, "net_cash_from_investing").value == -511174.0


def test_cash_balances_excluded_net_change_kept():
    # Argue 關鍵刀:balance 進了重建流會被 FY−9M 硬算
    rows = adapt_twse_facts(_fx("Q1_FY2025", {
        "beginning_cash":     _fact(2048546.0, "cash_flow_summary", 8045, "ytd"),
        "ending_cash":        _fact(1907355.0, "cash_flow_summary", 8050, "ytd"),
        "net_change_in_cash": _fact(-141191.0, "cash_flow_summary", 8040, "ytd"),
    }, "2025-03-31"))
    unis = {r.uni_account for r in rows}
    assert unis == {"net_change_in_cash"}


def test_provenance_and_concept_carried():
    rows = adapt_twse_facts(_fx("Q1_FY2025",
        {"revenue": _fact(100.0, "income_statement", 4000, "ytd", "ifrs-full:Revenue")},
        "2025-03-31"))
    r = _one(rows, "revenue")
    assert r.source_account == "ifrs-full:Revenue" and r.xbrl_tag == "ifrs-full:Revenue"
    assert r.provenance["market"] == "TW"
    assert r.provenance["substatement"] == "income_statement"
    assert r.period_end == "2025-03-31" and r.cell_id


def test_unexpected_top_unit_fails_closed():
    bad = _fx("Q1_FY2025", {})
    bad["unit"] = "TWD_millions"
    try:
        adapt_twse_facts(bad)
        assert False, "should raise"
    except ValueError:
        pass


def test_reconcile_disclosed_quarters():
    fx = {"ticker": "3081", "report_category": "ir", "unit": "TWD_thousands",
          "periods": ["Q1_FY2025", "Q2_FY2025"],
          "facts_by_period": {
              "Q1_FY2025": {"period_end": "2025-03-31", "report_category": "ir",
                  "facts": {"revenue": _fact(100.0, "income_statement", 4000, "ytd")}},
              "Q2_FY2025": {"period_end": "2025-06-30", "report_category": "ir",
                  "facts": {"revenue":    _fact(220.0, "income_statement", 4000, "ytd"),
                            "revenue__q": _fact(120.0, "income_statement", 4000, "quarter"),
                            "eps_basic":    _fact(2.0, "income_statement", 9710, "ytd"),
                            "eps_basic__q": _fact(1.1, "income_statement", 9710, "quarter")}}}}
    rep = reconcile_disclosed_quarters(fx)
    rev = [r for r in rep if r["uni_account"] == "revenue"][0]
    assert rev["status"] == "MATCH" and rev["ytd_diff"] == 120.0
    eps = [r for r in rep if r["uni_account"] == "eps_basic"][0]
    assert eps["status"] == "SKIPPED_NON_ADDITIVE"   # per-share 不做 ytd 差對帳


def test_reconcile_flags_mismatch():
    fx = {"ticker": "3081", "report_category": "ir", "unit": "TWD_thousands",
          "periods": ["Q1_FY2025", "Q2_FY2025"],
          "facts_by_period": {
              "Q1_FY2025": {"period_end": "2025-03-31", "report_category": "ir",
                  "facts": {"revenue": _fact(100.0, "income_statement", 4000, "ytd")}},
              "Q2_FY2025": {"period_end": "2025-06-30", "report_category": "ir",
                  "facts": {"revenue":    _fact(220.0, "income_statement", 4000, "ytd"),
                            "revenue__q": _fact(119.0, "income_statement", 4000, "quarter")}}}}
    rev = [r for r in reconcile_disclosed_quarters(fx) if r["uni_account"] == "revenue"][0]
    assert rev["status"] == "MISMATCH" and rev["diff"] == -1.0
