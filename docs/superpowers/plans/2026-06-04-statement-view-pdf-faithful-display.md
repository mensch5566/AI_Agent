# Statement View PDF-Faithful Display — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render each ticker's IS/BS/CF Statement view exactly like its filing PDF — company's own line labels, PDF row order, PDF number format, only disclosed rows.

**Architecture:** Resolution lives entirely in the upsert layer (`parse-10QK-gaap` UNTOUCHED). The upsert reads the already-produced `{TICKER}_gaap_labels.json` + `{TICKER}_gaap_edges_pre.json`, resolves a per-fact `display_label` + `ordinal`, writes them to `sec_financial_facts`. Where the XBRL presentation network is missing (AAOI BS/CF), a new NLM ordering artifact (human-audited) supplies row order. Frontend Statement view becomes data-driven off `(display_label, ordinal)`.

**Tech Stack:** Python 3.13 (upsert + scripts, `uv run`, pytest), Supabase Postgres (SQL migration), Next.js App Router + TypeScript (frontend, vitest + tsc), NotebookLM MCP (NLM ordering).

**Spec:** `docs/superpowers/specs/2026-06-04-statement-view-pdf-faithful-display.md` (v5; §13 architecture, §12 G-findings, §14 G1–G5, §15 G6–G8 + P3 plan note). Read it before starting.

**Worktree:** Per the user's instruction this Build runs in an isolated git worktree (create via `superpowers:using-git-worktrees` at execution start).

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `supabase/migrations/2026060500_add_display_label.sql` | add `display_label` column (reuse existing `ordinal`) + rollback | create |
| `Tools/research-tools/_shared/source_account_class.py` | classify source_account into tag_like / synthetic / null / preserved_pdf_label | create |
| `Tools/research-tools/_shared/presentation_resolver.py` | network selection + qname-strip label/ordinal resolution from labels.json + edges_pre | create |
| `scripts/nlm_statement_order.py` | produce + read the NLM ordering artifact (AAOI BS/CF), audit gate | create |
| `scripts/upsert_sec_financials.py` | wire resolver into adapter; write display_label + ordinal; coverage hard gate | modify |
| `Tools/research-tools/_shared/sec_json_adapter.py` | attach display_label/ordinal/provenance to each adapted fact row | modify |
| `app/api/financials/[ticker]/route.ts` | return `display_label, ordinal` (source_account already returned) | modify |
| `app/components/financials-v2/useFinancialMatrix.ts` | data-driven IS/BS/CF row builder (rowId contract, derived single-quarter `derived_q2/q3/q4` attach, display-ineligible synthetic) | modify |
| `app/components/financials-v2/StatementMatrix.tsx` | render `display_label`; statement-scoped PDF number formatter | modify |
| `app/components/financials-v2/constants.ts` | `KNOWN_TICKERS += "MU"`; `DERIVED_NONGAAP_ABSOLUTE_ROWS`; keep ROWS as label fallback | modify |
| `docs/sec-financials-v2-schema.md`, `docs/financials-data-rules.md` | document display_label + ordinal contract | modify |

Phases produce working software incrementally: P1 (migration) → P2 (classifier) → P3 (resolver) → P4 (NLM order) → P5 (upsert wiring + gate) → P6 (API) → P7 (frontend) → P8 (rollout + review).

---

## Phase 1 — Migration: `display_label` column

### Task 1: Add `display_label` to `sec_financial_facts`

**Files:**
- Create: `supabase/migrations/2026060500_add_display_label.sql`
- Modify: `docs/sec-financials-v2-schema.md` (note the column)

- [ ] **Step 1: Write the migration**

```sql
-- Add PDF-faithful display label to facts. Presentation ORDER reuses the existing
-- `ordinal smallint` column (added 20260516234808). display_label is nullable
-- (frontend falls back to source_account when null). Display metadata only — NOT
-- part of the fact identity key, so no dedupe/identity impact.
alter table public.sec_financial_facts
  add column if not exists display_label text;

comment on column public.sec_financial_facts.display_label is
  'PDF-faithful line label resolved at upsert from labels.json preferred_label role; null => frontend falls back to source_account';

-- rollback:
-- alter table public.sec_financial_facts drop column if exists display_label;
```

