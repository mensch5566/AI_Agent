# Codex Functional Review — derive-base Q2/Q3 reconstruction (P2.1)

**Gate**: ADR-001 review-before-prod. All code is committed + tested + dry-run-verified, but
**NOTHING is applied to production yet** (no migration, no `--apply`). This review must converge
before the migration + 5-ticker re-upsert. Frontend Build (PDF-faithful Statement view) waits behind this.

Reviewer: Codex (adversarial). Author: Claude. Debate to convergence — no performative agreement.

**Commits**: CC_Switch_Config `b4bc7af` (derive-base engine) + `0edbb38` (derive-analytics TTM);
AI_Agent `17209b2` (migration + frontend + docs + prototype tests).

---

## 0. The gap being closed (Codex P2.1, from the prior session review)

After the 2026-05-17 "YTD first-class" parse change, the parser stopped silently back-computing single
quarters and instead discloses 6M/9M YTD cumulatives. derive-base had **only Q4 rules** (`rules_q4`;
`derive_engine` emitted only `derived_q4`), so re-parsed YTD-CF tickers (INTC/AAOI/SNDK, and MU/LITE
which are also on the YTD contract) lost their **Q2/Q3 single-quarter IS/CF flows** (OCF / capex / D&A)
AND their **quarterly TTM analytics** for Q2/Q3-ending windows. This is a missing-row gap (no wrong
values). The contract "derive-base 靠 YTD 算 Q2/Q3/Q4" had only ever built Q4.

---

## 1. Change — derive-base `rules_q2q3.py` (NEW): Q2/Q3 single-quarter reconstruction

`q2q3_candidates(facts, *, skips_collector=None)` mirrors `rules_q4.q4_candidates`:

- **Q2 = 6M − Q1**, **Q3 = 9M − 6M** (single formula each, `rule_priority=1`, no fallback).
- `period_kind = derived_q2 / derived_q3`; `rule_id = Q2_6M_MINUS_Q1 / Q3_9M_MINUS_6M`.
- **Reuses the proven Q4 guards verbatim** (`_is_denied` / `_units_match` / `_concepts_match` /
  `_fy_year` imported from `rules_q4`) — GAAP only, IS/CF only, additive-USD-only allowlist (rejects
  per-share / ratios / share counts / `*_long_tail` buckets), concept + unit identity required across
  the two inputs, never emitted when the single quarter is already directly disclosed.
- `period_end` = minuend YTD's end (Q2←6M, Q3←9M); `period_start` = day-after subtrahend's end
  (Q2←Q1.end+1, Q3←6M.end+1). `source_account`/`xbrl_tag` carried from the YTD minuend (so Pass 3 can
  match it as a calc child). inputs = `[minuend, subtrahend]`.
- **`rules_q4.py` is byte-untouched** (zero regression risk to the proven Q4 path).

**Scrutinize**: (a) is importing the underscore-prefixed guards from `rules_q4` acceptable, or should
they be extracted to a shared module? (b) carrying concept identity from the *minuend* (6M for Q2, 9M
for Q3) — correct vs carrying from the subtrahend? (c) `_fy_year_any` accepts both `FY2024` and
`6M_FY2024`-style labels to discover the fiscal year from whichever rows exist — any label it
mis-parses?

## 2. Change — `derive_engine.py`: Pass 2 wiring + Pass 3 symmetry

- Pass 2 now runs `q4_candidates` **and** `q2q3_candidates`, both reading `facts_after_p1` (direct +
  Pass-1 identity) only → **Q2/Q3/Q4 are independent and never chain on one another** (the Q4=FY−Q1Q2Q3
  fallback still uses only directly-disclosed quarters, never derived Q2/Q3).
- Pass 3 identity filter widened `derived_q4` → `{derived_q2, derived_q3, derived_q4}` so subtotals
  (gross_profit, etc.) are derived on the new single quarters too (same tier as Q4). Direct quarters
  (`quarter_duration`) and YTD are excluded from Pass 3 as before (Pass 1 covered them).
- `stats`/result surface `q2q3_skips`; `audit.py` md renames Pass labels + merges Q2/Q3/Q4 skip
  diagnostics.

