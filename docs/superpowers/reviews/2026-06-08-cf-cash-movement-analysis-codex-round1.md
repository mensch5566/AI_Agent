**Findings**

1. **P1 — annual `uni` mode cannot implement this design as written because the underlying cash-end row is dropped before any helper can see it.**  
`buildDictionaryMatrix()` only renders keys present in `ROWS_BY_STATEMENT[statement]` and skips every cell whose `uni_account` is not in that fixed row list ([useFinancialMatrix.ts](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/components/financials-v2/useFinancialMatrix.ts:378), [useFinancialMatrix.ts](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/components/financials-v2/useFinancialMatrix.ts:390), [constants.ts](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/components/financials-v2/constants.ts:103)). `CF_ROWS` contains `ending_cash`, but not `cf_long_tail` or `fx_effect` ([constants.ts](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/components/financials-v2/constants.ts:103)). Your authority fact pattern says annual ending cash lives in `cf_long_tail`, so `uni` annual mode currently drops that fact entirely before parity logic runs.  
**Resolution:** blocker. Either add explicit semantic CF rows for annual cash movement to `CF_ROWS`, or run a pre-builder normalization step that maps qualifying cash-balance/fx facts onto stable semantic keys before `buildDictionaryMatrix()`.

2. **P1 — the spec’s “shared helper for pdf + uni” is only feasible pre-builder, not post-builder.**  
PDF mode keys rows by `rowId` (`uni_account` or `uni_account|source_account`) and is data-driven ([useFinancialMatrix.ts](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/components/financials-v2/useFinancialMatrix.ts:138), [useFinancialMatrix.ts](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/components/financials-v2/useFinancialMatrix.ts:260)). `uni` mode is fixed-dictionary and long-tail-summing ([useFinancialMatrix.ts](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/components/financials-v2/useFinancialMatrix.ts:369)). If you wait until after matrix build, pdf mode still knows the long-tail member identity, but `uni` mode has already collapsed or discarded it.  
**Resolution:** shared helper should consume raw filtered `Cell[]` and emit a normalized “cash movement model” per period: `{ endingCandidate, beginningSynthetic, fxCandidate, netChangeCandidate }`, then each builder projects that model into its own row system.

3. **P1 — “fx already inside net_change” is not a safe invariant; the proposed footing test encodes the wrong contract.**  
The spec hardcodes `beginning + net_change == ending` and says `fx_effect` is already inside `net_change` ([design spec](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/docs/superpowers/specs/2026-06-08-cf-cash-movement-analysis-design.md:77)). But the code/schema already recognize a separate FX cash row family: `fx_effect_on_cash` exists in the checklist, while CF row dictionaries only list `net_change_in_cash` and `ending_cash` as separate concepts ([docs/financials-core-checklist.md](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/docs/financials-core-checklist.md:313), [docs/sec-financials-v2-schema.md](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/docs/sec-financials-v2-schema.md:226), [constants.ts](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/components/financials-v2/constants.ts:125)). Across filers, some tags include FX in the delta and some present FX separately.  
**Resolution:** the generic validation must be concept-aware, not arithmetic-only. Accept either:
- `ending - beginning == net_change`, or
- `ending - beginning == net_change + fx_effect`,
based on the actual source concept family present for that period.  
MU-specific test can assert the verified MU identity, but the implementation contract must not generalize that identity blindly.

4. **P2 — cross-period lookup must use the exact predecessor period, not the previous visible column.**  
Periods are whatever survives current statement/frequency/version filtering, then sorted with `comparePeriods()` ([useFinancialMatrix.ts](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/components/financials-v2/useFinancialMatrix.ts:193), [useFinancialMatrix.ts](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/components/financials-v2/useFinancialMatrix.ts:231), [constants.ts](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/components/financials-v2/constants.ts:346)). If a quarter is missing from the filtered set, “previous visible period” is not necessarily “immediately prior fiscal period”. EFM supports blank, not back-solving, so a gap must yield empty beginning.  
**Resolution:** helper should compute predecessor by period name (`Q2_FY2026 -> Q1_FY2026`, `Q1_FY2026 -> Q4_FY2025`, `FY2025 -> FY2024`) and require an exact match. No fallback to “nearest earlier column”.

5. **P2 — the design rejects an adapter fix too broadly; the stored label for the fact itself is objectively wrong and should be corrected upstream.**  
Today pdf-mode row labels are denormalized from the latest-period prototype fact ([useFinancialMatrix.ts](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/components/financials-v2/useFinancialMatrix.ts:261), [useFinancialMatrix.ts](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/components/financials-v2/useFinancialMatrix.ts:293), [useFinancialMatrix.ts](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/components/financials-v2/useFinancialMatrix.ts:355)). So the DB-stored wrong label directly contaminates UI/debugging. The spec’s rejection is correct for the synthesized beginning row, but not for the base fact’s own label when displayed in its own period ([design spec](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/docs/superpowers/specs/2026-06-08-cf-cash-movement-analysis-design.md:90)).  
**Resolution:** split the problem:
- adapter/upsert should relabel the stored instant fact as `...end of period`;
- renderer should synthesize `...beginning of period` cross-period.  
That reduces UI/DB divergence and makes future audits less confusing.

