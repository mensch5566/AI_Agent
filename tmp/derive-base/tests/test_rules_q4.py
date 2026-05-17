from rules_q4 import q4_candidates


def test_q4_prefer_fy_minus_9m(sample_gaap_revenue_facts):
    # FY=249000, 9M=148000 → Q4=101000
    cands = q4_candidates(sample_gaap_revenue_facts)
    # Expect one Q4 candidate per (uni_account, fy) where inputs are sufficient
    q4 = [c for c in cands if c.period == "Q4_FY2024"]
    assert len(q4) == 1
    assert q4[0].value == 101000.0
    assert q4[0].rule_id == "Q4_FY_MINUS_9M"
    assert q4[0].rule_priority == 1
    assert q4[0].uni_account == "revenue"
    assert q4[0].period_kind == "derived_q4"
    assert q4[0].chain_depth == 1


def test_q4_fallback_when_9m_missing(sample_gaap_revenue_facts):
    rows_no_9m = [f for f in sample_gaap_revenue_facts if f.period != "9M_FY2024"]
    cands = q4_candidates(rows_no_9m)
    q4 = [c for c in cands if c.period == "Q4_FY2024"]
    assert len(q4) == 1
    # FY 249000 - (40000+43000+65000) = 101000
    assert q4[0].value == 101000.0
    assert q4[0].rule_id == "Q4_FY_MINUS_Q1Q2Q3"
    assert q4[0].rule_priority == 2


def test_q4_skipped_when_missing_inputs(sample_gaap_revenue_facts):
    rows_no_fy = [f for f in sample_gaap_revenue_facts if f.period != "FY2024"]
    cands = q4_candidates(rows_no_fy)
    assert [c for c in cands if c.period == "Q4_FY2024"] == []


def test_q4_only_for_is_cf_gaap(sample_gaap_revenue_facts):
    # If we relabel everything as BS, nothing should be derived
    for f in sample_gaap_revenue_facts:
        f.statement = "BS"
    cands = q4_candidates(sample_gaap_revenue_facts)
    assert cands == []


def test_q4_skipped_when_units_mismatch(sample_gaap_revenue_facts):
    """If FY is in USD_millions but YTD/quarters are in USD_thousands,
    _units_match() should drop the candidate silently — derive must never
    mix units."""
    for f in sample_gaap_revenue_facts:
        if f.period == "FY2024":
            f.unit = "USD_millions"   # mismatch vs other periods (USD_thousands)
    cands = q4_candidates(sample_gaap_revenue_facts)
    assert [c for c in cands if c.period == "Q4_FY2024"] == []


def test_q4_skipped_when_q4_already_direct(sample_gaap_revenue_facts):
    """If Q4 is already a direct fact, derive must NOT emit a candidate
    (facts always win — disclosed > derived)."""
    from _shared.sec_json_adapter import FactRow
    direct_q4 = FactRow(
        cell_id="q4_direct", ticker="AAOI", period="Q4_FY2024",
        period_end="2024-12-31", period_kind="quarter_duration",
        statement="IS", version="GAAP", uni_account="revenue",
        source_account="us-gaap:Revenues", xbrl_tag="Revenues",
        value=101050.0, weight=1, unit="USD_thousands",
        status="SOURCE_OF_TRUTH", ordinal=None, long_tail_metadata=None,
        provenance={},
    )
    facts = list(sample_gaap_revenue_facts) + [direct_q4]
    cands = q4_candidates(facts)
    assert [c for c in cands if c.period == "Q4_FY2024"] == []
