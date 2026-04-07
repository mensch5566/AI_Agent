# News Pipeline 已知問題 & 解決方案

## ✓ 已修復

### 1. RSS Description 包含 HTML 標籤
**問題**：Command Center 表格中「情緒」欄顯示原始 HTML（`<a href="...">...</a>`）
- **原因**：Google News RSS 的 `summary` 欄位是 HTML 格式
- **修復**：fetch_rss.py 新增 `clean_html()` 函數，移除標籤並解碼 HTML 實體
- **修復日期**：2026-03-25
- **測試**：執行 fetch_rss.py，驗證 description 為純文本

## ⚠️ 待改進

### 1. RSS 候選新聞過多（1000+ → 94 後）
**現象**：過去 24h 內單個標的搜尋返回 ~100 項結果，去重率 91%
**原因**：
- Google News RSS 預設返回 100 項/搜尋
- 同一篇文章被多家媒體轉載（重複標題+URL 變異）
- 搜尋詞過寬鬆（例如「AMD」會撈到所有提到 AMD 的新聞）

**建議改進**：
```python
# 改為更精確的搜尋詞
PRECISE_QUERIES = {
    "LEU": "LEU HALEU",          # 而非 Centrus
    "SNDK": "SNDK NAND storage", # 而非 SanDisk
    "TSM": "TSM 3nm OR 2nm",     # 而非 TSMC
}

# 或改用更短時間範圍
when:12h  # 過去 12 小時，而非 24h
```

### 2. LEU/SNDK 新聞量偏低
**LEU**：過去 24h 只有 5 條新聞，實際入庫 2 條
- 原因：HALEU 市場報導不足
- **替代方案**：用 NotebookLM query 補充 LEU 最新進展

**SNDK**：37 條候選，實際入庫 1 條
- 原因：大部分是產品規格、競品評測，非供需相關
- **替代方案**：改搜尋詞為 「SNDK storage demand」、「NAND price trends」

### 3. 台股標的新聞噪音多（聯發科、鴻勁）
**現象**：入庫的聯發科新聞多為股價漲跌、法人買賣，缺乏基本面內容
**建議**：
- 改為只抓官方新聞源（IR 頁面）
- 或手動審核後才納入

## 📋 改進計畫（優先順序）

| 優先級 | 項目 | 預期效果 | 工作量 |
|--------|------|---------|--------|
| P1 | ✓ HTML 清理（已完成） | 修正表格顯示 | 完成 |
| P2 | 精確搜尋詞配置 | 減少去重、提升相關性 | 0.5h |
| P3 | 引入 NotebookLM 補充 | 補強 LEU 新聞不足 | 1h |
| P4 | 台股官方新聞源 | 降低噪音 | 2h |
| P5 | 自動排程（cron）| 每日自動執行 | 1h |

## 🔄 執行 Pipeline 前檢查清單

- [ ] tickers.json 已同步最新 in_pool/observe 設定
- [ ] 策略摘要（NotebookLM note）已更新（檢查日期）
- [ ] Supabase `news_archive` 表可正常連接
- [ ] fetch_rss.py 能正常執行（無網路錯誤）
- [ ] HTML 清理函數已啟用（查看 description 輸出）

## 📝 維護記錄

- **2026-03-24**：初版 Pipeline 執行，入庫 94 條新聞，發現 HTML 標籤問題
- **2026-03-25**：修復 HTML 清理，更新本文檔
