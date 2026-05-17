import json, hashlib, pathlib, os
from pathlib import Path
from io_loader import sha256_file, discover_sources, load_facts, load_calc_edges


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
    VAULT = Path(os.path.expanduser(
        "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian"
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
