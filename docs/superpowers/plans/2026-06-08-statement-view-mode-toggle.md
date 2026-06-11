# Statement View-Mode Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single global toggle that switches the Financials Viewer IS/BS/CF tables between PDF-faithful mode (current data-driven `buildMatrix`) and uni_account mode (existing `buildDictionaryMatrix`).

**Architecture:** Reuse the in-worktree `buildDictionaryMatrix` (today RATIO-only) for uni mode; add a `viewMode` param to `buildMatrix` that routes IS/BS/CF to it; add a persisted `viewMode` state + toggle UI in `Viewer.tsx`. Render shell (`StatementMatrix`) is untouched, so both modes inherit the PDF number formatter + `display_negated` sign logic. Two correctness fixes ride along inside `buildDictionaryMatrix`: suppress `METRIC_ONLY_UNI` rows (no inline EBITDA/FCF — they live on the Ratios tab) and clear `display_negated` on synthetic long-tail SUM cells (latent sign bug).

**Tech Stack:** Next.js (App Router) + React + TypeScript; vitest; `tsc --noEmit`.

**Spec:** `docs/superpowers/specs/2026-06-08-statement-view-mode-toggle-design.md` (design-converged, 3 Codex rounds).

**Working dir:** `~/AI_Agent/.claude/worktrees/statement-view-pdf-faithful` (branch `worktree-statement-view-pdf-faithful`). Run all commands from there.

---

## File Structure

- `app/components/financials-v2/useFinancialMatrix.ts` — Modify: `buildDictionaryMatrix` (METRIC_ONLY_UNI filter + SUM `display_negated: null`); `buildMatrix` (new `viewMode` param + uni routing).
- `app/financials/[ticker]/Viewer.tsx` — Modify: `viewMode` state + localStorage hydration + chart-reset effect + toggle UI + pass `viewMode` to `buildMatrix`.
- `app/components/financials-v2/__tests__/useFinancialMatrix.test.ts` — Modify: add uni-mode, METRIC_ONLY_UNI-suppression, and SUM-sign tests.
- `app/components/financials-v2/StatementMatrix.tsx` — UNCHANGED.

---

## Task 1: `buildDictionaryMatrix` — suppress METRIC_ONLY_UNI + fix SUM sign

**Files:**
- Modify: `app/components/financials-v2/useFinancialMatrix.ts` (`buildDictionaryMatrix`, ~line 361 and the synthetic SUM cell ~line 405-430)
- Test: `app/components/financials-v2/__tests__/useFinancialMatrix.test.ts`

- [ ] **Step 1: Write failing tests**

Add to `useFinancialMatrix.test.ts` (adapt the existing `makeCell`/fixture helpers in that file for shape):

