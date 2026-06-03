# Statement View — PDF-Faithful Display (source_account labels + presentation order)

Date: 2026-06-04
Tier: **T3** (財務資料管道 + 對外展示；100% 精準要求)
Status: Design — awaiting human review before writing-plans
Branch: to be developed in a dedicated **git worktree** (per user instruction; change spans backend + frontend)

## 1. Context & Goal

The per-ticker **Statement view** (Income Statement / Balance Sheet / Cash Flow) currently renders a
**hardcoded** row list (`IS_ROWS` / `BS_ROWS` / `CF_ROWS` in
`app/components/financials-v2/constants.ts`), keyed by the unified cross-ticker `uni_account`, with
hand-written English labels and fixed array ordering. That is correct for the **Comparison view**
(cross-ticker, needs a common key) but wrong for the per-ticker statement, which should look **exactly
like that company's filing PDF**.

**Goal**: every ticker's Statement view (IS/BS/CF) shows the **company's own disclosed line items**,
with the **PDF label text**, in **PDF order**, with **PDF number formatting** — nothing more, nothing
less. This is the per-ticker, PDF-faithful presentation the 3-layer architecture
(`docs/financials-architecture.md` §Frontend Statement View Rendering, lines 388–422) always intended.

## 2. Locked Decisions (from brainstorming)

1. **Label sourcing = denormalize onto each cell.** Resolve a `display_label` per fact and store it on
   the row; the frontend just reads it (no client-side join).
2. **Scope** = (a) PDF label text, (b) only the rows the ticker actually discloses (no empty rows for
   metrics only other tickers report), (c) PDF row order, (d) PDF number formatting. NOT indentation /
   bold-subtotals / section-header layout fidelity (deferred).
3. **Number format = PDF-style**: `$` amounts as whole numbers (unit already encodes millions/thousands,
   e.g. `13,643`), EPS = 2 decimals, ratio/percent = 1 decimal.
4. **Three statements show ONLY disclosed (filing) rows.** Derived values (EBITDA, FCF, all ratios) are
   removed from IS/BS/CF and live only in the Ratios/analytics area. Comparison view + Ratios view stay
   `uni_account`-keyed (unchanged).

## 3. Data sources (verified)

Both produced by `parse-10QK-gaap` `build_separated.py`, already upserted/available locally:

- **`{TICKER}_gaap_labels.json`** → `labels[concept_qname] = [{role, lang, text}, …]`.
  e.g. `labels["us-gaap:GrossProfit"]` has `terseLabel → "Gross margin"`, `totalLabel → "Gross profit"`,
  `label → "Gross Profit"`. The PDF text is the `text` whose `role` matches the presentation
  `preferred_label`. (Intel's IS uses terseLabel "Gross margin" — exactly the PDF wording.)
- **`{TICKER}_gaap_edges_pre.json`** (Presentation Linkbase) → edges with
  `{period, parent_qname, child_qname, order, preferred_label (role URI), role_uri (network)}`.
  `role_uri` identifies the statement network (e.g.
  `…/ConsolidatedStatementsofIncome`, `…/ConsolidatedBalanceSheets`, `…/StatementsofCashFlows`,
  plus `…Parenthetical` and detail networks to be excluded).
- **`sec_financial_facts`** already stores `source_account` (the concept qname/tag, e.g.
  `CostOfGoodsAndServicesSold`) + `value` + `unit` + `statement` + `period`/`period_kind`.

## 4. Architecture — resolution algorithm (upsert-layer, parse skill UNTOUCHED)

Resolution happens in `scripts/upsert_sec_financials.py` (it already reads the edges). The
`parse-10QK-gaap` skill (定案) is **not modified**.

### 4.1 Pick the primary presentation network per (ticker, statement)

`edges_pre` carries several networks. For each statement map by `role_uri` keyword and exclude noise:

- IS → role_uri contains `StatementsofIncome` / `StatementsOfOperations`, NOT `Parenthetical`.
- BS → contains `BalanceSheets`, NOT `Parenthetical`.
- CF → contains `CashFlows`, NOT `Parenthetical`.

When >1 candidate (e.g. `Consolidated` vs `ConsolidatedCondensed`), pick the network whose child set
has the **largest overlap with the ticker's actual facts** for that statement (the real statement, not
a stub). Tie-break: most child edges. Resolved once per (ticker, statement).

### 4.2 Per-period vs single ordering

The presentation linkbase can differ per filing (`edges_pre` rows carry `period`). The Statement view
renders one ordering per statement across all period columns, so use the **latest filing's** network
for that statement (newest `period`). Record the source period in provenance for auditability.

### 4.3 Per-fact resolution → display_ordinal + display_label

For each fact `(statement, source_account=concept, …)`:

1. Find its edge in the chosen network where `child_qname == concept`.
2. `display_ordinal` = that edge's `order` (float; defines PDF row order within the statement).
3. `role = edge.preferred_label`; `display_label = labels[concept]` text whose `role == role`.
   Fallback chain if missing: `terseLabel → totalLabel → label (standard) → source_account`.
4. **No edge found** (rare — e.g. a tag the filer didn't put in this presentation network, or a
   long-tail tag): `display_ordinal = NULL` → frontend appends after ordered rows; `display_label`
   falls back to `labels[concept].terseLabel||label || source_account`. Log a coverage warning.

