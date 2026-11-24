# Soochow EATs

東吳大學黑客松校園智慧代購平台的資料庫原型。使用 SQLite 儲存雙溪與城中校區資料、餐廳與菜單、訂單、雙向評價及規則式媒合結果。FastAPI 提供校區、餐廳及菜單的查詢介面。

## 專案結構

```text
.
├── .gitignore
├── README.md
├── requirements.txt
└── backend/
    ├── database.py                       # SQLite 路徑、連線與外鍵設定
    ├── init_db.py                        # 建立 11 張資料表
    ├── main.py                           # FastAPI 查詢端點
    ├── seed_campus_data_with_campus.py   # 校區地點、餐廳及預估步行時間
    ├── seed_menu_items.py                # 菜單匯入
    ├── test_create_order.py              # 互動式發單
    ├── test_matching_results.py          # 用固定測試分數驗證推薦排名與儲存
    ├── test_real_matching.py             # 用校區、空堂與步行時間測試規則式媒合
    └── test_order_flow.py                # 接單、送達、完成與雙向評價
```

## 安裝與初始化

從 GitHub Repository 複製或下載專案後，在專案根目錄開啟 PowerShell。以下指令使用 Python 3.12。

```powershell
py -3.12 -m venv .venv
$python = ".\.venv\Scripts\python.exe"
& $python -m pip install -r requirements.txt
& $python backend/init_db.py
& $python backend/seed_campus_data_with_campus.py
& $python backend/seed_menu_items.py
```

資料庫與測試腳本使用 Python 標準函式庫。啟動 API 時才需要 `requirements.txt` 中的 FastAPI 和 Uvicorn。

預設資料庫為 `backend/soochow_eats.db`。空白資料庫依序匯入後，共有 30 筆地點、25 家餐廳、204 項菜色（13 家餐廳）與 492 筆同校區的雙向預估步行紀錄。可以重跑三支腳本補齊資料。若要指定另一個檔案，請在執行前設定 `SOOCHOW_EATS_DB_PATH`，建議使用絕對路徑。

從專案根目錄啟動 API。

```powershell
& $python -m uvicorn main:app --app-dir backend
```

在瀏覽器開啟 `http://127.0.0.1:8000/docs` 即可試用。可查詢 `/campuses`、`/restaurants?campus=shuangxi`（城中使用 `downtown`）及 `/restaurants/{restaurant_id}/menu`。

## 資料表

| 資料表 | 用途與關聯 |
| --- | --- |
| `users` | LINE 使用者識別碼、顯示名稱、信用與帳號狀態 |
| `locations` | 校區、建築與樓層。校區匯入腳本會補上 `campus` 欄位 |
| `restaurants` | 餐廳與營運狀態，連至 `locations` |
| `menu_items` | 餐點、價格與供應狀態，連至 `restaurants` |
| `orders` | 發單者、餐廳、送達地點、期限、獎勵金與狀態 |
| `order_items` | 訂單明細、數量與下單單價，連至 `orders` 與 `menu_items` |
| `order_matches` | 實際接單紀錄與履約狀態，連至 `orders` 與接單者 `users` |
| `reviews` | 訂單雙向評價，連至 `orders`、評價者及受評者 |
| `user_availability` | 接單意願、位置與可接單時段，連至 `users` 與 `locations` |
| `walking_times` | 起點與終點間的預估步行分鐘數，兩端皆連至 `locations` |
| `matching_results` | 候選人的信用、路線、時間、總分、名次與推薦批次，連至 `orders` 與 `users` |

## 在臨時資料庫執行測試

測試會寫入模擬資料。從專案根目錄開啟 PowerShell，使用剛建立的虛擬環境及新的臨時 SQLite 檔案。

```powershell
$python = ".\.venv\Scripts\python.exe"
$env:SOOCHOW_EATS_DB_PATH = Join-Path ([IO.Path]::GetTempPath()) "soochow-eats-test-$([guid]::NewGuid()).db"

& $python backend/init_db.py
& $python backend/seed_campus_data_with_campus.py
& $python backend/seed_menu_items.py
& $python backend/test_create_order.py
& $python backend/test_matching_results.py
& $python backend/test_real_matching.py
& $python backend/test_order_flow.py
```

發單時選擇有菜單的餐廳，例如雙溪丼物園，最後輸入 `yes` 確認。趁訂單仍是 `pending` 時先跑兩支媒合測試，再把發單時顯示的訂單編號輸入接單測試並輸入 `yes`。成功時會看到兩批推薦結果、`completed` 訂單與兩筆互評。

測完可移除剛建立的臨時檔並解除路徑設定。

```powershell
Remove-Item -LiteralPath $env:SOOCHOW_EATS_DB_PATH
Remove-Item Env:SOOCHOW_EATS_DB_PATH
```

## 原型範圍

- 訂單、接單、評價及媒合目前透過測試腳本操作。現有 API 只提供查詢，尚未串接這些流程的 API、前端與 LINE Bot。
- 規則式媒合使用模擬的接單意願、位置和空堂資料。候餐時間採固定假設，步行時間未實測，路線限同校區。
- 菜單目前收錄可辨識項目，部分店家的菜單、客製化選項、營業時段及未確認價格仍待補齊。
