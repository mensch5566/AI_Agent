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

from presentation_resolver import resolve_label_ordinal, AmbiguityError, _TERSE_LABEL
import pytest

_LABELS = {"us-gaap:GrossProfit": [
    {"role":"http://www.xbrl.org/2003/role/terseLabel","text":"Gross margin"},
    {"role":"http://www.xbrl.org/2003/role/totalLabel","text":"Gross profit"}]}
_EDGES = [{"role_uri":"r/operations","child_qname":"us-gaap:GrossProfit","order":5.0,"preferred_label":"http://www.xbrl.org/2003/role/terseLabel"}]

def test_resolves_pdf_label_and_order():
    lbl, ordn, neg = resolve_label_ordinal("GrossProfit", "r/operations", _EDGES, _LABELS)
    assert lbl == "Gross margin" and ordn == 5.0   # terseLabel = PDF wording
    assert neg is False                            # terseLabel is NOT a negated role

def test_ambiguous_local_name_fails_closed():
    edges = _EDGES + [{"role_uri":"r/operations","child_qname":"intc:GrossProfit","order":6.0,"preferred_label":"x"}]
    with pytest.raises(AmbiguityError):
        resolve_label_ordinal("GrossProfit", "r/operations", edges, _LABELS)


# --------------------------------------------------------------------------- #
# PDF-faithful sign: display_negated from the matched arc's preferred_label.
# True iff _norm(preferred).startswith("negated"). TRUE negation, never -abs.
# --------------------------------------------------------------------------- #

_NEG_TERSE = "http://www.xbrl.org/2009/role/negatedTerseLabel"
_NEG_LABEL = "http://www.xbrl.org/2009/role/negatedLabel"


def test_negated_terse_label_sets_negated_true():
    # MU BS TreasuryStockCommonValue: arc preferred_label = negatedTerseLabel.
    edges = [{"role_uri": "r/bs", "child_qname": "us-gaap:TreasuryStockCommonValue",
              "order": 4.0, "preferred_label": _NEG_TERSE}]
    labels = {"us-gaap:TreasuryStockCommonValue": [
        {"role": _NEG_TERSE, "text": "Treasury stock"}]}
    lbl, ordn, neg = resolve_label_ordinal(
        "TreasuryStockCommonValue", "r/bs", edges, labels)
    assert neg is True
    assert lbl == "Treasury stock" and ordn == 4.0


def test_negated_label_role_sets_negated_true():
    # MU IS IncomeTaxExpenseBenefit / InterestExpenseNonoperating: negatedLabel.
    edges = [{"role_uri": "r/is", "child_qname": "us-gaap:IncomeTaxExpenseBenefit",
              "order": 8.0, "preferred_label": _NEG_LABEL}]
    _, _, neg = resolve_label_ordinal(
        "IncomeTaxExpenseBenefit", "r/is", edges, {})
    assert neg is True


def test_non_negated_terse_label_sets_negated_false():
    # CostOfGoodsAndServicesSold with a plain terseLabel → NOT negated.
    edges = [{"role_uri": "r/is", "child_qname": "us-gaap:CostOfGoodsAndServicesSold",
              "order": 2.0, "preferred_label": _TERSE_LABEL}]
    _, _, neg = resolve_label_ordinal(
        "CostOfGoodsAndServicesSold", "r/is", edges, {})
    assert neg is False


def test_no_match_returns_negated_false():
    _, ordn, neg = resolve_label_ordinal("NotPresent", "r/is", _EDGES, _LABELS)
    assert ordn is None and neg is False


def test_missing_preferred_label_negated_false():
    edges = [{"role_uri": "r/is", "child_qname": "us-gaap:Revenues", "order": 1.0}]
    _, _, neg = resolve_label_ordinal("Revenues", "r/is", edges, {})
    assert neg is False

from presentation_resolver import resolve_via_uni, NeedsNlmOrder

def test_uni_canonical_present():
    edges = [{"role_uri":"r/cf","child_qname":"us-gaap:NetIncomeLoss","order":1.0,"preferred_label":"http://www.xbrl.org/2003/role/label"}]
    labels = {"us-gaap:NetIncomeLoss":[{"role":"http://www.xbrl.org/2003/role/label","text":"Net income"}]}
    lbl, ordn, neg = resolve_via_uni("net_income", "CF", "r/cf", edges, labels)
    assert lbl == "Net income" and ordn == 1.0 and neg is False

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
    lbl, ordn, neg = resolve_label_ordinal_any(
        "OperatingIncomeLoss", _TWO_NET_EDGES, _TWO_NET_LABELS, "IS")
    assert lbl == "Operating income" and ordn == 5.0 and neg is False


