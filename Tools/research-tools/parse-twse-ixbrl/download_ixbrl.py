#!/usr/bin/env python3
"""
從 TWSE 自動下載聯發科所有可用的 XBRL 檔案
"""

import sys
import time
import requests
from pathlib import Path
from lxml import html as html_lib

TWSE_BASE = "https://mopsov.twse.com.tw/server-java/t164sb01"


def download_ixbrl_files(ticker: str, years: list = None) -> dict:
    """從 TWSE 下載 XBRL 檔案"""

    if years is None:
        years = [2025, 2024, 2023]  # 預設下載最近 3 年

    download_dir = Path.home() / "Downloads"
    downloaded = {}

    print(f"📥 從 TWSE 下載 {ticker} 的 XBRL 檔案...\n")

    for year in years:
        for season in [1, 2, 3, 4]:
            period = f"Q{season}_FY{year}"

            print(f"  {period}: ", end="", flush=True)

            try:
                # 查詢頁面
                response = requests.get(
                    TWSE_BASE,
                    params={
                        'step': 1,
                        'CO_ID': ticker,
                        'SYEAR': year,
                        'SSEASON': season,
                        'REPORT_ID': 'C'
                    },
                    timeout=10
                )
                response.raise_for_status()

                # 解析 HTML 尋找下載連結
                root = html_lib.fromstring(response.content)
                links = root.xpath('//a[contains(@href, ".html")]/@href')

                if not links:
                    print("❌ 無檔案")
                    time.sleep(0.5)
                    continue

                # 下載第一個匹配的檔案
                file_url = links[0]
                if not file_url.startswith('http'):
                    file_url = f"https://mopsov.twse.com.tw{file_url}"

                file_response = requests.get(file_url, timeout=30)
                file_response.raise_for_status()

                # 從 URL 提取檔名
                file_name = file_url.split('/')[-1]
                if not file_name.endswith('.html'):
                    file_name = f"tifrs-fr1-m1-ci-cr-{ticker}-{year}Q{season}.html"

                file_path = download_dir / file_name
                file_path.write_bytes(file_response.content)

                print(f"✅ ({len(file_response.content)/1024:.1f}KB)")
                downloaded[period] = str(file_path)

            except requests.exceptions.RequestException as e:
                print(f"❌ {type(e).__name__}")

            time.sleep(1)  # 避免被限速

    print(f"\n✅ 下載完成: {len(downloaded)} 個期別")
    print(f"   位置: {download_dir}")

    return downloaded


def main():
    if len(sys.argv) < 2:
        print("用法: python3 download_ixbrl.py <ticker> [year1 year2...]")
        print("\n範例:")
        print("  python3 download_ixbrl.py 2454          # 下載最近 3 年")
        print("  python3 download_ixbrl.py 2454 2025 2024")
        sys.exit(1)

    ticker = sys.argv[1]
    years = [int(y) for y in sys.argv[2:]] if len(sys.argv) > 2 else [2025, 2024, 2023]

    downloaded = download_ixbrl_files(ticker, years)

    if not downloaded:
        print("\n⚠️ 未下載任何檔案，請確認 ticker 是否正確")
        sys.exit(1)

    print("\n🎯 下一步，執行批量解析:")
    print(f"  python3 batch_parse.py {ticker}")


if __name__ == '__main__':
    main()
