"""Task 6 — NLM ordering artifact matcher + schema + reader (spec G1, G7, G8).

Pure-Python tests: no network, no NLM calls. The matcher binds human-audited
PDF lines (top-to-bottom order) to fact cell_ids so the frontend can order
rows for statements that have NO XBRL presentation network (AAOI BS/CF).

Safety properties under test:
  - G8: NEVER guess at the uni_account tier when >1 display-eligible candidate.
  - G1/G7: NEVER feed a pending_audit artifact's order into production.

Run: uv run --with pytest python3 -m pytest scripts/tests/test_nlm_statement_order.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from nlm_statement_order import (  # noqa: E402
    match_pdf_line_to_fact,
    bidirectional_unmatched,
    validate_artifact,
    read_audited_order,
    produce_nlm_order,
)

import json


# --------------------------------------------------------------------------- #
# match_pdf_line_to_fact — priority order + uniqueness (G8)
# --------------------------------------------------------------------------- #
def test_uni_fallback_requires_unique_candidate():
    facts = [
        {"uni_account": "x", "display_label": None, "source_account": None, "cell_id": "a"},
        {"uni_account": "x", "display_label": None, "source_account": None, "cell_id": "b"},
    ]
    pdf_line = {"pdf_label": "X", "ordinal": 1}
    res = match_pdf_line_to_fact(pdf_line, facts, display_eligible=True)
    assert res["matched_cell_id"] is None
    assert res["unmatched_reason"] == "ambiguous_uni_account"
    assert res["match_method"] is None


def test_uni_fallback_unique_candidate_matches():
    facts = [
        {"uni_account": "x", "display_label": None, "source_account": None, "cell_id": "only"},
    ]
    pdf_line = {"pdf_label": "X", "ordinal": 1}
    res = match_pdf_line_to_fact(pdf_line, facts, display_eligible=True)
    assert res["matched_cell_id"] == "only"
    assert res["match_method"] == "uni_account"
    assert res["unmatched_reason"] is None


def test_exact_display_label_wins():
    facts = [
        {
            "uni_account": "u",
            "display_label": "Net income",
            "source_account": "NetIncomeLoss",
            "cell_id": "c1",
        }
    ]
    res = match_pdf_line_to_fact({"pdf_label": "Net income", "ordinal": 3}, facts, True)
    assert res["matched_cell_id"] == "c1"
    assert res["match_method"] == "exact_display_label"
    assert res["unmatched_reason"] is None


def test_exact_display_label_beats_lower_tiers():
    # Two facts: one matches exact display_label, another would match
    # source_account. Exact display_label must win.
    facts = [
        {
            "uni_account": "u1",
            "display_label": "Net income",
            "source_account": "Other",
            "cell_id": "win",
        },
        {
            "uni_account": "u2",
            "display_label": "Something else",
            "source_account": "Net income",
            "cell_id": "lose",
        },
    ]
    res = match_pdf_line_to_fact({"pdf_label": "Net income", "ordinal": 1}, facts, True)
    assert res["matched_cell_id"] == "win"
    assert res["match_method"] == "exact_display_label"


def test_normalized_display_label_match():
    # Differs by case, extra whitespace, and a trailing colon/punctuation.
    facts = [
        {
            "uni_account": "u",
            "display_label": "Total current assets",
            "source_account": "AssetsCurrent",
            "cell_id": "c2",
        }
    ]
    res = match_pdf_line_to_fact(
        {"pdf_label": "  TOTAL   current assets: ", "ordinal": 5}, facts, True
    )
    assert res["matched_cell_id"] == "c2"
    assert res["match_method"] == "normalized_display_label"


def test_source_account_match():
    facts = [
        {
            "uni_account": "u",
            "display_label": "Friendly label",
            "source_account": "NetIncomeLoss",
            "cell_id": "c3",
        }
    ]
    res = match_pdf_line_to_fact({"pdf_label": "NetIncomeLoss", "ordinal": 2}, facts, True)
    assert res["matched_cell_id"] == "c3"
    assert res["match_method"] == "source_account"


def test_no_match_returns_reason():
    facts = [
        {
            "uni_account": "u",
            "display_label": "Net income",
            "source_account": "NetIncomeLoss",
            "cell_id": "c1",
        }
    ]
    res = match_pdf_line_to_fact({"pdf_label": "Nonexistent line", "ordinal": 9}, facts, True)
    assert res["matched_cell_id"] is None
    assert res["match_method"] is None
    assert res["unmatched_reason"] == "no_fact_for_pdf_line"


def test_no_match_on_empty_facts():
    res = match_pdf_line_to_fact({"pdf_label": "X", "ordinal": 1}, [], True)
    assert res["matched_cell_id"] is None
    assert res["unmatched_reason"] == "no_fact_for_pdf_line"


def test_exact_display_label_ambiguous_falls_through_then_unique_source():
    # Two facts share an exact display_label (non-unique → tier skipped),
    # but only one matches source_account → source_account tier wins.
    facts = [
        {"uni_account": "u1", "display_label": "Cash", "source_account": "AAA", "cell_id": "a"},
        {"uni_account": "u2", "display_label": "Cash", "source_account": "BBB", "cell_id": "b"},
    ]
    # pdf_label "AAA" won't match display_label "Cash" at exact/normalized,
    # but matches source_account AAA uniquely.
    res = match_pdf_line_to_fact({"pdf_label": "AAA", "ordinal": 1}, facts, True)
    assert res["matched_cell_id"] == "a"
    assert res["match_method"] == "source_account"


# --------------------------------------------------------------------------- #
# bidirectional_unmatched
# --------------------------------------------------------------------------- #
def test_bidirectional_unmatched():
    facts = [
        {"uni_account": "u1", "display_label": "Net income", "source_account": "NI", "cell_id": "c1"},
        {"uni_account": "u2", "display_label": "Revenue", "source_account": "REV", "cell_id": "c2"},
    ]
    pdf_lines = [
        {"pdf_label": "Net income", "ordinal": 1},   # matches c1
        {"pdf_label": "Mystery line", "ordinal": 2},  # matches nothing
    ]
    res = bidirectional_unmatched(pdf_lines, facts)
    assert res["pdf_without_fact"] == [{"pdf_label": "Mystery line", "ordinal": 2}]
    assert res["fact_without_pdf_line"] == ["c2"]


def test_bidirectional_all_matched():
    facts = [
        {"uni_account": "u1", "display_label": "Net income", "source_account": "NI", "cell_id": "c1"},
    ]
    pdf_lines = [{"pdf_label": "Net income", "ordinal": 1}]
    res = bidirectional_unmatched(pdf_lines, facts)
    assert res["pdf_without_fact"] == []
    assert res["fact_without_pdf_line"] == []


# --------------------------------------------------------------------------- #
# validate_artifact
# --------------------------------------------------------------------------- #
def _good_artifact():
    return {
        "source_doc": "d",
        "accession": "a",
        "period": "FY2025",
        "form": "10-K",
        "page_or_section": "p1",
        "statement": "BS",
        "status": "audited",
        "signer": "human",
        "lines": [{"ordinal": 1, "pdf_label": "X"}],
    }


def test_validate_artifact_ok():
    assert validate_artifact(_good_artifact()) == []


def test_validate_artifact_flags_bad_status():
    art = _good_artifact()
    art["status"] = "WRONG"
    errs = validate_artifact(art)
    assert any("status" in e for e in errs)


def test_validate_artifact_flags_bad_statement():
    art = _good_artifact()
    art["statement"] = "XX"
    errs = validate_artifact(art)
    assert any("statement" in e for e in errs)


def test_validate_artifact_flags_missing_top_key():
    art = _good_artifact()
    del art["accession"]
    errs = validate_artifact(art)
    assert any("accession" in e for e in errs)


def test_validate_artifact_flags_bad_line():
    art = _good_artifact()
    art["lines"] = [{"ordinal": "not-a-number", "pdf_label": "X"}, {"pdf_label": "Y"}]
    errs = validate_artifact(art)
    # one line has non-numeric ordinal, one is missing ordinal entirely
    assert any("ordinal" in e for e in errs)


def test_validate_artifact_flags_missing_pdf_label():
    art = _good_artifact()
    art["lines"] = [{"ordinal": 1}]
    errs = validate_artifact(art)
    assert any("pdf_label" in e for e in errs)


# --------------------------------------------------------------------------- #
# read_audited_order — G1/G7 safety
# --------------------------------------------------------------------------- #
def test_read_audited_order_skips_pending():
    art = {"status": "pending_audit", "lines": [{"ordinal": 1, "pdf_label": "X", "matched_cell_id": "c1"}]}
    assert read_audited_order(art) == {}


def test_read_audited_order_returns_map_when_audited():
    art = {
        "status": "audited",
        "lines": [
            {"ordinal": 1, "pdf_label": "X", "matched_cell_id": "c1"},
            {"ordinal": 2, "pdf_label": "Y", "matched_cell_id": None},
        ],
    }
    assert read_audited_order(art) == {"c1": 1}


def test_read_audited_order_skips_lines_without_cell_id():
    art = {
        "status": "audited",
        "lines": [
            {"ordinal": 1, "pdf_label": "A", "matched_cell_id": "c1"},
            {"ordinal": 2, "pdf_label": "B"},  # no matched_cell_id key at all
            {"ordinal": 3, "pdf_label": "C", "matched_cell_id": "c3"},
        ],
    }
    assert read_audited_order(art) == {"c1": 1, "c3": 3}


# --------------------------------------------------------------------------- #
# produce_nlm_order — pending_audit artifact producer (NLM call injected)
# --------------------------------------------------------------------------- #
def _stub_query(lines):
    def q(ticker, statement):
        return lines

    return q


def test_produce_writes_pending_audit_artifact(tmp_path):
    facts = [{"uni_account": "u1", "display_label": "Total assets", "source_account": "Assets", "cell_id": "c1"}]
    lines = [{"pdf_label": "Total assets", "page_or_section": "BS p.3"}]
    art, unmatched = produce_nlm_order(
        "AAOI", "BS", facts, _stub_query(lines), str(tmp_path),
        source_doc="aaoi-10k.htm", accession="0001", period="FY2025",
        form="10-K", page_or_section="BS")
    assert art["status"] == "pending_audit" and art["signer"] is None
    assert art["lines"][0]["ordinal"] == 1
    assert art["lines"][0]["matched_cell_id"] == "c1"
    # file written + valid + still pending (read_audited_order returns {})
    written = json.loads((tmp_path / "AAOI_BS_nlm_order.json").read_text())
    assert validate_artifact(written) == []
    assert read_audited_order(written) == {}


def test_produce_reports_unmatched(tmp_path):
    facts = [{"uni_account": "u1", "display_label": "Total assets", "source_account": "Assets", "cell_id": "c1"}]
    lines = [{"pdf_label": "Goodwill", "page_or_section": "BS"}]  # no matching fact
    art, unmatched = produce_nlm_order("AAOI", "BS", facts, _stub_query(lines), str(tmp_path),
        source_doc="d", accession="a", period="FY2025", form="10-K", page_or_section="BS")
    assert art["lines"][0]["matched_cell_id"] is None
    assert unmatched["pdf_without_fact"] and unmatched["fact_without_pdf_line"]