6. **P2 — the synthetic beginning row needs an explicit transient sort contract; overloading raw ordinals is fragile.**  
PDF rows sort purely by numeric `ordinal`; `uni` rows sort by `CF_ROWS` order ([useFinancialMatrix.ts](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/components/financials-v2/useFinancialMatrix.ts:301), [useFinancialMatrix.ts](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/components/financials-v2/useFinancialMatrix.ts:465), [constants.ts](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/components/financials-v2/constants.ts:103)). A synthetic row needs to sit above `net_change_in_cash`; the ending row needs to remain below it. Using fake fractional ordinals in the same field is workable but semantically muddy.  
**Resolution:** add transient row-level sort metadata in the matrix model, e.g. `sortOrdinal`, instead of pretending the synthetic row has a real filing ordinal. In `uni` mode, update `CF_ROWS` to include the synthetic beginning row explicitly in canonical order.

7. **P2 — cash-balance detection should be fail-closed per period, and `source_account` is the safer key than `uni_account`.**  
In pdf mode, annual cash end may be a long-tail member, so `uni_account=cf_long_tail` is too coarse; many unrelated long-tail members can share it ([useFinancialMatrix.ts](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/components/financials-v2/useFinancialMatrix.ts:129), [useFinancialMatrix.ts](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/components/financials-v2/useFinancialMatrix.ts:138)). The spec’s source-account allowlist is directionally right.  
**Resolution:** detect cash-balance candidates by `source_account`/concept-family allowlist, then require exactly one match per period per lane. If multiple candidates survive, log/fail that period rather than guessing or summing.

8. **P2 — derived-quarter CF interaction needs a stricter rule than the spec states.**  
Quarterly CF mode allows `derived_q2/q3/q4` metrics into the lane ([useFinancialMatrix.ts](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/components/financials-v2/useFinancialMatrix.ts:87), [useFinancialMatrix.ts](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/components/financials-v2/useFinancialMatrix.ts:335)). But cash ending balance is an instant-style reconciliation anchor, not something derive-base should synthesize from YTD flow metrics.  
**Resolution:** movement-analysis helper must only use direct disclosed cash-balance facts for ending/beginning rows. Never source those rows from `derived_q2/q3/q4`, and never infer them from flow arithmetic.

9. **P2 — toggle parity has an existing schema/UI mismatch beyond the cash fix: `fx_effect` is not in `CF_ROWS`.**  
Even before this change, `uni` mode cannot show `fx_effect` because the canonical CF dictionary omits it ([constants.ts](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/components/financials-v2/constants.ts:103), [useFinancialMatrix.ts](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/components/financials-v2/useFinancialMatrix.ts:391)). So the spec’s “toggle parity” claim is incomplete.  
**Resolution:** if parity is a requirement, include `fx_effect` in the canonical `uni` CF view or explicitly narrow the parity claim to begin/end only.

**Per-question judgment**

1. Cross-period lookup: **real risk, P2**. Empty on first/gap is correct; but only if predecessor matching is exact, not nearest visible.
2. Cash-row identification: **real risk, P1**. Use `source_account` concept-family allowlist plus exact-one-per-period guard; `uni_account` is insufficient in annual/pdf mode.
3. Relabel divergence: **real risk, P2**. Frontend-only override works, but cleaner is adapter fix for the stored ending label plus renderer-only synthetic beginning.
4. Ordinal/order: **real risk, P2**. Needs transient sort metadata or explicit canonical row insertion; do not hand-wave ordinal collisions.
5. Toggle parity/shared helper: **real risk, P1**. Shared helper must be pre-builder; post-builder parity is not defensible.
6. Footing validation: **real risk, P1**. Generic identity cannot assume FX is already inside `net_change`.
7. Derived single-quarter interaction: **real risk, P2**. Beginning/end rows must come only from direct cash-balance facts, never from derived CF flows.

**Verdict**

Not ready for implementation yet. Remaining blockers are:

- `uni` annual mode has no viable cash-end row path today (`cf_long_tail` dropped).
- The proposed shared helper is placed at the wrong abstraction level unless it runs pre-builder.
- The footing rule is overclaimed and would encode a false accounting invariant across filers.

If those three are fixed in the design, the rest are implementable as P2 refinements rather than blockers.