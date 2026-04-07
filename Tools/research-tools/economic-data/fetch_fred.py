"""
FRED Economic Data Fetcher → Supabase
=======================================
從 FRED API 抓取經濟指標，組裝成 Command Center data.json 的 ReportData 結構，
寫入 Supabase economic_data table。

無 FRED API 的指標（ISM PMI, VXN, HHDC, 台灣出口）保留現有值不覆蓋。

用法:
  set -a; source .env; set +a
  uv run --with requests --with supabase python3 Tools/research-tools/economic-data/fetch_fred.py
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests
from supabase import create_client

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# ── FRED series 對照 ─────────────────────────────────────────
YIELD_CURVE_SERIES = {
    "1M": "DGS1MO", "3M": "DGS3MO", "6M": "DGS6MO",
    "1Y": "DGS1",   "2Y": "DGS2",   "5Y": "DGS5",
    "10Y": "DGS10", "20Y": "DGS20", "30Y": "DGS30",
}

INFLATION_SERIES = {
    "cpi": "CPIAUCSL",       # CPI All Items (index)
    "coreCpi": "CPILFESL",   # Core CPI (index)
    "pce": "PCEPI",          # PCE Price Index
    "corePce": "PCEPILFE",   # Core PCE Price Index
}

EMPLOYMENT_SERIES = {
    "nfp": "PAYEMS",     # All Employees, Total Nonfarm (thousands)
    "unrate": "UNRATE",  # Unemployment Rate
}

# Leading indicators with FRED API (id -> series_id)
LEADING_FRED = {
    1: "A191RL1Q225SBEA",  # GDP QoQ SAAR
    2: "FEDFUNDS",          # Federal Funds Rate
    3: "PCEPI",             # PCE YoY (need to compute)
    4: "PCEPILFE",          # Core PCE YoY
    5: "CPIAUCSL",          # CPI YoY
    6: "CPILFESL",          # Core CPI YoY
    8: "VIXCLS",            # VIX
    10: "USALOLITONOSTSAM", # OECD CLI
    11: "BSCICP03USM665S",  # OECD BCI
    12: "CP",               # Corporate Profits (billions)
    13: "PAYEMS",           # NFP (compute MoM change)
    14: "UNRATE",           # Unemployment Rate
}

# Risk indicators with FRED API
RISK_FRED = {
    2: "DRALACBN",       # Delinquency rate - all loans
    3: "DRSFRMACBS",     # Delinquency - residential RE
    5: "DRCLACBS",       # Delinquency - auto loans
    6: "DRCCLACBS",      # Delinquency - credit cards
    8: "DRCCLACBS",      # Bank delinquency - credit cards (same series)
    9: "BAMLH0A1HYBBEY", # HY BB yield
    10: "BAMLH0A2HYBEY", # HY B yield
    11: "BAMLH0A3HYCEY", # HY CCC yield
    12: "DRSDCILM",      # SLOOS demand - large firms
    13: "DRTSCILM",      # SLOOS standards - large firms
    14: "DRSDCIS",       # SLOOS demand - small firms
    15: "DRTSCIS",       # SLOOS standards - small firms
}


def fred_get(series_id: str, api_key: str, limit: int = 24,
             sort_order: str = "desc") -> list[dict]:
    """Fetch observations from FRED API."""
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": sort_order,
        "limit": limit,
    }
    r = requests.get(FRED_BASE, params=params, timeout=15)
    r.raise_for_status()
    obs = r.json().get("observations", [])
    # Filter out missing values
    return [o for o in obs if o["value"] != "."]


def parse_float(v: str) -> float | None:
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def fmt_month(date_str: str) -> str:
    """'2026-01-01' -> \"Jan '26\""""
    d = datetime.strptime(date_str[:10], "%Y-%m-%d")
    return d.strftime("%b '%y")


def fmt_quarter(date_str: str) -> str:
    """'2025-10-01' -> '25Q4'"""
    d = datetime.strptime(date_str[:10], "%Y-%m-%d")
    q = (d.month - 1) // 3 + 1
    return f"{d.strftime('%y')}Q{q}"


