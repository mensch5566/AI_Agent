#!/usr/bin/env python3
"""Phase 6.3 — one-shot DB migration: normalize pre-v4 audit_source enums in
existing Supabase data per schema v4 §7.3.

What it does
------------
For each `sec_financial_*` table that has a `provenance` JSONB column:
  1. Reads rows where `provenance->>audit_source` is in
     {MANUAL_AUDIT_FROM_PDF, MANUAL_AUDIT_FROM_8K_PDF, AGENT_CLASSIFIED}
  2. For each row:
     - `MANUAL_AUDIT_FROM_PDF` / `MANUAL_AUDIT_FROM_8K_PDF` →
       set `provenance.audit_source = MANUAL_AUDIT_FROM_OFFICIAL_FILING`
       (canonical), preserve original in `provenance.audit_source_raw`
     - `AGENT_CLASSIFIED` → promote to classification channel:
       `provenance.classification_source = AGENT_CLASSIFIED`
       (don't write `audit_source_raw`; the legacy field is being moved, not
       preserved as forensic audit raw)
  3. Writes back the updated `provenance` JSONB

Safety
------
- Always dry-run first: prints per-table counts + sample rows
- Real run requires `--apply` flag (extra `--ticker TICKER` to limit blast radius)
- Per-ticker run is the default unit (one ticker at a time) so a bug surfaces
  before all 4+ tickers get touched
- Each row update is a single UPDATE statement; no transaction batching —
  granular failure is easier to diagnose than a half-applied batch

Usage
-----

  # dry-run all tickers
  python3 scripts/migrate_db_audit_source_v4.py

  # dry-run a specific ticker
  python3 scripts/migrate_db_audit_source_v4.py --ticker LITE

  # apply (one ticker at a time recommended)
  python3 scripts/migrate_db_audit_source_v4.py --ticker LITE --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "Tools" / "research-tools"))

from _shared.audit_metadata import (  # noqa: E402
    LEGACY_AUDIT_SOURCE_MAP,
    MANUAL_AUDIT_SOURCES,
    MANUAL_CLASSIFICATION_SOURCES,
    normalize_audit_source,
)

try:
    from supabase import create_client
except ImportError:
    sys.exit(
        "❌ supabase-py not installed. Install via:\n"
        "    uv run --with supabase python3 scripts/migrate_db_audit_source_v4.py ..."
    )


TABLES = (
    "sec_financial_facts",
    "sec_financial_dimensional_facts",
    "sec_financial_metrics",
)

# Pre-v4 audit_source values we know to migrate
LEGACY_AUDIT_VALUES = sorted(LEGACY_AUDIT_SOURCE_MAP.keys())
# `AGENT_CLASSIFIED` lived in audit_source field pre-v4 — promote to
# classification_source
LEGACY_CLASSIFICATION_IN_AUDIT_FIELD = sorted(MANUAL_CLASSIFICATION_SOURCES)


def supabase_client():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
    if not url or not key:
        sys.exit("❌ Need SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY in env.")
    return create_client(url, key)


def classify_row(prov: dict) -> str | None:
    """Return one of:
      - 'audit_normalize'        — legacy audit enum → canonical
      - 'classification_promote' — AGENT_CLASSIFIED in audit_source → classification
      - None                     — row doesn't need migration
    """
    src = prov.get("audit_source")
    if src in LEGACY_AUDIT_SOURCE_MAP:
        return "audit_normalize"
    if src in MANUAL_CLASSIFICATION_SOURCES:
        return "classification_promote"
    return None


def build_updated_provenance(prov: dict) -> tuple[dict, str]:
    """Return (new_provenance, operation) where operation is one of
    'audit_normalize' / 'classification_promote'."""
    src = prov["audit_source"]
    op = classify_row(prov)
    if op == "audit_normalize":
        new = {**prov}
        new["audit_source"] = normalize_audit_source(src)
        # Preserve original under audit_source_raw if not already there.
        if not new.get("audit_source_raw"):
            new["audit_source_raw"] = src
        return new, op
    if op == "classification_promote":
        new = {**prov}
        # Don't preserve in audit_source_raw — this wasn't an audit source.
        # If the row also has long_tail_metadata, drop a forensic marker
        # there (mirrors Phase 2 F14 ADDED_BACK canonicalization).
        ltm = new.get("long_tail_metadata") or {}
        if isinstance(ltm, dict):
            ltm.setdefault("legacy_audit_source_raw", src)
            new["long_tail_metadata"] = ltm
        new["classification_source"] = src
        # Remove the legacy audit_source so it doesn't keep matching the
        # legacy enum check on next read.
        new.pop("audit_source", None)
        return new, op
    raise AssertionError("classify_row returned None but caller wanted update")


def scan_table(client, table: str, ticker: str | None) -> list[dict]:
    """Fetch rows matching legacy audit_source values. Returns full row dicts."""
    legacy_values = LEGACY_AUDIT_VALUES + LEGACY_CLASSIFICATION_IN_AUDIT_FIELD
    affected = []
    for legacy_val in legacy_values:
        q = client.table(table).select("*").eq("provenance->>audit_source", legacy_val)
        if ticker:
            q = q.eq("ticker", ticker)
        # paginate (Supabase default 1000 row limit)
        offset = 0
        page_size = 1000
        while True:
            res = q.range(offset, offset + page_size - 1).execute()
            data = res.data or []
            affected.extend(data)
            if len(data) < page_size:
                break
            offset += page_size
    return affected


def summarize(rows: list[dict], table: str) -> dict:
    """Group rows by operation and audit_source value."""
    counts: dict[tuple[str, str], int] = {}
    for r in rows:
        prov = r.get("provenance") or {}
        op = classify_row(prov)
        if op is None:
            continue
        src = prov.get("audit_source", "<unknown>")
        counts[(op, src)] = counts.get((op, src), 0) + 1
    return {"table": table, "total": len(rows), "counts": counts}


def apply_one_row(client, table: str, row: dict) -> bool:
    """Returns True if row was updated."""
    prov = row.get("provenance") or {}
    op = classify_row(prov)
    if op is None:
        return False
    new_prov, _ = build_updated_provenance(prov)
    cell_id = row.get("cell_id")
    if not cell_id:
        print(f"  ⚠ skipping row without cell_id in {table}: {row}")
        return False
    client.table(table).update({"provenance": new_prov}).eq("cell_id", cell_id).execute()
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", help="Limit to one ticker (recommended).")
    ap.add_argument("--apply", action="store_true",
                    help="Actually apply updates. Without this, dry-run only.")
    ap.add_argument("--table", choices=TABLES,
                    help="Limit to one table (for debug; defaults to all).")
    args = ap.parse_args()

    client = supabase_client()
    tables = (args.table,) if args.table else TABLES

    overall_summary = []
    overall_to_apply: list[tuple[str, dict]] = []

    for table in tables:
        scope = f"ticker={args.ticker}" if args.ticker else "all tickers"
        print(f"\n=== {table} ({scope}) ===")
        try:
            rows = scan_table(client, table, args.ticker)
        except Exception as e:
            print(f"  ⚠ scan failed (table may not exist / no rows): {e}")
            continue
        summary = summarize(rows, table)
        overall_summary.append(summary)
        if not rows:
            print(f"  no legacy audit_source rows.")
            continue
        print(f"  {summary['total']} legacy row(s) found:")
        for (op, src), n in sorted(summary["counts"].items()):
            print(f"    {op:24s} audit_source={src!r:40s} → {n} row(s)")
        if not args.apply:
            # Print 2 sample rows for sanity
            print(f"  sample row provenance (first 2):")
            for r in rows[:2]:
                ident = r.get("cell_id", "?")[:48]
                prov = r.get("provenance") or {}
                new_prov, op = build_updated_provenance(prov)
                print(f"    cell_id={ident}")
                print(f"      before: {json.dumps(prov, ensure_ascii=False)[:120]}")
                print(f"      after : {json.dumps(new_prov, ensure_ascii=False)[:120]}  ({op})")
        else:
            for r in rows:
                overall_to_apply.append((table, r))

    if not args.apply:
        print(f"\n=== DRY-RUN ===")
        total = sum(s["total"] for s in overall_summary)
        print(f"Would migrate {total} row(s) across {len(overall_summary)} table(s).")
        print(f"Re-run with --apply (and --ticker for blast-radius control) to write.")
        return 0

    # APPLY
    print(f"\n=== APPLY ({len(overall_to_apply)} row(s)) ===")
    if not args.ticker:
        confirm = input(
            "⚠ No --ticker filter; will touch ALL tickers across all tables. "
            "Type 'YES' to continue: "
        )
        if confirm.strip() != "YES":
            print("Aborted.")
            return 1
    updated = 0
    for table, row in overall_to_apply:
        try:
            if apply_one_row(client, table, row):
                updated += 1
        except Exception as e:
            print(f"  ⚠ row update failed in {table} cell_id={row.get('cell_id')}: {e}")
    print(f"Updated {updated} / {len(overall_to_apply)} row(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
