---
type: design-spec
topic: cf-cash-movement-analysis
date: 2026-06-08
status: design (Codex round-1 folded; pending round-2)
tier: T2 (frontend render + a contained adapter relabel; no DB schema/migration)
branch: worktree-statement-view-pdf-faithful
authority: SEC EDGAR Financial Report Manual (EFM) via NLM "Topic - Parse_SEC_Filings",
  source a146d037 (EFM §6.7.4/§6.8.12/§7.7/§9.7). Supersedes abandoned "Approach X"
  (store begin/end twins — violates EFM §6.8.12).
---

# CF cash beginning/end — Movement Analysis

## Authority & bug (summary)

EFM §6.8.12: do NOT store separate begin/end concepts — one instant = ending(P) =
beginning(P+1). Vendors render this as **movement analysis** (§7.7): the renderer
shows the stored ending instant as ending(P) and as beginning(P+1); cash is an
instant → single-quarter beginning = prior quarter's ending instant (never subtract).

Bug (verified, visible): the cash-reconciliation concept is stored once per period as
the period-END balance (single-quarter → `uni=ending_cash`; YTD → `cf_long_tail`
[ytd, view-excluded]; FY → `cf_long_tail`), but its stored `display_label` is wrongly
"…at beginning of period" (resolver picked `matched[0]`=periodStart arc). And the
real "beginning" row is absent. Frontend shows: Q2_FY2026 ending_cash 13,934 and
FY2025 cf_long_tail 9,646 both mislabeled "…beginning of period".

## Design — folds all 9 Codex round-1 findings

