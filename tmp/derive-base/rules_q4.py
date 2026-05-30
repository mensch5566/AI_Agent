"""GAAP Q4 single-quarter reconstruction rules.

Two formulas, in priority order:
  1. Q4 = FY - 9M           (prefer; most filings have 10-Q YTD)
  2. Q4 = FY - (Q1+Q2+Q3)   (fallback)

Scope (design §3.1):
  - Only GAAP version (Non-GAAP Q4 derive is out of scope for v1)
  - Only IS / CF statements (BS Q4 is direct period-end snapshot)
  - Only duration-style uni_accounts (we don't filter by uni_account here;
    caller passes whatever facts they have, and a Q4 candidate is emitted
    for each (uni_account, FY) whose inputs are present)
"""
from __future__ import annotations
from collections.abc import Iterable
from datetime import date, timedelta
from typing import TYPE_CHECKING
import re

from derive_types import Candidate, input_dict_from_fact

if TYPE_CHECKING:
    from _shared.sec_json_adapter import FactRow  # noqa: F401

_FY_RE = re.compile(r"^FY(\d{4})$")

# Allowlist — Q4 = FY − 9M is mathematically valid only for additive duration
# amounts in USD. Anything else (shares WASO, per-share EPS, ratios, %, long-
# tail buckets) is rejected. Canonical adapter normalizes pct/ratio→`Pure`,
# shares→`thousands_shares` / `millions_shares`; an allowlist is robust to
# those canonical labels in a way `_DENY_UNITS` was not.
_ADDITIVE_Q4_UNITS = frozenset({
    "USD_thousands",
    "USD_millions",
})


def _is_denied(uni_account: str, unit: str) -> bool:
    # Allowlist on unit: anything outside the additive set is denied.
    if unit not in _ADDITIVE_Q4_UNITS:
        return True
    # Long-tail buckets aggregate multiple source_accounts into one uni_account,
    # so Q4 = FY−9M would discard which source contributed and collapse
    # provenance on upsert; deny independently of unit.
    if uni_account.endswith("_long_tail"):
        return True
    return False


def _fy_year(period: str) -> str | None:
    m = _FY_RE.match(period)
    return m.group(1) if m else None


def q4_candidates(
    facts: Iterable["FactRow"],
    *,
    skips_collector: list | None = None,
) -> list[Candidate]:
    """Emit Q4 candidates for every (uni_account, fy) where inputs are sufficient.

    Optional `skips_collector` is appended (not replaced) with diagnostic
    dicts for inputs that were rejected after passing the basic gate. This
    is the only way a reviewer can tell that a row WAS considered but
    intentionally dropped — vs simply missing inputs. Codex round-4 F3.

    Skip reason codes:
      - `concept_mismatch_skip`: FY/9M/Q inputs differ in normalized
        source_account/xbrl_tag (e.g. INTC FY=IncreaseDecreaseInEquity
        SecuritiesFvNi vs Q=EquitySecuritiesFvNiGainLoss).
      - `unit_mismatch_skip`: inputs differ in unit (FY in millions vs Q
        in thousands — canonical adapter should prevent this).
    """
    by_key: dict[tuple, dict[str, object]] = {}
    for f in facts:
        if f.version != "GAAP":
            continue
        if f.statement not in ("IS", "CF"):
            continue
        if _is_denied(f.uni_account, f.unit):
            continue
        key = (f.ticker, f.statement, f.uni_account, f.unit)
        slot = by_key.setdefault(key, {"facts_by_period": {}})
        slot["facts_by_period"][f.period] = f

    out: list[Candidate] = []
    for (ticker, stmt, uni, unit), slot in by_key.items():
        fbp = slot["facts_by_period"]
        for period, fact in list(fbp.items()):
            fy = _fy_year(period)
            if fy is None:
                continue
            q4_period = f"Q4_FY{fy}"
            if q4_period in fbp:
                continue  # already direct
            fy_fact = fact
            nm = fbp.get(f"9M_FY{fy}")
            q1 = fbp.get(f"Q1_FY{fy}")
            q2 = fbp.get(f"Q2_FY{fy}")
            q3 = fbp.get(f"Q3_FY{fy}")
            q4_end = _q4_end_from_fy(fy_fact)
            q4_start = _q4_start_from_q3_or_fy(q3, q4_end)

            # Carry source concept identity from FY fact so Pass 3 calc-
            # linkbase can match this derived Q4 row as a child.
            src_acct = getattr(fy_fact, "source_account", "") or ""
            xbrl_tag = getattr(fy_fact, "xbrl_tag", "") or ""

            def _record_skip(reason: str, inputs_) -> None:
                if skips_collector is None:
                    return
                skips_collector.append({
                    "ticker": ticker, "period": q4_period, "statement": stmt,
                    "uni_account": uni, "unit": unit, "reason": reason,
                    "inputs": [{
                        "period": getattr(i, "period", None),
                        "source_account": getattr(i, "source_account", None),
                        "xbrl_tag": getattr(i, "xbrl_tag", None),
                        "unit": getattr(i, "unit", None),
                    } for i in inputs_],
                })

            if nm is not None:
                if not _units_match(fy_fact, nm):
                    _record_skip("unit_mismatch_skip", [fy_fact, nm])
                elif not _concepts_match(fy_fact, nm):
                    _record_skip("concept_mismatch_skip", [fy_fact, nm])
                else:
                    v = fy_fact.value - nm.value
                    out.append(Candidate(
                        ticker=ticker, period=q4_period, period_kind="derived_q4",
                        period_start=q4_start, period_end=q4_end,
                        statement=stmt, version="GAAP", uni_account=uni,
                        value=v, unit=unit,
                        rule_id="Q4_FY_MINUS_9M", rule_priority=1,
                        chain_depth=1, chained=False,
                        inputs=[
                            input_dict_from_fact(fy_fact),
                            input_dict_from_fact(nm),
                        ],
                        source_account=src_acct, xbrl_tag=xbrl_tag,
                        extras={"formula": f"FY{fy} - 9M_FY{fy}"},
                    ))
                    continue
            if q1 is not None and q2 is not None and q3 is not None:
                if not _units_match(fy_fact, q1, q2, q3):
                    _record_skip("unit_mismatch_skip", [fy_fact, q1, q2, q3])
                elif not _concepts_match(fy_fact, q1, q2, q3):
                    _record_skip("concept_mismatch_skip", [fy_fact, q1, q2, q3])
                else:
                    v = fy_fact.value - q1.value - q2.value - q3.value
                    out.append(Candidate(
                        ticker=ticker, period=q4_period, period_kind="derived_q4",
                        period_start=q4_start, period_end=q4_end,
                        statement=stmt, version="GAAP", uni_account=uni,
                        value=v, unit=unit,
                        rule_id="Q4_FY_MINUS_Q1Q2Q3", rule_priority=2,
                        chain_depth=1, chained=False,
                        inputs=[
                            input_dict_from_fact(fy_fact),
                            input_dict_from_fact(q1), input_dict_from_fact(q2), input_dict_from_fact(q3),
                        ],
                        source_account=src_acct, xbrl_tag=xbrl_tag,
                        extras={"formula": f"FY{fy} - Q1_FY{fy} - Q2_FY{fy} - Q3_FY{fy}"},
                    ))
            # else: silent skip — missing inputs (per design §3.4)
    return out


