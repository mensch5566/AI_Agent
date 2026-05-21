# SEC Financials — Audit Metadata Schema v4

Date: 2026-05-21
Status: **Canonical implementation contract**
Supersedes: `tmp/manual-edit-audit-note-plan.md` §1-§8（這份是 review trail）

這份文件定義所有 parse skill 跨 GAAP / Non-GAAP / Supplement 三條 path 的 audit metadata schema。任何 row 寫進 parse output JSON 都遵循這個 schema；adapter / upsert / API / derive-base 都用同一套 helper 識別「人工校正」vs「分類」vs「preservation 事件」。

文件範圍：
- 哪些欄位定義在 row 上
- 各欄位 strict allowlist
- helper 函式 + key 常數集合
- Re-extract preservation 行為矩陣
- Backward-compat（legacy enum normalization）
- DB / API canonical contract

不在範圍：
- CLI 介面（manual_edit.py 等）— 見 plan §15.6 + Phase 5 task
- conflict.json 機械阻擋細節 — 見 plan §15.2 C6 + Phase 4 task

---

## 1. 三個語意 channel

一個 row 上的 audit metadata 拆成三個**語意上獨立**的 channel：

| Channel | 代表 | Predicate | Copy helper |
|---|---|---|---|
| **Audit provenance** | value 的證據來源（人工校正） | `is_manual_audit_source(audit_source)` | `copy_audit_provenance(dst, src)` |
| **Classification** | row 的分類來源（long-tail bucket assignment） | `is_manual_classification_source(classification_source)` | `copy_classification_metadata(dst, src)` |
| **Preservation event** | 「這一次 re-extract 發生了什麼」的事件記錄 | （不是 predicate；是事件 marker） | 不複製；每次 re-extract 重新設定（見 §6 行為矩陣） |

關鍵原則：
- **audit_source 跟 classification_source 不要混進同一個欄位**。一個 row 可以同時帶兩者（同時被人工校正 value + 分類到 bucket），但兩者用不同欄位記。
- **preservation event 不是 source**，不要塞進 audit_source。

---

## 2. Row schema

### 2.1 完整欄位範例

```jsonc
{
  // ── 一般 row fields ──
  "period": "Q1_FY2026",
  "period_end": "2025-09-27",
  "period_kind": "single_quarter",
  "axis": "product",
  "source_account": "Components",
  "uni_account": "revenue",
  "value": 379.2,
  "unit": "USD_millions",

  // ── Channel 1: Audit provenance（value 證據來源）──
  "audit_source": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
  "audit_source_raw": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",  // 寫入時跟 audit_source 相同；legacy row 才有差
  "audit_note": "10-Q Note 15 Revenue Recognition table.",   // ≤500 chars
  "audited_at": "2026-05-21T11:20:00Z",                       // ISO datetime
  "audited_by": "user@example.com",                           // or "agent:claude-session-xxx"
  "audit_evidence": {
    "source_doc":         "lite-20250927.htm",
    "page_or_section":    "Note 15. Revenue Recognition",
    "quote":              "Components $379.2 Systems $154.6 Net revenue $533.8",
    "accession_number":   "0001628280-25-049073",
    "tool":               "notebooklm-mcp 2026-05-21",
    "period_scope":       "Three Months Ended September 27, 2025"   // 對 cumulative_ytd / Q-only 區分
  },

  // ── Channel 2: Classification（row 分類來源；非 value provenance）──
  "classification_source": null,    // "AGENT_CLASSIFIED" / "MANUAL_RECLASSIFIED" / null
  "classification_note":   null,
  "classified_at":         null,
  "long_tail_metadata":    null,    // {rolls_up_to, is_recurring, ...}

  // ── Channel 3: Preservation event（re-extract 事件記錄；不是 source）──
  "preserved_from_audit":  false,
  "preserved_at":          null,
  "preservation_event":    null     // "REEXTRACT_PRESERVED_PRIOR_AUDIT" / "REEXTRACT_PRESERVED_PRIOR_CLASSIFICATION"
}
```

### 2.2 欄位必填規則

