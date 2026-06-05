"""Task 8 — adapter attaches display_label + ordinal + provenance (spec G4 prep).

Wires the 4-class classifier (Task 2) + presentation resolver (Tasks 3-5) +
audited NLM order reader (Task 6) into the upsert adapter. Per display-eligible
fact, resolve (display_label, ordinal, provenance); mark synthetic-SUM-of-
multiple-PDF-lines display_eligible=False (no statement row); metric-only rows
(derived_q2/q3/q4, ebitda, free_cash_flow) carry NO statement ordinal.
"""
import os
import sys

# Resolve THIS worktree's `_shared` package. Some sibling tests
# (test_xbrl_extract_preservation / test_8k_apply_audit_parse /
# test_extract_8k_preservation) import an external parse-skill module that
# inserts the MAIN repo's Tools/research-tools onto sys.path[0] and caches its
# `_shared` package in sys.modules. A plain `from _shared import …` would then
# resolve to that main-repo copy (which lacks attach_display_metadata). We
# prepend the worktree path AND evict any pre-cached `_shared*` modules so the
# import re-resolves from the worktree (the package uses relative imports, so we
# can't safely load a single file by synthetic name).
_WT_SHARED_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "Tools", "research-tools")
)
sys.path.insert(0, _WT_SHARED_ROOT)
for _m in [m for m in list(sys.modules) if m == "_shared" or m.startswith("_shared.")]:
    _cached = sys.modules[_m]
    _file = getattr(_cached, "__file__", "") or ""
    if not os.path.abspath(_file).startswith(_WT_SHARED_ROOT):
        del sys.modules[_m]

from _shared import sec_json_adapter as A  # noqa: E402
from _shared.sec_json_adapter import FactRow, attach_display_metadata  # noqa: E402


_STD = "http://www.xbrl.org/2003/role/label"
_TERSE = "http://www.xbrl.org/2003/role/terseLabel"
_TOTAL = "http://www.xbrl.org/2003/role/totalLabel"

# IS presentation network (role contains "operations" → matched by select_network).
_IS_NETWORK = "http://x/role/statement-consolidated-statements-of-operations"

# edges_pre for the IS network.
_IS_EDGES = [
    {"role_uri": _IS_NETWORK, "child_qname": "us-gaap:GrossProfit",
     "order": 3.0, "preferred_label": _TERSE, "period": "FY2025"},
    {"role_uri": _IS_NETWORK, "child_qname": "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxes",
     "order": 7.0, "preferred_label": _STD, "period": "FY2025"},
    {"role_uri": _IS_NETWORK, "child_qname": "us-gaap:WeightedAverageNumberOfSharesOutstandingBasic",
     "order": 10.0, "preferred_label": _STD, "period": "FY2025"},
]

_IS_LABELS = {
    "us-gaap:GrossProfit": [
        {"role": _TERSE, "text": "Gross margin"},
        {"role": _TOTAL, "text": "Gross profit"},
    ],
    "us-gaap:WeightedAverageNumberOfSharesOutstandingBasic": [
        {"role": _STD, "text": "Basic shares outstanding"},
    ],
    # NOTE: no label entry for IncomeLossFromContinuingOperations... — the
    # preserved_pdf_label fact uses source_account verbatim, not this lookup.
}


def _fact(uni_account, source_account, *, statement="IS", period="FY2025",
          period_kind="annual", version="GAAP", cell_id=None):
    return FactRow(
        cell_id=cell_id or f"cid::{uni_account}::{period}",
        ticker="TEST",
        period=period,
        period_end="2025-12-31",
        period_kind=period_kind,
        statement=statement,
        version=version,
        uni_account=uni_account,
        source_account=source_account,
        xbrl_tag=None,
        value=1.0,
        weight=1,
        unit="USD_thousands",
        status="SOURCE_OF_TRUTH",
        ordinal=None,
        long_tail_metadata=None,
        provenance={"source_filing": "10-K", "accession_number": "0001-25-1"},
    )


def _run(facts, audited_orders=None):
    """Resolve display metadata for an IS batch."""
    attach_display_metadata(
        facts,
        statement="IS",
        edges=_IS_EDGES,
        labels=_IS_LABELS,
        network_role=_IS_NETWORK,
        audited_orders=audited_orders or {},
    )


# --------------------------------------------------------------------------- #
# tag_like
# --------------------------------------------------------------------------- #

def test_tag_like_resolves_label_ordinal_xbrl():
    f = _fact("gross_profit", "GrossProfit")
    _run([f])
    assert f.display_label == "Gross margin"   # terseLabel = PDF wording
    assert f.ordinal == 3.0
    assert f.display_eligible is True
    assert f.provenance["ordinal_source"] == "xbrl"
    assert f.provenance["ordinal_source_doc"] == "10-K"
    assert f.provenance["ordinal_source_period"] == "FY2025"
    assert f.provenance["ordinal_match_method"] == "xbrl_presentation"


