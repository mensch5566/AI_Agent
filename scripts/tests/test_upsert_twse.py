"""TDD tests for scripts/upsert_twse_financials.py — Phase E1 (TW storage).

Hermetic: uses small synthetic fixtures (a few facts + a couple derive rows),
never the live 3081 files, so the suite is deterministic and offline. Mirrors
the SEC upsert test patterns (test_upsert_derived.py) but for the TW pipeline:
Chinese-company-folder glob discovery, adapt_company_twse (TWD/TWSE), facts +
metrics assembly, freshness gate, facts-wins collision drop, dry-run diff.
"""
import json
import sys
import importlib.util
from pathlib import Path

import pytest


def _import_upsert():
    p = Path(__file__).resolve().parents[1] / "upsert_twse_financials.py"
    spec = importlib.util.spec_from_file_location("upsert_twse_mod", str(p))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["upsert_twse_mod"] = mod
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------- #
# Synthetic fixtures
# --------------------------------------------------------------------------- #

MOPS = "01_Source/MOPS Filings/Skill_Output"


def _twse_facts_json(ticker="9999"):
    """A minimal but structurally-valid twse facts JSON (keyed-dict shape the
    real parse-twse-ixbrl emits)."""
    return {
        "ticker": ticker,
        "report_category": "ir",
        "unit": "TWD_thousands",
        "periods": ["Q1_FY2024"],
        "facts_by_period": {
            "Q1_FY2024": {
                "period_end": "2024-03-31",
                "report_category": "ir",
                "facts": {
                    "revenue": {"statement": "income_statement", "value": 1000.0,
                                "xbrl_concept": "ifrs-full:Revenue"},
                    "gross_profit": {"statement": "income_statement", "value": 400.0,
                                     "xbrl_concept": "ifrs-full:GrossProfit"},
                    "total_assets": {"statement": "balance_sheet_assets", "value": 5000.0,
                                     "xbrl_concept": "ifrs-full:Assets"},
                    "eps_basic": {"statement": "income_statement", "value": 1.23,
                                  "xbrl_concept": "ifrs-full:BasicEarningsLossPerShare"},
                },
            },
        },
        "last_updated": "2026-07-02",
    }


def _write_twse_company_tree(vault_root, company_name, ticker):
    """Create the Chinese-company folder + parse-twse-ixbrl facts. Returns the
    Skill_Output base path."""
    base = Path(vault_root) / "Khouse" / "Semiconductors" / company_name / MOPS
    (base / "parse-twse-ixbrl").mkdir(parents=True)
    (base / "parse-twse-ixbrl" / f"{ticker}_twse_facts.json").write_text(
        json.dumps(_twse_facts_json(ticker)), encoding="utf-8")
    return base


def _write_derive_base(base, ticker, twse_facts_path, run="2026-07-02-2356",
                       rows=None, extra_input_files=None):
    import hashlib
    run_dir = base / "derive-base" / run
    run_dir.mkdir(parents=True)
    input_files = {"twse_facts": {
        "path": str(twse_facts_path),
        "sha256": hashlib.sha256(twse_facts_path.read_bytes()).hexdigest()}}
    if extra_input_files:
        input_files.update(extra_input_files)
    payload = {
        "metadata": {"ticker": ticker, "managed_rule_ids": ["Q4_FY_MINUS_9M"],
                     "input_files": input_files},
        "derived_metrics": rows if rows is not None else [
            {"cell_id": "db1", "ticker": ticker, "period": "FY2023",
             "period_kind": "fy_annual_duration", "period_start": None,
             "period_end": "2023-12-31", "statement": "CF", "version": "GAAP",
             "uni_account": "depreciation_and_amortization", "value": 300.0,
             "unit": "TWD_thousands", "status": "DERIVED_FROM_DISCLOSED",
             "provenance": {"rule_id": "IDENTITY_DA_DEP_PLUS_AMORT"}},
        ],
    }
    (run_dir / f"{ticker}_derived.json").write_text(json.dumps(payload))
    return run_dir / f"{ticker}_derived.json"