def _units_match(*facts) -> bool:
    units = {f.unit for f in facts}
    return len(units) == 1


def _concepts_match(*facts) -> bool:
    """Codex round-3 F1: same uni_account can be populated by different XBRL
    concepts across periods (e.g. INTC FY uses `IncreaseDecreaseInEquity
    SecuritiesFvNi` but Q1/Q2/Q3 use `EquitySecuritiesFvNiGainLoss`).
    Subtracting these is arithmetically possible but semantically wrong.
    Require the normalized concept identity (local-name of source_account
    or xbrl_tag) to match across all inputs.

    Exception: NLM-audited rows (apply_audit-written) carry the PDF label as
    `source_account` but the value's semantic identity is anchored by
    `uni_account` (auditor confirmed). Different PDFs may use different
    wording for the same line item across years (e.g. "Income before income
    taxes" vs "Loss before income taxes") — treat all audit-sourced inputs
    as concept-compatible.
    """
    def _local(s: str | None) -> str:
        return (s or "").rsplit(":", 1)[-1]
    # If ANY input is audit-sourced, fall back to uni_account+unit identity
    # (already enforced by caller). PDF-label variation is not a concept change.
    if any(
        (getattr(f, "provenance", None) or {}).get("audit_source") or
        getattr(f, "audit_source", None)
        for f in facts
    ):
        return True
    concepts = set()
    for f in facts:
        concept = _local(getattr(f, "source_account", "")) or _local(getattr(f, "xbrl_tag", ""))
        concepts.add(concept)
    # If all inputs lack source/tag identity (test fixtures, allowlist-only),
    # treat as compatible — caller already has uni_account + unit guards.
    if concepts == {""}:
        return True
    return len(concepts) == 1


def _q4_end_from_fy(fy_fact) -> str:
    # Q4 ends when FY ends. Inherit verbatim from the FY input's period_end so
    # non-Dec fiscal years (e.g., SNDK FY-end June) get correct CY mapping.
    return fy_fact.period_end


def _q4_start_from_q3_or_fy(q3, q4_end: str) -> str:
    # Prefer (Q3.period_end + 1 day) when Q3 is present; this is exact.
    # Fall back to (Q4_end - ~92 days) when Q3 is missing — audit-only field.
    if q3 is not None and q3.period_end:
        try:
            return (date.fromisoformat(q3.period_end) + timedelta(days=1)).isoformat()
        except ValueError:
            pass
    try:
        return (date.fromisoformat(q4_end) - timedelta(days=92)).isoformat()
    except ValueError:
        return ""
