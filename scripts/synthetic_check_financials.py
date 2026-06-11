"""Synthetic monitoring for the production financials data (SOP §3.7 Observe /
P9: run a test subset against production to catch business-logic / data drift).

Read-only. Queries Supabase production `sec_financial_facts` for every
KNOWN_TICKER and asserts the PDF-faithful + dedup invariants that the upsert
gate enforces at write time — so a future re-upsert (or a manual edit) that
silently breaks them is caught here instead of by a user noticing a wrong page.

Invariants:
  A. Coverage / position contract — a display-eligible row (display_label set)
     in IS/BS/CF for a displayed (non-YTD) period MUST carry an ordinal; else it
     renders at the wrong position.
  B. Dedup suppression intact — the rows the dedup pass suppresses must stay
     suppressed (display_label AND ordinal NULL). A re-upsert that drops the
     dedup pass would resurface duplicate As-Reported rows.
  C. Liveness — each ticker still has a sane number of display-eligible IS rows
     (catches a ticker silently going empty).

Exit 0 = all green; exit 1 = at least one violation (wire to cron + alert).
Run: uv run --with supabase --with python-dateutil python3 scripts/synthetic_check_financials.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Tools", "research-tools"))

import upsert_sec_financials as U  # noqa: E402

TICKERS = ["AAOI", "INTC", "LITE", "MU", "SNDK"]
_YTD = {"cumulative_ytd", "ytd_duration"}
_FACE = {"IS", "BS", "CF"}

# Known rows the dedup pass suppresses (must stay display_label/ordinal NULL).
DEDUP_SUPPRESSED = {
    "SNDK": [("nonoperating_long_tail", "Gain on business divestiture"),
             ("nonoperating_long_tail", "Loss on business divestiture")],
    "LITE": [("income_statement_long_tail", "IncomeLossAttributableToParent")],
}
MIN_IS_DISPLAY_ROWS = 10  # liveness floor


def _all_facts(client, ticker, page=1000):
    rows, start = [], 0
    while True:
        r = (client.table("sec_financial_facts")
             .select("statement,period,period_kind,uni_account,source_account,display_label,ordinal")
             .eq("ticker", ticker).order("cell_id")
             .range(start, start + page - 1).execute())
        rows.extend(r.data)
        if len(r.data) < page:
            break
        start += page
    return rows


def check_ticker(client, ticker):
    facts = _all_facts(client, ticker)
    fails = []

    # A. coverage / position
    cov = [f for f in facts
           if f["statement"] in _FACE
           and f["period_kind"] not in _YTD
           and f.get("display_label") is not None
           and f.get("ordinal") is None]
    if cov:
        fails.append(f"A.coverage: {len(cov)} display-eligible row(s) missing ordinal "
                     f"(e.g. {cov[0]['statement']}/{cov[0]['period']}/{cov[0]['source_account']!r})")

    # B. dedup suppression intact
    for uni, sa in DEDUP_SUPPRESSED.get(ticker, []):
        live = [f for f in facts
                if f["uni_account"] == uni and f["source_account"] == sa
                and (f.get("display_label") is not None or f.get("ordinal") is not None)]
        if live:
            fails.append(f"B.dedup: {uni}/{sa!r} resurfaced ({len(live)} cell(s) with "
                         f"display_label/ordinal set — dedup pass regressed)")

    # C. liveness
    is_disp = [f for f in facts
               if f["statement"] == "IS" and f.get("display_label") is not None
               and f["period_kind"] not in _YTD]
    if len(is_disp) < MIN_IS_DISPLAY_ROWS:
        fails.append(f"C.liveness: only {len(is_disp)} display-eligible IS rows "
                     f"(< {MIN_IS_DISPLAY_ROWS}) — ticker may be empty/broken")

    return fails


def main():
    client = U.supabase_client()
    print("=== Synthetic check: production financials invariants ===")
    total_fail = 0
    for t in TICKERS:
        fails = check_ticker(client, t)
        if fails:
            total_fail += len(fails)
            print(f"  ✗ {t}: {len(fails)} violation(s)")
            for f in fails:
                print(f"      - {f}")
        else:
            print(f"  ✓ {t}: coverage + dedup + liveness OK")
    print("=" * 56)
    if total_fail:
        print(f"  ✗ {total_fail} violation(s) — investigate before next user-facing use.")
        sys.exit(1)
    print("  ✓ All tickers green.")
    sys.exit(0)


if __name__ == "__main__":
    main()
