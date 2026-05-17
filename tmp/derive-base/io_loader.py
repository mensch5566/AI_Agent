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
import sys
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


# Allow imports from AI_Agent/Tools/research-tools/_shared/
AI_AGENT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AI_AGENT_ROOT / "Tools" / "research-tools"))
from _shared.sec_json_adapter import (
    adapt_gaap_facts, adapt_nongaap_facts,
    build_period_end_map, FactRow,
)


def load_facts(sources: dict[str, Path | None]) -> list[FactRow]:
    """Return canonical FactRow list (GAAP ∪ Non-GAAP)."""
    rows: list[FactRow] = []
    gaap_facts = sources["gaap_facts"]
    if gaap_facts is None or not gaap_facts.exists():
        raise FileNotFoundError(f"gaap_facts json missing: {gaap_facts}")
    gaap_json = json.loads(gaap_facts.read_text())
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
