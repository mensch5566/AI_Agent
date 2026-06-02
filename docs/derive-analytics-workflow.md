# derive-analytics 開發流程（process contract）

Updated: 2026-06-02

這份文件是 `derive-analytics`（以及同模式的 parse / derive-base skills）的**開發流程契約**。
緣起：2026-06-02 用 NLM「Topic - Project Dev」筆記本對照軟體工程最佳實踐，檢討
既有流程，採用四項調整（見文末 ADR-001）。實際 code 規則仍以各 repo 的
`docs/STATUS.md`、`CLAUDE.md`、skill 內 `SKILL.md` 為準。

---

## 1. Single Source of Truth（SSOT）

- **唯一權威 = canonical git repo**：`~/CC_Switch_Config/skills/derive-analytics/`
  - `scripts/` = 引擎與 runner；`tests/` = 測試；`SKILL.md` = skill 說明
- **不再使用** `~/AI_Agent/tmp/derive-analytics/`（扁平 prototype）做開發。
  - 該目錄 git-ignored、是歷史遺留的手動 working copy，現標記為 DEPRECATED。
  - 過去的「5 鏡像」= prototype + canonical + 3 runtime，prototype→canonical 是
    **手動 cp**（無腳本、易漂移）。砍掉 prototype 後變「4 鏡像」：canonical（SSOT）
    + 3 runtime（部署目標）。
- **3 runtime 是部署產物，不是來源**：`~/.claude`、`~/.codex`、`~/.cc-switch`。
  由 `bash scripts/sync-to-local.sh`（在 CC_Switch_Config 跑）從 canonical 推出。

## 2. 開發迴圈（dev loop）

1. **直接編輯 canonical**（`~/CC_Switch_Config/skills/derive-analytics/scripts|tests/`）。
2. 在 canonical 跑測試：
   ```bash
   cd ~/CC_Switch_Config/skills/derive-analytics
   export PATH="/Library/Frameworks/Python.framework/Versions/3.13/bin:$PATH"
   uv run --with pytest --with hypothesis python -m pytest tests/ -q
   ```
   - 兩套引擎的 `sys.path.insert` 會互相 shadow → **分檔跑**
     （`test_crossperiod.py`、`test_rules_ratios.py`、`test_properties.py` 各自跑）。
3. `bash scripts/sync-to-local.sh` 推 3 runtime。
4. 才進入 production rollout（見 §3）。

## 3. 部署順序：**先審再上 production**（Shift Left）

> 改自舊流程的「實作→上 production→Codex review」。NLM #1：審查/驗證若在部署後
> 才做，AI 產生的邏輯錯誤已對 production 造成實際影響；最佳實踐是 commit/deploy 前
> 就把缺陷攔下（防禦縱深）。

**新順序：**

1. TDD 實作（紅→綠）+ **property-based 測試**（見 §4）。
2. **本地等價驗證**：dry-run upsert（不帶 `--apply`）+ 對既有 production 值做 diff，
   確認既有指標 byte-identical、新指標數值合理（手算 / NLM 對數）。
3. 寫 **handoff（ADR 格式，見 §5）**。
4. **Codex functional review** → 我逐項質疑、互相辯論收斂（沒有誰拍板，辯到最優；
   不為了過 review 越改越多 bug）。
5. **收斂後才** re-upsert 上 production（`--apply`），再驗一次前端。

例外：純文件 / 純測試新增（不動引擎、不寫 DB）可直接 commit，無需先過 Codex。

> Staging 備註：目前無獨立 staging Supabase。緩解 = §3.2 的 dry-run + diff gate +
> derive-base STALE gate + facts-wins gate。是內部研究工具（4 ticker、非對外流量），
> 風險低於對外產品；要不要建獨立 staging 之後再評估（NLM #2 緩解版）。

## 4. Property-based 測試（對抗 confirmation bias）

> NLM #4：AI 寫的 example 測試偏「happy path」，AI 作者 + AI reviewer 可能在同一個盲點
> 上達成共識（幻覺放大）。Property-based fuzzing 是對抗手段：對引擎的**純守衛函式**丟
> 大量任意輸入，驗證 skip/不變量對所有輸入都成立。

- 檔案：`tests/test_properties.py`（Hypothesis）。
- 涵蓋引擎的 pure guard：
  - EL2：`_kind_value`（days/ratio skip）、`_nopat`（abnormal-tax skip，不 clamp）、
    `_day_after`（total、None-safe、+1 天）、`_yoy_candidate`（prior>0 required）。
  - EL1：`compute_single_period_ratios` 的除零守衛、`denom_skip` 政策、exact-value dedup。
- **人類仍是最後把關**（human-in-the-loop）：property test 是補強，不取代用戶 review。
- 新增引擎守衛函式時，**同步加 property test**。

## 5. Handoff = ADR 格式

> NLM #5：handoff / STATUS 不是負擔，是「AI 的制度記憶」（documentation-AI feedback
> loop）——讓後續 session 不必重學、不重提已否決方案。升級成 ADR 讓「為什麼」可追。

每份 review handoff（`tmp/derive-analytics-*-review.md`）與重大決策，盡量含 ADR 欄位：

```
# ADR-NNN: <一句話決策>
- Status: Proposed | Accepted | Superseded by ADR-MMM
- Context: 為什麼要做這個決定（問題、限制、資料現況）
- Decision: 決定了什麼（含 skip 政策、口徑）
- Alternatives: 考慮過但否決的方案 + 否決原因（特別是 Codex 提過、被辯論掉的）
- Consequences: 影響、風險、已知 limitation、後續待辦
```

---

## ADR-001: 採用四項開發流程調整（2026-06-02）

- **Status**: Accepted
- **Context**: 用 NLM「Topic - Project Dev」對照軟體工程最佳實踐，檢討既有
  derive-analytics 流程（5 鏡像手動同步、實作後才 Codex review、example-only 測試、
  每功能寫 handoff）。
- **Decision**: 採用全部四項——
  1. **先審再上 production**（Shift Left；§3）
  2. **砍掉 dev-prototype 重複**，canonical = SSOT（§1）
  3. **加 property-based 測試**對抗 confirmation bias（§4）
  4. **handoff 升級成 ADR 格式**（§5）
- **Alternatives**:
  - 建獨立 staging Supabase（NLM #2）→ 緩，先用 dry-run + 多重 gate 緩解（內部、4 ticker）。
  - 完全 CI/CD 自動部署 3 runtime（NLM #3 的 GitHub Actions 版）→ 緩，sync-to-local.sh
    已足夠，先確立「canonical=SSOT、prototype 退役」即解決主要 drift 風險。
- **Consequences**:
  - 之後每個指標：先 TDD+property+dry-run 驗 → ADR handoff → Codex review → 收斂 →
    才 `--apply`。
  - prototype 目錄退役（留 DEPRECATED 標記，不刪，可回溯）。
  - 引擎新增 `OverflowError` 守衛（`_day_after`）——由 property fuzzing 暴露的
    robustness 缺口，示範本流程價值。
  - 來源（NLM「Topic - Project Dev」）：Google SWE《Software Engineering at Google》
    （shift-left / VCS source-of-truth / testing-in-production 風險）、CD pipeline、
    AI-assisted dev（confirmation bias、hallucination amplification、ADR、文件即制度記憶）。
