"""
Market Indices Fetcher
======================
從 yfinance 拉取主要指數 ETF 報價，寫入 Supabase market_indices table。

用法:
  # 需先 source .env 取得 Supabase credentials
  set -a; source .env; set +a
  uv run --with yfinance --with supabase python3 Tools/research-tools/market-indices/fetch_market.py
"""

import os
import sys
from datetime import datetime, timezone

import yfinance as yf
from supabase import create_client

INDICES = [
    {"id": "dow_jones", "symbol": "DIA", "name": "Dow Jones"},
    {"id": "sp500", "symbol": "SPY", "name": "S&P 500"},
    {"id": "nasdaq", "symbol": "QQQ", "name": "NASDAQ"},
    {"id": "russell2000", "symbol": "IWM", "name": "Russell 2000"},
    {"id": "dxy", "symbol": "UUP", "name": "US Dollar Index"},
]


def fetch_and_upsert():
    url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("ERROR: NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        sys.exit(1)

    sb = create_client(url, key)
    symbols = [idx["symbol"] for idx in INDICES]
    symbol_map = {idx["symbol"]: idx for idx in INDICES}

    print(f"Fetching quotes for {symbols}...")
    tickers = yf.Tickers(" ".join(symbols))

    now = datetime.now(timezone.utc).isoformat()
    rows = []

    for sym in symbols:
        info = tickers.tickers[sym].fast_info
        prev_close = info.get("previousClose") or info.get("previous_close")
        price = info.get("lastPrice") or info.get("last_price")
        day_high = info.get("dayHigh") or info.get("day_high")
        day_low = info.get("dayLow") or info.get("day_low")
        day_open = info.get("open")

        if price is None or prev_close is None:
            # fallback: try .info dict
            full_info = tickers.tickers[sym].info
            price = price or full_info.get("regularMarketPrice")
            prev_close = prev_close or full_info.get("regularMarketPreviousClose")
            day_high = day_high or full_info.get("regularMarketDayHigh")
            day_low = day_low or full_info.get("regularMarketDayLow")
            day_open = day_open or full_info.get("regularMarketOpen")

        if price is None:
            print(f"  WARN: {sym} - no price data, skipping")
            continue

        change = round(price - prev_close, 4) if prev_close else None
        change_pct = round(change / prev_close * 100, 2) if prev_close and change is not None else None

        idx = symbol_map[sym]
        row = {
            "id": idx["id"],
            "symbol": sym,
            "name": idx["name"],
            "price": round(price, 2),
            "change": change,
            "change_pct": change_pct,
            "prev_close": round(prev_close, 2) if prev_close else None,
            "high": round(day_high, 3) if day_high else None,
            "low": round(day_low, 3) if day_low else None,
            "open": round(day_open, 2) if day_open else None,
            "fetched_at": now,
        }
        rows.append(row)
        print(f"  {sym:5s}  ${price:>10.2f}  {change_pct:>+6.2f}%")

    if not rows:
        print("ERROR: No data fetched")
        sys.exit(1)

    print(f"\nUpserting {len(rows)} rows to market_indices...")
    sb.table("market_indices").upsert(rows, on_conflict="id").execute()
    print("Done.")


if __name__ == "__main__":
    fetch_and_upsert()
