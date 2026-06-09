"""Tests for resolve_via_label_text — the narrow, fail-closed PDF-label→face-concept
ordinal fallback (SNDK legacy AGENT_CLASSIFIED rows with no concept link).
Spec: docs/superpowers/specs/2026-06-09-sndk-label-text-fallback-design.md
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from presentation_resolver import resolve_via_label_text

# A realistic SNDK-shaped IS face network. role_uri contains "operations" so it
# counts as an IS face network. Two real concepts with their official labels.
_IS_ROLE = "http://sandisk.com/role/statement-consolidated-statements-of-operations"
_TERSE = "http://www.xbrl.org/2003/role/terseLabel"
_NEG_TERSE = "http://www.xbrl.org/2009/role/negatedTerseLabel"
_STD = "http://www.xbrl.org/2003/role/label"

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
    # "Business separation costs" == sndk:BusinessSeparationCosts terseLabel.
    concept, ordn, neg = resolve_via_label_text(
        "Business separation costs", _EDGES, _LABELS, "IS")
    assert concept == "BusinessSeparationCosts"
    assert ordn == 4.0
    assert neg is False  # terseLabel preferred_label → not negated


def test_gain_variant_hits_gainloss_concept():
    # PDF "Gain on business divestiture" == terseLabel of GainLossOnSaleOfBusiness.
    concept, ordn, neg = resolve_via_label_text(
        "Gain on business divestiture", _EDGES, _LABELS, "IS")
    assert concept == "GainLossOnSaleOfBusiness"
    assert ordn == 6.0
    # face edge preferred_label = negatedTerseLabel → sign comes from the FACE arc.
    assert neg is True


def test_loss_variant_paren_strip_same_concept():
    # PDF "Loss on business divestiture" must match negatedTerseLabel
    # "(Gain) loss on business divestiture" via the narrow leading-paren strip.
    concept, ordn, neg = resolve_via_label_text(
        "Loss on business divestiture", _EDGES, _LABELS, "IS")
    assert concept == "GainLossOnSaleOfBusiness"
    assert ordn == 6.0
    assert neg is True


def test_no_match_returns_none():
    concept, ordn, neg = resolve_via_label_text(
        "Some line that is not on the face", _EDGES, _LABELS, "IS")
    assert (concept, ordn, neg) == (None, None, None)


def test_empty_source_returns_none():
    assert resolve_via_label_text("", _EDGES, _LABELS, "IS") == (None, None, None)
    assert resolve_via_label_text(None, _EDGES, _LABELS, "IS") == (None, None, None)


def test_ambiguous_two_concepts_same_label_fail_closed():
    # Two DISTINCT concepts carry the same normalized label → must NOT pick one.
    edges = _EDGES + [
        {"role_uri": _IS_ROLE, "child_qname": "sndk:OtherSeparationCosts",
         "order": 5.0, "preferred_label": _TERSE, "period": "FY2025"},
    ]
    labels = dict(_LABELS)
    labels["sndk:OtherSeparationCosts"] = [
        {"role": _TERSE, "text": "Business separation costs"}]  # collides
    assert resolve_via_label_text(
        "Business separation costs", edges, labels, "IS") == (None, None, None)


def test_note_network_concept_not_used():
    # The concept is ONLY on a note/reconciliation network (not a face network) →
    # must not resolve (discipline #1: accepted face networks only).
    note_role = "http://sandisk.com/role/statement-note-income-taxes-reconciliation"
    edges = [
        {"role_uri": note_role, "child_qname": "sndk:BusinessSeparationCosts",
         "order": 4.0, "preferred_label": _TERSE, "period": "FY2025"},
    ]
    assert resolve_via_label_text(
        "Business separation costs", edges, _LABELS, "IS") == (None, None, None)


def test_no_face_network_returns_none():
    # AAOI-shaped: no matching face network at all for the statement.
    assert resolve_via_label_text(
        "Business separation costs", [], _LABELS, "IS") == (None, None, None)


def test_punctuation_and_case_normalized():
    # Case + trailing punctuation differences still match.
    concept, ordn, _ = resolve_via_label_text(
        "  BUSINESS SEPARATION COSTS.  ", _EDGES, _LABELS, "IS")
    assert concept == "BusinessSeparationCosts" and ordn == 4.0
