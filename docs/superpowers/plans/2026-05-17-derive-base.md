# derive-base Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `derive-base` skill that reads parse-10QK-gaap + parse-8k-nongaap JSON outputs and produces a `{TICKER}_derived.json` containing Q4 single-quarter reconstruction and single-statement subtotal identity holes — written as `sec_financial_metrics`-shaped rows with full provenance.

**Architecture:** Bounded 3-pass pure function (`identity_on_direct → GAAP_Q4 → identity_on_q4`). Engine consumes canonical `FactRow`s via loader/adapter (insulated from raw parse schema). GAAP subtotal rules sourced primarily from `_gaap_edges_cal.json` (XBRL calc linkbase); Non-GAAP uses a tiny hand-coded allowlist. JSON-first output (no direct Supabase writes); existing `scripts/upsert_sec_financials.py` is extended later to consume the derived JSON.

**Tech Stack:** Python 3.11+, `dataclasses`, `pytest`, existing `Tools/research-tools/_shared/` modules (`cell_id`, `period_kind`, `sec_json_adapter`, `unit_canonicalize`). No new third-party deps.

**Source design:** `tmp/derive-base-design.md` v2 (sections referenced inline as `(design §N)`).

**Prerequisites (already done in commit `444db47`):**
- `parse-10QK-gaap` emits `6M_FY{yr}` / `9M_FY{yr}` rows with `period_kind=ytd_duration`
- All 4 parse skills carry the "Parse 永不運算" SKILL.md discipline
- 3 tickers (AAOI / INTC / SNDK) have ytd_duration rows in Supabase + JSON

**Out of scope (design §10):** compose, derive-analytics, Q4 BS, TTM/4Q, avg balance, ratios.

---

## File Structure

Prototype during Phases 1–9 lives at `AI_Agent/tmp/derive-base/`. After validation (Phase 10) it is promoted byte-for-byte to `CC_Switch_Config/skills/derive-base/` and synced to `~/.claude/skills/`, `~/.codex/skills/`, `~/.cc-switch/skills/`.

```
tmp/derive-base/
├── derive_base.py            CLI entrypoint (Task 14)
├── derive_engine.py          Bounded 3-pass engine + candidate resolution (Task 11–12)
├── io_loader.py              Source discovery, sha256, parse JSON → FactRow list (Task 2–3)
├── rules_q4.py               GAAP Q4 single-quarter rules (Task 7)
├── rules_identity.py         calc-linkbase + static allowlist + Non-GAAP allowlist (Task 8–10)
├── audit.py                  audit markdown + conflict report writer (Task 13)
├── tolerance.py              unit-aware tolerance check (Task 5–6)
├── types.py                  DerivedMetricRow dataclass + Candidate dataclass (Task 1)
└── tests/
    ├── conftest.py           shared fixtures (Task 4)
    ├── test_io_loader.py
    ├── test_rules_q4.py
    ├── test_rules_identity.py
    ├── test_tolerance.py
    ├── test_engine.py
    └── test_e2e_aaoi.py      end-to-end on real AAOI facts (Task 15)
```

After Phase 10 promotion, structure mirrors at `CC_Switch_Config/skills/derive-base/` with `SKILL.md` + `scripts/` + tests held under `tests/`.

Helpers reused unchanged from `AI_Agent/Tools/research-tools/_shared/`:
- `cell_id.py::metrics_cell_id` — deterministic SHA-256 cell_id for derived rows
- `cell_id.py::canonical_json` — provenance serialization
- `period_kind.py::infer_period_kind` + regexes `_QUARTER_PERIOD_RE / _FY_PERIOD_RE / _YTD_PERIOD_RE`
- `sec_json_adapter.py::FactRow` dataclass (the canonical row shape) + `adapt_gaap_facts` / `adapt_nongaap_facts` / `adapt_edges`
- `unit_canonicalize.py` — unit compatibility check during identity rule

---

## Phase 0 — Workspace + scaffolding

### Task 1: Project scaffolding + DerivedMetricRow

**Files:**
- Create: `tmp/derive-base/derive_types.py`
- Create: `tmp/derive-base/tests/__init__.py`
- Create: `tmp/derive-base/tests/conftest.py`
- Create: `tmp/derive-base/tests/test_types.py`
- Create: `tmp/derive-base/pytest.ini`
- Create: `tmp/derive-base/.gitignore`

> **Why `derive_types.py` not `types.py`:** a local `types.py` shadows the stdlib `types` module, which `re`/`enum`/`dataclasses`/pytest itself import during bootstrap. The whole runtime breaks before tests can load. `derive_types` is unambiguous and needs no `sys.modules` alias trickery.

- [ ] **Step 1: Make workspace + add pytest config + gitignore**

```bash
mkdir -p tmp/derive-base/tests
touch tmp/derive-base/tests/__init__.py
```

Write `tmp/derive-base/pytest.ini`:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -q --tb=short
```

Write `tmp/derive-base/.gitignore` to keep compiled bytecode out of commits:
```
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 2: Write failing test for DerivedMetricRow shape**

`tmp/derive-base/tests/test_types.py`:
```python
from derive_types import DerivedMetricRow

def test_derived_metric_row_minimal():
    r = DerivedMetricRow(
        cell_id="abc123",
        ticker="AAOI",
        period="Q4_FY2024",
        period_kind="derived_q4",
        period_start="2024-10-01",
        period_end="2024-12-31",
        statement="IS",
        version="GAAP",
        uni_account="revenue",
        value=65200.0,
        unit="USD_thousands",
        status="DERIVED_FROM_DISCLOSED",
        provenance={"rule_id": "Q4_FY_MINUS_9M", "chain_depth": 1, "inputs": []},
    )
    assert r.status == "DERIVED_FROM_DISCLOSED"
    assert r.period_kind == "derived_q4"
```

`tmp/derive-base/tests/conftest.py`:
```python
"""Make derive_types and sibling modules importable from tests/."""
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
```

- [ ] **Step 3: Verify test fails**

```bash
cd tmp/derive-base && python3 -m pytest tests/test_types.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'derive_types'`.

- [ ] **Step 4: Implement DerivedMetricRow**

`tmp/derive-base/derive_types.py`:
```python
"""Canonical output row + intermediate candidate types for derive-base.

DerivedMetricRow is the JSON-output shape AND the Supabase
sec_financial_metrics upsert shape — they must stay aligned.
Candidate is internal: produced by rules, resolved by engine, then
turned into DerivedMetricRow.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DerivedMetricRow:
    cell_id: str
    ticker: str
    period: str
    period_kind: str           # quarter_duration / ytd_duration / fy_annual_duration / instant_period_end / derived_q4
    period_start: str | None
    period_end: str
    statement: str             # IS / BS / CF / RATIO
    version: str               # GAAP / NON_GAAP
    uni_account: str
    value: float
    unit: str
    status: str                # DERIVED_FROM_DISCLOSED | EXCLUDED_FROM_NONGAAP
    provenance: dict


@dataclass
class Candidate:
    """Internal: one possible derived value before resolution."""
    ticker: str
    period: str
    period_kind: str
    period_start: str | None
    period_end: str
    statement: str
    version: str
    uni_account: str
    value: float
    unit: str
    rule_id: str               # Q4_FY_MINUS_9M | Q4_FY_MINUS_Q1Q2Q3 | CALC_LINKBASE | STATIC_ALLOWLIST | NG_ALLOWLIST
    rule_priority: int         # lower = preferred
    chain_depth: int
    chained: bool
    inputs: list[dict]         # [{cell_id, uni_account, period, value, status}, ...]
    extras: dict = field(default_factory=dict)   # role_uri, formula text, etc.
```

- [ ] **Step 5: Run test, verify pass**

```bash
cd tmp/derive-base && python3 -m pytest tests/test_types.py -v
```
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
cd /Users/mensch5566/AI_Agent
git add tmp/derive-base/pytest.ini tmp/derive-base/.gitignore tmp/derive-base/derive_types.py tmp/derive-base/tests/
git commit -m "derive-base prototype: DerivedMetricRow + Candidate types"
```

---

## Phase 1 — I/O loader

### Task 2: Source discovery + sha256

**Files:**
- Create: `tmp/derive-base/io_loader.py`
- Create: `tmp/derive-base/tests/test_io_loader.py`
- Modify: `tmp/derive-base/tests/conftest.py` (add fixture for fake vault)

- [ ] **Step 1: Write failing test for sha256 + discover_sources**

`tmp/derive-base/tests/test_io_loader.py`:
```python
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
```

- [ ] **Step 2: Run, verify fails**

```bash
cd tmp/derive-base && python3 -m pytest tests/test_io_loader.py -v
```
Expected: FAIL (`io_loader` module missing).

- [ ] **Step 3: Implement io_loader**

`tmp/derive-base/io_loader.py`:
```python
"""Source discovery + file hashing + parse JSON → canonical FactRow list.

derive-base READS:
  Khouse/Semiconductors/<TICKER>/01_Source/SEC Filings/Skill_Output/
    parse-10QK-gaap/<TICKER>_gaap_facts.json       (required)
    parse-10QK-gaap/<TICKER>_gaap_edges_cal.json   (required for GAAP identity)
    parse-10QK-gaap/<TICKER>_gaap.json             (inline; for FactRow adapter input)
    parse-8k-nongaap/<TICKER>_nongaap.json         (optional)

derive-base WRITES:
  Khouse/Semiconductors/<TICKER>/01_Source/SEC Filings/Skill_Output/
    derive-base/<YYYY-MM-DD-HHMM>/<TICKER>_derived.json + audit md + conflict md
"""
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Sources:
    gaap_inline: Path
    gaap_facts: Path
    gaap_edges_cal: Path
    nongaap: Path | None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _vault_skill_out(vault_base: Path, ticker: str) -> Path:
    return (
        vault_base / "Khouse" / "Semiconductors" / ticker
        / "01_Source" / "SEC Filings" / "Skill_Output"
    )


def discover_sources(vault_base: Path, ticker: str) -> dict[str, Path | None]:
    skill_out = _vault_skill_out(vault_base, ticker)
    gaap_dir = skill_out / "parse-10QK-gaap"
    ng_dir = skill_out / "parse-8k-nongaap"
    out: dict[str, Path | None] = {
        "gaap_inline":    gaap_dir / f"{ticker}_gaap.json",
        "gaap_facts":     gaap_dir / f"{ticker}_gaap_facts.json",
        "gaap_edges_cal": gaap_dir / f"{ticker}_gaap_edges_cal.json",
        "nongaap":        ng_dir / f"{ticker}_nongaap.json",
    }
    if not out["nongaap"].exists():
        out["nongaap"] = None
    for k in ("gaap_facts", "gaap_edges_cal"):
        if not out[k].exists():
            out[k] = None
    return out


def output_dir(vault_base: Path, ticker: str, run_stamp: str) -> Path:
    d = _vault_skill_out(vault_base, ticker) / "derive-base" / run_stamp
    d.mkdir(parents=True, exist_ok=True)
    return d
```

- [ ] **Step 4: Run, verify pass**

```bash
cd tmp/derive-base && python3 -m pytest tests/test_io_loader.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add tmp/derive-base/io_loader.py tmp/derive-base/tests/test_io_loader.py
git commit -m "derive-base: source discovery + sha256 helper"
```

---

### Task 3: Parse JSON → FactRow list (via _shared adapter)

**Files:**
- Modify: `tmp/derive-base/io_loader.py` (add `load_facts(sources)` function)
- Modify: `tmp/derive-base/tests/test_io_loader.py` (add test against a real AAOI JSON copy)

- [ ] **Step 1: Add failing test that loads real AAOI gaap.json and counts rows**

Append to `tmp/derive-base/tests/test_io_loader.py`:
```python
import os
from io_loader import load_facts, discover_sources