- [ ] **Step 2: Apply via the migration runner used by the repo**

Run (per repo convention — Supabase Management API apply of the migration file, NOT ad-hoc console):
`python3 scripts/apply_migration.py supabase/migrations/2026060500_add_display_label.sql` *(if the repo lacks this helper, apply the SQL file through the same path the `20260602000000_add_ttm_duration_metrics.sql` migration used; confirm with `\d sec_financial_facts` that `display_label text` + `ordinal smallint` both exist).*

- [ ] **Step 3: Verify column exists**

Run a read-only check that `display_label` and `ordinal` are both present on `sec_financial_facts`.
Expected: both columns listed.

- [ ] **Step 4: Commit**

```bash
git add supabase/migrations/2026060500_add_display_label.sql docs/sec-financials-v2-schema.md
git commit -m "migration: add sec_financial_facts.display_label (reuse existing ordinal)"
```

---

## Phase 2 — `source_account` 4-class classifier (spec G6)

### Task 2: Classifier with the 4 classes

**Files:**
- Create: `Tools/research-tools/_shared/source_account_class.py`
- Test: `Tools/research-tools/_shared/test_source_account_class.py`

- [ ] **Step 1: Write the failing test** (covers the 5-ticker real cases from spec G6/G2)

```python
from source_account_class import classify_source_account as c

def test_tag_like():
    assert c("GrossProfit") == "tag_like"
    assert c("CostOfGoodsAndServicesSold") == "tag_like"

def test_null():
    assert c(None) == "null"
    assert c("") == "null"

def test_synthetic():
    assert c("SUM(D&A components)") == "synthetic"
    assert c("SUM(S&M+G&A)") == "synthetic"

def test_preserved_pdf_label():
    # LITE / SNDK real cases — human PDF text stored as source_account
    assert c("Income before income taxes") == "preserved_pdf_label"
    assert c("Gain on business divestiture") == "preserved_pdf_label"
    assert c("Loss before income taxes") == "preserved_pdf_label"
```

- [ ] **Step 2: Run test, verify it fails** — `uv run --with pytest python3 -m pytest Tools/research-tools/_shared/test_source_account_class.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement classifier**

```python
"""Classify a fact.source_account into one of four display-resolution classes
(spec §15 G6). Order matters: null -> synthetic -> preserved_pdf_label -> tag_like."""
import re

_QNAME_LIKE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")  # CamelCase local tag, no spaces

def classify_source_account(sa):
    if sa is None or sa == "":
        return "null"
    if sa.startswith("SUM(") or "components)" in sa or "+G&A)" in sa:
        return "synthetic"
    if _QNAME_LIKE.match(sa):
        return "tag_like"
    return "preserved_pdf_label"   # has spaces / punctuation -> already PDF text
```

- [ ] **Step 4: Run test, verify pass.**

- [ ] **Step 5: Commit** — `git commit -m "feat: source_account 4-class classifier (spec G6)"`.

---

## Phase 3 — Presentation resolver (label + ordinal from XBRL)

### Task 3: Network selection (spec §12-P2.5, G3)

**Files:**
- Create: `Tools/research-tools/_shared/presentation_resolver.py`
- Test: `Tools/research-tools/_shared/test_presentation_resolver.py`

- [ ] **Step 1: Write failing test** for `select_network(edges, statement)`:

```python
from presentation_resolver import select_network

def test_is_network_selected_case_hyphen_insensitive():
    edges = [
        {"role_uri": "http://x/role/statement-consolidated-statements-of-operations", "child_qname": "us-gaap:Revenues", "order": 1.0, "period": "FY2025"},
        {"role_uri": "http://x/role/statement-note-income-taxes-reconciliation", "child_qname": "us-gaap:Foo", "order": 1.0, "period": "FY2025"},
    ]
    net = select_network(edges, "IS")
    assert net is not None and "operations" in net.lower()

