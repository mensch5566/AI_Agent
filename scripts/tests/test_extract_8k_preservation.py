"""Regression tests for extract_8k_nongaap._preserve_audited_cells — schema v4 §5.

Mirrors xbrl_extract preservation tests; ensures both pipelines stay in sync.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "Tools" / "research-tools"))
sys.path.insert(
    0,
    "/Users/mensch5566/CC_Switch_Config/skills/parse-8k-nongaap/scripts",
)

import extract_8k_nongaap as e8k  # noqa: E402


def _write_existing(tmp_path, rows):
    p = tmp_path / "existing.json"
    p.write_text(json.dumps({"income_statement": rows}))
    return str(p)


def test_8k_match_carries_audit_no_event(tmp_path):
    existing = _write_existing(tmp_path, [{
        "period": "Q1_FY2026", "uni_account": "adj_eps", "value": 1.23,
        "audit_source": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "audit_source_raw": "MANUAL_AUDIT_FROM_8K_PDF",
    }])
    new_data = {"income_statement": [
        {"period": "Q1_FY2026", "uni_account": "adj_eps", "value": 1.23}
    ]}
    out, *_ = e8k._preserve_audited_cells(new_data, existing)
    row = out["income_statement"][0]
    assert row["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    assert row["audit_source_raw"] == "MANUAL_AUDIT_FROM_8K_PDF"
    assert "preservation_event" not in row


def test_8k_conflict_default_preserves_audit(tmp_path):
    existing = _write_existing(tmp_path, [{
        "period": "Q1_FY2026", "uni_account": "adj_eps", "value": 1.23,
        "audit_source": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
    }])
    new_data = {"income_statement": [
        {"period": "Q1_FY2026", "uni_account": "adj_eps", "value": 9.99}
    ]}
    out, _, n_conf = e8k._preserve_audited_cells(new_data, existing)
    row = out["income_statement"][0]
    assert row["value"] == 1.23
    assert row["preservation_event"] == "REEXTRACT_PRESERVED_PRIOR_AUDIT"
    assert row["new_extract_value_rejected"] == 9.99
    assert n_conf == 1


def test_8k_legacy_audit_from_8k_pdf_detected(tmp_path):
    existing = _write_existing(tmp_path, [{
        "period": "Q4_FY2025", "uni_account": "adj_net_income", "value": 50.0,
        "audit_source": "MANUAL_AUDIT_FROM_8K_PDF",  # legacy raw
    }])
    new_data = {"income_statement": []}
    out, *_ = e8k._preserve_audited_cells(new_data, existing)
    row = out["income_statement"][0]
    assert row["preservation_event"] == "REEXTRACT_PRESERVED_PRIOR_AUDIT"
    assert row["audit_source"] == "MANUAL_AUDIT_FROM_8K_PDF"


def test_8k_accept_new_clears_audit(tmp_path):
    existing = _write_existing(tmp_path, [{
        "period": "Q1_FY2026", "uni_account": "adj_eps", "value": 1.23,
        "audit_source": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "audit_note": "from 8K",
    }])
    new_data = {"income_statement": [
        {"period": "Q1_FY2026", "uni_account": "adj_eps", "value": 9.99}
    ]}
    out, *_ = e8k._preserve_audited_cells(new_data, existing, accept_new_values=True)
    row = out["income_statement"][0]
    assert row["value"] == 9.99
    assert "audit_source" not in row
    assert "audit_note" not in row
    assert row["accepted_new_value_replaces_audit"]["prior_audit_value"] == 1.23
