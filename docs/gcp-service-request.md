# GCP 服務開通需求

**申請日期**：2026-03-30
**需求說明**：我們需要使用 GCP 來部署一個內部網站，以及用程式讀寫 Google Sheet。

---

## 請協助開通以下項目

### 第 1 項：建立 GCP Project 並綁定帳單

- 在公司的 Google Workspace 組織下建立一個 GCP Project
- 綁定公司的 Billing Account（備註：我們使用的服務均在 GCP 免費額度內，預計不會產生費用）

### 第 2 項：啟用 4 個 API

在上述 Project 中啟用以下 API：

1. **Google Sheets API** — 讓程式可以讀寫 Google Sheet
2. **Cloud Run Admin API** — 用來部署網站
3. **Cloud Build API** — 用來自動建構網站
4. **Cloud Storage API** — 用來存放網站的靜態檔案（圖片、資料檔）

### 第 3 項：建立 Service Account

- 建立一個 Service Account（服務帳戶）
- 產生一組 JSON 金鑰檔案，交付給我們
- 授予這個 Service Account 以下權限：
  - `roles/run.admin`（管理網站部署）
  - `roles/cloudbuild.builds.editor`（管理自動建構）
  - `roles/storage.admin`（管理檔案儲存）
  - `roles/iam.serviceAccountUser`（部署時需要）

### 第 4 項：授予使用者帳號操作權限

- 對象帳號：`（請填入你的 @khouse.com.tw 信箱）`
- 授予 Project 層級的 **Editor（編輯者）** 權限
- 讓此帳號可以在 GCP Console 上操作上述服務

---

## 預估費用

| 服務 | 每月免費額度 | 我們的預估用量 |
|---|---|---|
| Cloud Run（網站） | 200 萬次請求 | 內部少量使用，遠低於上限 |
| Cloud Build（建構） | 每日 120 分鐘 | 每日數次，每次幾分鐘 |
| Cloud Storage（檔案） | 5 GB 儲存 | < 1 GB |
| Google Sheets API | 每分鐘 300 次 | 極低頻 |

**預計初期費用：$0（全部在免費額度內）**

---

## 備註

- Service Account 的 JSON 金鑰檔案含有敏感資訊，請透過安全管道交付（勿用 email 明文傳送）
- 如有疑問可聯繫我們討論
