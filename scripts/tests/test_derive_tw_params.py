"""Engine parameterization for TWD (derive-A spec §5). US behavior frozen by
Gate 3 (Task 9); these tests lock the TW-side semantics unit-level."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Tools" / "research-tools"))
sys.path.insert(0, "/Users/mensch5566/CC_Switch_Config/skills/derive-base/scripts")
sys.path.insert(0, "/Users/mensch5566/CC_Switch_Config/skills/derive-analytics/scripts")

from _shared.sec_json_adapter import FactRow


def _row(uni, period, value, *, stmt="IS", unit="TWD_thousands", kind="quarter_duration",
         pe="2025-03-31", version="GAAP"):
    return FactRow(cell_id=f"t::{uni}::{period}", ticker="3081", period=period,
                   period_end=pe, period_kind=kind, statement=stmt, version=version,
                   uni_account=uni, source_account="ifrs-full:X", xbrl_tag="ifrs-full:X",
                   value=value, weight=1, unit=unit, status="SOURCE_OF_TRUTH",
                   ordinal=None, long_tail_metadata=None, provenance={})


def test_q4_reconstruction_accepts_twd():
    from rules_q4 import q4_candidates
    facts = [
        _row("revenue", "FY2024", 500.0, kind="fy_annual_duration", pe="2024-12-31"),
        _row("revenue", "9M_FY2024", 380.0, kind="ytd_duration", pe="2024-09-30"),
    ]
    cands = q4_candidates(facts)
    assert len(cands) == 1
    assert cands[0].value == 120.0 and cands[0].unit == "TWD_thousands"
    assert cands[0].rule_id == "Q4_FY_MINUS_9M"


def test_q4_eps_approx_never_fires_for_twd_per_share():
    # spec §5 row 4:_EPS_UNIT="USD_per_share" 即是 market gate — TW 留空是紀律
    from rules_q4 import q4_eps_approx_candidates
    facts = [
        _row("eps_basic", "FY2024", 4.66, unit="TWD_per_share", kind="fy_annual_duration", pe="2024-12-31"),
        _row("eps_basic", "Q1_FY2024", 1.0, unit="TWD_per_share"),
        _row("eps_basic", "Q2_FY2024", 1.2, unit="TWD_per_share"),
        _row("eps_basic", "Q3_FY2024", 1.3, unit="TWD_per_share"),
    ]
    assert q4_eps_approx_candidates(facts) == []


def test_tolerance_has_twd_entries():
    from tolerance import ABS_TOL_BY_UNIT
    assert ABS_TOL_BY_UNIT["TWD_thousands"] == 1.0
    assert ABS_TOL_BY_UNIT["TWD_per_share"] == 0.01


def test_da_identity_from_split_components():
    from rules_identity import apply_static_allowlist
    facts = [
        _row("depreciation_expense", "Q1_FY2025", 30.0, stmt="CF"),
        _row("amortization_expense", "Q1_FY2025", 12.0, stmt="CF"),
    ]
    cands = apply_static_allowlist(facts, "GAAP")
    da = [c for c in cands if c.uni_account == "depreciation_and_amortization"]
    assert len(da) == 1
    assert da[0].value == 42.0 and da[0].statement == "CF"
    assert da[0].rule_id == "IDENTITY_DA_DEP_PLUS_AMORT"
    assert da[0].extras["formula"] == "depreciation_expense + amortization_expense"


def test_da_identity_skips_when_da_direct():
    from rules_identity import apply_static_allowlist
    facts = [
        _row("depreciation_expense", "Q1_FY2025", 30.0, stmt="CF"),
        _row("amortization_expense", "Q1_FY2025", 12.0, stmt="CF"),
        _row("depreciation_and_amortization", "Q1_FY2025", 42.0, stmt="CF"),
    ]
    cands = apply_static_allowlist(facts, "GAAP")
    assert not [c for c in cands if c.uni_account == "depreciation_and_amortization"]


def test_existing_allowlist_formula_unchanged():
    # Gate 3 前哨:5-tuple 舊規則的 formula 字串必須維持 " - ".join
    from rules_identity import apply_static_allowlist
    facts = [
        _row("revenue", "Q1_FY2025", 100.0),
        _row("cost_of_goods_sold", "Q1_FY2025", 60.0),
    ]
    gp = [c for c in apply_static_allowlist(facts, "GAAP")
          if c.uni_account == "gross_profit"]
    assert gp and gp[0].extras["formula"] == "revenue - cost_of_goods_sold"


def test_money_scale_accepts_twd():
    import rules_ratios as rr
    assert rr._MONEY_SCALE["TWD_thousands"] == 1e3
    assert rr._MONEY_SCALE["USD_millions"] == 1e6   # US 原值不動
