"""
Migrate financials JSON → Supabase
Tables:
  financial_companies  (ticker, company, exchange, cik, fiscal_year_end_month, currency, unit, last_updated, data_source)
  financial_facts      (ticker, period, period_end, statement, metric, value, unit)
  financial_supplemental (ticker, period, section, subsection, dimension, value, unit, source)
"""

import json
import os
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

    # financial_facts from long_format
    long_format = data.get("long_format", [])
    if long_format:
        facts_rows = [
            {
                "ticker": ticker,
                "period": row["period"],
                "period_end": row.get("period_end") or None,
                "statement": row["statement"],
                "metric": row["metric"],
                "value": row["value"],
                "unit": row.get("unit"),
            }
            for row in long_format
        ]
        n = upsert_batch("financial_facts", facts_rows)
        print(f"  [{ticker}] financial_facts: {n} rows")
    else:
        print(f"  [{ticker}] financial_facts: no long_format data")


# ── migrate supplemental.json ────────────────────────────────────────────────

def migrate_supplemental(ticker: str, path: Path):
    with open(path) as f:
        data = json.load(f)

    rows = []

    # segments: {section_name: {period: {dimension: {value, source}}}}
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
                    "section": "segments",
                    "subsection": subsection,
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
                "section": "non_gaap",
                "subsection": metric,
                "dimension": "",
                "value": vobj.get("value"),
                "unit": vobj.get("unit"),
                "source": vobj.get("source"),
            })

    if rows:
        n = upsert_batch("financial_supplemental", rows)
        print(f"  [{ticker}] financial_supplemental: {n} rows")
    else:
        print(f"  [{ticker}] financial_supplemental: no data")


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
