"""Phase 3 regression tests — schema v4 §7 + §8.

Covers:
  - adapter GAAP/Non-GAAP canonical+raw audit_source dual-write
  - upsert provenance JSONB shape via asdict(FactRow)
  - derive-base input_dict_from_fact carries audit lineage
  - derive-base to_derived_metric_row has_audited_inputs + audited_input_cell_ids
  - rules_q4._concepts_match uses is_manual_audit_source predicate
    (not legacy truthy check; AGENT_CLASSIFIED does NOT trigger relaxation)

Run: uv run --with pytest python3 -m pytest scripts/tests/test_phase3_adapter_derive.py -v
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "Tools" / "research-tools"))
sys.path.insert(
    0,
    "/Users/mensch5566/CC_Switch_Config/skills/derive-base/scripts",
)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3.1: adapter GAAP canonical+raw dual-write
# ─────────────────────────────────────────────────────────────────────────────

def _make_gaap_json(audit_source=None, audit_source_raw=None, **extra_audit):
    """Minimal gaap.json input."""
    row = {
        "period": "Q1_FY2026",
        "period_end": "2025-09-27",
        "statement": "IS",
        "uni_account": "revenue",
        "source_account": "Revenues",
        "value": 100.0,
        "unit": "USD_millions",
        "weight": 1,
    }
    if audit_source is not None:
        row["audit_source"] = audit_source
    if audit_source_raw is not None:
        row["audit_source_raw"] = audit_source_raw
    row.update(extra_audit)
    return {
        "metadata": {
            "ticker": "TEST",
            "filings": {
                "Q1_FY2026": {"form": "10-Q", "accession_number": "0001234567-25-000001"},
            },
        },
        "facts": [row],
    }


def test_adapter_carries_canonical_audit_source():
    from _shared.sec_json_adapter import adapt_gaap_facts
    j = _make_gaap_json(audit_source="MANUAL_AUDIT_FROM_OFFICIAL_FILING")
    rows, rejected = adapt_gaap_facts(j, pe_map={})
    assert not rejected
    prov = rows[0].provenance
    assert prov["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    assert prov["audit_source_raw"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"


def test_adapter_normalizes_legacy_audit_source_keeps_raw():
    """Legacy MANUAL_AUDIT_FROM_PDF must be normalized to canonical, but
    audit_source_raw preserves the legacy enum for forensic."""
    from _shared.sec_json_adapter import adapt_gaap_facts
    j = _make_gaap_json(audit_source="MANUAL_AUDIT_FROM_PDF")
    rows, _ = adapt_gaap_facts(j, pe_map={})
    prov = rows[0].provenance
    assert prov["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"  # canonical
    assert prov["audit_source_raw"] == "MANUAL_AUDIT_FROM_PDF"          # raw preserved


def test_adapter_carries_audit_note_and_evidence():
    from _shared.sec_json_adapter import adapt_gaap_facts
    j = _make_gaap_json(
        audit_source="MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        audit_note="10-Q Note 15",
        audited_at="2026-05-21T11:00:00Z",
        audited_by="user@example.com",
        audit_evidence={"source_doc": "lite-Q1.htm"},
    )
    rows, _ = adapt_gaap_facts(j, pe_map={})
    prov = rows[0].provenance
    assert prov["audit_note"] == "10-Q Note 15"
    assert prov["audited_at"] == "2026-05-21T11:00:00Z"
    assert prov["audited_by"] == "user@example.com"
    assert prov["audit_evidence"] == {"source_doc": "lite-Q1.htm"}


def test_adapter_carries_classification_source_independently():
    from _shared.sec_json_adapter import adapt_gaap_facts
    j = _make_gaap_json(
        classification_source="AGENT_CLASSIFIED",
        long_tail_metadata={"rolls_up_to": "operating_expenses"},
    )
    rows, _ = adapt_gaap_facts(j, pe_map={})
    prov = rows[0].provenance
    assert prov["classification_source"] == "AGENT_CLASSIFIED"
    assert prov["long_tail_metadata"] == {"rolls_up_to": "operating_expenses"}
    # No audit_source set → predicate should return False (it's classification only)
    assert "audit_source" not in prov


def test_adapter_no_audit_source_no_field_polluted():
    """Plain XBRL row without audit metadata should have no audit_source key."""
    from _shared.sec_json_adapter import adapt_gaap_facts
    j = _make_gaap_json()
    rows, _ = adapt_gaap_facts(j, pe_map={})
    prov = rows[0].provenance
    assert "audit_source" not in prov
    assert "audit_source_raw" not in prov


# ─────────────────────────────────────────────────────────────────────────────
# P3-F1: allowlist guard + legacy AGENT_CLASSIFIED promotion
# ─────────────────────────────────────────────────────────────────────────────

def test_adapter_promotes_legacy_agent_classified_to_classification_source():
    """P3-F1: legacy row with audit_source=AGENT_CLASSIFIED (pre-v4 parser
    wrote classification into audit_source field) must be promoted to
    classification_source, NOT pass-through to provenance.audit_source."""
    from _shared.sec_json_adapter import adapt_gaap_facts
    j = _make_gaap_json(audit_source="AGENT_CLASSIFIED")
    rows, _ = adapt_gaap_facts(j, pe_map={})
    prov = rows[0].provenance
    # MUST NOT pollute audit channel
    assert "audit_source" not in prov
    assert "audit_source_raw" not in prov
    # Promoted to classification channel
    assert prov["classification_source"] == "AGENT_CLASSIFIED"


def test_adapter_drops_unknown_audit_source_value():
    """P3-F1: unknown audit_source string (not in MANUAL_AUDIT_SOURCES, not
    a classification source either) must not be written to audit channel."""
    from _shared.sec_json_adapter import adapt_gaap_facts
    j = _make_gaap_json(audit_source="SOME_UNKNOWN_STRING")
    rows, _ = adapt_gaap_facts(j, pe_map={})
    prov = rows[0].provenance
    assert "audit_source" not in prov
    assert "audit_source_raw" not in prov
    # And not promoted (it's not a classification enum either)
    assert "classification_source" not in prov


def test_adapter_does_not_overwrite_existing_classification_source():
    """P3-F1 legacy promotion must NOT clobber an explicit classification_source."""
    from _shared.sec_json_adapter import adapt_gaap_facts
    j = _make_gaap_json(
        audit_source="AGENT_CLASSIFIED",            # legacy
        classification_source="MANUAL_RECLASSIFIED",  # explicit override
    )
    rows, _ = adapt_gaap_facts(j, pe_map={})
    prov = rows[0].provenance
    assert prov["classification_source"] == "MANUAL_RECLASSIFIED"  # not overwritten


def test_adapter_legacy_pdf_still_writes_to_audit_channel():
    """Sanity: MANUAL_AUDIT_FROM_PDF (legacy AUDIT enum) still goes to
    audit channel — only non-audit strings are blocked from audit_source."""
    from _shared.sec_json_adapter import adapt_gaap_facts
    j = _make_gaap_json(audit_source="MANUAL_AUDIT_FROM_PDF")
    rows, _ = adapt_gaap_facts(j, pe_map={})
    prov = rows[0].provenance
    assert prov["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    assert prov["audit_source_raw"] == "MANUAL_AUDIT_FROM_PDF"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3.2: adapter Non-GAAP
# ─────────────────────────────────────────────────────────────────────────────

def _make_nongaap_json(**audit_kw):
    row = {
        "period": "Q1_FY2026",
        "period_end": "2025-09-27",
        "uni_account": "adj_eps",
        "value": 0.48,
        "unit": "USD_per_share",
        "weight": 1,
    }
    row.update(audit_kw)
    return {
        "metadata": {
            "ticker": "TEST",
            "filings_8k": {
                "Q1_FY2026": {"accession_number": "0001234567-25-000099"},
            },
        },
        "income_statement": [row],
    }


def test_adapter_nongaap_no_legacy_audit_source_default():
    """Non-GAAP adapter should NOT pollute audit_source with
    'NotebookLM_PDF_read' anymore — that's now data_source."""
    from _shared.sec_json_adapter import adapt_nongaap_facts
    j = _make_nongaap_json()
    rows, rejected = adapt_nongaap_facts(j, pe_map={})
    assert not rejected
    prov = rows[0].provenance
    assert prov.get("audit_source") is None
    assert prov["data_source"] == "NotebookLM_PDF_read"


