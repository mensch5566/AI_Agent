---
type: design-spec
topic: statement-view-mode-toggle
date: 2026-06-08
status: draft
tier: T2  # frontend feature; no production data writes, no irreversible pipeline change
branch: worktree-statement-view-pdf-faithful
related:
  - docs/superpowers/specs/2026-06-04-statement-view-pdf-faithful-display.md
---

# Statement View-Mode Toggle (PDF-faithful ⇄ uni_account)

## Problem / Goal

The Financials Viewer three statements (IS / BS / CF) currently render in ONE mode:
**PDF-faithful** — each ticker shows its own filing's line labels, the filing's
top-to-bottom order, PDF number format, and only disclosed rows (data-driven from
`display_label` + `ordinal`). Before the `statement-view-pdf-faithful` branch, the
same viewer rendered in **uni_account mode** — a fixed set of canonical core rows
(`IS_ROWS` / `BS_ROWS` / `CF_ROWS` from `constants.ts`) where uncommon accounts
collapse into `*_long_tail` bucket rows (summed). That mode is cross-ticker
comparable; the PDF mode is faithful to each filing.

**Goal:** add a single global toggle so the user can switch the whole viewer
between the two modes. Both render strategies already exist in code — PDF mode is
the worktree's current data-driven `buildMatrix`; uni_account mode is `main`'s
prior `buildMatrix` (known-good, "the finished version" per the user).

Non-goal: changing data, the API, the DB, or the parse/derive pipeline. This is a
pure frontend render-strategy switch over the same `cells` payload.

## Key facts (verified)

- Both builders return the SAME `Matrix` shape: `{ rows: {key,label,kind,indent}[],
  cells: Record<rowKey, Record<period, MatrixCell>> }`. The render shell
  (`StatementMatrix`) looks up cells by `row.key`, so it renders either matrix as
  long as each builder is internally consistent (its `rows[].key` match its `cells`
  keys). PDF builder keys rows by `rowId` (uni_account, or uni+source for long-tail
  members); uni builder keys rows by `uni_account`.
- The uni_account builder already lives in the worktree: `buildDictionaryMatrix`
  (`useFinancialMatrix.ts:361`), used today for `RATIO`. It reads `ROWS_BY_STATEMENT`
  + sums `*_long_tail` members. So uni mode is "route IS/BS/CF through the existing
  dictionary builder", NOT a restore from `main`.
- Viewer wiring: `Viewer.tsx` computes the matrix in a `useMemo` —
  `buildMatrix(cells, statement, "GAAP"|"NON_GAAP", frequency)` — and passes it to
  `<StatementMatrix statement=… gaap=… signFlipConcepts=… />`. The toggle plugs in
  exactly here (pick the builder by mode).

## Design (Approach A — reuse the existing dictionary builder, one render shell, mode flag)

> Revised after Codex design-gate review (GPT-5.5). The uni_account builder
> **already exists** in the worktree as the private `buildDictionaryMatrix(filtered,
> statement, periods)` (`useFinancialMatrix.ts:361`), today used only for `RATIO`.
> It builds rows from `ROWS_BY_STATEMENT` (= `IS_ROWS/BS_ROWS/CF_ROWS`) and SUMs
> `*_long_tail` members with rollup suppression — exactly the uni mode we want. So
> we do **not** restore anything from `main`; we route IS/BS/CF to this existing
> function in uni mode. This also sidesteps the `METRIC_ONLY_UNI` resurrection trap
> (a literal `main` restore would re-inline `ebitda`/`free_cash_flow`).

### Components

1. **`useFinancialMatrix.ts` — `buildMatrix`**
   - Add a `viewMode: 'pdf' | 'uni'` parameter (default `'pdf'`).
   - Cell filtering + `periods` computation stay shared. After filtering, for
     `statement ∈ {IS,BS,CF}`: if `viewMode === 'uni'`, return
     `buildDictionaryMatrix(filtered, statement, periods)`; else run the existing
     data-driven (PDF) path. `RATIO` is unchanged (already dictionary).
   - **Fix (Codex P1):** in `buildDictionaryMatrix`'s synthetic long-tail SUM cell
     (`useFinancialMatrix.ts:~408` `{ ...base, … }`), the spread currently carries
     `display_negated` (and could carry stale display metadata) from `children[0]`.
     `StatementMatrix.displayValue` then applies TRUE negation to the WHOLE summed
     bucket → wrong sign. Explicitly set `display_negated: null` (xbrl_tag already
     null) on the synthetic cell so a bucket renders its natural summed sign. (Add a
     regression test; this is a latent bug independent of the toggle.)

