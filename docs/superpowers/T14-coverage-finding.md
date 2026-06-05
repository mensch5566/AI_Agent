# T14 coverage finding — Codex review (1 bug fixed + 1 contract decision)

**Context**: T14c (real-data dry-run, read-only) of the PDF-faithful statement build revealed the
coverage hard gate (Task 9) blocking `--apply` at INTC IS 66%. Investigation split it into TWO distinct
issues. Issue 1 was a clear gate bug (FIXED). Issue 2 is a display-contract decision that needs sign-off
before implementing. Branch `worktree-statement-view-pdf-faithful`. Reviewer: Codex (adversarial).

Prod safety: only `sec_financial_facts.display_label` column was ADDED (nullable, empty). No `--apply`
has written any display_label/ordinal. No production data changed.

---

## Issue 1 — coverage gate counted NON_GAAP facts (FIXED, commit 00c474c)

**Bug**: `coverage_report` / `_is_coverage_eligible` counted Non-GAAP (8-K reconciliation) facts in the
GAAP-statement coverage denominator. But `attach_display_to_batch` only resolves GAAP facts
(`version=="GAAP"`); Non-GAAP facts are an OVERLAY keyed by uni_account onto the GAAP face rows and have
no XBRL presentation network, so they can NEVER carry an XBRL ordinal. They falsely failed the gate
(INTC: 26 of the 48 IS "missing" were Non-GAAP, all with PDF-label source_accounts like "Gross margin").

**Fix**: `_is_coverage_eligible` now excludes `version != "GAAP"`. +1 TDD test
(`test_non_gaap_facts_excluded_from_coverage_denominator`). Result: INTC IS **66.2% → 81.0%**; scripts
suite 313 passed.

**Scrutinize**: is excluding ALL Non-GAAP from the GAAP coverage gate correct? (Author claim: yes — the
spec scopes Task 8 resolution to GAAP only; Non-GAAP overlays by uni_account and is ordered via the GAAP
row it attaches to, never via its own XBRL ordinal. A separate Non-GAAP-view ordering contract, if ever
needed, is out of scope here.)

## Issue 2 — note-level GAAP facts not in the face presentation network (CONTRACT DECISION, not implemented)

After Issue 1, INTC residual missing: **IS 22 / BS 10 / CF 13**, ALL GAAP. Diagnosed: these are GAAP
facts whose XBRL concept is **NOT in the statement's face presentation network** — they are NOTE-LEVEL
sub-components that roll up into a face aggregate line.

