"""Phase 5 regression tests — manual_edit.py CLI for ad-hoc audit edits.

Covers schema v4 §2 row schema, §3 audit allowlist, §4 stamp helpers, §11
accepted_new_value_replaces_audit forensic field.

Run: uv run --with pytest python3 -m pytest scripts/tests/test_phase5_manual_edit.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "Tools" / "research-tools"))

import manual_edit  # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────────────

def _write_gaap(tmp_path, rows):
    p = tmp_path / "LITE_gaap.json"
    p.write_text(json.dumps({"metadata": {"ticker": "LITE"}, "income_statement": rows}))
    return p


def _write_supplement(tmp_path, facts):
    p = tmp_path / "LITE_supplement_facts_v3.json"
    p.write_text(json.dumps({"metadata": {"ticker": "LITE"}, "facts": facts}))
    return p


def _run(json_path, **overrides):
    """Invoke manual_edit.run() with default args + overrides."""
    defaults = {
        "ticker":            "LITE",
        "target":            "gaap",
        "period":            "Q1_FY2026",
        "uni_account":       "income_before_taxes",
        "new_value":         -172.1,
        "source_account":    None,
        "row_type":          None,
        "unit":              "USD_millions",
        "period_kind":       None,
        "axis":              None,
        "axis_qname":        None,
        "member_qname":      None,
        "audit_source":      "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "source_doc":        "lite-20250927.htm",
        "page_or_section":   None,
        "quote":             None,
        "accession_number":  None,
        "period_scope":      None,
        "audit_note":        "10-Q income statement",
        "audited_by":        "test@example.com",
        "accept_new_values": False,
        "dry_run":           False,
        "json_path":         str(json_path),
        "facts_key":         None,
    }
    defaults.update(overrides)
    return manual_edit.run(_NS(**defaults))


class _NS:
    """argparse.Namespace-like for run() input."""
    def __init__(self, **kw):
        self.__dict__.update(kw)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5.1: stamp new audit on existing un-audited row
# ─────────────────────────────────────────────────────────────────────────────

def test_stamp_existing_row_writes_v4_metadata(tmp_path):
    """Existing row without audit_source → stamp new audit metadata."""
    p = _write_gaap(tmp_path, [{
        "period": "Q1_FY2026", "uni_account": "income_before_taxes",
        "source_account": "IncomeLossFromContinuingOperationsBeforeIncomeTax",
        "value": -150.0, "unit": "USD_millions", "type": "GAAP",
    }])
    rc = _run(p)
    assert rc == 0
    doc = json.loads(p.read_text())
    row = doc["income_statement"][0]
    assert row["value"] == -172.1   # new value
    assert row["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    assert row["audit_source_raw"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    assert row["audit_note"] == "10-Q income statement"
    assert row["audit_evidence"]["source_doc"] == "lite-20250927.htm"
    assert row["audited_by"] == "test@example.com"


def test_stamp_appends_to_log(tmp_path):
    p = _write_gaap(tmp_path, [{
        "period": "Q1_FY2026", "uni_account": "income_before_taxes",
        "value": -150.0, "unit": "USD_millions", "type": "GAAP",
    }])
    _run(p)
    log = (tmp_path / "manual_edit_audit_log.jsonl").read_text()
    lines = [json.loads(l) for l in log.strip().splitlines()]
    assert len(lines) == 1
    entry = lines[0]
    assert entry["ticker"] == "LITE"
    assert entry["operation"] == "stamp_existing_row"
    assert entry["prior_value"] == -150.0
    assert entry["new_value"] == -172.1
    assert entry["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"


def test_stamp_new_row_when_no_match(tmp_path):
    """No matching row → append new row with v4 audit metadata."""
    p = _write_gaap(tmp_path, [])
    _run(p)
    doc = json.loads(p.read_text())
    assert len(doc["income_statement"]) == 1
    row = doc["income_statement"][0]
    assert row["value"] == -172.1
    assert row["uni_account"] == "income_before_taxes"
    assert row["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    log = (tmp_path / "manual_edit_audit_log.jsonl").read_text()
    assert json.loads(log.strip())["operation"] == "stamp_new_row"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5.2: override existing audit (--accept-new-values)
# ─────────────────────────────────────────────────────────────────────────────

def test_override_requires_accept_new_values_flag(tmp_path):
    """Row already has audit metadata → without --accept-new-values, exit."""
    p = _write_gaap(tmp_path, [{
        "period": "Q1_FY2026", "uni_account": "income_before_taxes",
        "value": -150.0, "unit": "USD_millions", "type": "GAAP",
        "audit_source": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "audit_source_raw": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "audit_note": "prior audit",
    }])
    with pytest.raises(SystemExit) as exc:
        _run(p)
    assert "already carries audit metadata" in str(exc.value)


def test_override_with_accept_new_values_writes_forensic(tmp_path):
    """--accept-new-values + existing audit → write accepted_new_value_replaces_audit."""
    p = _write_gaap(tmp_path, [{
        "period": "Q1_FY2026", "uni_account": "income_before_taxes",
        "value": -150.0, "unit": "USD_millions", "type": "GAAP",
        "audit_source": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "audit_source_raw": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "audit_note": "prior audit",
    }])
    _run(p, new_value=-180.0, accept_new_values=True,
         source_doc="amended-filing.htm", audit_note="override after amendment")
    doc = json.loads(p.read_text())
    row = doc["income_statement"][0]
    assert row["value"] == -180.0
    assert row["audit_note"] == "override after amendment"
    assert row["audit_evidence"]["source_doc"] == "amended-filing.htm"
    # Forensic field per schema §11
    assert row["accepted_new_value_replaces_audit"]["prior_audit_value"] == -150.0
    assert row["accepted_new_value_replaces_audit"]["new_extracted_value"] == -180.0
    log = json.loads((tmp_path / "manual_edit_audit_log.jsonl").read_text().strip())
    assert log["operation"] == "override_existing_audit"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5.3: dry-run + safety guards
# ─────────────────────────────────────────────────────────────────────────────

def test_dry_run_does_not_write(tmp_path):
    """--dry-run shows diff but doesn't mutate JSON or log."""
    p = _write_gaap(tmp_path, [{
        "period": "Q1_FY2026", "uni_account": "income_before_taxes",
        "value": -150.0, "unit": "USD_millions", "type": "GAAP",
    }])
    original = p.read_text()
    _run(p, dry_run=True)
    assert p.read_text() == original  # unchanged
    assert not (tmp_path / "manual_edit_audit_log.jsonl").exists()


