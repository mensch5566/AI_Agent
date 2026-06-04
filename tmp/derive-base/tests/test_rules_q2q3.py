"""Tests for Q2/Q3 single-quarter reconstruction (rules_q2q3.q2q3_candidates).

Q2 = 6M − Q1   (second quarter = H1 YTD minus Q1)
Q3 = 9M − 6M   (third  quarter = 9M YTD minus H1 YTD)

Same scope/guards as Q4 (rules_q4): GAAP only, IS/CF only, additive USD units
only (no long-tail buckets, no per-share/ratio/share-count), concept + unit
identity required across inputs, never emitted when the single quarter is
already directly disclosed.
"""
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent.parent / "Tools" / "research-tools"))

import pytest
from rules_q2q3 import q2q3_candidates
from _shared.sec_json_adapter import FactRow


def _facts(rows, **overrides):
    base = dict(
        ticker="AAOI", statement="IS", version="GAAP",
        uni_account="revenue", source_account="us-gaap:Revenues",
        xbrl_tag="Revenues", unit="USD_thousands", weight=1,
        status="SOURCE_OF_TRUTH", ordinal=None, long_tail_metadata=None,
        provenance={"source_filing": "10-Q"},
    )
    base.update(overrides)
    return [FactRow(**{**base, **r}) for r in rows]


# Canonical period set WITHOUT direct Q2 and Q3 — only Q1 + 6M + 9M + FY.
# (Models a YTD-first-class parse: single-quarter Q2/Q3 are NOT disclosed.)
def _ytd_only_rows():
    return [
        {"cell_id": "q1", "period": "Q1_FY2024", "period_kind": "quarter_duration", "period_end": "2024-03-31", "value": 40000.0},
        {"cell_id": "h1", "period": "6M_FY2024", "period_kind": "ytd_duration",     "period_end": "2024-06-30", "value": 83000.0},
        {"cell_id": "9m", "period": "9M_FY2024", "period_kind": "ytd_duration",     "period_end": "2024-09-30", "value": 148000.0},
        {"cell_id": "fy", "period": "FY2024",    "period_kind": "fy_annual_duration","period_end": "2024-12-31", "value": 249000.0},
    ]


def test_q2_from_6m_minus_q1():
    cands = q2q3_candidates(_facts(_ytd_only_rows()))
    q2 = [c for c in cands if c.period == "Q2_FY2024"]
    assert len(q2) == 1
    c = q2[0]
    assert c.value == 43000.0                 # 83000 − 40000
    assert c.rule_id == "Q2_6M_MINUS_Q1"
    assert c.rule_priority == 1
    assert c.period_kind == "derived_q2"
    assert c.uni_account == "revenue"
    assert c.unit == "USD_thousands"
    assert c.period_end == "2024-06-30"        # Q2 ends when 6M ends
    assert c.period_start == "2024-04-01"      # day after Q1 end
    assert c.chain_depth == 1
    assert len(c.inputs) == 2                  # [6M, Q1]


def test_q3_from_9m_minus_6m():
    cands = q2q3_candidates(_facts(_ytd_only_rows()))
    q3 = [c for c in cands if c.period == "Q3_FY2024"]
    assert len(q3) == 1
    c = q3[0]
    assert c.value == 65000.0                  # 148000 − 83000
    assert c.rule_id == "Q3_9M_MINUS_6M"
    assert c.rule_priority == 1
    assert c.period_kind == "derived_q3"
    assert c.period_end == "2024-09-30"        # Q3 ends when 9M ends
    assert c.period_start == "2024-07-01"      # day after 6M end
    assert len(c.inputs) == 2                  # [9M, 6M]


