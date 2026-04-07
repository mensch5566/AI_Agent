#!/usr/bin/env python3
"""
Import historical stock price data into Supabase.
Usage: python3 import_stock_prices.py --ticker SPY --years 5
"""

import yfinance as yf
from supabase import create_client
from datetime import datetime, timedelta
import argparse

SUPABASE_URL = "https://zpriwdyjmqvbtaektnlq.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inpwcml3ZHlqbXF2YnRhZWt0bmxxIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MzQ4OTYzMywiZXhwIjoyMDg5MDY1NjMzfQ.VSsBqjOgZPK142kBI3FjbezmJ3ShBtk2XD-LZo2wSmQ"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def fetch_stock_data(ticker: str, years: int = 5):
    """Fetch historical stock data from Yahoo Finance."""
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=365 * years)

    print(f"📊 Fetching {ticker} from {start_date} to {end_date}...")

    stock = yf.Ticker(ticker)
    df = stock.history(start=start_date, end=end_date)

    if df.empty:
        raise ValueError(f"No data found for {ticker}")

    print(f"✓ Fetched {len(df)} records")
    return df


def insert_stock_data(ticker: str, df):
    """Insert stock data into Supabase via REST API."""
    # Reset index to make date a column
    df = df.reset_index()

    records = []
    for _, row in df.iterrows():
        records.append({
            "ticker": ticker.upper(),
            "date": row['Date'].strftime('%Y-%m-%d'),
            "open": float(round(row['Open'], 4)),
            "high": float(round(row['High'], 4)),
            "low": float(round(row['Low'], 4)),
            "close": float(round(row['Close'], 4)),
            "volume": int(row['Volume']),
        })

    # Insert in batches of 1000
    batch_size = 1000
    for i in range(0, len(records), batch_size):
        batch = records[i:i+batch_size]
        try:
            result = supabase.table('stock_prices').upsert(batch).execute()
            print(f"✓ Inserted batch {i//batch_size + 1} ({len(batch)} records)")
        except Exception as e:
            print(f"⚠️  Batch {i//batch_size + 1} error: {e}")

    print(f"✓ Total {len(records)} records inserted into stock_prices")


def main():
    parser = argparse.ArgumentParser(description="Import stock prices to Supabase")
    parser.add_argument("--ticker", default="SPY", help="Stock ticker (default: SPY)")
    parser.add_argument("--years", type=int, default=5, help="Years of history (default: 5)")
    args = parser.parse_args()

    try:
        print(f"🔌 Connecting to Supabase...")

        # Fetch data from Yahoo Finance
        df = fetch_stock_data(args.ticker, args.years)

        # Insert into Supabase
        insert_stock_data(args.ticker, df)

        print(f"✅ {args.ticker} data import complete!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)


if __name__ == "__main__":
    main()