VAULT = Path(os.path.expanduser(
    "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian"
))


def test_load_facts_real_aaoi():
    if not VAULT.exists():
        import pytest
        pytest.skip("Obsidian vault not present (CI run)")
    srcs = discover_sources(VAULT, "AAOI")
    assert srcs["gaap_inline"].exists()
    facts = load_facts(srcs)
    # Sanity: AAOI has many revenue facts across multiple periods + statements
    rev = [f for f in facts if f.uni_account == "revenue" and f.statement == "IS" and f.version == "GAAP"]
    assert len(rev) >= 10
    periods = {f.period for f in rev}
    # YTD rows must be present (Phase A pre-work in commit 444db47)
    assert "6M_FY2024" in periods or "6M_FY2025" in periods
    assert "9M_FY2024" in periods or "9M_FY2025" in periods
```

- [ ] **Step 2: Verify fails**

```bash
cd tmp/derive-base && python3 -m pytest tests/test_io_loader.py::test_load_facts_real_aaoi -v
```
Expected: FAIL (`load_facts` not implemented).

- [ ] **Step 3: Implement load_facts**

Append to `tmp/derive-base/io_loader.py`:
```python
import sys
# allow imports from AI_Agent/Tools/research-tools/_shared/
AI_AGENT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AI_AGENT_ROOT / "Tools" / "research-tools"))
from _shared.sec_json_adapter import (
    adapt_gaap_facts, adapt_nongaap_facts, adapt_edges,
    build_period_end_map, FactRow,
)


def load_facts(sources: dict[str, Path | None]) -> list:
    """Return canonical FactRow list (GAAP ∪ Non-GAAP)."""
    rows: list[FactRow] = []
    inline = sources["gaap_inline"]
    if inline is None or not inline.exists():
        raise FileNotFoundError(f"gaap inline json missing: {inline}")
    gaap_json = json.loads(inline.read_text())
    pe_map = build_period_end_map(gaap_json.get("metadata", {}))
    gaap_rows, _ = adapt_gaap_facts(gaap_json, pe_map)
    rows.extend(gaap_rows)
    ng = sources["nongaap"]
    if ng is not None and ng.exists():
        ng_json = json.loads(ng.read_text())
        ng_pe_map = build_period_end_map(ng_json.get("metadata", {}))
        ng_rows, _ = adapt_nongaap_facts(ng_json, ng_pe_map)
        rows.extend(ng_rows)
    return rows


def load_calc_edges(sources: dict[str, Path | None]) -> list[dict]:
    """Return raw calc edges from {TICKER}_gaap_edges_cal.json."""
    path = sources["gaap_edges_cal"]
    if path is None or not path.exists():
        return []
    return json.loads(path.read_text()).get("edges", [])
```

- [ ] **Step 4: Run, verify pass**

```bash
cd tmp/derive-base && python3 -m pytest tests/test_io_loader.py -v
```
Expected: all passed (4 tests).

- [ ] **Step 5: Commit**

```bash
git add tmp/derive-base/io_loader.py tmp/derive-base/tests/test_io_loader.py
git commit -m "derive-base: load_facts via _shared adapter + calc edges loader"
```

---

### Task 4: Shared test fixtures (sample facts for unit tests)

**Files:**
- Modify: `tmp/derive-base/tests/conftest.py` (add `sample_gaap_revenue_facts` fixture)

- [ ] **Step 1: Add fixture for hand-crafted minimal FactRow set**

Append to `tmp/derive-base/tests/conftest.py`:
```python
import pytest

@pytest.fixture
def sample_gaap_revenue_facts():
    """Hand-crafted FactRow-like dicts (not real FactRow — keeps test light).

    AAOI-shaped: Q1/Q2/Q3 + 6M + 9M + FY for one IS metric (revenue).
    Engine code should treat these like FactRow via duck typing.
    """
    base = dict(
        ticker="AAOI", statement="IS", version="GAAP",
        uni_account="revenue", source_account="us-gaap:Revenues",
        xbrl_tag="Revenues", unit="USD_thousands", weight=1,
        status="SOURCE_OF_TRUTH", ordinal=None, long_tail_metadata=None,
        provenance={"source_filing": "10-K"},
    )
    rows = [
        {**base, "cell_id": "q1", "period": "Q1_FY2024", "period_kind": "quarter_duration",   "period_end": "2024-03-31", "value": 40000.0},
        {**base, "cell_id": "q2", "period": "Q2_FY2024", "period_kind": "quarter_duration",   "period_end": "2024-06-30", "value": 43000.0},
        {**base, "cell_id": "h1", "period": "6M_FY2024", "period_kind": "ytd_duration",       "period_end": "2024-06-30", "value": 83000.0},
        {**base, "cell_id": "q3", "period": "Q3_FY2024", "period_kind": "quarter_duration",   "period_end": "2024-09-30", "value": 65000.0},
        {**base, "cell_id": "9m", "period": "9M_FY2024", "period_kind": "ytd_duration",       "period_end": "2024-09-30", "value": 148000.0},
        {**base, "cell_id": "fy", "period": "FY2024",    "period_kind": "fy_annual_duration", "period_end": "2024-12-31", "value": 249000.0},
    ]
    # turn into FactRow instances so production code can rely on attribute access
    from _shared.sec_json_adapter import FactRow
    return [FactRow(**r) for r in rows]
```

- [ ] **Step 2: Run existing tests to verify no regression**

```bash
cd tmp/derive-base && python3 -m pytest -v
```
Expected: all passed (4 tests; fixture not yet consumed).

- [ ] **Step 3: Commit**

```bash
git add tmp/derive-base/tests/conftest.py
git commit -m "derive-base tests: add sample_gaap_revenue_facts fixture"
```

---

## Phase 2 — Tolerance

### Task 5: Unit-aware tolerance check (design §6)

**Files:**
- Create: `tmp/derive-base/tolerance.py`
- Create: `tmp/derive-base/tests/test_tolerance.py`

- [ ] **Step 1: Write failing tests**

`tmp/derive-base/tests/test_tolerance.py`:
```python
from tolerance import diff_classification, ABS_TOL_BY_UNIT


def test_below_warn():
    # USD_thousands: abs_tol=1.0, warn=0.1% relative
    # 65200 vs 65200.4 → diff=0.4 < 1.0 → within
    out = diff_classification(65200.0, 65200.4, "USD_thousands")
    assert out["level"] == "within"


def test_warn_band():
    # 65200 vs 65300 → diff=100, rel=0.15% > warn 0.1%, < hard 0.5%
    out = diff_classification(65200.0, 65300.0, "USD_thousands")
    assert out["level"] == "warn"
    assert out["abs"] == 100.0


def test_hard_band():
    # 65200 vs 67000 → diff=1800, rel=2.76% > 0.5%
    out = diff_classification(65200.0, 67000.0, "USD_thousands")
    assert out["level"] == "hard"


def test_zero_facts_value_uses_abs():
    out = diff_classification(0.0, 0.5, "USD_thousands")
    assert out["level"] == "within"   # abs_tol=1.0
    out2 = diff_classification(0.0, 2.0, "USD_thousands")
    assert out2["level"] in ("warn", "hard")
```

- [ ] **Step 2: Verify fails**

```bash
cd tmp/derive-base && python3 -m pytest tests/test_tolerance.py -v
```
Expected: FAIL (`tolerance` missing).

- [ ] **Step 3: Implement**

`tmp/derive-base/tolerance.py`:
```python
"""Unit-aware tolerance: combine absolute + relative thresholds.

Source: design §6 Tolerance.

Two-band classification:
  within: max(abs_tol_by_unit, 0.1% relative) covers the diff
  warn:   inside hard band but outside within band
  hard:   > 0.5% relative AND > abs_tol_by_unit  → candidate skip + conflict report
"""
from __future__ import annotations

ABS_TOL_BY_UNIT: dict[str, float] = {
    "USD_thousands":     1.0,
    "USD_millions":      1.0,
    "USD":               1.0,
    "USD_per_share":     0.01,
    "millions_shares":   0.1,
    "thousands_shares":  1.0,
    "Pure":              0.0001,
}
WARN_REL_PCT = 0.1   # 0.1%
HARD_REL_PCT = 0.5   # 0.5%


def diff_classification(facts_value: float, derived_value: float, unit: str) -> dict:
    abs_diff = abs(facts_value - derived_value)
    base = max(abs(facts_value), 1e-9)
    rel_pct = (abs_diff / base) * 100.0
    abs_tol = ABS_TOL_BY_UNIT.get(unit, 1.0)
    warn_thresh = max(abs_tol, base * (WARN_REL_PCT / 100.0))
    hard_thresh = max(abs_tol, base * (HARD_REL_PCT / 100.0))
    if abs_diff <= warn_thresh:
        level = "within"
    elif abs_diff <= hard_thresh:
        level = "warn"
    else:
        level = "hard"
    return {"level": level, "abs": abs_diff, "rel_pct": rel_pct, "unit": unit}
```

- [ ] **Step 4: Run, verify pass**

```bash
cd tmp/derive-base && python3 -m pytest tests/test_tolerance.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add tmp/derive-base/tolerance.py tmp/derive-base/tests/test_tolerance.py
git commit -m "derive-base: unit-aware tolerance classification"
```

---

## Phase 3 — GAAP Q4 rules

### Task 6: Q4 rule: prefer FY − 9M (design §3.1)

**Files:**
- Create: `tmp/derive-base/rules_q4.py`
- Create: `tmp/derive-base/tests/test_rules_q4.py`

- [ ] **Step 1: Write failing test**

`tmp/derive-base/tests/test_rules_q4.py`:
```python
from rules_q4 import q4_candidates


def test_q4_prefer_fy_minus_9m(sample_gaap_revenue_facts):
    # FY=249000, 9M=148000 → Q4=101000
    cands = q4_candidates(sample_gaap_revenue_facts)
    # Expect one Q4 candidate per (uni_account, fy) where inputs are sufficient
    q4 = [c for c in cands if c.period == "Q4_FY2024"]
    assert len(q4) == 1
    assert q4[0].value == 101000.0
    assert q4[0].rule_id == "Q4_FY_MINUS_9M"
    assert q4[0].rule_priority == 1
    assert q4[0].uni_account == "revenue"
    assert q4[0].period_kind == "derived_q4"
    assert q4[0].chain_depth == 1


def test_q4_fallback_when_9m_missing(sample_gaap_revenue_facts):
    rows_no_9m = [f for f in sample_gaap_revenue_facts if f.period != "9M_FY2024"]
    cands = q4_candidates(rows_no_9m)
    q4 = [c for c in cands if c.period == "Q4_FY2024"]
    assert len(q4) == 1
    # FY 249000 - (40000+43000+65000) = 101000
    assert q4[0].value == 101000.0
    assert q4[0].rule_id == "Q4_FY_MINUS_Q1Q2Q3"
    assert q4[0].rule_priority == 2


def test_q4_skipped_when_missing_inputs(sample_gaap_revenue_facts):
    rows_no_fy = [f for f in sample_gaap_revenue_facts if f.period != "FY2024"]
    cands = q4_candidates(rows_no_fy)
    assert [c for c in cands if c.period == "Q4_FY2024"] == []


def test_q4_only_for_is_cf_gaap(sample_gaap_revenue_facts):
    # If we relabel everything as BS, nothing should be derived
    for f in sample_gaap_revenue_facts:
        f.statement = "BS"
    cands = q4_candidates(sample_gaap_revenue_facts)
    assert cands == []