# --------------------------------------------------------------------------- #
# preserved_pdf_label
# --------------------------------------------------------------------------- #

def test_preserved_pdf_label_uses_source_account_verbatim():
    f = _fact("income_before_income_taxes", "Income before income taxes",
              cell_id="cid::ibt")
    # Provide an audited NLM ordinal for it (preserved labels never use the
    # namespace-strip resolver for order).
    _run([f], audited_orders={
        "IS": {
            "cell_id_to_ordinal": {"cid::ibt": 7},
            "source_doc": "TEST_10K.pdf",
            "period": "FY2025",
            "artifact_hash": "deadbeef",
        }
    })
    assert f.display_label == "Income before income taxes"
    assert f.display_eligible is True
    assert f.ordinal == 7
    assert f.provenance["ordinal_source"] == "nlm"
    assert f.provenance["ordinal_artifact_hash"] == "deadbeef"


# --------------------------------------------------------------------------- #
# synthetic SUM-of-multiple → display_eligible False, no row
# --------------------------------------------------------------------------- #

def test_synthetic_sum_of_multiple_is_display_ineligible():
    f = _fact("selling_general_administrative", "SUM(S&M+G&A)")
    _run([f])
    assert f.display_eligible is False
    assert f.ordinal is None
    assert f.display_label is None
    # No ordinal provenance written for a non-display row.
    assert "ordinal_source" not in f.provenance


def test_synthetic_da_components_is_display_ineligible():
    f = _fact("depreciation_and_amortization", "SUM(D&A components)",
              statement="CF")
    attach_display_metadata(
        [f], statement="CF", edges=[], labels={}, network_role=None,
        audited_orders={},
    )
    assert f.display_eligible is False
    assert f.ordinal is None


# --------------------------------------------------------------------------- #
# null source → resolve via uni → canonical
# --------------------------------------------------------------------------- #

def test_null_source_resolved_via_uni_canonical():
    f = _fact("shares_basic_millions", None)
    _run([f])
    assert f.display_label == "Basic shares outstanding"
    assert f.ordinal == 10.0
    assert f.display_eligible is True
    assert f.provenance["ordinal_source"] == "xbrl"


def test_null_source_canonical_miss_falls_to_nlm_then_none():
    # net_income → NetIncomeLoss, not present in this IS network/labels → NeedsNlmOrder.
    f = _fact("net_income", None, statement="CF", cell_id="cid::ni")
    attach_display_metadata(
        [f], statement="CF", edges=[], labels={}, network_role=None,
        audited_orders={
            "CF": {
                "cell_id_to_ordinal": {"cid::ni": 1},
                "source_doc": "TEST_10K.pdf",
                "period": "FY2025",
                "artifact_hash": "cafe1234",
            }
        },
    )
    assert f.ordinal == 1
    assert f.provenance["ordinal_source"] == "nlm"
    assert f.provenance["ordinal_artifact_hash"] == "cafe1234"


def test_null_source_canonical_miss_no_nlm_leaves_ordinal_none():
    f = _fact("net_income", None, statement="CF", cell_id="cid::ni2")
    attach_display_metadata(
        [f], statement="CF", edges=[], labels={}, network_role=None,
        audited_orders={},
    )
    # Coverage gate (next task) will catch this — here it just stays unresolved.
    assert f.ordinal is None
    assert "ordinal_source" not in f.provenance
    # Still display-eligible (it IS a PDF row, just unordered yet).
    assert f.display_eligible is True


# --------------------------------------------------------------------------- #
# metric-only rows (derived_q2/q3/q4 + ebitda) carry NO statement ordinal
# --------------------------------------------------------------------------- #

def _metric_row(uni_account, period_kind):
    """Shape mirrors a sec_financial_metrics row dict (NOT a FactRow)."""
    return {
        "uni_account": uni_account,
        "period_kind": period_kind,
        "statement": "IS",
        "period": "FY2025",
        "value": 1.0,
    }


def test_derived_single_quarter_and_ebitda_metrics_carry_no_statement_ordinal():
    rows = [
        _metric_row("operating_income", "derived_q2"),
        _metric_row("operating_income", "derived_q3"),
        _metric_row("operating_income", "derived_q4"),
        _metric_row("ebitda", "quarter_duration"),
    ]
    for r in rows:
        # Adapter must not assign a statement display ordinal to a metric row.
        assert A.metric_row_carries_statement_ordinal(r) is False


