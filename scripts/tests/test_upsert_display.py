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
