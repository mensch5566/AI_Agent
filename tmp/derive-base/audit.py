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

# Reuse _shared.cell_id from AI_Agent
AI_AGENT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AI_AGENT_ROOT / "Tools" / "research-tools"))
from _shared.cell_id import metrics_cell_id  # noqa: E402

from derive_types import Candidate, DerivedMetricRow


def to_derived_metric_row(c: Candidate) -> DerivedMetricRow:
    provenance = {
        "rule_id":      c.rule_id,
        "rule_version": "derive-base/1.0",
        "formula":      c.extras.get("formula") or "",
        "inputs":       c.inputs,
        "chained":      c.chained,
        "chain_depth":  c.chain_depth,
        "target_table": "sec_financial_metrics",
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
