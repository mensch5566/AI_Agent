#!/usr/bin/env python3
"""
Anchor Checker — 檢查 Supabase research_todos 的 anchor 是否與報告 JSON 內容一致。

用法：
  python3 Tools/research-tools/anchor-checker/check_anchors.py [TICKER]        # 檢查
  python3 Tools/research-tools/anchor-checker/check_anchors.py --fix [TICKER]   # 自動修正 offset 偏移

檢查項目：
  1. blockId 是否存在於報告 JSON 中
  2. subAnchor 指向的元素是否存在（如 paragraph-1）
  3. textFragment 是否在 textOffset 位置匹配

--fix 模式：
  🟡 offset 偏移 → 自動更新 Supabase 中的 textOffset
  🔴 嚴重問題（block/element/fragment 消失） → 僅報告，不自動修正
"""

import json
import os
import re
import ssl
import sys
import urllib.request

# ── Config ──────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
REPORTS_DIR = os.path.join(PROJECT_ROOT, "public", "data", "equity-research")
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


def load_env():
    """Read .env file and return dict."""
    env = {}
    if not os.path.exists(ENV_FILE):
        print(f"❌ .env not found at {ENV_FILE}")
        sys.exit(1)
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def fetch_todos(env, ticker=None):
    """Fetch research_todos from Supabase REST API."""
    url = f"{env['NEXT_PUBLIC_SUPABASE_URL']}/rest/v1/research_todos?select=id,ticker,title,anchor"
    if ticker:
        url += f"&ticker=eq.{ticker}"
    url += "&anchor=not.is.null"

    req = urllib.request.Request(url, headers={
        "apikey": env["NEXT_PUBLIC_SUPABASE_ANON_KEY"],
        "Authorization": f"Bearer {env['NEXT_PUBLIC_SUPABASE_ANON_KEY']}",
    })
    with urllib.request.urlopen(req, context=SSL_CTX) as resp:
        return json.loads(resp.read())