**Telescoping correctness (exact, no rounding)**: Q2=6M−Q1, Q3=9M−6M, Q4=FY−9M ⟹
Q1+Q2+Q3+Q4 = Q1+(6M−Q1)+(9M−6M)+(FY−9M) = FY; and Q1+Q2=6M, Q1+Q2+Q3=9M.

**Scrutinize**: (d) Pass 3 widening — could it emit a derived_q2/q3 subtotal that double-counts or
conflicts with the Pass-2 q2q3 output? (resolve_candidates dedupes by semantic key; static allowlist
skips when the parent is already present.) (e) any path where a derived_q2 input feeds a derived_q4
(unwanted chaining)? (claim: no — both read `facts_after_p1`, not each other.)

## 3. Change — derive-analytics `rules_crossperiod.py`: TTM single-quarter set (SCOPE EXPANSION)

**Discovered during dry-run**: the review framed P2.1 as a derive-base change, but
`_SINGLE_Q_KINDS = {"quarter_duration", "derived_q4"}` in derive-analytics did **not** include
`derived_q2/q3`. So even with derive-base producing Q2/Q3, the TTM numerator (trailing-4 single
quarters) would silently drop them → Q2/Q3-ending TTM ratios (ROE/ROA/ROIC/efficiency/
net_debt_to_ebitda) would still never compute. **The quarterly-TTM half of the gap needs this too.**

Fix: `_SINGLE_Q_KINDS += {derived_q2, derived_q3}`. Sound because the derived values are exact
(telescoping): TTM(Q3) = Q4_prev + Q1 + Q2 + Q3 = Q4_prev + 9M_FY (correct trailing-12-month). +2 tests
(index includes q2/q3; e2e mixed direct+derived TTM ROE). 125 derive-analytics tests pass.

**Scrutinize**: (f) is mixing direct `quarter_duration` and `derived_q2/q3` in one TTM sum ever
unsound (e.g. concept drift across the window)? (g) does adding q2/q3 change any **existing** TTM value,
or only add new windows? (author claim: value-preserving — a window that was computable before still
finds the same 4 quarters; only previously-uncomputable windows now emit. Also, where a quarter is now
`derived_q2` instead of the old parser's silent `quarter_duration`, the value is identical by
construction.)

## 4. Change — migration + enum/frontend/docs sync (NOT YET APPLIED)

- **`supabase/migrations/20260604120000_add_derived_q2_q3_metrics.sql`** — DROP+ADD
  `sfm_period_kind_check` to add `derived_q2`/`derived_q3` (metrics-only; facts/dimensional constraints
  untouched). **Constraint widening only — cannot corrupt existing rows. NOT YET APPLIED to prod.**
- `_shared/period_kind.py` `VALID_KINDS` (+docstring) — note: VALID_KINDS is doc-grade (not a runtime
  gate; the DB CHECK is the real gate; upsert does not validate against it).
- Frontend `types.ts` PeriodKind + `useFinancialMatrix.ts` `QUARTERLY_PKINDS_IS_CF` += derived_q2/q3
  (IS/CF + RATIO quarterly routing). `tsc --noEmit` clean.
- Docs: `sec-financials-v2-schema.md`, `financials-data-rules.md`, `financials-view-schema.md` enum
  tables.

## 5. Drift reconciliation (pre-work, committed)

derive-base's prototype (`tmp/derive-base/`, where the test harness lives) had drifted **behind**
canonical (`CC_Switch_Config/skills/derive-base/scripts/`) on 3 files (`rules_q4.py`/`audit.py`/
`derive_types.py` — canonical had Phase 3.4/3.5/3.6 audit-lineage features the prototype lacked).
Reconciled prototype→canonical first (forward sync, verified by the existing suite staying green), so
TDD ran on a faithful copy of production code and the final port prototype→canonical is byte-identical.
A stale e2e test (`test_intc_q4_uses_q1q2q3_fallback`) was corrected — INTC now has 9M YTD post-reparse,
so Q4 uses FY−9M (renamed `test_intc_q4_uses_fy_minus_9m`).

