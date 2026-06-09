---
type: design-spec
topic: cf-cash-movement-analysis
date: 2026-06-08
status: draft (for Codex GPT-5.5 design-gate review)
tier: T2 (frontend render; no parse/DB/storage change, no migration)
branch: worktree-statement-view-pdf-faithful
authority: SEC EDGAR Financial Report Manual (EFM) — via NLM "Topic - Parse_SEC_Filings",
  source a146d037 (EFM §6.7.4/§6.8.12/§7.7/§9.7). Supersedes the abandoned
  "Approach X" (store begin/end twins), which violates EFM §6.8.12.
---

# CF cash beginning/end — Movement Analysis (display layer)

## Authority (why store-two-rows is WRONG)

SEC EFM §6.8.12: **"Do not define separate concepts to represent the instants at the
beginning and the end of a period. The same instant represents the end of one period,
and the beginning of the next."** Vendors (Bloomberg/FactSet/CapIQ) implement this as
**"movement analysis"** (EFM §7.7): ONE instant fact is stored; the *renderer* shows
the same value as the **ending** balance of period P's column AND the **beginning**
balance of period P+1's column. Cash balances are instants → **never** derive by
subtraction (EFM): single-quarter beginning = prior quarter's ending instant.

So: keep storage as-is (one instant per period), fix purely in the frontend renderer.

## Bug (verified, visible in the frontend)

The cash-reconciliation concept `CashCashEquivalentsRestrictedCashAndRestricted
CashEquivalents` is stored once per period as the **period-END** cash balance:
- single-quarter Qx → `uni_account=ending_cash` (core, `quarter_duration`)
- YTD/FY → `uni_account=cf_long_tail` (`ytd_duration` excluded from statement view /
  `fy_annual_duration` shown in annual)

But the stored `display_label` (resolved at upsert) is **"Cash … at beginning of
period"** — wrong — because the resolver maps the single instant to `matched[0]` =
the `periodStartLabel` arc instead of matching by date. Verified frontend rows:
- Quarterly Q2_FY2026: `ending_cash` 13,934 labeled "…beginning of period" (it's the
  Q2 END balance → must read "…end of period").
- Annual FY2025: `cf_long_tail` 9,646 labeled "…beginning of period" (FY2025 END).

And the genuine "…beginning of period" row (prior period's ending balance) is absent.

## Design — Movement Analysis in the frontend renderer

Pure frontend (`useFinancialMatrix` / CF render). No parse, DB, adapter, or migration
change. The cash-reconciliation rows are rendered by movement-analysis rules, not by
the (wrong) stored `display_label`.

### Detection
A stored CF fact is a **cash-reconciliation balance** iff its `source_account` (XBRL
local name) is in a small allowlist of cash/restricted-cash reconciliation concepts
(`CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents`,
`CashCashEquivalents…IncludingDisposalGroupAndDiscontinuedOperations`,
`CashAndCashEquivalentsAtCarryingValue`, `RestrictedCash…`) — the same family the
parse instant-fallback already recognizes (`_is_cash_concept`). These rows carry an
instant value = the period-END balance, regardless of the (mislabeled) display_label.

### Rule 1 — relabel the stored row as "end of period"
For each column (period P), render the stored cash-balance fact with label
**"Cash, cash equivalents, and restricted cash at end of period"** and the period-END
ordinal (after `net_change_in_cash`), NOT the stored "beginning" label. (Date logic:
the stored instant's date == period_end → it is the ending balance per EFM movement
analysis.)

### Rule 2 — synthesize the "beginning of period" row
Add a row **"… at beginning of period"** whose value in column P = the **ending
cash-balance fact of the immediately-prior period** (same frequency lane):
- quarterly: beginning(Qn) = ending(Q n−1) (Q1 beginning = prior-FY Q4 ending).
- annual: beginning(FYn) = ending(FY n−1).
Place it ABOVE net_change / above the ending row, per PDF order (beginning →
net change → … → end). If the prior period's ending balance is absent (first period
in range), render the beginning cell empty (never invent / never subtract).

### Validation (EFM §9.7 "instant without matching duration", adapted)
Sanity check (dev-time / test): for each period, `beginning + net_change_in_cash
(+ fx_effect already inside net_change) == ending`. If it doesn't foot, log — do not
silently show mismatched begin/end. (MU 6M_FY2026: 9,646 + 4,288 = 13,934 ✓.)

## Scope / placement
- `useFinancialMatrix.buildMatrix` (PDF mode) + `buildDictionaryMatrix` (uni mode):
  both must apply the same movement-analysis transform to the cash rows so the toggle
  stays consistent. Factor the transform into one helper used by both.
- Frequency-aware: quarterly lane uses quarter periods; annual lane uses FY periods.
  (YTD facts remain excluded from the statement view — unchanged.)

## Alternatives (rejected)
- **Store begin+end twins (old Approach X):** violates EFM §6.8.12; invisible on YTD
  facts; needs a DB migration. Rejected on authority.
- **Fix stored display_label at the adapter (re-upsert):** a single stored label can't
  be both "end" (period P) and "beginning" (period P+1) — movement analysis is
  inherently a per-column render concern → must live in the renderer.

## Testing (TDD, vitest)
- movement-analysis helper: given cash instants per period, column P shows ending =
  instant(P) labeled "…end of period", beginning = instant(P−1); first period →
  beginning empty.
- relabel: a stored cash fact with display_label "…beginning of period" renders as
  "…end of period".
- footing: beginning(P) + net_change(P) == ending(P) for MU quarters/annual.
- toggle parity: pdf mode and uni mode both show corrected begin/end.
- tsc + existing vitest green.
- e2e (manual / DB-reproduction): MU quarterly Q2_FY2026 → end 13,934 + beginning
  9,732 (Q1 end); annual FY2025 → end 9,646 + beginning 7,052 (FY2024 end).

## Out of scope
- Issue A (gov-incentives mu: extension tag absent from companyfacts).
- Any parse / DB / adapter / migration change.