def compute_yoy_pct(obs_desc: list[dict]) -> list[dict]:
    """Given index observations (desc order), compute YoY % change.
    Returns list of {date, label, value} in chronological order (last 18 months)."""
    # Need 30 months of data to compute 18 months of YoY
    obs = list(reversed(obs_desc))  # chronological
    results = []
    for i, o in enumerate(obs):
        # Find observation ~12 months earlier
        curr_date = datetime.strptime(o["date"][:10], "%Y-%m-%d")
        curr_val = parse_float(o["value"])
        if curr_val is None:
            continue
        # Look for matching month from previous year
        for j in range(max(0, i - 14), i):
            prev_date = datetime.strptime(obs[j]["date"][:10], "%Y-%m-%d")
            month_diff = (curr_date.year - prev_date.year) * 12 + (curr_date.month - prev_date.month)
            if 11 <= month_diff <= 13:
                prev_val = parse_float(obs[j]["value"])
                if prev_val and prev_val > 0:
                    yoy = (curr_val - prev_val) / prev_val * 100
                    results.append({
                        "date": o["date"],
                        "label": fmt_month(o["date"]),
                        "value": round(yoy, 2),
                    })
                break
    return results[-18:]  # last 18 months


def build_yield_curve(api_key: str) -> dict:
    """Build yieldCurveData from FRED."""
    labels = list(YIELD_CURVE_SERIES.keys())
    current = []
    prev_week = []

    for label, series_id in YIELD_CURVE_SERIES.items():
        obs = fred_get(series_id, api_key, limit=10)
        if len(obs) >= 1:
            current.append(parse_float(obs[0]["value"]))
        else:
            current.append(None)
        if len(obs) >= 6:
            prev_week.append(parse_float(obs[5]["value"]))
        elif len(obs) >= 2:
            prev_week.append(parse_float(obs[-1]["value"]))
        else:
            prev_week.append(None)

    return {"labels": labels, "current": current, "prevWeek": prev_week}


def build_fed_funds(api_key: str) -> dict:
    """Build fedFundsRate from FRED."""
    obs = fred_get("FEDFUNDS", api_key, limit=2)
    current = parse_float(obs[0]["value"]) if obs else None
    # Derive target range (round to nearest 0.25)
    if current is not None:
        low = round(current * 4) / 4 - 0.25
        high = low + 0.25
        # Adjust so current falls within range
        if current > high:
            low += 0.25
            high += 0.25
        target = f"{low:.2f}\u2013{high:.2f}%"
    else:
        target = "N/A"
    return {"current": current, "target": target}


def build_inflation(api_key: str) -> dict:
    """Build inflationData with YoY computation from FRED index series."""
    # We need ~30 months of data for each to compute 18 months of YoY
    cpi_obs = fred_get("CPIAUCSL", api_key, limit=36)
    core_cpi_obs = fred_get("CPILFESL", api_key, limit=36)
    pce_obs = fred_get("PCEPI", api_key, limit=36)
    core_pce_obs = fred_get("PCEPILFE", api_key, limit=36)

    cpi_yoy = compute_yoy_pct(cpi_obs)
    core_cpi_yoy = compute_yoy_pct(core_cpi_obs)
    pce_yoy = compute_yoy_pct(pce_obs)
    core_pce_yoy = compute_yoy_pct(core_pce_obs)

    # Use CPI labels as the master (most complete); take last 5
    labels = [r["label"] for r in cpi_yoy[-5:]]

    def align(data: list[dict], target_labels: list[str]) -> list[float | None]:
        lookup = {r["label"]: r["value"] for r in data}
        return [lookup.get(l) for l in target_labels]

    return {
        "labels": labels,
        "cpiYoY": align(cpi_yoy, labels),
        "coreYoY": align(core_cpi_yoy, labels),
        "pceYoY": align(pce_yoy, labels),
        "corePce": align(core_pce_yoy, labels),
    }


def build_employment(api_key: str) -> dict:
    """Build employmentData from FRED."""
    nfp_obs = list(reversed(fred_get("PAYEMS", api_key, limit=24)))  # chronological
    unrate_obs = list(reversed(fred_get("UNRATE", api_key, limit=24)))

    # NFP: compute MoM change in thousands
    nfp_changes = []
    for i in range(1, len(nfp_obs)):
        curr = parse_float(nfp_obs[i]["value"])
        prev = parse_float(nfp_obs[i - 1]["value"])
        if curr is not None and prev is not None:
            nfp_changes.append({
                "label": fmt_month(nfp_obs[i]["date"]),
                "value": round(curr - prev),  # already in thousands
            })

    nfp_changes = nfp_changes[-5:]
    labels = [r["label"] for r in nfp_changes]

    unrate_lookup = {fmt_month(o["date"]): parse_float(o["value"]) for o in unrate_obs}

    return {
        "labels": labels,
        "nfp": [r["value"] for r in nfp_changes],
        "unemployRate": [unrate_lookup.get(l) for l in labels],
        "avgHourlyEarningsYoY": None,
        "joltsCurrent": None,
    }


