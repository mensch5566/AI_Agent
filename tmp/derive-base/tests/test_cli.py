import json
import subprocess
import sys
from pathlib import Path


def test_cli_runs_on_minimal_stub(tmp_path):
    """Build a tiny vault with one inline gaap.json + empty facts/edges + no nongaap.

    Just verifies the CLI exits 0, writes derived.json + 2 md files, and
    doesn't crash. End-to-end logic correctness is checked by test_e2e_aaoi.
    """
    vault = tmp_path / "vault"
    skill_out = vault / "Khouse" / "Semiconductors" / "STUB" / "01_Source" / "SEC Filings" / "Skill_Output" / "parse-10QK-gaap"
    skill_out.mkdir(parents=True)
    (skill_out / "STUB_gaap.json").write_text(json.dumps({
        "metadata": {"ticker": "STUB", "filings": {}, "cik": "0", "company": "Stub",
                     "fiscal_year_end_month": 12, "currency": "USD"},
        "income_statement": [], "balance_sheet": [], "cash_flow_statement": [],
    }))
    (skill_out / "STUB_gaap_facts.json").write_text(json.dumps({"facts": [], "metadata": {}}))
    (skill_out / "STUB_gaap_edges_cal.json").write_text(json.dumps({"edges": [], "metadata": {}}))

    cli = Path(__file__).resolve().parents[1] / "derive_base.py"
    r = subprocess.run(
        [sys.executable, str(cli), "--ticker", "STUB", "--vault", str(vault)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr

    # The CLI prints the output dir as the last non-empty line
    out_lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
    out_dir = Path(out_lines[-1].strip())
    assert (out_dir / "STUB_derived.json").exists()
    assert (out_dir / "STUB_derive_audit.md").exists()
    assert (out_dir / "STUB_conflict_report.md").exists()
