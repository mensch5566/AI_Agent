from derive_engine import resolve_candidates
from derive_types import Candidate


def _c(**kw):
    base = dict(
        ticker="X", period="Q4_FY2024", period_kind="derived_q4",
        period_start=None, period_end="2024-12-31",
        statement="IS", version="GAAP", uni_account="revenue",
        value=100.0, unit="USD_thousands",
        rule_id="Q4_FY_MINUS_9M", rule_priority=1,
        chain_depth=1, chained=False, inputs=[], extras={},
    )
    base.update(kw)
    return Candidate(**base)


def test_resolve_prefers_lowest_priority():
    a = _c(rule_id="Q4_FY_MINUS_9M",     rule_priority=1, value=100.0)
    b = _c(rule_id="Q4_FY_MINUS_Q1Q2Q3", rule_priority=2, value=100.1)
    winners, conflicts = resolve_candidates([a, b])
    assert len(winners) == 1
    assert winners[0].rule_id == "Q4_FY_MINUS_9M"
    assert conflicts == []


def test_resolve_hard_conflict_skips_both():
    a = _c(rule_id="Q4_FY_MINUS_9M",     rule_priority=1, value=100.0)
    b = _c(rule_id="Q4_FY_MINUS_Q1Q2Q3", rule_priority=2, value=200.0)
    winners, conflicts = resolve_candidates([a, b])
    assert winners == []
    assert len(conflicts) == 1
    assert conflicts[0]["uni_account"] == "revenue"


def test_resolve_two_keys_independent():
    a = _c(uni_account="revenue",      value=100.0)
    b = _c(uni_account="gross_profit", value=40.0)
    winners, conflicts = resolve_candidates([a, b])
    assert len(winners) == 2