def test_bs_returns_none_when_absent():   # AAOI case
    edges = [{"role_uri": "http://ao-inc.com/role/statement-consolidated-statements-of-operations", "child_qname": "us-gaap:Revenues", "order": 1.0, "period":"FY2025"}]
    assert select_network(edges, "BS") is None
```

- [ ] **Step 2: Run, verify fail.**

- [ ] **Step 3: Implement** `select_network` (latest-10K-network primary; keyword set case/hyphen/underscore-insensitive; exclude parenthetical/details/note/reconciliation; tie-break by child∩facts overlap passed in; return None if no match):

```python
import re
_KW = {"IS": ("operations", "income"), "BS": ("balancesheet", "financialposition"), "CF": ("cashflow",)}
_EXCLUDE = ("parenthetical", "details", "note", "reconciliation")

def _norm(role): return re.sub(r"[-_]", "", role.split("/role/")[-1].lower())

def select_network(edges, statement, facts_concepts=None):
    roles = {}
    for e in edges:
        r = e.get("role_uri", "")
        n = _norm(r)
        if any(x in n for x in _EXCLUDE):
            continue
        if any(k in n for k in _KW[statement]):
            roles.setdefault(r, set()).add(e["child_qname"].split(":")[-1])
    if not roles:
        return None
    # prefer the network with the largest overlap with the ticker's facts; tie-break by size
    def score(item):
        role, childs = item
        ov = len(childs & facts_concepts) if facts_concepts else 0
        return (ov, len(childs))
    return max(roles.items(), key=score)[0]
```

- [ ] **Step 4: Run, verify pass.** **Step 5: Commit.**

### Task 4: qname-strip label + ordinal resolution, fail-closed (spec §13.2, G3)

**Files:** Modify `presentation_resolver.py`; Test `test_presentation_resolver.py`.

- [ ] **Step 1: Write failing test** for `resolve(concept_local, network_role, edges, labels)` returning `(display_label, ordinal)` + ambiguity fail-closed:

```python
from presentation_resolver import resolve_label_ordinal, AmbiguityError
import pytest

LABELS = {"us-gaap:GrossProfit": [
    {"role":"http://www.xbrl.org/2003/role/terseLabel","text":"Gross margin"},
    {"role":"http://www.xbrl.org/2003/role/totalLabel","text":"Gross profit"}]}
EDGES = [{"role_uri":"r/operations","child_qname":"us-gaap:GrossProfit","order":5.0,"preferred_label":"http://www.xbrl.org/2003/role/terseLabel"}]

def test_resolves_pdf_label_and_order():
    lbl, ordn = resolve_label_ordinal("GrossProfit", "r/operations", EDGES, LABELS)
    assert lbl == "Gross margin" and ordn == 5.0   # terseLabel = PDF wording

def test_ambiguous_local_name_fails_closed():
    edges = EDGES + [{"role_uri":"r/operations","child_qname":"intc:GrossProfit","order":6.0,"preferred_label":"x"}]
    with pytest.raises(AmbiguityError):
        resolve_label_ordinal("GrossProfit", "r/operations", edges, LABELS)
```

- [ ] **Step 2: Run, verify fail.**

- [ ] **Step 3: Implement** — match child_qname local==concept within the selected network; >1 distinct qname → `AmbiguityError` (no silent prefer, G3); use the resolved full qname for the labels lookup; pick text whose role==edge.preferred_label, fallback terseLabel→totalLabel→label→None.

- [ ] **Step 4: Run, verify pass. Step 5: Commit.**

### Task 5: synthetic/null via uni_account→canonical, with canonical-miss → needs-NLM (spec G2, G7)

**Files:** Modify `presentation_resolver.py`; Test.

- [ ] **Step 1: Write failing test** for `resolve_via_uni(uni_account, statement, network_role, edges, labels)`:

```python
from presentation_resolver import resolve_via_uni, NeedsNlmOrder
import pytest
# canonical present -> resolves
def test_uni_canonical_present(): ...   # net_income -> NetIncomeLoss present in labels+edges -> (label, ordinal)
# canonical MISS (D&A reported as components) -> raise NeedsNlmOrder (NEVER 'SUM(...)' as label)
def test_uni_canonical_miss_raises_needs_nlm():
    with pytest.raises(NeedsNlmOrder):
        resolve_via_uni("depreciation_and_amortization", "CF", "r/cashflow", edges=[], labels={})
