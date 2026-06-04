"""Convert resolved Candidates → DerivedMetricRow → JSON file.

Also writes:
  {TICKER}_derived.json       canonical JSON (derived_metrics[] + metadata)
  {TICKER}_derive_audit.md    human audit (per-pass counts, chain paths)
  {TICKER}_conflict_report.md tolerance conflicts + facts-already-cover diffs
"""
from __future__ import annotations
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Reuse _shared.cell_id from AI_Agent. Robust path discovery mirrors
# io_loader so audit.py can be import-ed standalone in any of the 4
# mirrors (CC_Switch_Config + 3 runtimes + prototype tmp/) without
# relying on derive_base.py running io_loader first. Codex round-5 F2.
AI_AGENT_ROOT = Path(__file__).resolve().parents[4] / "AI_Agent"
if not (AI_AGENT_ROOT / "Tools" / "research-tools" / "_shared").exists():
    # Fallback: prototype location (parents[2] = AI_Agent when run from tmp/derive-base)
    AI_AGENT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AI_AGENT_ROOT / "Tools" / "research-tools"))
from _shared.cell_id import metrics_cell_id  # noqa: E402
from _shared.audit_metadata import is_manual_audit_source  # noqa: E402

from derive_types import Candidate, DerivedMetricRow


def to_derived_metric_row(c: Candidate) -> DerivedMetricRow:
    # Phase 3.5 (schema §8.2): aggregate audit lineage from input cells.
    # A derived row "has audited inputs" iff any of its inputs carry a manual
    # audit source. Front-end uses this flag to render audit indicators on
    # derived metrics; downstream forensic can follow audited_input_cell_ids
    # back to the source rows.
    audited_input_cell_ids = [
        i["cell_id"] for i in c.inputs
        if is_manual_audit_source(i.get("audit_source"))
        or is_manual_audit_source(i.get("audit_source_raw"))
    ]
    provenance = {
        "rule_id":      c.rule_id,
        "rule_version": "derive-base/1.0",
        "formula":      c.extras.get("formula") or "",
        "inputs":       c.inputs,
        "chained":      c.chained,
        "chain_depth":  c.chain_depth,
        "target_table": "sec_financial_metrics",
        # Phase 3.5: audit lineage
        "has_audited_inputs":     bool(audited_input_cell_ids),
        "audited_input_cell_ids": audited_input_cell_ids,
    }
    if "role_uri" in c.extras:
        provenance["role_uri"] = c.extras["role_uri"]
    if "parent_qname" in c.extras:
        provenance["parent_qname"] = c.extras["parent_qname"]
    cell_id = metrics_cell_id(
        ticker=c.ticker, period=c.period, period_kind=c.period_kind,
        version=c.version, statement=c.statement, uni_account=c.uni_account,
    )
    return DerivedMetricRow(
        cell_id=cell_id, ticker=c.ticker, period=c.period,
        period_kind=c.period_kind, period_start=c.period_start, period_end=c.period_end,
        statement=c.statement, version=c.version, uni_account=c.uni_account,
        value=c.value, unit=c.unit,
        status="DERIVED_FROM_DISCLOSED",
        provenance=provenance,
    )


def write_derived_json(out_dir: Path, ticker: str, rows: list[DerivedMetricRow], meta: dict) -> Path:
    doc = {
        "metadata": {
            "ticker":        ticker,
            "skill_version": "derive-base/1.0",
            "run_timestamp": datetime.now(timezone.utc).isoformat(),
            **meta,
        },
        "derived_metrics": [_row_to_dict(r) for r in rows],
    }
    p = out_dir / f"{ticker}_derived.json"
    p.write_text(json.dumps(doc, indent=2, ensure_ascii=False))
    return p


def _row_to_dict(r: DerivedMetricRow) -> dict:
    return {
        "cell_id":     r.cell_id,
        "ticker":      r.ticker,
        "period":      r.period,
        "period_kind": r.period_kind,
        "period_start":r.period_start,
        "period_end":  r.period_end,
        "statement":   r.statement,
        "version":     r.version,
        "uni_account": r.uni_account,
        "value":       r.value,
        "unit":        r.unit,
        "status":      r.status,
        "provenance":  r.provenance,
    }