def test_missing_locator_rejected(tmp_path):
    """Schema §2.2: OFFICIAL_FILING requires source_doc OR page_or_section.
    manual_edit relies on stamp_audit_provenance to enforce this."""
    p = _write_gaap(tmp_path, [{
        "period": "Q1_FY2026", "uni_account": "income_before_taxes",
        "value": -150.0, "unit": "USD_millions", "type": "GAAP",
    }])
    with pytest.raises(ValueError, match="audit_evidence|source_doc|page_or_section"):
        _run(p, source_doc=None, page_or_section=None)


def test_restatement_requires_accession_number(tmp_path):
    """Schema §2.2: RESTATEMENT requires accession_number."""
    p = _write_gaap(tmp_path, [{
        "period": "Q1_FY2026", "uni_account": "income_before_taxes",
        "value": -150.0, "unit": "USD_millions", "type": "GAAP",
    }])
    with pytest.raises(ValueError, match="accession_number"):
        _run(p,
             audit_source="MANUAL_RESTATEMENT_FROM_AMENDED_FILING",
             source_doc="amended.htm",
             accession_number=None)


def test_restatement_with_accession_succeeds(tmp_path):
    p = _write_gaap(tmp_path, [{
        "period": "Q1_FY2026", "uni_account": "income_before_taxes",
        "value": -150.0, "unit": "USD_millions", "type": "GAAP",
    }])
    _run(p,
         audit_source="MANUAL_RESTATEMENT_FROM_AMENDED_FILING",
         source_doc="amended.htm",
         accession_number="0001234567-25-000001")
    row = json.loads(p.read_text())["income_statement"][0]
    assert row["audit_source"] == "MANUAL_RESTATEMENT_FROM_AMENDED_FILING"
    assert row["audit_evidence"]["accession_number"] == "0001234567-25-000001"


def test_json_path_missing_exits(tmp_path):
    """Target JSON doesn't exist → fail-closed."""
    with pytest.raises(SystemExit) as exc:
        _run(tmp_path / "nonexistent.json")
    assert "not found" in str(exc.value)


# ─────────────────────────────────────────────────────────────────────────────
# Disambiguation: ambiguous match raises
# ─────────────────────────────────────────────────────────────────────────────

def test_ambiguous_match_raises(tmp_path):
    """Two rows share (period, uni_account) — caller must narrow with
    --source-account."""
    p = _write_gaap(tmp_path, [
        {"period": "Q1_FY2026", "uni_account": "operating_expense_long_tail",
         "source_account": "Goodwill Impairment", "value": 10.0,
         "unit": "USD_millions", "type": "GAAP"},
        {"period": "Q1_FY2026", "uni_account": "operating_expense_long_tail",
         "source_account": "Restructuring", "value": 5.0,
         "unit": "USD_millions", "type": "GAAP"},
    ])
    with pytest.raises(ValueError, match="ambiguous"):
        _run(p, uni_account="operating_expense_long_tail")