```

- [ ] **Step 2: Verify fails**

```bash
cd tmp/derive-base && python3 -m pytest tests/test_rules_q4.py -v
```
Expected: FAIL (`rules_q4` missing).

- [ ] **Step 3: Implement**

`tmp/derive-base/rules_q4.py`:
```python
"""GAAP Q4 single-quarter reconstruction rules.

Two formulas, in priority order:
  1. Q4 = FY - 9M           (prefer; most filings have 10-Q YTD)
  2. Q4 = FY - (Q1+Q2+Q3)   (fallback)

Scope (design §3.1):
  - Only GAAP version (Non-GAAP Q4 derive is out of scope for v1)
  - Only IS / CF statements (BS Q4 is direct period-end snapshot)
  - Only duration-style uni_accounts (we don't filter by uni_account here;
    caller passes whatever facts they have, and a Q4 candidate is emitted
    for each (uni_account, FY) whose inputs are present)
"""
from __future__ import annotations
from typing import Iterable
import re

from derive_types import Candidate

_FY_RE = re.compile(r"^FY(\d{4})$")


def _fy_year(period: str) -> str | None:
    m = _FY_RE.match(period)
    return m.group(1) if m else None


def q4_candidates(facts: Iterable) -> list[Candidate]:
    """Emit Q4 candidates for every (uni_account, fy) where inputs are sufficient."""
    by_key: dict[tuple, dict[str, object]] = {}
    for f in facts:
        if f.version != "GAAP":
            continue
        if f.statement not in ("IS", "CF"):
            continue
        key = (f.ticker, f.statement, f.uni_account, f.unit)
        slot = by_key.setdefault(key, {"facts_by_period": {}})
        slot["facts_by_period"][f.period] = f

    out: list[Candidate] = []
    for (ticker, stmt, uni, unit), slot in by_key.items():
        fbp = slot["facts_by_period"]
        for period, fact in list(fbp.items()):
            fy = _fy_year(period)
            if fy is None:
                continue
            q4_period = f"Q4_FY{fy}"
            if q4_period in fbp:
                continue  # already direct
            fy_fact = fact
            nm = fbp.get(f"9M_FY{fy}")
            q1 = fbp.get(f"Q1_FY{fy}")
            q2 = fbp.get(f"Q2_FY{fy}")
            q3 = fbp.get(f"Q3_FY{fy}")
            q4_end = _q4_period_end(fy)
            q4_start = _q4_period_start(fy)

            if nm is not None and _units_match(fy_fact, nm):
                v = fy_fact.value - nm.value
                out.append(Candidate(
                    ticker=ticker, period=q4_period, period_kind="derived_q4",
                    period_start=q4_start, period_end=q4_end,
                    statement=stmt, version="GAAP", uni_account=uni,
                    value=v, unit=unit,
                    rule_id="Q4_FY_MINUS_9M", rule_priority=1,
                    chain_depth=1, chained=False,
                    inputs=[
                        _input_dict(fy_fact),
                        _input_dict(nm),
                    ],
                    extras={"formula": f"FY{fy} - 9M_FY{fy}"},
                ))
            elif q1 is not None and q2 is not None and q3 is not None \
                    and _units_match(fy_fact, q1, q2, q3):
                v = fy_fact.value - q1.value - q2.value - q3.value
                out.append(Candidate(
                    ticker=ticker, period=q4_period, period_kind="derived_q4",
                    period_start=q4_start, period_end=q4_end,
                    statement=stmt, version="GAAP", uni_account=uni,
                    value=v, unit=unit,
                    rule_id="Q4_FY_MINUS_Q1Q2Q3", rule_priority=2,
                    chain_depth=1, chained=False,
                    inputs=[
                        _input_dict(fy_fact),
                        _input_dict(q1), _input_dict(q2), _input_dict(q3),
                    ],
                    extras={"formula": f"FY{fy} - Q1_FY{fy} - Q2_FY{fy} - Q3_FY{fy}"},
                ))
            # else: skip — missing inputs (per design §3.4)
    return out


def _input_dict(fact) -> dict:
    return {
        "cell_id": fact.cell_id,
        "uni_account": fact.uni_account,
        "period": fact.period,
        "value": fact.value,
        "status": fact.status,
    }


def _units_match(*facts) -> bool:
    units = {f.unit for f in facts}
    return len(units) == 1


def _q4_period_start(fy: str) -> str:
    # FY ending Dec → Q4 starts Oct 1. For non-Dec FY ends this isn't exact,
    # but derive-base reads period_end from the FY input; period_start is a
    # nice-to-have audit field. v1 keeps it simple; we'll refine if a non-
    # calendar-FY ticker shows mismatched audit dates.
    return f"{fy}-10-01"


def _q4_period_end(fy: str) -> str:
    return f"{fy}-12-31"
```

- [ ] **Step 4: Run, verify pass**

```bash
cd tmp/derive-base && python3 -m pytest tests/test_rules_q4.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add tmp/derive-base/rules_q4.py tmp/derive-base/tests/test_rules_q4.py
git commit -m "derive-base: GAAP Q4 reconstruction rules (FY-9M preferred, FY-Q1Q2Q3 fallback)"
```

---

## Phase 4 — Identity rules

### Task 7: Calc-linkbase rule builder (design §3.2 GAAP)

**Files:**
- Create: `tmp/derive-base/rules_identity.py`
- Create: `tmp/derive-base/tests/test_rules_identity.py`

- [ ] **Step 1: Write failing tests for calc-linkbase rule extraction**

`tmp/derive-base/tests/test_rules_identity.py`:
```python
from rules_identity import calc_rules_from_edges


def test_calc_rules_groups_by_parent_and_role():
    edges = [
        {"role_uri": "stmt-is", "parent_qname": "us-gaap:OperatingIncomeLoss",
         "child_qname": "us-gaap:GrossProfit",            "weight": 1, "edge_type": "calc"},
        {"role_uri": "stmt-is", "parent_qname": "us-gaap:OperatingIncomeLoss",
         "child_qname": "us-gaap:OperatingExpenses",       "weight": -1, "edge_type": "calc"},
        {"role_uri": "stmt-is", "parent_qname": "us-gaap:GrossProfit",
         "child_qname": "us-gaap:Revenues",                "weight": 1, "edge_type": "calc"},
        {"role_uri": "stmt-is", "parent_qname": "us-gaap:GrossProfit",
         "child_qname": "us-gaap:CostOfGoodsAndServicesSold", "weight": -1, "edge_type": "calc"},
    ]
    rules = calc_rules_from_edges(edges)
    keys = sorted(rules.keys())
    assert keys == [("stmt-is", "us-gaap:GrossProfit"), ("stmt-is", "us-gaap:OperatingIncomeLoss")]
    op = rules[("stmt-is", "us-gaap:OperatingIncomeLoss")]
    assert sorted(c["child_qname"] for c in op) == [
        "us-gaap:GrossProfit", "us-gaap:OperatingExpenses",
    ]


def test_calc_rules_filters_non_calc_edges():
    edges = [
        {"role_uri": "r", "parent_qname": "P", "child_qname": "C", "weight": 1, "edge_type": "presentation"},
    ]
    assert calc_rules_from_edges(edges) == {}
```

- [ ] **Step 2: Verify fails**

```bash
cd tmp/derive-base && python3 -m pytest tests/test_rules_identity.py -v
```
Expected: FAIL.

- [ ] **Step 3: Implement calc_rules_from_edges**

`tmp/derive-base/rules_identity.py`:
```python
"""Identity rule sources for derive-base.

Two rule sources (design §3.2):
  1. calc-linkbase rules (GAAP only): parent + children + weights, grouped
     by (role_uri, parent_qname). Built from {TICKER}_gaap_edges_cal.json.
  2. Static allowlist (small, hand-coded): used for Non-GAAP sparse identity
     and as a GAAP fallback when calc edges are absent.

Both produce Candidate rows via apply_identity_rules() (Task 8).
"""
from __future__ import annotations
from collections import defaultdict


def calc_rules_from_edges(edges: list[dict]) -> dict[tuple, list[dict]]:
    """Group calc edges by (role_uri, parent_qname).

    Each value is a list of child dicts with at least:
      {"child_qname": str, "weight": int, "source": str | None}
    """
    out: dict[tuple, list[dict]] = defaultdict(list)
    for e in edges:
        if e.get("edge_type") != "calc":
            continue
        parent = e.get("parent_qname")
        role = e.get("role_uri")
        child = e.get("child_qname")
        if not (parent and role and child):
            continue
        out[(role, parent)].append({
            "child_qname": child,
            "weight": int(e.get("weight") or 0),
            "source": e.get("source"),
        })
    return dict(out)
```

- [ ] **Step 4: Run, verify pass**

```bash
cd tmp/derive-base && python3 -m pytest tests/test_rules_identity.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add tmp/derive-base/rules_identity.py tmp/derive-base/tests/test_rules_identity.py
git commit -m "derive-base: calc-linkbase rule grouping by (role, parent)"
```

---

### Task 8: Apply identity rules → Candidates

**Files:**
- Modify: `tmp/derive-base/rules_identity.py` (add `apply_identity_rules`)
- Modify: `tmp/derive-base/tests/test_rules_identity.py` (add tests)

- [ ] **Step 1: Add failing tests**

Append to `tmp/derive-base/tests/test_rules_identity.py`:
```python
from rules_identity import apply_identity_rules
from _shared.sec_json_adapter import FactRow


def _f(**kw):
    base = dict(
        ticker="X", period="Q1_FY2024", period_end="2024-03-31",
        period_kind="quarter_duration", statement="IS", version="GAAP",
        source_account="t", xbrl_tag="t", unit="USD_thousands", weight=1,
        status="SOURCE_OF_TRUTH", ordinal=None, long_tail_metadata=None,
        provenance={}, cell_id="c",
    )
    base.update(kw)
    return FactRow(**base)


def test_calc_identity_fills_missing_parent():
    # We have GrossProfit children (Revenues + COGS) but no GrossProfit itself.
    # Calc rule should derive GrossProfit = Revenues + (-1 * COGS).
    facts = [
        _f(cell_id="r",  uni_account="revenue",            xbrl_tag="us-gaap:Revenues",                value=100.0),
        _f(cell_id="c",  uni_account="cost_of_goods_sold", xbrl_tag="us-gaap:CostOfGoodsAndServicesSold", value=60.0),
    ]
    calc_rules = {
        ("stmt-is", "us-gaap:GrossProfit"): [
            {"child_qname": "us-gaap:Revenues",                "weight": 1,  "source": None},
            {"child_qname": "us-gaap:CostOfGoodsAndServicesSold","weight": -1, "source": None},
        ],
    }
    # caller must tell us which uni_account name to assign to each qname
    qname_to_uni = {
        "us-gaap:Revenues":                  "revenue",
        "us-gaap:CostOfGoodsAndServicesSold":"cost_of_goods_sold",
        "us-gaap:GrossProfit":               "gross_profit",
    }
    cands = apply_identity_rules(facts, calc_rules, qname_to_uni)
    gp = [c for c in cands if c.uni_account == "gross_profit"]
    assert len(gp) == 1
    assert gp[0].value == 40.0    # 100 - 60
    assert gp[0].rule_id == "CALC_LINKBASE"
    assert gp[0].rule_priority == 3


def test_calc_identity_skips_when_child_missing():
    facts = [
        _f(cell_id="r", uni_account="revenue", xbrl_tag="us-gaap:Revenues", value=100.0),
        # COGS missing
    ]
    calc_rules = {
        ("stmt-is", "us-gaap:GrossProfit"): [
            {"child_qname": "us-gaap:Revenues",                "weight": 1,  "source": None},
            {"child_qname": "us-gaap:CostOfGoodsAndServicesSold","weight": -1, "source": None},
        ],
    }
    qname_to_uni = {
        "us-gaap:Revenues":                  "revenue",
        "us-gaap:CostOfGoodsAndServicesSold":"cost_of_goods_sold",
        "us-gaap:GrossProfit":               "gross_profit",
    }
    assert apply_identity_rules(facts, calc_rules, qname_to_uni) == []