| 欄位 | 新寫入（apply_audit / manual_edit） | Legacy row | Re-extract preserved row |
|---|---|---|---|
| `audit_source` | required（如果是 audit） | optional（legacy 可缺） | copy 自舊 row |
| `audit_source_raw` | required（寫入時 = audit_source） | 缺則 fallback 到 `audit_source` 值 | copy |
| `audit_note` | optional ≤500 chars | optional | copy |
| `audited_at` | required（ISO datetime） | optional（缺則 adapter 報 validation warning） | copy |
| `audited_by` | optional | optional | copy |
| `audit_evidence` | required（如果 audit_source == OFFICIAL_FILING 或 RESTATEMENT）| optional | copy |
| `audit_evidence.accession_number` | **required when audit_source == MANUAL_RESTATEMENT_FROM_AMENDED_FILING** | optional | copy |
| `classification_source` | required（如果 row 是 long-tail bucket assignment） | optional | copy（如果這 row 是 classified） |
| `long_tail_metadata` | required（如果是 long-tail row） | optional | copy |
| `preserved_from_audit` | **不寫入**（false default）；只在 re-extract preservation 事件時設定 | optional | 重設（見 §6） |
| `preserved_at` | 同上 | optional | 重設 |
| `preservation_event` | 同上 | optional | 重設 |

---

## 3. Allowlist

### 3.1 `audit_source` strict allowlist

```python
MANUAL_AUDIT_SOURCES = frozenset({
    # === Canonical (current) ===
    "MANUAL_AUDIT_FROM_OFFICIAL_FILING",     # 官方 10-Q / 10-K / 8-K 揭露，人工校正 parser 抽錯
    "MANUAL_RESTATEMENT_FROM_AMENDED_FILING", # 公司事後 amended filing；audit_evidence.accession_number 必填

    # === Legacy (accepted, normalized) ===
    "MANUAL_AUDIT_FROM_PDF",      # 舊 cross-check apply_audit 寫的；normalize → MANUAL_AUDIT_FROM_OFFICIAL_FILING
    "MANUAL_AUDIT_FROM_8K_PDF",   # 舊 8K apply_audit 寫的；normalize → MANUAL_AUDIT_FROM_OFFICIAL_FILING
})

LEGACY_AUDIT_SOURCE_MAP = {
    "MANUAL_AUDIT_FROM_PDF":     "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
    "MANUAL_AUDIT_FROM_8K_PDF":  "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
}

def normalize_audit_source(raw: str | None) -> str | None:
    """Map legacy enum to canonical. Unknown values pass through unchanged
    (caller decides whether to reject or warn)."""
    if raw is None:
        return None
    return LEGACY_AUDIT_SOURCE_MAP.get(raw, raw)

def is_manual_audit_source(audit_source_raw_or_normalized: str | None) -> bool:
    """True iff this row's value came from a manual audit source.
    Used by preservation helpers + derive-base relaxation guards.
    Accepts either raw or normalized value (set equality on union)."""
    return audit_source_raw_or_normalized in MANUAL_AUDIT_SOURCES
```

### 3.2 `classification_source` strict allowlist

```python
MANUAL_CLASSIFICATION_SOURCES = frozenset({
    "AGENT_CLASSIFIED",       # parse-sec-cross-check long-tail bucket assigned by agent/LLM
    "MANUAL_RECLASSIFIED",    # user override via manual_edit.py
})

def is_manual_classification_source(classification_source: str | None) -> bool:
    return classification_source in MANUAL_CLASSIFICATION_SOURCES
```

### 3.3 `preservation_event` strict allowlist

```python
PRESERVATION_EVENTS = frozenset({
    "REEXTRACT_PRESERVED_PRIOR_AUDIT",         # re-extract 時保留舊 audit row
    "REEXTRACT_PRESERVED_PRIOR_CLASSIFICATION",  # re-extract 時保留舊 classification row
})
```

---

## 4. Helper key 常數

跨 GAAP / 8K / Supplement / derive-base 共用。建議放 `Tools/research-tools/_shared/audit_metadata.py`：

