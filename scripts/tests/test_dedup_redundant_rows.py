"""Dedup pass — whole-row redundancy suppression (spec
docs/superpowers/specs/2026-06-10-dedup-display-suppression-design.md v2).

As Reported duplicate rows: a legacy prose fact and a capture-everything tag
fact denote the SAME economic line. v2 design = WHOLE-ROW suppression: null a
loser row's display_label+ordinal across ALL periods, ONLY when every displayed
(non-YTD) period has a winner competitor (fail-safe otherwise). Pairing:
  Key A — long-tail vs long-tail (SNDK): prose label-text concept == tag concept.
  Key B — core vs long-tail   (LITE): tag concept in DEDUP_EQUIVALENT_CONCEPTS[U].
Both guarded by value-disagreement / multi-occurrence / CF-instant vetoes.
Suppression nulls the persisted display fields (display_eligible is adapter-only,
not a DB column — Blocker 1 from 3-way review).
"""
import os
import sys

_WT_SHARED_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "Tools", "research-tools")
)
sys.path.insert(0, _WT_SHARED_ROOT)
for _m in [m for m in list(sys.modules) if m == "_shared" or m.startswith("_shared.")]:
    _cached = sys.modules[_m]
    _file = getattr(_cached, "__file__", "") or ""
    if not os.path.abspath(_file).startswith(_WT_SHARED_ROOT):
        del sys.modules[_m]

from _shared.sec_json_adapter import FactRow, dedup_redundant_rows  # noqa: E402

_TERSE = "http://www.xbrl.org/2003/role/terseLabel"
_STD = "http://www.xbrl.org/2003/role/label"
_NEG = "http://www.xbrl.org/2009/role/negatedLabel"
# IS face network (role contains "operations" → matched by matching_face_networks).
_IS_NET = "http://x/role/statement-consolidated-statements-of-operations"

# Divestiture concept on the IS face, displayed via a terseLabel the prose text
# matches. One edge per period so resolve_via_label_text finds it on the face.
_DIVEST_EDGES = [
    {"role_uri": _IS_NET, "child_qname": "us-gaap:GainLossOnSaleOfBusiness",
     "order": 18.0, "preferred_label": _NEG, "period": p}
    for p in ("FY2025", "Q2_FY2025", "Q3_FY2025")
]
_DIVEST_LABELS = {
    "us-gaap:GainLossOnSaleOfBusiness": [
        {"role": _TERSE, "text": "Gain on business divestiture"},
        {"role": _NEG, "text": "(Gain) loss on business divestiture"},
    ],
}


def _fact(uni_account, source_account, *, period, value, period_kind="single_quarter",
          statement="IS", display_label=None, ordinal=None, display_negated=None,
          xbrl_tag=None):
    return FactRow(
        cell_id=f"cid::{uni_account}::{source_account}::{period}",
        ticker="TEST",
        period=period,
        period_end="2025-12-31",
        period_kind=period_kind,
        statement=statement,
        version="GAAP",
        uni_account=uni_account,
        source_account=source_account,
        xbrl_tag=xbrl_tag,
        value=value,
        weight=1,
        unit="USD_thousands",
        status="SOURCE_OF_TRUTH",
        ordinal=ordinal,
        long_tail_metadata=None,
        provenance={"source_filing": "10-K"},
        display_label=display_label,
        display_eligible=True,
        display_negated=display_negated,
    )