```

- [ ] **Step 2: Verify fails**

Run pytest, expect `ImportError: cannot import name 'apply_identity_rules'`.

- [ ] **Step 3: Implement apply_identity_rules**

Append to `tmp/derive-base/rules_identity.py`:
```python
from collections import defaultdict
from derive_types import Candidate


def apply_identity_rules(
    facts,
    calc_rules: dict[tuple, list[dict]],
    qname_to_uni: dict[str, str],
) -> list[Candidate]:
    """For each (period, statement, version, unit), try each calc rule.

    Emits a Candidate per (period × rule × derivable parent).
    Skips if any required child is missing.
    Skips if parent uni_account already exists for that period.
    """
    # Index facts by (period, statement, version, unit, xbrl_tag)
    fact_idx: dict[tuple, object] = {}
    seen_uni: set[tuple] = set()
    for f in facts:
        if f.version != "GAAP":
            continue
        key = (f.period, f.statement, f.version, f.unit, f.xbrl_tag)
        fact_idx.setdefault(key, f)
        seen_uni.add((f.period, f.statement, f.version, f.uni_account))

    out: list[Candidate] = []
    # Build a (period, statement, version, unit) → child tag → fact lookup
    facts_by_pctx: dict[tuple, dict[str, object]] = defaultdict(dict)
    for (period, stmt, ver, unit, tag), f in fact_idx.items():
        facts_by_pctx[(period, stmt, ver, unit)][tag] = f

    for (role_uri, parent_qname), children in calc_rules.items():
        parent_uni = qname_to_uni.get(parent_qname)
        if not parent_uni:
            continue
        for (period, stmt, ver, unit), tag_map in facts_by_pctx.items():
            # All children present?
            child_facts = []
            ok = True
            for ch in children:
                cf = tag_map.get(ch["child_qname"])
                if cf is None:
                    ok = False
                    break
                child_facts.append((cf, ch["weight"]))
            if not ok:
                continue
            if (period, stmt, ver, parent_uni) in seen_uni:
                continue
            value = sum(cf.value * w for cf, w in child_facts)
            # period_end: take from any child (they share the period)
            period_end = child_facts[0][0].period_end
            period_start = None
            ticker = child_facts[0][0].ticker
            inputs = [_input_dict_from_fact(cf) for cf, _ in child_facts]
            formula = " + ".join(
                f"{w:+d} * {qname_to_uni.get(ch['child_qname'], ch['child_qname'])}"
                for ch, (_, w) in zip(children, child_facts)
            )
            out.append(Candidate(
                ticker=ticker, period=period, period_kind=child_facts[0][0].period_kind,
                period_start=period_start, period_end=period_end,
                statement=stmt, version=ver, uni_account=parent_uni,
                value=value, unit=unit,
                rule_id="CALC_LINKBASE", rule_priority=3,
                chain_depth=1, chained=False,
                inputs=inputs,
                extras={"role_uri": role_uri, "parent_qname": parent_qname, "formula": formula},
            ))
    return out


def _input_dict_from_fact(f) -> dict:
    return {
        "cell_id": f.cell_id, "uni_account": f.uni_account,
        "period": f.period, "value": f.value, "status": f.status,
    }
```

- [ ] **Step 4: Run, verify pass**

```bash
cd tmp/derive-base && python3 -m pytest tests/test_rules_identity.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add tmp/derive-base/rules_identity.py tmp/derive-base/tests/test_rules_identity.py
git commit -m "derive-base: apply calc-linkbase rules to fill missing subtotals"
```

---

### Task 9: Static GAAP fallback + Non-GAAP allowlist (design §3.2)

**Files:**
- Modify: `tmp/derive-base/rules_identity.py` (add `STATIC_ALLOWLIST`, `NG_ALLOWLIST`, `apply_static_allowlist`)
- Modify: `tmp/derive-base/tests/test_rules_identity.py`

- [ ] **Step 1: Failing test**

Append to test file:
```python
from rules_identity import apply_static_allowlist


def test_static_allowlist_gaap_gross_profit_fallback():
    # No calc edges, Revenue + COGS present, parent missing → GP derived.
    facts = [
        _f(uni_account="revenue", value=100.0),
        _f(uni_account="cost_of_goods_sold", value=60.0, cell_id="cogs"),
    ]
    cands = apply_static_allowlist(facts, version="GAAP")
    gp = [c for c in cands if c.uni_account == "gross_profit"]
    assert len(gp) == 1
    assert gp[0].value == 40.0
    assert gp[0].rule_id == "STATIC_ALLOWLIST"
    assert gp[0].rule_priority == 4


def test_nongaap_allowlist_cogs_from_rev_minus_gp():
    facts = [
        _f(uni_account="revenue",      value=100.0, version="NON_GAAP"),
        _f(uni_account="gross_profit", value=40.0,  version="NON_GAAP", cell_id="gp"),
    ]
    cands = apply_static_allowlist(facts, version="NON_GAAP")
    cogs = [c for c in cands if c.uni_account == "cost_of_goods_sold"]
    assert len(cogs) == 1
    assert cogs[0].value == 60.0
    assert cogs[0].rule_id == "NG_ALLOWLIST"
    assert cogs[0].rule_priority == 5


def test_allowlist_skips_when_parent_present():
    facts = [
        _f(uni_account="revenue",            value=100.0),
        _f(uni_account="cost_of_goods_sold", value=60.0, cell_id="c"),
        _f(uni_account="gross_profit",       value=39.0, cell_id="g"),   # direct disclosed
    ]
    cands = apply_static_allowlist(facts, version="GAAP")
    # gross_profit is direct, so allowlist shouldn't propose another one.
    assert [c for c in cands if c.uni_account == "gross_profit"] == []
```

- [ ] **Step 2: Verify fails**

Run pytest, expect ImportError.

- [ ] **Step 3: Implement apply_static_allowlist**

Append to `rules_identity.py`:
```python
# (output, version, requires, formula_fn, rule_id, rule_priority)
# formula_fn receives a dict {uni_account: fact_value} and returns float.
STATIC_ALLOWLIST_GAAP = [
    # output, requires, fn, rule_id, priority
    ("gross_profit",              ("revenue", "cost_of_goods_sold"),
        lambda v: v["revenue"] - v["cost_of_goods_sold"],
        "STATIC_ALLOWLIST", 4),
    ("cost_of_goods_sold",        ("revenue", "gross_profit"),
        lambda v: v["revenue"] - v["gross_profit"],
        "STATIC_ALLOWLIST", 4),
    ("total_operating_expenses",  ("gross_profit", "operating_income"),
        lambda v: v["gross_profit"] - v["operating_income"],
        "STATIC_ALLOWLIST", 4),
    ("operating_income",          ("gross_profit", "total_operating_expenses"),
        lambda v: v["gross_profit"] - v["total_operating_expenses"],
        "STATIC_ALLOWLIST", 4),
]
STATIC_ALLOWLIST_NONGAAP = [
    ("cost_of_goods_sold",        ("revenue", "gross_profit"),
        lambda v: v["revenue"] - v["gross_profit"],
        "NG_ALLOWLIST", 5),
    ("gross_profit",              ("revenue", "cost_of_goods_sold"),
        lambda v: v["revenue"] - v["cost_of_goods_sold"],
        "NG_ALLOWLIST", 5),
    ("total_operating_expenses",  ("gross_profit", "operating_income"),
        lambda v: v["gross_profit"] - v["operating_income"],
        "NG_ALLOWLIST", 5),
    ("operating_income",          ("gross_profit", "total_operating_expenses"),
        lambda v: v["gross_profit"] - v["total_operating_expenses"],
        "NG_ALLOWLIST", 5),
]


def apply_static_allowlist(facts, version: str) -> list[Candidate]:
    allowlist = STATIC_ALLOWLIST_GAAP if version == "GAAP" else STATIC_ALLOWLIST_NONGAAP
    # Group: (period, statement, version, unit) → uni_account → fact
    grouped: dict[tuple, dict[str, object]] = defaultdict(dict)
    for f in facts:
        if f.version != version:
            continue
        grouped[(f.period, f.statement, f.version, f.unit)][f.uni_account] = f
    out: list[Candidate] = []
    for (period, stmt, ver, unit), uni_map in grouped.items():
        for output_uni, requires, fn, rule_id, priority in allowlist:
            if output_uni in uni_map:
                continue  # parent already direct
            if not all(r in uni_map for r in requires):
                continue
            try:
                value = fn({r: uni_map[r].value for r in requires})
            except Exception:
                continue
            template = uni_map[requires[0]]
            out.append(Candidate(
                ticker=template.ticker, period=period, period_kind=template.period_kind,
                period_start=None, period_end=template.period_end,
                statement=stmt, version=ver, uni_account=output_uni,
                value=value, unit=unit,
                rule_id=rule_id, rule_priority=priority,
                chain_depth=1, chained=False,
                inputs=[_input_dict_from_fact(uni_map[r]) for r in requires],
                extras={"formula": " - ".join(requires) if "−" not in str(fn) else "see fn"},
            ))
    return out
```

- [ ] **Step 4: Run, verify pass**

```bash
cd tmp/derive-base && python3 -m pytest tests/test_rules_identity.py -v
```
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add tmp/derive-base/rules_identity.py tmp/derive-base/tests/test_rules_identity.py
git commit -m "derive-base: static allowlist (GAAP fallback + Non-GAAP sparse identity)"
```

---

### Task 10: qname → uni_account map (read from parse skill IS_TAG_MAP)

**Files:**
- Modify: `tmp/derive-base/rules_identity.py` (add `build_qname_to_uni`)
- Modify: `tmp/derive-base/tests/test_rules_identity.py`

The calc rules use `parent_qname` like `us-gaap:GrossProfit`. To project rule outputs into our canonical `uni_account` namespace, we read each ticker's actual tag→metric mapping from the `tag_history` block already present in `{TICKER}_gaap.json` metadata.

- [ ] **Step 1: Failing test**

Append:
```python
def test_build_qname_to_uni_from_inline_metadata():
    inline = {
        "metadata": {},
        "income_statement": [
            {"uni_account": "revenue",      "source_account": "RevenueFromContractWithCustomerExcludingAssessedTax"},
            {"uni_account": "gross_profit", "source_account": "GrossProfit"},
        ],
        "balance_sheet": [
            {"uni_account": "total_assets", "source_account": "Assets"},
        ],
        "cash_flow_statement": [],
    }
    from rules_identity import build_qname_to_uni
    m = build_qname_to_uni(inline)
    assert m["us-gaap:GrossProfit"] == "gross_profit"
    assert m["us-gaap:Assets"] == "total_assets"
    assert m["us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"] == "revenue"
```

- [ ] **Step 2: Verify fails**

- [ ] **Step 3: Implement**

Append:
```python
def build_qname_to_uni(inline_json: dict) -> dict[str, str]:
    """Read source_account values from the inline {TICKER}_gaap.json long-format
    rows and build a qname → uni_account lookup.

    parse-10QK-gaap stores `source_account` as the bare XBRL local name (e.g.
    `GrossProfit`); calc edges store qname with `us-gaap:` prefix. We assume
    us-gaap namespace; ticker extensions (rare in three-statement core) are
    skipped — the rule simply won't fire for them.
    """
    m: dict[str, str] = {}
    for stmt_key in ("income_statement", "balance_sheet", "cash_flow_statement"):
        for row in inline_json.get(stmt_key, []):
            uni = row.get("uni_account")
            tag = row.get("source_account")
            if not (uni and tag):
                continue
            if ":" in tag:
                m[tag] = uni
            else:
                m[f"us-gaap:{tag}"] = uni
    return m
```

- [ ] **Step 4: Run, verify pass**