def test_no_derive_when_quarter_already_direct():
    # Full set incl. direct Q2 + Q3 → neither is reconstructed.
    rows = _ytd_only_rows() + [
        {"cell_id": "q2", "period": "Q2_FY2024", "period_kind": "quarter_duration", "period_end": "2024-06-30", "value": 43000.0},
        {"cell_id": "q3", "period": "Q3_FY2024", "period_kind": "quarter_duration", "period_end": "2024-09-30", "value": 65000.0},
    ]
    cands = q2q3_candidates(_facts(rows))
    assert [c for c in cands if c.period in ("Q2_FY2024", "Q3_FY2024")] == []


def test_q2_skipped_when_6m_missing():
    rows = [r for r in _ytd_only_rows() if r["period"] != "6M_FY2024"]
    cands = q2q3_candidates(_facts(rows))
    # No 6M → cannot build Q2 (and Q3 needs 6M too).
    assert [c for c in cands if c.period == "Q2_FY2024"] == []
    assert [c for c in cands if c.period == "Q3_FY2024"] == []


def test_q3_skipped_when_9m_missing():
    rows = [r for r in _ytd_only_rows() if r["period"] != "9M_FY2024"]
    cands = q2q3_candidates(_facts(rows))
    assert [c for c in cands if c.period == "Q3_FY2024"] == []
    # Q2 still derivable (needs 6M + Q1 only).
    assert len([c for c in cands if c.period == "Q2_FY2024"]) == 1


def test_q2_skipped_when_q1_missing():
    rows = [r for r in _ytd_only_rows() if r["period"] != "Q1_FY2024"]
    cands = q2q3_candidates(_facts(rows))
    assert [c for c in cands if c.period == "Q2_FY2024"] == []
    # Q3 = 9M − 6M does not need Q1 → still derivable.
    assert len([c for c in cands if c.period == "Q3_FY2024"]) == 1


def test_denied_for_non_additive_unit_eps():
    # Per-share is non-additive → denied (allowlist is USD-only), same as Q4.
    cands = q2q3_candidates(_facts(_ytd_only_rows(), unit="Pure", uni_account="eps_diluted"))
    assert cands == []


def test_denied_for_long_tail_bucket():
    cands = q2q3_candidates(_facts(_ytd_only_rows(), uni_account="operating_expense_long_tail"))
    assert cands == []


def test_only_is_cf_statements():
    # BS facts are instant snapshots, not duration → never reconstructed here.
    cands = q2q3_candidates(_facts(_ytd_only_rows(), statement="BS"))
    assert cands == []


def test_cf_statement_reconstructed():
    cands = q2q3_candidates(_facts(_ytd_only_rows(), statement="CF",
                                   uni_account="net_cash_from_operating"))
    assert len([c for c in cands if c.period == "Q2_FY2024"]) == 1
    assert len([c for c in cands if c.period == "Q3_FY2024"]) == 1


def test_concept_mismatch_skip_recorded():
    # 6M tagged differently from Q1 → arithmetically possible, semantically
    # wrong; must skip and record a diagnostic.
    rows = _ytd_only_rows()
    facts = _facts(rows)
    for f in facts:
        if f.period == "Q1_FY2024":
            f.xbrl_tag = "RevenueFromContractWithCustomerExcludingAssessedTax"
            f.source_account = "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"
    skips: list = []
    cands = q2q3_candidates(facts, skips_collector=skips)
    assert [c for c in cands if c.period == "Q2_FY2024"] == []
    assert any(s["reason"] == "concept_mismatch_skip" and s["period"] == "Q2_FY2024" for s in skips)


def test_source_concept_carried_from_ytd_minuend():
    # Derived Q2 carries the concept identity of its YTD minuend (6M) so Pass 3
    # calc-linkbase can match it as a child.
    cands = q2q3_candidates(_facts(_ytd_only_rows()))
    q2 = next(c for c in cands if c.period == "Q2_FY2024")
    assert q2.source_account == "us-gaap:Revenues"
    assert q2.xbrl_tag == "Revenues"


def test_non_gaap_excluded():
    cands = q2q3_candidates(_facts(_ytd_only_rows(), version="NON_GAAP"))
    assert cands == []