# --------------------------------------------------------------------------- #
# Key B — core uni vs tag long-tail (LITE income_before_taxes shape)
# --------------------------------------------------------------------------- #
def test_keyB_suppresses_tag_longtail_when_core_covers_all_periods():
    # LITE: prose core `income_before_taxes` (ordinal 24) + tag long-tail
    # `IncomeLossAttributableToParent` (ordinal 22); equal values every period.
    core = [_fact("income_before_taxes", "Income before income taxes", period=p,
                  value=v, display_label="Income before income taxes", ordinal=24)
            for p, v in [("FY2024", 100.0), ("FY2025", 120.0)]]
    tag = [_fact("income_statement_long_tail", "IncomeLossAttributableToParent",
                 period=p, value=v,
                 display_label="Net income attributable to parent", ordinal=22)
           for p, v in [("FY2024", 100.0), ("FY2025", 120.0)]]
    facts = core + tag

    dedup_redundant_rows(facts, statement="IS", edges=[], labels={})

    # tag long-tail row fully suppressed (both periods nulled)
    for f in tag:
        assert f.display_label is None, "display_label must be nulled (Blocker 1)"
        assert f.ordinal is None, "ordinal must be nulled (Blocker 1)"
        assert f.display_eligible is False
        assert f.provenance.get("display_exclusion_reason") == "dedup_redundant_row"
        assert f.provenance.get("dedup_key") == "B"
    # core row untouched (winner)
    for f in core:
        assert f.display_label == "Income before income taxes"
        assert f.ordinal == 24
        assert f.display_eligible is True
        assert "display_exclusion_reason" not in (f.provenance or {})


def test_keyB_failsafe_not_suppressed_when_a_displayed_period_lacks_winner():
    # Whole-row precondition (Blocker 2): if ANY displayed period of the loser
    # row has no winner competitor, the row must NOT be suppressed — better a
    # temporary duplicate than a vanished value.
    core = [_fact("income_before_taxes", "Income before income taxes",
                  period="FY2024", value=100.0,
                  display_label="Income before income taxes", ordinal=24)]
    tag = [_fact("income_statement_long_tail", "IncomeLossAttributableToParent",
                 period=p, value=v,
                 display_label="Net income attributable to parent", ordinal=22)
           for p, v in [("FY2024", 100.0), ("FY2025", 120.0)]]  # FY2025 has no core
    facts = core + tag

    dedup_redundant_rows(facts, statement="IS", edges=[], labels={})

    for f in tag:  # untouched — FY2025 would vanish otherwise
        assert f.display_label == "Net income attributable to parent"
        assert f.ordinal == 22
        assert f.display_eligible is True


def test_keyB_value_disagreement_veto_blocks_suppression():
    # If the displayed values disagree (e.g. attributable-to-parent differs
    # from consolidated by the NCI share), the rows are NOT the same line →
    # do not suppress (value as VETO, not match key).
    core = [_fact("income_before_taxes", "Income before income taxes", period=p,
                  value=v, display_label="Income before income taxes", ordinal=24)
            for p, v in [("FY2024", 100.0), ("FY2025", 120.0)]]
    tag = [_fact("income_statement_long_tail", "IncomeLossAttributableToParent",
                 period=p, value=v,
                 display_label="Net income attributable to parent", ordinal=22)
           for p, v in [("FY2024", 100.0), ("FY2025", 95.0)]]  # FY2025 disagrees
    facts = core + tag

    dedup_redundant_rows(facts, statement="IS", edges=[], labels={})

    for f in tag:
        assert f.display_label == "Net income attributable to parent"
        assert f.display_eligible is True


def test_keyB_ytd_period_excluded_from_precondition_but_nulled_on_suppress():
    # A YTD-only cell on the loser row (no core competitor) must NOT block
    # suppression (YTD is not displayed), yet IS nulled when the row is
    # suppressed (harmless — never rendered).
    core = [_fact("income_before_taxes", "Income before income taxes", period=p,
                  value=v, display_label="Income before income taxes", ordinal=24)
            for p, v in [("Q1_FY2025", 30.0), ("Q2_FY2025", 40.0)]]
    tag = [
        _fact("income_statement_long_tail", "IncomeLossAttributableToParent",
              period="Q1_FY2025", value=30.0, display_label="ATP", ordinal=22),
        _fact("income_statement_long_tail", "IncomeLossAttributableToParent",
              period="Q2_FY2025", value=40.0, display_label="ATP", ordinal=22),
        # YTD cell — no core competitor, must not block, must be nulled
        _fact("income_statement_long_tail", "IncomeLossAttributableToParent",
              period="6M_FY2025", value=70.0, period_kind="cumulative_ytd",
              display_label="ATP", ordinal=22),
    ]
    facts = core + tag

    dedup_redundant_rows(facts, statement="IS", edges=[], labels={})

    for f in tag:
        assert f.display_label is None
        assert f.ordinal is None
        assert f.display_eligible is False