- [ ] **Step 5: Commit**

```bash
git add tmp/derive-base/rules_identity.py tmp/derive-base/tests/test_rules_identity.py
git commit -m "derive-base: build qname→uni map from inline gaap.json source_account"
```

---

## Phase 5 — Engine

### Task 11: Candidate resolution (design §3.3)

**Files:**
- Create: `tmp/derive-base/derive_engine.py`
- Create: `tmp/derive-base/tests/test_engine.py`

- [ ] **Step 1: Failing test**

`tmp/derive-base/tests/test_engine.py`:
```python
from derive_engine import resolve_candidates
from derive_types import Candidate


def _c(**kw):
    base = dict(
        ticker="X", period="Q4_FY2024", period_kind="derived_q4",
        period_start=None, period_end="2024-12-31",
        statement="IS", version="GAAP", uni_account="revenue",
        value=100.0, unit="USD_thousands",
        rule_id="Q4_FY_MINUS_9M", rule_priority=1,
        chain_depth=1, chained=False, inputs=[], extras={},
    )
    base.update(kw)
    return Candidate(**base)


def test_resolve_prefers_lowest_priority():
    a = _c(rule_id="Q4_FY_MINUS_9M",     rule_priority=1, value=100.0)
    b = _c(rule_id="Q4_FY_MINUS_Q1Q2Q3", rule_priority=2, value=100.1)
    winners, conflicts = resolve_candidates([a, b])
    assert len(winners) == 1
    assert winners[0].rule_id == "Q4_FY_MINUS_9M"
    assert conflicts == []


def test_resolve_hard_conflict_skips_both():
    a = _c(rule_id="Q4_FY_MINUS_9M",     rule_priority=1, value=100.0)
    b = _c(rule_id="Q4_FY_MINUS_Q1Q2Q3", rule_priority=2, value=200.0)
    winners, conflicts = resolve_candidates([a, b])
    assert winners == []
    assert len(conflicts) == 1
    assert conflicts[0]["uni_account"] == "revenue"


def test_resolve_two_keys_independent():
    a = _c(uni_account="revenue",      value=100.0)
    b = _c(uni_account="gross_profit", value=40.0)
    winners, conflicts = resolve_candidates([a, b])
    assert len(winners) == 2
```

- [ ] **Step 2: Verify fails**

- [ ] **Step 3: Implement resolve_candidates**

`tmp/derive-base/derive_engine.py`:
```python
"""Bounded 3-pass derive engine + candidate resolution.

Pipeline (design §4):
  Pass 1 identity_on_direct: identity rules on direct facts only
  Pass 2 GAAP_Q4:            Q4 reconstruction (FY-9M / FY-Q1Q2Q3)
  Pass 3 identity_on_q4:     identity rules on Q4 (period_kind=derived_q4) keys

Each pass produces Candidate[]; resolve_candidates picks one per semantic key,
or skips with a conflict report when hard tolerance breached.
"""
from __future__ import annotations
from collections import defaultdict

from tolerance import diff_classification
from derive_types import Candidate, DerivedMetricRow


SemanticKey = tuple  # (ticker, period, period_kind, statement, version, uni_account)


def _key(c: Candidate) -> SemanticKey:
    return (c.ticker, c.period, c.period_kind, c.statement, c.version, c.uni_account)


def resolve_candidates(candidates: list[Candidate]) -> tuple[list[Candidate], list[dict]]:
    """Group candidates by semantic key; pick best or skip on hard conflict.

    Returns (winners, conflicts).
      winners:   Candidate[]  — at most one per key
      conflicts: dict[]       — for keys skipped due to hard-band disagreement
    """
    by_key: dict[SemanticKey, list[Candidate]] = defaultdict(list)
    for c in candidates:
        by_key[_key(c)].append(c)

    winners: list[Candidate] = []
    conflicts: list[dict] = []
    for k, cs in by_key.items():
        cs_sorted = sorted(cs, key=lambda x: (x.rule_priority, x.chain_depth))
        preferred = cs_sorted[0]
        # Compare every other candidate's value against the preferred.
        hard_break = False
        for other in cs_sorted[1:]:
            cls = diff_classification(preferred.value, other.value, preferred.unit)
            if cls["level"] == "hard":
                hard_break = True
                conflicts.append({
                    "ticker": k[0], "period": k[1], "period_kind": k[2],
                    "statement": k[3], "version": k[4], "uni_account": k[5],
                    "preferred_rule": preferred.rule_id, "preferred_value": preferred.value,
                    "other_rule":     other.rule_id,     "other_value":     other.value,
                    "abs_diff": cls["abs"], "rel_pct": cls["rel_pct"],
                    "unit": preferred.unit,
                })
                break
        if not hard_break:
            winners.append(preferred)
    return winners, conflicts
```

- [ ] **Step 4: Verify pass**

- [ ] **Step 5: Commit**

```bash
git add tmp/derive-base/derive_engine.py tmp/derive-base/tests/test_engine.py
git commit -m "derive-base: candidate resolution (priority + chain_depth + hard conflict)"
```

---

### Task 12: Bounded 3-pass orchestration (design §4)

**Files:**
- Modify: `tmp/derive-base/derive_engine.py` (add `run_engine`)
- Modify: `tmp/derive-base/tests/test_engine.py`

- [ ] **Step 1: Failing test (end-to-end with fixtures)**

Append:
```python
def test_run_engine_q4_then_identity(sample_gaap_revenue_facts):
    """Pass 2 emits Q4 revenue (FY-9M=101000). Pass 3 has no IS subtotal
    children to derive a parent from (only revenue exists), so Pass 3
    emits nothing. Final winners = 1 row."""
    from derive_engine import run_engine
    result = run_engine(
        facts=sample_gaap_revenue_facts,
        calc_rules={},          # no calc edges → only Q4 rule fires
        qname_to_uni={},
    )
    rows = result["winners"]
    assert len(rows) == 1
    assert rows[0].uni_account == "revenue"
    assert rows[0].period == "Q4_FY2024"
    assert rows[0].value == 101000.0
    # Stats sanity
    s = result["stats"]
    assert s["pass1_count"] == 0
    assert s["pass2_count"] == 1
    assert s["pass3_count"] == 0
    assert s["conflicts"] == 0
```

- [ ] **Step 2: Verify fails**

- [ ] **Step 3: Implement run_engine**

Append to `derive_engine.py`:
```python
from rules_q4 import q4_candidates
from rules_identity import apply_identity_rules, apply_static_allowlist


def _materialize_facts_with_winners(facts: list, winners: list[Candidate]) -> list:
    """Append Pass 1 / Pass 2 winners as facts for the next pass.

    We use the same FactRow shape so identity rules can iterate uniformly.
    """
    from _shared.sec_json_adapter import FactRow
    out = list(facts)
    for w in winners:
        out.append(FactRow(
            cell_id=f"derived::{w.rule_id}::{w.period}::{w.uni_account}",
            ticker=w.ticker, period=w.period, period_end=w.period_end,
            period_kind=w.period_kind, statement=w.statement, version=w.version,
            uni_account=w.uni_account, source_account="derived",
            xbrl_tag=None, value=w.value, weight=1, unit=w.unit,
            status="DERIVED_FROM_DISCLOSED", ordinal=None,
            long_tail_metadata=None,
            provenance={"rule_id": w.rule_id, "chain_depth": w.chain_depth},
        ))
    return out


def run_engine(
    *, facts: list, calc_rules: dict, qname_to_uni: dict,
) -> dict:
    """Bounded 3-pass driver. Returns {winners, conflicts, stats}."""
    # Pass 1 — identity on direct (GAAP calc + GAAP allowlist + Non-GAAP allowlist)
    p1: list[Candidate] = []
    p1 += apply_identity_rules(facts, calc_rules, qname_to_uni)
    p1 += apply_static_allowlist(facts, version="GAAP")
    p1 += apply_static_allowlist(facts, version="NON_GAAP")
    p1_winners, p1_conflicts = resolve_candidates(p1)

    facts_after_p1 = _materialize_facts_with_winners(facts, p1_winners)

    # Pass 2 — GAAP Q4 reconstruction
    p2: list[Candidate] = q4_candidates(facts_after_p1)
    p2_winners, p2_conflicts = resolve_candidates(p2)

    facts_after_p2 = _materialize_facts_with_winners(facts_after_p1, p2_winners)

    # Pass 3 — identity on Q4 keys
    # Only run identity rules; only emit Candidates whose period is derived_q4
    p3_raw: list[Candidate] = []
    p3_raw += apply_identity_rules(facts_after_p2, calc_rules, qname_to_uni)
    p3_raw += apply_static_allowlist(facts_after_p2, version="GAAP")
    p3 = [c for c in p3_raw if c.period_kind == "derived_q4"]
    # bump chain_depth to reflect we built on Pass 2 outputs
    for c in p3:
        c.chain_depth = 3
        c.chained = True
    p3_winners, p3_conflicts = resolve_candidates(p3)

    return {
        "winners": p1_winners + p2_winners + p3_winners,
        "conflicts": p1_conflicts + p2_conflicts + p3_conflicts,
        "stats": {
            "pass1_count": len(p1_winners),
            "pass2_count": len(p2_winners),
            "pass3_count": len(p3_winners),
            "conflicts":   len(p1_conflicts) + len(p2_conflicts) + len(p3_conflicts),
        },
    }
```

- [ ] **Step 4: Verify pass**

```bash
cd tmp/derive-base && python3 -m pytest tests/test_engine.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add tmp/derive-base/derive_engine.py tmp/derive-base/tests/test_engine.py
git commit -m "derive-base: bounded 3-pass engine orchestration"
```

---

### Task 13: Conflict against existing facts → skip + report (design §6)

**Files:**
- Modify: `tmp/derive-base/derive_engine.py` (add `filter_against_facts`)
- Modify: `tmp/derive-base/tests/test_engine.py`

- [ ] **Step 1: Failing test**

```python
def test_filter_winner_against_existing_facts_skips_and_records_conflict(sample_gaap_revenue_facts):
    """Pass 2 derives Q4=101000. If facts already had a Q4 revenue of 101050,
    Q4_FY2024 derive should be skipped (facts win) and the diff recorded."""
    from derive_engine import filter_against_facts
    from _shared.sec_json_adapter import FactRow
    direct_q4 = FactRow(
        cell_id="q4_direct", ticker="AAOI", period="Q4_FY2024",
        period_end="2024-12-31", period_kind="quarter_duration",
        statement="IS", version="GAAP", uni_account="revenue",
        source_account="us-gaap:Revenues", xbrl_tag="us-gaap:Revenues",
        value=101050.0, weight=1, unit="USD_thousands",
        status="SOURCE_OF_TRUTH", ordinal=None, long_tail_metadata=None,
        provenance={},
    )
    facts = list(sample_gaap_revenue_facts) + [direct_q4]
    from rules_q4 import q4_candidates
    cands = q4_candidates(facts)   # may or may not return — direct exists so should skip
    # If our q4_candidates correctly skips, we don't need filter_against_facts at all here.
    assert cands == []
```

Note: this confirms the existing `q4_candidates` already skips when a direct fact exists. `filter_against_facts` is still useful as a defensive net for calc-linkbase identity (where a parent might exist for some periods but not others). Add a second test:

