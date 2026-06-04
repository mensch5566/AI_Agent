"""GAAP Q2 / Q3 single-quarter reconstruction rules.

Companion to rules_q4. After the 2026-05-17 "YTD first-class" parse change,
the parser emits 6M / 9M YTD duration rows as first-class facts and no longer
silently back-computes single quarters. derive-base must therefore rebuild the
single quarters from the disclosed YTD cumulatives:

  Q2 = 6M − Q1     (single formula; H1 YTD minus first quarter)
  Q3 = 9M − 6M     (single formula; 9M YTD minus H1 YTD)

(Q1 needs no reconstruction — it IS the first single quarter. Q4 lives in
rules_q4 because its inputs/fallbacks differ: FY − 9M, or FY − Q1Q2Q3.)

Scope mirrors rules_q4 exactly (design §3.1):
  - GAAP only (Non-GAAP single-quarter derive is out of scope for v1)
  - IS / CF only (BS Q2/Q3 are direct period-end snapshots, not durations)
  - additive USD duration amounts only (the shared `_is_denied` allowlist
    rejects per-share / ratios / share counts / long-tail buckets)
  - concept + unit identity required across the two inputs (a YTD cumulative
    and a quarter/YTD subtrahend must be the same XBRL concept to subtract)
  - never emitted when the single quarter is already directly disclosed

Each rule reads only directly-disclosed facts (the caller passes facts that
already include Pass-1 identity winners but NOT other Pass-2 single quarters),
so Q2/Q3/Q4 are independent and never chain on one another.
"""
from __future__ import annotations
from collections.abc import Iterable
from datetime import date, timedelta
from typing import TYPE_CHECKING

from derive_types import Candidate, input_dict_from_fact
# Reuse the proven Q4 guards verbatim — identical semantics, single source.
from rules_q4 import _is_denied, _units_match, _concepts_match, _fy_year

if TYPE_CHECKING:
    from _shared.sec_json_adapter import FactRow  # noqa: F401


# (rule_id, priority, target single-quarter, minuend YTD label, subtrahend label)
# minuend/subtrahend are resolved per fiscal year against the disclosed facts.
_Q2Q3_SPECS = (
    # target_q, derived_kind, minuend_prefix, subtrahend_prefix, rule_id
    ("Q2", "derived_q2", "6M", "Q1", "Q2_6M_MINUS_Q1"),
    ("Q3", "derived_q3", "9M", "6M", "Q3_9M_MINUS_6M"),
)


def q2q3_candidates(
    facts: Iterable["FactRow"],
    *,
    skips_collector: list | None = None,
) -> list[Candidate]:
    """Emit Q2/Q3 candidates for every (uni_account, fy) with sufficient inputs.

    Optional `skips_collector` is appended (not replaced) with diagnostic dicts
    for inputs rejected after passing the basic gate (unit / concept mismatch),
    mirroring rules_q4 so a reviewer can tell a row was *intentionally* dropped
    vs simply missing inputs.
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
        # fiscal years present among this key's facts (any YTD/FY/quarter row)
        fys = {fy for p in fbp if (fy := _fy_year_any(p)) is not None}
        for fy in fys:
            for _q, derived_kind, minuend_pfx, subtr_pfx, rule_id in _Q2Q3_SPECS:
                target_period = f"{_q}_FY{fy}"
                if target_period in fbp:
                    continue  # already direct — never override disclosed
                minuend = fbp.get(f"{minuend_pfx}_FY{fy}")
                subtr = fbp.get(f"{subtr_pfx}_FY{fy}")
                if minuend is None or subtr is None:
                    continue  # silent skip — missing inputs

                if not _units_match(minuend, subtr):
                    _record_skip(skips_collector, ticker, target_period, stmt,
                                 uni, unit, "unit_mismatch_skip", [minuend, subtr])
                    continue
                if not _concepts_match(minuend, subtr):
                    _record_skip(skips_collector, ticker, target_period, stmt,
                                 uni, unit, "concept_mismatch_skip", [minuend, subtr])
                    continue

                value = minuend.value - subtr.value
                period_end = minuend.period_end           # quarter ends when YTD ends
                period_start = _start_after(subtr)        # day after subtrahend's end
                # Carry concept identity from the YTD minuend so Pass 3 calc-
                # linkbase can match this derived row as a child.
                src_acct = getattr(minuend, "source_account", "") or ""
                xbrl_tag = getattr(minuend, "xbrl_tag", "") or ""

                out.append(Candidate(
                    ticker=ticker, period=target_period, period_kind=derived_kind,
                    period_start=period_start, period_end=period_end,
                    statement=stmt, version="GAAP", uni_account=uni,
                    value=value, unit=unit,
                    rule_id=rule_id, rule_priority=1,
                    chain_depth=1, chained=False,
                    inputs=[
                        input_dict_from_fact(minuend),
                        input_dict_from_fact(subtr),
                    ],
                    source_account=src_acct, xbrl_tag=xbrl_tag,
                    extras={"formula": f"{minuend_pfx}_FY{fy} - {subtr_pfx}_FY{fy}"},
                ))
    return out


_FY_SUFFIX_LEN = len("_FY2024")


def _fy_year_any(period: str) -> str | None:
    """Extract the 4-digit fiscal year from any period label of the form
    `<prefix>_FY{yyyy}` (Q1_FY2024 / 6M_FY2024 / 9M_FY2024 / FY2024).

    Plain `FY2024` is handled by rules_q4._fy_year; here we accept both the
    bare and the prefixed forms so a fiscal year is discovered from whichever
    rows exist for this key.
    """
    bare = _fy_year(period)
    if bare is not None:
        return bare
    if "_FY" in period:
        tail = period.rsplit("_FY", 1)[-1]
        if len(tail) == 4 and tail.isdigit():
            return tail
    return None


def _start_after(subtr) -> str:
    """Single quarter starts the day after the subtrahend period ends:
      Q2 starts after Q1 ends; Q3 starts after 6M (H1) ends.
    Audit-only field; returns "" on an unparseable date."""
    pe = getattr(subtr, "period_end", None)
    if not pe:
        return ""
    try:
        return (date.fromisoformat(pe) + timedelta(days=1)).isoformat()
    except ValueError:
        return ""


def _record_skip(collector, ticker, period, stmt, uni, unit, reason, inputs_) -> None:
    if collector is None:
        return
    collector.append({
        "ticker": ticker, "period": period, "statement": stmt,
        "uni_account": uni, "unit": unit, "reason": reason,
        "inputs": [{
            "period": getattr(i, "period", None),
            "source_account": getattr(i, "source_account", None),
            "xbrl_tag": getattr(i, "xbrl_tag", None),
            "unit": getattr(i, "unit", None),
        } for i in inputs_],
    })
