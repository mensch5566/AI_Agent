"""Task 9 — coverage hard gate (spec G4).

100% of display-eligible FACT rows (per ticker × statement IS/BS/CF) must carry
an ordinal, else the gate FAILS and blocks --apply.

Denominator = display-eligible FACT rows only. EXCLUDED from the denominator:
  - YTD-duration rows (period_kind == "ytd_duration")
  - metric-only rows (derived_q2/q3/q4 single quarters; ebitda / free_cash_flow)
  - display-INELIGIBLE synthetic SUM-of-multiple-PDF-lines rows (display_eligible False)

`coverage_report(rows)` returns per-statement
    {statement: {"eligible": int, "with_ordinal": int, "missing": [..]}}
and `coverage_gate_blocks_apply(report)` is the apply-blocking predicate (True =
must block; any statement < 100%).
"""
import os
import sys

# Resolve THIS worktree's `_shared` package (mirror test_upsert_display.py).
_WT_SHARED_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "Tools", "research-tools")
)
sys.path.insert(0, _WT_SHARED_ROOT)
for _m in [m for m in list(sys.modules) if m == "_shared" or m.startswith("_shared.")]:
    _cached = sys.modules[_m]
    _file = getattr(_cached, "__file__", "") or ""
    if not os.path.abspath(_file).startswith(_WT_SHARED_ROOT):
        del sys.modules[_m]

# Load the upsert module by file path (it lives in scripts/, not a package).
import importlib.util  # noqa: E402

_UPSERT_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "upsert_sec_financials.py")
)
_spec = importlib.util.spec_from_file_location("_upsert_sec_financials_cg", _UPSERT_PATH)
U = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(U)

from _shared.sec_json_adapter import FactRow  # noqa: E402


def _fact(uni_account, *, statement="IS", period="FY2025", period_kind="annual",
          version="GAAP", ordinal=None, display_eligible=True, source_account=None,
          cell_id=None):
    return FactRow(
        cell_id=cell_id or f"cid::{statement}::{uni_account}::{period}",
        ticker="TEST",
        period=period,
        period_end="2025-12-31",
        period_kind=period_kind,
        statement=statement,
        version=version,
        uni_account=uni_account,
        source_account=source_account if source_account is not None else uni_account,
        xbrl_tag=None,
        value=1.0,
        weight=1,
        unit="USD_thousands",
        status="SOURCE_OF_TRUTH",
        ordinal=ordinal,
        long_tail_metadata=None,
        provenance={},
        display_eligible=display_eligible,
    )


# --------------------------------------------------------------------------- #
# A display-eligible BS fact missing ordinal → BS < 100% + must-block
# --------------------------------------------------------------------------- #

def test_missing_ordinal_on_eligible_bs_fact_blocks_apply():
    rows = [
        _fact("revenue", statement="IS", ordinal=1.0),
        _fact("gross_profit", statement="IS", ordinal=2.0),
        # BS: one ordered, one MISSING ordinal.
        _fact("cash", statement="BS", period_kind="instant", ordinal=1.0),
        _fact("inventory", statement="BS", period_kind="instant", ordinal=None,
              source_account="Inventories"),
    ]
    report = U.coverage_report(rows)

    assert report["IS"]["eligible"] == 2
    assert report["IS"]["with_ordinal"] == 2
    assert report["IS"]["missing"] == []

    assert report["BS"]["eligible"] == 2
    assert report["BS"]["with_ordinal"] == 1
    assert len(report["BS"]["missing"]) == 1
    miss = report["BS"]["missing"][0]
    assert miss["statement"] == "BS"
    # missing entry surfaces enough to locate the unmatched line.
    assert miss.get("uni_account") == "inventory" or miss.get("source_account") == "Inventories"
    assert miss.get("period") == "FY2025"

    # Apply-blocking predicate: BS is < 100% → must block.
    assert U.coverage_gate_blocks_apply(report) is True