**(P3, flagged not done)**: derive-base is NOT yet migrated to the ADR-001 canonical-SSOT-with-tests
layout (derive-analytics is). Its tests still live in the prototype mirror. A separate cleanup.

---

## 6. Evidence

- **Tests**: derive-base prototype **86 passed** (69 baseline + 13 rules_q2q3 unit + 4 engine_q2q3);
  derive-analytics **125 passed** (+2). `tsc` clean.
- **Dry-run gates (all 5, read-only)**: 0 rejected / 0 conflicts / all identity unique. derive-base
  output rows: INTC 82 / AAOI 159 / SNDK 62 / MU 369 / LITE 367.
- **Local re-derive counts (derived_q2 / derived_q3)**: INTC 21/21, AAOI 33/34, SNDK 0/21, MU 89/76,
  LITE 91/95. (SNDK derived_q2=0 — flagged below, needs explanation before apply.)
- **Analytics row deltas after TTM fix**: INTC 75→77, MU 521→536 (new Q2/Q3 TTM windows); AAOI 278 /
  SNDK 53 / LITE 664 unchanged by the TTM fix (AAOI/SNDK chronic-loss → ROE/ROIC skip; LITE unchanged —
  to confirm).
- **INTC spot-check**: Q2_FY2025 OCF = 2050.0 = 6M(2863, SOURCE_OF_TRUTH) − Q1(813, SOURCE_OF_TRUTH),
  same xbrl_tag `NetCashProvidedByUsedInOperatingActivities`. Q3 OCF=2546, capex Q2/Q3=3550/2425, D&A
  Q2/Q3=3013/2992 — all `rule_id=Q2_6M_MINUS_Q1`/`Q3_9M_MINUS_6M`.

## 7. Verification items

**RESOLVED (investigated read-only, both correct — not bugs):**

1. **SNDK derived_q2 = 0** — CORRECT. SNDK (WD spin-off, Feb 2025) has no `Q1_FY2025` in parse (no
   standalone pre-spin Q1 financials); its OCF periods are `6M_FY2025 / 9M_FY2025 / FY2025 / Q1_FY2026`.
   Q2=6M−Q1 lacks Q1 → correct silent skip. Q3=9M−6M has both → 21 derived_q3 rows emitted. The
   missing-input guard behaving exactly as designed.
2. **LITE analytics unchanged by TTM fix (664→664)** — CORRECT, the fix is a no-op for LITE *by
   construction*. LITE discloses its TTM-driving metrics as **direct single quarters**: D&A has the full
   set Q1/Q2/Q3 (`quarter_duration`) + 6M/9M + FY (41 periods); net_income likewise direct. So LITE's
   roe/roa/roic/net_debt_to_ebitda TTM windows already computed from direct quarters (always in
   `_SINGLE_Q_KINDS`) before the fix → no new windows. LITE's 91/95 derived_q2/q3 are for *YTD-only*
   line items (where no direct quarter is disclosed); for D&A (direct exists) q2q3_candidates correctly
   SKIPs (never overrides a disclosed quarter), so no duplicate/conflict. Confirms the
   "never emitted when already direct" guard + the additive-only property hold on a mixed-disclosure
   ticker. Both `_index_flows` (IS) and `_index_cf_flows` (CF) share the one `_SINGLE_Q_KINDS`, so
   net_debt_to_ebitda's inline EBITDA D&A summation is covered by the same one-line fix (no missed path).

**STILL OPEN (close right after apply):**

3. **Additivity empirical check** — after apply, spot-check ≥1 pre-existing derived_q4 value and ≥1
   pre-existing annual analytics value are unchanged vs the prior DB (logical proof in §2/§3; want
   empirical confirmation for T3).
4. Frontend visual: Q2/Q3 single-quarter CF flows + quarterly TTM ratios render correctly (deferred to
   the frontend Build / preview).

## 8. Ask

Confirm Changes 1–4 are production-correct or list P1/P2. On convergence: apply migration → re-upsert
all 5 (`--apply`, per-write authorization) → empirical additivity check → close P2.1. Then P2.2
(fy_end_month fail-closed) → frontend Build.
