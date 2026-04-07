"""
parse.py — 解析 SEC 10-Q / 10-K HTML，提取財務數據
用法：
    python3 parse.py --file /path/to/filing.htm \
                     --ticker MU --period Q1_FY2026

策略：
  - 不強制對應標準欄位名，直接用財報原始標籤作為 key
  - 用「錨點資料行」定位財務報表（避免誤抓目錄頁碼）
  - 自動定位損益表、資產負債表、現金流量表
  - 第一欄數值 = 當期報告期間的數字

輸出：JSON dict，包含該期間所有可提取的財務指標
"""

import argparse, json, re, sys
from collections import OrderedDict
from html.parser import HTMLParser


# ── HTML → 純文字 ─────────────────────────────────────────────────────────────

class TextExtractor(HTMLParser):
    """從 iXBRL / HTML 中提取純文字（跳過 ix:hidden 和 script/style）"""
    SKIP_TAGS = {"script", "style", "ix:hidden", "ix:header"}

    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        tag_lower = tag.lower()
        if tag_lower in self.SKIP_TAGS:
            self.skip_depth += 1
        if tag_lower in {"br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag.lower() in self.SKIP_TAGS and self.skip_depth > 0:
            self.skip_depth -= 1

    def handle_data(self, data):
        if self.skip_depth == 0:
            stripped = data.strip()
            if stripped:
                self.parts.append(stripped)

    def get_text(self):
        text = " ".join(self.parts)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n", text)
        return text


# ── 數值處理 ──────────────────────────────────────────────────────────────────

# 只比對括號內全為數字的（避免把 "(loss)" "(net)" 誤判為負數）
# 包含 em-dash / en-dash 作為「零值」token
_NUM_TOK = re.compile(
    r'\$\s*\(\s*[\d,]+(?:\.\d+)?\s*\)'           # $ ( 16.6 )
    r'|\$\s*[\d,]+(?:\.\d+)?'                     # $ 74.9
    r'|\(\s*[\d,]+(?:\.\d+)?\s*\)'               # ( 16.6 )
    r'|(?<![a-zA-Z(])\b[\d,]{1,10}(?:\.\d+)?\b(?![a-zA-Z%)])'  # 74.9（不緊跟字母）
    r'|(?<!\w)[—–](?!\w)'                         # — 或 – 代表零值（當期無數字）
)


def clean_number(s: str):
    """'$13,643' / '( 829 )' / '56.7' / '—' → float or None"""
    if not s:
        return None
    s = s.strip().replace("$", "").replace(",", "").replace(" ", "")
    if s in ("—", "–", "\u2014", "\u2013"):      # em-dash / en-dash = 0
        return 0.0
    if s in ("N/A", ""):
        return None
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return None


def row_values(line: str):
    """
    從一行提取所有數值（含 0.0 代表 '—'）。
    第一個元素 = 當期欄位的值。
    若全部都是 0.0 / None → 回傳空 list（代表沒有真實數據的行）。
    """
    all_vals = []
    for tok in _NUM_TOK.findall(line):
        v = clean_number(tok)
        if v is not None:
            all_vals.append(v)
    if not all_vals:
        return []
    # 若全為零（全 "—"）且只有一欄，視為無意義行跳過
    if all(v == 0.0 for v in all_vals) and len(all_vals) == 1:
        return []
    return all_vals


def row_label(line: str) -> str:
    """去掉數值 token 後取得標籤文字"""
    lbl = _NUM_TOK.sub("", line)
    lbl = re.sub(r"[$(),]", " ", lbl)
    lbl = re.sub(r"\s+", " ", lbl).strip(" .:$")
    return lbl


# ── 段落定位（核心改進）───────────────────────────────────────────────────────

def find_section_header(lines, keywords, start_from=0, max_line_len=80):
    """
    找財務報表段落標題行（含 keywords，無數值，行長短）。
    用於定位「CONSOLIDATED BALANCE SHEETS」等真正的報表標題，
    跳過目錄（TOC 有頁碼）和 MD&A 長句。
    回傳行號，或 None。
    """
    for i in range(start_from, len(lines)):
        line = lines[i]
        if len(line) > max_line_len:
            continue
        if all(kw.lower() in line.lower() for kw in keywords):
            if not row_values(line):    # 標題行不含數值
                return i
    return None


def find_anchor(lines, label_keywords, start_from=0, max_line_len=300):
    """
    找「含 keywords 且同行有數值」的第一行（錨點）。
    - 跳過目錄（TOC）條目：TOC 雖有頁碼但不是財務數字
    - 跳過 MD&A 敘述長句（長度 > max_line_len）：財務表格行通常很短
    回傳行號，或 None。
    """
    for i in range(start_from, len(lines)):
        line = lines[i]
        if len(line) > max_line_len:      # MD&A 敘述句子比表格行長得多
            continue
        if all(kw.lower() in line.lower() for kw in label_keywords):
            if row_values(line):          # 確認同行真的有數值
                return i
    return None


# 跳過這些純標題/頁碼/欄位標頭行
_SKIP_RE = re.compile(
    r"^[\d\s$().,%\-]+$"   # 純數字符號行
    r"|^\d{1,3}$"           # 頁碼
    r"|^Item\s*\.\s*\w"     # 文件 Item 標題（如 "Item . Financial Statements"）
    r"|^(?:three months|six months|nine months|twelve months"
    r"|year ended|years ended|period ended|quarter ended"
    r"|january|february|march|april|may|june|july|august"
    r"|september|october|november|december"
    r"|20\d\d[\s\d]+|20\d\d$"
    r"|unaudited|in millions|in thousands"
    r"|except.*share"
    r"|\(in millions|\(in thousands|\(unaudited)",
    re.I
)

# 偵測到另一個財務報表段落標題時停止提取
_NEW_SECTION_RE = re.compile(
    r"(^|\s)(consolidated\s+)?(balance sheets?|statements? of (cash flows?|"
    r"stockholders|equity|operations|comprehensive)|cash flows?$|"
    r"notes? to (consolidated|financial)|item\s+[12]\.|"
    r"management.{0,10}discussion|selected financial data)",
    re.I
)


def extract_section(lines, anchor_idx, back=10, max_rows=90):
    """
    從 anchor_idx - back 開始，往下提取所有帶標籤的財務項目。
    回傳 OrderedDict: { 原始標籤: 第一欄數值 }
    """
    result = OrderedDict()
    if anchor_idx is None:
        return result

    start = max(0, anchor_idx - back)
    data_started = False

    for i in range(start, min(start + max_rows, len(lines))):
        line = lines[i].strip()
        if not line or len(line) < 2:
            continue

        # 財務表格行通常短於 300 字元；跳過 MD&A 敘述長句
        if len(line) > 300:
            continue

        # 找到資料後，偵測到下一個主要財務報表標題則停止
        if data_started and _NEW_SECTION_RE.search(line) and i > anchor_idx + 5:
            break

        if _SKIP_RE.match(line):
            continue

        vals = row_values(line)
        if not vals:
            continue

        lbl = row_label(line)
        if not lbl or len(lbl) < 2:
            continue
        if re.match(r"^[\d.\-\s]+$", lbl):   # 殘留純數字
            continue
        if len(lbl) > 120:                    # 敘述長句不是財務標籤（表格標籤通常 < 80 字）
            continue

        data_started = True
        if lbl not in result:
            result[lbl] = vals[0]   # 第一欄 = 當期數值

    return result


# ── 主解析 ────────────────────────────────────────────────────────────────────

def parse_htm(filepath, ticker, period):
    """
    主解析函數：用錨點定位各財務報表段落，提取原始標籤與數值。
    """
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        raw = f.read()

    extractor = TextExtractor()
    extractor.feed(raw)
    text = extractor.get_text()
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    warnings = []

    # ────────────────────────────────────────────────────────────────────────
    # 策略：先找「資產負債表」的錨點（通常位於財務報表真正開始的地方），
    #       再以該位置為基準往前/往後搜尋損益表和現金流量表。
    #       這樣可以跳過 10-K MD&A 敘述段落中帶有數字的句子。
    # ────────────────────────────────────────────────────────────────────────

    # ── 1. 資產負債表錨點 ─────────────────────────────────────────────────────
    # 先找「CONSOLIDATED BALANCE SHEETS」標題行（無數值），再在標題後找資料錨點。
    # 這樣可以跳過 MD&A 中含有相同關鍵字的流動性摘要表。
    bs_header = None
    for kws in [
        ["balance sheets"],
        ["balance sheet"],
    ]:
        bs_header = find_section_header(lines, kws)
        if bs_header is not None:
            break

    bs_search_from = bs_header if bs_header is not None else 0
    bs_anchor = None
    for kws in [
        ["Cash and cash equivalents"],
        ["Cash, cash equivalents"],
        ["Total current assets"],
        ["Total assets"],
    ]:
        bs_anchor = find_anchor(lines, kws, start_from=bs_search_from)
        if bs_anchor is not None:
            break

    balance = extract_section(lines, bs_anchor, back=3, max_rows=60)
    if not balance:
        warnings.append("資產負債表：未能找到錨點 (Cash and cash equivalents)")

    # ── 2. 損益表錨點（在資產負債表附近搜尋）────────────────────────────────
    # 財報慣例：損益表緊接在資產負債表前後，範圍內搜尋避免誤抓 MD&A 文字
    bs_ref = bs_anchor if bs_anchor is not None else 0
    search_from = max(0, bs_ref - 50)    # 10-Q 損益表在 BS 之後；10-K 可能在前後

    is_anchor = None
    for kws in [
        ["Total revenue"],
        ["Total net revenue"],
        ["Net revenues"],
        ["Net revenue"],
    ]:
        # 先嘗試在 BS 附近（±200 行）搜尋
        candidate = find_anchor(lines, kws, start_from=search_from)
        if candidate is not None and abs(candidate - bs_ref) < 300:
            is_anchor = candidate
            break

    # 若附近找不到，嘗試 BS 之後搜尋（10-K 損益表接在 BS 後）
    if is_anchor is None:
        for kws in [["Total revenue"], ["Net revenues"], ["Revenue"]]:
            candidate = find_anchor(lines, kws, start_from=bs_ref)
            if candidate is not None:
                is_anchor = candidate
                break

    income = extract_section(lines, is_anchor, back=10, max_rows=80)

    # EPS（在損益表附近找）
    eps_start = is_anchor if is_anchor is not None else bs_ref
    eps_anchor = find_anchor(lines, ["Diluted"], start_from=eps_start)
    if eps_anchor and abs(eps_anchor - eps_start) < 60:
        for j in range(max(0, eps_anchor - 5), min(eps_anchor + 10, len(lines))):
            lbl = row_label(lines[j])
            vals = row_values(lines[j])
            if not vals:
                continue
            ll = lbl.lower()
            if "diluted" in ll and "eps_diluted" not in income:
                income["eps_diluted"] = vals[0]
            elif "basic" in ll and "eps_basic" not in income:
                income["eps_basic"] = vals[0]

    # 衍生利潤率（用 _ 前綴標示為計算欄位）
    rev = gross = op = net = None
    for k, v in income.items():
        kl = k.lower()
        if rev is None and re.search(r"total (net )?revenue|net (revenues?|sales)", kl):
            rev = v
        if gross is None and re.search(r"gross (profit|margin|loss)", kl):
            gross = v
        if op is None and re.search(r"operating (income|loss|profit)", kl):
            op = v
        if net is None and re.search(r"^net income|net income \(loss\)|net (income|loss) and", kl):
            net = v

    if rev and rev != 0:
        if gross is not None:
            income["_gross_margin_pct"]     = round(gross / rev, 4)
        if op is not None:
            income["_operating_margin_pct"] = round(op / rev, 4)
        if net is not None:
            income["_net_margin_pct"]       = round(net / rev, 4)

    if not income:
        warnings.append("損益表：未能找到錨點 (Total revenue / Net revenues)")

    # ── 3. 現金流量表錨點（資產負債表之後搜尋）──────────────────────────────
    cf_start = bs_ref + 20   # 現金流一定在 BS 之後

    cf_anchor = None
    for kws in [
        ["Cash provided by", "operating"],
        ["Cash used in", "operating"],
        ["Net cash provided by operating"],
        ["Net cash used in operating"],
        ["Net cash from operating"],
        ["operating activities"],
    ]:
        candidate = find_anchor(lines, kws, start_from=cf_start)
        if candidate is not None:
            cf_anchor = candidate
            break

    cashflow = extract_section(lines, cf_anchor, back=5, max_rows=70)

    # 衍生 FCF
    ocf = capex = None
    for k, v in cashflow.items():
        kl = k.lower()
        if ocf is None and re.search(r"(provided by|used in|from) operating|cash.*operating", kl):
            ocf = v
        if capex is None and re.search(
            r"capital expenditure|expenditure.*property|purchases? of property"
            r"|purchase.*equipment|acquisitions? of property", kl
        ):
            capex = v

    if ocf is not None and capex is not None:
        cashflow["_free_cash_flow"] = round(ocf + capex, 1)

    if not cashflow:
        warnings.append("現金流量表：未能找到錨點")

    # ── 組裝結果 ──────────────────────────────────────────────────────────────
    result = {
        "period":           period,
        "ticker":           ticker,
        "income_statement": dict(income),
        "balance_sheet":    dict(balance),
        "cash_flow":        dict(cashflow),
        "parse_warnings":   warnings,
    }

    if warnings:
        print(f"⚠️  {len(warnings)} 個段落未能提取：", file=sys.stderr)
        for w in warnings:
            print(f"   - {w}", file=sys.stderr)
    else:
        print(
            f"✓  {ticker} {period} 解析完成：損益表 {len(income)} 項、"
            f"資產負債表 {len(balance)} 項、現金流 {len(cashflow)} 項",
            file=sys.stderr
        )

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file",   required=True, help="HTM 檔案路徑")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--period", required=True, help="e.g. Q1_FY2026")
    args = parser.parse_args()

    result = parse_htm(args.file, args.ticker.upper(), args.period)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
