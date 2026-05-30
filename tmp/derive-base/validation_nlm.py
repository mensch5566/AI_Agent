"""NLM validation for derived metrics.

Reads parse-sec-cross-check's `raw_nlm_responses/{period}.json` (each one a
list of {label, value, unit} extracted from a 10-Q/10-K PDF by NotebookLM),
maps PDF labels to uni_account via the cross-check ticker config's
`label_to_key`, then compares derived metric values against the NLM raw
values for the same (uni_account, period). Output: a markdown report
listing pass/fail per (period, uni_account) within tolerance.

Used by derive-base to surface arithmetic errors in identity rules
(e.g. IDENTITY_IBT_FROM_OP_PLUS_NONOP) — if a derived value doesn't match
what the PDF directly disclosed, the rule may have a bug or a sign-
convention error.

Why not in cross-check itself? Cross-check is a raw-XBRL ↔ raw-PDF gate.
Validating derived metrics is derive-base's responsibility because only
derive-base knows which values it produced.
"""

from __future__ import annotations

import json
from pathlib import Path


DEFAULT_TOLERANCE_USD_MILLIONS = 0.5  # PDF rounding tolerance
DEFAULT_TOLERANCE_USD_PER_SHARE = 0.01
DEFAULT_TOLERANCE_PCT = 0.001  # for ratios (Pure units)


def _tolerance_for_unit(unit: str) -> float:
    if unit == "USD_per_share":
        return DEFAULT_TOLERANCE_USD_PER_SHARE
    if unit == "Pure":
        return DEFAULT_TOLERANCE_PCT
    return DEFAULT_TOLERANCE_USD_MILLIONS


def load_cross_check_label_map(cross_check_config_path: Path) -> dict[str, str]:
    """Read parse-sec-cross-check's {TICKER}.json and return label_to_key
    (PDF label → uni_account). Filters out null mappings (intentional skips)."""
    cfg = json.loads(cross_check_config_path.read_text())
    raw = cfg.get("label_to_key", {})
    return {k: v for k, v in raw.items() if v and k != "_note"}