def test_adapter_nongaap_carries_audit_metadata_when_present():
    from _shared.sec_json_adapter import adapt_nongaap_facts
    j = _make_nongaap_json(
        audit_source="MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        audit_note="8-K table",
        audit_evidence={"source_doc": "8k.htm"},
    )
    rows, _ = adapt_nongaap_facts(j, pe_map={})
    prov = rows[0].provenance
    assert prov["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    assert prov["audit_source_raw"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    assert prov["audit_note"] == "8-K table"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3.3: upsert provenance shape (via asdict roundtrip)
# ─────────────────────────────────────────────────────────────────────────────

def test_upsert_provenance_jsonb_shape_via_asdict():
    """asdict(FactRow) must produce a dict whose provenance carries all v4
    fields verbatim — this is what gets written to Supabase JSONB."""
    from _shared.sec_json_adapter import adapt_gaap_facts
    j = _make_gaap_json(
        audit_source="MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        audit_note="x",
        audit_evidence={"source_doc": "y.htm"},
    )
    rows, _ = adapt_gaap_facts(j, pe_map={})
    d = asdict(rows[0])
    assert d["provenance"]["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    assert d["provenance"]["audit_source_raw"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    assert d["provenance"]["audit_note"] == "x"
    assert d["provenance"]["audit_evidence"] == {"source_doc": "y.htm"}
    assert d["provenance"]["source_filing"] == "10-Q"
    assert d["provenance"]["accession_number"] == "0001234567-25-000001"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3.4: input_dict_from_fact carries audit lineage
# ─────────────────────────────────────────────────────────────────────────────

def test_input_dict_from_fact_carries_audit_source():
    from _shared.sec_json_adapter import adapt_gaap_facts
    import derive_types  # noqa: E402
    j = _make_gaap_json(
        audit_source="MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        audit_evidence={"source_doc": "x.htm"},
    )
    rows, _ = adapt_gaap_facts(j, pe_map={})
    d = derive_types.input_dict_from_fact(rows[0])
    assert d["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    assert d["audit_source_raw"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    assert d["audit_evidence"] == {"source_doc": "x.htm"}


def test_input_dict_from_fact_no_audit_lineage_when_absent():
    from _shared.sec_json_adapter import adapt_gaap_facts
    import derive_types
    j = _make_gaap_json()
    rows, _ = adapt_gaap_facts(j, pe_map={})
    d = derive_types.input_dict_from_fact(rows[0])
    assert "audit_source" not in d
    assert "audit_evidence" not in d


def test_input_dict_does_not_carry_classification_source():
    """Schema §8.1: classification_source is row metadata, not value provenance —
    derive-base input_dict should NOT carry it."""
    from _shared.sec_json_adapter import adapt_gaap_facts
    import derive_types
    j = _make_gaap_json(classification_source="AGENT_CLASSIFIED")
    rows, _ = adapt_gaap_facts(j, pe_map={})
    d = derive_types.input_dict_from_fact(rows[0])
    assert "classification_source" not in d


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3.5: has_audited_inputs in derived row
# ─────────────────────────────────────────────────────────────────────────────

def _make_candidate(inputs):
    import derive_types
    return derive_types.Candidate(
        ticker="TEST", period="Q4_FY2025", period_kind="derived_q4",
        period_start="2025-10-01", period_end="2025-12-31",
        statement="IS", version="GAAP", uni_account="revenue",
        value=100.0, unit="USD_millions",
        rule_id="Q4_FY_MINUS_9M", rule_priority=1, chain_depth=1,
        chained=False, inputs=inputs,
    )


def test_to_derived_metric_row_flags_has_audited_inputs():
    import audit  # noqa: E402
    cand = _make_candidate([
        {"cell_id": "c1", "audit_source": "MANUAL_AUDIT_FROM_OFFICIAL_FILING"},
        {"cell_id": "c2"},  # no audit
    ])
    row = audit.to_derived_metric_row(cand)
    assert row.provenance["has_audited_inputs"] is True
    assert row.provenance["audited_input_cell_ids"] == ["c1"]


def test_to_derived_metric_row_no_audited_inputs():
    import audit
    cand = _make_candidate([
        {"cell_id": "c1"},
        {"cell_id": "c2"},
    ])
    row = audit.to_derived_metric_row(cand)
    assert row.provenance["has_audited_inputs"] is False
    assert row.provenance["audited_input_cell_ids"] == []


def test_to_derived_metric_row_legacy_audit_source_raw_detected():
    """Legacy DB row with only audit_source_raw should still trigger
    has_audited_inputs."""
    import audit
    cand = _make_candidate([
        {"cell_id": "c1", "audit_source_raw": "MANUAL_AUDIT_FROM_PDF"},
    ])
    row = audit.to_derived_metric_row(cand)
    assert row.provenance["has_audited_inputs"] is True
    assert row.provenance["audited_input_cell_ids"] == ["c1"]


def test_to_derived_metric_row_classification_does_not_count_as_audit():
    """AGENT_CLASSIFIED is classification, not audit. Must not flag
    has_audited_inputs."""
    import audit
    cand = _make_candidate([
        {"cell_id": "c1", "classification_source": "AGENT_CLASSIFIED"},
    ])
    row = audit.to_derived_metric_row(cand)
    assert row.provenance["has_audited_inputs"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3.6: rules_q4._concepts_match uses predicate
# ─────────────────────────────────────────────────────────────────────────────

def test_concepts_match_relaxes_for_manual_audit():
    """Audited rows with different PDF labels for same uni_account should
    be treated as concept-compatible (PDF wording variation, not concept
    change)."""
    import rules_q4

    class F:
        def __init__(self, source_account, audit_source=None, audit_source_raw=None):
            self.source_account = source_account
            self.xbrl_tag = source_account
            self.audit_source = audit_source
            self.provenance = {"audit_source": audit_source,
                                "audit_source_raw": audit_source_raw}

    fy = F("Income before income taxes", audit_source="MANUAL_AUDIT_FROM_OFFICIAL_FILING")
    q1 = F("Loss before income taxes",   audit_source="MANUAL_AUDIT_FROM_OFFICIAL_FILING")
    q2 = F("Income before income taxes", audit_source="MANUAL_AUDIT_FROM_OFFICIAL_FILING")
    q3 = F("Loss before income taxes",   audit_source="MANUAL_AUDIT_FROM_OFFICIAL_FILING")
    assert rules_q4._concepts_match(fy, q1, q2, q3) is True


def test_concepts_match_does_not_relax_for_classification_only():
    """Phase 3.6 / schema §8.3: AGENT_CLASSIFIED in audit_source field
    (legacy) must NOT trigger relaxation — it's classification, not audit."""
    import rules_q4

    class F:
        def __init__(self, source_account, audit_source=None):
            self.source_account = source_account
            self.xbrl_tag = source_account
            self.audit_source = audit_source
            self.provenance = {"audit_source": audit_source}

    fy = F("FooConcept", audit_source="AGENT_CLASSIFIED")  # legacy classification
    q1 = F("BarConcept", audit_source="AGENT_CLASSIFIED")
    # Different concepts; classification source must NOT relax to True
    assert rules_q4._concepts_match(fy, q1) is False


def test_concepts_match_normal_path_still_works():
    """Without audit, function uses local-name concept identity comparison."""
    import rules_q4

    class F:
        def __init__(self, source_account):
            self.source_account = source_account
            self.xbrl_tag = source_account
            self.audit_source = None
            self.provenance = {}

    same1 = F("us-gaap:Revenues")
    same2 = F("us-gaap:Revenues")
    assert rules_q4._concepts_match(same1, same2) is True

    diff1 = F("us-gaap:Revenues")
    diff2 = F("us-gaap:SalesRevenueNet")
    assert rules_q4._concepts_match(diff1, diff2) is False