def test_disambiguated_with_source_account_finds_one(tmp_path):
    p = _write_gaap(tmp_path, [
        {"period": "Q1_FY2026", "uni_account": "operating_expense_long_tail",
         "source_account": "Goodwill Impairment", "value": 10.0,
         "unit": "USD_millions", "type": "GAAP"},
        {"period": "Q1_FY2026", "uni_account": "operating_expense_long_tail",
         "source_account": "Restructuring", "value": 5.0,
         "unit": "USD_millions", "type": "GAAP"},
    ])
    _run(p,
         uni_account="operating_expense_long_tail",
         source_account="Goodwill Impairment",
         new_value=12.0)
    rows = json.loads(p.read_text())["income_statement"]
    by_src = {r["source_account"]: r for r in rows}
    assert by_src["Goodwill Impairment"]["value"] == 12.0
    assert "audit_source" in by_src["Goodwill Impairment"]
    assert by_src["Restructuring"]["value"] == 5.0
    assert "audit_source" not in by_src["Restructuring"]


# ─────────────────────────────────────────────────────────────────────────────
# Supplement target
# ─────────────────────────────────────────────────────────────────────────────

def test_supplement_target_match_and_stamp(tmp_path):
    """Supplement uses dimensional identity (axis_qname + member_qname)."""
    p = _write_supplement(tmp_path, [{
        "period":               "Q1_FY2026",
        "period_kind":          "single_quarter",
        "axis":                 "business_segment",
        "axis_qname":           "us-gaap:StatementBusinessSegmentsAxis",
        "source_account":       "Components",
        "source_account_qname": "us-gaap:ComponentsMember",
        "uni_account":          "revenue",
        "value":                370.0,
        "unit":                 "USD_millions",
        "other_dimensions":     [],
        "type":                 "GAAP_SEGMENT",
    }])
    _run(p,
         target="supplement",
         period="Q1_FY2026",
         uni_account="revenue",
         new_value=379.2,
         source_account="Components",
         period_kind="single_quarter",
         axis="business_segment",
         axis_qname="us-gaap:StatementBusinessSegmentsAxis",
         member_qname="us-gaap:ComponentsMember",
         source_doc="lite-Q1-FY26.htm")
    fact = json.loads(p.read_text())["facts"][0]
    assert fact["value"] == 379.2
    assert fact["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    assert fact["audit_evidence"]["source_doc"] == "lite-Q1-FY26.htm"


def test_supplement_target_no_match_creates_new_row(tmp_path):
    """Supplement: no matching dimensional identity → create new fact."""
    p = _write_supplement(tmp_path, [])
    _run(p,
         target="supplement",
         period="Q1_FY2026",
         uni_account="revenue",
         new_value=379.2,
         source_account="Components",
         period_kind="single_quarter",
         axis="business_segment",
         axis_qname="us-gaap:StatementBusinessSegmentsAxis",
         member_qname="us-gaap:ComponentsMember",
         source_doc="lite-Q1-FY26.htm")
    facts = json.loads(p.read_text())["facts"]
    assert len(facts) == 1
    assert facts[0]["value"] == 379.2
    assert facts[0]["axis_qname"] == "us-gaap:StatementBusinessSegmentsAxis"
    assert facts[0]["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"


# ─────────────────────────────────────────────────────────────────────────────
# Legacy enum input
# ─────────────────────────────────────────────────────────────────────────────

def test_legacy_audit_source_normalized_to_canonical(tmp_path):
    """User passes legacy MANUAL_AUDIT_FROM_PDF → adapter writes canonical
    + audit_source_raw preserves legacy."""
    p = _write_gaap(tmp_path, [{
        "period": "Q1_FY2026", "uni_account": "income_before_taxes",
        "value": -150.0, "unit": "USD_millions", "type": "GAAP",
    }])
    _run(p, audit_source="MANUAL_AUDIT_FROM_PDF")
    row = json.loads(p.read_text())["income_statement"][0]
    assert row["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    assert row["audit_source_raw"] == "MANUAL_AUDIT_FROM_PDF"


def test_unknown_audit_source_rejected(tmp_path):
    p = _write_gaap(tmp_path, [{
        "period": "Q1_FY2026", "uni_account": "income_before_taxes",
        "value": -150.0, "unit": "USD_millions", "type": "GAAP",
    }])
    with pytest.raises(ValueError, match="unknown audit_source"):
        _run(p, audit_source="SOME_INVALID_ENUM")