def _write_derive_analytics(base, ticker, twse_facts_path, derive_base_path,
                            run="2026-07-02-2356", rows=None):
    import hashlib
    run_dir = base / "derive-analytics" / run
    run_dir.mkdir(parents=True)
    input_files = {
        "twse_facts": {"path": str(twse_facts_path),
                       "sha256": hashlib.sha256(twse_facts_path.read_bytes()).hexdigest()},
        "derive_base": {"path": str(derive_base_path),
                        "sha256": hashlib.sha256(derive_base_path.read_bytes()).hexdigest()},
    }
    payload = {
        "metadata": {"ticker": ticker, "managed_rule_ids": ["RATIO_GROSS_MARGIN_PCT"],
                     "input_files": input_files},
        "analytics_metrics": rows if rows is not None else [
            {"cell_id": "an1", "ticker": ticker, "period": "Q1_FY2024",
             "period_kind": "quarter_duration", "period_start": None,
             "period_end": "2024-03-31", "statement": "RATIO", "version": "GAAP",
             "uni_account": "gross_margin_pct", "value": 0.4, "unit": "Pure",
             "status": "DERIVED_FROM_DISCLOSED",
             "provenance": {"rule_id": "RATIO_GROSS_MARGIN_PCT"}},
        ],
    }
    (run_dir / f"{ticker}_analytics.json").write_text(json.dumps(payload))
    return run_dir / f"{ticker}_analytics.json"


# --------------------------------------------------------------------------- #
# 1. Folder-glob discovery (0 / 1 / >1 hits)
# --------------------------------------------------------------------------- #

def test_discover_tw_base_single_hit(tmp_path):
    upsert = _import_upsert()
    _write_twse_company_tree(tmp_path, "聯亞", "3081")
    base = upsert.discover_tw_base(tmp_path, "3081")
    assert base is not None
    assert (base / "parse-twse-ixbrl" / "3081_twse_facts.json").exists()
    # folder is the Chinese company NAME, not the ticker
    assert "聯亞" in str(base)


def test_discover_tw_base_zero_hits_fail_loud(tmp_path):
    upsert = _import_upsert()
    # No company tree at all → fail loud
    with pytest.raises(SystemExit):
        upsert.discover_tw_base(tmp_path, "3081")


def test_discover_tw_base_multiple_hits_fail_loud(tmp_path):
    upsert = _import_upsert()
    # Two different Chinese folders both containing 3081's facts → ambiguous → fail
    _write_twse_company_tree(tmp_path, "聯亞", "3081")
    _write_twse_company_tree(tmp_path, "聯亞_dup", "3081")
    with pytest.raises(SystemExit):
        upsert.discover_tw_base(tmp_path, "3081")


# --------------------------------------------------------------------------- #
# 2. Company adaptation (currency=TWD, exchange=TWSE)
# --------------------------------------------------------------------------- #

def test_company_adaptation_is_twd_twse(tmp_path):
    upsert = _import_upsert()
    base = _write_twse_company_tree(tmp_path, "聯亞", "3081")
    batch = upsert.normalize("3081", base)
    assert batch.company.exchange == "TWSE"
    assert batch.company.currency == "TWD"
    assert batch.company.cik == ""
    assert batch.company.ticker == "3081"


# --------------------------------------------------------------------------- #
# 3. Facts + metrics row assembly
# --------------------------------------------------------------------------- #

def test_facts_assembly_shapes(tmp_path):
    upsert = _import_upsert()
    base = _write_twse_company_tree(tmp_path, "聯亞", "3081")
    batch = upsert.normalize("3081", base)
    assert len(batch.facts) == 4  # revenue, gross_profit, total_assets, basic_eps
    units = {r.unit for r in batch.facts}
    assert "TWD_thousands" in units
    assert "TWD_per_share" in units  # basic_eps
    # all TW facts are GAAP SOURCE_OF_TRUTH
    assert all(r.version == "GAAP" for r in batch.facts)
    assert all(r.status == "SOURCE_OF_TRUTH" for r in batch.facts)
    # TW pipeline has NO dimensional / edges
    assert batch.dimensional == []
    assert batch.edges == []
    # cell_ids unique
    ids = [r.cell_id for r in batch.facts]
    assert len(set(ids)) == len(ids)


