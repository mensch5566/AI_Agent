**Findings**

No P1/P2 findings remain after checking the v3 folds against the current repo.

P3: [2026-06-08-statement-view-mode-toggle-design.md](</Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/docs/superpowers/specs/2026-06-08-statement-view-mode-toggle-design.md:26>) still says uni mode is `main`’s prior `buildMatrix`, while the verified implementation path is the existing in-worktree dictionary builder at [useFinancialMatrix.ts](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/components/financials-v2/useFinancialMatrix.ts:361). The later sections already say the right thing at [spec line 41](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/docs/superpowers/specs/2026-06-08-statement-view-mode-toggle-design.md:41) and [line 52](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/docs/superpowers/specs/2026-06-08-statement-view-mode-toggle-design.md:52). This is editorial, not a blocker.

**Round-2 fold checks**

1. Correct. `METRIC_ONLY_UNI` currently contains `ebitda`, `adjusted_ebitda`, `free_cash_flow` at [useFinancialMatrix.ts](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/components/financials-v2/useFinancialMatrix.ts:117). `IS_ROWS` still contains raw `ebitda` and `CF_ROWS` still contains raw `free_cash_flow` at [constants.ts](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/components/financials-v2/constants.ts:54) and [constants.ts](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/components/financials-v2/constants.ts:119), so the uni builder does need that filter. It is a true no-op for `RATIO`, because `RATIO_ROWS` has only ratio keys and no raw `ebitda`/`free_cash_flow` key at [constants.ts](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/components/financials-v2/constants.ts:132). Suppressing them inline does not hide them entirely, because the separate derived section is built by `buildDerivedNonGaapRows` and rendered on the Ratios tab at [Viewer.tsx](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/financials/[ticker]/Viewer.tsx:52) and [Viewer.tsx](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/financials/[ticker]/Viewer.tsx:257).

2. Correct. The proposed mount-read plus `if (!hydrated) return` persist guard is the right fix for this component shape. Current `Viewer` has no localStorage logic yet and computes matrices directly from local state at [Viewer.tsx](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/financials/[ticker]/Viewer.tsx:41). I do not see a stale-closure issue in the proposed read effect, and `hydrated` not resetting on ticker navigation is consistent with the stated global-scope behavior.

3. Correct. The wording fix for `SEGMENT` matches code reality: `view === "SEGMENT"` still aliases `statement` to `"IS"` at [Viewer.tsx](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/financials/[ticker]/Viewer.tsx:39), but the UI renders `SegmentDashboard`, not `StatementMatrix`, at [Viewer.tsx](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/financials/[ticker]/Viewer.tsx:237). So “not user-visible” is the precise description.

**New-issue scan**

The arity change is safe if implemented exactly as specified: add `viewMode` as an optional/defaulted 5th parameter. All current call sites and tests still use the 4-arg form at [Viewer.tsx](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/financials/[ticker]/Viewer.tsx:42) and [useFinancialMatrix.test.ts](/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful/app/components/financials-v2/__tests__/useFinancialMatrix.test.ts:89), so a required 5th arg would break them, but the spec already says default `'pdf'`, which avoids that.

**Verdict**

CONVERGED (ready for implementation).

No substantive P1/P2 blockers remain. Residual work is the expected implementation/test discipline the spec already names: uni-mode matrix tests, long-tail SUM sign regression coverage, and chart-reset coverage.