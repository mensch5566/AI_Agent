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

from io_loader import discover_sources, load_facts, load_calc_edges, output_dir, sha256_file
from rules_identity import build_qname_to_uni, calc_rules_from_edges
from derive_engine import run_engine
from audit import to_derived_metric_row, write_derived_json, write_audit_md, write_conflict_md


DEFAULT_VAULT = Path(os.path.expanduser(
    "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian"
))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--vault", default=str(DEFAULT_VAULT),
                    help="Obsidian vault root (default: real iCloud vault)")
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

    run_stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    od = output_dir(vault, ticker, run_stamp)
    meta_extras = {
        "input_facts_count": len(facts),
        "calc_rules_count":  len(calc_rules),
        "qname_to_uni_count": len(qname_to_uni),
        "stats": result["stats"],
        "input_files": {
            k: {"path": str(v), "sha256": sha256_file(v)}
            for k, v in srcs.items() if v is not None and v.exists()
        },
    }
    write_derived_json(od, ticker, rows, meta=meta_extras)
    write_audit_md(od, ticker, result, meta_extras=meta_extras)
    write_conflict_md(od, ticker, result)

    print(f"derive-base done — {len(rows)} rows, {result['stats']['conflicts']} conflicts, {result['stats']['fact_skips']} facts-skips")
    print(str(od))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
