"""Regression tests for xbrl_extract._preserve_audited_cells — schema v4 §5.

Covers the behavior matrix:
  MATCH        → copy provenance + classification, no event
  ADDED_BACK   → carry old row + set REEXTRACT_PRESERVED_PRIOR_AUDIT
  CONFLICT     → restore old value + set REEXTRACT_PRESERVED_PRIOR_AUDIT
  ACCEPT_NEW   → clear audit provenance (classification kept)
  LEGACY       → AGENT_CLASSIFIED in audit_source field still preserved

Run: uv run --with pytest python3 -m pytest scripts/tests/test_xbrl_extract_preservation.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "Tools" / "research-tools"))
sys.path.insert(
    0,
    "/Users/mensch5566/CC_Switch_Config/skills/parse-10QK-gaap/scripts",
)

import xbrl_extract  # noqa: E402


def _write_existing(tmp_path, rows):
    p = tmp_path / "existing.json"
    p.write_text(json.dumps({"income_statement": rows}))
    return str(p)


# ── MATCH ────────────────────────────────────────────────────────────────────

def test_match_copies_audit_provenance_no_event(tmp_path):
    existing = _write_existing(tmp_path, [{
        "period": "Q1_FY2026", "uni_account": "revenue", "value": 100.0,
        "audit_source": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "audit_source_raw": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "audit_note": "from 10-Q", "audited_at": "2026-05-21T00:00:00Z",
    }])
    new_data = {"income_statement": [
        {"period": "Q1_FY2026", "uni_account": "revenue", "value": 100.0}
    ]}
    out, n_pres, n_conf = xbrl_extract._preserve_audited_cells(new_data, existing)
    new_row = out["income_statement"][0]
    assert new_row["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    assert new_row["audit_note"] == "from 10-Q"
    # MATCH should NOT set preservation event
    assert "preservation_event" not in new_row
    assert "preserved_from_audit" not in new_row
    assert n_pres == 1 and n_conf == 0


# ── ADDED_BACK ──────────────────────────────────────────────────────────────

def test_added_back_carries_row_with_audit_event(tmp_path):
    existing = _write_existing(tmp_path, [{
        "period": "FY2024", "uni_account": "income_before_taxes", "value": -172.1,
        "audit_source": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "audit_source_raw": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "audit_note": "PDF table",
    }])
    new_data = {"income_statement": []}
    out, n_pres, n_conf = xbrl_extract._preserve_audited_cells(new_data, existing)
    assert len(out["income_statement"]) == 1
    new_row = out["income_statement"][0]
    assert new_row["value"] == -172.1
    assert new_row["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    assert new_row["preservation_event"] == "REEXTRACT_PRESERVED_PRIOR_AUDIT"
    assert new_row["preserved_from_audit"] is True
    assert "preserved_at" in new_row
    assert n_pres == 1 and n_conf == 0


def test_added_back_classification_only_sets_classification_event(tmp_path):
    existing = _write_existing(tmp_path, [{
        "period": "Q1_FY2026", "uni_account": "operating_expense_long_tail",
        "value": 5.0,
        "classification_source": "AGENT_CLASSIFIED",
        "long_tail_metadata": {"rolls_up_to": "operating_expenses"},
    }])
    new_data = {"income_statement": []}
    out, *_ = xbrl_extract._preserve_audited_cells(new_data, existing)
    new_row = out["income_statement"][0]
    assert new_row["preservation_event"] == "REEXTRACT_PRESERVED_PRIOR_CLASSIFICATION"
    assert new_row["preserved_from_audit"] is False
    assert new_row["classification_source"] == "AGENT_CLASSIFIED"


# ── CONFLICT (default: keep audit) ──────────────────────────────────────────

def test_conflict_default_keeps_audit_and_sets_event(tmp_path):
    existing = _write_existing(tmp_path, [{
        "period": "Q1_FY2026", "uni_account": "revenue", "value": 100.0,
        "audit_source": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "audit_source_raw": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
    }])
    new_data = {"income_statement": [
        {"period": "Q1_FY2026", "uni_account": "revenue", "value": 999.0}
    ]}
    out, n_pres, n_conf = xbrl_extract._preserve_audited_cells(new_data, existing)
    new_row = out["income_statement"][0]
    assert new_row["value"] == 100.0  # audited value restored
    assert new_row["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    assert new_row["preservation_event"] == "REEXTRACT_PRESERVED_PRIOR_AUDIT"
    assert new_row["new_extract_value_rejected"] == 999.0
    assert n_conf == 1


# ── CONFLICT + accept_new_values ─────────────────────────────────────────────

def test_conflict_accept_new_clears_audit_provenance(tmp_path):
    existing = _write_existing(tmp_path, [{
        "period": "Q1_FY2026", "uni_account": "revenue", "value": 100.0,
        "audit_source": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "audit_source_raw": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "audit_note": "old", "audited_at": "2026-05-21T00:00:00Z",
    }])
    new_data = {"income_statement": [
        {"period": "Q1_FY2026", "uni_account": "revenue", "value": 999.0}
    ]}
    out, *_ = xbrl_extract._preserve_audited_cells(
        new_data, existing, accept_new_values=True
    )
    new_row = out["income_statement"][0]
    assert new_row["value"] == 999.0
    assert "audit_source" not in new_row
    assert "audit_note" not in new_row
    assert "preservation_event" not in new_row
    assert new_row["accepted_new_value_replaces_audit"]["prior_audit_value"] == 100.0


# ── Legacy AGENT_CLASSIFIED in audit_source field ────────────────────────────

def test_legacy_agent_classified_in_audit_source_field_preserved(tmp_path):
    """Pre-v4 apply_audit wrote AGENT_CLASSIFIED into audit_source. We still
    must preserve those rows (as classification, not audit)."""
    existing = _write_existing(tmp_path, [{
        "period": "Q3_FY2025", "uni_account": "operating_expense_long_tail",
        "value": 3.5,
        "audit_source": "AGENT_CLASSIFIED",
        "long_tail_metadata": {"rolls_up_to": "operating_expenses"},
    }])
    new_data = {"income_statement": []}
    out, n_pres, _ = xbrl_extract._preserve_audited_cells(new_data, existing)
    assert n_pres == 1
    new_row = out["income_statement"][0]
    # Legacy field carried through (don't lose data)
    assert new_row["audit_source"] == "AGENT_CLASSIFIED"
    # Treated as classification preservation, not audit
    assert new_row["preservation_event"] == "REEXTRACT_PRESERVED_PRIOR_CLASSIFICATION"
    assert new_row["preserved_from_audit"] is False


# ── Legacy MANUAL_AUDIT_FROM_PDF still detected ─────────────────────────────

def test_legacy_manual_audit_from_pdf_detected_as_audit(tmp_path):
    existing = _write_existing(tmp_path, [{
        "period": "Q1_FY2025", "uni_account": "revenue", "value": 250.0,
        "audit_source": "MANUAL_AUDIT_FROM_PDF",  # legacy
    }])
    new_data = {"income_statement": []}
    out, *_ = xbrl_extract._preserve_audited_cells(new_data, existing)
    new_row = out["income_statement"][0]
    assert new_row["preservation_event"] == "REEXTRACT_PRESERVED_PRIOR_AUDIT"
    assert new_row["audit_source"] == "MANUAL_AUDIT_FROM_PDF"  # raw preserved as-is


# ── No audit/classification → no-op ──────────────────────────────────────────

def test_no_audit_or_classification_rows_no_op(tmp_path):
    existing = _write_existing(tmp_path, [{
        "period": "Q1_FY2026", "uni_account": "revenue", "value": 100.0,
    }])
    new_data = {"income_statement": [
        {"period": "Q1_FY2026", "uni_account": "revenue", "value": 200.0}
    ]}
    out, n_pres, n_conf = xbrl_extract._preserve_audited_cells(new_data, existing)
    assert n_pres == 0 and n_conf == 0
    assert out["income_statement"][0]["value"] == 200.0  # new value wins


# ── Stale preservation timestamps not carried forward ───────────────────────

def test_added_back_does_not_carry_stale_preserved_at(tmp_path):
    """If old row already had preserved_at from a prior re-extract,
    the new preservation event should use a fresh timestamp."""
    existing = _write_existing(tmp_path, [{
        "period": "FY2023", "uni_account": "revenue", "value": 500.0,
        "audit_source": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "preserved_from_audit": True,
        "preserved_at": "2020-01-01T00:00:00Z",
        "preservation_event": "REEXTRACT_PRESERVED_PRIOR_AUDIT",
    }])
    new_data = {"income_statement": []}
    out, *_ = xbrl_extract._preserve_audited_cells(new_data, existing)
    new_row = out["income_statement"][0]
    assert new_row["preserved_at"] != "2020-01-01T00:00:00Z"  # fresh timestamp


# ── F2 fix: classification-only conflict gets classification event ───────────

def test_classification_only_conflict_uses_classification_event(tmp_path):
    existing = _write_existing(tmp_path, [{
        "period": "Q1_FY2026", "uni_account": "operating_expense_long_tail",
        "source_account": "Some Long-Tail Item", "unit": "USD_millions",
        "type": "GAAP", "value": 5.0,
        "classification_source": "AGENT_CLASSIFIED",
        "long_tail_metadata": {"rolls_up_to": "operating_expenses"},
    }])
    new_data = {"income_statement": [{
        "period": "Q1_FY2026", "uni_account": "operating_expense_long_tail",
        "source_account": "Some Long-Tail Item", "unit": "USD_millions",
        "type": "GAAP", "value": 7.5,  # value differs
    }]}
    out, _, n_conf = xbrl_extract._preserve_audited_cells(new_data, existing)
    new_row = out["income_statement"][0]
    assert n_conf == 1
    assert new_row["value"] == 5.0  # restored
    # F2: classification-only conflict must use CLASSIFICATION event, not AUDIT
    assert new_row["preservation_event"] == "REEXTRACT_PRESERVED_PRIOR_CLASSIFICATION"
    assert new_row["preserved_from_audit"] is False
    assert new_row["classification_source"] == "AGENT_CLASSIFIED"
    assert new_row["new_extract_value_rejected"] == 7.5


def test_classification_only_accept_new_keeps_classification(tmp_path):
    """ACCEPT_NEW + classification-only: classification must be carried
    explicitly (was a bug pre-F2)."""
    existing = _write_existing(tmp_path, [{
        "period": "Q1_FY2026", "uni_account": "operating_expense_long_tail",
        "source_account": "Some Item", "unit": "USD_millions", "type": "GAAP",
        "value": 5.0,
        "classification_source": "AGENT_CLASSIFIED",
        "long_tail_metadata": {"rolls_up_to": "operating_expenses"},
    }])
    new_data = {"income_statement": [{
        "period": "Q1_FY2026", "uni_account": "operating_expense_long_tail",
        "source_account": "Some Item", "unit": "USD_millions", "type": "GAAP",
        "value": 9.9,
    }]}
    out, *_ = xbrl_extract._preserve_audited_cells(
        new_data, existing, accept_new_values=True
    )
    new_row = out["income_statement"][0]
    assert new_row["value"] == 9.9  # new value wins
    # Classification must be explicitly carried
    assert new_row["classification_source"] == "AGENT_CLASSIFIED"
    assert new_row["long_tail_metadata"]["rolls_up_to"] == "operating_expenses"
    # F2/F5: accepted_new_value_replaces_audit must NOT be written for
    # classification-only accept-new
    assert "accepted_new_value_replaces_audit" not in new_row


def test_audit_and_classification_conflict_audit_takes_priority(tmp_path):
    """Row has BOTH audit + classification, value conflict.
    Audit takes priority on event type, both metadata copied."""
    existing = _write_existing(tmp_path, [{
        "period": "Q1_FY2026", "uni_account": "research_and_development",
        "source_account": "ResearchAndDevelopmentExpense", "unit": "USD_millions",
        "type": "GAAP", "value": 50.0,
        "audit_source": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "audit_source_raw": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "classification_source": "AGENT_CLASSIFIED",
        "long_tail_metadata": {"rolls_up_to": "operating_expenses"},
    }])
    new_data = {"income_statement": [{
        "period": "Q1_FY2026", "uni_account": "research_and_development",
        "source_account": "ResearchAndDevelopmentExpense", "unit": "USD_millions",
        "type": "GAAP", "value": 60.0,
    }]}
    out, _, n_conf = xbrl_extract._preserve_audited_cells(new_data, existing)
    new_row = out["income_statement"][0]
    assert n_conf == 1
    assert new_row["value"] == 50.0
    assert new_row["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    assert new_row["classification_source"] == "AGENT_CLASSIFIED"
    # Audit priority on event
    assert new_row["preservation_event"] == "REEXTRACT_PRESERVED_PRIOR_AUDIT"


# ── F1 fix: duplicate identity fails closed ──────────────────────────────────

def test_duplicate_identity_in_new_extract_fails_closed(tmp_path):
    """Two rows in new extract with same identity tuple → fail-closed."""
    existing = _write_existing(tmp_path, [{
        "period": "Q1_FY2026", "uni_account": "revenue",
        "source_account": "Revenues", "unit": "USD_millions", "type": "GAAP",
        "value": 100.0,
        "audit_source": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
    }])
    # Two new rows with identical identity (statement+period+uni+source+unit+type)
    new_data = {"income_statement": [
        {"period": "Q1_FY2026", "uni_account": "revenue",
         "source_account": "Revenues", "unit": "USD_millions", "type": "GAAP",
         "value": 100.0},
        {"period": "Q1_FY2026", "uni_account": "revenue",
         "source_account": "Revenues", "unit": "USD_millions", "type": "GAAP",
         "value": 999.0},  # duplicate
    ]}
    from _shared.audit_metadata import DuplicateIdentityError
    with pytest.raises(DuplicateIdentityError, match="duplicate identity"):
        xbrl_extract._preserve_audited_cells(new_data, existing)


def test_duplicate_identity_in_existing_audited_fails_closed(tmp_path):
    existing = _write_existing(tmp_path, [
        {"period": "Q1_FY2026", "uni_account": "revenue",
         "source_account": "Revenues", "unit": "USD_millions", "type": "GAAP",
         "value": 100.0, "audit_source": "MANUAL_AUDIT_FROM_OFFICIAL_FILING"},
        {"period": "Q1_FY2026", "uni_account": "revenue",
         "source_account": "Revenues", "unit": "USD_millions", "type": "GAAP",
         "value": 999.0, "audit_source": "MANUAL_AUDIT_FROM_OFFICIAL_FILING"},
    ])
    new_data = {"income_statement": []}
    from _shared.audit_metadata import DuplicateIdentityError
    with pytest.raises(DuplicateIdentityError, match="duplicate audit"):
        xbrl_extract._preserve_audited_cells(new_data, existing)


def test_long_tail_rows_with_different_source_account_no_collision(tmp_path):
    """Two long-tail rows sharing uni_account but different source_account
    must NOT collide on identity (this is the bug F1 fixes)."""
    existing = _write_existing(tmp_path, [
        {"period": "Q1_FY2026", "uni_account": "operating_expense_long_tail",
         "source_account": "Goodwill Impairment", "unit": "USD_millions",
         "type": "GAAP", "value": 10.0,
         "classification_source": "AGENT_CLASSIFIED"},
        {"period": "Q1_FY2026", "uni_account": "operating_expense_long_tail",
         "source_account": "Restructuring", "unit": "USD_millions",
         "type": "GAAP", "value": 5.0,
         "classification_source": "AGENT_CLASSIFIED"},
    ])
    new_data = {"income_statement": []}
    # Should succeed (no collision) and preserve BOTH rows
    out, n_pres, _ = xbrl_extract._preserve_audited_cells(new_data, existing)
    assert n_pres == 2
    sources = {r["source_account"] for r in out["income_statement"]}
    assert sources == {"Goodwill Impairment", "Restructuring"}
