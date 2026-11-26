# Soochow EATs｜資資吱吱

東吳大學校園代購媒合系統的 MVP 後端。此版本以影片展示為目標，保留組員原本的 SQLite 資料表與資料匯入腳本，將主要操作整理成 FastAPI API。

## 目前包含

- 使用者建立、查詢與顯示名稱更新。
- 餐廳與菜單查詢。
- 建立訂單及餐點明細，餐點價格由 SQLite 菜單取得。
- 查詢訂單列表及詳細內容。
- 自主接單，使用 SQLite `BEGIN IMMEDIATE` 與條件式更新避免同筆訂單被重複承接。
- 訂單送達、完成及待接單取消。
- 雙向評價與信用分數更新。
- 雙向信用計算依交接規格書公式實作。
- 接單者空堂時段與目前位置設定。
- 雙向 AI 智慧媒合（三階段動態權重計算「訂單找人」與「人找訂單」順路推薦）。
- 動態獎勵金建議（依尖峰緊迫時段、偏遠大樓、高樓層與即時供需計算）。
- Google Gemini 生成式 AI 整合（推薦理由白話摘要生成、一句話自然語言發單解析；未設定 API Key 時自動降級為規則式摘要）。

## 專案結構

```text
Soochow-EATs-main/
├── README.md
├── requirements.txt
└── backend/
    ├── database.py
    ├── init_db.py
    ├── main.py                 # MVP API 與信用計算
    ├── seed_campus_data_with_campus.py
    ├── seed_menu_items.py
    ├── test_mvp_api.py         # 自動化整合測試
    ├── 原有測試腳本
    ├── ai_matching.py          # AI 智慧媒合、動態獎勵金與 Gemini 生成式 AI 引擎
    └── test_ai_api.py          # AI 媒合與 Gemini 自動化整合測試
```

## 安裝與初始化（Windows PowerShell）

在專案根目錄執行：

```powershell
py -3.12 -m venv .venv
$python = ".\.venv\Scripts\python.exe"
& $python -m pip install -r requirements.txt
& $python backend/init_db.py
& $python backend/seed_campus_data_with_campus.py
& $python backend/seed_menu_items.py
```

注意：初始化及匯入腳本會操作 `backend/soochow_eats.db`。若已有重要資料，請先備份。第一次展示建議使用全新的資料庫。

## 啟動 API

```powershell
$python = ".\.venv\Scripts\python.exe"
& $python -m uvicorn main:app --app-dir backend --reload

若要啟用 Gemini 自然語言發單與推薦理由生成，請先於終端機設定免費的 `GEMINI_API_KEY` 環境變數（未設定時推薦理由會自動切換為規則式摘要，不影響伺服器運行）：
$env:GEMINI_API_KEY="貼上你的_Gemini_API_Key"
```

瀏覽器開啟 `http://127.0.0.1:8000/docs`，可直接操作 API。

## API 一覽

| 方法 | 路徑 | 用途 |
|---|---|---|
| GET | `/` | 確認 API 運作 |
| GET | `/campuses` | 查詢校區 |
| GET | `/restaurants?campus=shuangxi` | 查詢校區餐廳 |
| GET | `/restaurants/{restaurant_id}/menu` | 查詢菜單 |
| POST | `/users` | 建立使用者 |
| GET | `/users/{user_id}` | 查詢使用者 |
| PATCH | `/users/{user_id}` | 更新顯示名稱 |
| GET | `/users/{user_id}/credits` | 查詢雙向信用 |
| POST | `/orders` | 建立訂單 |
| GET | `/orders` | 查詢訂單列表，可用 requester_id、status 篩選 |
| GET | `/orders/{order_id}` | 查詢訂單及明細 |
| POST | `/orders/{order_id}/accept` | 自主接單，Body 傳入 runner_id |
| POST | `/orders/{order_id}/deliver` | 更新為已送達 |
| POST | `/orders/{order_id}/complete` | 確認完成並重算信用 |
| POST | `/orders/{order_id}/cancel` | 取消待接單訂單 |
| POST | `/orders/{order_id}/reviews` | 提交雙向評價 |
| POST | `/users/availability` | 接單者設定可接單時段與目前位置 |
| POST | `/orders/{order_id}/match` | AI 智慧媒合（訂單找人，計算三階段推薦排序） |
| GET | `/runners/{runner_id}/recommended-orders` | AI 順路推薦（人找訂單，依位置與空堂排序待接訂單） |
| POST | `/rewards/suggest` | 動態獎勵金建議（依時段、步行距離、樓層與供需計算） |
| POST | `/ai/parse-order` | Gemini 自然語言發單解析（將口語輸入轉為結構化訂單草稿） |

