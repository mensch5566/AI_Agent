"""
Google News RSS fetcher for news pipeline.

Usage:
  uv run --with feedparser,certifi python3 Tools/research-tools/news-pipeline/fetch_rss.py

Reads ticker configs from tickers.json, fetches Google News RSS (last 24h),
and outputs a JSON array of candidate news items to stdout.

URLs are converted from rss/articles/{base64}?oc=5 → news.google.com/articles/{base64},
which redirects to the original source in browser. No decoding API needed.
"""

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus
import re
from html import unescape

import certifi
import feedparser
import ssl
import urllib.request

TICKERS_FILE = Path(__file__).parent / "tickers.json"

RSS_LOCALES = {
    "US": "hl=en-US&gl=US&ceid=US:en",
    "TW": "hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
}

_ssl_ctx = ssl.create_default_context(cafile=certifi.where())
_opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=_ssl_ctx))


def clean_html(html_text):
    """移除 HTML 標籤，保留純文本"""
    if not html_text:
        return ""
    # 移除 HTML 標籤
    text = re.sub(r'<[^>]+>', '', html_text)
    # 解碼 HTML 實體
    text = unescape(text)
    # 多個空白縮為單個
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def fetch_ticker_rss(ticker: str, query: str, market: str, cutoff: datetime) -> list[dict]:
    locale = RSS_LOCALES.get(market, RSS_LOCALES["US"])
    full_query = f"{query} when:1d"
    url = f"https://news.google.com/rss/search?q={quote_plus(full_query)}&{locale}"

    resp = _opener.open(url, timeout=15)
    feed = feedparser.parse(resp.read())
    items = []

    for entry in feed.entries:
        pub = entry.get("published_parsed")
        if pub:
            pub_dt = datetime(*pub[:6], tzinfo=timezone.utc)
            if pub_dt < cutoff:
                continue
            date_str = pub_dt.strftime("%Y-%m-%d")
        else:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Google News RSS: "Title - Source"
        title = entry.get("title", "")
        source = ""
        if " - " in title:
            parts = title.rsplit(" - ", 1)
            title = parts[0].strip()
            source = parts[1].strip()

        # Convert rss/articles/{base64}?oc=5 → news.google.com/articles/{base64}
        raw_url = entry.get("link", "")
        gn_url = raw_url.replace("rss/articles/", "articles/").split("?")[0]

        items.append({
            "ticker": ticker,
            "title": title,
            "description": clean_html(entry.get("summary", "")),
            "url": gn_url,
            "source": source,
            "date": date_str,
        })

    return items


def main():
    tickers = json.loads(TICKERS_FILE.read_text())

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    all_items = []

    for cfg in tickers:
        ticker = cfg["ticker"]
        query = cfg.get("rss_query", "")
        market = cfg.get("market", "US")
        if not query:
            continue
        try:
            items = fetch_ticker_rss(ticker, query, market, cutoff)
            all_items.extend(items)
            print(f"[INFO] {ticker}: {len(items)} items", file=sys.stderr)
        except Exception as e:
            print(f"[WARN] {ticker} RSS fetch failed: {e}", file=sys.stderr)
        time.sleep(0.5)

    all_items.sort(key=lambda x: x["date"], reverse=True)

    json.dump(all_items, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
