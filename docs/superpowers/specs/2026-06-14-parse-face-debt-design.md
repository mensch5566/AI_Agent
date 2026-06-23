# parse-10QK-gaap face-debt exposure — converged design v2 (Argue 2026-06-14)

**SUPERSEDES the round-1 design.** Round 1 (MU evidence only) converged on a
finance-lease-presence guard that REGRESSED LITE (11 periods lost long_term_debt).
Round 2 (`facedebt-r2d`, architect=Claude Opus vs skeptic=Codex GPT-5.5, 5 rounds /
8m7s, **status=consensus**, score 91.82, 12/12 claims accepted by BOTH seats 0.89–1.00)
replaced it with a structure-aware, per-period aggregate-presence rule.
Transcript: `~/.config/argue/facedebt-r2d-{result.json,summary.md}`.

## The two real structures (ground truth, companyconcept us-gaap)

### MU = AGGREGATE structure (Q1_FY2025, end 2024-11-28)
- `DebtCurrent` = 533,000,000 ← face "Current debt" (aggregate)
- `LongTermDebtAndCapitalLeaseObligations` = 13,252,000,000 ← face "Long-term debt" (aggregate)
- `LongTermDebt` = 11,306,000,000 ← bonds-only DECOMPOSITION (component of the aggregate)
- `FinanceLeaseLiabilityNoncurrent` = 2,052,000,000 ← finance-lease DECOMPOSITION (component)
- `FinanceLeaseLiabilityCurrent` = 427,000,000 ← component inside DebtCurrent 533
→ aggregate tags ARE the face lines; decomposed tags are their components.

### LITE = DECOMPOSED/STANDALONE structure
- FY2024 (2024-06-29): `LongTermDebtNoncurrent` = 2,503,200,000; NO aggregate, NO finance lease.
- FY2020 (2020-06-27): bare `LongTermDebt` = 1,538,600,000 ← IS the face line (standalone);
  `FinanceLeaseLiabilityCurrent` = 600,000 is a TINY SEPARATE line; NO aggregate tag.
- FY2019: `SecuredLongTermDebt` = 484,000,000 (filer-specific, discovered by tag-discovery).
→ bare `LongTermDebt`/`LongTermDebtNoncurrent`/`SecuredLongTermDebt` IS the face debt, NOT a
partial of any aggregate. A finance-lease-presence guard WRONGLY deletes FY2020's 1,538.6M.

## The GENERAL rule (consensus)

### 1. Candidate lists — per-normalized-period first-match (after period/unit/dimension filtering)
- `long_term_debt` ← `[LongTermDebtAndCapitalLeaseObligations, LongTermDebtNoncurrent,
  LongTermDebt, <vetted discovered/override standalone LT-debt tags e.g. SecuredLongTermDebt>]`
- `current_debt` ← `[DebtCurrent, LongTermDebtCurrent]`
- **No finance-lease-presence guard. It is eliminated entirely.**

### 2. Suppression trigger — accepted same-period aggregate, per bucket, independent
A decomposed component is suppressed from core + footing for a period **only when that same
normalized period (unit + dimensions + period identity + debt domain) has an ACCEPTED
corresponding AGGREGATE face row** — i.e. the aggregate was the SELECTED face fact after
filtering, not merely "a tag that exists in the filer":
- LT components (`FinanceLeaseLiabilityNoncurrent`, bare `LongTermDebt` when it is a component)
  → suppressed **only under** `LongTermDebtAndCapitalLeaseObligations`.
- current components (`FinanceLeaseLiabilityCurrent`, current-LTD component)
  → suppressed **only under** `DebtCurrent`.
- The two signals are evaluated **independently per bucket, per period** — never coupled into a
  filer-level flag. A filer may report `DebtCurrent` but decompose LT, or report the aggregate
  in some periods and decompose in others (ASC 842 transition). MU reports both; do not couple.
- When no corresponding aggregate is accepted that period, components REMAIN separate core
  lines (this is the LITE non-regression path).

### 3. Containment guard (sanity, before suppression)
Before suppressing a same-period same-domain component under an accepted aggregate, compare
normalized values **only when unit, dimensions, period identity, and scale are comparable**.
Suppress only when `component <= aggregate`. If comparison is impossible or `component >
aggregate`: do NOT foot the component beside the aggregate; emit the accepted aggregate face row
if unambiguous; flag the component/period for review. This guard is a sanity check, NOT proof of
containment, and never authorizes parse derivation.