def build_indicator(indicator_id: int, series_id: str, existing: dict | None,
                    api_key: str) -> dict:
    """Build a single leading/risk indicator from FRED."""
    if existing is None:
        existing = {}

    obs = fred_get(series_id, api_key, limit=24)
    if not obs:
        return existing  # keep as-is

    obs_chrono = list(reversed(obs))

    latest_val = parse_float(obs[0]["value"])
    prev_val = parse_float(obs[1]["value"]) if len(obs) > 1 else None
    latest_date = obs[0]["date"][:10]

    # Determine formatting
    is_quarterly = series_id in (
        "A191RL1Q225SBEA", "DRALACBN", "DRSFRMACBS", "DRCLACBS",
        "DRCCLACBS", "CP", "DRSDCILM", "DRTSCILM", "DRSDCIS", "DRTSCIS",
    )

    # Special handling per indicator type
    if indicator_id in LEADING_FRED:
        # Indicators 3-6: need YoY computation from index
        if indicator_id in (3, 4, 5, 6):
            yoy_data = compute_yoy_pct(obs)
            if yoy_data:
                latest_val = yoy_data[-1]["value"]
                prev_val = yoy_data[-2]["value"] if len(yoy_data) > 1 else None
                latest_date = yoy_data[-1]["date"] if "date" in yoy_data[-1] else latest_date

                # Build history
                history = {
                    "labels": [r["label"] for r in yoy_data],
                    "values": [r["value"] for r in yoy_data],
                }
                result = dict(existing)
                result.update({
                    "prev": f"{prev_val:.2f}%" if prev_val is not None else existing.get("prev"),
                    "latest": f"{latest_val:.2f}%" if latest_val is not None else existing.get("latest"),
                    "chgPct": round((latest_val - prev_val) / abs(prev_val) * 100, 2) if prev_val and prev_val != 0 else None,
                    "date": latest_date[:7] if not is_quarterly else fmt_quarter(latest_date),
                    "history": history,
                })
                return result

        # Indicator 13 (NFP): compute MoM in thousands
        if indicator_id == 13:
            if len(obs_chrono) >= 2:
                changes = []
                for i in range(1, len(obs_chrono)):
                    c = parse_float(obs_chrono[i]["value"])
                    p = parse_float(obs_chrono[i - 1]["value"])
                    if c is not None and p is not None:
                        changes.append({
                            "label": fmt_month(obs_chrono[i]["date"]),
                            "value": round(c - p),
                            "date": obs_chrono[i]["date"],
                        })
                if changes:
                    latest_val = changes[-1]["value"]
                    prev_val = changes[-2]["value"] if len(changes) > 1 else None
                    result = dict(existing)
                    result.update({
                        "prev": str(prev_val) if prev_val is not None else existing.get("prev"),
                        "latest": str(latest_val),
                        "chgPct": round((latest_val - prev_val) / abs(prev_val) * 100, 2) if prev_val and prev_val != 0 else None,
                        "date": changes[-1]["date"][:7],
                        "history": {
                            "labels": [c["label"] for c in changes[-18:]],
                            "values": [c["value"] for c in changes[-18:]],
                        },
                    })
                    return result

    # Default: use raw values
    fmt_label = fmt_quarter if is_quarterly else fmt_month
    if latest_val is not None:
        # Format with % for rate-like indicators
        is_rate = series_id in (
            "FEDFUNDS", "UNRATE", "BAMLH0A1HYBBEY", "BAMLH0A2HYBEY",
            "BAMLH0A3HYCEY", "DRALACBN", "DRSFRMACBS", "DRCLACBS",
            "DRCCLACBS", "DRSDCILM", "DRTSCILM", "DRSDCIS", "DRTSCIS",
        )
        fmt_val = lambda v: f"{v:.2f}%" if is_rate else f"{v:.2f}" if v is not None else "—"

        chg_pct = None
        if prev_val is not None and prev_val != 0:
            chg_pct = round((latest_val - prev_val) / abs(prev_val) * 100, 2)

        # Build history from chronological observations
        history_data = [
            {"label": fmt_label(o["date"]), "value": parse_float(o["value"])}
            for o in obs_chrono if parse_float(o["value"]) is not None
        ]

        result = dict(existing)
        result.update({
            "prev": fmt_val(prev_val) if prev_val is not None else existing.get("prev"),
            "latest": fmt_val(latest_val),
            "chgPct": chg_pct,
            "date": fmt_quarter(latest_date) if is_quarterly else latest_date,
        })
        if history_data:
            result["history"] = {
                "labels": [h["label"] for h in history_data[-18:]],
                "values": [h["value"] for h in history_data[-18:]],
            }
        return result

    return existing