def test_normalize_fails_loud_when_facts_missing(tmp_path):
    upsert = _import_upsert()
    base = Path(tmp_path) / "Khouse" / "Semiconductors" / "聯亞" / MOPS
    (base / "parse-twse-ixbrl").mkdir(parents=True)
    # facts file absent
    with pytest.raises(SystemExit):
        upsert.normalize("3081", base)


def test_derive_metrics_pass_through_shape(tmp_path):
    """derive-base + analytics JSON rows are already DB-row-shaped; the loaders
    return them as-is (no transformation), matching the SEC pass-through."""
    upsert = _import_upsert()
    base = _write_twse_company_tree(tmp_path, "聯亞", "3081")
    facts_path = base / "parse-twse-ixbrl" / "3081_twse_facts.json"
    _write_derive_base(base, "3081", facts_path)
    status, rows = upsert.load_derived_metrics(base, "3081")
    assert status == "loaded"
    assert rows[0]["uni_account"] == "depreciation_and_amortization"
    assert rows[0]["status"] == "DERIVED_FROM_DISCLOSED"


def test_load_analytics_run_reads_analytics_metrics_key(tmp_path):
    upsert = _import_upsert()
    base = _write_twse_company_tree(tmp_path, "聯亞", "3081")
    facts_path = base / "parse-twse-ixbrl" / "3081_twse_facts.json"
    dbp = _write_derive_base(base, "3081", facts_path)
    _write_derive_analytics(base, "3081", facts_path, dbp)
    status, payload = upsert.load_analytics_run(base, "3081")
    assert status == "loaded"
    rows = payload.get("analytics_metrics") or []
    assert rows[0]["uni_account"] == "gross_margin_pct"


def test_load_derived_metrics_missing_run_tri_state(tmp_path):
    upsert = _import_upsert()
    base = _write_twse_company_tree(tmp_path, "聯亞", "3081")
    status, rows = upsert.load_derived_metrics(base, "3081")
    assert status == "missing_run"
    assert rows == []


def test_load_derived_metrics_incomplete_run_tri_state(tmp_path):
    upsert = _import_upsert()
    base = _write_twse_company_tree(tmp_path, "聯亞", "3081")
    (base / "derive-base" / "2026-07-02-2356").mkdir(parents=True)
    status, rows = upsert.load_derived_metrics(base, "3081")
    assert status == "incomplete_run"
    assert rows == []


def test_load_derived_metrics_latest_run_wins(tmp_path):
    upsert = _import_upsert()
    base = _write_twse_company_tree(tmp_path, "聯亞", "3081")
    facts_path = base / "parse-twse-ixbrl" / "3081_twse_facts.json"
    _write_derive_base(base, "3081", facts_path, run="2026-06-01-0000",
                       rows=[{"cell_id": "old"}])
    _write_derive_base(base, "3081", facts_path, run="2026-07-02-2356",
                       rows=[{"cell_id": "new"}])
    status, rows = upsert.load_derived_metrics(base, "3081")
    assert status == "loaded"
    assert rows[0]["cell_id"] == "new"


# --------------------------------------------------------------------------- #
# 4. Freshness gate (pass / fail)
# --------------------------------------------------------------------------- #

def test_freshness_gate_passes_on_matching_hashes(tmp_path):
    upsert = _import_upsert()
    base = _write_twse_company_tree(tmp_path, "聯亞", "3081")
    facts_path = base / "parse-twse-ixbrl" / "3081_twse_facts.json"
    dbp = _write_derive_base(base, "3081", facts_path)
    payload = json.loads(dbp.read_text())
    mismatches = upsert.verify_derived_freshness(payload)
    assert mismatches == []