### 4. Single-emission contract
`LongTermDebtCurrent` can serve as both a `current_debt` fallback AND a
`current_portion_of_long_term_debt` component. Enforce single-emission: one concept fact must
populate **at most one** core row per period.

### 5. Override / discovered tags
`SecuredLongTermDebt` survives as a vetted standalone override when no higher-priority candidate
is present. Future discovered tags are eligible only after tag-discovery / override classifies
them as standalone LT debt; unclassified large debt-like tags are flagged, never silently mapped.
Discovered aggregate-like tags must NOT become suppression triggers without explicit TDD.

### 6. Fail-closed ambiguity
When same-period same-domain candidates conflict without a clear aggregate-component,
equivalent-tag, or vetted-standalone relationship: emit the accepted unambiguous face fact if
one exists, exclude ambiguous lower-priority / unclassified discovered facts from core+footing,
flag for review, and never synthesize total debt in parse.

### 7. Operating leases
`OperatingLeaseLiabilityCurrent` / `OperatingLeaseLiabilityNoncurrent` are NEVER debt candidates
and never footed into `current_debt` / `long_term_debt`. Explicit test required.

### 8. total_debt
`current_debt` (533) and `long_term_debt` (13,252) are direct XBRL facts exposed by parse.
`total_debt = current_debt + long_term_debt = 13,785` is **derive-base only**; parse never
synthesizes it (parse-never-derives iron law).

### 9. Provenance
Each emitted or suppressed debt fact carries provenance: selected concept, normalized period,
debt domain, role (`aggregate_face` / `standalone_face` / `component`), and suppression reason.
Needed to debug T3 failures (MU component suppression, LITE standalone preservation) without
inferring totals.

## Skill-doc pattern wording (paste into skill.md)
> US filers report interest-bearing debt in per-period **aggregate** or **standalone/decomposed**
> structures, and one filer can switch across periods. Select face rows per normalized
> period/unit/dimensions by first-match: `long_term_debt=[LongTermDebtAndCapitalLeaseObligations,
> LongTermDebtNoncurrent, LongTermDebt, vetted standalone overrides such as SecuredLongTermDebt]`;
> `current_debt=[DebtCurrent, LongTermDebtCurrent]`. Suppress decomposed components from
> core+footing **only when the same normalized period/unit/dimensions has an accepted
> corresponding aggregate face row**: LT components only under
> `LongTermDebtAndCapitalLeaseObligations`; current components only under `DebtCurrent`. Require
> comparable `component <= aggregate` for automatic suppression; if comparability fails or
> `component > aggregate`, keep the accepted aggregate if unambiguous, do not foot the component
> beside it, and flag for review. **Never delete bare `LongTermDebt` because a finance lease
> exists.** Enforce single-emission so one concept fact populates at most one core row per period.
> Exclude operating leases. `total_debt` is derive only, never parsed.

## TDD matrix (required — grounded in MU + LITE values)
1. **MU aggregate**: 2024-11-28 selects `current_debt=DebtCurrent`=533,000,000 and
   `long_term_debt=LongTermDebtAndCapitalLeaseObligations`=13,252,000,000; suppresses
   `LongTermDebt`=11,306,000,000 + `FinanceLeaseLiabilityNoncurrent`=2,052,000,000 under the LT
   aggregate; suppresses `FinanceLeaseLiabilityCurrent`=427,000,000 under `DebtCurrent`; all
   suppressed components excluded from core+footing; parse writes NO total_debt.
2. **LITE FY2020 standalone**: keeps bare `LongTermDebt`=1,538,600,000 despite
   `FinanceLeaseLiabilityCurrent`=600,000 (no aggregate → no suppression).
3. **LITE FY2024 standalone**: keeps `LongTermDebtNoncurrent`=2,503,200,000.
4. **LITE FY2019 override**: keeps vetted `SecuredLongTermDebt`=484,000,000.
5. **Containment violation**: component > aggregate (or non-comparable) → component NOT footed
   beside aggregate, flagged, no double-count.
6. **Independent bucket suppression**: aggregate present in one bucket does not suppress the
   other bucket's components.
7. **LongTermDebtCurrent single-emission**: one fact cannot populate both current_debt and the
   current-portion component in the same period.
8. **Cross-period isolation**: aggregate accepted in another period must NOT suppress current
   period's components.
9. **Dimension/unit mismatch**: an aggregate at different dimensions/unit does not trigger
   suppression.
10. **Operating lease excluded**: an operating-lease tag present in a period enters no debt row.
