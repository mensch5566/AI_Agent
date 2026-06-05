import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from presentation_resolver import select_network

def test_is_network_selected_case_hyphen_insensitive():
    edges = [
        {"role_uri": "http://x/role/statement-consolidated-statements-of-operations", "child_qname": "us-gaap:Revenues", "order": 1.0, "period": "FY2025"},
        {"role_uri": "http://x/role/statement-note-income-taxes-reconciliation", "child_qname": "us-gaap:Foo", "order": 1.0, "period": "FY2025"},
    ]
    net = select_network(edges, "IS")
    assert net is not None and "operations" in net.lower()

def test_bs_returns_none_when_absent():   # AAOI case
    edges = [{"role_uri": "http://ao-inc.com/role/statement-consolidated-statements-of-operations", "child_qname": "us-gaap:Revenues", "order": 1.0, "period":"FY2025"}]
    assert select_network(edges, "BS") is None

from presentation_resolver import resolve_label_ordinal, AmbiguityError
import pytest

_LABELS = {"us-gaap:GrossProfit": [
    {"role":"http://www.xbrl.org/2003/role/terseLabel","text":"Gross margin"},
    {"role":"http://www.xbrl.org/2003/role/totalLabel","text":"Gross profit"}]}
_EDGES = [{"role_uri":"r/operations","child_qname":"us-gaap:GrossProfit","order":5.0,"preferred_label":"http://www.xbrl.org/2003/role/terseLabel"}]

def test_resolves_pdf_label_and_order():
    lbl, ordn = resolve_label_ordinal("GrossProfit", "r/operations", _EDGES, _LABELS)
    assert lbl == "Gross margin" and ordn == 5.0   # terseLabel = PDF wording

def test_ambiguous_local_name_fails_closed():
    edges = _EDGES + [{"role_uri":"r/operations","child_qname":"intc:GrossProfit","order":6.0,"preferred_label":"x"}]
    with pytest.raises(AmbiguityError):
        resolve_label_ordinal("GrossProfit", "r/operations", edges, _LABELS)

from presentation_resolver import resolve_via_uni, NeedsNlmOrder

def test_uni_canonical_present():
    edges = [{"role_uri":"r/cf","child_qname":"us-gaap:NetIncomeLoss","order":1.0,"preferred_label":"http://www.xbrl.org/2003/role/label"}]
    labels = {"us-gaap:NetIncomeLoss":[{"role":"http://www.xbrl.org/2003/role/label","text":"Net income"}]}
    lbl, ordn = resolve_via_uni("net_income", "CF", "r/cf", edges, labels)
    assert lbl == "Net income" and ordn == 1.0

def test_uni_canonical_miss_raises_needs_nlm():
    # D&A reported as components → combined canonical absent → must NOT render SUM(...)
    with pytest.raises(NeedsNlmOrder):
        resolve_via_uni("depreciation_and_amortization", "CF", "r/cashflow", [], {})

def test_uni_unknown_account_raises_needs_nlm():
    with pytest.raises(NeedsNlmOrder):
        resolve_via_uni("some_unmapped_account", "IS", "r/op", [], {})


# --------------------------------------------------------------------------- #
# T14 Issue2: accepted-face-network SET + multi-network resolution
# --------------------------------------------------------------------------- #

from presentation_resolver import (
    matching_face_networks,
    accepted_face_concepts,
    resolve_label_ordinal_any,
)

# A filer with BOTH a 10-K full IS network and a 10-Q condensed IS network.
_FULL = "http://x/role/statement-consolidated-statements-of-operations"
_COND = "http://x/role/statement-condensed-consolidated-statements-of-operations"

_TWO_NET_EDGES = [
    # Full network: has Revenues + GrossProfit
    {"role_uri": _FULL, "child_qname": "us-gaap:Revenues", "order": 1.0,
     "preferred_label": "http://www.xbrl.org/2003/role/label"},
    {"role_uri": _FULL, "child_qname": "us-gaap:GrossProfit", "order": 3.0,
     "preferred_label": "http://www.xbrl.org/2003/role/terseLabel"},
    # Condensed network: has Revenues + OperatingIncomeLoss
    {"role_uri": _COND, "child_qname": "us-gaap:Revenues", "order": 1.0,
     "preferred_label": "http://www.xbrl.org/2003/role/label"},
    {"role_uri": _COND, "child_qname": "us-gaap:OperatingIncomeLoss", "order": 5.0,
     "preferred_label": "http://www.xbrl.org/2003/role/label"},
]