def load_nlm_responses(run_folder: Path) -> dict[str, list[dict]]:
    """Read all raw_nlm_responses/{period}.json files into {period: [rows]}.
    Each row has keys: label, value, unit."""
    rd = run_folder / "raw_nlm_responses"
    if not rd.exists():
        return {}
    out: dict[str, list[dict]] = {}
    for fp in sorted(rd.glob("*.json")):
        period = fp.stem
        try:
            rows = json.loads(fp.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(rows, list):
            out[period] = rows
    return out


def _q4_from_fy_and_ytd(period: str) -> tuple[str, list[str]] | None:
    """If period is `Q4_FY{y}`, return (FY{y}, [Q1_FY{y}, Q2_FY{y}, Q3_FY{y}]).
    Otherwise None. Used to reconstruct Q4 from PDF disclosures:
    Q4 = FY_annual − (Q1 + Q2 + Q3)."""
    if not period.startswith("Q4_FY"):
        return None
    year = period[5:]
    if len(year) != 4 or not year.isdigit():
        return None
    return f"FY{year}", [f"Q1_FY{year}", f"Q2_FY{year}", f"Q3_FY{year}"]


def validate_derived(
    derived_rows: list[dict],
    nlm_by_period: dict[str, list[dict]],
    label_to_key: dict[str, str],
    tolerance_fn=_tolerance_for_unit,
) -> dict:
    """Compare each derived row's value to the NLM raw value (when available).

    Two matching strategies:
      1. Direct: NLM has a value for (period, uni_account) — direct compare.
      2. Q4 reconstruction: if derived row is Q4_FY{y}, compute expected =
         NLM[FY{y}] − sum(NLM[Q1..Q3_FY{y}]) and compare. This is the most
         common derive-base case (Q4 = FY − 9M_YTD) translated to PDF reads.

    Returns dict with keys:
        passed:    list of {period, uni_account, derived, nlm, diff, method}
        failed:    list of {period, uni_account, derived, nlm, diff, tolerance, method}
        unmatched: list of {period, uni_account, reason}
        counts:    {passed, failed, unmatched, total_derived}
    """
    # Build NLM index: {(period, uni_account): (value, unit)}
    nlm_idx: dict[tuple[str, str], tuple[float, str]] = {}
    for period, rows in nlm_by_period.items():
        for r in rows:
            label = r.get("label")
            value = r.get("value")
            unit = r.get("unit", "")
            if label is None or value is None:
                continue
            key = label_to_key.get(label)
            if not key:
                continue
            idx_key = (period, key)
            if idx_key not in nlm_idx:
                nlm_idx[idx_key] = (float(value), unit)

    passed: list[dict] = []
    failed: list[dict] = []
    unmatched: list[dict] = []
    for d in derived_rows:
        period = d.get("period")
        uni = d.get("uni_account")
        unit = d.get("unit", "")
        derived_val = d.get("value")
        if period is None or uni is None or derived_val is None:
            continue

        # Strategy 1: direct match
        direct = nlm_idx.get((period, uni))
        nlm_val: float | None = None
        method = ""
        if direct is not None:
            nlm_val = direct[0]
            method = "direct"
        else:
            # Strategy 2: Q4 = FY - (Q1+Q2+Q3) reconstruction from NLM raw
            q4_decomp = _q4_from_fy_and_ytd(period)
            if q4_decomp is not None:
                fy_period, q_periods = q4_decomp
                fy_entry = nlm_idx.get((fy_period, uni))
                q_entries = [nlm_idx.get((qp, uni)) for qp in q_periods]
                if fy_entry is not None and all(e is not None for e in q_entries):
                    nlm_val = fy_entry[0] - sum(e[0] for e in q_entries)  # type: ignore
                    method = "q4_reconstruct_fy_minus_q1q2q3"

        if nlm_val is None:
            unmatched.append({"period": period, "uni_account": uni,
                              "reason": "no NLM value for direct or Q4-reconstruction"})
            continue

        diff = abs(float(derived_val) - nlm_val)
        tol = tolerance_fn(unit)
        # Sign-flip detection: same as parse-sec-cross-check convention.
        # XBRL stores certain items as positive magnitude (e.g. interest_expense,
        # cost_of_goods_sold) while PDF discloses them with sign for arithmetic.
        # If abs values match within tolerance and signs differ, treat as pass.
        sign_flipped = (
            abs(abs(float(derived_val)) - abs(nlm_val)) <= tol
            and float(derived_val) * nlm_val < 0
        )
        rec = {
            "period":      period,
            "uni_account": uni,
            "derived":     derived_val,
            "nlm":         nlm_val,
            "diff":        diff,
            "tolerance":   tol,
            "unit":        unit,
            "method":      method,
            "sign_flipped": sign_flipped,
            "rule_id":     (d.get("provenance") or {}).get("rule_id"),
        }
        if diff <= tol or sign_flipped:
            passed.append(rec)
        else:
            failed.append(rec)

    return {
        "passed":    passed,
        "failed":    failed,
        "unmatched": unmatched,
        "counts": {
            "passed":        len(passed),
            "failed":        len(failed),
            "unmatched":     len(unmatched),
            "total_derived": len(derived_rows),
        },
    }


def render_validation_md(ticker: str, report: dict, nlm_source: Path | None) -> str:
    c = report["counts"]
    lines = [
        f"# {ticker} derive-base NLM validation",
        "",
        f"- NLM source: `{nlm_source}`" if nlm_source else "- NLM source: (none — cross-check run not found)",
        f"- Derived rows checked: {c['total_derived']}",
        f"- ✅ Passed: {c['passed']}",
        f"- ❌ Failed: {c['failed']}",
        f"- ⚠️ Unmatched (NLM has no value for this uni_account): {c['unmatched']}",
        "",
    ]
    if report["failed"]:
        lines += [
            "## ❌ Failed",
            "",
            "| period | uni_account | derived | NLM | diff | tolerance | rule_id |",
            "|---|---|---:|---:|---:|---:|---|",
        ]
        for r in report["failed"]:
            lines.append(
                f"| {r['period']} | {r['uni_account']} | "
                f"{r['derived']:.4g} | {r['nlm']:.4g} | "
                f"{r['diff']:.4g} | {r['tolerance']:.4g} | {r.get('rule_id') or '—'} |"
            )
        lines.append("")
    if report["passed"]:
        lines += [
            f"## ✅ Passed ({len(report['passed'])})",
            "",
            "| period | uni_account | derived | NLM | diff | rule_id |",
            "|---|---|---:|---:|---:|---|",
        ]
        for r in report["passed"]:
            lines.append(
                f"| {r['period']} | {r['uni_account']} | "
                f"{r['derived']:.4g} | {r['nlm']:.4g} | "
                f"{r['diff']:.4g} | {r.get('rule_id') or '—'} |"
            )
        lines.append("")
    return "\n".join(lines)