def main():
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        print("ERROR: FRED_API_KEY must be set")
        print("Get a free key at: https://fred.stlouisfed.org/docs/api/api_key.html")
        sys.exit(1)

    url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    skey = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not skey:
        print("ERROR: NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        sys.exit(1)

    sb = create_client(url, skey)

    # Load existing data to preserve manual-only indicators
    existing_data = {}
    try:
        res = sb.table("economic_data").select("data").eq("id", "latest").single().execute()
        if res.data and res.data.get("data"):
            existing_data = res.data["data"]
    except Exception:
        pass

    # Also load from static JSON as fallback for existing values
    if not existing_data:
        try:
            with open("public/data/command-center/data.json") as f:
                existing_data = json.load(f)
        except Exception:
            existing_data = {}

    existing_leading = {ind["id"]: ind for ind in existing_data.get("leadingIndicators", [])}
    existing_risk = {ind["id"]: ind for ind in existing_data.get("riskIndicators", [])}

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # ISO week
    now = datetime.now(timezone.utc)
    iso_week = f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"

    print("[1/6] Fetching yield curve...")
    yield_curve = build_yield_curve(api_key)

    print("[2/6] Fetching fed funds rate...")
    fed_funds = build_fed_funds(api_key)

    print("[3/6] Fetching inflation data...")
    inflation = build_inflation(api_key)

    print("[4/6] Fetching employment data...")
    employment = build_employment(api_key)

    print("[5/6] Fetching leading indicators...")
    leading_indicators = []
    for i in range(1, 17):
        existing = existing_leading.get(i, {"id": i, "name": f"Indicator {i}", "type": "", "prev": "—", "latest": "—", "chgPct": None, "date": "—", "nextUpdate": ""})
        if i in LEADING_FRED:
            try:
                updated = build_indicator(i, LEADING_FRED[i], existing, api_key)
                # Preserve id/name/type/nextUpdate from existing
                updated["id"] = existing["id"]
                updated["name"] = existing.get("name", updated.get("name", ""))
                updated["type"] = existing.get("type", updated.get("type", ""))
                updated["nextUpdate"] = existing.get("nextUpdate", updated.get("nextUpdate", ""))
                leading_indicators.append(updated)
                print(f"  #{i} {existing.get('name','')[:20]:20s} ✓")
            except Exception as e:
                print(f"  #{i} {existing.get('name','')[:20]:20s} FAILED: {e}")
                leading_indicators.append(existing)
        else:
            leading_indicators.append(existing)
            print(f"  #{i} {existing.get('name','')[:20]:20s} (manual, kept)")

    print("[6/6] Fetching risk indicators...")
    risk_indicators = []
    for i in range(1, 16):
        existing = existing_risk.get(i, {"id": i, "name": f"Risk Indicator {i}", "type": "", "prev": "—", "latest": "—", "chgPct": None, "date": "—", "nextUpdate": ""})
        if i in RISK_FRED:
            try:
                updated = build_indicator(i, RISK_FRED[i], existing, api_key)
                updated["id"] = existing["id"]
                updated["name"] = existing.get("name", updated.get("name", ""))
                updated["type"] = existing.get("type", updated.get("type", ""))
                updated["nextUpdate"] = existing.get("nextUpdate", updated.get("nextUpdate", ""))
                risk_indicators.append(updated)
                print(f"  #{i} {existing.get('name','')[:20]:20s} ✓")
            except Exception as e:
                print(f"  #{i} {existing.get('name','')[:20]:20s} FAILED: {e}")
                risk_indicators.append(existing)
        else:
            risk_indicators.append(existing)
            print(f"  #{i} {existing.get('name','')[:20]:20s} (manual, kept)")

    # Assemble ReportData
    report_data = {
        "REPORT_DATE": today,
        "REPORT_WEEK": iso_week,
        "dataFreshness": {
            "ffr": today,
            "cpi": today,
            "pce": today,
            "nfp": today,
            "unemployment": today,
        },
        "yieldCurveData": yield_curve,
        "fedFundsRate": fed_funds,
        "inflationData": inflation,
        "employmentData": employment,
        "equityData": existing_data.get("equityData", {"indices": [], "spxWeeklyLabels": [], "spxWeeklyClose": []}),
        "leadingIndicators": leading_indicators,
        "riskIndicators": risk_indicators,
        "newsItems": [],  # News comes from separate API
    }

    print(f"\nUpserting to economic_data...")
    sb.table("economic_data").upsert({
        "id": "latest",
        "report_date": today,
        "report_week": iso_week,
        "data": report_data,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }, on_conflict="id").execute()

    print("Done.")


if __name__ == "__main__":
    main()
