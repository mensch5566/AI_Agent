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
from typing import Iterable
import re

from derive_types import Candidate

_FY_RE = re.compile(r"^FY(\d{4})$")


def _fy_year(period: str) -> str | None:
    m = _FY_RE.match(period)
    return m.group(1) if m else None


def q4_candidates(facts: Iterable) -> list[Candidate]:
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
            q4_end = _q4_period_end(fy)
            q4_start = _q4_period_start(fy)

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
                        _input_dict(fy_fact),
                        _input_dict(nm),
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
                        _input_dict(fy_fact),
                        _input_dict(q1), _input_dict(q2), _input_dict(q3),
                    ],
                    extras={"formula": f"FY{fy} - Q1_FY{fy} - Q2_FY{fy} - Q3_FY{fy}"},
                ))
            # else: skip — missing inputs (per design §3.4)
    return out


def _input_dict(fact) -> dict:
    return {
        "cell_id": fact.cell_id,
        "uni_account": fact.uni_account,
        "period": fact.period,
        "value": fact.value,
        "status": fact.status,
    }


def _units_match(*facts) -> bool:
    units = {f.unit for f in facts}
    return len(units) == 1


def _q4_period_start(fy: str) -> str:
    # FY ending Dec → Q4 starts Oct 1. For non-Dec FY ends this isn't exact,
    # but derive-base reads period_end from the FY input; period_start is a
    # nice-to-have audit field. v1 keeps it simple; we'll refine if a non-
    # calendar-FY ticker shows mismatched audit dates.
    return f"{fy}-10-01"


def _q4_period_end(fy: str) -> str:
    return f"{fy}-12-31"