Two layers, cleanly split (Codex P2 #5):
- **Adapter (upstream):** relabel the stored ending instant to "…end of period"
  (fix the objectively-wrong stored label). Re-upsert. Display metadata only — no
  schema/migration.
- **Frontend renderer (movement analysis):** synthesize the "…beginning of period"
  row cross-period; both happen via ONE pre-builder helper feeding both view modes.

### A. Adapter relabel (sec_json_adapter — worktree) [Codex P2 #5, P2 #7]
- Detect cash-reconciliation balance facts by a **source_account concept-family
  allowlist** (`CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents`,
  `…IncludingDisposalGroupAndDiscontinuedOperations`,
  `CashAndCashEquivalentsAtCarryingValue`, `RestrictedCash`).
- For such a fact (the stored value = period-END balance), force the display_label +
  ordinal to the **periodEndLabel** arc ("…at end of period", ordinal after
  net_change), overriding the `matched[0]` pick. **Fail-closed:** require exactly one
  cash-balance candidate per (period, lane); if >1 survive, log + leave unresolved
  (coverage gate catches), never guess.
- Re-upsert affected tickers → stored label is now correct; UI/DB no longer diverge.

### B. Pre-builder cash-movement helper (useFinancialMatrix — worktree) [Codex P1 #1, P1 #2, P2 #4, P2 #7, P2 #8]
A single helper consumes the **raw filtered `Cell[]`** (BEFORE either builder runs,
so neither pdf-rowId nor uni-dictionary collapse has happened) and returns, per
period column, a **cash-movement model**:
```
{ period, endingFact, beginningFact, fxFact, netChangeFact }
```
- `endingFact` = the one cash-balance fact for that period (by the concept-family
  allowlist above; exactly-one-per-period or the period is flagged, never summed).
  MUST be a DIRECT disclosed cash-balance fact — never `derived_q2/q3/q4`, never
  inferred from flow arithmetic (Codex P2 #8).
- `beginningFact` (synthetic) = the **exact predecessor period's** `endingFact`
  (Codex P2 #4): `Q2_FY2026→Q1_FY2026`, `Q1_FY2026→Q4_FY2025`, `FY2025→FY2024`,
  computed by period-name, requiring an EXACT match in the period set. If the
  predecessor is absent (first period / gap) → beginning cell **empty** (EFM: blank,
  never back-solve).
- Both `buildMatrix` (pdf) and `buildDictionaryMatrix` (uni) project this model into
  their own row systems (pdf: rowId rows; uni: canonical CF rows). The helper runs
  pre-builder so the annual `cf_long_tail` cash fact is not dropped before it is seen
  (Codex P1 #1: `buildDictionaryMatrix` skips non-`ROWS_BY_STATEMENT` keys).

### C. uni-mode canonical rows (constants.ts) [Codex r1 P1#1/P2#6/P2#9, r2 P2#1]
**Reuse approved keys — do NOT invent new `uni_account`s** (schema governance,
`financials-view-schema.md`; a new `cash_end_of_period` would duplicate the approved
`ending_cash` contract — Codex r2 #1):
- **End row** = the existing approved `ending_cash` uni (uni mode already maps an
  `ending_cash` fact to its CF_ROWS row; the movement model just supplies that fact).
- **FX row** = the existing approved FX cash key family (`fx_effect` / the checklist's
  registered fx-on-cash key) — add it to `CF_ROWS` (it is omitted today, Codex P2#9),
  keyed to the APPROVED uni, not a new one.
- **Beginning row** = a **frontend-only matrix row id** `cash_beginning_of_period`
  (NOT a `uni_account`, never stored / never upserted — it is a synthesized display
  row). Add it to `CF_ROWS` as a presentation-only row the movement model fills.
- Sort: beginning ABOVE `net_change_in_cash`; ending at the bottom (PDF order).

### D. Footing validation — concept-aware (Codex P1 #3)
Do NOT hardcode `beginning + net_change == ending`. The net-change concept family
differs across filers:
- `…PeriodIncreaseDecreaseIncludingExchangeRateEffect` → `ending − beginning ==
  net_change` (fx already inside; MU: 9,646 + 4,288 = 13,934 ✓; separate fx_effect=5
  is an informational sub-line).
- `…ExcludingExchangeRateEffect` → `ending − beginning == net_change + fx_effect`.
Pick the identity by the actual `net_change` source concept present that period; this
is a dev-time/test assertion + optional UI sanity log, not a hard render gate.

## Layer / placement summary
- adapter relabel: `Tools/research-tools/_shared/sec_json_adapter.py` (cash-family
  arc override) → re-upsert.
- pre-builder helper + projection: `app/components/financials-v2/useFinancialMatrix.ts`
  — `cashMovementModel(filtered, statement, frequency)` runs AFTER `filtered`/`periods`
  are computed and BEFORE the `viewMode` split (the shared call site); both builders
  project it.
- **sortOrdinal lives entirely in `useFinancialMatrix.ts` (Codex r2 #2):** add the
  optional field to the LOCAL `Matrix.rows` row shape defined in that file; the
  BUILDERS apply it when ordering (pdf sort + uni CF_ROWS placement). `types.ts` and
  `StatementMatrix.tsx` are NOT touched — `StatementMatrix` renders builder output in
  order and does not sort.
- canonical rows: `app/components/financials-v2/constants.ts` `CF_ROWS` (+ approved fx
  key row + frontend-only `cash_beginning_of_period` presentation row).

## Alternatives (rejected)
- Store begin/end twins (Approach X): violates EFM §6.8.12; needs migration; invisible
  on YTD. Rejected on authority.
- Frontend-only relabel of the base fact: leaves DB label wrong → UI/DB divergence
  (Codex P2 #5). Adapter owns the base fact's correct label.

## Testing (TDD, vitest + pytest)
- adapter (pytest): a cash-balance fact resolves to the periodEnd arc ("…end of
  period"); >1 candidate per period → fail-closed (unresolved, logged); non-cash rows
  unchanged.
- helper (vitest): `cashMovementModel` returns ending=instant(P), beginning=instant
  (exact predecessor); first-period/gap → beginning empty; never uses derived_q2/q3/q4.
- predecessor mapping: Q2→Q1, Q1→prior-FY-Q4, FY→FY-1 exact; nearest-visible NOT used.
- footing (concept-aware): MU 6M-equivalent quarters/annual — Including→`end−begin==
  net_change`; a synthetic Excluding fixture → `end−begin==net_change+fx`.
- toggle parity: pdf + uni both show beginning/end/fx in PDF order; sortOrdinal places
  synthetic rows; chart selectedKeys unaffected by synthetic rowIds.
- tsc + full vitest green.
- e2e (DB-reproduction): MU quarterly Q2_FY2026 → beginning 9,732 (Q1 end) + end
  13,934; annual FY2025 → beginning 7,052 (FY2024 end) + end 9,646; footing holds.

## Rollout (after Codex converge + tests green; production = user-auth)
dev TDD → Codex functional review (converge) → adapter relabel merged + re-upsert MU
(user-auth) → frontend movement-analysis → manual verify CF vs PDF (both modes) →
other tickers inherit on re-upsert.

## Out of scope
Issue A (gov-incentives mu: extension tag absent from companyfacts).