def test_resolve_any_concept_only_in_full_even_when_primary_condensed():
    # Make condensed win the primary selection by giving it more children, then
    # confirm a full-only concept still resolves via the multi-network walk.
    edges = _TWO_NET_EDGES + [
        {"role_uri": _COND, "child_qname": "us-gaap:Extra1", "order": 6.0},
        {"role_uri": _COND, "child_qname": "us-gaap:Extra2", "order": 7.0},
    ]
    assert select_network(edges, "IS") == _COND  # condensed now primary (size)
    lbl, ordn, neg = resolve_label_ordinal_any("GrossProfit", edges, _TWO_NET_LABELS, "IS")
    assert lbl == "Gross margin" and ordn == 3.0 and neg is False


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
    lbl, ordn, neg = resolve_label_ordinal_any("GrossProfit", edges, labels, "IS")
    # Skipped the ambiguous full network, resolved from condensed (order 9.0).
    assert lbl == "Gross profit" and ordn == 9.0 and neg is False


def test_resolve_any_concept_in_no_network_returns_none():
    lbl, ordn, neg = resolve_label_ordinal_any(
        "NotOnAnyFace", _TWO_NET_EDGES, _TWO_NET_LABELS, "IS")
    assert lbl is None and ordn is None and neg is False


# --------------------------------------------------------------------------- #
# T14 item1: resolve_via_uni_any — multi-network uni→canonical ORDINAL borrow
# (for the preserved_pdf_label fallback; laxer than resolve_via_uni — no labels
# guard, since the caller owns its own PDF-text display label).
# --------------------------------------------------------------------------- #

from presentation_resolver import resolve_via_uni_any, CANONICAL_CONCEPT

# LITE's real canonical concept for income_before_taxes (preserved_pdf_label
# periods store PDF text like "Income before income taxes" instead of this tag).
_IBT = "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"


def test_canonical_concept_has_income_before_taxes():
    assert CANONICAL_CONCEPT.get("income_before_taxes") == _IBT


def test_resolve_via_uni_any_maps_and_borrows_ordinal_across_networks():
    # Canonical concept only present in the condensed network → must still
    # resolve via the multi-network walk. No labels entry for it → label None,
    # but the ORDINAL comes back (the borrow target).
    edges = [
        {"role_uri": _COND, "child_qname": f"us-gaap:{_IBT}", "order": 8.0,
         "preferred_label": "http://www.xbrl.org/2003/role/label"},
        {"role_uri": _COND, "child_qname": "us-gaap:Revenues", "order": 1.0},
    ]
    lbl, ordn, neg = resolve_via_uni_any("income_before_taxes", edges, {}, "IS")
    assert ordn == 8.0   # ordinal borrowed even with no labels entry
    assert neg is False  # plain label role on the canonical edge


def test_resolve_via_uni_any_unknown_uni_raises_needs_nlm():
    # A long-tail bucket has no canonical mapping → NeedsNlmOrder (caller routes
    # to NLM, unchanged). This is the SNDK nonoperating_long_tail safety case.
    with pytest.raises(NeedsNlmOrder):
        resolve_via_uni_any("nonoperating_long_tail", _TWO_NET_EDGES, {}, "IS")


def test_resolve_via_uni_any_canonical_not_on_face_returns_none():
    # uni maps to a canonical concept, but that concept is on NO face network →
    # (None, None) (never invents an order).
    lbl, ordn, neg = resolve_via_uni_any("income_before_taxes", _TWO_NET_EDGES, {}, "IS")
    assert lbl is None and ordn is None and neg is False


# --------------------------------------------------------------------------- #
# T15 fix: compute_global_ordinals — pre-order DFS over the MERGED presentation
# tree of ALL face networks (XBRL `order` is sibling-relative; this flattens to a
# global top-to-bottom statement position).
# --------------------------------------------------------------------------- #

from presentation_resolver import compute_global_ordinals