def patch_todo(env, todo_id, anchors):
    """Update a todo's anchor array in Supabase."""
    url = f"{env['NEXT_PUBLIC_SUPABASE_URL']}/rest/v1/research_todos?id=eq.{todo_id}"
    body = json.dumps({"anchor": anchors}).encode()
    req = urllib.request.Request(url, data=body, method="PATCH", headers={
        "apikey": env["NEXT_PUBLIC_SUPABASE_ANON_KEY"],
        "Authorization": f"Bearer {env['NEXT_PUBLIC_SUPABASE_ANON_KEY']}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    })
    with urllib.request.urlopen(req, context=SSL_CTX) as resp:
        return resp.status


def load_report(ticker):
    """Load report JSON."""
    path = os.path.join(REPORTS_DIR, f"{ticker}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def strip_inline_markdown(text):
    """Remove **bold** and __underline__ markers to get plain textContent."""
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    return text


def build_block_index(report):
    """Build a dict: block_id -> block data."""
    index = {}
    for chapter in report.get("chapters", []):
        for section in chapter.get("sections", []):
            for block in section.get("blocks", []):
                if block.get("id"):
                    index[block["id"]] = block
    return index


def resolve_sub_anchor_text(block, sub_anchor):
    """Given a block and sub_anchor like 'paragraph-1', return the plain text content."""
    match = re.match(r'^(\w+)-(\d+)$', sub_anchor)
    if not match:
        return None

    element_type = match.group(1)
    idx = int(match.group(2))

    if element_type == "paragraph":
        paragraphs = block.get("paragraphs", [])
        if idx < len(paragraphs):
            return strip_inline_markdown(paragraphs[idx])
    elif element_type == "bullet":
        bullets = block.get("bullets", {}).get("items", [])
        if idx < len(bullets):
            return strip_inline_markdown(bullets[idx])
    elif element_type == "table":
        table = block.get("table")
        if table:
            parts = []
            for header in table.get("headers", []):
                parts.append(str(header))
            for row in table.get("rows", []):
                for cell in row:
                    parts.append(str(cell))
            return "".join(parts)

    return None


def get_block_full_text(block):
    """Get the full textContent of a block (all paragraphs + bullets + table)."""
    parts = []
    if block.get("title"):
        parts.append(strip_inline_markdown(block["title"]))
    for p in block.get("paragraphs", []):
        parts.append(strip_inline_markdown(p))
    for item in block.get("bullets", {}).get("items", []):
        parts.append(strip_inline_markdown(item))
    table = block.get("table")
    if table:
        for header in table.get("headers", []):
            parts.append(str(header))
        for row in table.get("rows", []):
            for cell in row:
                parts.append(str(cell))
    return "".join(parts)


# ── Issue types ─────────────────────────────────────────────────
ISSUE_BLOCK_MISSING = "block_missing"
ISSUE_SUB_MISSING = "sub_missing"
ISSUE_FRAGMENT_MISSING = "fragment_missing"
ISSUE_OFFSET_DRIFT = "offset_drift"


def check_anchor(anchor, block_index):
    """Check a single anchor. Returns (issue_type, message, fix_data) or None."""
    block_id = anchor.get("blockId")
    sub_anchor = anchor.get("subAnchor")
    text_fragment = anchor.get("textFragment")
    text_offset = anchor.get("textOffset")

    if not block_id:
        return None

    # Check 1: blockId exists
    if block_id not in block_index:
        return (ISSUE_BLOCK_MISSING,
                f"🔴 blockId '{block_id}' 不存在於報告中", None)

    block = block_index[block_id]

    # Check 2: subAnchor element exists
    if sub_anchor:
        text = resolve_sub_anchor_text(block, sub_anchor)
        if text is None:
            return (ISSUE_SUB_MISSING,
                    f"🔴 subAnchor '{sub_anchor}' 在 block '{block_id}' 中找不到對應元素", None)
    else:
        text = get_block_full_text(block)

    # Check 3: textFragment + textOffset
    if text_fragment:
        anchor_ref = f"{block_id}{'--' + sub_anchor if sub_anchor else ''}"
        if text_fragment not in text:
            return (ISSUE_FRAGMENT_MISSING,
                    f"🔴 textFragment '{text_fragment}' 在元素中完全找不到"
                    f"\n     anchor: {anchor_ref}", None)
        elif text_offset is not None:
            actual = text[text_offset:text_offset + len(text_fragment)]
            if actual != text_fragment:
                correct_pos = text.find(text_fragment)
                return (ISSUE_OFFSET_DRIFT,
                        f"🟡 textOffset 偏移：'{text_fragment}' 預期在 offset={text_offset}，"
                        f"實際在 offset={correct_pos}"
                        f"\n     anchor: {anchor_ref}",
                        correct_pos)  # fix_data = correct offset

    return None


def main():
    # Parse args
    fix_mode = "--fix" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ticker_filter = args[0].upper() if args else None

    env = load_env()
    todos = fetch_todos(env, ticker_filter)

    if not todos:
        print("✅ 沒有帶 anchor 的 To-Do 項目" + (f"（{ticker_filter}）" if ticker_filter else ""))
        return

    # Group by ticker
    by_ticker = {}
    for todo in todos:
        by_ticker.setdefault(todo["ticker"], []).append(todo)

    total_issues = 0
    total_fixed = 0

    for ticker, items in sorted(by_ticker.items()):
        report = load_report(ticker)
        if not report:
            print(f"⚠️  {ticker}: 報告 JSON 不存在，跳過")
            continue

        block_index = build_block_index(report)
        ticker_issues = []

        for todo in items:
            anchors = todo.get("anchor", [])
            if not anchors:
                continue

            anchors_modified = False

            for ai, anchor in enumerate(anchors):
                result = check_anchor(anchor, block_index)
                if not result:
                    continue

                issue_type, message, fix_data = result
                ticker_issues.append(f"  [{todo['title']}] {message}")

                # Auto-fix offset drift
                if fix_mode and issue_type == ISSUE_OFFSET_DRIFT and fix_data is not None:
                    anchors[ai]["textOffset"] = fix_data
                    anchors_modified = True
                    ticker_issues[-1] += f"\n     → ✅ 已修正 textOffset 為 {fix_data}"

            if anchors_modified:
                status = patch_todo(env, todo["id"], anchors)
                if status < 300:
                    total_fixed += 1
                else:
                    ticker_issues.append(f"  [{todo['title']}] ❌ Supabase PATCH 失敗 (status {status})")

        if ticker_issues:
            print(f"\n📋 {ticker}:")
            for issue in ticker_issues:
                print(issue)
            total_issues += len([i for i in ticker_issues if "🔴" in i or "🟡" in i])
        else:
            print(f"✅ {ticker}: 所有 anchor 正常")

    if total_fixed:
        print(f"\n🔧 已自動修正 {total_fixed} 筆 todo 的 textOffset")
    if total_issues and not fix_mode:
        print(f"\n⚠️  共發現 {total_issues} 個問題")
        print(f"💡 執行 --fix 可自動修正 offset 偏移")
        sys.exit(1)
    elif total_issues == 0 or (fix_mode and all("🔴" not in i for t in by_ticker.values() for i in [])):
        print(f"\n✅ 全部通過")


if __name__ == "__main__":
    main()
