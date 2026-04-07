"""
Dollar Volume Ingestion → Supabase
===================================
用 screener.py 的核心邏輯，一次跑 1/5/10 天三種 timeframe，
將 top 50 寫入 Supabase dollar_volume table。

用法:
  set -a; source .env; set +a
  uv run --with finvizfinance --with yfinance --with pandas --with supabase \
    python3 Tools/research-tools/dollar-volume-screener/scripts/ingest_dv.py
"""

import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf
from finvizfinance.screener.overview import Overview
from supabase import create_client

TOP_N = 50
FETCH_LIMIT = 500
TIMEFRAMES = [1, 5, 10]


def fetch_candidates(limit: int = FETCH_LIMIT) -> pd.DataFrame:
    """從 Finviz 拉取 volume 前 N 名股票。"""
    foverview = Overview()
    df = foverview.screener_view(order="Volume", limit=limit, ascend=False, verbose=0)
    df["Is_ETF"] = df["Industry"].str.contains(
        "Exchange Traded Fund", case=False, na=False
    )
    return df


def calc_dollar_volume(tickers: list[str], days: int) -> pd.DataFrame:
    """計算多日 dollar volume。"""
    calendar_days = days * 2 + 5
    start_date = (datetime.now() - timedelta(days=calendar_days)).strftime("%Y-%m-%d")

    data = yf.download(
        tickers, start=start_date, progress=False, group_by="ticker", threads=True
    )

    results = []
    for ticker in tickers:
        try:
            tk_data = data[ticker] if len(tickers) > 1 else data
            tk_data = tk_data.dropna(subset=["Close", "Volume"]).tail(days)
            if len(tk_data) == 0:
                continue

            daily_dv = tk_data["Close"] * tk_data["Volume"]
            total_dv = daily_dv.sum()
            actual_days = len(tk_data)

            results.append({
                "Ticker": ticker,
                "Dollar_Volume": total_dv,
                "Avg_Daily_DV": total_dv / actual_days,
                "Total_Volume": int(tk_data["Volume"].sum()),
                "Last_Price": float(tk_data["Close"].iloc[-1]),
                "Days": actual_days,
            })
        except Exception:
            continue

    df = pd.DataFrame(results)
    return df.sort_values("Dollar_Volume", ascending=False).reset_index(drop=True)


def main():
    url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("ERROR: NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        sys.exit(1)

    sb = create_client(url, key)

    # Step 1: Finviz candidates
    print(f"[1/3] Fetching top {FETCH_LIMIT} by volume from Finviz...")
    candidates = fetch_candidates(FETCH_LIMIT)
    meta = candidates[["Ticker", "Company", "Sector", "Industry", "Is_ETF"]].copy()
    tickers = candidates["Ticker"].tolist()

    # Step 2: yfinance — 用最大天數(10)一次抓，再切片算 1/5/10
    max_days = max(TIMEFRAMES)
    print(f"[2/3] Downloading {max_days}-day history for {len(tickers)} tickers via yfinance...")
    calendar_days = max_days * 2 + 5
    start_date = (datetime.now() - timedelta(days=calendar_days)).strftime("%Y-%m-%d")

    raw_data = yf.download(
        tickers, start=start_date, progress=False, group_by="ticker", threads=True
    )

    today_str = datetime.now().strftime("%Y-%m-%d")
    all_rows = []

    for days in TIMEFRAMES:
        results = []
        for ticker in tickers:
            try:
                tk_data = raw_data[ticker] if len(tickers) > 1 else raw_data
                tk_data = tk_data.dropna(subset=["Close", "Volume"]).tail(days)
                if len(tk_data) == 0:
                    continue

                daily_dv = tk_data["Close"] * tk_data["Volume"]
                total_dv = daily_dv.sum()
                actual_days = len(tk_data)

                results.append({
                    "Ticker": ticker,
                    "Dollar_Volume": float(total_dv),
                    "Avg_Daily_DV": float(total_dv / actual_days),
                    "Total_Volume": int(tk_data["Volume"].sum()),
                    "Last_Price": float(tk_data["Close"].iloc[-1]),
                    "Days": actual_days,
                })
            except Exception:
                continue

        df = pd.DataFrame(results)
        df = df.sort_values("Dollar_Volume", ascending=False).reset_index(drop=True)
        df = df.merge(meta, on="Ticker", how="left")
        df = df.head(TOP_N)

        for _, row in df.iterrows():
            all_rows.append({
                "ticker": row["Ticker"],
                "company": row.get("Company"),
                "sector": row.get("Sector"),
                "industry": row.get("Industry"),
                "last_price": round(row["Last_Price"], 2),
                "total_volume": row["Total_Volume"],
                "dollar_volume": round(row["Dollar_Volume"], 2),
                "avg_daily_dv": round(row["Avg_Daily_DV"], 2),
                "days": days,
                "is_etf": bool(row.get("Is_ETF", False)),
                "fetched_at": today_str,
            })

        print(f"  {days}D: {len(df)} tickers (top={df['Ticker'].iloc[0] if len(df) > 0 else 'N/A'})")

    # Step 3: Upsert to Supabase
    print(f"[3/3] Upserting {len(all_rows)} rows to dollar_volume...")
    # Upsert in batches of 50
    for i in range(0, len(all_rows), 50):
        batch = all_rows[i : i + 50]
        sb.table("dollar_volume").upsert(
            batch, on_conflict="ticker,days,fetched_at"
        ).execute()

    print("Done.")


if __name__ == "__main__":
    main()
