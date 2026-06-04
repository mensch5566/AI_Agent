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

## 12. Codex round-1 review — accepted findings & spec deltas (2026-06-04)

Codex reviewed v1; all 6 P1/P2 + 3 P3 findings independently **verified true** against the 5-ticker
local parse output and the repo. No pushback — Claude's own verification additionally escalated the
AAOI coverage risk. The following deltas **amend** the sections above and are binding for v2.

**P1.1 — `source_account` is a BARE local name, not a prefixed qname. (verified: direct
`child_qname == source_account` match = 0 for ALL 5 tickers.)** §4.3 step 1 is replaced by a **qname
resolver**: facts store `GrossProfit`; `edges_pre.child_qname` and `labels.json` keys are
`us-gaap:GrossProfit`. Match on the **local name** (`child_qname.split(':')[-1] == source_account`).
Namespace ambiguity (same local name under >1 namespace) is resolved **within the chosen presentation
network** (§4.1), which already scopes to one statement; if still ambiguous, prefer `us-gaap` then the
filer extension. Same local-name resolution applies to the `labels.json` lookup.

**P1.2 + P2.6 — row identity contract (this was under-specified; would have broken quarterly IS/CF).**
Derived single-quarter values (`derived_q2` / `derived_q3` / `derived_q4` — see the §16 post-P2.1
addendum; pre-P2.1 only `derived_q4` existed) live in `sec_financial_metrics` keyed by `uni_account`
with **no `source_account`/`ordinal`**, and quarterly IS/CF must show
`quarter_duration ∪ derived_q2 ∪ derived_q3 ∪ derived_q4` (`useFinancialMatrix.ts`). The row builder
therefore:
- **Row prototypes come from DIRECT FACTS only** (they carry `source_account` + `uni_account` + display
  metadata). A metric cell never creates a row.
- **`rowId` = `uni_account` for core rows** (so a derived single-quarter metric cell attaches to its PDF row by
  `uni_account`); **`rowId` = `uni_account + '|' + source_account` for long-tail bucket members** (many
  share one bucket `uni_account`, so they need `source_account` to disambiguate — long-tail has no
  derived single-quarter attach problem because those derived `derived_q2/q3/q4` values are bucket-less).
- **Metric-only rows with no fact prototype (ebitda, free_cash_flow) are EXCLUDED from IS/BS/CF**, not
  rendered as `(uni_account|null)` ghost rows. Exclusion is by "no direct-fact prototype", NOT "is a
  metric" (derived single-quarter `derived_q2/q3/q4` metrics still attach).
- `Matrix.rows[].key` stays a single string (`rowId`); chart selection / cellMap / tooltip / long-tail
  must consume `rowId` + a separate `displayLabel`, never assume `key === uni_account`.

**P2.3 — EBITDA/FCF relocation data path. (verified: `ebitda` in `IS_ROWS:44`, `free_cash_flow` in
`CF_ROWS:109`; `RATIO_ROWS` has only the margins; RATIO builder filters `statement==="RATIO"`.)** Add an
explicit **`DERIVED_NONGAAP_ABSOLUTE_ROWS`** subsection in the analytics/Ratios area that reads the
`ebitda` (statement=IS) + `free_cash_flow` (statement=CF) metric rows directly (they are NOT
`statement="RATIO"`, so the existing RATIO builder will not pick them up). Remove their inline IS/CF
placement only.

**P2.4 — migration discipline (T3) + reuse existing column. (verified: `sec_financial_facts` already
has `ordinal smallint -- presentation order` at migration `20260516234808_…:7`, currently unpopulated.)**
- **Reuse the existing `ordinal` column** for presentation order (do NOT add `display_ordinal`).
- Add only **`display_label TEXT`** via a **proper SQL migration file** under `supabase/migrations/`
  (SSOT) with a `-- rollback` block — NOT the Supabase Management API console. Update
  `docs/sec-financials-v2-schema.md` + `docs/financials-data-rules.md` in the same change.