Concrete INTC IS evidence:
- The chosen face IS network (`ConsolidatedCondensedStatementsofIncome`, 20 children, correctly ordered:
  revenue=1, GrossProfit=3, OperatingIncomeLoss=8, **NonoperatingIncomeExpense=10** ("Interest and
  other, net"), NetIncomeLoss=15, EPS=17…) DOES contain the face aggregate `NonoperatingIncomeExpense`.
- The 22 missing IS facts are 6 uni_accounts: `interest_expense` (InterestExpenseNonoperating),
  `interest_income` (InvestmentIncomeInterest), `other_nonoperating_income_expense`
  (OtherNonoperatingIncomeExpense), `amortization_of_acquired_intangibles`, `goodwill_impairment`,
  `gain_loss_on_equity_investments` — i.e. the NOTE-LEVEL breakdown of "Interest and other, net". On
  INTC's PDF FACE income statement these do NOT appear as separate lines (only the aggregate does).

**Safety verification (key)**: categorized ALL residual missing GAAP facts (IS 22 / BS 10 / CF 13) by
"concept in face network?" → **45/45 are concept-NOT-in-face-network (note-level); 0 are
in-network-but-failed-to-resolve**. So there is NO hidden resolver bug — every residual is genuinely a
note-level item, and the resolver resolves every true face concept correctly.

### Proposed rule (needs sign-off)

A **GAAP** fact whose concept is **not present in the statement's face presentation network** is
**display-INELIGIBLE** for the face statement (builds no face row, excluded from the coverage
denominator) — the same treatment as a synthetic-SUM-of-multiple (spec G7). The fact stays in storage
(feeds analytics / long-tail / Comparison view), it just isn't a FACE row.

**Boundary (important)**: this only fires when the face network IS present but the concept isn't in it.
When the face network is ABSENT for a statement (AAOI BS/CF), facts are NOT auto-hidden — they route to
the human-audited NLM ordering artifact (the existing G1 design). So:
- network present + concept in it → face row (XBRL ordinal).
- network present + concept NOT in it + no audited NLM order → **display-ineligible (note-level)** ← NEW
- network absent → NLM ordering for all face rows (unchanged).

This is principled (XBRL: the presentation network IS the face-statement definition) and PDF-faithful
(face shows the aggregate; the breakdown lives in storage/Comparison/notes, not the face). With this rule
INTC reaches 100% on all three statements.

### Scrutinize / open questions for Codex

1. Is "GAAP concept not in present face network → display-ineligible" the right contract, or should some
   of these (e.g. interest_expense) still be face rows via NLM? (Author: no — the PDF face shows the
   aggregate; forcing the components onto the face would be LESS faithful, not more.)
2. Risk: could a genuine face line ever be excluded because `select_network` picked the wrong/condensed
   network? (Author: verified 0 such cases for INTC; but the rule should still be validated across all 5
   tickers' dry-runs before apply — a true face line wrongly hidden would be a silent data-loss.)
3. Where to implement: `attach_display_metadata` (set `display_eligible=False` when network_role is not
   None and ordinal is still None after the NLM fallback). Plus a log line so a human can audit what was
   classified note-level (no silent truncation).
4. Should the note-level classification be LOGGED per ticker for human review (vs silent)? (Author leans
   yes — print the note-level list in the dry-run so the user can confirm nothing real was dropped.)

## State / next steps (after Issue 2 sign-off)

1. Implement Issue 2 rule (TDD in attach_display_metadata + adjust coverage test expectations).
2. Re-dry-run ALL 5 tickers; require 100% per statement (residual, if any, must be genuine
   network-absent → audited NLM). AAOI BS/CF still need the audited NLM artifact (T7 live run + human
   audit).
3. Then the gated production rollout: T14d `--apply` (user auth) → T15 visual verify → T16 docs/Codex/finish.

Branch state: T1–T13 + vitest + Issue 1 fix. 313 py + 34 vitest + tsc green. Commits up to 00c474c.

---

## Issue 2 IMPLEMENTED (commit aceb8d8) + full 5-ticker dry-run residual map

Converged Issue 2 shipped (accepted-face-network SET = 10-K∪10-Q, non-condensed tie-break, narrow
tag_like-only note-level exclusion + `provenance.display_exclusion_reason` + dry-run audit print). 340 py
+ 34 vitest + tsc green. Read-only 5-ticker dry-run coverage:

| ticker | IS | BS | CF |
|---|---|---|---|
| **MU**   | 100% | 100% | 100% |
| INTC | 100% | 100% | 93.2% (5) |
| SNDK | 90.9% (8) | 100% | 100% |
| LITE | ~~95.7% (24)~~ → **100%** | 100% | 100% |
| AAOI | 100% | 0% (357) | 0% (159) |

> **UPDATE (Path-to-100% item 1 SHIPPED)** — LITE IS now 100% (558/558).
> The 24 `income_before_taxes` preserved_pdf_label periods now borrow their
> face ordinal via the uni→canonical concept (commit below). Verified by
> read-only dry-run: LITE IS/BS/CF all 100%, gate PASSED; MU/INTC/SNDK/AAOI
> byte-identical to the table above (no regression). Only items 2–4 remain.

MU is fully PDF-faithful end-to-end → the contract is sound. Note-level exclusions printed per run (INTC
50, etc.), all genuine sub-components. Remaining residuals (all correctly fail-loud, NOT auto-hidden):

- **INTC CF — net_income ×5 (class `null`)**: INTC's CF starts with `ProfitLoss` (net income incl NCI),
  NOT `NetIncomeLoss`. The carried-in net_income (NetIncomeLoss canonical) isn't a CF face concept.
  Fix options: (a) context-aware canonical (net_income→ProfitLoss in CF) — risky (different line item);
  (b) NLM order for INTC CF; (c) leave as needs-NLM.
- **SNDK IS — long-tail ×8 (class `preserved_pdf_label`)**: `nonoperating_long_tail` /
  `operating_expense_long_tail` disclosed lines whose source_account is PDF text (no XBRL tag to match).
  Genuine face rows → need NLM ordinal (or xbrl_tag-based resolution if the parse carries it).
- **LITE IS — income_before_taxes ×24 (class `preserved_pdf_label`)**: a CORE face line stored with the
  PDF label "Income before income taxes" (spec G6). The XBRL concept
  (`IncomeLossFromContinuingOperationsBeforeIncomeTaxes…`) IS in the IS face network. Fix: for
  preserved_pdf_label facts, ALSO try the uni→canonical ordinal path (`resolve_via_uni`) + extend
  `CANONICAL_CONCEPT` with `income_before_taxes`. Cleanest pure-XBRL fix (no NLM needed).
- **AAOI BS/CF — 516 (no presentation network)**: the designed NLM-ordering case (Task 6/7). Needs the
  live NLM query (`produce_nlm_order` AAOI BS+CF) + **human audit** of the artifact.

### Path to 100% (per residual class — iterative)
1. ~~preserved_pdf_label core lines (LITE income_before_taxes)~~ ✅ **DONE** —
   added `resolve_via_uni_any` (multi-network uni→canonical ORDINAL borrow, laxer
   than `resolve_via_uni`: no labels guard since the preserved fact owns its
   PDF-text label) + extended `CANONICAL_CONCEPT["income_before_taxes"]`. The
   preserved branch borrows the face ordinal when its local-name match misses,
   keeping the period-exact PDF wording ("Income"/"Loss before income taxes") as
   the display label, stamping `ordinal_match_method=xbrl_presentation_via_uni`
   for audit. SNDK long-tail (uni not in CANONICAL_CONCEPT) → NeedsNlmOrder →
   unchanged NLM routing (safety verified by test + dry-run). +8 tests, 348 py.
2. **INTC CF net_income ×5** (NEXT — needs a small design call): INTC's CF starts
   with `ProfitLoss` (net income incl NCI), not `NetIncomeLoss`; the carried-in
   net_income (NetIncomeLoss canonical) isn't a CF face concept. Options: (a)
   context-aware canonical (net_income→ProfitLoss in CF) — risky, different line
   item; (b) NLM order for INTC CF; (c) leave as needs-NLM. **Decision pending
   user.**
3. SNDK long-tail ×8 + AAOI BS/CF ×516: NLM ordering artifacts → **human audit
   gate** (T7 live run). Cannot be autonomous.
4. Re-dry-run all 5 → 100% → then T14d --apply (user auth) → T15 visual → T16.

State: branch T1–T13 + vitest + Issue 1 (00c474c) + Issue 2 (aceb8d8). Prod unchanged (display_label
column only, empty). No --apply run.