2. **`Viewer.tsx`**
   - `const [viewMode, setViewMode] = useState<'pdf'|'uni'>('pdf')` — deterministic
     default (hydration-safe). A `useEffect` reads `localStorage['fin-view-mode-v1']`
     on mount and applies it; another effect persists on change. (Codex P2:
     never read `localStorage` in the `useState` initializer under App Router.)
   - Matrix `useMemo` passes `viewMode` to `buildMatrix`; `viewMode` joins deps.
   - **Reset chart selection on mode switch (Codex P2):** uni rows key by
     `uni_account`, PDF rows by `rowId` — a selected PDF-only key (e.g.
     `operating_expense_long_tail|Restructuring`) does not exist in uni mode, which
     would silently null the chart + drop highlight. On `viewMode` change, reset
     `selectedKeys` to the statement preset (same effect already used on `statement`
     change). [Decision: reset, not per-mode memory — simplest, predictable.]
   - **Toggle scope (Codex P2):** render the 2-segment toggle **only when
     `view ∈ {IS,BS,CF}`**. `SEGMENT` bypasses `StatementMatrix` (renders
     `SegmentDashboard`); `RATIO` already uses the dictionary path so the toggle is a
     no-op there. Labels: **「依財報」**(pdf) / **「標準科目」**(uni), placed near the
     frequency (quarterly/annual) control.

3. **`StatementMatrix.tsx`** — UNCHANGED. Renders any `Matrix`; both modes inherit
   the corrected PDF number format (`5,985`) + `display_negated` sign logic.

### Sign / format behavior across modes

- **PDF mode**: rows map 1:1 to a fact → `display_negated` drives the sign.
- **uni mode** core rows map to the single core `uni_account` cell → `display_negated`
  carries through, signs correct.
- **uni mode long-tail SUM buckets**: with the P1 fix, `display_negated` is forced
  `null` on the synthetic cell → render shell shows the summed value's natural sign
  (a sum's sign is the sum's sign). Correct and matches the pre-display_negated
  `main` behavior.

### Persistence & scope
- One global `viewMode`, persisted in `localStorage` (`fin-view-mode-v1`) across
  tickers/sessions, default `'pdf'`, hydration-safe (effect-read). Switching is a
  client-side rebuild (no refetch). Toggle visible only on IS/BS/CF tabs.

## Alternatives considered
- **B. One builder with a `mode` param** — rejected: entangles two distinct row
  strategies in one function, erodes the isolation that protects PDF-faithful
  correctness.
- **C. Two Matrix components** — rejected: duplicates the render shell (chart,
  periods, number format, sign logic) and risks the two drifting.

## Testing
- Unit (`useFinancialMatrix.test.ts`): `buildMatrix(cells, IS|BS|CF, GAAP, freq,
  'uni')` returns the fixed `ROWS_BY_STATEMENT` rows keyed by `uni_account` with
  `*_long_tail` members collapsed into the bucket SUM; `'pdf'` mode yields the
  data-driven label/ordinal rows. Same `cells` → two distinct expected row sets.
- **SUM-sign regression (Codex P1):** a long-tail bucket whose `children[0]` has
  `display_negated: true` must render its natural summed sign — assert the synthetic
  SUM cell has `display_negated: null`, and `displayValue` does NOT negate it.
- **Mode-switch chart reset:** selecting a PDF-only key then switching to uni resets
  `selectedKeys` to the statement preset (no stale/all-null chart).
- `tsc --noEmit` + existing vitest green.
- Manual: MU IS/BS/CF toggle both ways; uni shows core rows + `Other … (long-tail)`
  buckets, PDF shows filing labels; toggle hidden on Ratios/Segment; localStorage
  round-trips; reload restores last mode.

## Risks
- Only ONE builder runs per render; the two matrices' cells are never merged, so no
  cross-mode key collision.
- `buildDictionaryMatrix` is already battle-tested for RATIO; routing IS/BS/CF
  through it reuses known-good code rather than reintroducing `main`'s variant.
- The SUM-sign fix touches a shared synthetic-cell path — covered by the regression
  test above; `tsc` guards type drift.

## Out of scope
- Other 4 tickers' display metadata re-upsert (separate, pending).
- PDF-mode share-count format / parenthetical-row ordering polish (separate).