# --------------------------------------------------------------------------- #
# Key A — long-tail prose vs long-tail tag (SNDK divestiture shape)
# --------------------------------------------------------------------------- #
def test_keyA_suppresses_prose_when_tag_covers_all_periods_negated_equal():
    # tag GainLossOnSaleOfBusiness is on a negatedLabel arc: stored +34 renders
    # as -34, matching the prose 'Gain on business divestiture' stored -34.
    # Preference order: tag_like long-tail beats prose long-tail → prose loses.
    # (Assumes the Q2-window re-parse so tag covers every prose period.)
    tag = [_fact("is_long_tail", "GainLossOnSaleOfBusiness", period=p, value=v,
                 display_label="(Gain) loss on business divestiture", ordinal=18,
                 display_negated=True)
           for p, v in [("FY2025", 34.0), ("Q2_FY2025", 34.0), ("Q3_FY2025", 0.0)]]
    prose = [_fact("nonoperating_long_tail", "Gain on business divestiture",
                   period=p, value=v,
                   display_label="Gain on business divestiture", ordinal=18)
             for p, v in [("FY2025", -34.0), ("Q2_FY2025", -34.0), ("Q3_FY2025", 0.0)]]
    facts = tag + prose

    dedup_redundant_rows(facts, statement="IS",
                         edges=_DIVEST_EDGES, labels=_DIVEST_LABELS)

    for f in prose:  # loser — fully suppressed
        assert f.display_label is None, "prose row must be nulled"
        assert f.ordinal is None
        assert f.display_eligible is False
        assert f.provenance.get("display_exclusion_reason") == "dedup_redundant_row"
        assert f.provenance.get("dedup_key") == "A"
    for f in tag:  # winner — untouched
        assert f.display_label == "(Gain) loss on business divestiture"
        assert f.ordinal == 18
        assert f.display_eligible is True


def test_keyA_value_veto_compares_magnitude_not_signed_display():
    # Real SNDK: BOTH rows carry display_negated=True and OPPOSITE raw signs
    # (tag GainLossOnSaleOfBusiness raw +34, prose 'Gain on business
    # divestiture' raw -34 — prose is pre-negated legacy data). They are the
    # SAME event (magnitude 34); the value veto must compare |value|, else it
    # spuriously blocks a real duplicate.
    tag = [_fact("is_long_tail", "GainLossOnSaleOfBusiness", period=p, value=v,
                 display_label="(Gain) loss on business divestiture", ordinal=11,
                 display_negated=True)
           for p, v in [("FY2025", 34.0), ("Q2_FY2025", 34.0), ("Q3_FY2025", 0.0)]]
    prose = [_fact("nonoperating_long_tail", "Gain on business divestiture",
                   period=p, value=v,
                   display_label="Gain on business divestiture", ordinal=11,
                   display_negated=True)
             for p, v in [("FY2025", -34.0), ("Q2_FY2025", -34.0), ("Q3_FY2025", 0.0)]]
    facts = tag + prose

    dedup_redundant_rows(facts, statement="IS",
                         edges=_DIVEST_EDGES, labels=_DIVEST_LABELS)

    for f in prose:  # loser — suppressed (same magnitude every period)
        assert f.display_label is None
        assert f.display_eligible is False
        assert f.provenance.get("dedup_key") == "A"


