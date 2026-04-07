"""
Migrate financials JSON → Supabase
Tables:
  financial_companies  (ticker, company, cik, exchange, currency, fiscal_year_end_month, last_updated, notes)
  financial_facts      (ticker, period, period_end, statement, metric, dimension, value, unit, source)
    - GAAP 三表: dimension = '' (default)
    - segments:   statement = 'segments', metric = subsection (e.g. 'revenue_by_product'), dimension = 'Datacenter'
    - non_gaap:   statement = 'non_gaap', metric = e.g. 'adjusted_eps_diluted', dimension = ''
"""

import json
from pathlib import Path

# ── read .env ────────────────────────────────────────────────────────────────
env = {}
env_path = Path(__file__).parents[1] / ".env"
with open(env_path) as f:
    for line in f:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k] = v

SUPABASE_URL = env.get("NEXT_PUBLIC_SUPABASE_URL") or env.get("SUPABASE_URL")
SUPABASE_KEY = env.get("SUPABASE_SERVICE_ROLE_KEY")

from supabase import create_client  # noqa: E402

client = create_client(SUPABASE_URL, SUPABASE_KEY)

DATA_DIR = Path(__file__).parents[1] / "public" / "data" / "financials"

# ── helpers ──────────────────────────────────────────────────────────────────

def upsert_batch(table: str, rows: list[dict], batch_size: int = 500) -> int:
    total = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        client.table(table).upsert(batch).execute()
        total += len(batch)
    return total


# ── migrate financials.json ──────────────────────────────────────────────────

def migrate_financials(ticker: str, path: Path):
    with open(path) as f:
        data = json.load(f)

    meta = data.get("metadata", {})

    # financial_companies
    company_row = {
        "ticker": ticker,
        "company": meta.get("company"),
        "exchange": meta.get("exchange"),
        "cik": meta.get("cik"),
        "fiscal_year_end_month": meta.get("fiscal_year_end_month"),
        "currency": meta.get("currency"),
        "last_updated": meta.get("last_updated"),
        "notes": json.dumps(meta.get("notes")) if meta.get("notes") else None,
    }
    client.table("financial_companies").upsert(company_row).execute()
    print(f"  [{ticker}] companies: 1 row")

    # ── IS + BS from long_format ──
    long_format = data.get("long_format", [])
    facts_rows = []
    if long_format:
        for row in long_format:
            facts_rows.append({
                "ticker": ticker,
                "period": row["period"],
                "period_end": row.get("period_end") or None,
                "statement": row["statement"],
                "metric": row["metric"],
                "dimension": "",
                "value": row["value"],
                "unit": row.get("unit"),
            })

    # ── Cash Flow (nested → long format) ──
    cf = data.get("cash_flow_statement", {})
    filings = data.get("filings", {})
    unit = meta.get("unit")

    cf_section_map = {
        "operating_activities": "cash_flow_operating",
        "investing_activities": "cash_flow_investing",
        "financing_activities": "cash_flow_financing",
    }
    cf_summary_keys = [
        "fx_effect_on_cash", "fx_effect", "net_change_in_cash",
        "beginning_cash", "ending_cash", "free_cash_flow",
    ]

    for nested_key, stmt_name in cf_section_map.items():
        section = cf.get(nested_key, {})
        for metric, vals in section.items():
            if not isinstance(vals, dict):
                continue
            for period, value in vals.items():
                if value is None:
                    continue
                facts_rows.append({
                    "ticker": ticker,
                    "period": period,
                    "period_end": filings.get(period, {}).get("period_end"),
                    "statement": stmt_name,
                    "metric": metric,
                    "dimension": "",
                    "value": value,
                    "unit": unit,
                })

    for key in cf_summary_keys:
        vals = cf.get(key)
        if not isinstance(vals, dict):
            continue
        for period, value in vals.items():
            if value is None:
                continue
            facts_rows.append({
                "ticker": ticker,
                "period": period,
                "period_end": filings.get(period, {}).get("period_end"),
                "statement": "cash_flow_summary",
                "metric": key,
                "dimension": "",
                "value": value,
                "unit": unit,
            })

    # ── Financial Ratios (nested: period → {metric: value}) ──
    ratios = data.get("financial_ratios", {})
    for period, metrics in ratios.items():
        if not isinstance(metrics, dict):
            continue
        for metric, value in metrics.items():
            if value is None:
                continue
            facts_rows.append({
                "ticker": ticker,
                "period": period,
                "period_end": filings.get(period, {}).get("period_end"),
                "statement": "financial_ratios",
                "metric": metric,
                "dimension": "",
                "value": value,
            })

    if facts_rows:
        n = upsert_batch("financial_facts", facts_rows)
        print(f"  [{ticker}] facts: {n} rows")
    else:
        print(f"  [{ticker}] facts: no data")


# ── migrate supplemental.json ────────────────────────────────────────────────

def migrate_supplemental(ticker: str, path: Path):
    with open(path) as f:
        data = json.load(f)

    rows = []

    # segments: {subsection: {period: {dimension: {value, source}}}}
    segments = data.get("segments", {})
    for subsection, periods in segments.items():
        for period, dimensions in periods.items():
            if not isinstance(dimensions, dict):
                continue
            for dimension, vobj in dimensions.items():
                if not isinstance(vobj, dict):
                    continue
                rows.append({
                    "ticker": ticker,
                    "period": period,
                    "statement": "segments",
                    "metric": subsection,
                    "dimension": dimension,
                    "value": vobj.get("value"),
                    "unit": vobj.get("unit"),
                    "source": vobj.get("source"),
                })

    # non_gaap: {metric: {period: {value, source}}}
    non_gaap = data.get("non_gaap", {})
    for metric, periods in non_gaap.items():
        if not isinstance(periods, dict):
            continue
        for period, vobj in periods.items():
            if not isinstance(vobj, dict):
                continue
            rows.append({
                "ticker": ticker,
                "period": period,
                "statement": "non_gaap",
                "metric": metric,
                "dimension": "",
                "value": vobj.get("value"),
                "unit": vobj.get("unit"),
                "source": vobj.get("source"),
            })

    if rows:
        n = upsert_batch("financial_facts", rows)
        print(f"  [{ticker}] facts (supplemental): {n} rows")
    else:
        print(f"  [{ticker}] supplemental: no data")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    tickers = [d.name for d in DATA_DIR.iterdir() if d.is_dir()]
    print(f"Found tickers: {tickers}\n")

    for ticker in sorted(tickers):
        ticker_dir = DATA_DIR / ticker
        fin_path = ticker_dir / f"{ticker}_financials.json"
        sup_path = ticker_dir / f"{ticker}_supplemental.json"

        if fin_path.exists():
            print(f"Migrating {ticker} financials...")
            migrate_financials(ticker, fin_path)
        else:
            print(f"  [{ticker}] no financials.json, skip")

        if sup_path.exists():
            print(f"Migrating {ticker} supplemental...")
            migrate_supplemental(ticker, sup_path)

    print("\nDone.")


if __name__ == "__main__":
    main()
