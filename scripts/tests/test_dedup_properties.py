"""Property-based (Hypothesis) tests for the dedup pass guards (SOP P3 / Build
gate T2+: new guard functions get property tests that fuzz the boundaries the
example-based tests in test_dedup_redundant_rows.py don't reach).

Invariants under test (must hold for ARBITRARY inputs):
  1. _magnitude is sign-invariant (the value veto is magnitude-only).
  2. _face_fullqname is fail-closed: returns a qname ONLY when exactly one
     namespace carries the bare local on the face; 0 or >1 → None.
  3. dedup_redundant_rows NEVER mutates any fact.value (suppress-not-delete).
  4. Suppression is whole-row ATOMIC: a rowId's cells are either all
     dedup-suppressed or none are (never partial — the frontend renders
     per-rowId, so a partial suppression would resurrect).
  5. dedup_redundant_rows never raises on arbitrary facts/edges (robustness;
     mirrors the OverflowError fuzz finding in derive-analytics).
"""
import os
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

_WT_SHARED_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "Tools", "research-tools")
)
sys.path.insert(0, _WT_SHARED_ROOT)
for _m in [m for m in list(sys.modules) if m == "_shared" or m.startswith("_shared.")]:
    _cached = sys.modules[_m]
    _file = getattr(_cached, "__file__", "") or ""
    if not os.path.abspath(_file).startswith(_WT_SHARED_ROOT):
        del sys.modules[_m]

from _shared.sec_json_adapter import (  # noqa: E402
    FactRow,
    dedup_redundant_rows,
    _face_fullqname,
    _magnitude,
)

_IS_NET = "http://x/role/statement-consolidated-statements-of-operations"  # → IS


def _fact(uni_account, source_account, *, period="FY2025", value=1.0,
          period_kind="single_quarter", display_negated=None, ordinal=11,
          display_label="L"):
    return FactRow(
        cell_id=f"cid::{uni_account}::{source_account}::{period}",
        ticker="T", period=period, period_end="2025-12-31",
        period_kind=period_kind, statement="IS", version="GAAP",
        uni_account=uni_account, source_account=source_account, xbrl_tag=None,
        value=value, weight=1, unit="USD_thousands", status="SOURCE_OF_TRUTH",
        ordinal=ordinal, long_tail_metadata=None, provenance={},
        display_label=display_label, display_eligible=True,
        display_negated=display_negated,
    )


_finite = st.floats(allow_nan=False, allow_infinity=False,
                    min_value=-1e12, max_value=1e12)


# 1. _magnitude sign-invariance ------------------------------------------------
@given(v=_finite, neg=st.booleans())
def test_magnitude_is_sign_invariant(v, neg):
    # magnitude ignores sign AND display_negated — it is |raw value|.
    assert _magnitude(_fact("u", "s", value=v, display_negated=neg)) == abs(v)
    assert (_magnitude(_fact("u", "s", value=v))
            == _magnitude(_fact("u", "s", value=-v)))


# 2. _face_fullqname fail-closed ----------------------------------------------
_NS = st.sampled_from(["us-gaap", "ext", "foo", "bar"])
_LOCAL = st.sampled_from(["Foo", "Bar", "GainLossOnSaleOfBusiness"])


@given(namespaces=st.lists(_NS, min_size=0, max_size=4), local=_LOCAL,
       noise=st.lists(st.tuples(_NS, _LOCAL), max_size=4))
def test_face_fullqname_failclosed(namespaces, local, noise):
    edges = [{"role_uri": _IS_NET, "child_qname": f"{ns}:{local}", "order": 1.0}
             for ns in namespaces]
    # noise = other locals on the face; must not affect the answer for `local`.
    edges += [{"role_uri": _IS_NET, "child_qname": f"{ns}:{loc}", "order": 2.0}
              for (ns, loc) in noise if loc != local]
    res = _face_fullqname(local, edges, "IS")
    distinct = {f"{ns}:{local}" for ns in namespaces}
    if len(distinct) == 1:
        assert res == next(iter(distinct))           # unique → that full qname
    else:
        assert res is None                           # 0 or ≥2 → fail-closed
    if res is not None:
        assert res.rsplit(":", 1)[-1] == local       # recovered local matches


@given(local=_LOCAL, ns=_NS)
def test_face_fullqname_offface_is_none(local, ns):
    # concept present only on a NOTE role (not a face network) → None.
    note = "http://x/role/note-7-income-taxes-details"
    edges = [{"role_uri": note, "child_qname": f"{ns}:{local}", "order": 1.0}]
    assert _face_fullqname(local, edges, "IS") is None


# strategy for arbitrary fact lists (mix of core + long-tail, tag + prose) -----
_UNI = st.sampled_from([
    "income_before_taxes", "net_income", "revenue",          # core
    "income_statement_long_tail", "nonoperating_long_tail",  # long-tail buckets
    "misc_long_tail",
])
_SA = st.sampled_from([
    "IncomeLossAttributableToParent", "GainLossOnSaleOfBusiness",  # tag-like
    "Income before income taxes", "Gain on business divestiture",  # prose
])
_PERIOD = st.sampled_from(["FY2024", "FY2025", "Q1_FY2025", "6M_FY2025"])
_PKIND = st.sampled_from(["single_quarter", "fy_annual_duration",
                         "cumulative_ytd", "ytd_duration"])


@st.composite
def _facts(draw):
    n = draw(st.integers(min_value=0, max_value=12))
    out = []
    for _ in range(n):
        out.append(_fact(
            draw(_UNI), draw(_SA), period=draw(_PERIOD),
            value=draw(_finite), period_kind=draw(_PKIND),
            display_negated=draw(st.booleans() | st.none()),
        ))
    return out


def _dedup_flag(f):
    return (f.provenance or {}).get("display_exclusion_reason") == "dedup_redundant_row"


# 3. value preservation (suppress-not-delete) ---------------------------------
@settings(max_examples=200)
@given(facts=_facts())
def test_dedup_never_mutates_value(facts):
    before = [f.value for f in facts]
    dedup_redundant_rows(facts, statement="IS", edges=[], labels={})
    assert [f.value for f in facts] == before


# 4. whole-row atomicity ------------------------------------------------------
@settings(max_examples=200)
@given(facts=_facts())
def test_dedup_suppression_is_whole_row_atomic(facts):
    dedup_redundant_rows(facts, statement="IS", edges=[], labels={})
    by_row: dict = {}
    for f in facts:
        by_row.setdefault((f.uni_account, f.source_account), []).append(f)
    for cells in by_row.values():
        flags = [_dedup_flag(c) for c in cells]
        assert all(flags) or not any(flags), "partial suppression resurrects in frontend"
        # a suppressed row has display_label AND ordinal nulled on every cell
        if any(flags):
            for c in cells:
                assert c.display_label is None and c.ordinal is None


# 5. robustness: never raises -------------------------------------------------
@settings(max_examples=200)
@given(facts=_facts())
def test_dedup_does_not_raise(facts):
    dedup_redundant_rows(facts, statement="IS", edges=[], labels={})
