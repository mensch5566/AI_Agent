import json, hashlib, pathlib, os
from pathlib import Path
from io_loader import sha256_file, discover_sources, load_facts, load_calc_edges, _backfill_filing_provenance


def test_backfill_filing_provenance_from_metadata():
    """Codex round-3 F4: load_facts must backfill accession_number/form/
    filing_date/primary_doc from gaap_facts.metadata.filings onto each
    FactRow.provenance, otherwise input_dict_from_fact has nothing to
    surface for restatement audit."""
    from _shared.sec_json_adapter import FactRow
    rows = [
        FactRow(cell_id="r1", ticker="X", period="FY2024", period_end="2024-12-31",
                period_kind="fy_annual_duration", statement="IS", version="GAAP",
                uni_account="revenue", source_account="us-gaap:Revenues",
                xbrl_tag="Revenues", value=100.0, weight=1, unit="USD_thousands",
                status="SOURCE_OF_TRUTH", ordinal=None, long_tail_metadata=None,
                provenance={}),
        FactRow(cell_id="r2", ticker="X", period="Q1_FY2025", period_end="2025-03-31",
                period_kind="quarter_duration", statement="IS", version="GAAP",
                uni_account="revenue", source_account="us-gaap:Revenues",
                xbrl_tag="Revenues", value=30.0, weight=1, unit="USD_thousands",
                status="SOURCE_OF_TRUTH", ordinal=None, long_tail_metadata=None,
                provenance={}),
    ]
    # metadata.filings is keyed by filing-event period (Q1/Q2/Q3 10-Q,
    # Q4 10-K). FY2024 fact maps to Q4_FY2024 filing; Q1_FY2025 maps to
    # itself. R3-F4 backfill must walk this mapping.
    metadata = {
        "filings": {
            "Q4_FY2024": {"form": "10-K", "filing_date": "2025-02-15", "accession_number": "0001-00", "primary_doc": "x-20241231_10k.htm"},
            "Q1_FY2025": {"form": "10-Q", "filing_date": "2025-05-01", "accession_number": "0001-01", "primary_doc": "x-20250331_10q.htm"},
        }
    }
    _backfill_filing_provenance(rows, metadata)
    # FY2024 row picks up the Q4_FY2024 10-K via _filing_period_for mapping.
    assert rows[0].provenance["accession_number"] == "0001-00"
    assert rows[0].provenance["form"] == "10-K"
    assert rows[0].provenance["source_filing"] == "x-20241231_10k.htm"
    assert rows[1].provenance["accession_number"] == "0001-01"
    assert rows[1].provenance["form"] == "10-Q"


def test_filing_period_for_ytd_mapping():
    from io_loader import _filing_period_for
    assert _filing_period_for("Q1_FY2025") == "Q1_FY2025"
    assert _filing_period_for("Q4_FY2025") == "Q4_FY2025"
    assert _filing_period_for("6M_FY2025") == "Q2_FY2025"  # 6M → Q2 10-Q
    assert _filing_period_for("9M_FY2025") == "Q3_FY2025"  # 9M → Q3 10-Q
    assert _filing_period_for("FY2025")    == "Q4_FY2025"  # FY → Q4 10-K
    assert _filing_period_for("weird")     is None


def test_sha256_file(tmp_path):
    p = tmp_path / "a.json"
    p.write_text("hello")
    expected = hashlib.sha256(b"hello").hexdigest()
    assert sha256_file(p) == expected


def test_discover_sources_finds_gaap_facts(tmp_path):
    vault = tmp_path / "Khouse" / "Semiconductors" / "AAOI" / "01_Source" / "SEC Filings" / "Skill_Output"
    (vault / "parse-10QK-gaap").mkdir(parents=True)
    (vault / "parse-8k-nongaap").mkdir(parents=True)
    (vault / "parse-10QK-gaap" / "AAOI_gaap_facts.json").write_text("{}")
    (vault / "parse-10QK-gaap" / "AAOI_gaap_edges_cal.json").write_text("{}")
    (vault / "parse-8k-nongaap" / "AAOI_nongaap.json").write_text("{}")

    out = discover_sources(tmp_path, "AAOI")
    assert out["gaap_facts"].name == "AAOI_gaap_facts.json"
    assert out["gaap_edges_cal"].name == "AAOI_gaap_edges_cal.json"
    assert out["nongaap"].name == "AAOI_nongaap.json"


def test_discover_sources_missing_nongaap_optional(tmp_path):
    vault = tmp_path / "Khouse" / "Semiconductors" / "INTC" / "01_Source" / "SEC Filings" / "Skill_Output"
    (vault / "parse-10QK-gaap").mkdir(parents=True)
    (vault / "parse-10QK-gaap" / "INTC_gaap_facts.json").write_text("{}")
    out = discover_sources(tmp_path, "INTC")
    assert out["nongaap"] is None


def test_load_facts_real_aaoi():
    VAULT = Path(os.environ.get(
        "OBSIDIAN_VAULT",
        os.path.expanduser("~/Obsidian")
    ))
    if not VAULT.exists():
        import pytest
        pytest.skip("Obsidian vault not present (CI run)")
    srcs = discover_sources(VAULT, "AAOI")
    assert srcs["gaap_facts"].exists()
    facts = load_facts(srcs)
    # Sanity: AAOI has many revenue facts across multiple periods + statements
    rev = [f for f in facts if f.uni_account == "revenue" and f.statement == "IS" and f.version == "GAAP"]
    assert len(rev) >= 10
    periods = {f.period for f in rev}
    # YTD rows must be present (Phase A pre-work in commit 444db47)
    assert "6M_FY2024" in periods or "6M_FY2025" in periods
    assert "9M_FY2024" in periods or "9M_FY2025" in periods
