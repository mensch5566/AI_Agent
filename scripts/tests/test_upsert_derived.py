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


def test_missing_run_db_lookup_ignores_ratio_rows(tmp_path, monkeypatch):
    """R8-F2: when checking if Supabase already has derive-base-managed
    metrics, the query must restrict to statement IN ('IS','CF'). RATIO
    rows belong to future derive-analytics scope and must not trigger the
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
        def __init__(self): self._has_isfc = False
        def select(self, *a, **kw): return self
        def eq(self, *a, **kw): return self
        def in_(self, col, vals):
            captured_filters.append((col, tuple(vals)))
            self._has_isfc = (col == "statement" and set(vals) == {"IS", "CF"})
            return self
        def limit(self, *a, **kw): return self
        def execute(self):
            # Only return count > 0 if the IS/CF filter was applied.
            return _StubExec(7 if self._has_isfc else 0)
    class _StubClient:
        def table(self, name): return _StubQuery()
    monkeypatch.setattr(upsert, "supabase_client", lambda: _StubClient())
    monkeypatch.setattr(sys, "argv", ["upsert_sec_financials.py", "RTONLY", "--apply"])

    # With IS/CF filter present, stub returns 7 → exit 4 (gate fires correctly)
    with pytest.raises(SystemExit) as exc:
        upsert.main()
    assert exc.value.code == 4
    # The IS/CF filter must have been applied to the lookup
    assert ("statement", ("IS", "CF")) in captured_filters


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
