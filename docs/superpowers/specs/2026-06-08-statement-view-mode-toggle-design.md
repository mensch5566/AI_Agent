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
- `main`'s `buildMatrix` (uni_account mode) reads only fields that still exist on
  the current `Cell` type (`uni_account`, `source_account`, `long_tail_metadata`,
  `period_kind`, `period`, `value`, `unit`, `weight`). The current `Cell` is a
  superset (adds `display_label` / `ordinal` / `display_negated`), so `main`'s
  builder restores essentially verbatim.
- Viewer wiring: `Viewer.tsx` computes the matrix in a `useMemo` —
  `buildMatrix(cells, statement, "GAAP"|"NON_GAAP", frequency)` — and passes it to
  `<StatementMatrix statement=… gaap=… signFlipConcepts=… />`. The toggle plugs in
  exactly here (pick the builder by mode).

## Design (Approach A — two builders, one render shell, mode flag)

### Components

1. **`useFinancialMatrix.ts`**
   - Keep the current data-driven builder, exported as `buildMatrix` (PDF mode) —
     unchanged.
   - Restore `main`'s prior uni_account builder as a NEW export
     `buildMatrixUni(cells, statement, channel, frequency)` (same signature). Bring
     it back via `git show main:…/useFinancialMatrix.ts` and adapt only imports /
     type names if they drifted. Its rows come from `IS_ROWS/BS_ROWS/CF_ROWS`; its
     long-tail bucket rows aggregate (`SUM`) the matching `*_long_tail` members.
   - Both builders live side by side; neither calls the other.

2. **`Viewer.tsx`**
   - Add `const [viewMode, setViewMode] = useState<'pdf'|'uni'>(…)` initialized from
     `localStorage` (key `fin-view-mode-v1`, default `'pdf'`), and an effect that
     writes back on change.
   - The matrix `useMemo` selects the builder:
     `(viewMode === 'pdf' ? buildMatrix : buildMatrixUni)(cells, statement, channel, frequency)`.
     `viewMode` joins the memo deps.
   - Render a 2-segment toggle near the frequency (quarterly/annual) control:
     labels e.g. **「依財報」**(pdf) / **「標準科目」**(uni). Global — one control,
     applies to whichever statement tab is active.

3. **`StatementMatrix.tsx`** — UNCHANGED. It already renders any `Matrix` and
   applies the shared PDF number formatter + `display_negated` sign logic. Both
   modes therefore inherit the corrected number format (`5,985`) and sign handling.

### Sign / format behavior across modes

- **PDF mode** rows map 1:1 to a fact → `display_negated` drives the sign.
- **uni mode** core rows also map to a single fact (the core `uni_account` cell) →
  `display_negated` carries through, signs render correctly.
- **uni mode long-tail bucket rows** are `SUM(long_tail)` aggregates with no single
  `display_negated` → cell flag is null → render shell falls back to legacy
  (no flip), showing the summed value's natural sign. Acceptable: a bucket is a sum,
  its sign is the sum's sign. (Documented limitation; not a regression vs `main`,
  which also summed.)

### Persistence & scope
- One global `viewMode`, persisted in `localStorage` across tickers and sessions,
  default `'pdf'`. Switching is instant (client-side rebuild, no refetch).

## Alternatives considered
- **B. One builder with a `mode` param** — rejected: entangles two distinct row
  strategies in one function, erodes the isolation that protects PDF-faithful
  correctness.
- **C. Two Matrix components** — rejected: duplicates the render shell (chart,
  periods, number format, sign logic) and risks the two drifting.

## Testing
- Unit (`useFinancialMatrix.test.ts`): `buildMatrixUni` produces the fixed
  `IS_ROWS`/`BS_ROWS`/`CF_ROWS` rows, collapses `*_long_tail` members into the
  bucket SUM, and keys cells by `uni_account`; `buildMatrix` (pdf) unchanged.
- A mode-selection test: given the same `cells`, `pdf` vs `uni` yield the two
  expected row sets (data-driven labels vs fixed canonical labels).
- `tsc --noEmit` + existing vitest green.
- Manual: MU BS/IS/CF toggle both ways; confirm uni mode shows core rows +
  `Other … (long-tail)` buckets and PDF mode shows filing labels; localStorage
  round-trips.

## Risks
- Row-key collision if `buildMatrixUni`'s cells and `buildMatrix`'s cells were ever
  mixed — mitigated: only ONE builder runs per render; outputs never merged.
- `main`'s builder referencing a symbol the worktree renamed — caught at `tsc`.

## Out of scope
- Other 4 tickers' display metadata re-upsert (separate, pending).
- PDF-mode share-count format / parenthetical-row ordering polish (separate).