```

- [ ] **Step 2: Run fail.** **Step 3: Implement** — map uni_account→canonical via `CANONICAL_CONCEPT` (primary candidate per `IS_TAG_MAP`/`BS_TAG_MAP`/`CF_TAG_MAP`, e.g. `net_income→NetIncomeLoss`, `shares_basic_millions→WeightedAverageNumberOfSharesOutstandingBasic`, `depreciation_and_amortization→DepreciationAndAmortization`, `selling_general_administrative→SellingGeneralAndAdministrativeExpense`); if the canonical concept is absent from labels OR not in the selected network → raise `NeedsNlmOrder` (caller routes to NLM/manual; never render `SUM(...)`). **Step 4: pass. Step 5: Commit.**

---

## Phase 4 — NLM ordering artifact (spec G1, G7, G8)

### Task 6: NLM ordering artifact schema + reader + bidirectional unmatched + uniqueness

**Files:**
- Create: `scripts/nlm_statement_order.py`
- Test: `scripts/tests/test_nlm_statement_order.py`

- [ ] **Step 1: Write failing tests** covering: artifact schema validation; match priority (exact `pdf_label`==`display_label` → normalized → source_account → uni_account); **uniqueness on uni_account tier** (>1 candidate in statement+period+display-eligible → unmatched, G8); bidirectional unmatched report (PDF line w/o fact; fact w/o PDF line).

```python
def test_uni_fallback_requires_unique_candidate():
    facts = [{"uni_account":"x","display_label":None,"source_account":None,"cell_id":"a"},
             {"uni_account":"x","display_label":None,"source_account":None,"cell_id":"b"}]
    pdf_line = {"pdf_label":"X","ordinal":1}
    res = match_pdf_line_to_fact(pdf_line, facts, display_eligible=True)
    assert res["matched_cell_id"] is None and res["unmatched_reason"] == "ambiguous_uni_account"
