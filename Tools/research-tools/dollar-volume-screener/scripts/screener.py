"""
Dollar Volume Screener
======================
從 Finviz 拉取美股成交量前 N 名作為候選，再用 yfinance 拉歷史資料
計算多日 dollar volume 加總並排名。

用法:
  uv run --with finvizfinance --with pandas --with yfinance python3 screener.py [OPTIONS]

Options:
  --days N         計算最近 N 個交易日的 dollar volume 加總 (default: 10)
  --top N          顯示前 N 名 (default: 30)
  --fetch N        從 Finviz 拉取 volume 前 N 名作為候選池 (default: 500)
  --no-etf         排除 ETF
  --etf-only       只顯示 ETF
  --min-price P    最低股價門檻 (default: 0)
  --sector S       只顯示特定 sector（部分匹配，不分大小寫）
  --csv FILE       輸出 CSV 檔案
  --quiet          只輸出表格，不印標題說明
"""

import argparse
import sys
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf
from finvizfinance.screener.overview import Overview


def fetch_candidates(limit: int = 500) -> pd.DataFrame:
    """從 Finviz 拉取 volume 前 N 名股票作為候選池。"""
    foverview = Overview()
    df = foverview.screener_view(
        order="Volume", limit=limit, ascend=False, verbose=0
    )
    return df


def calc_multi_day_dollar_volume(
    tickers: list[str], days: int = 10, quiet: bool = False
) -> pd.DataFrame:
    """用 yfinance 拉歷史資料，計算多日 dollar volume 加總。

    Returns DataFrame with columns: Ticker, Dollar_Volume, Avg_Daily_DV, Days, Last_Price
    """
    # 多抓一些天數來確保有足夠交易日（假日、weekend）
    calendar_days = days * 2 + 5
    start_date = (datetime.now() - timedelta(days=calendar_days)).strftime("%Y-%m-%d")

    if not quiet:
        print(
            f"正在用 yfinance 拉取 {len(tickers)} 支標的最近 {days} 個交易日資料...",
            file=sys.stderr,
        )

    # 批量下載
    data = yf.download(
        tickers, start=start_date, progress=False, group_by="ticker", threads=True
    )

    results = []
    for ticker in tickers:
        try:
            if len(tickers) == 1:
                tk_data = data
            else:
                tk_data = data[ticker]

            # 取最近 N 個交易日
            tk_data = tk_data.dropna(subset=["Close", "Volume"])
            tk_data = tk_data.tail(days)

            if len(tk_data) == 0:
                continue

            # dollar volume = close × volume，逐日加總
            daily_dv = tk_data["Close"] * tk_data["Volume"]
            total_dv = daily_dv.sum()
            actual_days = len(tk_data)
            avg_daily_dv = total_dv / actual_days
            last_price = tk_data["Close"].iloc[-1]
            total_volume = tk_data["Volume"].sum()
            date_start = tk_data.index[0].strftime("%m/%d")
            date_end = tk_data.index[-1].strftime("%m/%d")

            results.append(
                {
                    "Ticker": ticker,
                    "Dollar_Volume": total_dv,
                    "Avg_Daily_DV": avg_daily_dv,
                    "Total_Volume": total_volume,
                    "Last_Price": last_price,
                    "Days": actual_days,
                    "Period": f"{date_start}~{date_end}",
                }
            )
        except Exception:
            continue

    df = pd.DataFrame(results)
    df = df.sort_values("Dollar_Volume", ascending=False).reset_index(drop=True)
    df.index += 1
    df.index.name = "Rank"
    return df


def format_number(n: float) -> str:
    """格式化大數字：B / M / K。"""
    if pd.isna(n):
        return "N/A"
    abs_n = abs(n)
    if abs_n >= 1e9:
        return f"${n / 1e9:.2f}B"
    elif abs_n >= 1e6:
        return f"${n / 1e6:.1f}M"
    elif abs_n >= 1e3:
        return f"${n / 1e3:.0f}K"
    else:
        return f"${n:.0f}"


def format_volume(n: float) -> str:
    """格式化成交量。"""
    if pd.isna(n):
        return "N/A"
    if n >= 1e9:
        return f"{n / 1e9:.2f}B"
    elif n >= 1e6:
        return f"{n / 1e6:.1f}M"
    elif n >= 1e3:
        return f"{n / 1e3:.0f}K"
    else:
        return f"{n:.0f}"


