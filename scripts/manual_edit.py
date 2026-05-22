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
    MANUAL_CLASSIFICATION_SOURCES,
    build_supplement_identity,
    clear_audit_provenance,
    is_manual_audit_source,
    is_manual_classification_source,
    row_has_audited_value,
    stamp_audit_provenance,
    stamp_classification,
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


def _parsed_other_dimensions(args) -> list[dict]:
    """P5-F4: parse --other-dimensions-json into list[{axis, member}].
    Empty/missing → []."""
    raw = getattr(args, "other_dimensions_json", None)
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"--other-dimensions-json must be valid JSON: {e}") from e
    if not isinstance(parsed, list):
        raise ValueError("--other-dimensions-json must be a JSON list of {axis, member} objects")
    for d in parsed:
        if not isinstance(d, dict) or "axis" not in d or "member" not in d:
            raise ValueError(
                "each --other-dimensions-json entry must be {\"axis\": ..., \"member\": ...}"
            )
    return parsed


def find_matching_row(facts: list[dict], target: str, args) -> tuple[int | None, dict | None]:
    """Find the row in `facts` that matches the CLI identity args.

    Returns (index, row) or (None, None) if no match.
    Raises ValueError if multiple rows match (ambiguous — caller must
    disambiguate with --source-account / --unit / --other-dimensions-json).
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
            # P5-F5: unit is identity per schema §6.1. If caller gave --unit,
            # row must match it (prevents accidentally overwriting a
            # different-unit row that shares all other identity fields).
            if args.unit is not None and r.get("unit") != args.unit:
                continue
            matches.append((i, r))
    elif target == "supplement":
        # P5-F4: use --other-dimensions-json so multi-dim rows resolve correctly.
        synth_row = {
            "period":               args.period,
            "period_kind":          args.period_kind,
            "axis":                 args.axis,
            "axis_qname":           args.axis_qname,
            "source_account":       args.source_account,
            "source_account_qname": args.member_qname,
            "uni_account":          args.uni_account,
            "other_dimensions":     _parsed_other_dimensions(args),
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
            f"For GAAP/8K narrow with --source-account / --row-type / --unit; "
            f"for supplement narrow with --axis-qname / --member-qname / --unit / "
            f"--other-dimensions-json."
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
    P5-F7: when args specify classification_source (not audit_source),
    write classification channel via stamp_classification instead.
    """
    is_classification_edit = bool(args.classification_source)
    evidence = build_audit_evidence(args) if not is_classification_edit else None
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
    if is_classification_edit:
        # P5-F7: classification path (MANUAL_RECLASSIFIED). Does NOT write
        # audit channel; long_tail_metadata optional.
        ltm = None
        if args.long_tail_metadata_json:
            try:
                ltm = json.loads(args.long_tail_metadata_json)
            except json.JSONDecodeError as e:
                raise ValueError(f"--long-tail-metadata-json invalid: {e}") from e
        stamp_classification(
            row,
            classification_source=args.classification_source,
            classification_note=args.classification_note,
            classified_at=audited_at_iso,
            long_tail_metadata=ltm,
        )
    else:
        stamp_audit_provenance(
            row,
            audit_source=args.audit_source,
            audit_note=args.audit_note,
            audited_at=audited_at_iso,
            audited_by=audited_by,
            audit_evidence=evidence,
        )


# P5-F3: per-target default `type` so re-extract preservation identity matches.
TARGET_DEFAULT_TYPE = {
    "gaap":       "GAAP",
    "nongaap":    "NON_GAAP",
    "supplement": "GAAP_SEGMENT",
}