```

- [ ] **Step 2: Run fail. Step 3: Implement** the matcher + artifact schema `{source_doc, accession, period, form, page_or_section, statement, ordinal, pdf_label, matched_cell_id, match_method, confidence, unmatched_reason}` + reader that returns `{cell_id: ordinal}` only for the human-audited artifact. **Step 4: pass. Step 5: Commit.**

### Task 7: NLM query producer for AAOI BS/CF (run-time, human-audited)

**Files:** Modify `scripts/nlm_statement_order.py` (add the NLM query step using `mcp__notebooklm-mcp__notebook_query` against the ticker's notebook from `parse-sec-cross-check/ticker_configs/{T}.json`, single source per statement, asking for line items in PDF top-to-bottom order with page/section).

- [ ] **Step 1:** Implement `produce_nlm_order(ticker, statement)` that queries NLM for AAOI BS + CF row order, writes `{TICKER}_{STATEMENT}_nlm_order.json` (status `pending_audit`), and prints the bidirectional unmatched report.
- [ ] **Step 2:** Run for AAOI BS + CF; human reviews the artifact, flips `status: audited` + signer. (This is the §14-G1 human audit gate — NOT auto-shipped.)
- [ ] **Step 3: Commit** the audited AAOI BS/CF ordering artifacts + the producer script.

---

## Phase 5 — Upsert wiring + coverage hard gate (spec G4)

### Task 8: Adapter attaches display_label + ordinal + provenance

**Files:** Modify `Tools/research-tools/_shared/sec_json_adapter.py`; Modify `scripts/upsert_sec_financials.py`; Test `scripts/tests/test_upsert_display.py`.

- [ ] **Step 1: Write failing test**: given a facts batch (mix of all 4 classes + derived single-quarter metrics `derived_q2`/`derived_q3`/`derived_q4` + an ebitda metric), `adapt_*` produces rows where each display-eligible fact has `display_label` + `ordinal` + `provenance.ordinal_source ∈ {xbrl,nlm}`; synthetic-SUM-of-components rows are flagged `display_eligible=False` (no statement row); ebitda/fcf metric-only rows carry no statement ordinal.

- [ ] **Step 2: Run fail. Step 3: Implement**: per fact → `classify_source_account` → resolve via Task 3–5 (tag_like / preserved_pdf_label / synthetic|null) → on `NeedsNlmOrder` read the audited NLM artifact (Task 6); set `display_label`, `ordinal`, `provenance` (`ordinal_source`, `ordinal_source_doc`, `ordinal_source_period`, `ordinal_match_method`, `ordinal_artifact_hash` when NLM). Mark synthetic-SUM-of-multiple-PDF-lines `display_eligible=False`. **Step 4: pass. Step 5: Commit.**

### Task 9: Coverage hard gate (G4) — 100% of display-eligible rows, else fail loud

**Files:** Modify `scripts/upsert_sec_financials.py`; Test.

- [ ] **Step 1: Write failing test**: for a ticker×statement, if any display-eligible row lacks an `ordinal`, the upsert raises/aborts with the unmatched list (no `--apply`); denominator = display-eligible rows only (exclude YTD, metric-only, display-ineligible synthetic).
- [ ] **Step 2: fail. Step 3: Implement** the gate in the dry-run report + block `--apply` when <100%. **Step 4: pass. Step 5: Commit.**

---

## Phase 6 — API

### Task 10: Return `display_label, ordinal`

**Files:** Modify `app/api/financials/[ticker]/route.ts:96`; Test (vitest or route test).

- [ ] **Step 1:** Add `display_label, ordinal` to the `.select(...)` string (facts query) + to the `Cell` type in `types.ts`.
- [ ] **Step 2:** `tsc --noEmit` clean; a read smoke for one ticker shows the two fields.
- [ ] **Step 3: Commit.**

---

## Phase 7 — Frontend data-driven Statement view

### Task 11: Row identity + data-driven builder (spec G5, G2, P3 plan note)

**Files:** Modify `app/components/financials-v2/useFinancialMatrix.ts`; Test `app/components/financials-v2/__tests__/useFinancialMatrix.test.ts`.

- [ ] **Step 1: Write failing vitest** asserting, for statement IS/BS/CF:
  - rows are built from **direct facts** (not the hardcoded ROWS list);
  - `rowId = uni_account` for core; `uni_account + '|' + source_account` for long-tail bucket members;
  - rows sorted by `ordinal` (nulls last, stable); label = `display_label` (fallback `source_account`);
  - a derived single-quarter metric cell (`derived_q2` / `derived_q3` / `derived_q4`) **attaches by uni_account** to the display-eligible prototype (no `(uni|null)` ghost row) — Q2/Q3/Q4 are all routed into the quarterly IS/CF view (matches `QUARTERLY_PKINDS_IS_CF` + `docs/financials-data-rules.md` §quarterly IS/CF), so the test must assert all three attach, not only Q4;
  - a synthetic-SUM display-ineligible core fact builds **no** row prototype, and none of `derived_q2/q3/q4` pulls it back;
  - `ebitda`/`free_cash_flow` metric-only rows are **excluded** from IS/BS/CF.
- [ ] **Step 2: Run fail. Step 3: Implement** `buildMatrix` for IS/BS/CF accordingly; label prototype = latest-10K/NLM matched fact (deterministic, not data order). **Step 4: pass + `tsc`. Step 5: Commit.**

### Task 12: Render display_label + PDF number formatter (statement-scoped)

**Files:** Modify `app/components/financials-v2/StatementMatrix.tsx`; add a statement-scoped formatter (NOT global `fmtValue`). Test.

- [ ] **Step 1: Write failing test** for the statement formatter: `$` rows → whole number with separators (`13,643`, negatives in parens); EPS rows (`unit==='USD_per_share'`) → 2 decimals; ratio rows untouched (formatter is statement-scoped).
- [ ] **Step 2: fail. Step 3: Implement** the formatter + render `row.displayLabel`. **Step 4: pass + `tsc`. Step 5: Commit.**

### Task 13: DERIVED_NONGAAP_ABSOLUTE_ROWS subsection + KNOWN_TICKERS += MU (spec P2.3, P3)

**Files:** Modify `app/components/financials-v2/constants.ts` (`KNOWN_TICKERS += "MU"`; add `DERIVED_NONGAAP_ABSOLUTE_ROWS = ["ebitda","free_cash_flow"]`); wire a Ratios-area subsection that reads the IS `ebitda` + CF `free_cash_flow` metric rows. Test.

- [ ] **Step 1: test** MU present in KNOWN_TICKERS; ebitda/fcf render in the Derived subsection (read from IS/CF metrics, not RATIO). **Step 2–4: implement + pass + tsc. Step 5: Commit.**

---

## Phase 8 — Rollout, review, docs

### Task 14: Re-upsert 5 tickers with the gate; dry-run diff

- [ ] **Step 1:** Dry-run each of MU/INTC/AAOI/LITE/SNDK (`python3 scripts/upsert_sec_financials.py <T>`): expect `display_label`/`ordinal` populated, **existing values unchanged**, coverage gate = 100% (AAOI BS/CF via the audited NLM artifact). Any <100% → fix before apply.
- [ ] **Step 2:** `--apply` all 5 after gate green. **Step 3: Commit** any artifact/doc updates.

### Task 15: Frontend visual verification (T3 acceptance gate)

- [ ] **Step 1:** Start dev server + Claude Preview; for each of the 5 tickers, IS/BS/CF rows match the filing PDF (labels, which lines, order, number format). Record per-ticker pass.

### Task 16: Docs + Codex functional review + STATUS

- [ ] **Step 1:** Update `docs/sec-financials-v2-schema.md` + `docs/financials-data-rules.md` (display_label + ordinal contract, 4-class rule, NLM ordering provenance).
- [ ] **Step 2:** Write Codex review handoff `tmp/statement-view-pdf-faithful-review.md`; Codex functional review → converge no P1/P2.
- [ ] **Step 3:** Update `docs/STATUS.md`; finish the worktree per `superpowers:finishing-a-development-branch`.

---

## Self-Review

- **Spec coverage**: §13 architecture (P3 resolver) ✔; G1 NLM contract (Task 6/7) ✔; G2/G7 synthetic/null + canonical-miss (Task 5) ✔; G3 fail-closed (Task 4) ✔; G4 coverage gate (Task 9) ✔; G5 prototype + derived single-quarter `derived_q2/q3/q4` attach (Task 11) ✔; G6 4-class (Task 2) ✔; G8 uniqueness (Task 6) ✔; P2.3 derived subsection (Task 13) ✔; P3 plan note display-ineligible (Task 11) ✔; migration reuse ordinal (Task 1) ✔; KNOWN_TICKERS MU (Task 13) ✔; statement-scoped formatter (Task 12) ✔; docs in gate (Task 16) ✔; parse UNTOUCHED ✔ (no parse-skill file in the file map).
- **Data-layer delta since the plan was first written (2026-06-04, P2.1 shipped)**: `sec_financial_metrics` now carries `derived_q2`/`derived_q3` single-quarter IS/CF rows (not just `derived_q4`); the migration `20260604120000_add_derived_q2_q3_metrics.sql` is already applied; `useFinancialMatrix.ts` `QUARTERLY_PKINDS_IS_CF` already routes `derived_q2/q3/q4` into the quarterly view. Tasks 8 & 11 generalized accordingly (derived single-quarter attach must cover Q2/Q3/Q4). No other task is affected — the resolver/classifier/NLM/coverage-gate/formatter operate on FACTS display metadata, orthogonal to the derived metric period_kind.
- **Open follow-up (not in this plan, separate ticket)**: why `build_separated` did not capture AAOI's BS/CF presentation networks (fixing it later lets AAOI drop the NLM ordering fallback).