def test_freshness_gate_fails_on_stale_hash(tmp_path):
    upsert = _import_upsert()
    base = _write_twse_company_tree(tmp_path, "聯亞", "3081")
    facts_path = base / "parse-twse-ixbrl" / "3081_twse_facts.json"
    dbp = _write_derive_base(base, "3081", facts_path)
    payload = json.loads(dbp.read_text())
    # Corrupt the stored hash → stale
    payload["metadata"]["input_files"]["twse_facts"]["sha256"] = "0" * 64
    mismatches = upsert.verify_derived_freshness(payload)
    assert any(m["reason"] == "hash_mismatch" for m in mismatches)


def test_freshness_gate_fails_on_missing_input_files(tmp_path):
    upsert = _import_upsert()
    payload = {"metadata": {}, "derived_metrics": [{"cell_id": "x"}]}
    mismatches = upsert.verify_derived_freshness(payload)
    assert any(m["reason"] == "input_files_missing" for m in mismatches)


def test_freshness_gate_requires_twse_facts_key(tmp_path):
    """TW derive-base's required input contract is `twse_facts` (not the SEC
    gaap_* keys). A payload lacking it must fail closed."""
    upsert = _import_upsert()
    payload = {"metadata": {"input_files": {
        "derive_base": {"path": "/nope", "sha256": "a" * 64}}},
        "derived_metrics": []}
    mismatches = upsert.verify_derived_freshness(payload)
    keys = {m["key"] for m in mismatches}
    assert "twse_facts" in keys
    assert any(m["reason"] == "input_file_key_missing" for m in mismatches)


def test_analytics_required_keys_includes_derive_base_when_loaded(tmp_path):
    upsert = _import_upsert()
    assert "derive_base" in upsert.analytics_required_keys("loaded")
    assert "twse_facts" in upsert.analytics_required_keys("loaded")
    assert "derive_base" not in upsert.analytics_required_keys("missing_run")


# --------------------------------------------------------------------------- #
# 5. facts-wins collision drop
# --------------------------------------------------------------------------- #

def test_facts_wins_drops_colliding_derived_row():
    upsert = _import_upsert()
    derived_rows = [
        {"period": "Q1_FY2024", "period_kind": "quarter_duration", "version": "GAAP",
         "statement": "CF", "uni_account": "free_cash_flow", "cell_id": "collide"},
        {"period": "Q1_FY2024", "period_kind": "quarter_duration", "version": "GAAP",
         "statement": "RATIO", "uni_account": "gross_margin_pct", "cell_id": "keep"},
    ]
    facts_keys = {("Q1_FY2024", "quarter_duration", "GAAP", "CF", "free_cash_flow")}
    kept = upsert.filter_derived_rows_against_facts(derived_rows, facts_keys)
    assert [r["cell_id"] for r in kept] == ["keep"]


def test_analytics_delete_scope_covers_tw_registry():
    """The TW analytics owned-scope fallback must include the QoQ/YoY rules the
    TW pipeline emits (which the stale SEC fallback lacks), so a rule that emits
    0 rows in a later run still has its stale Supabase rows cleared."""
    upsert = _import_upsert()
    fb = set(upsert.DERIVE_ANALYTICS_RULE_IDS_FALLBACK)
    for rid in ("RATIO_REVENUE_QOQ", "RATIO_GROSS_PROFIT_QOQ",
                "RATIO_NET_INCOME_QOQ", "RATIO_EPS_DILUTED_QOQ",
                "RATIO_OPERATING_INCOME_QOQ", "RATIO_GROSS_PROFIT_YOY",
                "RATIO_OPERATING_INCOME_YOY"):
        assert rid in fb


def test_analytics_fallback_includes_new_growth_rule_ids():
    """Task 4 (rate-of-change): the growth registry expanded 10 → 44 rule_ids
    (22 IS metrics × {qoq,yoy}). The TW snapshot-delete fallback must list the
    new growth ids too, else a rule that stops firing for a period would strand
    its stale RATIO rows in Supabase. Same representative new ids the SEC test
    asserts, so both fallbacks stay in lockstep."""
    upsert = _import_upsert()
    fb = set(upsert.DERIVE_ANALYTICS_RULE_IDS_FALLBACK)
    for rid in ("RATIO_COST_OF_GOODS_SOLD_YOY", "RATIO_EPS_BASIC_QOQ",
                "RATIO_INCOME_TAX_EXPENSE_YOY",
                "RATIO_SELLING_GENERAL_ADMINISTRATIVE_YOY",
                "RATIO_NET_INCOME_NCI_QOQ"):
        assert rid in fb