def write_audit_md(out_dir: Path, ticker: str, result: dict, *, meta_extras: dict | None = None) -> Path:
    """Write human-readable audit markdown with per-pass counts and chain depth distribution."""
    stats = result["stats"]
    lines = [
        f"# {ticker} derive-base audit",
        "",
        f"- Pass 1 (identity_on_direct):    {stats['pass1_count']}",
        f"- Pass 2 (GAAP_quarters Q2/Q3/Q4):{stats['pass2_count']}",
        f"- Pass 3 (identity_on_derived):   {stats['pass3_count']}",
        f"- Final winners (after facts):    {stats['final_count']}",
        f"- Hard tolerance conflicts:       {stats['conflicts']}",
        f"- Facts-already-cover skips:      {stats['fact_skips']}",
        f"- Q4 input-mismatch skips:        {stats.get('q4_skips', 0)}",
        f"- Q2/Q3 input-mismatch skips:     {stats.get('q2q3_skips', 0)}",
        "",
    ]
    # R4-F3: surface the single-quarter candidates that were intentionally
    # dropped (concept/unit mismatch) so a reviewer can tell missing != skipped.
    quarter_skips = (result.get("q4_skips") or []) + (result.get("q2q3_skips") or [])
    if quarter_skips:
        lines.append("## Single-quarter input-mismatch skips (Q2/Q3/Q4)")
        for s in quarter_skips:
            inputs_desc = ", ".join(
                f"{i.get('period')}={i.get('source_account') or i.get('xbrl_tag') or '?'}@{i.get('unit')}"
                for i in s["inputs"]
            )
            lines.append(
                f"- `{s['reason']}` {s['ticker']} {s['period']} {s['statement']}.{s['uni_account']} "
                f"(unit={s['unit']}) — inputs: {inputs_desc}"
            )
        lines.append("")
    if meta_extras:
        lines.append("## metadata")
        for k, v in meta_extras.items():
            lines.append(f"- {k}: {v}")
        lines.append("")
    # Chain depth distribution
    by_depth: dict[int, int] = {}
    for w in result["winners"]:
        # winners are Candidate objects; use .chain_depth directly.
        d = w.chain_depth if hasattr(w, "chain_depth") else 1
        by_depth[d] = by_depth.get(d, 0) + 1
    lines.append("## chain_depth distribution")
    for d in sorted(by_depth):
        lines.append(f"- depth {d}: {by_depth[d]}")
    p = out_dir / f"{ticker}_derive_audit.md"
    p.write_text("\n".join(lines))
    return p


def write_conflict_md(out_dir: Path, ticker: str, result: dict) -> Path:
    """Write conflict report markdown: tolerance breaches + facts-already-cover diffs."""
    lines = [f"# {ticker} derive-base conflicts", ""]
    confs = result.get("conflicts", [])
    if confs:
        lines.append("## Hard tolerance conflicts (candidate skipped)")
        lines.append("")
        lines.append("| period | uni_account | preferred | other | abs | rel |")
        lines.append("|---|---|---|---|---:|---:|")
        for c in confs:
            lines.append(
                f"| {c['period']} | {c['uni_account']} | "
                f"{c['preferred_rule']}={c['preferred_value']} | "
                f"{c['other_rule']}={c['other_value']} | "
                f"{c['abs_diff']} {c['unit']} | {c['rel_pct']:.1f}% |"
            )
        lines.append("")
    fc = result.get("fact_conflicts", [])
    if fc:
        lines.append("## Facts already cover (derive skipped, diff recorded)")
        lines.append("")
        lines.append("| period | uni_account | facts_value | derived_value | abs | rel | level |")
        lines.append("|---|---|---:|---:|---:|---:|---|")
        for c in fc:
            lines.append(
                f"| {c['period']} | {c['uni_account']} | "
                f"{c['facts_value']} | {c['derived_value']} | "
                f"{c['abs_diff']} | {c['rel_pct']:.2f}% | {c['tolerance_level']} |"
            )
        lines.append("")
    if not confs and not fc:
        lines.append("_(none)_")
    p = out_dir / f"{ticker}_conflict_report.md"
    p.write_text("\n".join(lines))
    return p