def test_all_three_derived_quarters_behave_identically():
    # Codex finding: do not test only derived_q4. Assert Q2/Q3/Q4 identical.
    results = {
        pk: A.metric_row_carries_statement_ordinal(_metric_row("operating_income", pk))
        for pk in ("derived_q2", "derived_q3", "derived_q4")
    }
    assert results == {"derived_q2": False, "derived_q3": False, "derived_q4": False}
    assert len(set(results.values())) == 1  # all identical


# --------------------------------------------------------------------------- #
# T14 Issue2: narrow note-level exclusion (tag_like NOT in accepted face set)
# --------------------------------------------------------------------------- #
#
# The accepted face set for _IS_NETWORK = the 3 concepts in _IS_EDGES:
#   GrossProfit, IncomeLossFromContinuingOperationsBeforeIncomeTaxes,
#   WeightedAverageNumberOfSharesOutstandingBasic
_ACCEPTED = {
    "GrossProfit",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxes",
    "WeightedAverageNumberOfSharesOutstandingBasic",
}


def _run_accepted(facts, accepted, audited_orders=None):
    attach_display_metadata(
        facts,
        statement="IS",
        edges=_IS_EDGES,
        labels=_IS_LABELS,
        network_role=_IS_NETWORK,
        accepted_concepts=accepted,
        audited_orders=audited_orders or {},
    )


def test_tag_like_not_in_accepted_set_excluded_with_reason():
    # InterestExpenseNonoperating is a note-level sub-component — concrete XBRL
    # concept (tag_like) but NOT on the face network. Auto-excluded.
    f = _fact("interest_expense", "InterestExpenseNonoperating")
    _run_accepted([f], _ACCEPTED)
    assert f.display_eligible is False
    assert f.display_label is None
    assert f.ordinal is None
    assert f.provenance["display_exclusion_reason"] == "note_level_not_in_face_network"
    # Existing provenance keys preserved.
    assert f.provenance["source_filing"] == "10-K"


def test_tag_like_in_accepted_but_unresolved_stays_eligible():
    # Concept IS on the face network (in accepted set) but the labels/edges did
    # not yield an ordinal here → must NOT be hidden; gate must still block.
    f = _fact("income_before_income_taxes",
              "IncomeLossFromContinuingOperationsBeforeIncomeTaxes")
    # Remove the matching edge ordinal by using a statement whose network has no
    # ordinal: simplest is to give an accepted concept that resolves to None.
    # IncomeLossFromContinuingOperations... IS an edge (order 7.0) so it WOULD
    # resolve. Use a fresh accepted-only concept with no edge instead.
    f2 = _fact("some_face_line", "SomeFaceLineConcept")
    accepted = _ACCEPTED | {"SomeFaceLineConcept"}
    _run_accepted([f2], accepted)
    assert f2.display_eligible is True               # NOT auto-hidden
    assert f2.ordinal is None                        # gate will block
    assert "display_exclusion_reason" not in f2.provenance


def test_preserved_pdf_label_unresolved_not_auto_hidden():
    # preserved_pdf_label (has spaces) must NEVER be auto-excluded — needs NLM.
    f = _fact("interest_and_other_net", "Interest and other, net")
    _run_accepted([f], _ACCEPTED)
    assert f.display_eligible is True
    assert f.ordinal is None
    assert "display_exclusion_reason" not in f.provenance
    # preserved label falls back to the source_account verbatim.
    assert f.display_label == "Interest and other, net"


def test_null_source_unresolved_not_auto_hidden():
    # null source resolves via uni→canonical; canonical absent → must NOT hide.
    f = _fact("net_income", None, cell_id="cid::ni3")
    _run_accepted([f], _ACCEPTED)
    assert f.display_eligible is True
    assert "display_exclusion_reason" not in f.provenance


def test_accepted_empty_no_face_network_tag_like_not_hidden():
    # No face network at all (accepted empty) → tag_like unresolved must NOT be
    # auto-hidden (fail-loud; gate blocks). Mirrors AAOI BS/CF with no network.
    f = _fact("inventory", "InventoryNet", statement="BS", period_kind="instant")
    attach_display_metadata(
        [f], statement="BS", edges=[], labels={}, network_role=None,
        accepted_concepts=set(), audited_orders={},
    )
    assert f.display_eligible is True
    assert f.ordinal is None
    assert "display_exclusion_reason" not in f.provenance


def test_tag_like_in_accepted_and_resolves_still_eligible():
    # Sanity: a normal face concept still resolves with ordinal + stays eligible.
    f = _fact("gross_profit", "GrossProfit")
    _run_accepted([f], _ACCEPTED)
    assert f.display_eligible is True
    assert f.display_label == "Gross margin"
    assert f.ordinal == 3.0
    assert "display_exclusion_reason" not in f.provenance


