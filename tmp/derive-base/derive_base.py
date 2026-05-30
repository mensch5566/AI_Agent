#!/usr/bin/env python3
"""derive-base CLI entrypoint.

Usage:
  python3 derive_base.py --ticker AAOI [--vault /path/to/obsidian]

Reads from   <vault>/Khouse/Semiconductors/<TICKER>/01_Source/SEC Filings/Skill_Output/parse-10QK-gaap/
Writes to    <vault>/Khouse/Semiconductors/<TICKER>/01_Source/SEC Filings/Skill_Output/derive-base/<run_stamp>/
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from io_loader import (
    discover_sources, load_facts, load_calc_edges, output_dir, sha256_file,
    discover_cross_check_run,
)
from rules_identity import build_qname_to_uni, calc_rules_from_edges
from derive_engine import run_engine
from audit import to_derived_metric_row, write_derived_json, write_audit_md, write_conflict_md
from validation_nlm import (
    load_cross_check_label_map, load_nlm_responses, validate_derived,
    render_validation_md,
)


def _cross_check_config_path(ticker: str) -> Path | None:
    """Locate cross-check ticker config in known runtime mirrors.
    Falls back to None if no mirror has it (e.g. fresh install)."""
    candidates = [
        Path("~/.claude/skills/parse-sec-cross-check/ticker_configs").expanduser() / f"{ticker}.json",
        Path("~/.codex/skills/parse-sec-cross-check/ticker_configs").expanduser() / f"{ticker}.json",
        Path("~/.cc-switch/skills/parse-sec-cross-check/ticker_configs").expanduser() / f"{ticker}.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


DEFAULT_VAULT = Path(os.environ.get(
    "OBSIDIAN_VAULT",
    os.path.expanduser("~/Obsidian"),
))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--vault", default=str(DEFAULT_VAULT),
                    help="Obsidian vault root (default: ~/Obsidian or $OBSIDIAN_VAULT)")
    args = ap.parse_args()

    ticker = args.ticker.upper()
    vault = Path(args.vault).expanduser()

    srcs = discover_sources(vault, ticker)
    if srcs["gaap_inline"] is None or not srcs["gaap_inline"].exists():
        print(f"❌ {ticker} inline gaap.json not found under {vault}", file=sys.stderr)
        return 2

    facts = load_facts(srcs)
    edges = load_calc_edges(srcs)
    calc_rules = calc_rules_from_edges(edges)

    inline = json.loads(srcs["gaap_inline"].read_text())
    qname_to_uni = build_qname_to_uni(inline)

    result = run_engine(facts=facts, calc_rules=calc_rules, qname_to_uni=qname_to_uni)
    rows = [to_derived_metric_row(c) for c in result["winners"]]

    # managed_rule_ids: distinct rule_ids actually produced by this run.
    # upsert_sec_financials uses this as the snapshot-replacement scope
    # (delete-then-insert) instead of hardcoding a period_kind. This keeps
    # the contract self-describing and lets future identity rules (IDENTITY_*)
    # participate automatically without changing upsert code.
    managed_rule_ids = sorted({r.provenance["rule_id"] for r in rows
                                if r.provenance.get("rule_id")})

    run_stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    od = output_dir(vault, ticker, run_stamp)
    meta_extras = {
        "input_facts_count": len(facts),
        "calc_rules_count":  len(calc_rules),
        "qname_to_uni_count": len(qname_to_uni),
        "managed_rule_ids":  managed_rule_ids,
        "stats": result["stats"],
        "input_files": {
            k: {"path": str(v), "sha256": sha256_file(v)}
            for k, v in srcs.items() if v is not None and v.exists()
        },
    }

    # NLM validation: compare derived values against parse-sec-cross-check's
    # raw NLM PDF readings. Informational by default (does not gate derive-base
    # exit code) — surfaces arithmetic bugs in identity rules. Adds each NLM
    # response file's sha256 to input_files so the upsert freshness gate also
    # protects validation source.
    cc_run = discover_cross_check_run(vault, ticker)
    cc_cfg = _cross_check_config_path(ticker)
    validation_report = None
    if cc_run and cc_cfg:
        label_map = load_cross_check_label_map(cc_cfg)
        nlm_by_period = load_nlm_responses(cc_run)
        # Serialize derived rows (dataclass) for validation_nlm consumption
        derived_dicts = [
            {
                "period":      r.period,
                "uni_account": r.uni_account,
                "value":       r.value,
                "unit":        r.unit,
                "provenance":  r.provenance,
            }
            for r in rows
        ]
        validation_report = validate_derived(derived_dicts, nlm_by_period, label_map)
        meta_extras["validation"] = {
            "cross_check_run":   str(cc_run),
            "cross_check_config": str(cc_cfg),
            "counts": validation_report["counts"],
        }
        # Add NLM response files to input_files for freshness contract
        nlm_files = sorted((cc_run / "raw_nlm_responses").glob("*.json"))
        for fp in nlm_files:
            meta_extras["input_files"][f"nlm:{fp.stem}"] = {
                "path": str(fp), "sha256": sha256_file(fp),
            }

    write_derived_json(od, ticker, rows, meta=meta_extras)
    write_audit_md(od, ticker, result, meta_extras=meta_extras)
    write_conflict_md(od, ticker, result)

    # NLM validation report (separate md so it doesn't crowd audit log)
    if validation_report is not None:
        (od / f"{ticker}_nlm_validation.md").write_text(
            render_validation_md(ticker, validation_report, cc_run)
        )

    print(f"derive-base done — {len(rows)} rows, {result['stats']['conflicts']} conflicts, {result['stats']['fact_skips']} facts-skips")
    if validation_report is not None:
        c = validation_report["counts"]
        print(f"  NLM validation: {c['passed']} ✅ / {c['failed']} ❌ / {c['unmatched']} unmatched")
    print(str(od))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