```python
# Audit provenance — value 證據來源。Copy 邏輯：matched row 沿用既有；conflict 時依規則
AUDIT_PROVENANCE_KEYS = (
    "audit_source",
    "audit_source_raw",
    "audit_note",
    "audited_at",
    "audited_by",
    "audit_evidence",
)

# Classification — row 分類來源。Copy 邏輯：matched row 沿用；獨立 predicate
CLASSIFICATION_KEYS = (
    "classification_source",
    "classification_note",
    "classified_at",
    "long_tail_metadata",
)

# Preservation event — 不複製。Re-extract 時依事件矩陣（§6）決定 set / reset
PRESERVATION_EVENT_KEYS = (
    "preserved_from_audit",
    "preserved_at",
    "preservation_event",
)

def copy_audit_provenance(dst: dict, src: dict) -> None:
    """Copy value-source audit metadata from src to dst.
    Does NOT touch preservation event keys — those are re-set per event."""
    for key in AUDIT_PROVENANCE_KEYS:
        if key in src and src[key] is not None:
            dst[key] = src[key]

def copy_classification_metadata(dst: dict, src: dict) -> None:
    """Copy classification metadata (e.g. long-tail bucket assignment).
    Independent from audit provenance."""
    for key in CLASSIFICATION_KEYS:
        if key in src and src[key] is not None:
            dst[key] = src[key]

def set_preservation_event(
    dst: dict,
    event: str,   # one of PRESERVATION_EVENTS
    *, now_iso: str | None = None,
) -> None:
    """Mark this row as preserved during current re-extract.
    Always uses fresh timestamp (preserved_at = now), not carried-over."""
    from datetime import datetime, timezone
    if event not in PRESERVATION_EVENTS:
        raise ValueError(f"unknown preservation_event: {event}")
    dst["preserved_from_audit"] = (event == "REEXTRACT_PRESERVED_PRIOR_AUDIT")
    dst["preserved_at"] = now_iso or datetime.now(timezone.utc).isoformat()
    dst["preservation_event"] = event

def clear_audit_provenance(dst: dict) -> None:
    """Remove all audit provenance keys (used by --accept-new-values)."""
    for key in AUDIT_PROVENANCE_KEYS + PRESERVATION_EVENT_KEYS:
        dst.pop(key, None)
```

---

## 5. Re-extract preservation 行為矩陣

每個 parse skill（xbrl_extract.py / extract_8k_nongaap.py / extract_supplement_v3.py）在 re-extract 時遇到舊 row 的處理規則：

| 情境 | 條件 | audit provenance | classification | preservation event |
|---|---|---|---|---|
| **MATCH** | new row found AND abs(new_value - audit_value) ≤ tolerance | `copy_audit_provenance(new, old)` | `copy_classification_metadata(new, old)` | **不設** event（沒有衝突需要記錄）|
| **CONFLICT (keep audit)** | new row found AND value differs > tolerance AND `--accept-new-values` NOT given AND has_audit | `copy_audit_provenance(new, old)` | copy classification | `set_preservation_event(new, "REEXTRACT_PRESERVED_PRIOR_AUDIT")` + 寫 `new_extract_value_rejected` + Supplement 另寫 conflict.json 標 `audit_conflicts_unresolved=true` |
| **CONFLICT (classification only)** | value differs AND has_classification AND NOT has_audit AND `--accept-new-values` NOT given | — | `copy_classification_metadata(new, old)` + restore `value=old_val` | `set_preservation_event(new, "REEXTRACT_PRESERVED_PRIOR_CLASSIFICATION")` + 寫 `new_extract_value_rejected` |
| **ADDED_BACK (audit)** | new XBRL/PDF 不再有此 row，但舊 audit row 還在 | `copy_audit_provenance` | copy classification | `set_preservation_event(new, "REEXTRACT_PRESERVED_PRIOR_AUDIT")` |
| **ADDED_BACK (classification only)** | new XBRL/PDF 不再有此 row，舊 row 只有 classification | — | `copy_classification_metadata` | `set_preservation_event(new, "REEXTRACT_PRESERVED_PRIOR_CLASSIFICATION")` |
| **ACCEPT_NEW (audit)** | `--accept-new-values` flag 給定 + CONFLICT + has_audit | `clear_audit_provenance(new)` | `copy_classification_metadata(new, old)`（顯式保 classification） | 清除 event；寫 `accepted_new_value_replaces_audit={prior_audit_value, new_extracted_value}`；decision 寫進 manual_edit_audit_log.jsonl |
| **ACCEPT_NEW (classification only)** | `--accept-new-values` + CONFLICT + classification-only | — | `copy_classification_metadata` | 清除 event；**不寫** `accepted_new_value_replaces_audit`（該欄位只記 audit conflict）|
| **NO_AUDIT** | 舊 row 沒 audit metadata | — | — | — |
| **NEW_ROW** | new row 出現，舊資料無此 row | — | — | — |

Predicate：
- 判斷舊 row 是否屬「audit-preserved」: `is_manual_audit_source(old_row.get("audit_source"))` OR `is_manual_audit_source(old_row.get("audit_source_raw"))`
- 判斷舊 row 是否屬「classification-preserved」: `is_manual_classification_source(old_row.get("classification_source"))`
- 一個 row 可能同時兩種（preservation 都做）

---

## 6. 識別 key（preservation matching）

