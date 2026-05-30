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
        "ticker":                 "LITE",
        "target":                 "gaap",
        "period":                 "Q1_FY2026",
        "uni_account":            "income_before_taxes",
        "new_value":              -172.1,
        "source_account":         None,
        "row_type":               None,
        "unit":                   "USD_millions",
        "period_kind":            None,
        "axis":                   None,
        "axis_qname":             None,
        "member_qname":           None,
        "period_end":             None,
        "decimals":               None,
        "other_dimensions_json":  None,
        "audit_source":           "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "source_doc":             "lite-20250927.htm",
        "page_or_section":        None,
        "quote":                  None,
        "accession_number":       None,
        "period_scope":           None,
        "audit_note":             "10-Q income statement",
        "audited_by":             "test@example.com",
        "accept_new_values":      False,
        "dry_run":                False,
        "json_path":              str(json_path),
        "facts_key":              None,
        "classification_source":  None,
        "classification_note":    None,
        "long_tail_metadata_json": None,
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
    """Supplement: no matching dimensional identity → create new fact.
    P5-F2: must supply --period-end (adapter rejects rows without it)."""
    p = _write_supplement(tmp_path, [])
    _run(p,
         target="supplement",
         period="Q1_FY2026",
         uni_account="revenue",
         new_value=379.2,
         source_account="Components",
         period_kind="single_quarter",
         period_end="2025-09-27",     # P5-F2 required
         axis="business_segment",
         axis_qname="us-gaap:StatementBusinessSegmentsAxis",
         member_qname="us-gaap:ComponentsMember",
         source_doc="lite-Q1-FY26.htm")
    facts = json.loads(p.read_text())["facts"]
    assert len(facts) == 1
    fact = facts[0]
    assert fact["value"] == 379.2
    assert fact["axis_qname"] == "us-gaap:StatementBusinessSegmentsAxis"
    assert fact["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    # P5-F2: adapter-required fields
    assert fact["period_end"] == "2025-09-27"
    assert fact["type"] == "GAAP_SEGMENT"  # P5-F3 default
    assert fact["source_doc"] == "lite-Q1-FY26.htm"


# ─────────────────────────────────────────────────────────────────────────────
# P5-F1: supplement adapter carries v4 audit metadata
# ─────────────────────────────────────────────────────────────────────────────

def test_supplement_adapter_carries_audit_metadata():
    """P5-F1: a supplement fact with audit metadata must surface in adapter
    output's provenance, not get dropped."""
    from _shared.sec_json_adapter import adapt_supplement_facts
    supp_doc = {
        "metadata": {"ticker": "LITE"},
        "facts": [{
            "period":               "Q1_FY2026",
            "period_end":           "2025-09-27",
            "period_kind":          "single_quarter",
            "axis":                 "product",
            "axis_qname":           "srt:ProductOrServiceAxis",
            "source_account":       "Components",
            "source_account_qname": "us-gaap:ComponentsMember",
            "uni_account":          "revenue",
            "value":                379.2,
            "unit":                 "USD_millions",
            "type":                 "GAAP_SEGMENT",
            "source_doc":           "lite-q1.htm",
            "audit_source":         "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
            "audit_source_raw":     "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
            "audit_note":           "10-Q Note 15",
            "audit_evidence":       {"source_doc": "lite-q1.htm"},
        }],
    }
    rows, rejected, _, _ = adapt_supplement_facts(supp_doc)
    assert not rejected
    assert len(rows) == 1
    prov = rows[0].provenance
    assert prov["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    assert prov["audit_source_raw"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    assert prov["audit_note"] == "10-Q Note 15"
    assert prov["audit_evidence"] == {"source_doc": "lite-q1.htm"}


def test_supplement_adapter_legacy_audit_source_normalized():
    """P5-F1: legacy MANUAL_AUDIT_FROM_PDF on supplement also gets normalized."""
    from _shared.sec_json_adapter import adapt_supplement_facts
    supp_doc = {
        "metadata": {"ticker": "LITE"},
        "facts": [{
            "period":               "Q1_FY2026",
            "period_end":           "2025-09-27",
            "period_kind":          "single_quarter",
            "axis":                 "product",
            "axis_qname":           "srt:ProductOrServiceAxis",
            "source_account":       "Components",
            "source_account_qname": "us-gaap:ComponentsMember",
            "uni_account":          "revenue",
            "value":                379.2,
            "unit":                 "USD_millions",
            "type":                 "GAAP_SEGMENT",
            "source_doc":           "lite-q1.htm",
            "audit_source":         "MANUAL_AUDIT_FROM_PDF",  # legacy
            "audit_evidence":       {"source_doc": "lite-q1.htm"},
        }],
    }
    rows, _, _, _ = adapt_supplement_facts(supp_doc)
    prov = rows[0].provenance
    assert prov["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    assert prov["audit_source_raw"] == "MANUAL_AUDIT_FROM_PDF"


# ─────────────────────────────────────────────────────────────────────────────
# P5-F2: supplement new row requires --period-end (fail-closed)
# ─────────────────────────────────────────────────────────────────────────────

def test_supplement_new_row_without_period_end_rejected(tmp_path):
    """P5-F2: stamp_new_row for supplement without --period-end raises."""
    p = _write_supplement(tmp_path, [])
    with pytest.raises(ValueError, match="--period-end"):
        _run(p,
             target="supplement",
             period="Q1_FY2026",
             uni_account="revenue",
             new_value=379.2,
             source_account="Components",
             period_kind="single_quarter",
             axis="business_segment",
             axis_qname="us-gaap:StatementBusinessSegmentsAxis",
             member_qname="us-gaap:ComponentsMember")


def test_supplement_new_row_without_period_kind_rejected(tmp_path):
    """P5-F2: same fail-closed for missing --period-kind."""
    p = _write_supplement(tmp_path, [])
    with pytest.raises(ValueError, match="--period-kind"):
        _run(p,
             target="supplement",
             period="Q1_FY2026",
             uni_account="revenue",
             new_value=379.2,
             source_account="Components",
             period_end="2025-09-27",
             axis="business_segment",
             axis_qname="us-gaap:StatementBusinessSegmentsAxis",
             member_qname="us-gaap:ComponentsMember")


# ─────────────────────────────────────────────────────────────────────────────
# P5-F3: GAAP / 8K new row default type
# ─────────────────────────────────────────────────────────────────────────────

def test_gaap_new_row_defaults_to_type_GAAP(tmp_path):
    """P5-F3: GAAP new row carries type='GAAP' by default."""
    p = _write_gaap(tmp_path, [])
    _run(p)
    row = json.loads(p.read_text())["income_statement"][0]
    assert row["type"] == "GAAP"


def test_nongaap_new_row_defaults_to_type_NON_GAAP(tmp_path):
    """P5-F3: nongaap new row carries type='NON_GAAP'."""
    p = tmp_path / "LITE_nongaap.json"
    p.write_text(json.dumps({"metadata": {"ticker": "LITE"}, "income_statement": []}))
    _run(p, target="nongaap", uni_account="adj_eps", unit="USD_per_share",
         new_value=0.48)
    row = json.loads(p.read_text())["income_statement"][0]
    assert row["type"] == "NON_GAAP"


def test_row_type_override_wins(tmp_path):
    p = _write_gaap(tmp_path, [])
    _run(p, row_type="CUSTOM_TYPE")
    row = json.loads(p.read_text())["income_statement"][0]
    assert row["type"] == "CUSTOM_TYPE"


# ─────────────────────────────────────────────────────────────────────────────
# P5-F4: --other-dimensions-json for supplement multi-dim
# ─────────────────────────────────────────────────────────────────────────────

def test_supplement_locate_uses_other_dimensions(tmp_path):
    """P5-F4: existing multi-dim supplement row matches when caller supplies
    --other-dimensions-json."""
    p = _write_supplement(tmp_path, [{
        "period":               "Q1_FY2026",
        "period_kind":          "single_quarter",
        "axis":                 "product",
        "axis_qname":           "srt:ProductOrServiceAxis",
        "source_account":       "Components",
        "source_account_qname": "us-gaap:ComponentsMember",
        "uni_account":          "revenue",
        "value":                300.0,
        "unit":                 "USD_millions",
        "type":                 "GAAP_SEGMENT",
        "other_dimensions":     [{"axis": "srt:Geo", "member": "country:US"}],
    }])
    _run(p,
         target="supplement",
         period="Q1_FY2026",
         uni_account="revenue",
         new_value=350.0,
         source_account="Components",
         period_kind="single_quarter",
         axis="product",
         axis_qname="srt:ProductOrServiceAxis",
         member_qname="us-gaap:ComponentsMember",
         other_dimensions_json='[{"axis": "srt:Geo", "member": "country:US"}]',
         source_doc="x.htm")
    facts = json.loads(p.read_text())["facts"]
    assert len(facts) == 1   # didn't create a duplicate empty-dim row
    assert facts[0]["value"] == 350.0
    assert facts[0]["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"


def test_supplement_no_match_when_other_dimensions_differ(tmp_path):
    """P5-F4: caller's other_dimensions doesn't match → no match (creates
    new row). Critical that this NOT silently overwrite the existing row."""
    p = _write_supplement(tmp_path, [{
        "period":               "Q1_FY2026",
        "period_kind":          "single_quarter",
        "axis":                 "product",
        "axis_qname":           "srt:ProductOrServiceAxis",
        "source_account":       "Components",
        "source_account_qname": "us-gaap:ComponentsMember",
        "uni_account":          "revenue",
        "value":                300.0,
        "unit":                 "USD_millions",
        "type":                 "GAAP_SEGMENT",
        "other_dimensions":     [{"axis": "srt:Geo", "member": "country:US"}],
    }])
    _run(p,
         target="supplement",
         period="Q1_FY2026",
         uni_account="revenue",
         new_value=50.0,
         source_account="Components",
         period_kind="single_quarter",
         period_end="2025-09-27",
         axis="product",
         axis_qname="srt:ProductOrServiceAxis",
         member_qname="us-gaap:ComponentsMember",
         other_dimensions_json='[{"axis": "srt:Geo", "member": "country:JP"}]',
         source_doc="x.htm")
    facts = json.loads(p.read_text())["facts"]
    assert len(facts) == 2  # two distinct rows for US vs JP


# ─────────────────────────────────────────────────────────────────────────────
# P5-F5: GAAP/8K locate uses --unit
# ─────────────────────────────────────────────────────────────────────────────

def test_gaap_locate_requires_unit_match_when_unit_given(tmp_path):
    """P5-F5: caller passes --unit; row with different unit must NOT match
    (would otherwise overwrite the wrong row)."""
    p = _write_gaap(tmp_path, [{
        "period": "Q1_FY2026", "uni_account": "shares_basic",
        "value": 1_000_000.0, "unit": "shares", "type": "GAAP",
    }])
    # Caller mistakenly passes unit=millions_shares — must NOT match the row
    _run(p,
         uni_account="shares_basic",
         unit="millions_shares",
         new_value=1.0)
    rows = json.loads(p.read_text())["income_statement"]
    # Should have appended a NEW row, not overwritten the existing shares row
    assert len(rows) == 2
    by_unit = {r["unit"]: r for r in rows}
    assert by_unit["shares"]["value"] == 1_000_000.0   # unchanged
    assert by_unit["millions_shares"]["value"] == 1.0   # new audit row


# ─────────────────────────────────────────────────────────────────────────────
# P5-F6: log records canonical + raw audit_source pair
# ─────────────────────────────────────────────────────────────────────────────

def test_log_records_canonical_and_raw_for_legacy_input(tmp_path):
    """P5-F6: caller passes legacy MANUAL_AUDIT_FROM_PDF → log has both
    canonical and raw fields."""
    p = _write_gaap(tmp_path, [{
        "period": "Q1_FY2026", "uni_account": "income_before_taxes",
        "value": -150.0, "unit": "USD_millions", "type": "GAAP",
    }])
    _run(p, audit_source="MANUAL_AUDIT_FROM_PDF")
    log_entry = json.loads(
        (tmp_path / "manual_edit_audit_log.jsonl").read_text().strip()
    )
    assert log_entry["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"  # canonical
    assert log_entry["audit_source_raw"] == "MANUAL_AUDIT_FROM_PDF"          # raw preserved


def test_log_records_forensic_field_on_override(tmp_path):
    """P5-F6: override path log includes accepted_new_value_replaces_audit."""
    p = _write_gaap(tmp_path, [{
        "period": "Q1_FY2026", "uni_account": "income_before_taxes",
        "value": -150.0, "unit": "USD_millions", "type": "GAAP",
        "audit_source": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "audit_source_raw": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
    }])
    _run(p, new_value=-180.0, accept_new_values=True,
         source_doc="amended.htm")
    log_entry = json.loads(
        (tmp_path / "manual_edit_audit_log.jsonl").read_text().strip()
    )
    assert log_entry["operation"] == "override_existing_audit"
    assert log_entry["accepted_new_value_replaces_audit"]["prior_audit_value"] == -150.0
    assert log_entry["accepted_new_value_replaces_audit"]["new_extracted_value"] == -180.0


# ─────────────────────────────────────────────────────────────────────────────
# P5-F7: classification path (MANUAL_RECLASSIFIED)
# ─────────────────────────────────────────────────────────────────────────────

def test_classification_stamp_writes_classification_source(tmp_path):
    """P5-F7: --classification-source path writes classification channel,
    not audit channel."""
    p = _write_gaap(tmp_path, [{
        "period": "Q1_FY2026", "uni_account": "operating_expense_long_tail",
        "source_account": "Goodwill Impairment", "value": 100.0,
        "unit": "USD_millions", "type": "GAAP",
        "classification_source": "AGENT_CLASSIFIED",
        "long_tail_metadata": {"rolls_up_to": "operating_expenses"},
    }])
    _run(p,
         audit_source=None,
         classification_source="MANUAL_RECLASSIFIED",
         classification_note="re-bucketed after review",
         uni_account="operating_expense_long_tail",
         source_account="Goodwill Impairment",
         new_value=100.0,
         long_tail_metadata_json='{"rolls_up_to": "selling_general_administrative"}')
    row = json.loads(p.read_text())["income_statement"][0]
    # Classification channel updated
    assert row["classification_source"] == "MANUAL_RECLASSIFIED"
    assert row["classification_note"] == "re-bucketed after review"
    assert row["long_tail_metadata"]["rolls_up_to"] == "selling_general_administrative"
    # Audit channel untouched
    assert "audit_source" not in row
    # log uses classification_source
    log_entry = json.loads(
        (tmp_path / "manual_edit_audit_log.jsonl").read_text().strip()
    )
    assert log_entry["classification_source"] == "MANUAL_RECLASSIFIED"
    assert "audit_source" not in log_entry


def test_audit_and_classification_mutually_exclusive(tmp_path):
    """P5-F7: passing both --audit-source and --classification-source raises."""
    p = _write_gaap(tmp_path, [])
    with pytest.raises(ValueError, match="mutually exclusive"):
        _run(p,
             audit_source="MANUAL_AUDIT_FROM_OFFICIAL_FILING",
             classification_source="MANUAL_RECLASSIFIED")


def test_neither_audit_nor_classification_source_raises(tmp_path):
    p = _write_gaap(tmp_path, [])
    with pytest.raises(ValueError, match="must specify either"):
        _run(p, audit_source=None, classification_source=None)


def test_invalid_classification_source_rejected(tmp_path):
    p = _write_gaap(tmp_path, [])
    with pytest.raises(ValueError, match="invalid --classification-source"):
        _run(p, audit_source=None, classification_source="SOMETHING_ELSE")


# ─────────────────────────────────────────────────────────────────────────────
# P5-F9: classification mode cannot change value / cannot stamp new numeric row
# ─────────────────────────────────────────────────────────────────────────────

def test_classification_mode_cannot_change_value(tmp_path):
    """P5-F9: classification edit with --new-value != existing → SystemExit.
    Classification is metadata-only; value changes require --audit-source."""
    p = _write_gaap(tmp_path, [{
        "period": "Q1_FY2026", "uni_account": "operating_expense_long_tail",
        "source_account": "Goodwill Impairment", "value": 100.0,
        "unit": "USD_millions", "type": "GAAP",
    }])
    with pytest.raises(SystemExit) as exc:
        _run(p,
             audit_source=None,
             classification_source="MANUAL_RECLASSIFIED",
             classification_note="want to change value via classification",
             uni_account="operating_expense_long_tail",
             source_account="Goodwill Impairment",
             new_value=999.0)   # ≠ existing 100.0
    assert "cannot change row value" in str(exc.value)


def test_classification_mode_value_unchanged_on_existing_row(tmp_path):
    """P5-F9: classification edit with matching --new-value → value stays
    at existing (not mutated; new_value just acknowledges current)."""
    p = _write_gaap(tmp_path, [{
        "period": "Q1_FY2026", "uni_account": "operating_expense_long_tail",
        "source_account": "Goodwill Impairment", "value": 100.0,
        "unit": "USD_millions", "type": "GAAP",
    }])
    _run(p,
         audit_source=None,
         classification_source="MANUAL_RECLASSIFIED",
         classification_note="re-bucket only",
         uni_account="operating_expense_long_tail",
         source_account="Goodwill Impairment",
         new_value=100.0)
    row = json.loads(p.read_text())["income_statement"][0]
    assert row["value"] == 100.0   # unchanged
    assert row["classification_source"] == "MANUAL_RECLASSIFIED"
    # Audit channel untouched
    assert "audit_source" not in row


def test_classification_mode_no_match_fails_closed(tmp_path):
    """P5-F9: classification edit + no matching row → SystemExit, do NOT
    create a new numeric row without audit provenance."""
    p = _write_gaap(tmp_path, [])
    with pytest.raises(SystemExit) as exc:
        _run(p,
             audit_source=None,
             classification_source="MANUAL_RECLASSIFIED",
             classification_note="trying to create a new long-tail row",
             uni_account="operating_expense_long_tail",
             source_account="Goodwill Impairment",
             new_value=10.0)
    assert "no matching row" in str(exc.value).lower()
    # File untouched
    assert json.loads(p.read_text())["income_statement"] == []


# ─────────────────────────────────────────────────────────────────────────────
# P5-F8: supplement dedupe preserves v4 metadata
# ─────────────────────────────────────────────────────────────────────────────

def _supp_row(value, **extras):
    """Build a supplement input fact dict (pre-adapter)."""
    base = {
        "period":               "Q1_FY2026",
        "period_end":           "2025-09-27",
        "period_kind":          "single_quarter",
        "axis":                 "product",
        "axis_qname":           "srt:ProductOrServiceAxis",
        "source_account":       "Components",
        "source_account_qname": "us-gaap:ComponentsMember",
        "uni_account":          "revenue",
        "value":                value,
        "unit":                 "USD_millions",
        "type":                 "GAAP_SEGMENT",
        "source_doc":           "test.htm",
    }
    base.update(extras)
    return base


def test_supplement_dedupe_preserves_audit_metadata_from_non_chosen():
    """P5-F8: same-value duplicates — one with audit metadata, one without.
    Dedupe must NOT drop the audit channel just because the audited row is
    not 'members[0]'."""
    from _shared.sec_json_adapter import adapt_supplement_facts
    supp_doc = {
        "metadata": {"ticker": "LITE"},
        "facts": [
            # First (plain — no audit)
            _supp_row(379.2),
            # Second (audited)
            _supp_row(379.2,
                      audit_source="MANUAL_AUDIT_FROM_OFFICIAL_FILING",
                      audit_source_raw="MANUAL_AUDIT_FROM_OFFICIAL_FILING",
                      audit_note="from 10-Q",
                      audit_evidence={"source_doc": "manual.htm"}),
        ],
    }
    rows, rejected, _, _ = adapt_supplement_facts(supp_doc)
    assert not rejected
    assert len(rows) == 1   # collapsed
    prov = rows[0].provenance
    # P5-F8: audit channel must survive
    assert prov["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    assert prov["audit_note"] == "from 10-Q"
    assert prov["audit_evidence"] == {"source_doc": "manual.htm"}
    # sources[] still merged from both
    assert len(prov["sources"]) == 2


def test_supplement_dedupe_preserves_classification_from_non_chosen():
    """P5-F8: classification metadata also survives dedupe."""
    from _shared.sec_json_adapter import adapt_supplement_facts
    supp_doc = {
        "metadata": {"ticker": "LITE"},
        "facts": [
            _supp_row(50.0),
            _supp_row(50.0,
                      classification_source="AGENT_CLASSIFIED",
                      long_tail_metadata={"rolls_up_to": "revenue"}),
        ],
    }
    rows, _, _, _ = adapt_supplement_facts(supp_doc)
    assert len(rows) == 1
    prov = rows[0].provenance
    assert prov["classification_source"] == "AGENT_CLASSIFIED"
    assert prov["long_tail_metadata"] == {"rolls_up_to": "revenue"}


def test_supplement_dedupe_conflicting_v4_metadata_fails_closed():
    """P5-F8: if two duplicates carry CONFLICTING v4 audit metadata, dedupe
    rejects the group instead of silently picking one."""
    from _shared.sec_json_adapter import adapt_supplement_facts
    supp_doc = {
        "metadata": {"ticker": "LITE"},
        "facts": [
            _supp_row(100.0,
                      audit_source="MANUAL_AUDIT_FROM_OFFICIAL_FILING",
                      audit_note="from filing A"),
            _supp_row(100.0,
                      audit_source="MANUAL_AUDIT_FROM_OFFICIAL_FILING",
                      audit_note="from filing B"),   # conflicting note
        ],
    }
    rows, rejected, _, _ = adapt_supplement_facts(supp_doc)
    assert len(rows) == 0
    assert len(rejected) == 1
    assert "conflicting v4 metadata" in rejected[0]["reason"]


def test_supplement_dedupe_no_audit_no_change_in_behavior():
    """P5-F8 regression: same-value duplicates with no v4 metadata still
    collapse correctly (no spurious v4 fields appear)."""
    from _shared.sec_json_adapter import adapt_supplement_facts
    supp_doc = {
        "metadata": {"ticker": "LITE"},
        "facts": [
            _supp_row(100.0),
            _supp_row(100.0),
        ],
    }
    rows, rejected, _, _ = adapt_supplement_facts(supp_doc)
    assert not rejected
    assert len(rows) == 1
    prov = rows[0].provenance
    assert "audit_source" not in prov
    assert "classification_source" not in prov
    assert len(prov["sources"]) == 2


# ─────────────────────────────────────────────────────────────────────────────
# P5-F10: precision-dedupe must not merge v4 metadata across different values
# ─────────────────────────────────────────────────────────────────────────────

def test_precision_dedupe_chosen_classification_dropped_audit_rejected():
    """P5-F10 core: chosen has classification, dropped less-precise row has
    audit metadata. Audit is value-evidence — must NOT be transplanted onto
    a row with a different numeric value."""
    from _shared.sec_json_adapter import adapt_supplement_facts
    supp_doc = {
        "metadata": {"ticker": "LITE"},
        "facts": [
            # Chosen: more precise (decimals=0), value=100.12, classification only
            _supp_row(100.12, decimals=0,
                      classification_source="AGENT_CLASSIFIED"),
            # Dropped: less precise (decimals=-1), different value=100.0, audited
            _supp_row(100.0, decimals=-1,
                      audit_source="MANUAL_AUDIT_FROM_OFFICIAL_FILING",
                      audit_note="audited less precise value",
                      audit_evidence={"source_doc": "manual.htm"}),
        ],
    }
    rows, rejected, _, _ = adapt_supplement_facts(supp_doc)
    # Entire group rejected — won't silently transplant audit metadata
    assert len(rows) == 0
    assert len(rejected) == 1
    assert "less-precise duplicate" in rejected[0]["reason"]


def test_precision_dedupe_dropped_audit_only_rejected():
    """P5-F10: even if chosen has no v4 metadata at all, a dropped audited
    row should not be silently lost — reject so reviewer decides."""
    from _shared.sec_json_adapter import adapt_supplement_facts
    supp_doc = {
        "metadata": {"ticker": "LITE"},
        "facts": [
            _supp_row(100.12, decimals=0),   # no v4
            _supp_row(100.0, decimals=-1,
                      audit_source="MANUAL_AUDIT_FROM_OFFICIAL_FILING",
                      audit_evidence={"source_doc": "manual.htm"}),
        ],
    }
    rows, rejected, _, _ = adapt_supplement_facts(supp_doc)
    assert len(rows) == 0
    assert len(rejected) == 1


def test_precision_dedupe_dropped_classification_only_rejected():
    """P5-F10: also reject if only classification (not audit) is on the
    dropped row — keeps the channel-boundary rule simple/uniform."""
    from _shared.sec_json_adapter import adapt_supplement_facts
    supp_doc = {
        "metadata": {"ticker": "LITE"},
        "facts": [
            _supp_row(100.12, decimals=0),
            _supp_row(100.0, decimals=-1,
                      classification_source="AGENT_CLASSIFIED"),
        ],
    }
    rows, rejected, _, _ = adapt_supplement_facts(supp_doc)
    assert len(rows) == 0
    assert len(rejected) == 1


def test_precision_dedupe_no_v4_metadata_still_works():
    """P5-F10 regression: precision-dedupe with no v4 metadata on either
    side still collapses to most-precise row (no spurious rejection)."""
    from _shared.sec_json_adapter import adapt_supplement_facts
    supp_doc = {
        "metadata": {"ticker": "LITE"},
        "facts": [
            _supp_row(100.12, decimals=0),
            _supp_row(100.0, decimals=-1),
        ],
    }
    rows, rejected, _, _ = adapt_supplement_facts(supp_doc)
    assert not rejected
    assert len(rows) == 1
    assert rows[0].value == 100.12   # most precise wins
    assert rows[0].provenance["precision_dedupe"]["kept_decimals"] == 0


def test_precision_dedupe_chosen_audit_no_dropped_v4_still_works():
    """P5-F10: chosen has audit, dropped has NO v4. Chosen's own audit
    metadata stays; dropped rounds collapse normally."""
    from _shared.sec_json_adapter import adapt_supplement_facts
    supp_doc = {
        "metadata": {"ticker": "LITE"},
        "facts": [
            _supp_row(100.12, decimals=0,
                      audit_source="MANUAL_AUDIT_FROM_OFFICIAL_FILING",
                      audit_evidence={"source_doc": "x.htm"}),
            _supp_row(100.0, decimals=-1),   # rounded duplicate, no v4
        ],
    }
    rows, rejected, _, _ = adapt_supplement_facts(supp_doc)
    assert not rejected
    assert len(rows) == 1
    assert rows[0].value == 100.12
    # Chosen's own audit metadata stays (was never about merging)
    assert rows[0].provenance["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"


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
