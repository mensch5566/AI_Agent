"""
audit.py — 審計現有財務資料完整性
用法：
    python3 audit.py --ticker MU --base-dir /path/to/financials --start "Q1 FY2024"

輸出（stdout）：
    STATUS: new
    STATUS: up_to_date
    STATUS: missing [Q2_FY2024, Q3_FY2024]
"""

import argparse, json, os, sys
from datetime import date

# Micron 財政年度結束月份 mapping（各公司不同）
# key: ticker, value: fiscal_year_end_month（8 = August）
FISCAL_YEAR_END_MONTHS = {
    "DEFAULT": 12,  # 大多數公司 = 12月
    "MU":  8,
    "NVDA": 1,
    "AAPL": 9,
}

def parse_period(s):
    """Q1 FY2024 → (1, 2024)"""
    s = s.strip().replace("_", " ")
    parts = s.upper().split()
    q = int(parts[0].replace("Q", ""))
    fy = int(parts[1].replace("FY", ""))
    return q, fy

def period_key(q, fy):
    return f"Q{q}_FY{fy}"

def next_period(q, fy):
    if q < 4:
        return q + 1, fy
    else:
        return 1, fy + 1

def get_current_period(ticker):
    """根據今天日期估算最新可用季度（保守估計，留一季緩衝）"""
    today = date.today()
    fy_end_month = FISCAL_YEAR_END_MONTHS.get(ticker.upper(), FISCAL_YEAR_END_MONTHS["DEFAULT"])
    # 簡化：直接用日曆季度近似
    q = (today.month - 1) // 3 + 1
    fy = today.year
    # 往回一季（財報通常落後 6-8 週）
    if q == 1:
        q, fy = 4, fy - 1
    else:
        q -= 1
    return q, fy

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker",   required=True)
    parser.add_argument("--base-dir", required=True)
    parser.add_argument("--start",    required=True, help='e.g. "Q1 FY2024"')
    args = parser.parse_args()

    ticker   = args.ticker.upper()
    base_dir = os.path.expanduser(args.base_dir)
    json_path = os.path.join(base_dir, ticker, f"{ticker}_financials.json")

    start_q, start_fy = parse_period(args.start)
    cur_q,   cur_fy   = get_current_period(ticker)

    # 建立所有期望期間的列表
    expected = []
    q, fy = start_q, start_fy
    while (fy < cur_fy) or (fy == cur_fy and q <= cur_q):
        expected.append(period_key(q, fy))
        q, fy = next_period(q, fy)

    # 如果 JSON 不存在 → 全新
    if not os.path.exists(json_path):
        print("STATUS: new")
        print(f"EXPECTED: {json.dumps(expected)}")
        return

    # 讀取現有 JSON
    with open(json_path) as f:
        data = json.load(f)

    existing = set(data.get("metadata", {}).get("periods", []))
    missing  = [p for p in expected if p not in existing]

    if not missing:
        print("STATUS: up_to_date")
        print(f"PERIODS: {json.dumps(list(existing))}")
    else:
        print("STATUS: missing")
        print(f"MISSING: {json.dumps(missing)}")
        print(f"EXISTING: {json.dumps(sorted(existing))}")

if __name__ == "__main__":
    main()