def main():
    parser = argparse.ArgumentParser(description="Dollar Volume Screener")
    parser.add_argument("--days", type=int, default=10, help="計算最近 N 個交易日")
    parser.add_argument("--top", type=int, default=30, help="顯示前 N 名")
    parser.add_argument("--fetch", type=int, default=500, help="候選池大小")
    parser.add_argument("--no-etf", action="store_true", help="排除 ETF")
    parser.add_argument("--etf-only", action="store_true", help="只顯示 ETF")
    parser.add_argument("--min-price", type=float, default=0, help="最低股價門檻")
    parser.add_argument("--sector", type=str, default="", help="篩選 sector")
    parser.add_argument("--csv", type=str, default="", help="輸出 CSV")
    parser.add_argument("--quiet", action="store_true", help="安靜模式")
    args = parser.parse_args()

    # Step 1: 從 Finviz 拿候選名單 + ETF/Sector 資訊
    if not args.quiet:
        print(f"[1/2] 從 Finviz 拉取 volume 前 {args.fetch} 名...", file=sys.stderr)

    candidates = fetch_candidates(limit=args.fetch)

    # 標記 ETF
    candidates["Is_ETF"] = candidates["Industry"].str.contains(
        "Exchange Traded Fund", case=False, na=False
    )

    # 先做 ETF/Sector 過濾（減少 yfinance 需要拉的量）
    if args.no_etf:
        candidates = candidates[~candidates["Is_ETF"]]
    if args.etf_only:
        candidates = candidates[candidates["Is_ETF"]]
    if args.sector:
        candidates = candidates[
            candidates["Sector"].str.contains(args.sector, case=False, na=False)
        ]
    if args.min_price > 0:
        candidates = candidates[candidates["Price"] >= args.min_price]

    # 保留 metadata 供後續 merge
    meta = candidates[["Ticker", "Company", "Sector", "Industry", "Is_ETF"]].copy()

    tickers = candidates["Ticker"].tolist()

    # Step 2: yfinance 拉歷史資料計算多日 dollar volume
    if not args.quiet:
        print(f"[2/2] 計算最近 {args.days} 個交易日 dollar volume...", file=sys.stderr)

    dv = calc_multi_day_dollar_volume(tickers, days=args.days, quiet=args.quiet)

    # Merge metadata
    dv = dv.merge(meta, on="Ticker", how="left")

    # 重排排名
    dv = dv.sort_values("Dollar_Volume", ascending=False).reset_index(drop=True)
    dv.index += 1
    dv.index.name = "Rank"

    # 取 top N
    result = dv.head(args.top)

    # CSV output
    if args.csv:
        out_cols = [
            "Ticker", "Company", "Sector", "Last_Price",
            "Total_Volume", "Dollar_Volume", "Avg_Daily_DV",
            "Days", "Period", "Is_ETF",
        ]
        result[out_cols].to_csv(args.csv)
        if not args.quiet:
            print(f"已輸出至 {args.csv}", file=sys.stderr)

    # Console output
    if not args.quiet:
        today = datetime.now().strftime("%Y-%m-%d")
        etf_label = " (ETF only)" if args.etf_only else " (no ETF)" if args.no_etf else ""
        period = result["Period"].iloc[0] if len(result) > 0 else ""
        print(f"\n{'='*78}")
        print(
            f"  Dollar Volume Top {args.top}{etf_label}"
            f" — {args.days}日加總 ({period})"
        )
        print(f"{'='*78}")

    # 格式化顯示
    display = result[
        ["Ticker", "Last_Price", "Total_Volume", "Dollar_Volume", "Avg_Daily_DV", "Is_ETF"]
    ].copy()
    display["Last_Price"] = display["Last_Price"].apply(lambda x: f"${x:.2f}" if pd.notna(x) else "N/A")
    display["Total_Volume"] = display["Total_Volume"].apply(format_volume)
    display["Dollar_Volume"] = display["Dollar_Volume"].apply(format_number)
    display["Avg_Daily_DV"] = display["Avg_Daily_DV"].apply(format_number)
    display["Type"] = display["Is_ETF"].apply(lambda x: "ETF" if x else "Stock")
    display = display.drop(columns=["Is_ETF"])
    display.columns = ["Ticker", "Price", "10D Vol", "10D $ Vol", "Avg/Day", "Type"]

    print(display.to_string())


if __name__ == "__main__":
    main()