_TWO_NET_LABELS = {
    "us-gaap:Revenues": [{"role": "http://www.xbrl.org/2003/role/label", "text": "Total revenue"}],
    "us-gaap:GrossProfit": [{"role": "http://www.xbrl.org/2003/role/terseLabel", "text": "Gross margin"}],
    "us-gaap:OperatingIncomeLoss": [{"role": "http://www.xbrl.org/2003/role/label", "text": "Operating income"}],
}


def test_matching_face_networks_returns_all_matching():
    nets = matching_face_networks(_TWO_NET_EDGES, "IS")
    assert set(nets) == {_FULL, _COND}


def test_matching_face_networks_excludes_parenthetical_note():
    edges = _TWO_NET_EDGES + [
        {"role_uri": "http://x/role/statement-operations-parenthetical",
         "child_qname": "us-gaap:Foo", "order": 1.0},
        {"role_uri": "http://x/role/note-income-operations-detail",
         "child_qname": "us-gaap:Bar", "order": 1.0},
    ]
    nets = matching_face_networks(edges, "IS")
    assert set(nets) == {_FULL, _COND}


def test_select_network_tie_break_prefers_non_condensed():
    # Both networks tie on facts-overlap (none given) and child count (2 each).
    # Tie-break MUST prefer the non-condensed (10-K full) role.
    net = select_network(_TWO_NET_EDGES, "IS")
    assert net == _FULL


def test_accepted_face_concepts_is_union_of_all_networks():
    accepted = accepted_face_concepts(_TWO_NET_EDGES, "IS")
    assert accepted == {"Revenues", "GrossProfit", "OperatingIncomeLoss"}


def test_accepted_face_concepts_empty_when_no_network():
    # AAOI BS/CF case: no matching network → empty set.
    assert accepted_face_concepts(_TWO_NET_EDGES, "BS") == set()


def test_resolve_any_concept_only_in_condensed():
    # OperatingIncomeLoss lives only in the condensed network. Primary = full.
    lbl, ordn = resolve_label_ordinal_any(
        "OperatingIncomeLoss", _TWO_NET_EDGES, _TWO_NET_LABELS, "IS")
    assert lbl == "Operating income" and ordn == 5.0


def test_resolve_any_concept_only_in_full_even_when_primary_condensed():
    # Make condensed win the primary selection by giving it more children, then
    # confirm a full-only concept still resolves via the multi-network walk.
    edges = _TWO_NET_EDGES + [
        {"role_uri": _COND, "child_qname": "us-gaap:Extra1", "order": 6.0},
        {"role_uri": _COND, "child_qname": "us-gaap:Extra2", "order": 7.0},
    ]
    assert select_network(edges, "IS") == _COND  # condensed now primary (size)
    lbl, ordn = resolve_label_ordinal_any("GrossProfit", edges, _TWO_NET_LABELS, "IS")
    assert lbl == "Gross margin" and ordn == 3.0


def test_resolve_any_ambiguity_in_one_network_skips_to_other():
    # GrossProfit ambiguous in the FULL network (two distinct qnames), but the
    # condensed network has a clean single GrossProfit → must resolve there.
    edges = [
        {"role_uri": _FULL, "child_qname": "us-gaap:GrossProfit", "order": 3.0,
         "preferred_label": "http://www.xbrl.org/2003/role/label"},
        {"role_uri": _FULL, "child_qname": "intc:GrossProfit", "order": 4.0,
         "preferred_label": "http://www.xbrl.org/2003/role/label"},
        {"role_uri": _COND, "child_qname": "us-gaap:GrossProfit", "order": 9.0,
         "preferred_label": "http://www.xbrl.org/2003/role/label"},
        # give full more children so it stays primary
        {"role_uri": _FULL, "child_qname": "us-gaap:Revenues", "order": 1.0},
        {"role_uri": _FULL, "child_qname": "us-gaap:Foo", "order": 2.0},
    ]
    labels = {"us-gaap:GrossProfit": [
        {"role": "http://www.xbrl.org/2003/role/label", "text": "Gross profit"}]}
    assert select_network(edges, "IS") == _FULL  # full is primary
    lbl, ordn = resolve_label_ordinal_any("GrossProfit", edges, labels, "IS")
    # Skipped the ambiguous full network, resolved from condensed (order 9.0).
    assert lbl == "Gross profit" and ordn == 9.0


def test_resolve_any_concept_in_no_network_returns_none():
    lbl, ordn = resolve_label_ordinal_any(
        "NotOnAnyFace", _TWO_NET_EDGES, _TWO_NET_LABELS, "IS")
    assert lbl is None and ordn is None
