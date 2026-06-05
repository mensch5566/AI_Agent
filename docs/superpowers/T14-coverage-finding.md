# T14 dry-run finding — resolver doesn't reach 100% coverage on real multi-filing data

**Status**: BLOCKING. The coverage hard gate (Task 9) correctly refuses `--apply`. The PDF-faithful
statement view must NOT ship until the presentation-network resolution handles the 10-K/10-Q dual-network
+ YTD-period reality. T1–T13 code is all done + tested; this is a resolver design gap surfaced only by
real data at T14c.

## What happened

`display_label` migration applied to prod (T14a, 2026-06-05). INTC dry-run (read-only) coverage:

- **IS 66.2% (94/142)** — 48 display-eligible rows missing `ordinal`
- **BS 91.2% (103/113)** — 10 missing
- **CF 84.0% (68/81)** — 13 missing

The gate blocks apply (correct).

## Root cause (diagnosed)

INTC's `edges_pre` has **two** IS presentation networks, each with 20 children but DIFFERENT line items
and DIFFERENT period coverage:

| network role | children | periods present |
|---|---|---|
| `…ConsolidatedStatementsofIncome` (full 10-K) | 20 | FY2025 only |
| `…ConsolidatedCondensedStatementsofIncome` (condensed 10-Q) | 20 | Q1_FY2025, Q2_FY2025, Q3_FY2025, Q1_FY2026 only |

- The full 10-K statement breaks out `interest_expense`, `interest_income`,
  `other_nonoperating_income_expense`, `amortization_of_acquired_intangibles`, `goodwill_impairment`,
  `gain_loss_on_equity_investments`; the condensed 10-Q aggregates these into "interest and other, net".
- Neither network's `period` set covers the YTD periods `6M_FY2025` / `9M_FY2025` or aligns across both
  annual (FY2025) and quarterly facts.
- `select_network` (spec §4.1: largest facts-overlap, tie-break size) sees both at 20 children → picks one
  (the condensed). The other network's exclusive lines then get no ordinal → coverage gap.

So the spec's "pick ONE latest network and resolve every fact against it" (§4.1/§4.2) is insufficient for a
filer that has both a full 10-K statement and a condensed 10-Q statement (different line granularity), plus
YTD periods absent from either presentation network. Note: core concepts (revenue/gross_profit/
operating_income/net_income) DO resolve to an ordinal in the condensed network (revenue=1, gp=3, oi=8,
ni=15) — so the per-concept ordinal machinery works; the gap is which network(s) the ordering is sourced
from and which line items/periods that leaves uncovered. (A secondary observation: `resolve_label_ordinal`
returns `label=None` for these — labels.json text isn't resolving via preferred_label either; investigate
alongside.)

## Proposed fix direction (for the focused next task — design first)

1. **Network selection → network UNION/merge per statement.** Build the canonical row ordering from the
   most-complete statement network (prefer the full 10-K `ConsolidatedStatementsofIncome` over the
   `Condensed` one), then SUPPLEMENT with any concept/ordinal only present in the other network so every
   disclosed line gets a position. Resolve each concept's ordinal ONCE (period-independent) and apply to
   all periods of that concept (spec §4.2 intent: "one ordering per statement across all period columns").
2. Decide the merge ordering rule when 10-K and 10-Q disagree on order (10-K is the fuller PDF; prefer it).
3. Re-check the `label=None` issue (preferred_label → terse/total/label fallback not yielding text).
4. Genuinely-absent-from-all-XBRL lines (if any remain) route to the NLM ordering artifact (Task 6/7) as
   designed — but most of INTC's missing lines ARE in the 10-K network, so the union fix should recover
   them without NLM.
5. Re-run dry-run for all 5 tickers; coverage must hit 100% (or the residual goes to audited NLM order)
   before `--apply`.

This is a Task-3/Task-8 enhancement (presentation_resolver + attach_display_to_batch) with its own TDD +
real-data dry-run loop, then Codex review, then the gated production rollout (T14d) + visual verify (T15).

## State at stop

- Branch `worktree-statement-view-pdf-faithful`: T1–T13 + vitest, 14 commits, 34 vitest + 323 py + tsc green.
- Prod: `sec_financial_facts.display_label` column ADDED (nullable, empty) — harmless, frontend falls back
  to source_account when null, and no `--apply` wrote any display_label yet. No production data changed.
- NOT done: T14c coverage to 100% (blocked by the above), T14d `--apply`, T15 visual, T16 docs/Codex/finish.