# --------------------------------------------------------------------------- #
# YTD / metric-only / synthetic-ineligible rows are EXCLUDED from denominator
# → a batch whose ONLY missing-ordinal rows are those types → gate PASSES 100%
# --------------------------------------------------------------------------- #

def test_excluded_rows_do_not_count_against_coverage():
    rows = [
        # Real display-eligible facts WITH ordinal → 100% on each statement.
        _fact("revenue", statement="IS", ordinal=1.0),
        _fact("cash", statement="BS", period_kind="instant", ordinal=1.0),
        _fact("cfo", statement="CF", ordinal=1.0),

        # --- all of the following are missing ordinal but MUST be excluded ---
        # YTD-duration row (6M cumulative) — excluded.
        _fact("revenue", statement="IS", period="6M_FY2025",
              period_kind="ytd_duration", ordinal=None),
        # metric-only: derived single quarters — excluded.
        _fact("operating_income", statement="IS", period_kind="derived_q2", ordinal=None),
        _fact("operating_income", statement="IS", period_kind="derived_q3", ordinal=None),
        _fact("operating_income", statement="IS", period_kind="derived_q4", ordinal=None),
        # metric-only: ebitda / free_cash_flow by uni_account — excluded.
        _fact("ebitda", statement="IS", ordinal=None),
        _fact("free_cash_flow", statement="CF", ordinal=None),
        # display-INELIGIBLE synthetic SUM-of-multiple — excluded.
        _fact("selling_general_administrative", statement="IS",
              display_eligible=False, ordinal=None,
              source_account="SUM(S&M+G&A)"),
    ]
    report = U.coverage_report(rows)

    # Denominator counts ONLY the 3 real eligible facts (one per statement).
    assert report["IS"]["eligible"] == 1
    assert report["BS"]["eligible"] == 1
    assert report["CF"]["eligible"] == 1
    for stmt in ("IS", "BS", "CF"):
        assert report[stmt]["with_ordinal"] == report[stmt]["eligible"]
        assert report[stmt]["missing"] == []

    # 100% everywhere → gate PASSES, does not block apply.
    assert U.coverage_gate_blocks_apply(report) is False


def test_coverage_pct_helper_and_empty_statement():
    rows = [
        _fact("revenue", statement="IS", ordinal=1.0),
        _fact("gross_profit", statement="IS", ordinal=None),
    ]
    report = U.coverage_report(rows)
    # IS = 1/2 = 50% → blocks.
    assert report["IS"]["eligible"] == 2
    assert report["IS"]["with_ordinal"] == 1
    assert U.coverage_pct(report["IS"]) == 50.0
    assert U.coverage_gate_blocks_apply(report) is True
    # No BS/CF rows → those statements absent from report (vacuously fine).
    assert "BS" not in report or report["BS"]["eligible"] == 0


def test_non_gaap_facts_excluded_from_coverage_denominator():
    """Bug fix (T14): Non-GAAP (8-K reconciliation) facts overlay GAAP face rows
    by uni_account and have NO XBRL presentation network — attach_display_to_batch
    only resolves GAAP facts, so a Non-GAAP fact can never carry an ordinal.
    Counting them in the GAAP-statement coverage denominator falsely fails the
    gate. They must be EXCLUDED."""
    rows = [
        # one GAAP face row with an ordinal → 100% of the GAAP denominator
        _fact("revenue", statement="IS", ordinal=1.0, version="GAAP"),
        # Non-GAAP overlay facts with NO ordinal (PDF-label source_account) —
        # must NOT count against coverage.
        _fact("gross_profit", statement="IS", ordinal=None, version="NON_GAAP",
              source_account="Gross margin"),
        _fact("operating_income", statement="IS", ordinal=None, version="NON_GAAP",
              source_account="Operating income"),
    ]
    report = U.coverage_report(rows)
    assert report["IS"]["eligible"] == 1          # only the GAAP fact
    assert report["IS"]["with_ordinal"] == 1
    assert U.coverage_pct(report["IS"]) == 100.0
    assert U.coverage_gate_blocks_apply(report) is False  # Non-GAAP didn't break it