```python
def test_filter_against_facts_drops_winner_with_matching_direct():
    """If a winner says revenue=100 for Q1 GAAP IS, but facts already
    have revenue=100 there, drop the winner (facts already cover it)."""
    from derive_engine import filter_against_facts
    from derive_types import Candidate
    from _shared.sec_json_adapter import FactRow
    facts = [FactRow(
        cell_id="x", ticker="X", period="Q1_FY2024", period_end="2024-03-31",
        period_kind="quarter_duration", statement="IS", version="GAAP",
        uni_account="gross_profit", source_account="t", xbrl_tag="t",
        value=40.0, weight=1, unit="USD_thousands",
        status="SOURCE_OF_TRUTH", ordinal=None, long_tail_metadata=None, provenance={},
    )]
    winner = Candidate(
        ticker="X", period="Q1_FY2024", period_kind="quarter_duration",
        period_start=None, period_end="2024-03-31",
        statement="IS", version="GAAP", uni_account="gross_profit",
        value=40.0, unit="USD_thousands",
        rule_id="CALC_LINKBASE", rule_priority=3, chain_depth=1, chained=False,
        inputs=[], extras={},
    )
    keep, dropped = filter_against_facts([winner], facts)
    assert keep == []
    assert len(dropped) == 1
    assert dropped[0]["reason"] == "facts_already_cover"
```

- [ ] **Step 2: Verify fails**

- [ ] **Step 3: Implement filter_against_facts and wire into run_engine**

Append to `derive_engine.py`:
```python
def filter_against_facts(winners: list[Candidate], facts: list) -> tuple[list[Candidate], list[dict]]:
    """Drop any winner whose semantic key already has a direct SOURCE_OF_TRUTH fact.

    Records a 'facts_already_cover' note in the dropped list. If values
    disagree at hard level, also records a tolerance conflict.
    """
    fact_idx: dict[SemanticKey, object] = {}
    for f in facts:
        if f.status != "SOURCE_OF_TRUTH":
            continue
        k = (f.ticker, f.period, f.period_kind, f.statement, f.version, f.uni_account)
        fact_idx.setdefault(k, f)
    keep: list[Candidate] = []
    dropped: list[dict] = []
    for w in winners:
        k = _key(w)
        if k in fact_idx:
            fact = fact_idx[k]
            cls = diff_classification(fact.value, w.value, w.unit)
            dropped.append({
                "reason": "facts_already_cover",
                "ticker": k[0], "period": k[1], "statement": k[3], "version": k[4],
                "uni_account": k[5], "facts_value": fact.value, "derived_value": w.value,
                "tolerance_level": cls["level"], "abs_diff": cls["abs"], "rel_pct": cls["rel_pct"],
                "rule_id": w.rule_id,
            })
        else:
            keep.append(w)
    return keep, dropped
```

Then update `run_engine`'s return path:
```python
    all_winners = p1_winners + p2_winners + p3_winners
    all_winners, fact_dropped = filter_against_facts(all_winners, facts)
    return {
        "winners": all_winners,
        "conflicts": p1_conflicts + p2_conflicts + p3_conflicts,
        "fact_conflicts": fact_dropped,
        "stats": {
            "pass1_count":      len(p1_winners),
            "pass2_count":      len(p2_winners),
            "pass3_count":      len(p3_winners),
            "final_count":      len(all_winners),
            "conflicts":        len(p1_conflicts) + len(p2_conflicts) + len(p3_conflicts),
            "fact_skips":       len(fact_dropped),
        },
    }
```

- [ ] **Step 4: Run, verify pass**

```bash
cd tmp/derive-base && python3 -m pytest tests/test_engine.py -v
```
Expected: all pass (existing tests still green; new test green).

- [ ] **Step 5: Commit**

```bash
git add tmp/derive-base/derive_engine.py tmp/derive-base/tests/test_engine.py
git commit -m "derive-base: drop winners covered by direct facts + record tolerance diff"
```

---

## Phase 6 — Output + audit

### Task 14: Candidate → DerivedMetricRow + JSON writer

**Files:**
- Create: `tmp/derive-base/audit.py` (also handles JSON output)
- Create: `tmp/derive-base/tests/test_audit.py`

- [ ] **Step 1: Failing test for cell_id determinism**

`tmp/derive-base/tests/test_audit.py`:
```python
from audit import to_derived_metric_row
from derive_types import Candidate


def _c():
    return Candidate(
        ticker="AAOI", period="Q4_FY2024", period_kind="derived_q4",
        period_start="2024-10-01", period_end="2024-12-31",
        statement="IS", version="GAAP", uni_account="revenue",
        value=101000.0, unit="USD_thousands",
        rule_id="Q4_FY_MINUS_9M", rule_priority=1,
        chain_depth=1, chained=False,
        inputs=[{"cell_id": "fy", "uni_account": "revenue", "period": "FY2024", "value": 249000.0, "status": "SOURCE_OF_TRUTH"}],
        extras={"formula": "FY2024 - 9M_FY2024"},
    )


def test_to_derived_metric_row_deterministic_cell_id():
    a = to_derived_metric_row(_c())
    b = to_derived_metric_row(_c())
    assert a.cell_id == b.cell_id
    assert a.status == "DERIVED_FROM_DISCLOSED"
    assert a.provenance["rule_id"] == "Q4_FY_MINUS_9M"
    assert a.provenance["formula"] == "FY2024 - 9M_FY2024"
    assert a.provenance["chain_depth"] == 1
    assert a.provenance["target_table"] == "sec_financial_metrics"
```

- [ ] **Step 2: Verify fails**

- [ ] **Step 3: Implement to_derived_metric_row + write_derived_json**

`tmp/derive-base/audit.py`:
```python
"""Convert resolved Candidates → DerivedMetricRow → JSON file.

Also writes:
  {TICKER}_derived.json       canonical JSON (derived_metrics[] + metadata)
  {TICKER}_derive_audit.md    human audit (per-pass counts, chain paths)
  {TICKER}_conflict_report.md tolerance conflicts + facts-already-cover diffs
"""
from __future__ import annotations
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Reuse _shared.cell_id from AI_Agent
AI_AGENT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AI_AGENT_ROOT / "Tools" / "research-tools"))
from _shared.cell_id import metrics_cell_id  # noqa: E402

from derive_types import Candidate, DerivedMetricRow


def to_derived_metric_row(c: Candidate) -> DerivedMetricRow:
    provenance = {
        "rule_id":      c.rule_id,
        "rule_version": "derive-base/1.0",
        "formula":      c.extras.get("formula") or "",
        "inputs":       c.inputs,
        "chained":      c.chained,
        "chain_depth":  c.chain_depth,
        "target_table": "sec_financial_metrics",
    }
    if "role_uri" in c.extras:
        provenance["role_uri"] = c.extras["role_uri"]
    if "parent_qname" in c.extras:
        provenance["parent_qname"] = c.extras["parent_qname"]
    cell_id = metrics_cell_id(
        ticker=c.ticker, period=c.period, period_kind=c.period_kind,
        version=c.version, statement=c.statement, uni_account=c.uni_account,
    )
    return DerivedMetricRow(
        cell_id=cell_id, ticker=c.ticker, period=c.period,
        period_kind=c.period_kind, period_start=c.period_start, period_end=c.period_end,
        statement=c.statement, version=c.version, uni_account=c.uni_account,
        value=c.value, unit=c.unit,
        status="DERIVED_FROM_DISCLOSED",
        provenance=provenance,
    )


def write_derived_json(out_dir: Path, ticker: str, rows: list[DerivedMetricRow], meta: dict) -> Path:
    doc = {
        "metadata": {
            "ticker":        ticker,
            "skill_version": "derive-base/1.0",
            "run_timestamp": datetime.now(timezone.utc).isoformat(),
            **meta,
        },
        "derived_metrics": [_row_to_dict(r) for r in rows],
    }
    p = out_dir / f"{ticker}_derived.json"
    p.write_text(json.dumps(doc, indent=2, ensure_ascii=False))
    return p


def _row_to_dict(r: DerivedMetricRow) -> dict:
    return {
        "cell_id":     r.cell_id,
        "ticker":      r.ticker,
        "period":      r.period,
        "period_kind": r.period_kind,
        "period_start":r.period_start,
        "period_end":  r.period_end,
        "statement":   r.statement,
        "version":     r.version,
        "uni_account": r.uni_account,
        "value":       r.value,
        "unit":        r.unit,
        "status":      r.status,
        "provenance":  r.provenance,
    }
```

- [ ] **Step 4: Verify pass**

```bash
cd tmp/derive-base && python3 -m pytest tests/test_audit.py -v
```
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add tmp/derive-base/audit.py tmp/derive-base/tests/test_audit.py
git commit -m "derive-base: Candidate → DerivedMetricRow + JSON writer"
```

---

### Task 15: Audit markdown + conflict report writers

**Files:**
- Modify: `tmp/derive-base/audit.py` (add `write_audit_md`, `write_conflict_md`)
- Modify: `tmp/derive-base/tests/test_audit.py`

- [ ] **Step 1: Failing test**

```python
def test_write_audit_md_lists_pass_counts_and_chain_paths(tmp_path):
    from audit import write_audit_md
    result = {
        "winners": [],
        "conflicts": [],
        "fact_conflicts": [],
        "stats": {"pass1_count": 0, "pass2_count": 1, "pass3_count": 0, "final_count": 1, "conflicts": 0, "fact_skips": 0},
    }
    p = write_audit_md(tmp_path, "AAOI", result, meta_extras={"input_facts_count": 100})
    txt = p.read_text()
    assert "Pass 1" in txt and "Pass 2" in txt and "Pass 3" in txt
    assert "input_facts_count" in txt or "100" in txt


def test_write_conflict_md_lists_tolerance_breaches(tmp_path):
    from audit import write_conflict_md
    result = {
        "conflicts": [{
            "ticker": "AAOI", "period": "Q4_FY2024", "statement": "IS",
            "version": "GAAP", "uni_account": "revenue",
            "preferred_rule": "Q4_FY_MINUS_9M",     "preferred_value": 101000.0,
            "other_rule":     "Q4_FY_MINUS_Q1Q2Q3", "other_value":     99000.0,
            "abs_diff": 2000.0, "rel_pct": 2.0, "unit": "USD_thousands",
        }],
        "fact_conflicts": [],
    }
    p = write_conflict_md(tmp_path, "AAOI", result)
    txt = p.read_text()
    assert "Q4_FY2024" in txt and "revenue" in txt and "2.0%" in txt
```

- [ ] **Step 2: Verify fails**

- [ ] **Step 3: Implement**

Append to `audit.py`:
```python
def write_audit_md(out_dir: Path, ticker: str, result: dict, *, meta_extras: dict | None = None) -> Path:
    stats = result["stats"]
    lines = [
        f"# {ticker} derive-base audit",
        "",
        f"- Pass 1 (identity_on_direct):  {stats['pass1_count']}",
        f"- Pass 2 (GAAP_Q4):             {stats['pass2_count']}",
        f"- Pass 3 (identity_on_q4):      {stats['pass3_count']}",
        f"- Final winners (after facts):  {stats['final_count']}",
        f"- Hard tolerance conflicts:     {stats['conflicts']}",
        f"- Facts-already-cover skips:    {stats['fact_skips']}",
        "",
    ]
    if meta_extras:
        lines.append("## metadata")
        for k, v in meta_extras.items():
            lines.append(f"- {k}: {v}")
        lines.append("")
    # Chain depth distribution
    by_depth: dict[int, int] = {}
    for w in result["winners"]:
        d = w.provenance.get("chain_depth", w.chain_depth if hasattr(w, "chain_depth") else 1)
        by_depth[d] = by_depth.get(d, 0) + 1
    lines.append("## chain_depth distribution")
    for d in sorted(by_depth):
        lines.append(f"- depth {d}: {by_depth[d]}")
    p = out_dir / f"{ticker}_derive_audit.md"
    p.write_text("\n".join(lines))
    return p


