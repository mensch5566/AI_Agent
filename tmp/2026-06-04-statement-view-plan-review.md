# Plan-gate Review — Statement View PDF-faithful display (revalidated against post-P2.1 data layer)

**Why this doc**: the implementation plan `docs/superpowers/plans/2026-06-04-statement-view-pdf-faithful-display.md`
(16 tasks / 8 phases, spec v5) was written BEFORE P2.1/P2.2 shipped. Before executing it in a worktree we
revalidated it against the now-current backend data layer. This is the plan/design gate review — the plan
has NOT been executed yet (no worktree, no code).

Reviewer: Codex (adversarial). Author: Claude.

**Read**:
- Plan: `docs/superpowers/plans/2026-06-04-statement-view-pdf-faithful-display.md`
- Spec: `docs/superpowers/specs/2026-06-04-statement-view-pdf-faithful-display.md` (v5)

---

## 1. Data-layer delta since the plan was written (what changed under the plan)

P2.1 (shipped to production 2026-06-04) + P2.2 changed the backend the plan sits on:

- `sec_financial_metrics` now carries **`derived_q2` / `derived_q3`** single-quarter IS/CF rows
  (Q2=6M−Q1, Q3=9M−6M), not only `derived_q4`. Migration `20260604120000_add_derived_q2_q3_metrics.sql`
  is **already applied** (period_kind CHECK now allows derived_q2/q3).
- `app/components/financials-v2/useFinancialMatrix.ts` `QUARTERLY_PKINDS_IS_CF` already routes
  `derived_q2/q3/q4` into the quarterly IS/CF view; `docs/financials-data-rules.md` §quarterly IS/CF and
  the schema enum tables were updated to match.
- derive-analytics EL1 (FCF/EBITDA) now also emits at derived_q2/q3 periods; TTM (`net_debt_to_ebitda`)
  gained Q2/Q3-spanning windows. (These are metric rows, rendered via the same single-quarter attach.)
- P2.2: parse-SEC-supplement fy_end_month resolver is fail-closed (orthogonal to this plan; noted for
  completeness).

## 2. Plan changes made in response (Codex round-1 finding accepted)

Codex flagged that the plan still scoped the statement-row attach around `derived_q4` only, while the new
contract is `derived_q2 ∪ derived_q3 ∪ derived_q4`. Verified true and generalized the plan:

- **File map** (useFinancialMatrix.ts row): "derived_q4 attach" → "derived single-quarter
  `derived_q2/q3/q4` attach".
- **Task 8 Step 1** (adapter test fixture): "a derived_q4 metric" → "derived single-quarter metrics
  derived_q2/q3/q4".
- **Task 11 Step 1** (buildMatrix vitest): the derived-cell-attaches-by-uni_account assertion now
  requires **all three** (Q2/Q3/Q4) attach into the quarterly view (cross-referenced to
  `QUARTERLY_PKINDS_IS_CF` + data-rules), and the display-ineligible-synthetic guard now says "none of
  derived_q2/q3/q4 pulls it back".
- **Self-Review**: added a "Data-layer delta" bullet documenting the above + that the resolver / classifier
  / NLM-order / coverage-gate / formatter tasks are **orthogonal** (they operate on FACTS display metadata,
  not the derived-metric period_kind), so only Tasks 8 & 11 needed the generalization.

The plan body otherwise stays clean/executable (no review prose mixed in).

## 3. Author's full-plan revalidation (beyond the one finding)

Walked all 16 tasks against the new data layer:

- **Task 1 migration** `2026060500_add_display_label.sql` (facts.display_label) — independent column,
  no interaction with the metrics period_kind migration. Naming sorts after existing migrations. OK.
- **Tasks 2–5 classifier/resolver** — operate on `source_account` / labels.json / edges_pre of FACTS;
  the derived_q2/q3 change is in METRICS, not facts. Orthogonal. OK.
- **Tasks 6–7 NLM ordering (AAOI BS/CF)** — facts ordering only. Orthogonal. OK.
- **Task 9 coverage gate** — denominator = display-eligible FACTS rows (excludes metric-only). derived_q2/q3
  are metric rows → correctly excluded from the gate denominator (same as derived_q4 today). OK.
- **Task 11 buildMatrix** — the integration point; generalized (above).
- **Task 13 DERIVED_NONGAAP_ABSOLUTE_ROWS** (ebitda/fcf) — reads the IS ebitda + CF fcf metric rows
  regardless of period_kind; with derived_q2/q3 these now also have Q2/Q3-period instances, which Task 11's
  quarterly routing handles. No Task 13 change needed. OK.
- **Task 14 rollout re-upsert** — this re-upserts FACTS (display_label/ordinal); "existing values
  unchanged" still holds for facts. Independent of the metrics re-upsert P2.1 already did. OK.

## 4. Scrutinize (open questions for Codex)

1. Is generalizing only Tasks 8 & 11 sufficient, or is there a derived-single-quarter touch-point in the
   resolver/gate path I'm missing? (Author claim: derived metrics never carry display_label/ordinal —
   they render by uni_account attach to a fact prototype — so the resolver/gate are fact-only.)
2. Task 1's new migration adds `display_label` to `sec_financial_facts`; Task 14 re-upserts facts for all
   5 tickers. Any risk that re-upserting facts disturbs the P2.1 metrics rows? (Author claim: different
   tables / different scope; metrics untouched by the facts upsert path.)
3. The plan assumes `scripts/apply_migration.py` may not exist and falls back to the Management-API path
   (which we just used successfully for `20260604120000`). Acceptable, or should the plan hard-specify the
   Management-API apply step?

## 5. Ask

Confirm the plan is execution-ready under the post-P2.1 data layer, or list plan-gate P1/P2. On
convergence: open the worktree and execute via subagent-driven-development.
