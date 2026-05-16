"""Upsert SEC v2 financials (AAOI / INTC / SNDK / ...) → Supabase.

Spec: tmp/financials-viewer-redesign-plan.md §20 (v5.1) execution plan steps 4-7.

Pipeline:
  1. Load 3 source JSONs (parse-10QK-gaap, parse-8k-nongaap, parse-SEC-supplement)
     + edges (calc / presentation / def_dim).
  2. Run sec_json_adapter to normalize → DB-ready rows.
  3. Preflight: period_end map + ISO date validate + rejected log.
  4. Dry-run mode (--dry-run): print stats, NEVER touch DB. Default.
  5. Real-run mode (--apply): upsert to 4 tables (companies / facts /
     dimensional_facts / edges). Metrics table left empty (derive skills
     Phase 2 will populate).

Usage:
    # dry-run AAOI
    python scripts/upsert_sec_financials.py AAOI

    # real upsert
    python scripts/upsert_sec_financials.py AAOI --apply

Skill output is expected at:
    Obsidian/Khouse/Semiconductors/{TICKER}/01_Source/SEC Filings/Skill_Output/
        parse-10QK-gaap/{TICKER}_gaap_facts.json
        parse-10QK-gaap/{TICKER}_gaap_edges_cal.json
        parse-10QK-gaap/{TICKER}_gaap_edges_pre.json
        parse-10QK-gaap/{TICKER}_sign_flip_concepts.json
        parse-8k-nongaap/{TICKER}_nongaap.json
        parse-SEC-supplement/{TICKER}_supplement_facts_v3.json
        parse-SEC-supplement/{TICKER}_supplement_edges_v3.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "Tools" / "research-tools"))

from _shared import sec_json_adapter as A  # noqa: E402

OBSIDIAN_BASE = Path(
    "/Users/mensch5566/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian"
)

BATCH_SIZE = 500


# ---- IO helpers --------------------------------------------------------------


def skill_output_dir(ticker: str) -> Path:
    return OBSIDIAN_BASE / "Khouse" / "Semiconductors" / ticker / "01_Source" / "SEC Filings" / "Skill_Output"


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def load_sources(ticker: str) -> dict:
    """Load all 7 source JSONs (some may be absent)."""
    base = skill_output_dir(ticker)
    return {
        "gaap_facts": load_json(base / "parse-10QK-gaap" / f"{ticker}_gaap_facts.json"),
        "gaap_edges_cal": load_json(base / "parse-10QK-gaap" / f"{ticker}_gaap_edges_cal.json"),
        "gaap_edges_pre": load_json(base / "parse-10QK-gaap" / f"{ticker}_gaap_edges_pre.json"),
        "sign_flip": load_json(base / "parse-10QK-gaap" / f"{ticker}_sign_flip_concepts.json"),
        "nongaap": load_json(base / "parse-8k-nongaap" / f"{ticker}_nongaap.json"),
        "supplement_facts": load_json(base / "parse-SEC-supplement" / f"{ticker}_supplement_facts_v3.json"),
        "supplement_edges": load_json(base / "parse-SEC-supplement" / f"{ticker}_supplement_edges_v3.json"),
    }


# ---- Pipeline ----------------------------------------------------------------


def normalize(ticker: str, sources: dict) -> A.NormalizedBatch:
    """Run full adapter pipeline; return NormalizedBatch with rows + validation."""
    batch = A.NormalizedBatch(ticker=ticker)

    if sources["gaap_facts"] is None:
        raise SystemExit(f"GAAP facts missing for {ticker} — run parse-10QK-gaap first")

    gaap_meta = sources["gaap_facts"]["metadata"]
    sign_flip = (sources["sign_flip"] or {}).get("concepts", [])
    batch.company = A.adapt_company(gaap_meta, sign_flip_concepts=sign_flip)

    pe_map = A.build_period_end_map(gaap_meta)

    # GAAP facts
    gaap_rows, gaap_rej = A.adapt_gaap_facts(sources["gaap_facts"], pe_map)
    batch.facts.extend(gaap_rows)
    batch.rejected.extend(gaap_rej)

    # Non-GAAP facts (optional)
    if sources["nongaap"]:
        ng_rows, ng_rej = A.adapt_nongaap_facts(sources["nongaap"], pe_map)
        batch.facts.extend(ng_rows)
        batch.rejected.extend(ng_rej)

    # Dimensional facts (optional)
    if sources["supplement_facts"]:
        sp_rows, sp_rej, sp_dedupe, sp_conflicts = A.adapt_supplement_facts(sources["supplement_facts"])
        batch.dimensional.extend(sp_rows)
        batch.rejected.extend(sp_rej)
        batch.dedupe_stats = sp_dedupe
        batch.value_conflicts = sp_conflicts

    # Edges
    for key, edge_type in [
        ("gaap_edges_cal", "calc"),
        ("gaap_edges_pre", "presentation"),
        ("supplement_edges", "def_dim"),
    ]:
        if sources[key]:
            batch.edges.extend(A.adapt_edges(sources[key], ticker, edge_type))

    return batch


def print_report(batch: A.NormalizedBatch) -> bool:
    """Print dry-run / real-run report. Return True if gate passes."""
    print(f"\n=== {batch.ticker} normalization report ===")
    print(f"  company: {batch.company.company_name} ({batch.company.exchange}) cik={batch.company.cik}")
    print(f"  filings indexed: {len(batch.company.filings)}")
    print(f"  sign_flip_concepts: {len(batch.company.sign_flip_concepts)}")

    fact_by_stmt = Counter(r.statement for r in batch.facts)
    fact_by_ver = Counter(r.version for r in batch.facts)
    print(f"\n  facts: {len(batch.facts)} rows")
    print(f"    by statement: {dict(fact_by_stmt)}")
    print(f"    by version: {dict(fact_by_ver)}")
    print(f"    by period_kind: {dict(Counter(r.period_kind for r in batch.facts))}")
    print(f"    by unit: {dict(Counter(r.unit for r in batch.facts))}")

    print(f"\n  dimensional: {len(batch.dimensional)} rows")
    if batch.dimensional:
        print(f"    by axis: {dict(Counter(r.axis for r in batch.dimensional))}")
        print(f"    by period_kind: {dict(Counter(r.period_kind for r in batch.dimensional))}")
        print(f"    by unit: {dict(Counter(r.unit for r in batch.dimensional))}")
        print(f"    dedupe_stats: {batch.dedupe_stats}")

    print(f"\n  edges: {len(batch.edges)} rows")
    if batch.edges:
        print(f"    by type: {dict(Counter(r.edge_type for r in batch.edges))}")

    # Identity uniqueness
    fact_ids = [r.cell_id for r in batch.facts]
    dim_ids = [r.cell_id for r in batch.dimensional]
    edge_ids = [r.edge_id for r in batch.edges]
    fact_dup = len(fact_ids) - len(set(fact_ids))
    dim_dup = len(dim_ids) - len(set(dim_ids))
    edge_dup = len(edge_ids) - len(set(edge_ids))

    print(f"\n  identity uniqueness:")
    print(f"    facts: {len(set(fact_ids))}/{len(fact_ids)} unique (dup={fact_dup})")
    print(f"    dimensional: {len(set(dim_ids))}/{len(dim_ids)} unique (dup={dim_dup})")
    print(f"    edges: {len(set(edge_ids))}/{len(edge_ids)} unique (dup={edge_dup})")

    # Gate
    gate_pass = True
    print(f"\n  === §20.6 Open Gate ===")
    checks = [
        ("rejected rows = 0", len(batch.rejected) == 0, f"rejected={len(batch.rejected)}"),
        ("value conflicts = 0", len(batch.value_conflicts) == 0, f"conflicts={len(batch.value_conflicts)}"),
        ("facts identity unique", fact_dup == 0, f"dup={fact_dup}"),
        ("dimensional identity unique", dim_dup == 0, f"dup={dim_dup}"),
        ("edges identity unique", edge_dup == 0, f"dup={edge_dup}"),
    ]
    for name, ok, detail in checks:
        mark = "✓" if ok else "✗"
        print(f"    [{mark}] {name} ({detail})")
        if not ok:
            gate_pass = False

    if batch.rejected:
        print(f"\n  rejected rows (first 5):")
        for r in batch.rejected[:5]:
            print(f"    {r['source']} idx={r['idx']} reason={r['reason']}")

    if batch.value_conflicts:
        print(f"\n  value conflicts (first 5):")
        for c in batch.value_conflicts[:5]:
            print(f"    key={c['dedupe_key']}")
            for v in c['values']:
                print(f"      value={v['value']} dec={v.get('decimals')} src={v.get('source_doc')}")

    return gate_pass


# ---- Supabase upsert (real-run only) ----------------------------------------


def supabase_client():
    """Lazy import + env load."""
    env = {}
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k] = v
    url = env.get("NEXT_PUBLIC_SUPABASE_URL") or env.get("SUPABASE_URL")
    key = env.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("Missing NEXT_PUBLIC_SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY in .env")
    from supabase import create_client
    return create_client(url, key)


def upsert_batch(client, table: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        chunk = rows[i : i + BATCH_SIZE]
        client.table(table).upsert(chunk).execute()
        total += len(chunk)
    return total


def row_to_dict(row) -> dict:
    """asdict + JSON-friendly fixups (drop None unit/value where col is NOT NULL etc.)."""
    d = asdict(row)
    return d


def apply(batch: A.NormalizedBatch) -> None:
    client = supabase_client()

    # 1. companies
    company_row = {
        "ticker": batch.company.ticker,
        "company_name": batch.company.company_name,
        "exchange": batch.company.exchange,
        "cik": batch.company.cik,
        "currency": batch.company.currency,
        "fiscal_year_end_month": batch.company.fiscal_year_end_month,
        "filings": batch.company.filings,
        "sign_flip_concepts": batch.company.sign_flip_concepts,
    }
    client.table("sec_financial_companies").upsert(company_row).execute()
    print(f"  upserted: sec_financial_companies (1 row)")

    # 2. facts
    n = upsert_batch(client, "sec_financial_facts", [row_to_dict(r) for r in batch.facts])
    print(f"  upserted: sec_financial_facts ({n} rows)")

    # 3. dimensional_facts
    n = upsert_batch(client, "sec_financial_dimensional_facts", [row_to_dict(r) for r in batch.dimensional])
    print(f"  upserted: sec_financial_dimensional_facts ({n} rows)")

    # 4. edges
    n = upsert_batch(client, "sec_financial_edges", [row_to_dict(r) for r in batch.edges])
    print(f"  upserted: sec_financial_edges ({n} rows)")


# ---- CLI ---------------------------------------------------------------------


def main():
    p = argparse.ArgumentParser()
    p.add_argument("ticker", help="ticker symbol (case-insensitive)")
    p.add_argument("--apply", action="store_true", help="real upsert to Supabase (default: dry-run)")
    args = p.parse_args()
    ticker = args.ticker.upper()

    sources = load_sources(ticker)
    batch = normalize(ticker, sources)
    gate_pass = print_report(batch)

    if not gate_pass:
        print("\n  ✗ Gate FAILED — refusing to upsert. Fix issues above and re-run.")
        sys.exit(1)

    if args.apply:
        print(f"\n=== Real upsert to Supabase ===")
        apply(batch)
        print(f"  ✓ Upsert complete.")
    else:
        print(f"\n  ✓ Dry-run complete. Gate passed. Re-run with --apply to write to Supabase.")


if __name__ == "__main__":
    main()