def build_new_row(target: str, args) -> dict:
    """Build a brand new row when no existing row matches.

    P5-F2: supplement new rows now MUST carry period_end + type + source_doc
    so the downstream adapter doesn't reject them.
    P5-F3: GAAP / 8K / supplement new rows get sensible default `type` so
    schema §6.1 preservation identity matches across re-extract.
    P5-F4: supplement new rows honor --other-dimensions-json (no longer
    hardcoded to []).
    """
    row: dict[str, Any] = {
        "period":         args.period,
        "uni_account":    args.uni_account,
        "value":          args.new_value,
        "unit":           args.unit,
    }
    if args.source_account:
        row["source_account"] = args.source_account
    # P5-F3: type default
    row["type"] = args.row_type or TARGET_DEFAULT_TYPE[target]
    if target == "supplement":
        # P5-F2: supplement adapter requires period_end (valid ISO date) +
        # period_kind. Fail-closed before writing a row that downstream
        # would reject.
        if not args.period_end:
            raise ValueError(
                "supplement new row requires --period-end (ISO date). "
                "Without it the downstream adapter would reject the row."
            )
        row["period_end"] = args.period_end
        if not args.period_kind:
            raise ValueError(
                "supplement new row requires --period-kind "
                "(single_quarter / fy_annual / instant)."
            )
        row["period_kind"] = args.period_kind
        if args.axis:
            row["axis"] = args.axis
        if args.axis_qname:
            row["axis_qname"] = args.axis_qname
        if args.member_qname:
            row["source_account_qname"] = args.member_qname
        # P5-F2: source_doc for traceability (matches parser-produced rows)
        if args.source_doc:
            row["source_doc"] = args.source_doc
        if args.decimals is not None:
            row["decimals"] = args.decimals
        # P5-F4: honor caller-supplied other_dimensions
        row["other_dimensions"] = _parsed_other_dimensions(args)
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


def _validate_args(args) -> None:
    """Pre-flight CLI validation. P5-F7: must specify either audit_source
    OR classification_source, not both."""
    has_audit = bool(args.audit_source)
    has_cls = bool(args.classification_source)
    if has_audit and has_cls:
        raise ValueError(
            "--audit-source and --classification-source are mutually exclusive. "
            "Use audit channel for value corrections (MANUAL_AUDIT_FROM_OFFICIAL_FILING / "
            "MANUAL_RESTATEMENT_FROM_AMENDED_FILING) or classification channel "
            "for row bucket reclassification (MANUAL_RECLASSIFIED), not both."
        )
    if not has_audit and not has_cls:
        raise ValueError(
            "must specify either --audit-source or --classification-source."
        )
    if has_cls and args.classification_source not in MANUAL_CLASSIFICATION_SOURCES:
        raise ValueError(
            f"invalid --classification-source: {args.classification_source!r}. "
            f"Must be one of {sorted(MANUAL_CLASSIFICATION_SOURCES)}."
        )