```ts
import { buildDictionaryMatrix } from "../useFinancialMatrix"; // export it (Step 3a)

test("uni: METRIC_ONLY_UNI keys (ebitda) never become an IS row", () => {
  const cells = [
    makeCell({ uni_account: "revenue", statement: "IS", period: "Q2_FY2026", value: 100 }),
    makeCell({ uni_account: "ebitda", statement: "IS", period: "Q2_FY2026", value: 40 }),
  ];
  const m = buildDictionaryMatrix(cells, "IS", ["Q2_FY2026"]);
  expect(m.rows.some((r) => r.key === "ebitda")).toBe(false);
  expect(m.rows.some((r) => r.key === "revenue")).toBe(true);
});

test("uni: long-tail SUM cell clears display_negated so the bucket keeps natural summed sign", () => {
  // two long-tail members rolling into the same bucket; first child is negated
  const cells = [
    makeCell({ uni_account: "operating_expense_long_tail", source_account: "A",
               statement: "IS", period: "Q2_FY2026", value: 10, weight: 1, display_negated: true }),
    makeCell({ uni_account: "operating_expense_long_tail", source_account: "B",
               statement: "IS", period: "Q2_FY2026", value: 5, weight: 1, display_negated: false }),
  ];
  const m = buildDictionaryMatrix(cells, "IS", ["Q2_FY2026"]);
  const cell = m.cells["operating_expense_long_tail"]?.["Q2_FY2026"] as any;
  expect(cell.value).toBe(15);
  expect(cell.display_negated).toBeNull();
});
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `npx vitest run app/components/financials-v2/__tests__/useFinancialMatrix.test.ts -t "uni:"`
Expected: FAIL — `buildDictionaryMatrix` not exported / `ebitda` row present / `display_negated` not null.

- [ ] **Step 3a: Export `buildDictionaryMatrix`**

In `useFinancialMatrix.ts`, change `function buildDictionaryMatrix(` → `export function buildDictionaryMatrix(`.

- [ ] **Step 3b: Add METRIC_ONLY_UNI filter**

In `buildDictionaryMatrix`, immediately after `const rows = ROWS_BY_STATEMENT[statement];`, replace with:

```ts
  // ebitda / free_cash_flow are DERIVED (never on a filing's face statements);
  // they render only in the Ratios-tab DerivedNonGaap subsection, so never inline
  // here. Matches the PDF path (METRIC_ONLY_UNI). No-op for RATIO (no such raw key).
  const rows = ROWS_BY_STATEMENT[statement].filter((r) => !METRIC_ONLY_UNI.has(r.key));
```

- [ ] **Step 3c: Clear `display_negated` on the synthetic SUM cell**

In `buildDictionaryMatrix`'s long-tail SUM cell (`const synthetic: Cell = { ...base, … }`), add `display_negated: null,` to the synthetic object literal (next to `xbrl_tag: null`):

```ts
      const synthetic: Cell = {
        ...base,
        uni_account: k,
        source_account: children.length === 1 ? base.source_account : "SUM(long_tail)",
        xbrl_tag: null,
        display_negated: null, // bucket sign = summed sign; never inherit a child's flag
        value: summed,
        weight: 1,
        // …provenance unchanged…
```

- [ ] **Step 4: Run tests, verify pass**

Run: `npx vitest run app/components/financials-v2/__tests__/useFinancialMatrix.test.ts -t "uni:"`
Expected: PASS (both).

- [ ] **Step 5: Commit**

```bash
git add app/components/financials-v2/useFinancialMatrix.ts app/components/financials-v2/__tests__/useFinancialMatrix.test.ts
git commit -m "feat(view-mode): export buildDictionaryMatrix; suppress METRIC_ONLY_UNI inline + clear SUM display_negated (Codex P1s)"
```

---

## Task 2: `buildMatrix` — `viewMode` param routes IS/BS/CF to uni builder

**Files:**
- Modify: `app/components/financials-v2/useFinancialMatrix.ts` (`buildMatrix`, signature ~line 170; the IS/BS/CF return path)
- Test: `app/components/financials-v2/__tests__/useFinancialMatrix.test.ts`

- [ ] **Step 1: Write failing test**

```ts
test("buildMatrix viewMode='uni' yields fixed canonical rows; 'pdf' yields data-driven rows", () => {
  const cells = [
    makeCell({ uni_account: "revenue", source_account: "Revenues", statement: "IS",
               period: "Q2_FY2026", value: 100, display_label: "Net sales", ordinal: 1 }),
  ];
  const uni = buildMatrix(cells, "IS", "GAAP", "quarterly", "uni");
  const pdf = buildMatrix(cells, "IS", "GAAP", "quarterly", "pdf");
  // uni rows come from IS_ROWS (fixed canonical labels keyed by uni_account)
  expect(uni.rows.some((r) => r.key === "revenue" && r.label === "Revenue")).toBe(true);
  // pdf rows are data-driven (label from display_label)
  expect(pdf.rows.some((r) => r.label === "Net sales")).toBe(true);
});

test("buildMatrix defaults to pdf when viewMode omitted (back-compat arity)", () => {
  const cells = [makeCell({ uni_account: "revenue", source_account: "Revenues", statement: "IS",
                            period: "Q2_FY2026", value: 100, display_label: "Net sales", ordinal: 1 })];
  const def = buildMatrix(cells, "IS", "GAAP", "quarterly");
  expect(def.rows.some((r) => r.label === "Net sales")).toBe(true);
});
```

- [ ] **Step 2: Run test, verify it fails**

Run: `npx vitest run app/components/financials-v2/__tests__/useFinancialMatrix.test.ts -t "viewMode"`
Expected: FAIL — `buildMatrix` takes 4 args / uni path not wired.

- [ ] **Step 3: Add `viewMode` param + routing**

In `buildMatrix` signature, add a 5th defaulted param:

```ts
export function buildMatrix(
  cells: Cell[],
  statement: Statement,
  version: Version,
  frequency: Frequency,
  viewMode: "pdf" | "uni" = "pdf",
): Matrix {
```

After the shared cell filtering + `periods` computation, and BEFORE the data-driven PDF row-building block for IS/BS/CF, insert:

```ts
  // uni_account mode: route the three statements through the fixed-dictionary
  // builder (RATIO already uses it below, unchanged).
  if (statement !== "RATIO" && viewMode === "uni") {
    return buildDictionaryMatrix(filtered, statement, periods);
  }
```

(Place it right after `const periods = …` and the existing `if (statement === "RATIO") return buildDictionaryMatrix(...)` line, so RATIO still returns first and PDF logic is untouched.)

- [ ] **Step 4: Run test, verify pass**

Run: `npx vitest run app/components/financials-v2/__tests__/useFinancialMatrix.test.ts -t "viewMode"`
Expected: PASS (both).

- [ ] **Step 5: Run full vitest + tsc**

Run: `npx vitest run && npx tsc --noEmit`
Expected: all pass; tsc exit 0. (Existing 4-arg `buildMatrix` callers still compile via the default.)

- [ ] **Step 6: Commit**

```bash
git add app/components/financials-v2/useFinancialMatrix.ts app/components/financials-v2/__tests__/useFinancialMatrix.test.ts
git commit -m "feat(view-mode): buildMatrix viewMode param routes IS/BS/CF to uni builder (default pdf, back-compat)"
```

---

## Task 3: `Viewer.tsx` — viewMode state, persistence, chart reset, toggle UI

**Files:**
- Modify: `app/financials/[ticker]/Viewer.tsx`

- [ ] **Step 1: Add state + hydration-safe persistence**

Near the other `useState` calls (`view`, `frequency`, `showNonGaap`), add:

```tsx
  const [viewMode, setViewMode] = useState<"pdf" | "uni">("pdf");
  const [modeHydrated, setModeHydrated] = useState(false);

  // Read persisted mode once on mount (App Router: never read localStorage in the
  // useState initializer — SSR has no window).
  useEffect(() => {
    const saved = typeof window !== "undefined"
      ? window.localStorage.getItem("fin-view-mode-v1") : null;
    if (saved === "pdf" || saved === "uni") setViewMode(saved);
    setModeHydrated(true);
  }, []);

  // Persist — guarded so the initial 'pdf' render never overwrites a stored 'uni'
  // before the read effect commits.
  useEffect(() => {
    if (!modeHydrated) return;
    window.localStorage.setItem("fin-view-mode-v1", viewMode);
  }, [viewMode, modeHydrated]);
```

- [ ] **Step 2: Pass `viewMode` to the GAAP matrix build**

Change the GAAP matrix memo (the `buildMatrix(cells, statement, "GAAP", frequency)` call) to:

```tsx
  const matrix = useMemo(
    () => buildMatrix(cells, statement, "GAAP", frequency, viewMode),
    [cells, statement, frequency, viewMode],
  );
```

(Leave the NON_GAAP `buildMatrix(cells, statement, "NON_GAAP", frequency)` memo as-is — the Non-GAAP overlay stays PDF/default; uni mode applies to the primary GAAP grid. If the NON_GAAP overlay column visibly diverges in manual check, revisit — but spec scope is the GAAP statement grid.)

- [ ] **Step 3: Reset chart selection on mode switch**

Find the existing effect that resets `selectedKeys` on `statement` change (deps `[statement]`, sets `selectedKeys` to `CHART_DEFAULT_KEYS[statement]`). Add `viewMode` to its dependency array so switching modes also re-applies the preset (uni keys = uni_account, pdf keys = rowId; stale keys would null the chart):

```tsx
  }, [statement, viewMode]);
```

- [ ] **Step 4: Add the toggle UI (only on IS/BS/CF)**

Near the frequency (quarterly/annual) control, render the 2-segment toggle gated on `view`:

```tsx
  {(view === "IS" || view === "BS" || view === "CF") && (
    <div className="inline-flex rounded-md border" role="group" aria-label="view mode">
      {([["pdf", "依財報"], ["uni", "標準科目"]] as const).map(([m, label]) => (
        <button
          key={m}
          type="button"
          aria-pressed={viewMode === m}
          onClick={() => setViewMode(m)}
          className={viewMode === m ? "px-3 py-1 bg-red-600 text-white" : "px-3 py-1"}
        >
          {label}
        </button>
      ))}
    </div>
  )}
```

(Match the existing quarterly/annual toggle's exact class names / component for visual consistency — mirror that block's styling rather than the placeholder classes above.)

- [ ] **Step 5: tsc + vitest**

Run: `npx tsc --noEmit && npx vitest run`
Expected: tsc exit 0; all tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/financials/[ticker]/Viewer.tsx
git commit -m "feat(view-mode): Viewer toggle (依財報/標準科目) — persisted, hydration-safe, chart-reset on switch, IS/BS/CF only"
```

---

## Task 4: Manual verification + Codex functional review

- [ ] **Step 1: Start the worktree dev server** (via preview_start `worktree-financials`, port 3000) and open `/financials/MU`.

- [ ] **Step 2: Manual checklist**
  - Toggle visible on IS/BS/CF; hidden on Ratios + Segment/Geo.
  - `標準科目` (uni): IS/BS/CF show fixed canonical rows (e.g. "Cash & Equivalents", "Accounts Receivable") + `Other … (long-tail)` bucket rows; NO inline EBITDA/Free Cash Flow row.
  - `依財報` (pdf): MU's own labels/order (e.g. "Receivables", "Long-term debt"); signs correct (Treasury `(8,502)`, Interest expense `(32)`).
  - Number format `5,985` (not `5985.0M`) in both modes.
  - Switch modes → chart resets to the statement preset, no all-null/blank chart.
  - Reload page → last-selected mode restored from localStorage.

- [ ] **Step 3: Codex functional review (GPT-5.5, converge-to-clean)**

Run `codex exec -C <worktree> -s read-only -o <out> "<review ask>" < /dev/null` over the diff (`git diff main...HEAD` for the 3 files). Ask it to challenge: the viewMode routing, METRIC_ONLY_UNI filter correctness (RATIO no-op), SUM `display_negated: null`, the localStorage race/guard, chart-reset effect deps, and any NEW issue. Scrutinize each finding (verify in code — do not rubber-stamp), fold real ones, re-run until a round returns no new P1/P2.

- [ ] **Step 4: Final commit / handoff** after convergence; update STATUS if warranted; this branch's `finishing-a-development-branch` is handled separately (merge decision is the user's).

---

## Self-Review (done)

- **Spec coverage:** viewMode param (T2) ✓; buildDictionaryMatrix reuse (T2) ✓; METRIC_ONLY_UNI suppress (T1) ✓; SUM display_negated fix (T1) ✓; localStorage hydrated-guard (T3) ✓; chart reset (T3) ✓; toggle scope IS/BS/CF (T3) ✓; StatementMatrix unchanged ✓; tests for uni rows + sign + suppression (T1/T2) ✓.
- **Placeholders:** none — all steps carry concrete code/commands. (Styling class names are intentionally "mirror the existing toggle" because the exact utility classes must match the neighbouring control; this is a direction, not a code placeholder.)
- **Type consistency:** `viewMode: 'pdf'|'uni'` used identically across `buildMatrix`, Viewer state, localStorage value; `buildDictionaryMatrix(cells, statement, periods)` signature matches its existing definition.