_GROOT = "us-gaap:IncomeStatementAbstract"
_GOPEX = "us-gaap:OperatingExpensesAbstract"
# Network A (condensed, one period): root → Revenue, COGS, GrossProfit,
# OpExAbstract → [R&D, SG&A], OperatingIncome, NonOp, IncomeTax, NetIncome.
_NET_A = "http://x/role/statement-condensed-consolidated-statements-of-operations"
# Network B (full, another period): SAME spine but adds IncomeBeforeTaxes between
# NonOp and IncomeTax (and lacks Revenue) — the cross-period union case.
_NET_B = "http://x/role/statement-consolidated-statements-of-operations"

def _arc(role, parent, child, order):
    return {"role_uri": role, "parent_qname": parent, "child_qname": child,
            "order": order, "period": "FY2025"}

_GLOBAL_EDGES = [
    _arc(_NET_A, _GROOT, "us-gaap:Revenues", 1.0),
    _arc(_NET_A, _GROOT, "us-gaap:CostOfGoodsAndServicesSold", 2.0),
    _arc(_NET_A, _GROOT, "us-gaap:GrossProfit", 3.0),
    _arc(_NET_A, _GROOT, _GOPEX, 4.0),
    _arc(_NET_A, _GOPEX, "us-gaap:ResearchAndDevelopmentExpense", 1.0),
    _arc(_NET_A, _GOPEX, "us-gaap:SellingGeneralAndAdministrativeExpense", 2.0),
    _arc(_NET_A, _GROOT, "us-gaap:OperatingIncomeLoss", 5.0),
    _arc(_NET_A, _GROOT, "us-gaap:NonoperatingIncomeExpense", 6.0),
    _arc(_NET_A, _GROOT, "us-gaap:IncomeTaxExpenseBenefit", 8.0),
    _arc(_NET_A, _GROOT, "us-gaap:NetIncomeLoss", 9.0),
    # Network B: income_before_taxes at order 7 (between NonOp=6 and Tax=8).
    _arc(_NET_B, _GROOT, "us-gaap:NonoperatingIncomeExpense", 6.0),
    _arc(_NET_B, _GROOT,
         "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest", 7.0),
    _arc(_NET_B, _GROOT, "us-gaap:IncomeTaxExpenseBenefit", 8.0),
    # a parenthetical/note network must be ignored
    _arc("http://x/role/statement-operations-parenthetical", _GROOT, "us-gaap:Foo", 1.0),
]


def test_global_ordinals_preorder_dfs_flattens_tree():
    g = compute_global_ordinals(_GLOBAL_EDGES, "IS")
    # Pre-order: Revenue, COGS, GrossProfit, [R&D, SG&A under OpEx], OpInc,
    # NonOp, IncomeBeforeTaxes (from net B), IncomeTax, NetIncome.
    order = ["Revenues", "CostOfGoodsAndServicesSold", "GrossProfit",
             "ResearchAndDevelopmentExpense", "SellingGeneralAndAdministrativeExpense",
             "OperatingIncomeLoss", "NonoperatingIncomeExpense",
             "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
             "IncomeTaxExpenseBenefit", "NetIncomeLoss"]
    seq = [g[c] for c in order]
    assert seq == sorted(seq), f"not monotonically increasing: {list(zip(order, seq))}"
    # R&D/SG&A (children of OpEx) sit between GrossProfit and OperatingIncome.
    assert g["GrossProfit"] < g["ResearchAndDevelopmentExpense"] < g["OperatingIncomeLoss"]


def test_global_ordinals_cross_network_concept_slots_correctly():
    # income_before_taxes exists ONLY in network B but must land between NonOp
    # and IncomeTax in the MERGED order (the whole point of the union merge).
    g = compute_global_ordinals(_GLOBAL_EDGES, "IS")
    ibt = "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"
    assert g["NonoperatingIncomeExpense"] < g[ibt] < g["IncomeTaxExpenseBenefit"]


def test_global_ordinals_excludes_parenthetical_and_absent():
    g = compute_global_ordinals(_GLOBAL_EDGES, "IS")
    assert "Foo" not in g          # parenthetical network ignored
    assert "NotAConcept" not in g  # absent concept → not in map


def test_global_ordinals_empty_when_no_face_network():
    # BS keyword matches nothing here → empty map (AAOI-style; caller → NLM).
    assert compute_global_ordinals(_GLOBAL_EDGES, "BS") == {}
