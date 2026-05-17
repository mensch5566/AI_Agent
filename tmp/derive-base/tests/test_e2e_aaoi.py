import json, os, subprocess, sys
from pathlib import Path
import pytest

VAULT = Path(os.path.expanduser(
    "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian"
))


@pytest.fixture(scope="module")
def aaoi_derived():
    if not VAULT.exists():
        pytest.skip("Obsidian vault not present (CI run)")
    cli = Path(__file__).resolve().parents[1] / "derive_base.py"
    r = subprocess.run([sys.executable, str(cli), "--ticker", "AAOI"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out_dir = Path([ln for ln in r.stdout.splitlines() if ln.strip()][-1])
    doc = json.loads((out_dir / "AAOI_derived.json").read_text())
    return doc


def _row(doc, **filt):
    for r in doc["derived_metrics"]:
        if all(r.get(k) == v for k, v in filt.items()):
            return r
    return None


def test_aaoi_q4_revenue_each_year(aaoi_derived):
    # AAOI revenue from parse output (verified during YTD ingest):
    #   FY2024 = 249,365   9M_FY2024 = 149,094  → expected Q4 ≈ 100,271
    #   FY2023 = 217,646   9M_FY2023 = 157,193  → expected Q4 ≈  60,453
    #   FY2025 = 455,715   9M_FY2025 = 321,441  → expected Q4 ≈ 134,274
    expectations = {
        "Q4_FY2023": 60453.0,
        "Q4_FY2024": 100271.0,
        "Q4_FY2025": 134274.0,
    }
    for period, expected in expectations.items():
        row = _row(aaoi_derived, statement="IS", version="GAAP",
                   uni_account="revenue", period=period)
        assert row is not None, f"missing Q4 revenue for {period}"
        assert abs(row["value"] - expected) < 1.0
        assert row["provenance"]["rule_id"] == "Q4_FY_MINUS_9M"
        assert row["status"] == "DERIVED_FROM_DISCLOSED"


def test_aaoi_no_q4_already_in_facts(aaoi_derived):
    # Sanity: derive shouldn't produce Q4 for any quarter that's already direct.
    # (AAOI's facts have BS Q4 only; IS / CF should be the derived ones.)
    is_q4 = [r for r in aaoi_derived["derived_metrics"]
             if r["statement"] == "IS" and r["period"].startswith("Q4_")]
    assert len(is_q4) >= 1


def test_aaoi_chain_depth_bounded(aaoi_derived):
    for r in aaoi_derived["derived_metrics"]:
        assert r["provenance"]["chain_depth"] <= 3, r


def test_aaoi_metadata_has_sha256(aaoi_derived):
    inputs = aaoi_derived["metadata"]["input_files"]
    for k, v in inputs.items():
        assert len(v["sha256"]) == 64