def test_synthetic_sum_unaffected_by_accepted_set():
    # G7 synthetic SUM-of-multiple path unchanged even with accepted_concepts.
    f = _fact("selling_general_administrative", "SUM(S&M+G&A)")
    _run_accepted([f], _ACCEPTED)
    assert f.display_eligible is False
    assert f.ordinal is None
    # G7 path, NOT the note-level path.
    assert "display_exclusion_reason" not in f.provenance


# --------------------------------------------------------------------------- #
# T14 item1: preserved_pdf_label CORE line borrows ordinal via uni→canonical
# (LITE income_before_taxes: stored as PDF text, canonical concept ON the face
# network → resolve the face ordinal WITHOUT NLM, keep the period-exact label).
# --------------------------------------------------------------------------- #

_IBT_CONCEPT = "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"

# IS network where income_before_taxes's canonical concept IS a face edge (order
# 7.0) — mirrors LITE. No labels entry for it (the preserved fact owns its label).
_IBT_NETWORK = "http://lite/role/statement-condensed-consolidated-statements-of-operations"
_IBT_EDGES = [
    {"role_uri": _IBT_NETWORK, "child_qname": "us-gaap:Revenues", "order": 1.0,
     "preferred_label": _STD, "period": "FY2025"},
    {"role_uri": _IBT_NETWORK, "child_qname": f"us-gaap:{_IBT_CONCEPT}",
     "order": 7.0, "preferred_label": _STD, "period": "FY2025"},
]
_IBT_LABELS = {
    "us-gaap:Revenues": [{"role": _STD, "text": "Net revenue"}],
}


def _run_ibt(facts, accepted=None, audited_orders=None):
    attach_display_metadata(
        facts, statement="IS", edges=_IBT_EDGES, labels=_IBT_LABELS,
        network_role=_IBT_NETWORK, accepted_concepts=accepted,
        audited_orders=audited_orders or {},
    )


def test_preserved_pdf_label_core_borrows_ordinal_via_uni_canonical():
    # LITE: "Income before income taxes" / "Loss before income taxes" stored as
    # PDF text; uni_account=income_before_taxes maps to the face concept.
    for pdf_text in ("Income before income taxes", "Loss before income taxes",
                     "Income (loss) before income taxes"):
        f = _fact("income_before_taxes", pdf_text, cell_id=f"cid::{pdf_text}")
        _run_ibt([f])
        # Period-exact PDF wording preserved as the display label.
        assert f.display_label == pdf_text
        # Ordinal BORROWED from the canonical face concept — no NLM needed.
        assert f.ordinal == 7.0
        assert f.display_eligible is True
        assert f.provenance["ordinal_source"] == "xbrl"
        # Distinct match method so a human can audit the borrow.
        assert f.provenance["ordinal_match_method"] == "xbrl_presentation_via_uni"


def test_preserved_pdf_label_core_borrow_survives_note_level_pass():
    # Even with an accepted-set provided, the borrow resolves the ordinal first,
    # so the note-level exclusion (tag_like-only anyway) never fires.
    f = _fact("income_before_taxes", "Income before income taxes", cell_id="cid::ibt2")
    _run_ibt([f], accepted={"Revenues", _IBT_CONCEPT})
    assert f.ordinal == 7.0
    assert f.display_eligible is True
    assert "display_exclusion_reason" not in f.provenance


def test_preserved_pdf_label_longtail_unmapped_uni_still_needs_nlm():
    # SNDK safety: a preserved_pdf_label long-tail item whose uni_account is NOT
    # in CANONICAL_CONCEPT gets NO borrow → stays eligible, ordinal None (→ NLM),
    # never auto-hidden.
    f = _fact("nonoperating_long_tail", "Other charges, net", cell_id="cid::lt")
    _run_ibt([f], accepted={"Revenues", _IBT_CONCEPT})
    assert f.display_label == "Other charges, net"
    assert f.ordinal is None
    assert f.display_eligible is True
    assert "display_exclusion_reason" not in f.provenance


def test_preserved_pdf_label_core_falls_to_nlm_when_concept_absent():
    # If the canonical concept is NOT on this filing's face network, the borrow
    # returns nothing → fall to the audited NLM ordinal (unchanged path).
    f = _fact("income_before_taxes", "Income before income taxes", cell_id="cid::ibt3")
    attach_display_metadata(
        [f], statement="IS", edges=[], labels={}, network_role=None,
        audited_orders={"IS": {"cell_id_to_ordinal": {"cid::ibt3": 9},
                               "source_doc": "L_10K.pdf", "period": "FY2025",
                               "artifact_hash": "abc"}},
    )
    assert f.ordinal == 9
    assert f.provenance["ordinal_source"] == "nlm"
    assert f.display_label == "Income before income taxes"
