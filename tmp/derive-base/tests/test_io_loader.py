import json, hashlib, pathlib
from io_loader import sha256_file, discover_sources


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