**Long-tail disclosed lines**: they carry a real `source_account` (the filer's own tag) and a presentation
edge → they resolve to their true PDF label + ordinal and render **inline at their PDF position** (they
ARE PDF lines). No special-casing beyond the algorithm above.

### 4.4 Storage (denormalize onto the cell)

Add two nullable columns to `sec_financial_facts`:

- `display_label TEXT` — PDF label text (null → frontend falls back to source_account).
- `display_ordinal NUMERIC` — PDF row order within statement (null → appended last).

Migration via Supabase Management API (additive, nullable; no backfill needed beyond re-upsert).
Identity/dedupe unchanged (these are display metadata, not part of the fact identity key).

### 4.5 API

`app/api/financials/[ticker]/route.ts` `.select(...)` already returns `source_account`; add
`display_label, display_ordinal`. No new endpoint, no edges query from the frontend.

## 5. Frontend (Statement view only — IS/BS/CF)

`app/components/financials-v2/`:

- **`useFinancialMatrix.ts`**: for IS/BS/CF, stop iterating the hardcoded `ROWS_BY_STATEMENT` list.
  Build rows from the **ticker's actual cells**: distinct `(uni_account|source_account)` rows that have
  ≥1 value in the visible period set, ordered by `display_ordinal` (nulls last, stable), each row's
  label = `display_label` (fallback `source_account`). Derived rows (EBITDA/FCF) are excluded from
  IS/BS/CF here.
- **`StatementMatrix.tsx`**: render `row.display_label`; apply PDF number formatting (see §6).
- **Ratios view + Comparison view**: unchanged (still hardcoded `RATIO_ROWS` / uni_account). The two
  derived absolute-value rows currently inline in the statements — `ebitda` (in `IS_ROWS`) and
  `free_cash_flow` (in `CF_ROWS`) — are **removed from IS/CF** and instead shown in a **"Derived /
  Non-GAAP" subsection of the Ratios/analytics tab** (they are $ values, not ratios, so they get their
  own subsection rather than mixing into the ratio rows). `ebitda_margin_pct` and the other ratios
  already live in `RATIO_ROWS` and are untouched.
- **`constants.ts`**: keep `IS_ROWS`/`BS_ROWS`/`CF_ROWS` only as a labeling fallback (e.g. when
  `display_label` is null), not as the row driver.

## 6. Number formatting (PDF-style)

In the Statement view formatter (`fmtValue` or equivalent):

- `$` amounts (statement IS/BS/CF money rows): whole number with thousands separators, no decimals
  (`13,643`); negatives in parentheses (existing behavior); unit (millions/thousands) per-row as today.
- **EPS rows** (`eps_basic`/`eps_diluted`, `unit=USD_per_share`): 2 decimals.
- **Ratio/percent rows** (Ratios view): 1 decimal (e.g. `48.1%`, `2.19x`) — already largely so.

EPS detection reuses the existing `isEps()` / per-row unit check (`USD_per_share`).

## 7. Rollout

1. Migration: add 2 columns (additive, nullable).
2. Upsert change: implement the §4 resolution; **dry-run diff** each of the 5 tickers (MU/INTC/AAOI/
   LITE/SNDK) — expect only `display_label`/`display_ordinal` to populate, **zero change to existing
   values/identities**.
3. `--apply` all 5 (idempotent; gate must stay green).
4. Frontend deploy after backend columns exist.

## 8. Testing

- **Backend (TDD + property)**: `scripts/tests/` — network selection (picks the real IS/BS/CF network,
  excludes Parenthetical/detail); per-fact resolution (label role → text; fallback chain; null-edge →
  null ordinal); long-tail inline resolution; **upsert dry-run diff = 0 existing-value change** for a
  fixture ticker. Property: resolution never throws on missing concept/role/edge (returns null + warns).
- **Frontend**: `vitest` for the data-driven row builder (ordinal sort nulls-last, label fallback,
  derived-row exclusion) + `tsc --noEmit`.
- **Visual (E2E, T3)**: Claude Preview — for each of the 5 tickers, IS/BS/CF rows match the filing PDF
  (labels, which lines, order, number format). This is the acceptance gate for "looks like the PDF".

## 9. Review / Ship (SOP T3)

- Dev in a **git worktree**; spec → human approval (this doc) → writing-plans → TDD build → verify
  (dry-run diff + tsc + vitest) → **Codex adversarial functional review** (the §3.5 gate) → converge →
  ship (re-upsert 5 + frontend deploy) → STATUS update.
- Rollback: columns are additive (drop-column reverts backend); frontend behind the same view component
  (git revert).

## 10. Alternatives considered

- **Parse-layer resolution** (build_separated writes display_label/ordinal into gaap_facts.json):
  rejected — touches the 定案 parse skill for display concerns; upsert already has the edges.
- **Separate `sec_financial_labels` table + API join**: rejected (user chose denormalize) — more
  query/JOIN complexity for no normalization benefit at this scale.
- **Frontend client-side join of edges + labels**: rejected — heavier API payload + client perf; the
  resolution is deterministic and belongs server/ingest-side.

## 11. Out of scope (deferred)

- Indentation / bold subtotals / section-header layout fidelity (decision 2 excludes).
- Comparison view + Ratios view changes (stay uni_account).
- Per-period (column-specific) presentation ordering (we use latest filing's network for one stable
  order; revisit only if a filer materially re-orders its statement mid-history).
- Backfilling display metadata for tickers not in the current 5-ticker set (done when each is onboarded).
