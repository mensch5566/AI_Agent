"""Tests for resolve_via_label_text — the narrow, fail-closed PDF-label→face-concept
ordinal fallback (SNDK legacy AGENT_CLASSIFIED rows with no concept link).
Spec: docs/superpowers/specs/2026-06-09-sndk-label-text-fallback-design.md
Returns a 4-tuple (concept_local, ordinal, negated, network_role).
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from presentation_resolver import resolve_via_label_text, compute_global_ordinals

_IS_ROLE = "http://sandisk.com/role/statement-consolidated-statements-of-operations"
_TERSE = "http://www.xbrl.org/2003/role/terseLabel"
_NEG_TERSE = "http://www.xbrl.org/2009/role/negatedTerseLabel"
_STD = "http://www.xbrl.org/2003/role/label"
_DOC = "http://www.xbrl.org/2003/role/documentation"

_EDGES = [
    {"role_uri": _IS_ROLE, "child_qname": "us-gaap:GainLossOnSaleOfBusiness",
     "order": 6.0, "preferred_label": _NEG_TERSE, "period": "FY2025"},
    {"role_uri": _IS_ROLE, "child_qname": "sndk:BusinessSeparationCosts",
     "order": 4.0, "preferred_label": _TERSE, "period": "FY2025"},
    {"role_uri": _IS_ROLE, "child_qname": "us-gaap:Revenues",
     "order": 1.0, "preferred_label": _TERSE, "period": "FY2025"},
]
_LABELS = {
    "us-gaap:GainLossOnSaleOfBusiness": [
        {"role": _TERSE, "text": "Gain on business divestiture"},
        {"role": _NEG_TERSE, "text": "(Gain) loss on business divestiture"},
        {"role": _STD, "text": "Gain (Loss) on Disposition of Business"},
    ],
    "sndk:BusinessSeparationCosts": [
        {"role": _TERSE, "text": "Business separation costs"},
        {"role": _STD, "text": "Business Separation Costs"},
    ],
    "us-gaap:Revenues": [{"role": _TERSE, "text": "Revenue, net"}],
}


def test_unique_terse_hit_extension_concept():
    concept, ordn, neg, role = resolve_via_label_text(
        "Business separation costs", _EDGES, _LABELS, "IS")
    assert concept == "sndk:BusinessSeparationCosts"   # FULL qname (identity)
    assert ordn == 4.0
    assert neg is False
    assert role == _IS_ROLE


def test_gain_variant_hits_gainloss_concept():
    concept, ordn, neg, role = resolve_via_label_text(
        "Gain on business divestiture", _EDGES, _LABELS, "IS")
    assert concept == "us-gaap:GainLossOnSaleOfBusiness"
    assert ordn == 6.0
    assert neg is True   # face edge preferred_label = negatedTerseLabel
    assert role == _IS_ROLE


def test_loss_variant_paren_strip_same_concept():
    # "(Gain) loss on business divestiture" via the narrow leading-paren strip.
    concept, ordn, neg, _ = resolve_via_label_text(
        "Loss on business divestiture", _EDGES, _LABELS, "IS")
    assert concept == "us-gaap:GainLossOnSaleOfBusiness"
    assert ordn == 6.0
    assert neg is True


def test_no_match_returns_none():
    assert resolve_via_label_text(
        "Some line not on the face", _EDGES, _LABELS, "IS") == (None, None, None, None)


def test_empty_source_returns_none():
    assert resolve_via_label_text("", _EDGES, _LABELS, "IS") == (None, None, None, None)
    assert resolve_via_label_text(None, _EDGES, _LABELS, "IS") == (None, None, None, None)


def test_ambiguous_two_concepts_same_label_fail_closed():
    edges = _EDGES + [
        {"role_uri": _IS_ROLE, "child_qname": "sndk:OtherSeparationCosts",
         "order": 5.0, "preferred_label": _TERSE, "period": "FY2025"},
    ]
    labels = dict(_LABELS)
    labels["sndk:OtherSeparationCosts"] = [
        {"role": _TERSE, "text": "Business separation costs"}]  # collides
    assert resolve_via_label_text(
        "Business separation costs", edges, labels, "IS") == (None, None, None, None)


def test_note_network_concept_not_used():
    note_role = "http://sandisk.com/role/statement-note-income-taxes-reconciliation"
    edges = [
        {"role_uri": note_role, "child_qname": "sndk:BusinessSeparationCosts",
         "order": 4.0, "preferred_label": _TERSE, "period": "FY2025"},
    ]
    assert resolve_via_label_text(
        "Business separation costs", edges, _LABELS, "IS") == (None, None, None, None)


def test_no_face_network_returns_none():
    assert resolve_via_label_text(
        "Business separation costs", [], _LABELS, "IS") == (None, None, None, None)


def test_punctuation_and_case_normalized():
    concept, ordn, _, _ = resolve_via_label_text(
        "  BUSINESS SEPARATION COSTS.  ", _EDGES, _LABELS, "IS")
    assert concept == "sndk:BusinessSeparationCosts" and ordn == 4.0


def test_periodend_preferred_label_not_matched():
    # round2 #3: a periodEndLabel preferred_label must NOT be admitted into
    # label-text matching even though it is the edge's preferred_label.
    _PERIOD_END = "http://www.xbrl.org/2003/role/periodEndLabel"
    edges = [
        {"role_uri": _IS_ROLE, "child_qname": "sndk:OddCashLine",
         "order": 2.0, "preferred_label": _PERIOD_END, "period": "FY2025"},
    ]
    labels = {
        "sndk:OddCashLine": [
            {"role": _PERIOD_END, "text": "Mystery line at end of period"}],
    }
    assert resolve_via_label_text(
        "Mystery line at end of period", edges, labels, "IS") == (None, None, None, None)


# --------------------------------------------------------------------------- #
# Codex round1 #1/#4: FULL-QNAME identity. A same-local concept in another face
# network (different namespace) must NOT be substituted for the one whose label
# actually matched.
# --------------------------------------------------------------------------- #

_IS_ROLE_B = "http://sandisk.com/role/statement-condensed-consolidated-statements-of-income"


def test_full_qname_identity_no_cross_namespace_substitution():
    # Two face networks, same LOCAL name 'BusinessSeparationCosts' under different
    # namespaces. Only the sndk: one's label matches "Business separation costs".
    # The us-gaap: homonym (order 9, label "Reorganization items") must never be
    # returned. Old code degraded to the bare local and could grab the wrong one.
    edges = [
        {"role_uri": _IS_ROLE, "child_qname": "sndk:BusinessSeparationCosts",
         "order": 4.0, "preferred_label": _TERSE, "period": "FY2025"},
        {"role_uri": _IS_ROLE_B, "child_qname": "us-gaap:BusinessSeparationCosts",
         "order": 9.0, "preferred_label": _TERSE, "period": "Q1_FY2026"},
    ]
    labels = {
        "sndk:BusinessSeparationCosts": [
            {"role": _TERSE, "text": "Business separation costs"}],
        "us-gaap:BusinessSeparationCosts": [
            {"role": _TERSE, "text": "Reorganization items"}],   # does NOT match
    }
    concept, ordn, neg, role = resolve_via_label_text(
        "Business separation costs", edges, labels, "IS")
    assert concept == "sndk:BusinessSeparationCosts"   # exact qname, not us-gaap homonym
    assert ordn == 4.0          # sndk: edge, NOT the us-gaap homonym's 9.0
    assert role == _IS_ROLE


def test_two_namespaces_both_match_fail_closed():
    # If BOTH homonyms' labels match → 2 distinct qnames → fail-closed.
    edges = [
        {"role_uri": _IS_ROLE, "child_qname": "sndk:BusinessSeparationCosts",
         "order": 4.0, "preferred_label": _TERSE},
        {"role_uri": _IS_ROLE_B, "child_qname": "us-gaap:BusinessSeparationCosts",
         "order": 9.0, "preferred_label": _TERSE},
    ]
    labels = {
        "sndk:BusinessSeparationCosts": [{"role": _TERSE, "text": "Business separation costs"}],
        "us-gaap:BusinessSeparationCosts": [{"role": _TERSE, "text": "Business separation costs"}],
    }
    assert resolve_via_label_text(
        "Business separation costs", edges, labels, "IS") == (None, None, None, None)


# --------------------------------------------------------------------------- #
# Codex round1 #3: only FACE-DISPLAY label roles count. A match on a non-display
# role (documentation) must NOT bind the concept.
# --------------------------------------------------------------------------- #

def test_non_display_role_documentation_not_matched():
    edges = [
        {"role_uri": _IS_ROLE, "child_qname": "sndk:SpecialCharge",
         "order": 3.0, "preferred_label": _TERSE, "period": "FY2025"},
    ]
    labels = {
        "sndk:SpecialCharge": [
            {"role": _DOC, "text": "Special charge"},          # non-display only
            {"role": _TERSE, "text": "Restructuring, net"},    # the real face label
        ],
    }
    # PDF text equals the DOCUMENTATION text, not the displayed terseLabel → no bind.
    assert resolve_via_label_text(
        "Special charge", edges, labels, "IS") == (None, None, None, None)
    # Sanity: the actual face label DOES resolve.
    c, o, _, _ = resolve_via_label_text("Restructuring, net", edges, labels, "IS")
    assert c == "sndk:SpecialCharge" and o == 3.0


# --------------------------------------------------------------------------- #
# Codex round2 #1: full-qname identity must survive global-ordinal stamping.
# compute_global_ordinals now keys by BOTH bare local and full qname so an
# exact-qname caller (the label-text fallback) is never handed a homonym's slot.
# --------------------------------------------------------------------------- #

def test_global_ordinals_full_qname_key_distinguishes_homonyms():
    edges = [
        {"role_uri": _IS_ROLE, "child_qname": "sndk:Foo", "order": 1.0,
         "parent_qname": None},
        {"role_uri": _IS_ROLE, "child_qname": "us-gaap:Foo", "order": 2.0,
         "parent_qname": None},
    ]
    g = compute_global_ordinals(edges, "IS")
    # exact full-qname keys are distinct (the round2 fix)
    assert g["sndk:Foo"] == 1
    assert g["us-gaap:Foo"] == 2
    # bare-local key keeps first-DFS-wins (back-compat for legacy callers)
    assert g["Foo"] == 1