**P2.5 — network selection must be robust + a HARD GATE. (verified: AAOI role_uris are custom +
date-prefixed, e.g. `http://ao-inc.com/20260331/role/statement-condensed-consolidated-statements-of-
operations-unaudited`; plain `BalanceSheets`/`CashFlows` keywords miss them.)**
- Network match is **case-insensitive + hyphen/underscore-insensitive on the role local part**:
  IS = contains `operations` or `income` (and `statement`); BS = `balancesheet` or `financialposition`;
  CF = `cashflow`. **Exclude** `parenthetical`, `details`, `note`, `reconciliation`. Pick the latest
  filing's matching network; tie-break by largest child∩facts overlap.
- **HARD GATE**: for every (ticker × statement) the resolver must select **exactly one** primary network
  and reach a **coverage threshold** (≥ X% of that ticker-statement's direct facts get a non-null
  `ordinal`; threshold TBD in plan, e.g. 90%). Below threshold or zero-network → **FAIL the upsert
  loudly**, never silently ship null `ordinal`.
- **AAOI risk (Claude escalation)**: even after the qname resolver, a residual coverage gap may remain
  for AAOI. Rollout is therefore **per-ticker, gated**: ship the tickers that pass; if AAOI fails the
  gate, **defer AAOI** and open a follow-up to investigate its presentation-linkbase capture — do NOT
  weaken the gate to force it through.

**P2.2 (Claude refine) — ordering source across annual/quarterly.** §4.2's "latest filing" is refined to
**latest 10-K (annual) network as primary** (the full statement), **supplemented by the latest 10-Q
network** for any concept present only in 10-Q. This prevents annual-only lines from being null-ordinal
appended (Codex's open concern on my Q3 answer).

**P3 deltas**: (a) add `"MU"` to `KNOWN_TICKERS` (`constants.ts:9` currently `["AAOI","INTC","LITE",
"SNDK"]` — MU is upserted but unlisted in the UI). (b) PDF number formatting is a **statement-scoped
formatter**, not a global `fmtValue` edit (avoid collateral changes to chart/ratio rendering). (c)
`docs/financials-data-rules.md` + `docs/sec-financials-v2-schema.md` are in the implementation gate
(schema + display-contract change).

**Status**: v2 (this §12 supersedes the conflicting parts of §4–§8). Awaiting human approval; optional
Codex round-2 on v2 before writing-plans.

## 13. v3 — upsert-layer resolution + NLM ordering fallback (user-directed, 2026-06-04)

User-driven convergence after §12. Empirical re-measurement (per-statement, 5 tickers) reframed the
problem and the architecture. **This §13 is binding and supersedes §4's resolution layer, §10's
parse-layer alternative, and §12's AAOI-defer.** All other §12 findings (row identity, derived
subsection, migration column, formatter, KNOWN_TICKERS) carry over unchanged.

### 13.1 Reframing (verified)

- **`display_label` coverage is 95–100% for every ticker incl AAOI** (AAOI IS 95% / BS 100% / CF 95%).
  The earlier "AAOI 28%" was an artifact of conflating label-coverage with ordinal-coverage and of the
  bare-vs-prefixed string mismatch. **Labels are not the problem.**
- The real gap is **`ordinal` (row order)**, and AAOI's is specifically **BS = 0% / CF = 9%**: its
  captured presentation linkbase (`edges_pre`) contains **zero** balance-sheet/cash-flow networks (128
  roles, none match `balancesheet|financialposition|cashflow`; the `full_linkbase.py` regex is correct,
  so the networks were never captured — a separate parse data-capture gap, NOT a matching bug).

### 13.2 Architecture (decision: upsert-layer; parse-10QK-gaap UNTOUCHED)

Resolution lives entirely in `scripts/upsert_sec_financials.py`. **`parse-10QK-gaap`
(`xbrl_extract.py` / `build_separated.py`) is not modified** — it already emits `labels.json` +
`edges_pre.json`, which the upsert consumes.

- **`display_label`**: upsert matches `fact.source_account` (bare local name) to `labels.json` keys
  (prefixed qname) by **local name** (namespace-strip); pick the `text` whose `role` == the
  presentation `preferred_label` for that concept (fallback `terseLabel → totalLabel → label →
  source_account`). Verified 95–100% coverage.
- **`ordinal` primary = XBRL presentation**: from `edges_pre.order` within the network selected per
  §12-P2.5 (robust, case/hyphen-insensitive role matching; exclude parenthetical/details/notes).