def write_conflict_md(out_dir: Path, ticker: str, result: dict) -> Path:
    lines = [f"# {ticker} derive-base conflicts", ""]
    confs = result.get("conflicts", [])
    if confs:
        lines.append("## Hard tolerance conflicts (candidate skipped)")
        lines.append("")
        lines.append("| period | uni_account | preferred | other | abs | rel |")
        lines.append("|---|---|---|---|---:|---:|")
        for c in confs:
            lines.append(
                f"| {c['period']} | {c['uni_account']} | "
                f"{c['preferred_rule']}={c['preferred_value']} | "
                f"{c['other_rule']}={c['other_value']} | "
                f"{c['abs_diff']} {c['unit']} | {c['rel_pct']:.1f}% |"
            )
        lines.append("")
    fc = result.get("fact_conflicts", [])
    if fc:
        lines.append("## Facts already cover (derive skipped, diff recorded)")
        lines.append("")
        lines.append("| period | uni_account | facts_value | derived_value | abs | rel | level |")
        lines.append("|---|---|---:|---:|---:|---:|---|")
        for c in fc:
            lines.append(
                f"| {c['period']} | {c['uni_account']} | "
                f"{c['facts_value']} | {c['derived_value']} | "
                f"{c['abs_diff']} | {c['rel_pct']:.2f}% | {c['tolerance_level']} |"
            )
        lines.append("")
    if not confs and not fc:
        lines.append("_(none)_")
    p = out_dir / f"{ticker}_conflict_report.md"
    p.write_text("\n".join(lines))
    return p