## 訂單狀態

沿用資料庫原本五種狀態，不新增欄位或狀態：

- `pending`：已發布／待接單
- `accepted`：已接單／購餐中
- `delivered`：已送達
- `completed`：已完成
- `cancelled`：已取消

MVP 目前只允許待接單訂單取消。已接單後的取消、退款或責任歸屬暫不處理。

## 信用計算口徑（MVP）

- 接單者完成率：完成接單筆數 ÷ 全部接單筆數。
- 接單者準時率：準時送達筆數 ÷ 有送達時間的接單筆數。送達時間不晚於訂單 deadline 視為準時。
- 未取消比例：未取消筆數 ÷ 全部相關筆數。
- 評價：收到的評價平均分 ÷ 5。
- 發單者資訊完整度：餐廳、送達地點、期限及至少一筆餐點明細皆存在，視為完整。
- 新使用者或尚無樣本的指標暫以 1.0 計算，維持資料庫預設 5 分。

  ## AI 媒合與獎勵金計算口徑（MVP）

- 候選人硬性過濾：同校區、帳號狀態為 `active`、非發單本人，且目前時間落於可接單時段內。
- 任務總耗時估算：步行至餐廳 ＋ 預設取餐等待 5 分鐘 ＋ 餐廳送達目的地（採用 `walking_times` 含樓層補償時間），總耗時超過剩餘有效空堂者不予推薦。
- 動態權重配置：一般常態採信用 `0.4`、路線 `0.4`、時間 `0.2`；午餐尖峰（11:50～12:30）切換為信用 `0.3`、路線 `0.3`、時間 `0.4`。同餐廳歷史完成經驗每筆+1 分（上限 +3分）。
- 動態獎勵金：基礎 15 元，遇尖峰／緊迫時段 +5元、偏遠大樓（R 棟）+5元
- 生成式 AI 模型：採用 `gemini-3.8-flash`（遇高負載自動切換 `gemini-3.5-flash-lite` 備援）。

以上是為了讓展示流程可運作而採用的統計口徑。若正式競賽規格另有定義，應以團隊最後確認的口徑調整。

## 自動化測試

`test_mvp_api.py` 會建立獨立臨時資料庫，不會寫入正式資料庫。執行：

```powershell
$python = ".\.venv\Scripts\python.exe"
& $python backend/test_mvp_api.py
```

測試涵蓋使用者建立、訂單建立與查詢、接單防重複、送達、完成、雙向評價及信用查詢。

`test_ai_api.py` 同樣使用獨立臨時資料庫，不會寫入正式資料庫。執行：

```powershell
$env:GEMINI_API_KEY="貼上你的_Gemini_API_Key"
$python = ".\.venv\Scripts\python.exe"
& $python backend/test_ai_api.py
```
## MVP 尚未處理

- LINE 身分驗證與 API 權限驗證。
- 已接單後取消及爭議處理。
- LINE Bot 與 Streamlit 前端整合。
- 真實環境的多程序併發壓力測試。
- 正式部署、日誌、監控與資料備份自動化。

此版本定位為可供影片操作展示的課堂專題 MVP，不應直接視為正式上線版本。
