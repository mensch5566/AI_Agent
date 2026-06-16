"""Fetch FRED series and normalize to macro_facts rows."""
from __future__ import annotations
import hashlib, json, os, urllib.request, urllib.parse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG = REPO_ROOT / "lib" / "macro" / "indicators.json"
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"


def fact_id(indicator_key: str, period_end: str, version: int = 1) -> str:
    raw = f"{indicator_key}|{period_end}|{version}".encode()
    return hashlib.sha256(raw).hexdigest()


def load_config() -> dict:
    return json.loads(CONFIG.read_text())


def fetch_observations(series_id: str, api_key: str) -> list[dict]:
    q = urllib.parse.urlencode({"series_id": series_id, "api_key": api_key, "file_type": "json"})
    with urllib.request.urlopen(f"{FRED_BASE}?{q}", timeout=30) as r:
        return json.loads(r.read())["observations"]


def normalize_observations(indicator_key, series_id, layer, unit, freq, observations) -> list[dict]:
    rows = []
    for o in observations:
        v = o.get("value")
        if v in (".", "", None):   # FRED uses "." for missing
            continue
        period_end = o["date"]
        rows.append({
            "fact_id": fact_id(indicator_key, period_end),
            "indicator_key": indicator_key,
            "layer": layer,
            "value": float(v),
            "unit": unit,
            "period_end": period_end,
            "release_date": period_end,   # v1: FRED obs date ≈ release; refine later
            "freq": freq,
            "source_type": "api",
            "source_ref": f"FRED:{series_id}",
            "value_hash": hashlib.sha256(str(v).encode()).hexdigest()[:16],
            "version": 1,
        })
    return rows


def fetch_all(api_key: str) -> list[dict]:
    cfg = load_config()
    rows: list[dict] = []
    for ind in cfg["indicators"]:
        obs = fetch_observations(ind["fred_series"], api_key)
        rows.extend(normalize_observations(
            ind["indicator_key"], ind["fred_series"], ind["layer"],
            ind["unit"], ind["freq"], obs))
    return rows


if __name__ == "__main__":
    key = os.environ.get("FRED_API_KEY")
    if not key:
        raise SystemExit("Set FRED_API_KEY env var")
    print(f"fetched {len(fetch_all(key))} rows")