不同 skill 用不同 dimensional identity 比對舊/新 row 是否 match：

| Skill | Identity key (tuple, deterministic) |
|---|---|
| parse-10QK-gaap | `(period, period_kind, version, statement, uni_account, source_account, xbrl_tag, unit)` |
| parse-8k-nongaap | 同上，但 version 永遠 NON_GAAP |
| parse-SEC-supplement v3 | `(period, period_kind, axis_key, member_key, uni_account, canonical_json(other_dimensions), unit)` |

`axis_key` / `member_key` 由 `_shared/sec_json_adapter.py::build_axis_key()` / `build_member_key()` 計算，preference order：xbrl qname → local display label → fallback。**不要用 raw display label** 做 primary identity（會撞 label-variant case）。

`cell_id` 是上述 tuple 的 hash + deterministic encoding，可作為 identity 的 short form。

---

## 7. DB / API canonical contract

### 7.1 `provenance` JSONB shape（Supabase 內存的）

每 row 的 `provenance` 欄位至少包含：

```jsonc
{
  // ── Audit provenance (canonical) ──
  "audit_source":            "MANUAL_AUDIT_FROM_OFFICIAL_FILING",  // canonical normalized; legacy raw 也會 normalize
  "audit_source_raw":        "MANUAL_AUDIT_FROM_PDF",              // 原始 row 值；legacy / forensic 用
  "audit_note":              "...",
  "audited_at":              "ISO datetime",
  "audited_by":              "user@example.com",
  "audit_evidence":          { ... },

  // ── Classification ──
  "classification_source":   "AGENT_CLASSIFIED" | null,

  // ── Filing context (既有 fields, 保留) ──
  "source_filing":           "10-Q",
  "accession_number":        "0001628280-25-049073"
}
```

### 7.2 下游讀取規則

- **API / read model**: 永遠讀 `provenance.audit_source`（canonical normalized）。
- **不要讀 `audit_source_raw`** 來判斷 audit 性質 — 那是 forensic / debug 用。
- **derive-base**: 用 `is_manual_audit_source(provenance.audit_source)`，不要直接 string 比對。
- **前端**: 顯示 audit indicator 用 `provenance.audit_source` 判斷；hover 顯示 `audit_note` / `audited_at` / `audit_evidence`。

### 7.3 Legacy DB row 處理

既有 4 個 ticker 在 DB 內有 legacy `provenance.audit_source = 'MANUAL_AUDIT_FROM_PDF'` 的 row。**不做 one-shot migration**。

Adapter 行為（Phase 3 起）：
- Read 端: API 動態 normalize（讀 row 時跑 `normalize_audit_source(...)` 才往下游送）
- Write 端: 新 upsert 永遠寫 normalized 進 `audit_source` + 原始進 `audit_source_raw`
- 自然 refresh: 下次 re-extract → re-upsert 時 DB row 自然刷新成 v4 schema

如果未來決定清 DB legacy，另開 migration phase，必須先 dry-run count + backup。

---

## 8. derive-base 整合（Phase 3）

derive-base 為派生指標 carry audit lineage：

### 8.1 input 端

`tmp/derive-base/derive_types.input_dict_from_fact()` 在 input dict 加：

```python
{
    # ... existing
    "cell_id":                  fact.cell_id,
    "audit_source":             fact.provenance.get("audit_source"),        # canonical
    "audit_source_raw":         fact.provenance.get("audit_source_raw"),    # legacy raw
    "audit_evidence":           fact.provenance.get("audit_evidence"),
    # 不放 classification_source 進 inputs — 那是 row metadata 不是 value provenance
}
```

### 8.2 output 端

`tmp/derive-base/audit.to_derived_metric_row()` 計算：

```python
audited_input_cell_ids = [
    i["cell_id"] for i in candidate.inputs
    if is_manual_audit_source(i.get("audit_source"))
]
derived_row["provenance"]["has_audited_inputs"]   = len(audited_input_cell_ids) > 0
derived_row["provenance"]["audited_input_cell_ids"] = audited_input_cell_ids
```

**不複製 audit_note / audit_evidence** 到 derived row — 只保留 input cell_id linkage。前端要看 audit evidence 時，順 cell_id 回 input row 查。

### 8.3 rules_q4 concept relaxation

`tmp/derive-base/rules_q4._concepts_match()` 把：

```python
# OLD (buggy — AGENT_CLASSIFIED 也會誤觸):
if any(getattr(f, "provenance", {}).get("audit_source") for f in facts):
    return True
```

改成：

