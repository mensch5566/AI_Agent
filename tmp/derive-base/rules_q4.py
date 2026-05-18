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


def _fy_year(period: str) -> str | None:
    m = _FY_RE.match(period)
    return m.group(1) if m else None


def q4_candidates(facts: Iterable["FactRow"]) -> list[Candidate]:
    """Emit Q4 candidates for every (uni_account, fy) where inputs are sufficient."""
    by_key: dict[tuple, dict[str, object]] = {}
    for f in facts:
        if f.version != "GAAP":
            continue
        if f.statement not in ("IS", "CF"):
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

            if nm is not None and _units_match(fy_fact, nm):
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
                    extras={"formula": f"FY{fy} - 9M_FY{fy}"},
                ))
            elif q1 is not None and q2 is not None and q3 is not None \
                    and _units_match(fy_fact, q1, q2, q3):
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
                    extras={"formula": f"FY{fy} - Q1_FY{fy} - Q2_FY{fy} - Q3_FY{fy}"},
                ))
            # else: skip — missing inputs (per design §3.4)
    return out


def _units_match(*facts) -> bool:
    units = {f.unit for f in facts}
    return len(units) == 1


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
