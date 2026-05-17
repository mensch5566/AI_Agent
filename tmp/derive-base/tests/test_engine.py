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


def test_resolve_within_band_picks_preferred_no_conflict():
    """Small diff (within tolerance band) → preferred wins silently, no conflict."""
    # USD_thousands abs_tol=1.0; 100.0 vs 100.05 → within
    a = _c(rule_id="Q4_FY_MINUS_9M",     rule_priority=1, value=100.0)
    b = _c(rule_id="Q4_FY_MINUS_Q1Q2Q3", rule_priority=2, value=100.05)
    winners, conflicts = resolve_candidates([a, b])
    assert len(winners) == 1
    assert winners[0].rule_id == "Q4_FY_MINUS_9M"
    assert conflicts == []


def test_resolve_single_candidate_per_key():
    """One candidate per key → always wins, no comparison loop runs."""
    a = _c(value=42.0)
    winners, conflicts = resolve_candidates([a])
    assert len(winners) == 1
    assert winners[0].value == 42.0
    assert conflicts == []


def test_resolve_stable_tie_break_by_insertion_order():
    """When (rule_priority, chain_depth) are identical, the candidate that
    appeared first in input wins (Python sorted() is stable)."""
    # Both at priority 3, depth 1; first inserted is rule_a
    a = _c(rule_id="rule_a", rule_priority=3, chain_depth=1, value=10.0)
    b = _c(rule_id="rule_b", rule_priority=3, chain_depth=1, value=10.0)
    winners, _ = resolve_candidates([a, b])
    assert len(winners) == 1
    assert winners[0].rule_id == "rule_a"

    # Reverse insertion order → other wins
    winners2, _ = resolve_candidates([b, a])
    assert winners2[0].rule_id == "rule_b"


def test_run_engine_q4_then_identity(sample_gaap_revenue_facts):
    """Pass 2 emits Q4 revenue (FY-9M=101000). Pass 3 has no IS subtotal
    children to derive a parent from (only revenue exists), so Pass 3
    emits nothing. Final winners = 1 row."""
    from derive_engine import run_engine
    result = run_engine(
        facts=sample_gaap_revenue_facts,
        calc_rules={},          # no calc edges → only Q4 rule fires
        qname_to_uni={},
    )
    rows = result["winners"]
    assert len(rows) == 1
    assert rows[0].uni_account == "revenue"
    assert rows[0].period == "Q4_FY2024"
    assert rows[0].value == 101000.0
    # Stats sanity
    s = result["stats"]
    assert s["pass1_count"] == 0
    assert s["pass2_count"] == 1
    assert s["pass3_count"] == 0
    assert s["conflicts"] == 0