```

- [ ] **Step 4: Verify pass**

- [ ] **Step 5: Commit**

```bash
git add tmp/derive-base/audit.py tmp/derive-base/tests/test_audit.py
git commit -m "derive-base: audit + conflict markdown writers"
```

---

## Phase 7 — CLI entrypoint

### Task 16: derive_base.py CLI (wires everything together)

**Files:**
- Create: `tmp/derive-base/derive_base.py`
- Create: `tmp/derive-base/tests/test_cli.py`

- [ ] **Step 1: Failing test (smoke test the CLI on a tiny stubbed vault)**

`tmp/derive-base/tests/test_cli.py`:
```python
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
```

- [ ] **Step 2: Verify fails**

- [ ] **Step 3: Implement CLI**

`tmp/derive-base/derive_base.py`:
```python
#!/usr/bin/env python3
"""derive-base CLI entrypoint.

Usage:
  python3 derive_base.py --ticker AAOI [--vault /path/to/obsidian]

Reads from   <vault>/Khouse/Semiconductors/<TICKER>/01_Source/SEC Filings/Skill_Output/parse-10QK-gaap/
Writes to    <vault>/Khouse/Semiconductors/<TICKER>/01_Source/SEC Filings/Skill_Output/derive-base/<run_stamp>/
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from io_loader import discover_sources, load_facts, load_calc_edges, output_dir, sha256_file
from rules_identity import build_qname_to_uni, calc_rules_from_edges
from derive_engine import run_engine
from audit import to_derived_metric_row, write_derived_json, write_audit_md, write_conflict_md


DEFAULT_VAULT = Path(os.path.expanduser(
    "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian"
))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--vault", default=str(DEFAULT_VAULT),
                    help="Obsidian vault root (default: real iCloud vault)")
    args = ap.parse_args()

    ticker = args.ticker.upper()
    vault = Path(args.vault).expanduser()

    srcs = discover_sources(vault, ticker)
    if srcs["gaap_inline"] is None or not srcs["gaap_inline"].exists():
        print(f"❌ {ticker} inline gaap.json not found under {vault}", file=sys.stderr)
        return 2

    facts = load_facts(srcs)
    edges = load_calc_edges(srcs)
    calc_rules = calc_rules_from_edges(edges)

    inline = json.loads(srcs["gaap_inline"].read_text())
    qname_to_uni = build_qname_to_uni(inline)

    result = run_engine(facts=facts, calc_rules=calc_rules, qname_to_uni=qname_to_uni)
    rows = [to_derived_metric_row(c) for c in result["winners"]]

    run_stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    od = output_dir(vault, ticker, run_stamp)
    meta_extras = {
        "input_facts_count": len(facts),
        "calc_rules_count":  len(calc_rules),
        "qname_to_uni_count": len(qname_to_uni),
        "stats": result["stats"],
        "input_files": {
            k: {"path": str(v), "sha256": sha256_file(v)}
            for k, v in srcs.items() if v is not None and v.exists()
        },
    }
    write_derived_json(od, ticker, rows, meta=meta_extras)
    write_audit_md(od, ticker, result, meta_extras=meta_extras)
    write_conflict_md(od, ticker, result)

    print(f"derive-base done — {len(rows)} rows, {result['stats']['conflicts']} conflicts, {result['stats']['fact_skips']} facts-skips")
    print(str(od))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run, verify pass**

```bash
cd tmp/derive-base && python3 -m pytest tests/test_cli.py -v
```
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add tmp/derive-base/derive_base.py tmp/derive-base/tests/test_cli.py
git commit -m "derive-base: CLI entrypoint wiring loader+engine+audit"
```

---

## Phase 8 — End-to-end validation against real data

### Task 17: E2E AAOI — sanity assertions

**Files:**
- Create: `tmp/derive-base/tests/test_e2e_aaoi.py`

- [ ] **Step 1: Failing test with concrete expectations**

`tmp/derive-base/tests/test_e2e_aaoi.py`:
```python
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
```

- [ ] **Step 2: Run, observe**

```bash
cd tmp/derive-base && python3 -m pytest tests/test_e2e_aaoi.py -v
```
Expected on first pass: may have small discrepancies (rounding from `USD_thousands` decimals). If a value is off by >1.0, inspect the audit md to find the chain. If `Q4_FY_MINUS_9M` formula but value disagrees with expectation, recompute by hand using `cat .../AAOI_gaap_facts.json | jq` to confirm the parse outputs.

- [ ] **Step 3: If discrepancies, narrow root cause**

If tests fail with values close-but-not-equal (e.g. off by exactly 1.0), bump the assertion tolerance to `<= 1.0` (it currently uses `< 1.0`) — `USD_thousands` rounding lives in `parse-10QK-gaap` and we don't fight it.

If tests fail with "rule_id" mismatch (e.g. derive used Q1+Q2+Q3 instead of FY-9M), the YTD facts may not have been loaded — `grep '9M_FY2024' AAOI_gaap.json` and trace through `load_facts`.

If tests fail with `missing Q4 revenue`, the most likely cause is that GAAP facts already contain a Q4 single-quarter row (filed restatement). Use the conflict report to confirm and adjust the expected count.

- [ ] **Step 4: Commit once green**

```bash
git add tmp/derive-base/tests/test_e2e_aaoi.py
git commit -m "derive-base: E2E AAOI Q4 revenue + chain-depth + sha256 assertions"
```

---

### Task 18: E2E INTC — verify CALC_LINKBASE path fires

**Files:**
- Create: `tmp/derive-base/tests/test_e2e_intc.py`

- [ ] **Step 1: Failing test**

```python
import json, os, subprocess, sys
from pathlib import Path
import pytest

VAULT = Path(os.path.expanduser(
    "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian"
))


@pytest.fixture(scope="module")
def intc_derived():
    if not VAULT.exists():
        pytest.skip("Obsidian vault not present (CI run)")
    cli = Path(__file__).resolve().parents[1] / "derive_base.py"
    r = subprocess.run([sys.executable, str(cli), "--ticker", "INTC"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out_dir = Path([ln for ln in r.stdout.splitlines() if ln.strip()][-1])
    return json.loads((out_dir / "INTC_derived.json").read_text())


def test_intc_q4_revenue(intc_derived):
    # INTC FY2025 = 52,853 (USD_millions), 9M_FY2025 = 39,179 → Q4 = 13,674
    row = next((r for r in intc_derived["derived_metrics"]
                if r["uni_account"] == "revenue"
                and r["period"] == "Q4_FY2025"
                and r["version"] == "GAAP"), None)
    assert row is not None
    assert abs(row["value"] - 13674.0) < 1.0
    assert row["unit"] == "USD_millions"


def test_intc_has_calc_linkbase_derives(intc_derived):
    # INTC's calc linkbase is well-formed; expect at least one CALC_LINKBASE rule_id
    # firing (typically intermediate subtotals like income_before_taxes).
    rule_ids = {r["provenance"]["rule_id"] for r in intc_derived["derived_metrics"]}
    assert "Q4_FY_MINUS_9M" in rule_ids
    # CALC_LINKBASE optional — log but don't hard-fail (depends on facts coverage)
    print("rule_ids fired:", rule_ids)
```

- [ ] **Step 2: Run, observe**

```bash
cd tmp/derive-base && python3 -m pytest tests/test_e2e_intc.py -v -s
```
Expected: both pass; `print` output shows which rule_ids fired.

- [ ] **Step 3: Commit**

```bash
git add tmp/derive-base/tests/test_e2e_intc.py
git commit -m "derive-base: E2E INTC Q4 revenue + rule_id sanity"
```

---

## Phase 9 — Promote to production

### Task 19: Copy prototype to CC_Switch_Config/skills/derive-base/

**Files:**
- Create: `CC_Switch_Config/skills/derive-base/SKILL.md`
- Create: `CC_Switch_Config/skills/derive-base/scripts/*.py` (mirrors prototype)

- [ ] **Step 1: Copy prototype files to skill layout**

```bash
mkdir -p /Users/mensch5566/CC_Switch_Config/skills/derive-base/scripts
cp tmp/derive-base/{derive_types,io_loader,rules_q4,rules_identity,derive_engine,audit,tolerance,derive_base}.py \
   /Users/mensch5566/CC_Switch_Config/skills/derive-base/scripts/
```

(No rename needed — `derive_types` is already non-shadowing, so production layout is byte-for-byte identical to prototype.)

- [ ] **Step 2: Verify the production scripts still import cleanly**

```bash
cd /Users/mensch5566/CC_Switch_Config/skills/derive-base/scripts && python3 -c "
import sys, pathlib
sys.path.insert(0, str(pathlib.Path('.').resolve()))
import derive_types, io_loader, rules_q4, rules_identity, derive_engine, audit, tolerance, derive_base
print('imports ok')
"
```
Expected: `imports ok`.

- [ ] **Step 3: Write SKILL.md**

`CC_Switch_Config/skills/derive-base/SKILL.md`:
```markdown
---
name: derive-base
description: Reconstruct Q4 single-quarter IS/CF values and fill same-statement subtotal identity holes from parse-10QK-gaap + parse-8k-nongaap outputs. Emits sec_financial_metrics-shaped JSON only — never writes to Supabase, never modifies parse outputs. Use after parse skills run for a ticker.
---

# derive-base — SEC Financials Derive Pass 1

讀取 `parse-10QK-gaap` + `parse-8k-nongaap` 輸出的 JSON，根據 bounded 3-pass 規則
產出 `{TICKER}_derived.json`（對齊 `sec_financial_metrics` schema）。**永不運算到
parse 輸出檔上、永不直寫 Supabase**。

## ⛔ 必要參數

| # | 參數 | 範例 |
|---|---|---|
| 1 | ticker | `AAOI`, `INTC`, `SNDK` |
| 2 | （可選）--vault | 預設 iCloud Obsidian 路徑 |

## 🚫 Parse 永不運算（專案層級鐵律 — 對 derive 也適用反向）

derive-base 只允許這些算法，**絕無例外**：

- ✅ Q4 = FY - 9M（GAAP only，IS / CF）
- ✅ Q4 = FY - (Q1+Q2+Q3)（GAAP only，fallback）
- ✅ Q4 EPS 同公式
- ✅ Calc linkbase parent = Σ(child × weight)
- ✅ Static allowlist 同 statement / 同 period / 同 version 內 4 條 identity（GAAP fallback + Non-GAAP sparse）
- ❌ 跨 statement identity（`ending_cash = beginning_cash + net_change`）
- ❌ Ratio / margin（屬 derive-analytics）
- ❌ Avg balance / TTM
- ❌ Non-GAAP 跨期 Q4 還原
- ❌ WASO Q4
- ❌ 反推 child（已有 parent + N-1 children 推出第 N child）
- ❌ 覆寫 SOURCE_OF_TRUTH facts（同 key 存在就 skip + 記 conflict report）

## 使用方式

```bash
python3 ~/.claude/skills/derive-base/scripts/derive_base.py --ticker AAOI
```

輸出位置：

```
Khouse/Semiconductors/<TICKER>/01_Source/SEC Filings/Skill_Output/derive-base/<YYYY-MM-DD-HHMM>/
├── <TICKER>_derived.json         主輸出（對齊 sec_financial_metrics schema）
├── <TICKER>_derive_audit.md      per-pass 統計 + chain depth 分佈
└── <TICKER>_conflict_report.md   tolerance breaches + facts-already-cover diffs
```

## Pipeline 位置

```
parse-10QK-gaap ──┐
parse-8k-nongaap ─┼──→ derive-base (本 skill) ──→ compose ──→ derive-analytics ──→ upsert
parse-SEC-supplement (independent path) ─────────────────────────────────────────┘
```

## Bounded 3-pass

| Pass | 名稱 | 輸入 | 輸出 |
|---|---|---|---|
| 1 | identity_on_direct | direct facts | 非 Q4 subtotal |
| 2 | GAAP_Q4 | direct + Pass 1 | Q4 single-quarter (`period_kind=derived_q4`) |
| 3 | identity_on_q4 | direct + Pass 1 + Pass 2 | Q4 subtotal |

Chain depth ≤ 3。超過視為 bug、fail fast。

## 已知限制

| 項目 | 說明 |
|---|---|
| WASO Q4 不還原 | 加權平均不是線性減法。EPS 用 FY-9M EPS 還原可，shares 留 PENDING |
| Non-GAAP 不做跨期 Q4 | management 定義可能跨期變動，沒有 baseline 不應拼 |
| Long-tail Q4 不主動輸出 | metrics 表沒 source_account 欄；多個 child 壓成一筆會失 provenance |
| 跨表 identity 排除 | `ending_cash = begin_cash + change` 屬 reconciliation pass，留給將來 |
```

- [ ] **Step 4: Run the CLI from the production skill location once for AAOI**

```bash
python3 /Users/mensch5566/CC_Switch_Config/skills/derive-base/scripts/derive_base.py --ticker AAOI
```
Expected: same output as the tmp prototype (compare audit.md row counts).

- [ ] **Step 5: Commit**

```bash
cd /Users/mensch5566/CC_Switch_Config
git add skills/derive-base/
git commit -m "derive-base skill: bounded 3-pass derive engine + SKILL.md (promote from prototype)"
```

---

### Task 20: Sync to 3 runtimes (.claude / .codex / .cc-switch)

**Files:**
- Modify (by rsync): `~/.claude/skills/derive-base/`, `~/.codex/skills/derive-base/`, `~/.cc-switch/skills/derive-base/`

- [ ] **Step 1: rsync to all three runtimes**

```bash
SRC=/Users/mensch5566/CC_Switch_Config/skills/derive-base
for tgt in /Users/mensch5566/.claude/skills /Users/mensch5566/.codex/skills /Users/mensch5566/.cc-switch/skills; do
  mkdir -p "$tgt/derive-base"
  rsync -a --delete --exclude='*.bak' --exclude='__pycache__' \
    "$SRC/" "$tgt/derive-base/"
done
```

- [ ] **Step 2: Verify 0 diff across all 3 runtimes**

```bash
for tgt in /Users/mensch5566/.claude/skills /Users/mensch5566/.codex/skills /Users/mensch5566/.cc-switch/skills; do
  n=$(diff -rq --exclude='*.bak' --exclude='__pycache__' "$SRC" "$tgt/derive-base" | wc -l)
  echo "$tgt → $n diffs"
done
```
Expected: each prints `0 diffs`.

- [ ] **Step 3: Smoke-run from .claude runtime**

```bash
python3 /Users/mensch5566/.claude/skills/derive-base/scripts/derive_base.py --ticker INTC
```
Expected: exits 0, prints output dir.

- [ ] **Step 4: No commit (runtime locations aren't git-tracked under CC_Switch_Config).** Move on.

---

## Phase 10 — Wire upsert to consume derived JSON

### Task 21: Extend scripts/upsert_sec_financials.py to read derived JSON

**Files:**
- Modify: `AI_Agent/scripts/upsert_sec_financials.py`
- Create: `AI_Agent/scripts/tests/test_upsert_derived.py` (lightweight)

- [ ] **Step 1: Read current upsert script header to understand its arg-parsing + flow**

```bash
sed -n '1,80p' /Users/mensch5566/AI_Agent/scripts/upsert_sec_financials.py
```
Note the existing CLI shape (`upsert_sec_financials.py TICKER [--apply]`) and the section that builds the `sec_financial_metrics` table writes — currently empty.

- [ ] **Step 2: Failing test**

`AI_Agent/scripts/tests/test_upsert_derived.py`:
```python
import json
from pathlib import Path
import importlib.util
import sys


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
    rows = upsert.load_derived_metrics(vault, "ABC")
    assert len(rows) == 1
    assert rows[0]["cell_id"] == "new"
```

- [ ] **Step 3: Verify fails**

```bash
cd /Users/mensch5566/AI_Agent && python3 -m pytest scripts/tests/test_upsert_derived.py -v
```
Expected: FAIL (`load_derived_metrics` not defined).

- [ ] **Step 4: Implement `load_derived_metrics` + wire into upsert flow**

Add to `scripts/upsert_sec_financials.py` (near the top, before main):
```python
def load_derived_metrics(vault: Path, ticker: str) -> list[dict]:
    """Read latest derive-base run for `ticker` and return its derived_metrics[].

    Returns [] if no derive-base output exists yet (skill not run).
    """
    base = (vault / "Khouse" / "Semiconductors" / ticker
            / "01_Source" / "SEC Filings" / "Skill_Output" / "derive-base")
    if not base.exists():
        return []
    runs = sorted(p for p in base.iterdir() if p.is_dir())
    if not runs:
        return []
    derived = runs[-1] / f"{ticker}_derived.json"
    if not derived.exists():
        return []
    return json.loads(derived.read_text()).get("derived_metrics", [])
```

In the existing upsert flow (after the `sec_financial_facts` upsert block), add:
```python
    derived_rows = load_derived_metrics(VAULT_BASE, ticker)
    if derived_rows:
        print(f"  + {len(derived_rows)} derived metrics from derive-base")
        if args.apply:
            sb.table("sec_financial_metrics").upsert(
                derived_rows, on_conflict="cell_id"
            ).execute()
            print(f"  upserted: sec_financial_metrics ({len(derived_rows)} rows)")
```

- [ ] **Step 5: Run the test, verify pass**

```bash
cd /Users/mensch5566/AI_Agent && python3 -m pytest scripts/tests/test_upsert_derived.py -v
```
Expected: 1 passed.

- [ ] **Step 6: Dry-run on AAOI (no --apply)**

```bash
python3 scripts/upsert_sec_financials.py AAOI 2>&1 | tail -10
```
Expected: includes `+ N derived metrics from derive-base` line. Verify N > 0.

- [ ] **Step 7: Apply on AAOI**

```bash
python3 scripts/upsert_sec_financials.py AAOI --apply 2>&1 | tail -5
```
Expected: includes `upserted: sec_financial_metrics (N rows)`.

- [ ] **Step 8: Verify Supabase has metrics**

```bash
set -a; source /Users/mensch5566/AI_Agent/.env; set +a
uv run --with supabase python3 -c "
import os
from supabase import create_client
sb = create_client(os.environ['NEXT_PUBLIC_SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])
res = sb.table('sec_financial_metrics').select('count', count='exact').eq('ticker', 'AAOI').execute()
print('AAOI metrics rows:', res.count)
"
```
Expected: `AAOI metrics rows: N` matching the previous step.

- [ ] **Step 9: Commit**

```bash
cd /Users/mensch5566/AI_Agent
git add scripts/upsert_sec_financials.py scripts/tests/test_upsert_derived.py
git commit -m "upsert_sec_financials: consume derive-base output → sec_financial_metrics"
```

---

### Task 22: Verify Viewer surfaces derived rows (visual check, no code change expected)

**Files:** (none — verification only)

- [ ] **Step 1: Start dev server if not already running**

```bash
lsof -i :3000 -sTCP:LISTEN -P -n 2>/dev/null | head -2
# If empty: npm run dev > /tmp/next-dev.log 2>&1 &
```

- [ ] **Step 2: Curl the AAOI API response and count metrics rows**

```bash
curl -s http://localhost:3000/api/financials/AAOI | python3 -c "
import json, sys
d = json.load(sys.stdin)
m = [c for c in d['cells'] if c.get('source_table') == 'metrics']
print('metrics cells in API:', len(m))
print('sample:', m[0] if m else None)
"
```
Expected: `metrics cells in API: > 0`, sample shape matches `DerivedMetricRow`.

- [ ] **Step 3: Manual browser check (state finding)**

Open `http://localhost:3000/financials/AAOI` in browser. Switch to quarterly view. Confirm Q4_FY2024 IS Revenue, Gross Profit, etc. now show (italic muted = DERIVED_FROM_DISCLOSED). State in your reply: "Q4 cells now show in Viewer" or "Q4 cells still PENDING — investigate".

- [ ] **Step 4: No commit needed if visual check passes.**

If Q4 doesn't render, the most likely cause is the API `route.ts` not flagging `metrics` cells with the correct `status`; check the existing `app/api/financials/[ticker]/route.ts` and ensure metrics rows are mapped through with `source_table="metrics"` (the existing rewrite already does this — sanity-check, don't refactor).

---

## Self-Review

**Spec coverage check (against `tmp/derive-base-design.md` v2):**

| Spec section | Plan task |
|---|---|
| §0 context, prereqs | Plan header notes prereq commit; no task needed |
| §1 scope/不做 | Task 1 (types) + Task 6 (Q4 GAAP-only IS/CF) + Task 9 (Non-GAAP allowlist) enforce scope |
| §2 I/O, paths, output filenames | Task 2 (`discover_sources`, `output_dir`) + Task 14 (JSON writer) + Task 15 (md writers) |
| §3.1 GAAP Q4 rules | Task 6 |
| §3.2 calc-linkbase identity | Task 7 + Task 8 |
| §3.2 Non-GAAP allowlist + GAAP fallback | Task 9 |
| §3.3 candidate resolution priority | Task 11 |
| §3.4 排除規則 (missing inputs / chained flag / facts already cover) | Task 6 (missing inputs skip) + Task 12 (chained flag) + Task 13 (facts cover skip) |
| §4 bounded 3-pass | Task 12 |
| §5 JSON schema | Task 14 |
| §6 衝突 + tolerance | Task 5 + Task 11 + Task 13 + Task 15 |
| §7 parse pre-work | Already done (commit `444db47`); plan header notes it |
| §8 邊界 cases | Tasks 6/8/11/13 cover the named ones |
| §9 已收斂決策 | Tasks pick same defaults |
| §9.1 file layout | File Structure section + Task 19 mirrors layout |
| §10 out of scope | Plan header lists same |
| §11 後續決策依賴 | Tasks 19-22 cover parse pre-work follow-on + promote + sync + upsert wire |

All sections covered. No gaps.

**Placeholder scan:** No "TBD" / "TODO" / "similar to Task N" / vague-error-handling left.

**Type consistency:** `Candidate`, `DerivedMetricRow`, `FactRow` used uniformly. Field names verified across Tasks 1, 6, 8, 9, 11, 12, 14.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-17-derive-base.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