def test_keyA_failsafe_prose_kept_when_tag_misses_a_period():
    # Real current SNDK: tag has no Q2 (parse window). Q2 prose is the only
    # source → prose row must survive (fail-safe), else Q2 value vanishes.
    tag = [_fact("is_long_tail", "GainLossOnSaleOfBusiness", period=p, value=v,
                 display_label="(Gain) loss on business divestiture", ordinal=18,
                 display_negated=True)
           for p, v in [("FY2025", 34.0), ("Q3_FY2025", 0.0)]]  # no Q2
    prose = [_fact("nonoperating_long_tail", "Gain on business divestiture",
                   period=p, value=v,
                   display_label="Gain on business divestiture", ordinal=18)
             for p, v in [("FY2025", -34.0), ("Q2_FY2025", -34.0), ("Q3_FY2025", 0.0)]]
    facts = tag + prose

    dedup_redundant_rows(facts, statement="IS",
                         edges=_DIVEST_EDGES, labels=_DIVEST_LABELS)

    for f in prose:  # untouched — Q2 has no tag competitor
        assert f.display_label == "Gain on business divestiture"
        assert f.display_eligible is True


# Two concepts share a bare local name across namespaces on the same face. The
# prose label uniquely matches the us-gaap one; the tag long-tail row stores only
# the bare local. Matching on bare local would wrongly pair us-gaap prose with a
# possibly-ext tag → must fail-closed (Codex GPT-5.5 merge-review blocker).
_HOMONYM_EDGES = [
    {"role_uri": _IS_NET, "child_qname": "us-gaap:GainLossOnSaleOfBusiness",
     "order": 11.0, "preferred_label": _TERSE, "period": "FY2025"},
    {"role_uri": _IS_NET, "child_qname": "ext:GainLossOnSaleOfBusiness",
     "order": 12.0, "preferred_label": _STD, "period": "FY2025"},
]
_HOMONYM_LABELS = {
    "us-gaap:GainLossOnSaleOfBusiness": [{"role": _TERSE, "text": "Gain on business divestiture"}],
    "ext:GainLossOnSaleOfBusiness": [{"role": _STD, "text": "Extension unrelated line"}],
}


def test_keyA_namespace_homonym_fails_closed():
    # tag source_account is the bare local 'GainLossOnSaleOfBusiness', which is
    # ambiguous across us-gaap: and ext: on this face → cannot prove identity →
    # must NOT suppress (full-qname requirement, spec §3.3).
    tag = [_fact("is_long_tail", "GainLossOnSaleOfBusiness", period="FY2025",
                 value=34.0, display_label="x", ordinal=12, display_negated=True)]
    prose = [_fact("nonoperating_long_tail", "Gain on business divestiture",
                   period="FY2025", value=-34.0,
                   display_label="Gain on business divestiture", ordinal=11,
                   display_negated=True)]
    facts = tag + prose

    dedup_redundant_rows(facts, statement="IS",
                         edges=_HOMONYM_EDGES, labels=_HOMONYM_LABELS)

    for f in prose:  # untouched — bare-local ambiguity is fail-closed
        assert f.display_label == "Gain on business divestiture"
        assert f.display_eligible is True


def test_keyA_multi_occurrence_veto_blocks_suppression():
    # If the resolved concept appears on >1 tag long-tail row in scope (e.g. the
    # same concept landed in two buckets), we cannot pick a unique winner →
    # fail-closed, do not suppress.
    tag1 = [_fact("is_long_tail", "GainLossOnSaleOfBusiness", period="FY2025",
                  value=34.0, display_label="x", ordinal=18, display_negated=True)]
    tag2 = [_fact("misc_long_tail", "GainLossOnSaleOfBusiness", period="FY2025",
                  value=34.0, display_label="y", ordinal=19, display_negated=True)]
    prose = [_fact("nonoperating_long_tail", "Gain on business divestiture",
                   period="FY2025", value=-34.0,
                   display_label="Gain on business divestiture", ordinal=18)]
    facts = tag1 + tag2 + prose

    dedup_redundant_rows(facts, statement="IS",
                         edges=_DIVEST_EDGES, labels=_DIVEST_LABELS)

    for f in prose:  # untouched — ambiguous winner
        assert f.display_label == "Gain on business divestiture"
        assert f.display_eligible is True