def run(args) -> int:
    _validate_args(args)
    target = args.target
    ticker = args.ticker.upper()
    json_path = resolve_json_path(target, ticker, args.json_path)
    if not json_path.exists():
        sys.exit(f"❌ Target JSON not found: {json_path}")

    audited_at_iso = datetime.now(timezone.utc).isoformat()
    audited_by = args.audited_by or os.environ.get("USER") or "user"
    is_classification_edit = bool(args.classification_source)

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
    stamped_row: dict[str, Any]
    if existing_row is None:
        # Brand new row
        new_row = build_new_row(target, args)
        stamp_edit(new_row, args, audited_at_iso, audited_by)
        operation = ("stamp_new_classification_row" if is_classification_edit
                     else "stamp_new_row")
        stamped_row = new_row
        if not args.dry_run:
            facts.append(new_row)
    else:
        prior_value = existing_row.get("value")
        was_audited = row_has_audited_value(existing_row)
        if was_audited and not args.accept_new_values and not is_classification_edit:
            sys.exit(
                f"❌ Row already carries audit metadata "
                f"(audit_source={existing_row.get('audit_source')!r}, "
                f"value={prior_value}). "
                f"Pass --accept-new-values to override and write "
                f"accepted_new_value_replaces_audit forensic field."
            )
        if is_classification_edit:
            operation = "stamp_classification_existing_row"
        else:
            operation = "override_existing_audit" if was_audited else "stamp_existing_row"
        # Apply in place (also for dry-run, mutate a copy for diff)
        target_row = existing_row if not args.dry_run else dict(existing_row)
        stamp_edit(
            target_row, args, audited_at_iso, audited_by,
            prior_value=prior_value, is_override=(was_audited and not is_classification_edit),
        )
        stamped_row = target_row

    print(f"=== manual_edit ({operation}) ===")
    print(f"  Ticker:     {ticker}")
    print(f"  Target:     {target}  ({json_path})")
    print(f"  Period:     {args.period}")
    print(f"  uni_account:{args.uni_account}")
    if args.source_account:
        print(f"  source_acc: {args.source_account}")
    print(f"  Diff:       {prior_value} → {args.new_value}")
    if is_classification_edit:
        print(f"  Class src:  {args.classification_source}")
    else:
        print(f"  Audit src:  {args.audit_source} "
              f"(raw stored: {stamped_row.get('audit_source_raw')})")
    print(f"  Audited by: {audited_by} at {audited_at_iso}")
    if args.dry_run:
        print(f"  (dry-run — no write)")
        return 0

    json_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False))

    # P5-F6: log reads canonical + raw from the stamped row (not args.audit_source,
    # which could be a legacy enum that got normalized by stamp_audit_provenance).
    log_entry: dict[str, Any] = {
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
        "audited_by":     audited_by,
    }
    if is_classification_edit:
        log_entry["classification_source"] = stamped_row.get("classification_source")
        if args.classification_note:
            log_entry["classification_note"] = args.classification_note
    else:
        log_entry["audit_source"] = stamped_row.get("audit_source")
        log_entry["audit_source_raw"] = stamped_row.get("audit_source_raw")
        log_entry["audit_evidence"] = build_audit_evidence(args)
        if args.audit_note:
            log_entry["audit_note"] = args.audit_note
        if "accepted_new_value_replaces_audit" in stamped_row:
            log_entry["accepted_new_value_replaces_audit"] = (
                stamped_row["accepted_new_value_replaces_audit"]
            )
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
    ap.add_argument("--new-value", required=True, type=float,
                    help="The corrected value (always required — even for "
                         "classification edits, the row's value field is set).")
    ap.add_argument("--audit-source",
                    help="One of MANUAL_AUDIT_FROM_OFFICIAL_FILING / "
                         "MANUAL_RESTATEMENT_FROM_AMENDED_FILING (legacy "
                         "enums accepted but normalized). Mutually exclusive "
                         "with --classification-source.")
    # P5-F7: classification path
    ap.add_argument("--classification-source",
                    help="One of MANUAL_RECLASSIFIED / AGENT_CLASSIFIED. "
                         "Use for row bucket re-classification (not value "
                         "correction). Mutually exclusive with --audit-source.")
    ap.add_argument("--classification-note", help="Freeform classification reasoning.")
    ap.add_argument("--long-tail-metadata-json",
                    help="JSON object for long_tail_metadata field "
                         "(e.g. {\"rolls_up_to\": \"operating_expenses\"}).")
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
    # P5-F2: supplement new-row downstream requirements
    ap.add_argument("--period-end",
                    help="Supplement new row: ISO date for period_end "
                         "(required when creating a new supplement row; "
                         "downstream adapter rejects rows without it).")
    ap.add_argument("--decimals", type=int,
                    help="Supplement new row: XBRL decimals attribute.")
    # P5-F4: multi-dim supplement
    ap.add_argument("--other-dimensions-json",
                    help='Supplement multi-dim: JSON list of {axis, member} '
                         'objects, e.g. \'[{"axis": "srt:Geo", "member": "country:US"}]\'.')
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
