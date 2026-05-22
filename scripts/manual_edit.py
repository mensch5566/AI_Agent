#!/usr/bin/env python3
"""manual_edit.py — Phase 5: ad-hoc audit edit CLI for parse-pipeline JSON
outputs (GAAP / 8K Non-GAAP / SEC supplement v3).

Schema v4 contract: docs/audit-metadata-schema.md §2 (row schema), §3 (audit
allowlist), §4 (stamp helpers), §11 (accepted_new_value_replaces_audit).

This is for one-off cell corrections that aren't tied to a cross-check run.
For batch audit from a cross_check.md, use parse-sec-cross-check/apply_audit.py.

Usage examples
--------------

Stamp a new audit row (GAAP):

    python3 scripts/manual_edit.py --ticker LITE --target gaap \\
        --period Q1_FY2026 --uni-account income_before_taxes \\
        --new-value -172.1 --unit USD_millions \\
        --audit-source MANUAL_AUDIT_FROM_OFFICIAL_FILING \\
        --source-doc lite-20250927.htm \\
        --audit-note "10-Q income statement"

Override an existing audit (must pass --accept-new-values):

    python3 scripts/manual_edit.py --ticker LITE --target gaap \\
        --period Q1_FY2026 --uni-account income_before_taxes \\
        --new-value -180.0 --unit USD_millions \\
        --audit-source MANUAL_AUDIT_FROM_OFFICIAL_FILING \\
        --source-doc amended-filing.htm \\
        --accept-new-values

Dry-run (preview, no write):

    python3 scripts/manual_edit.py ... --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "Tools" / "research-tools"))

from _shared.audit_metadata import (  # noqa: E402
    build_supplement_identity,
    clear_audit_provenance,
    is_manual_audit_source,
    row_has_audited_value,
    stamp_audit_provenance,
)


KHOUSE_BASE = Path(
    os.environ.get("OBSIDIAN_VAULT", str(Path.home() / "Obsidian"))
) / "Khouse" / "Semiconductors"

TARGET_CONFIG = {
    "gaap": {
        "json_template": "{ticker}/01_Source/SEC Filings/Skill_Output/parse-10QK-gaap/{ticker}_gaap.json",
        "facts_key":     "income_statement",   # caller can override via --facts-key
    },
    "nongaap": {
        "json_template": "{ticker}/01_Source/SEC Filings/Skill_Output/parse-8k-nongaap/{ticker}_nongaap.json",
        "facts_key":     "income_statement",
    },
    "supplement": {
        "json_template": "{ticker}/01_Source/SEC Filings/Skill_Output/parse-SEC-supplement/{ticker}_supplement_facts_v3.json",
        "facts_key":     "facts",
    },
}

LOG_FILENAME = "manual_edit_audit_log.jsonl"


# ─────────────────────────────────────────────────────────────────────────────
# Identity & row matching
# ─────────────────────────────────────────────────────────────────────────────

def _gaap_8k_identity(row: dict) -> tuple:
    """For GAAP/8K rows: (period, uni_account, source_account, type)."""
    return (
        row.get("period"),
        row.get("uni_account"),
        row.get("source_account"),
        row.get("type"),
    )


def find_matching_row(facts: list[dict], target: str, args) -> tuple[int | None, dict | None]:
    """Find the row in `facts` that matches the CLI identity args.

    Returns (index, row) or (None, None) if no match.
    Raises ValueError if multiple rows match (ambiguous — caller must
    disambiguate with --source-account or supplement axis args).
    """
    matches: list[tuple[int, dict]] = []

    if target in ("gaap", "nongaap"):
        for i, r in enumerate(facts):
            if r.get("period") != args.period:
                continue
            if r.get("uni_account") != args.uni_account:
                continue
            if args.source_account is not None and r.get("source_account") != args.source_account:
                continue
            if args.row_type is not None and r.get("type") != args.row_type:
                continue
            matches.append((i, r))
    elif target == "supplement":
        # Build minimal supplement identity from args
        synth_row = {
            "period":               args.period,
            "period_kind":          args.period_kind,
            "axis":                 args.axis,
            "axis_qname":           args.axis_qname,
            "source_account":       args.source_account,
            "source_account_qname": args.member_qname,
            "uni_account":          args.uni_account,
            "other_dimensions":     [],
            "unit":                 args.unit,
        }
        target_ident = build_supplement_identity(synth_row)
        for i, r in enumerate(facts):
            if build_supplement_identity(r) == target_ident:
                matches.append((i, r))

    if not matches:
        return None, None
    if len(matches) > 1:
        raise ValueError(
            f"ambiguous: {len(matches)} rows match the identity criteria. "
            f"For GAAP/8K narrow with --source-account / --row-type; "
            f"for supplement narrow with --axis-qname / --member-qname / --unit."
        )
    return matches[0]


# ─────────────────────────────────────────────────────────────────────────────
# Edit execution
# ─────────────────────────────────────────────────────────────────────────────

def build_audit_evidence(args) -> dict[str, Any]:
    """Build the per-edit audit_evidence dict from CLI args."""
    evidence: dict[str, Any] = {"tool": "scripts/manual_edit.py"}
    if args.source_doc:
        evidence["source_doc"] = args.source_doc
    if args.page_or_section:
        evidence["page_or_section"] = args.page_or_section
    if args.quote:
        evidence["quote"] = args.quote
    if args.accession_number:
        evidence["accession_number"] = args.accession_number
    if args.period_scope:
        evidence["period_scope"] = args.period_scope
    return evidence


def stamp_edit(
    row: dict,
    args,
    audited_at_iso: str,
    audited_by: str,
    *,
    prior_value: Any = None,
    is_override: bool = False,
) -> None:
    """Mutate `row` in place: set new value + v4 audit metadata.

    If `is_override`, also writes accepted_new_value_replaces_audit forensic.
    """
    evidence = build_audit_evidence(args)
    if is_override:
        # Clear prior audit provenance before stamping new (Phase 2 F5 / §11)
        clear_audit_provenance(row)
        row["accepted_new_value_replaces_audit"] = {
            "prior_audit_value":   prior_value,
            "new_extracted_value": args.new_value,
        }
    row["value"] = args.new_value
    if args.unit is not None:
        row["unit"] = args.unit
    stamp_audit_provenance(
        row,
        audit_source=args.audit_source,
        audit_note=args.audit_note,
        audited_at=audited_at_iso,
        audited_by=audited_by,
        audit_evidence=evidence,
    )


def build_new_row(target: str, args) -> dict:
    """Build a brand new row when no existing row matches."""
    row: dict[str, Any] = {
        "period":         args.period,
        "uni_account":    args.uni_account,
        "value":          args.new_value,
        "unit":           args.unit,
    }
    if args.source_account:
        row["source_account"] = args.source_account
    if args.row_type:
        row["type"] = args.row_type
    if target == "supplement":
        if args.period_kind:
            row["period_kind"] = args.period_kind
        if args.axis:
            row["axis"] = args.axis
        if args.axis_qname:
            row["axis_qname"] = args.axis_qname
        if args.member_qname:
            row["source_account_qname"] = args.member_qname
        row["other_dimensions"] = []
    return row


def append_log(out_dir: Path, log_entry: dict) -> Path:
    """Append a JSON line to manual_edit_audit_log.jsonl in out_dir."""
    log_path = out_dir / LOG_FILENAME
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    return log_path


# ─────────────────────────────────────────────────────────────────────────────
# Main flow
# ─────────────────────────────────────────────────────────────────────────────

def resolve_json_path(target: str, ticker: str, override: str | None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    template = TARGET_CONFIG[target]["json_template"]
    return KHOUSE_BASE / template.format(ticker=ticker.upper())


def run(args) -> int:
    target = args.target
    ticker = args.ticker.upper()
    json_path = resolve_json_path(target, ticker, args.json_path)
    if not json_path.exists():
        sys.exit(f"❌ Target JSON not found: {json_path}")

    audited_at_iso = datetime.now(timezone.utc).isoformat()
    audited_by = args.audited_by or os.environ.get("USER") or "user"

    doc = json.loads(json_path.read_text())
    facts_key = args.facts_key or TARGET_CONFIG[target]["facts_key"]
    facts = doc.get(facts_key)
    if facts is None:
        sys.exit(f"❌ Target JSON has no '{facts_key}' array: {json_path}")
    if not isinstance(facts, list):
        sys.exit(f"❌ Target JSON '{facts_key}' is not a list: {json_path}")

    idx, existing_row = find_matching_row(facts, target, args)

    operation: str
    prior_value: Any = None
    diff_summary: dict[str, Any]
    if existing_row is None:
        # Brand new row
        new_row = build_new_row(target, args)
        stamp_edit(new_row, args, audited_at_iso, audited_by)
        operation = "stamp_new_row"
        diff_summary = {
            "operation":      operation,
            "new_value":      args.new_value,
            "row_appended":   True,
        }
        if not args.dry_run:
            facts.append(new_row)
    else:
        prior_value = existing_row.get("value")
        was_audited = row_has_audited_value(existing_row)
        if was_audited and not args.accept_new_values:
            sys.exit(
                f"❌ Row already carries audit metadata "
                f"(audit_source={existing_row.get('audit_source')!r}, "
                f"value={prior_value}). "
                f"Pass --accept-new-values to override and write "
                f"accepted_new_value_replaces_audit forensic field."
            )
        operation = "override_existing_audit" if was_audited else "stamp_existing_row"
        # Apply in place (also for dry-run, mutate a copy for diff)
        target_row = existing_row if not args.dry_run else dict(existing_row)
        stamp_edit(
            target_row, args, audited_at_iso, audited_by,
            prior_value=prior_value, is_override=was_audited,
        )
        diff_summary = {
            "operation":   operation,
            "prior_value": prior_value,
            "new_value":   args.new_value,
            "row_index":   idx,
        }

    print(f"=== manual_edit ({operation}) ===")
    print(f"  Ticker:     {ticker}")
    print(f"  Target:     {target}  ({json_path})")
    print(f"  Period:     {args.period}")
    print(f"  uni_account:{args.uni_account}")
    if args.source_account:
        print(f"  source_acc: {args.source_account}")
    print(f"  Diff:       {prior_value} → {args.new_value}")
    print(f"  Audit src:  {args.audit_source}")
    print(f"  Audited by: {audited_by} at {audited_at_iso}")
    if args.dry_run:
        print(f"  (dry-run — no write)")
        return 0

    json_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False))

    # Append to log
    log_entry = {
        "ts":             audited_at_iso,
        "ticker":         ticker,
        "target":         target,
        "json_path":      str(json_path),
        "operation":      operation,
        "period":         args.period,
        "uni_account":    args.uni_account,
        "source_account": args.source_account,
        "prior_value":    prior_value,
        "new_value":      args.new_value,
        "audit_source":   args.audit_source,
        "audited_by":     audited_by,
        "audit_evidence": build_audit_evidence(args),
    }
    if args.audit_note:
        log_entry["audit_note"] = args.audit_note
    log_path = append_log(json_path.parent, log_entry)
    print(f"  Wrote:      {json_path.name}")
    print(f"  Log:        {log_path.name}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Phase 5: ad-hoc audit edit for parse pipeline JSON outputs.",
    )
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--target", required=True, choices=list(TARGET_CONFIG.keys()),
                    help="Which parse output to edit.")
    ap.add_argument("--period", required=True)
    ap.add_argument("--uni-account", required=True)
    ap.add_argument("--new-value", required=True, type=float)
    ap.add_argument("--audit-source", required=True,
                    help="One of MANUAL_AUDIT_FROM_OFFICIAL_FILING / "
                         "MANUAL_RESTATEMENT_FROM_AMENDED_FILING (legacy "
                         "enums accepted but normalized).")
    # Row narrowing (optional for unique match)
    ap.add_argument("--source-account", help="Disambiguate when multiple rows share uni_account.")
    ap.add_argument("--row-type", help="GAAP/8K row 'type' field (e.g. GAAP / NON_GAAP).")
    ap.add_argument("--unit", help="Unit string (canonical or recognized raw).")
    # Supplement-specific identity
    ap.add_argument("--period-kind",
                    help="Supplement: single_quarter / fy_annual / instant.")
    ap.add_argument("--axis", help="Supplement: axis_class (e.g. business_segment).")
    ap.add_argument("--axis-qname",
                    help="Supplement: e.g. us-gaap:StatementBusinessSegmentsAxis.")
    ap.add_argument("--member-qname", help="Supplement: member qname.")
    # Audit evidence
    ap.add_argument("--source-doc",
                    help="Filing document name (e.g. lite-20250927.htm). "
                         "Required unless --page-or-section given.")
    ap.add_argument("--page-or-section",
                    help="Note number / section reference (alternative to --source-doc).")
    ap.add_argument("--quote", help="Literal quote from filing.")
    ap.add_argument("--accession-number",
                    help="SEC accession (required when audit-source=RESTATEMENT).")
    ap.add_argument("--period-scope",
                    help='e.g. "Three Months Ended 2025-09-27".')
    ap.add_argument("--audit-note", help="Freeform note (≤500 chars).")
    ap.add_argument("--audited-by", help="Defaults to $USER or 'user'.")
    # Behavior flags
    ap.add_argument("--accept-new-values", action="store_true",
                    help="Required when overriding a row that already carries "
                         "audit metadata.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would change, don't write JSON or log.")
    # Path overrides
    ap.add_argument("--json-path",
                    help="Override default ticker JSON path (useful for testing).")
    ap.add_argument("--facts-key",
                    help="Override default facts-array key for target.")
    return ap


def main():
    args = build_arg_parser().parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
