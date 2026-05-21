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
# Production path: absolute reference to AI_Agent repo (sibling of CC_Switch_Config)
AI_AGENT_ROOT = Path(__file__).resolve().parents[4] / "AI_Agent"
if not (AI_AGENT_ROOT / "Tools" / "research-tools" / "_shared").exists():
    # Fallback: try prototype location (parents[2] = AI_Agent when run from tmp/derive-base)
    AI_AGENT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AI_AGENT_ROOT / "Tools" / "research-tools"))
from _shared.sec_json_adapter import (
    adapt_gaap_facts, adapt_nongaap_facts,
    build_period_end_map, FactRow,
)


import re as _re
_YTD_RE = _re.compile(r"^(\d+)M_FY(\d{4})$")
_FY_RE  = _re.compile(r"^FY(\d{4})$")
_Q_RE   = _re.compile(r"^Q(\d)_FY(\d{4})$")


def _filing_period_for(period: str) -> str | None:
    """Map a fact's period to the filing-event period that contains it.
    metadata.filings is keyed by filing event (Q1/Q2/Q3 10-Q, Q4 10-K).
    YTD and FY periods don't appear directly — they come from the latest
    filing that covers their end date:
      6M_FY{y} → Q2_FY{y} 10-Q
      9M_FY{y} → Q3_FY{y} 10-Q
      FY{y}    → Q4_FY{y} 10-K
      Q{n}_FY{y} → itself."""
    if _Q_RE.match(period) or period.startswith("Q"):
        return period
    m = _YTD_RE.match(period)
    if m:
        months, year = int(m.group(1)), m.group(2)
        if months in (3, 6, 9):
            return f"Q{months // 3}_FY{year}"
    m = _FY_RE.match(period)
    if m:
        return f"Q4_FY{m.group(1)}"
    return None


def _backfill_filing_provenance(rows: list[FactRow], metadata: dict) -> None:
    """Codex round-3 F4: parse output's metadata.filings carries per-filing
    accession_number / form / filing_date / primary_doc, but adapter does
    not propagate them onto FactRow.provenance. Backfill in place so
    `input_dict_from_fact()` can surface restatement-trace info.

    Maps YTD (6M/9M) and FY periods to their containing filing via
    `_filing_period_for()` since metadata.filings is keyed by filing event."""
    filings = (metadata or {}).get("filings") or {}
    if not filings:
        return
    for r in rows:
        filing_key = _filing_period_for(r.period)
        info = filings.get(filing_key) if filing_key else None
        if not info:
            continue
        prov = getattr(r, "provenance", None)
        if prov is None:
            r.provenance = {}
            prov = r.provenance
        # Fill if upstream has the key but value is None / empty. Upstream
        # adapter pre-populates these as None placeholders so `key in prov`
        # is True even when no real value was captured; use truthy check.
        for key in ("accession_number", "form", "filing_date", "primary_doc"):
            val = info.get(key)
            if val and not prov.get(key):
                prov[key] = val
        # Mirror filing → source_filing for input_dict_from_fact lookup.
        if not prov.get("source_filing") and info.get("primary_doc"):
            prov["source_filing"] = info["primary_doc"]


def load_facts(sources: dict[str, Path | None]) -> list[FactRow]:
    """Return canonical FactRow list (GAAP ∪ Non-GAAP)."""
    rows: list[FactRow] = []
    gaap_facts = sources["gaap_facts"]
    if gaap_facts is None or not gaap_facts.exists():
        raise FileNotFoundError(f"gaap_facts json missing: {gaap_facts}")
    gaap_json = json.loads(gaap_facts.read_text())
    # Short-circuit: if facts list is empty, skip adapter (avoids KeyError on
    # minimal metadata stubs that omit ticker / filings).
    if gaap_json.get("facts"):
        pe_map = build_period_end_map(gaap_json.get("metadata", {}))
        gaap_rows, _ = adapt_gaap_facts(gaap_json, pe_map)
        _backfill_filing_provenance(gaap_rows, gaap_json.get("metadata", {}))
        rows.extend(gaap_rows)
    ng = sources["nongaap"]
    if ng is not None and ng.exists():
        ng_json = json.loads(ng.read_text())
        ng_pe_map = build_period_end_map(ng_json.get("metadata", {}))
        ng_rows, _ = adapt_nongaap_facts(ng_json, ng_pe_map)
        _backfill_filing_provenance(ng_rows, ng_json.get("metadata", {}))
        rows.extend(ng_rows)
    return rows


def load_calc_edges(sources: dict[str, Path | None]) -> list[dict]:
    """Return raw calc edges from {TICKER}_gaap_edges_cal.json."""
    path = sources["gaap_edges_cal"]
    if path is None or not path.exists():
        return []
    return json.loads(path.read_text()).get("edges", [])