```python
# NEW: 只認 manual audit value source
from _shared.audit_metadata import is_manual_audit_source
if any(is_manual_audit_source((getattr(f, "provenance", None) or {}).get("audit_source"))
       for f in facts):
    return True
```

避免 `AGENT_CLASSIFIED`（pure classification, no value audit）誤觸 Q4 concept relaxation。

---

## 9. Implementation phase mapping

| Phase | 對應這份 schema 哪段 |
|---|---|
| Phase 1.2 | §1-§9（這份文件） |
| Phase 2.1-2.2 | apply_audit.py 寫入時遵守 §2.1 schema（含 audit_note / audited_at / audit_evidence）|
| Phase 2.3 | `_shared/audit_metadata.py` 實作 §3 + §4 helpers |
| Phase 2.4-2.5 | xbrl_extract.py / extract_8k_nongaap.py 套用 §5 行為矩陣 |
| Phase 2.6 | regression test 驗證 §5 行為 |
| Phase 3.1-3.6 | adapter / upsert / API 套用 §7 canonical contract |
| Phase 3.x (new) | derive-base 套用 §8 |
| Phase 4 | extract_supplement_v3.py 套用 §5 + §6 dimensional identity + supplement 專用 conflict.json |
| Phase 5 | manual_edit.py 套用整份 schema |

---

## 10. 反例（不要這樣寫）

❌ **錯**：把 preservation 寫進 audit_source

```jsonc
{ "audit_source": "MANUAL_PRESERVED_FROM_PRIOR_AUDIT" }  // ✗ 撤回
```

✅ **對**：

```jsonc
{
  "audit_source": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",   // value source 不變
  "preserved_from_audit": true,                          // event 另立
  "preserved_at": "2026-05-22T03:00:00Z",
  "preservation_event": "REEXTRACT_PRESERVED_PRIOR_AUDIT"
}
```

---

❌ **錯**：用 string 比對判斷 audit

```python
if row.get("audit_source") == "MANUAL_AUDIT_FROM_PDF":   # ✗ 漏 canonical
    preserve(row)
```

✅ **對**：

```python
if is_manual_audit_source(row.get("audit_source")):       # 接受 legacy + canonical
    preserve(row)
```

---

❌ **錯**：把 classification 跟 audit 用同一個 predicate

```python
if row.get("audit_source"):   # ✗ AGENT_CLASSIFIED 也會誤觸
    preserve(row)
```

✅ **對**：

```python
if is_manual_audit_source(row.get("audit_source")):
    copy_audit_provenance(new, row)
if is_manual_classification_source(row.get("classification_source")):
    copy_classification_metadata(new, row)
```

---

❌ **錯**：preservation event timestamp 沿用舊值

```python
copy_audit_metadata(new, old)   # ✗ 把 preserved_at 也一起 copy
```

✅ **對**：

```python
copy_audit_provenance(new, old)    # 不含 event keys
set_preservation_event(new, "REEXTRACT_PRESERVED_PRIOR_AUDIT")  # 永遠 now
```

---

## 11. Forensic 欄位 — `accepted_new_value_replaces_audit`

當 re-extract 走 ACCEPT_NEW path 且舊 row has_audit 時，新 row 寫入：

```jsonc
{
  "accepted_new_value_replaces_audit": {
    "prior_audit_value":    -172.1,
    "new_extracted_value":  -180.5
  }
}
```

規則：
- **只用在 audit conflict accept-new**。Classification-only conflict + accept_new 不寫這欄位。
- 寫入時必須 `clear_audit_provenance` 已執行完。
- Phase 5 `manual_edit.py` 看到這欄位代表「該 row 曾經 override 過 audit」，需要寫進 `manual_edit_audit_log.jsonl` 留 forensic trail。

---

## CHANGELOG

### 2026-05-21 (v4.1, Phase 2 Codex review)
- §5 行為矩陣拆出 CONFLICT/ADDED_BACK/ACCEPT_NEW 的 audit vs classification-only 分支
- §11 新增 `accepted_new_value_replaces_audit` 欄位定義
- `stamp_audit_provenance` enforce OFFICIAL_FILING 也需要 audit_evidence (locator)

### 2026-05-21 (v4, Phase 1.2)
- 初版 canonical schema
- 三 channel 拆分（audit / classification / preservation event）
- Backward-compat legacy enum normalization
- Re-extract 行為矩陣明確化
- DB canonical contract: `audit_source` normalized + `audit_source_raw` raw 雙寫
- derive-base integration spec