- **`ordinal` fallback = NLM** (user's idea): for any ticker×statement where the XBRL presentation
  network is absent/below the coverage gate (e.g. AAOI BS/CF), a small **NLM ordering step** reads the
  actual filing PDF and returns the line items in PDF order; the upsert assigns `ordinal` from that
  sequence (matched to facts by display_label/source_account). `provenance.ordinal_source ∈ {xbrl,
  nlm}`. Row order is a low-hallucination "read the sequence" task and NLM reads the real PDF, so it is
  PDF-faithful by construction. **The NLM step is NEW code; it does NOT modify the 定案 parse skills**
  (it lives near `parse-sec-cross-check`, which already does NLM PDF reads, or as a small standalone;
  output is a per-ticker ordering artifact the upsert reads — plan decides exact home).

### 13.3 Coverage hard gate + AAOI (defer REMOVED)

Per ticker×statement, `ordinal` must reach the coverage threshold via **XBRL ∪ NLM combined**; below →
**fail the upsert loudly**. AAOI BS/CF reach coverage via the NLM fallback → **AAOI ships with the
other 4; no defer.** A separate follow-up ticket investigates why `build_separated` did not capture
AAOI's BS/CF presentation networks (a parse data-capture gap); fixing it later lets AAOI drop the NLM
fallback, but it does not block this feature.

### 13.4 Net effect on prior findings

- **P1.1 (qname resolver)**: handled at upsert via namespace-strip (verified). Not a blocker.
- **P1.2/P2.6 (row identity), P2.3 (derived subsection), P2.4 (reuse `ordinal` col + add `display_label`
  via SQL migration), P3 (MU in KNOWN_TICKERS, statement-scoped formatter, docs in gate)**: all carry
  over from §12 unchanged — they are frontend/migration concerns independent of the resolution layer.
- **P2.2 (annual/quarterly ordering)**: still use latest 10-K network primary + 10-Q supplement for the
  XBRL ordinal; the NLM fallback (when used) reads the most recent filing of that statement type.

**Status**: v3 (binding architecture = §13 + carried-over §12 findings). Ready for Codex round-2 on v3
before writing-plans.

## 14. Codex round-2 — accepted gates (2026-06-04)

Codex round-2 accepted the v3 architecture (parse untouched / upsert resolution / XBRL ordinal primary
/ NLM ordinal fallback) and raised 2 P1 + 3 P2 closure gates. All verified true; all accepted. Binding.

### G1 (P1.1) — NLM ordering fallback: full artifact + matching + provenance + audit contract

The NLM ordering source is a **new T3 data source** and must carry a real contract, not "low
hallucination" prose:

- **Artifact schema** (`{TICKER}_{STATEMENT}_nlm_order.json`, per ticker×statement that needs it):
  `{source_doc, accession, period, form, page_or_section, statement, ordinal, pdf_label,
  matched_cell_id, match_method, confidence, unmatched_reason}` per row.
- **Match priority** (NLM PDF line → fact): (1) exact `pdf_label` == `display_label`; (2) normalized
  label (lowercase, strip punctuation/whitespace); (3) `source_account`; (4) `uni_account`. Record the
  winning `match_method`.
- **Bidirectional unmatched report**: list every PDF line with no matched fact AND every display-eligible
  fact with no matched PDF line. Non-empty → surfaced for human audit.
- **Human audit gate**: NLM order goes to production only after a human signs off the artifact (same
  discipline as parse-sec-cross-check / parse-SEC-supplement NLM validation). No silent ship.
- **Provenance on each ordinal-via-NLM fact**: `ordinal_source='nlm'`, `ordinal_source_doc`,
  `ordinal_source_period`, `ordinal_match_method`, `ordinal_artifact_hash` (hash of the signed
  artifact). XBRL-sourced ordinals carry `ordinal_source='xbrl'` + the network role_uri + period.

### G2 (P1.2) — `source_account` is 3 classes; synthetic/null must be handled, not guessed

Verified across all 5 tickers: real PDF rows carry non-tag `source_account` —
- **null**: CF `net_income` (CF opening "Net income"); IS `shares_basic_millions` / `shares_diluted_millions`.
- **synthetic** `SUM(...)`: CF `depreciation_and_amortization`=`SUM(D&A components)` (INTC/AAOI/LITE);
  IS `selling_general_administrative`=`SUM(S&M+G&A)` (AAOI).

Classify + resolve:
1. **tag-like** (`GrossProfit`) → §13.2 namespace-strip → labels/edges.
2. **synthetic / null** → resolve display_label + ordinal via the row's **`uni_account` → canonical
   concept** (the primary candidate in `IS_TAG_MAP`/`BS_TAG_MAP`/`CF_TAG_MAP`, e.g. `net_income →
   NetIncomeLoss`, `shares_basic_millions → WeightedAverageNumberOfSharesOutstandingBasic`,
   `depreciation_and_amortization → DepreciationAndAmortization`), then labels/edges as normal. These
   ARE PDF rows and MUST display.
3. The plan must **enumerate** which facts land in each class for the 5 tickers and assert **none are
   silently dropped**; any genuinely non-display fact (if found) is excluded explicitly with the reason.

### G3 (P2.1) — namespace-strip fail-closed

If a bare local name resolves to **>1 qname** within the selected presentation network → **fail (or
route to manual mapping); never silent-prefer**. Once the full qname is resolved, the `labels.json`
lookup uses **that resolved qname**, not a second local-name lookup. (Current 5 tickers: no ambiguity
observed — the guard is a forward gate.)

### G4 (P2.2) — coverage gate: denominator + 100%

Coverage denominator = **display-eligible rows only** (exclude YTD period rows, metric-only rows, and
any explicitly-classified non-display synthetic rows). Gate = **visible-row ordinal coverage 100%**;
anything < 100% must emit the unmatched list and require **human approval** before ship — not a silent
90% pass.

### G5 (P2.3) — deterministic label prototype

For a core `rowId = uni_account` whose source tag/label varies across periods, the row's
`display_label` + `ordinal` come from a **deterministic prototype = latest 10-K (or NLM-matched)
matched fact**, never decided by data iteration order. Derived single-quarter cells
(`derived_q2` / `derived_q3` / `derived_q4`) attach by `uni_account` and must attach to a
**display-eligible** prototype row (not a YTD/synthetic-excluded one).

**Status**: v4 (= §13 architecture + §12 carried findings + §14 G1–G5 gates). Awaiting Codex round-3 /
human closure before writing-plans.

## 15. Codex round-3 — final spec gates (2026-06-04)

No new P1; G1–G5 converged. Two P2 spec-seams + one P3, all verified true, all accepted. Binding.

### G6 (P2.1) — `source_account` is **four** classes, not three

Verified: LITE has `Income before income taxes` / `Loss before income taxes`; SNDK has `Gain on business
divestiture` / `Business separation costs` / `Loss on business divestiture` — these are **preserved
PDF-label strings** (contain spaces; from NLM-audit / manual label discovery), neither tag-like nor
synthetic/null. The classifier (applied in order):

1. **null** → resolve via `uni_account → canonical concept` (G7).
2. **synthetic** (`source_account` starts with `SUM(` or carries the synthetic marker) → G7.
3. **preserved_pdf_label** (contains whitespace / is not a QName-shaped token) → **`display_label =
   source_account` verbatim** (it is already the PDF text); `ordinal` only via NLM exact/normalized-label
   match or explicit manual mapping — **never** the namespace-strip resolver.
4. **tag-like** (QName-shaped, e.g. `GrossProfit`) → §13.2 namespace-strip → labels/edges.

The plan must enumerate which facts land in each class for the 5 tickers; none silently dropped.

### G7 (P2.2) — synthetic/null `uni_account → canonical concept` can MISS; hard fallback + display-vs-aggregate

Verified: `depreciation_and_amortization → DepreciationAndAmortization` is **absent from labels AND
edges** for INTC/LITE (they report `Depreciation` + `Amortization` as separate lines), and absent from
edges for AAOI; `selling_general_administrative → SellingGeneralAndAdministrativeExpense` is absent for
AAOI (reports `S&M` + `G&A` separately). So G2's canonical path fails for exactly the SUM-synthetic rows.

Rules:
- When the canonical concept is **not in labels** or **not in the selected presentation network** →
  route to **NLM / manual ordinal (and label) mapping**; **never** render `SUM(...)` as a display label.
- **Display-vs-aggregate (the deeper resolution)**: a synthetic SUM that aggregates **multiple PDF
  lines** is **NOT a PDF row → non-display in the statement**; its **component long-tail rows are the PDF
  rows and display** (e.g. INTC/LITE CF show `Depreciation` and `Amortization` as two lines; AAOI IS
  shows `Selling & marketing` and `G&A`). The combined SUM row stays only in the analytics layer (EBITDA
  input). **NLM (reading the actual PDF) is the arbiter** of whether the combined line exists as one PDF
  row (then display it with the NLM label) or the components are the PDF rows (then SUM is non-display).
- G4's 100% coverage gate catches a silent ship, but this fallback path is now hardcoded in the spec so
  implementation does not naively try to label/order the SUM rows.

### G8 (P3) — NLM `uni_account` fallback match must be unique

The NLM match priority's `uni_account` tier (G1) may fire **only when, within
(statement, period, display-eligible row set), exactly one candidate fact has that `uni_account`**.
More than one → `unmatched` / manual audit, never a guess. Guards against future long-tail-bucket or
same-classification expansion mis-ordering.

**Status**: v5 (= §13 architecture + §12 + §14 G1–G5 + §15 G6–G8). Codex round-3 closure: no open
P1/P2. **Design gate CLOSED — human sign-off given 2026-06-04.** Next: writing-plans → git worktree → TDD.

**Plan note (Codex round-3 P3, binding on the implementation plan, not a spec change)**: §15 G7's "SUM
row stays only in analytics layer" means **Statement-view display-ineligible**, NOT a storage
relocation. The core synthetic facts `SUM(D&A components)` / `SUM(S&M+G&A)` remain in storage and
continue feeding EBITDA/analytics unchanged; they simply **do not create a Statement-view row
prototype**, and a derived single-quarter cell (`derived_q2` / `derived_q3` / `derived_q4`) must NOT
pull a non-display synthetic core back into the statement via its shared `uni_account`. The plan + tests
must explicitly cover: (a) non-display synthetic core builds no row prototype; (b) the component
long-tail rows are the PDF rows; (c) derived single-quarter cells attach only to display-eligible
prototypes.

---

## §16 — Post-P2.1 addendum (2026-06-04): derived single-quarter set generalized

This spec was written when `sec_financial_metrics` carried only `derived_q4` single-quarter rows. **P2.1
(shipped to production 2026-06-04)** added `derived_q2` (6M−Q1) and `derived_q3` (9M−6M) reconstruction
to derive-base, so the derived single-quarter set is now **`derived_q2 ∪ derived_q3 ∪ derived_q4`**.

Binding contract update — wherever this spec says "`derived_q4` attaches by `uni_account`" (the row
identity contract §P1.2/P2.6, the deterministic-prototype rule, and the synthetic-pull-back guard, all
generalized inline above), read it as **the derived single-quarter set `derived_q2/q3/q4`**:

- All three route into the quarterly IS/CF view (`useFinancialMatrix.ts` `QUARTERLY_PKINDS_IS_CF`;
  `docs/financials-data-rules.md` §quarterly IS/CF). The migration `20260604120000_add_derived_q2_q3_metrics.sql`
  is already applied (period_kind CHECK allows derived_q2/q3).
- The attach semantics are identical for Q2/Q3/Q4 (metric cell keyed by `uni_account`, no
  `source_account`/`ordinal`, attaches to a display-eligible direct-fact prototype). The implementation
  plan's Tasks 8 & 11 tests must assert **all three** attach (not only Q4) and that none of them pulls a
  display-ineligible synthetic core back.
- Everything else in this spec (4-class classifier, presentation resolver, NLM ordering, coverage hard
  gate, statement-scoped formatter) is **orthogonal** — it resolves FACTS display metadata
  (`display_label`/`ordinal`), which derived metrics never carry. No change.

EPS has no derived single quarters (non-additive → derive-base never reconstructs EPS), so EPS quarterly
columns remain Q1/Q4-direct as before.
