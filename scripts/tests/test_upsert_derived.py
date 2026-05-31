import json
from pathlib import Path
import importlib.util
import sys

import pytest


def _import_upsert():
    p = Path(__file__).resolve().parents[1] / "upsert_sec_financials.py"
    spec = importlib.util.spec_from_file_location("upsert_mod", str(p))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["upsert_mod"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_load_derived_metrics_latest_run(tmp_path):
    upsert = _import_upsert()
    # Build a vault skeleton with two run folders → expect the later one wins.
    vault = tmp_path
    base = vault / "Khouse" / "Semiconductors" / "ABC" / "01_Source" / "SEC Filings" / "Skill_Output" / "derive-base"
    (base / "2026-05-01-1000").mkdir(parents=True)
    (base / "2026-05-17-1200").mkdir(parents=True)
    (base / "2026-05-01-1000" / "ABC_derived.json").write_text(json.dumps({
        "metadata": {"ticker": "ABC", "skill_version": "0.1"},
        "derived_metrics": [{"cell_id": "old"}],
    }))
    (base / "2026-05-17-1200" / "ABC_derived.json").write_text(json.dumps({
        "metadata": {"ticker": "ABC", "skill_version": "1.0"},
        "derived_metrics": [{"cell_id": "new"}],
    }))
    status, rows = upsert.load_derived_metrics(vault, "ABC")
    assert status == "loaded"
    assert len(rows) == 1
    assert rows[0]["cell_id"] == "new"


def test_load_derived_metrics_missing_run_returns_tri_state(tmp_path):
    """Codex round-3 F2: no derive-base output dir at all → ('missing_run', []).
    Caller MUST use status, not bool-empty, to decide whether to DELETE."""
    upsert = _import_upsert()
    status, rows = upsert.load_derived_metrics(tmp_path, "XYZ")
    assert status == "missing_run"
    assert rows == []


def test_load_derived_metrics_incomplete_run_returns_tri_state(tmp_path):
    """Codex round-3 F2: latest run folder exists but JSON missing → ('incomplete_run', [])."""
    upsert = _import_upsert()
    vault = tmp_path
    base = vault / "Khouse" / "Semiconductors" / "DEF" / "01_Source" / "SEC Filings" / "Skill_Output" / "derive-base"
    (base / "2026-05-19-0000").mkdir(parents=True)
    # No DEF_derived.json file
    status, rows = upsert.load_derived_metrics(vault, "DEF")
    assert status == "incomplete_run"
    assert rows == []


def test_load_derived_metrics_unparseable_json_returns_incomplete(tmp_path):
    upsert = _import_upsert()
    vault = tmp_path
    base = vault / "Khouse" / "Semiconductors" / "GHI" / "01_Source" / "SEC Filings" / "Skill_Output" / "derive-base"
    (base / "2026-05-19-0000").mkdir(parents=True)
    (base / "2026-05-19-0000" / "GHI_derived.json").write_text("{not valid json")
    status, rows = upsert.load_derived_metrics(vault, "GHI")
    assert status == "incomplete_run"
    assert rows == []


def test_main_apply_fails_closed_on_incomplete_run(tmp_path, monkeypatch, capsys):
    """Codex round-5 F1: CLI main() with --apply MUST exit non-zero and
    refuse to touch Supabase when derive-base latest run is incomplete.
    Prevents regression of round-4 F2 fail-closed guard if someone moves
    the tri-state check back below apply(batch)."""
    upsert = _import_upsert()

    # Build vault with incomplete-run shape (folder but no JSON).
    vault = tmp_path
    base = vault / "Khouse" / "Semiconductors" / "MOCK" / "01_Source" / "SEC Filings" / "Skill_Output" / "derive-base"
    (base / "2026-05-19-9999").mkdir(parents=True)

    monkeypatch.setattr(upsert, "OBSIDIAN_BASE", vault)

    # Gate-pass stubs — make the parse-side path a no-op so the test
    # focuses on the derive-status branch.
    class _StubBatch:
        pass
    monkeypatch.setattr(upsert, "load_sources", lambda ticker: {})
    monkeypatch.setattr(upsert, "normalize", lambda ticker, sources: _StubBatch())
    monkeypatch.setattr(upsert, "print_report", lambda batch: True)

    apply_called = {"n": 0}
    supabase_called = {"n": 0}
    def _no_apply(batch):
        apply_called["n"] += 1
    def _no_supabase():
        supabase_called["n"] += 1
        raise AssertionError("supabase_client must not be called on incomplete_run")
    monkeypatch.setattr(upsert, "apply", _no_apply)
    monkeypatch.setattr(upsert, "supabase_client", _no_supabase)

    monkeypatch.setattr(sys, "argv", ["upsert_sec_financials.py", "MOCK", "--apply"])

    with pytest.raises(SystemExit) as exc:
        upsert.main()
    assert exc.value.code == 2
    assert apply_called["n"] == 0, "apply(batch) MUST NOT be called on incomplete_run"
    assert supabase_called["n"] == 0


def test_verify_derived_freshness_detects_hash_mismatch(tmp_path):
    """Codex round-6 F1: verify_derived_freshness must flag source files
    whose current sha256 != stored sha256 in payload.metadata.input_files."""
    import hashlib
    upsert = _import_upsert()
    src1 = tmp_path / "facts.json"
    src1.write_text('{"x": 1}')
    src3 = tmp_path / "inline.json"
    src3.write_text('{"i": 0}')
    h1 = hashlib.sha256(src1.read_bytes()).hexdigest()
    h3 = hashlib.sha256(src3.read_bytes()).hexdigest()

    src2 = tmp_path / "edges.json"
    src2.write_text('{"y": 2}')
    payload = {
        "metadata": {
            "input_files": {
                "gaap_inline": {"path": str(src3), "sha256": h3},
                "gaap_facts": {"path": str(src1), "sha256": h1},
                "gaap_edges_cal": {"path": str(src2), "sha256": "0" * 64},  # wrong
                "nongaap": None,
            }
        },
        "derived_metrics": [],
    }
    mismatches = upsert.verify_derived_freshness(payload)
    # Only the hash_mismatch on gaap_edges_cal — required keys all present, no
    # input_file_key_missing entries should appear.
    hash_mismatches = [m for m in mismatches if m["reason"] == "hash_mismatch"]
    contract_misses = [m for m in mismatches if m["reason"] == "input_file_key_missing"]
    assert contract_misses == []
    assert len(hash_mismatches) == 1
    assert hash_mismatches[0]["key"] == "gaap_edges_cal"


def test_verify_derived_freshness_flags_missing_file(tmp_path):
    upsert = _import_upsert()
    import hashlib
    # All 3 required keys present; only gaap_facts points to a non-existent file.
    real_inline = tmp_path / "inline.json"; real_inline.write_text('{"i":0}')
    real_edges  = tmp_path / "edges.json";  real_edges.write_text('{"e":0}')
    h_inline = hashlib.sha256(real_inline.read_bytes()).hexdigest()
    h_edges  = hashlib.sha256(real_edges.read_bytes()).hexdigest()
    payload = {
        "metadata": {"input_files": {
            "gaap_inline":    {"path": str(real_inline), "sha256": h_inline},
            "gaap_facts":     {"path": str(tmp_path / "missing.json"), "sha256": "abc" * 21 + "a"},
            "gaap_edges_cal": {"path": str(real_edges),  "sha256": h_edges},
        }},
        "derived_metrics": [],
    }
    m = upsert.verify_derived_freshness(payload)
    file_missing = [x for x in m if x["reason"] == "file_missing"]
    assert len(file_missing) == 1
    assert file_missing[0]["key"] == "gaap_facts"


def test_main_apply_fails_closed_on_stale_derived(tmp_path, monkeypatch):
    """R6-F1: main(--apply) MUST exit non-zero when derive-base output's
    stored source hashes don't match current parse files. Must not call
    apply() / supabase_client()."""
    import hashlib
    upsert = _import_upsert()

    vault = tmp_path
    parse_dir = vault / "Khouse" / "Semiconductors" / "STAL" / "01_Source" / "SEC Filings" / "Skill_Output" / "parse-10QK-gaap"
    parse_dir.mkdir(parents=True)
    facts_file = parse_dir / "STAL_gaap_facts.json"
    facts_file.write_text('{"facts": [], "metadata": {}}')
    inline_file = parse_dir / "STAL_gaap.json"
    inline_file.write_text('{"metadata": {}}')
    edges_file = parse_dir / "STAL_gaap_edges_cal.json"
    edges_file.write_text('{"edges": []}')

    import hashlib
    h_inline = hashlib.sha256(inline_file.read_bytes()).hexdigest()
    h_edges  = hashlib.sha256(edges_file.read_bytes()).hexdigest()

    derive_base = vault / "Khouse" / "Semiconductors" / "STAL" / "01_Source" / "SEC Filings" / "Skill_Output" / "derive-base"
    run = derive_base / "2026-05-19-9999"
    run.mkdir(parents=True)
    (run / "STAL_derived.json").write_text(json.dumps({
        "metadata": {
            "input_files": {
                "gaap_inline":    {"path": str(inline_file), "sha256": h_inline},
                "gaap_facts":     {"path": str(facts_file),  "sha256": "0" * 64},  # stale
                "gaap_edges_cal": {"path": str(edges_file),  "sha256": h_edges},
            }
        },
        "derived_metrics": [{"cell_id": "x"}],
    }))

    monkeypatch.setattr(upsert, "OBSIDIAN_BASE", vault)
    monkeypatch.setattr(upsert, "load_sources", lambda t: {})
    monkeypatch.setattr(upsert, "normalize", lambda t, s: object())
    monkeypatch.setattr(upsert, "print_report", lambda b: True)
    apply_called = {"n": 0}
    def _no_apply(b):
        apply_called["n"] += 1
    monkeypatch.setattr(upsert, "apply", _no_apply)
    monkeypatch.setattr(upsert, "supabase_client", lambda: (_ for _ in ()).throw(AssertionError("must not call supabase on stale derive")))
    monkeypatch.setattr(sys, "argv", ["upsert_sec_financials.py", "STAL", "--apply"])

    with pytest.raises(SystemExit) as exc:
        upsert.main()
    assert exc.value.code == 3
    assert apply_called["n"] == 0


def test_verify_derived_freshness_malformed_info_no_sha256(tmp_path):
    """R8-F1: required key present with path but no sha256 must NOT pass
    silently. Should produce input_file_metadata_invalid mismatch."""
    upsert = _import_upsert()
    src = tmp_path / "facts.json"; src.write_text('{"x":1}')
    payload = {
        "metadata": {"input_files": {
            "gaap_inline":    {"path": str(src), "sha256": "a" * 64},  # OK key
            "gaap_facts":     {"path": str(src)},  # malformed: no sha256
            "gaap_edges_cal": {"path": str(src), "sha256": "a" * 64},
        }},
        "derived_metrics": [],
    }
    m = upsert.verify_derived_freshness(payload)
    bad = [x for x in m if x["reason"] == "input_file_metadata_invalid"]
    assert len(bad) == 1
    assert bad[0]["key"] == "gaap_facts"


def test_verify_derived_freshness_malformed_info_no_path(tmp_path):
    """R8-F1: sha256 present but path absent must NOT crash — must produce
    structured input_file_metadata_invalid mismatch."""
    upsert = _import_upsert()
    src = tmp_path / "facts.json"; src.write_text('{"x":1}')
    payload = {
        "metadata": {"input_files": {
            "gaap_inline":    {"path": str(src), "sha256": "a" * 64},
            "gaap_facts":     {"sha256": "a" * 64},  # malformed: no path
            "gaap_edges_cal": {"path": str(src), "sha256": "a" * 64},
        }},
        "derived_metrics": [],
    }
    m = upsert.verify_derived_freshness(payload)
    bad = [x for x in m if x["reason"] == "input_file_metadata_invalid"]
    assert len(bad) == 1
    assert bad[0]["key"] == "gaap_facts"


def test_verify_derived_freshness_missing_input_files(tmp_path):
    """R7-F1: payload that has derived_metrics but no metadata.input_files
    must NOT be treated as fresh."""
    upsert = _import_upsert()
    payload = {"metadata": {}, "derived_metrics": [{"cell_id": "x"}]}
    m = upsert.verify_derived_freshness(payload)
    reasons = {x["reason"] for x in m}
    assert "input_files_missing" in reasons


def test_verify_derived_freshness_partial_input_files(tmp_path):
    """R7-F1: partial input_files (missing required key like gaap_facts)
    must fail the freshness gate even if all listed files match."""
    import hashlib
    upsert = _import_upsert()
    src = tmp_path / "inline.json"
    src.write_text('{"x": 1}')
    h = hashlib.sha256(src.read_bytes()).hexdigest()
    payload = {
        "metadata": {"input_files": {
            "gaap_inline": {"path": str(src), "sha256": h},
            # gaap_facts and gaap_edges_cal intentionally missing
        }},
        "derived_metrics": [],
    }
    m = upsert.verify_derived_freshness(payload)
    reasons = {x["reason"] for x in m}
    keys = {x["key"] for x in m}
    assert "input_file_key_missing" in reasons
    assert "gaap_facts" in keys
    assert "gaap_edges_cal" in keys


def test_main_apply_fails_closed_on_missing_input_files_contract(tmp_path, monkeypatch):
    """R7-F1: main --apply must exit 3 when derive payload lacks
    metadata.input_files contract."""
    upsert = _import_upsert()
    vault = tmp_path
    derive = vault / "Khouse" / "Semiconductors" / "NOMETA" / "01_Source" / "SEC Filings" / "Skill_Output" / "derive-base"
    run = derive / "2026-05-19-9999"
    run.mkdir(parents=True)
    (run / "NOMETA_derived.json").write_text(json.dumps({
        "metadata": {},  # no input_files
        "derived_metrics": [{"cell_id": "a"}],
    }))
    monkeypatch.setattr(upsert, "OBSIDIAN_BASE", vault)
    monkeypatch.setattr(upsert, "load_sources", lambda t: {})
    monkeypatch.setattr(upsert, "normalize", lambda t, s: object())
    monkeypatch.setattr(upsert, "print_report", lambda b: True)
    apply_called = {"n": 0}
    monkeypatch.setattr(upsert, "apply", lambda b: apply_called.__setitem__("n", apply_called["n"] + 1))
    monkeypatch.setattr(upsert, "supabase_client", lambda: (_ for _ in ()).throw(AssertionError("no DB on missing input_files")))
    monkeypatch.setattr(sys, "argv", ["upsert_sec_financials.py", "NOMETA", "--apply"])
    with pytest.raises(SystemExit) as exc:
        upsert.main()
    assert exc.value.code == 3
    assert apply_called["n"] == 0


def test_main_apply_fails_closed_on_missing_run_with_db_metrics(tmp_path, monkeypatch):
    """R7-F2: missing local derive run + DB already has derived_q4 metrics
    for ticker → SystemExit(4), apply not called. Requires opt-in flag."""
    upsert = _import_upsert()
    vault = tmp_path  # no derive-base folder → missing_run

    monkeypatch.setattr(upsert, "OBSIDIAN_BASE", vault)
    monkeypatch.setattr(upsert, "load_sources", lambda t: {})
    monkeypatch.setattr(upsert, "normalize", lambda t, s: object())
    monkeypatch.setattr(upsert, "print_report", lambda b: True)
    apply_called = {"n": 0}
    monkeypatch.setattr(upsert, "apply", lambda b: apply_called.__setitem__("n", apply_called["n"] + 1))

    # Stub supabase_client to report N existing derived rows
    class _StubExec:
        def __init__(self, n): self.count = n; self.data = []
    class _StubQuery:
        def __init__(self, n): self.n = n
        def select(self, *a, **kw): return self
        def eq(self, *a, **kw): return self
        def in_(self, *a, **kw): return self  # R8-F2 added IS/CF filter
        def limit(self, *a, **kw): return self
        def execute(self): return _StubExec(self.n)
    class _StubClient:
        def table(self, name): return _StubQuery(7)  # 7 existing derived rows
    monkeypatch.setattr(upsert, "supabase_client", lambda: _StubClient())

    monkeypatch.setattr(sys, "argv", ["upsert_sec_financials.py", "EXIST", "--apply"])
    with pytest.raises(SystemExit) as exc:
        upsert.main()
    assert exc.value.code == 4
    assert apply_called["n"] == 0


def test_missing_run_db_lookup_filters_by_rule_id(tmp_path, monkeypatch):
    """Replaces the legacy R8-F2 statement-IS-CF filter test.

    When checking if Supabase already has derive-base-managed metrics, the
    query must restrict by provenance->>rule_id IN DERIVE_BASE_RULE_IDS_FALLBACK.
    This is the provenance-based scope contract (replacing the old
    period_kind=derived_q4 + statement IN IS/CF combo) so RATIO rows from
    derive-analytics — which have different rule_ids — never trigger the
    missing_run + DB-existing exit-4 path."""
    upsert = _import_upsert()
    vault = tmp_path

    monkeypatch.setattr(upsert, "OBSIDIAN_BASE", vault)
    monkeypatch.setattr(upsert, "load_sources", lambda t: {})
    monkeypatch.setattr(upsert, "normalize", lambda t, s: object())
    monkeypatch.setattr(upsert, "print_report", lambda b: True)
    apply_called = {"n": 0}
    monkeypatch.setattr(upsert, "apply", lambda b: apply_called.__setitem__("n", apply_called["n"] + 1))

    captured_filters: list[tuple] = []
    class _StubExec:
        def __init__(self, n): self.count = n; self.data = []
    class _StubQuery:
        def __init__(self): self._has_rule_filter = False
        def select(self, *a, **kw): return self
        def eq(self, *a, **kw): return self
        def in_(self, col, vals):
            captured_filters.append((col, tuple(vals)))
            self._has_rule_filter = (
                col == "provenance->>rule_id"
                and set(vals) >= {"Q4_FY_MINUS_9M", "Q4_FY_MINUS_Q1Q2Q3"}
            )
            return self
        def limit(self, *a, **kw): return self
        def execute(self):
            # Only return count > 0 if the rule_id filter was applied.
            return _StubExec(7 if self._has_rule_filter else 0)
    class _StubClient:
        def table(self, name): return _StubQuery()
    monkeypatch.setattr(upsert, "supabase_client", lambda: _StubClient())
    monkeypatch.setattr(sys, "argv", ["upsert_sec_financials.py", "RTONLY", "--apply"])

    # With rule_id filter present, stub returns 7 → exit 4 (gate fires correctly)
    with pytest.raises(SystemExit) as exc:
        upsert.main()
    assert exc.value.code == 4
    # The rule_id filter must have been applied to the lookup
    assert any(col == "provenance->>rule_id" for col, _ in captured_filters)


def test_main_apply_allows_missing_run_when_flag_passed(tmp_path, monkeypatch):
    """R7-F2 opt-in: --allow-missing-derived bypasses the missing_run gate
    so first-time tickers or intentional parse-only refresh can proceed."""
    upsert = _import_upsert()
    vault = tmp_path

    monkeypatch.setattr(upsert, "OBSIDIAN_BASE", vault)
    monkeypatch.setattr(upsert, "load_sources", lambda t: {})
    monkeypatch.setattr(upsert, "normalize", lambda t, s: object())
    monkeypatch.setattr(upsert, "print_report", lambda b: True)
    apply_called = {"n": 0}
    monkeypatch.setattr(upsert, "apply", lambda b: apply_called.__setitem__("n", apply_called["n"] + 1))
    # supabase_client must not be called in this path (no DB lookup needed
    # because the gate is bypassed; derived rows are simply [] so no DELETE).
    monkeypatch.setattr(upsert, "supabase_client", lambda: (_ for _ in ()).throw(AssertionError("opt-in path must skip DB lookup")))

    monkeypatch.setattr(sys, "argv", ["upsert_sec_financials.py", "NEWTICK", "--apply", "--allow-missing-derived"])
    upsert.main()  # should complete normally
    assert apply_called["n"] == 1


def test_load_derived_metrics_legitimate_empty_returns_loaded(tmp_path):
    """Legitimate completed run with no derived rows must say 'loaded'."""
    upsert = _import_upsert()
    vault = tmp_path
    base = vault / "Khouse" / "Semiconductors" / "JKL" / "01_Source" / "SEC Filings" / "Skill_Output" / "derive-base"
    (base / "2026-05-19-0000").mkdir(parents=True)
    (base / "2026-05-19-0000" / "JKL_derived.json").write_text(json.dumps({
        "metadata": {"ticker": "JKL", "skill_version": "1.0"},
        "derived_metrics": [],
    }))
    status, rows = upsert.load_derived_metrics(vault, "JKL")
    assert status == "loaded"
    assert rows == []


def test_analytics_delete_scope_unions_payload_with_fallback():
    """Phase 0 P0.2: analytics delete scope must cover the full owned rule
    registry even if a payload lists only a subset, so stale rows for rules
    that emitted nothing this run still get cleared."""
    upsert = _import_upsert()
    scope = set(upsert.analytics_delete_scope(["RATIO_GROSS_MARGIN_PCT"]))
    assert set(upsert.DERIVE_ANALYTICS_RULE_IDS_FALLBACK) <= scope


def test_analytics_delete_scope_empty_payload_uses_full_fallback():
    upsert = _import_upsert()
    scope = set(upsert.analytics_delete_scope(None))
    assert scope == set(upsert.DERIVE_ANALYTICS_RULE_IDS_FALLBACK)


def test_verify_freshness_accepts_custom_required_keys(tmp_path):
    """Phase 0 P0.3: derive-analytics has a different minimum-input set than
    derive-base, so verify_derived_freshness must accept required_keys to gate
    both skills with the same hashing logic."""
    upsert = _import_upsert()
    payload = {"metadata": {"input_files": {
        "nongaap": {"path": str(tmp_path / "nope"), "sha256": "abc"},
    }}}
    m = upsert.verify_derived_freshness(payload, required_keys={"gaap_facts"})
    assert any(x["key"] == "gaap_facts" and x["reason"] == "input_file_key_missing" for x in m)


# ---- Phase 0 P1 fixes: analytics apply-path gating + client scoping ----

def _make_fresh_analytics_run(vault, ticker, tmp_path, rule_id="RATIO_GROSS_MARGIN_PCT"):
    """Build a 'loaded' analytics run whose input_files hash matches a real file
    so verify_derived_freshness passes."""
    import hashlib
    gaap = tmp_path / f"{ticker}_gaap_facts.json"
    gaap.write_text('{"facts": []}')
    sha = hashlib.sha256(gaap.read_bytes()).hexdigest()
    run = (vault / "Khouse" / "Semiconductors" / ticker / "01_Source" / "SEC Filings"
           / "Skill_Output" / "derive-analytics" / "2026-05-31-0000")
    run.mkdir(parents=True)
    (run / f"{ticker}_analytics.json").write_text(json.dumps({
        "metadata": {"ticker": ticker, "managed_rule_ids": [rule_id],
                     "input_files": {"gaap_facts": {"path": str(gaap), "sha256": sha}}},
        "ratio_metrics": [{"cell_id": "r1", "ticker": ticker, "statement": "RATIO",
                           "period": "Q1_FY2025", "period_kind": "quarter_duration",
                           "version": "GAAP", "uni_account": "gross_margin_pct",
                           "provenance": {"rule_id": rule_id}}],
    }))


class _RecQuery:
    def __init__(self, ops): self.ops = ops
    def delete(self): self.ops["delete"] += 1; return self
    def upsert(self, *a, **k): self.ops["upsert"] += 1; return self
    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def in_(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def execute(self):
        class _E: data = []; count = 0
        return _E()


class _RecClient:
    def __init__(self, ops): self.ops = ops
    def table(self, name): return _RecQuery(self.ops)


def test_main_allow_missing_derived_with_analytics_loaded_does_not_crash(tmp_path, monkeypatch):
    """P1.2: --allow-missing-derived (derive-base missing) + analytics loaded must
    NOT raise UnboundLocalError on `client` when the analytics block runs DB ops."""
    upsert = _import_upsert()
    vault = tmp_path / "vault"; vault.mkdir()
    _make_fresh_analytics_run(vault, "ALCK", tmp_path)
    monkeypatch.setattr(upsert, "OBSIDIAN_BASE", vault)
    monkeypatch.setattr(upsert, "load_sources", lambda t: {})
    monkeypatch.setattr(upsert, "normalize", lambda t, s: object())
    monkeypatch.setattr(upsert, "print_report", lambda b: True)
    apply_called = {"n": 0}
    monkeypatch.setattr(upsert, "apply", lambda b: apply_called.__setitem__("n", apply_called["n"] + 1))
    ops = {"delete": 0, "upsert": 0}
    monkeypatch.setattr(upsert, "supabase_client", lambda: _RecClient(ops))
    monkeypatch.setattr(sys, "argv", ["upsert_sec_financials.py", "ALCK", "--apply", "--allow-missing-derived"])
    upsert.main()  # must complete, no UnboundLocalError
    assert apply_called["n"] == 1
    assert ops["upsert"] >= 1, "analytics rows must be upserted via a valid client"


def test_main_apply_fails_closed_on_analytics_incomplete(tmp_path, monkeypatch):
    """P1.1: analytics incomplete run must fail closed BEFORE apply(batch), so
    fresh facts are never written alongside stale ratio rows."""
    upsert = _import_upsert()
    vault = tmp_path
    run = (vault / "Khouse" / "Semiconductors" / "AINC" / "01_Source" / "SEC Filings"
           / "Skill_Output" / "derive-analytics" / "2026-05-31-0000")
    run.mkdir(parents=True)  # folder but no JSON → incomplete_run
    monkeypatch.setattr(upsert, "OBSIDIAN_BASE", vault)
    monkeypatch.setattr(upsert, "load_sources", lambda t: {})
    monkeypatch.setattr(upsert, "normalize", lambda t, s: object())
    monkeypatch.setattr(upsert, "print_report", lambda b: True)
    apply_called = {"n": 0}
    monkeypatch.setattr(upsert, "apply", lambda b: apply_called.__setitem__("n", apply_called["n"] + 1))
    monkeypatch.setattr(upsert, "supabase_client", lambda: (_ for _ in ()).throw(AssertionError("no DB on analytics incomplete")))
    monkeypatch.setattr(sys, "argv", ["upsert_sec_financials.py", "AINC", "--apply", "--allow-missing-derived"])
    with pytest.raises(SystemExit):
        upsert.main()
    assert apply_called["n"] == 0, "apply(batch) MUST NOT run when analytics is incomplete"


def test_analytics_fallback_matches_skill_registry():
    """P2.2 drift guard: upsert's DERIVE_ANALYTICS_RULE_IDS_FALLBACK must equal
    the derive-analytics skill's ALL_RULE_IDS in EVERY deployed mirror, not just
    the first one found. They live in different repos and are hand-synced, so a
    rule added to the skill but not the upsert fallback (or a mirror left behind)
    would let that rule's stale rows survive. Checking all mirrors catches drift
    even when the dev prototype happens to match but a runtime mirror does not."""
    import importlib.util
    upsert = _import_upsert()
    fallback = set(upsert.DERIVE_ANALYTICS_RULE_IDS_FALLBACK)
    mirrors = [
        Path.home() / "AI_Agent" / "tmp" / "derive-analytics" / "rules_ratios.py",
        Path.home() / "CC_Switch_Config" / "skills" / "derive-analytics" / "scripts" / "rules_ratios.py",
        Path.home() / ".claude" / "skills" / "derive-analytics" / "scripts" / "rules_ratios.py",
        Path.home() / ".codex" / "skills" / "derive-analytics" / "scripts" / "rules_ratios.py",
        Path.home() / ".cc-switch" / "skills" / "derive-analytics" / "scripts" / "rules_ratios.py",
    ]
    found = [p for p in mirrors if p.is_file()]
    if not found:
        pytest.skip("derive-analytics skill rules_ratios.py not found in any known mirror")
    for i, src in enumerate(found):
        modname = f"ra_rules_{i}"
        spec = importlib.util.spec_from_file_location(modname, str(src))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[modname] = mod  # required for dataclass KW_ONLY under `from __future__ import annotations`
        spec.loader.exec_module(mod)
        assert set(mod.ALL_RULE_IDS) == fallback, (
            f"registry drift in mirror {src}: ALL_RULE_IDS={set(mod.ALL_RULE_IDS)} "
            f"!= upsert fallback={fallback}"
        )


def test_filter_ratio_rows_against_facts_drops_collisions():
    """P2.1 storage facts-wins: a derived RATIO row whose logical identity
    (period|period_kind|version|statement|uni_account) collides with a disclosed
    facts row must NOT be written to sec_financial_metrics — facts win at the
    storage boundary, not just in the API read model."""
    upsert = _import_upsert()
    ratio_rows = [
        {"period": "Q1_FY2025", "period_kind": "quarter_duration", "version": "GAAP",
         "statement": "RATIO", "uni_account": "gross_margin_pct", "cell_id": "g"},
        {"period": "Q1_FY2025", "period_kind": "quarter_duration", "version": "NON_GAAP",
         "statement": "RATIO", "uni_account": "gross_margin_pct", "cell_id": "ng"},
    ]
    facts_keys = {("Q1_FY2025", "quarter_duration", "GAAP", "RATIO", "gross_margin_pct")}
    kept = upsert.filter_ratio_rows_against_facts(ratio_rows, facts_keys)
    assert [r["cell_id"] for r in kept] == ["ng"]  # GAAP collides → dropped; NON_GAAP kept


def test_analytics_required_keys_includes_derive_base_when_derive_loaded():
    """P1 (2nd-pass): when derive-base is loaded, the analytics freshness gate
    must require the derive_base lineage too — otherwise analytics that ran
    WITHOUT derive-base passes the gate and ships raw-only ratios alongside
    fresh derive-base Q4 metrics (mixed-vintage)."""
    upsert = _import_upsert()
    assert "derive_base" in upsert.analytics_required_keys("loaded")
    assert "gaap_facts" in upsert.analytics_required_keys("loaded")
    # parse-only / no-derive-base refresh must NOT require derive_base lineage
    assert "derive_base" not in upsert.analytics_required_keys("missing_run")
    assert "derive_base" not in upsert.analytics_required_keys("incomplete_run")


def _make_fresh_derive_base_run(vault, ticker, tmp_path):
    """Build a 'loaded' + fresh derive-base run (input_files hashes match)."""
    import hashlib
    files = {}
    for key, suffix in (("gaap_inline", "_gaap.json"),
                        ("gaap_facts", "_gf.json"),
                        ("gaap_edges_cal", "_edges.json")):
        f = tmp_path / f"{ticker}{suffix}"
        f.write_text("{}")
        files[key] = {"path": str(f), "sha256": hashlib.sha256(f.read_bytes()).hexdigest()}
    run = (vault / "Khouse" / "Semiconductors" / ticker / "01_Source" / "SEC Filings"
           / "Skill_Output" / "derive-base" / "2026-05-31-0000")
    run.mkdir(parents=True)
    (run / f"{ticker}_derived.json").write_text(json.dumps({
        "metadata": {"ticker": ticker, "managed_rule_ids": ["Q4_FY_MINUS_9M"],
                     "input_files": files},
        "derived_metrics": [],
    }))


def test_main_apply_fails_closed_when_analytics_missing_derive_base_lineage(tmp_path, monkeypatch):
    """P1 (2nd-pass): derive-base loaded + analytics loaded but its input_files
    lacks derive_base → the analytics ran before derive-base existed → mixed
    vintage. Must exit BEFORE apply(batch)."""
    upsert = _import_upsert()
    vault = tmp_path / "vault"; vault.mkdir()
    _make_fresh_derive_base_run(vault, "LIN", tmp_path)
    _make_fresh_analytics_run(vault, "LIN", tmp_path)  # input_files = gaap_facts only
    monkeypatch.setattr(upsert, "OBSIDIAN_BASE", vault)
    monkeypatch.setattr(upsert, "load_sources", lambda t: {})
    monkeypatch.setattr(upsert, "normalize", lambda t, s: object())
    monkeypatch.setattr(upsert, "print_report", lambda b: True)
    apply_called = {"n": 0}
    monkeypatch.setattr(upsert, "apply", lambda b: apply_called.__setitem__("n", apply_called["n"] + 1))
    monkeypatch.setattr(upsert, "supabase_client", lambda: (_ for _ in ()).throw(AssertionError("must not hit DB before analytics lineage gate")))
    monkeypatch.setattr(sys, "argv", ["upsert_sec_financials.py", "LIN", "--apply"])
    with pytest.raises(SystemExit):
        upsert.main()
    assert apply_called["n"] == 0, "apply(batch) MUST NOT run when analytics lacks derive_base lineage"


def test_analytics_derive_base_is_current_path_match(tmp_path):
    """P1 (3rd-pass): the analytics run's recorded derive_base path must equal
    the CURRENT latest derive-base run JSON. A newer derive-base run (old folder
    still on disk) means analytics is stale even though its old-path hash still
    matches."""
    upsert = _import_upsert()
    latest = tmp_path / "derive-base" / "2026-05-31-0900" / "T_derived.json"
    older = tmp_path / "derive-base" / "2026-05-21-1419" / "T_derived.json"
    # analytics pointing at the current latest → current
    pay_ok = {"metadata": {"input_files": {"derive_base": {"path": str(latest), "sha256": "x"}}}}
    assert upsert.analytics_derive_base_is_current(pay_ok, latest) is True
    # analytics pointing at an older run → stale
    pay_old = {"metadata": {"input_files": {"derive_base": {"path": str(older), "sha256": "x"}}}}
    assert upsert.analytics_derive_base_is_current(pay_old, latest) is False
    # no current derive-base → nothing to be stale against
    assert upsert.analytics_derive_base_is_current(pay_old, None) is True
    # claims no derive_base lineage while derive-base exists → stale
    pay_none = {"metadata": {"input_files": {}}}
    assert upsert.analytics_derive_base_is_current(pay_none, latest) is False


def test_main_apply_fails_closed_when_analytics_points_to_older_derive_base(tmp_path, monkeypatch):
    """P1 (3rd-pass): a newer derive-base run exists but analytics' recorded
    derive_base path points to an OLDER run still on disk (old-path hash still
    matches). Must exit BEFORE apply — fresh derive-base + stale ratios."""
    import hashlib
    upsert = _import_upsert()
    vault = tmp_path / "vault"; vault.mkdir()
    db_base = (vault / "Khouse" / "Semiconductors" / "OLD" / "01_Source" / "SEC Filings"
               / "Skill_Output" / "derive-base")
    # Older derive-base run A (still on disk)
    runA = db_base / "2026-05-21-1419"; runA.mkdir(parents=True)
    a_json = runA / "OLD_derived.json"
    a_json.write_text(json.dumps({"metadata": {"ticker": "OLD"}, "derived_metrics": []}))
    a_sha = hashlib.sha256(a_json.read_bytes()).hexdigest()
    # Newer derive-base run B (latest, fresh inputs)
    files = {}
    for key, suffix in (("gaap_inline", "_gaap.json"), ("gaap_facts", "_gf.json"),
                        ("gaap_edges_cal", "_edges.json")):
        f = tmp_path / f"OLD{suffix}"; f.write_text("{}")
        files[key] = {"path": str(f), "sha256": hashlib.sha256(f.read_bytes()).hexdigest()}
    runB = db_base / "2026-05-31-0900"; runB.mkdir(parents=True)
    (runB / "OLD_derived.json").write_text(json.dumps({
        "metadata": {"ticker": "OLD", "managed_rule_ids": ["Q4_FY_MINUS_9M"], "input_files": files},
        "derived_metrics": []}))
    # Analytics loaded: gaap_facts fresh, derive_base pointing at the OLDER run A
    gf = tmp_path / "OLD_gaap_facts.json"; gf.write_text('{"facts": []}')
    gf_sha = hashlib.sha256(gf.read_bytes()).hexdigest()
    an = (vault / "Khouse" / "Semiconductors" / "OLD" / "01_Source" / "SEC Filings"
          / "Skill_Output" / "derive-analytics" / "2026-05-31-1000")
    an.mkdir(parents=True)
    (an / "OLD_analytics.json").write_text(json.dumps({
        "metadata": {"ticker": "OLD", "managed_rule_ids": ["RATIO_GROSS_MARGIN_PCT"],
                     "input_files": {"gaap_facts": {"path": str(gf), "sha256": gf_sha},
                                     "derive_base": {"path": str(a_json), "sha256": a_sha}}},
        "ratio_metrics": [{"cell_id": "r1", "period": "Q1_FY2025", "period_kind": "quarter_duration",
                           "version": "GAAP", "statement": "RATIO", "uni_account": "gross_margin_pct",
                           "provenance": {"rule_id": "RATIO_GROSS_MARGIN_PCT"}}]}))
    monkeypatch.setattr(upsert, "OBSIDIAN_BASE", vault)
    monkeypatch.setattr(upsert, "load_sources", lambda t: {})
    monkeypatch.setattr(upsert, "normalize", lambda t, s: object())
    monkeypatch.setattr(upsert, "print_report", lambda b: True)
    apply_called = {"n": 0}
    monkeypatch.setattr(upsert, "apply", lambda b: apply_called.__setitem__("n", apply_called["n"] + 1))
    monkeypatch.setattr(upsert, "supabase_client", lambda: (_ for _ in ()).throw(AssertionError("no DB before drift gate")))
    monkeypatch.setattr(sys, "argv", ["upsert_sec_financials.py", "OLD", "--apply"])
    with pytest.raises(SystemExit):
        upsert.main()
    assert apply_called["n"] == 0, "apply MUST NOT run when analytics points to an older derive-base run"