def test_analytics_fallback_includes_share_structure_adj_rule_ids():
    """Task 10: derive-analytics now emits Class-A-rebased share-structure ADJ
    rows (4 level ids from adjustment.py, not an AnalyticsRule) plus their
    qoq/yoy growth rows. The TW snapshot-delete fallback must list all 8, same
    as the SEC fallback, else a run emitting zero ADJ rows for a period would
    strand stale adjustment_factor_cum / *_adj level and growth rows in
    Supabase."""
    upsert = _import_upsert()
    fb = set(upsert.DERIVE_ANALYTICS_RULE_IDS_FALLBACK)
    for rid in ("ADJ_EPS_BASIC", "ADJ_EPS_DILUTED",
                "ADJ_COMMON_SHARES_OUTSTANDING", "ADJ_FACTOR_CUM",
                "RATIO_EPS_BASIC_ADJ_YOY", "RATIO_EPS_BASIC_ADJ_QOQ",
                "RATIO_EPS_DILUTED_ADJ_YOY", "RATIO_EPS_DILUTED_ADJ_QOQ"):
        assert rid in fb


def test_derive_base_delete_scope_covers_tw_identity_rule():
    upsert = _import_upsert()
    fb = set(upsert.DERIVE_BASE_RULE_IDS_FALLBACK)
    assert "IDENTITY_DA_DEP_PLUS_AMORT" in fb
    assert {"Q2_6M_MINUS_Q1", "Q3_9M_MINUS_6M", "Q4_FY_MINUS_9M"} <= fb


# --------------------------------------------------------------------------- #
# 6. dry-run produces a diff without writing
# --------------------------------------------------------------------------- #

def test_dry_run_produces_report_without_db(tmp_path, monkeypatch, capsys):
    """Default (no --apply) must print a normalization report and NEVER open a
    Supabase connection."""
    upsert = _import_upsert()
    vault = tmp_path
    base = _write_twse_company_tree(vault, "聯亞", "3081")
    facts_path = base / "parse-twse-ixbrl" / "3081_twse_facts.json"
    dbp = _write_derive_base(vault, "3081", facts_path)  # placeholder path fix below

    # derive-base must live UNDER the discovered base, not the vault root.
    # Rebuild it under `base`:
    import shutil
    shutil.rmtree(base / "derive-base", ignore_errors=True)
    dbp = _write_derive_base(base, "3081", facts_path)
    _write_derive_analytics(base, "3081", facts_path, dbp)

    monkeypatch.setattr(upsert, "OBSIDIAN_BASE", vault)
    monkeypatch.setattr(upsert, "supabase_client",
                        lambda: (_ for _ in ()).throw(AssertionError("dry-run must not touch DB")))
    monkeypatch.setattr(sys, "argv", ["upsert_twse_financials.py", "3081"])

    upsert.main()  # dry-run: must complete without DB
    out = capsys.readouterr().out
    assert "3081" in out
    assert "TWSE" in out
    assert "facts:" in out
    assert "Dry-run complete" in out


def test_dry_run_gate_fails_loud_when_facts_missing(tmp_path, monkeypatch):
    upsert = _import_upsert()
    vault = tmp_path
    base = Path(vault) / "Khouse" / "Semiconductors" / "聯亞" / MOPS
    (base / "parse-twse-ixbrl").mkdir(parents=True)  # empty — no facts json
    monkeypatch.setattr(upsert, "OBSIDIAN_BASE", vault)
    monkeypatch.setattr(sys, "argv", ["upsert_twse_financials.py", "3081"])
    with pytest.raises(SystemExit):
        upsert.main()
