# Soochow EATs｜資資吱吱

## MVP 後端操作、測試資料與展示流程說明

本文件整理目前專案的安裝方式、資料庫初始化、API
使用方式、測試資料、Swagger 操作順序、自動化測試與常見問題。

本版本定位為課堂專題 MVP 與影片展示用途。後端使用 FastAPI 與
SQLite，沿用專案既有資料表，提供使用者、餐廳菜單、訂單、接單、送達、完成、取消、雙向評價及信用查詢功能。

> **重要：** 本文件依據 `Soochow-EATs-MVP-redo.zip`
> 內的程式碼整理。若本機程式碼後續有修改，請以實際
> `main.py`、`init_db.py` 與資料匯入腳本為準。

------------------------------------------------------------------------

## 1. 專案功能範圍

### 1.1 已實作功能

1.  使用者建立、查詢及修改顯示名稱。
2.  查詢雙溪與城中校區。
3.  查詢校區內餐廳及餐廳菜單。
4.  建立訂單及多筆餐點明細。
5.  查詢訂單列表與訂單詳細資料。
6.  接單及防止同一筆訂單被重複承接。
7.  訂單送達、完成及待接單取消。
8.  發單者與接單者雙向評價。
9.  依目前 MVP 信用公式更新及查詢雙向信用。

### 1.2 尚未納入本版範圍

1.  LINE 身分驗證與正式登入授權。
2.  LINE Bot 前端整合。
3.  Streamlit 管理介面整合。
4.  AI 推薦模型與正式媒合排序。
5.  已接單後取消、退款及爭議處理。
6.  正式環境部署、監控與多程序壓力測試。

------------------------------------------------------------------------

## 2. 專案目錄

``` text
Soochow-EATs-MVP-redo/
└── Soochow-EATs-main/
    ├── README.md
    ├── requirements.txt
    └── backend/
        ├── database.py
        ├── init_db.py
        ├── main.py
        ├── seed_campus_data_with_campus.py
        ├── seed_menu_items.py
        ├── test_mvp_api.py
        ├── test_create_order.py
        ├── test_order_flow.py
        ├── test_matching_results.py
        └── test_real_matching.py
```

主要檔案用途：

  ----------------------------------------------------------------------------------------------------
  檔案                                        用途
  ------------------------------------------- --------------------------------------------------------
  `backend/main.py`                           FastAPI API、訂單流程及信用計算

  `backend/database.py`                       SQLite 連線及資料庫路徑設定

  `backend/init_db.py`                        建立資料表

  `backend/seed_campus_data_with_campus.py`   匯入校區、地點、餐廳與步行時間

  `backend/seed_menu_items.py`                匯入已整理的菜單品項

  `backend/test_mvp_api.py`                   使用臨時資料庫執行完整 API 整合測試

  `backend/test_create_order.py`              以互動方式建立一筆實際測試訂單

  `backend/test_order_flow.py`                舊版資料庫直接操作流程測試，會寫入正式資料庫

  `backend/test_real_matching.py`             使用模擬候選人位置與空堂資料測試規則式媒合

  `backend/test_matching_results.py`          推薦結果資料寫入測試，執行前需先檢查程式內容與資料需求
  ----------------------------------------------------------------------------------------------------

------------------------------------------------------------------------

## 3. 環境安裝

以下指令以 Windows PowerShell 為例，並假設終端機目前位於專案外層目錄：

``` text
C:\Users\<使用者>\Downloads\Soochow-EATs-MVP-redo
```

### 3.1 建立虛擬環境

第一次設定專案時執行：

``` powershell
# 建立 Python 虛擬環境
py -3.12 -m venv .venv

# 啟用虛擬環境
.\.venv\Scripts\Activate.ps1
```

若虛擬環境已建立，之後只需要啟用即可。

### 3.2 安裝套件

``` powershell
# 安裝 FastAPI、Uvicorn 與測試所需套件
python -m pip install -r .\Soochow-EATs-main\requirements.txt
```

若目前已切換到 `Soochow-EATs-main` 目錄，則使用：

``` powershell
python -m pip install -r requirements.txt
```

### 3.3 確認 Python 環境

``` powershell
# 確認目前使用的 Python
python --version

# 確認 FastAPI 與 Uvicorn 已安裝
python -m pip show fastapi uvicorn httpx
```

------------------------------------------------------------------------

## 4. SQLite 資料庫初始化

### 4.1 資料庫位置

預設資料庫檔案：

``` text
Soochow-EATs-main/backend/soochow_eats.db
```

`database.py` 會優先讀取環境變數
`SOOCHOW_EATS_DB_PATH`。若該環境變數沒有設定，才使用上述預設路徑。

可用 PowerShell 檢查：

``` powershell
# 查看是否指定其他資料庫路徑
echo $env:SOOCHOW_EATS_DB_PATH

# 確認預設資料庫檔案是否存在
Test-Path .\Soochow-EATs-main\backend\soochow_eats.db

# 查看資料庫檔案大小
Get-Item .\Soochow-EATs-main\backend\soochow_eats.db
```

資料庫檔案存在不代表已經建立資料表。若檔案大小為 0
bytes，通常代表資料庫尚未初始化。

### 4.2 第一次初始化的執行順序

請在專案外層目錄執行：

``` powershell
# 第一步：建立 SQLite 資料表
python .\Soochow-EATs-main\backend\init_db.py

# 第二步：匯入校區、地點、餐廳與步行時間
python .\Soochow-EATs-main\backend\seed_campus_data_with_campus.py

# 第三步：匯入已整理的菜單品項
python .\Soochow-EATs-main\backend\seed_menu_items.py
```

三個步驟的用途：

  --------------------------------------------------------------------------------------------------------------
  順序                    腳本                                作用
  ----------------------- ----------------------------------- --------------------------------------------------
  1                       `init_db.py`                        建立使用者、地點、餐廳、菜單、訂單、評價等資料表

  2                       `seed_campus_data_with_campus.py`   建立雙溪與城中校區資料、餐廳位置及步行時間，並為
                                                              `locations` 增加 `campus` 欄位

  3                       `seed_menu_items.py`                依餐廳名稱匯入已整理的餐點與價格
  --------------------------------------------------------------------------------------------------------------

### 4.3 資料初始化注意事項

1.  第一次建立資料庫時，依序執行三個初始化腳本。
2.  `init_db.py` 使用
    `CREATE TABLE IF NOT EXISTS`，既有資料表不會因此自動修復欄位。
3.  校區匯入腳本會嘗試補上 `locations.campus`
    欄位，並依地點名稱補上校區值。
4.  菜單匯入腳本會略過已存在的品項，不會自動覆寫既有價格。
5.  菜單資料只包含目前已整理的品項，並非所有店家完整菜單。
6.  若資料庫已有重要資料，執行初始化或匯入前應先備份。
7.  不建議為了解決單一 API 錯誤就直接刪除資料庫或重建資料庫。

### 4.4 備份資料庫

``` powershell
# 將目前資料庫複製一份備份
Copy-Item `
  .\Soochow-EATs-main\backend\soochow_eats.db `
  .\Soochow-EATs-main\backend\soochow_eats_backup.db
```

------------------------------------------------------------------------

## 5. 啟動 FastAPI

在專案外層目錄執行：

``` powershell
# 啟動 FastAPI，指定 backend 資料夾中的 main.py
python -m uvicorn main:app --app-dir Soochow-EATs-main/backend --reload
```

若目前終端機已切換到 `Soochow-EATs-main` 目錄，則執行：

``` powershell
# 在專案主目錄啟動 FastAPI
python -m uvicorn main:app --app-dir backend --reload
```

成功啟動時，終端機會顯示類似：

``` text
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

### 5.1 Swagger 文件

瀏覽器開啟：

http://127.0.0.1:8000/docs

Swagger 可直接查看 API、輸入測試資料並執行請求。

### 5.2 確認 API 運作

執行 `GET /`，預期回傳：

``` json
{
  "message": "Soochow EATs API 運作正常"
}
```

停止伺服器可在執行 Uvicorn 的終端機按下 `Ctrl + C`。

------------------------------------------------------------------------

## 6. API 清單

  ------------------------------------------------------------------------------------------------------
  方法                    路徑                                  用途
  ----------------------- ------------------------------------- ----------------------------------------
  GET                     `/`                                   確認 API 運作

  GET                     `/campuses`                           查詢校區

  GET                     `/restaurants?campus=shuangxi`        查詢雙溪校區餐廳

  GET                     `/restaurants?campus=downtown`        查詢城中校區餐廳

  GET                     `/restaurants/{restaurant_id}/menu`   查詢指定餐廳菜單

  POST                    `/users`                              建立使用者

  GET                     `/users/{user_id}`                    查詢使用者

  PATCH                   `/users/{user_id}`                    修改使用者顯示名稱

  GET                     `/users/{user_id}/credits`            查詢使用者雙向信用

  POST                    `/orders`                             建立訂單

  GET                     `/orders`                             查詢訂單列表

  GET                     `/orders/{order_id}`                  查詢訂單詳細資料

  POST                    `/orders/{order_id}/accept`           接單

  POST                    `/orders/{order_id}/deliver`          更新為已送達

  POST                    `/orders/{order_id}/complete`         確認完成訂單

  POST                    `/orders/{order_id}/cancel`           取消待接單訂單

  POST                    `/orders/{order_id}/reviews`          提交單向評價，每筆訂單由雙方各提交一次
  ------------------------------------------------------------------------------------------------------

------------------------------------------------------------------------

## 7. 校區測試

### 7.1 獲得校區

`GET /campuses`

直接獲取雙溪、城中校區id

### 7.2 取得各校區的餐廳

`GET /restaurants`

只能填 7.1 取得的ID，其他輸入會顯示無效校區

### 7.3 取得各餐廳菜單

`GET /restaurants/{restaurants_id}/menu`

有些餐廳沒有菜單，我測試用 id:19 沐達早餐

以上有收到回應就是正常

------------------------------------------------------------------------

## 8. 使用者 API 測試

建議先建立兩位測試使用者，分別扮演發單者與接單者。

### 8.1 建立發單者

`POST /users`

Request Body：

``` json
{
  "line_user_id": "demo_requester",
  "display_name": "展示發單者"
}
```

預期狀態碼：`201 Created`

回傳資料會包含資料庫自動產生的 `user_id`、雙向信用、帳號狀態及建立時間。

### 8.2 建立接單者

再次執行 `POST /users`：

``` json
{
  "line_user_id": "demo_runner",
  "display_name": "展示接單者"
}
```

預期狀態碼：`201 Created`

請記下兩位使用者實際回傳的
`user_id`。後續建立訂單、接單及評價都會使用這兩個 ID。

### 8.3 查詢使用者

`GET /users/{user_id}`

將 `{user_id}` 替換成實際 ID，例如：

``` text
GET /users/1
```

預期狀態碼：`200 OK`

### 8.4 修改使用者名稱

`PATCH /users/{user_id}`

Request Body：

``` json
{
  "display_name": "測試發單者"
}
```

預期狀態碼：`200 OK`

### 8.5 測試重複註冊

再次使用相同的 `line_user_id`：

``` json
{
  "line_user_id": "demo_requester",
  "display_name": "重複註冊測試"
}
```

預期狀態碼：`409 Conflict`

原因：`line_user_id` 在資料庫中具有唯一性限制。

------------------------------------------------------------------------

## 9. 餐廳與菜單 API 測試

### 9.1 查詢校區

`GET /campuses`

預期回傳兩個校區：

  id           校區名稱
  ------------ ----------
  `shuangxi`   雙溪校區
  `downtown`   城中校區

### 9.2 查詢餐廳

雙溪校區：

``` text
GET /restaurants?campus=shuangxi
```

城中校區：

``` text
GET /restaurants?campus=downtown
```

`campus` 必須使用 `shuangxi` 或 `downtown`，不能直接輸入中文校區名稱。

### 9.3 查詢菜單

先從餐廳查詢結果取得 `restaurant_id`，再執行：

``` text
GET /restaurants/{restaurant_id}/menu
```

例如：

``` text
GET /restaurants/1/menu
```

餐點 ID、餐廳 ID 會依資料庫實際匯入結果而變動，請勿假設每台電腦的 ID
都相同。

------------------------------------------------------------------------

## 9. 訂單建立與測試資料

### 9.1 建立訂單前需要準備的資料

建立訂單前，先取得以下資訊：

  ------------------------------------------------------------------------------
  欄位                     資料來源                說明
  ------------------------ ----------------------- -----------------------------
  `requester_id`           `POST /users`           發單者的 user_id

  `restaurant_id`          `GET /restaurants`      餐廳 ID

  `delivery_location_id`   校區地點資料            送達地點的
                                                   location_id，必須是校園地點

  `item_id`                餐廳菜單 API            所選餐點 ID

  `deadline`               自行設定                有效日期時間

  `reward_amount`          自行設定                獎勵金，可為 0

  `quantity`               自行設定                餐點數量
  ------------------------------------------------------------------------------

### 9.2 建立訂單

`POST /orders`

以下是請求格式範例。範例中的 ID 僅供理解欄位用途，實際測試時請替換成 API
查到的 ID。

``` json
{
  "requester_id": 1,
  "restaurant_id": 19,
  "delivery_location_id": 1,
  "deadline": "2099-12-31 23:59:59",
  "reward_amount": 20,
  "note": "不要辣",
  "items": [
    {
      "item_id": 1,
      "quantity": 2,
      "special_request": "醬料另外放"
    }
  ]
}
```

預期狀態碼：`201 Created`

預期回傳格式：

``` json
{
  "order_id": 1,
  "status": "pending",
  "message": "訂單建立成功"
}
```

重要規則：

1.  `items` 至少需要一筆餐點。
2.  `quantity` 必須介於 1 至 99。
3.  `item_id` 必須屬於所選餐廳，且餐點目前可供應。
4.  餐點價格由後端從 SQLite 菜單讀取，呼叫端不需要也不能自行指定價格。
5.  `deadline` 必須是有效日期時間，例如 `2026-11-25 12:30:00`。
6.  `delivery_location_id` 必須對應 `location_type = campus`
    的校園地點。
7.  `reward_amount` 預設為 0，允許範圍為 0 至 10000。

### 9.3 查詢訂單列表

查詢全部訂單：

``` text
GET /orders
```

依發單者查詢：

``` text
GET /orders?requester_id=1
```

依狀態查詢：

``` text
GET /orders?status=pending
```

可同時使用兩個條件：

``` text
GET /orders?requester_id=1&status=pending
```

合法狀態值：

`pending`、`accepted`、`delivered`、`completed`、`cancelled`

### 9.4 查詢訂單詳細資料

``` text
GET /orders/{order_id}
```

請使用建立訂單時回傳的
`order_id`。詳細資料會包含訂單與餐點明細，並呈現餐點小計及總金額等資訊。

------------------------------------------------------------------------

## 10. 完整訂單流程測試

建議使用同一筆訂單依序測試，避免跳過狀態造成 409 錯誤。

### 10.1 訂單狀態流轉

``` text
建立訂單
   |
   v
pending（待接單）
   |
   | 接單
   v
accepted（已接單／購餐中）
   |
   | 更新送達
   v
delivered（已送達）
   |
   | 發單者確認完成
   v
completed（已完成）
   |
   | 雙方各自評價
   v
信用資料更新
```

取消流程獨立進行：

``` text
pending（待接單）
   |
   | 取消
   v
cancelled（已取消）
```

目前 MVP 只允許 `pending` 訂單取消。已接單後的取消流程尚未實作。

### 10.2 接單

`POST /orders/{order_id}/accept`

Request Body：

``` json
{
  "runner_id": 2
}
```

將 `runner_id` 替換成接單者實際的 `user_id`。

預期狀態碼：`200 OK`

預期狀態：`accepted`

限制：

1.  訂單必須為 `pending`。
2.  發單者不能接自己的訂單。
3.  接單者必須存在且帳號狀態為 `active`。
4.  同一筆訂單只能成功接單一次。

### 10.3 測試重複接單

對同一筆已成功接單的訂單，再次執行：

`POST /orders/{order_id}/accept`

預期狀態碼：`409 Conflict`

後端使用 SQLite `BEGIN IMMEDIATE`
與條件式更新處理接單交易，降低多人同時接單時發生重複承接的風險。

### 10.4 更新為已送達

`POST /orders/{order_id}/deliver`

此 API 不需要 Request Body。

預期狀態碼：`200 OK`

前置條件：訂單狀態必須為 `accepted`。

執行後： 1. `orders.status` 更新為 `delivered`。 2. 對應的
`order_matches.status` 更新為 `delivered`。 3. 系統記錄送達時間
`delivered_at`。

### 10.5 確認完成

`POST /orders/{order_id}/complete`

此 API 不需要 Request Body。

預期狀態碼：`200 OK`

前置條件：訂單必須為 `delivered`，且存在有效的接單紀錄。

執行後： 1. `orders.status` 更新為 `completed`。 2.
`order_matches.status` 更新為 `completed`。 3.
重新計算發單者與接單者的信用。

### 10.6 取消待接單訂單

`POST /orders/{order_id}/cancel`

此 API 不需要 Request Body。

預期狀態碼：`200 OK`

前置條件：訂單狀態必須為 `pending`。

已接單、已送達或已完成的訂單不能透過目前的取消 API 取消，預期回傳
`409 Conflict`。

------------------------------------------------------------------------

## 11. 雙向評價測試

評價只能在訂單完成後提交，且只有發單者與接單者可以評價。

### 11.1 發單者評價接單者

`POST /orders/{order_id}/reviews`

Request Body：

``` json
{
  "reviewer_id": 1,
  "rating": 5,
  "comment": "送餐準時，服務很好"
}
```

`reviewer_id` 填入發單者的 user_id。

預期狀態碼：`201 Created`

### 11.2 接單者評價發單者

同一筆訂單再次執行：

``` json
{
  "reviewer_id": 2,
  "rating": 4,
  "comment": "交易順利，溝通良好"
}
```

`reviewer_id` 填入接單者的 user_id。

預期狀態碼：`201 Created`

### 11.3 評價限制

1.  訂單必須為 `completed`。
2.  評分範圍為 1 至 5。
3.  評價者必須是該筆訂單的發單者或接單者。
4.  同一位使用者不能重複評價同一筆訂單。
5.  每次評價成功後，系統會重新計算被評價者的信用。

------------------------------------------------------------------------

## 12. 信用查詢與計算

### 12.1 查詢信用

`GET /users/{user_id}/credits`

例如：

``` text
GET /users/1/credits
```

回傳發單者信用與接單者信用。

### 12.2 接單者信用公式

``` text
Cr = 5 × (0.35 × Rc + 0.25 × Rt + 0.20 × Rn + 0.20 × Rv)
```

  指標   意義
  ------ ----------------------------
  `Rc`   訂單完成率
  `Rt`   準時率
  `Rn`   未取消比例
  `Rv`   發單者給予的平均評價除以 5

### 12.3 發單者信用公式

``` text
Cp = 5 × (0.30 × Rf + 0.25 × Rn + 0.20 × Ri + 0.25 × Rv)
```

  指標   意義
  ------ ----------------------------
  `Rf`   交易履行率
  `Rn`   未取消比例
  `Ri`   訂單資訊完整度
  `Rv`   接單者給予的平均評價除以 5

### 12.4 目前 MVP 統計口徑

1.  接單者完成率：完成接單筆數除以全部接單筆數。
2.  接單者準時率：準時送達筆數除以有送達時間的接單筆數。送達時間不晚於訂單
    deadline 即視為準時。
3.  未取消比例：未取消筆數除以全部相關筆數。
4.  評價指標：收到的評價平均分數除以 5。
5.  發單者資訊完整度：餐廳、送達地點、期限及至少一筆餐點明細皆存在，視為完整。
6.  新使用者或尚無樣本的指標暫以 1.0 計算，使新使用者維持資料庫預設 5
    分。
7.  指標限制在 0 至 1，最後依公式換算為 0 至 5 分。

以上統計口徑屬於目前 MVP
的實作決策。若正式規格書對完成率、取消率或評價統計另有定義，應再依團隊確認結果調整。

------------------------------------------------------------------------

## 13. 建議的 Swagger 完整測試順序

以下順序適合第一次手動測試，也可作為影片展示腳本。

  順序   API                            操作                   預期結果
  ------ ------------------------------ ---------------------- ----------
  1      `GET /`                        確認伺服器             200
  2      `GET /campuses`                查詢校區               200
  3      `GET /restaurants`             查詢餐廳               200
  4      `GET /restaurants/{id}/menu`   查詢菜單               200
  5      `POST /users`                  建立發單者             201
  6      `POST /users`                  建立接單者             201
  7      `GET /users/{id}`              查詢使用者             200
  8      `PATCH /users/{id}`            修改顯示名稱           200
  9      `POST /orders`                 建立訂單               201
  10     `GET /orders`                  查詢訂單列表           200
  11     `GET /orders/{id}`             查詢訂單明細           200
  12     `POST /orders/{id}/accept`     接單                   200
  13     `POST /orders/{id}/accept`     重複接單測試           409
  14     `POST /orders/{id}/deliver`    更新送達               200
  15     `POST /orders/{id}/complete`   完成訂單               200
  16     `POST /orders/{id}/reviews`    發單者評價接單者       201
  17     `POST /orders/{id}/reviews`    接單者評價發單者       201
  18     `GET /users/{id}/credits`      查詢雙方信用           200
  19     `POST /orders`                 建立另一筆待接單訂單   201
  20     `POST /orders/{id}/cancel`     取消待接單訂單         200

測試時請記錄每次建立使用者及訂單所回傳的 ID。不要直接假設 ID 一定從 1
開始，因為資料庫可能已有其他資料。

------------------------------------------------------------------------

## 14. 自動化整合測試

### 14.1 測試檔案

``` text
backend/test_mvp_api.py
```

此測試會： 1. 建立獨立的臨時 SQLite 資料庫。 2. 使用 `init_db.py`
建立測試資料表。 3. 建立最少量測試校區、餐廳與菜單。 4.
建立發單者與接單者。 5. 測試建立訂單及查詢金額。 6.
測試接單與重複接單防護。 7. 測試送達、完成及雙向評價。 8.
測試信用更新及查詢。 9. 測試待接單訂單取消。

此測試使用臨時資料庫，不會把測試訂單寫入平常操作的
`backend/soochow_eats.db`。

### 14.2 執行方式

在專案外層目錄執行：

``` powershell
# 執行完整 API 自動化整合測試
python .\Soochow-EATs-main\backend\test_mvp_api.py
```

若目前位於 `Soochow-EATs-main` 目錄：

``` powershell
# 執行完整 API 自動化整合測試
python .\backend\test_mvp_api.py
```

全部通過時，預期顯示：

``` text
MVP API 整合測試全部通過：使用者、發單、查詢、接單防重複、送達、完成、取消、雙向評價、信用更新。
```

### 14.3 自動化測試與 Swagger 測試的差異

  項目                     自動化整合測試      Swagger 手動測試
  ------------------------ ------------------- ------------------------
  使用資料庫               臨時測試資料庫      預設正式開發資料庫
  是否寫入平常的測試資料   否                  是
  適合用途                 快速驗證 API 流程   確認實際資料與展示操作
  測試資料                 程式自動建立        由操作者輸入或查詢

------------------------------------------------------------------------

## 15. 其他測試腳本注意事項

### 15.1 `test_create_order.py`

此腳本會以互動方式讓操作者選擇校區、餐廳、菜色、數量及送達地點，並在確認後寫入目前設定的
SQLite 資料庫。

執行方式：

``` powershell
# 先切換到 backend 目錄
cd .\Soochow-EATs-main\backend

# 執行互動式建立訂單
python test_create_order.py
```

此腳本會建立或重複使用測試發單者
`test_soochow_eats_order_001`，並新增訂單及餐點明細。它會寫入開發資料庫，請勿把它當成唯讀測試。

### 15.2 `test_order_flow.py`

此為直接操作 SQLite
的舊版流程測試，會建立測試接單者，並直接更新訂單、接單紀錄及評價資料。

執行前應確認目標資料庫及訂單內容。此腳本會寫入資料庫，不建議與 Swagger
流程測試同時操作同一筆訂單。

### 15.3 `test_real_matching.py`

此腳本會挑選最新一筆待接訂單，建立模擬候選人及空堂資料，再依位置、步行時間、信用及可用時間計算規則式媒合分數，並寫入
`matching_results`。

注意： 1. 候選人的位置及空堂為模擬資料。 2.
等餐時間目前使用程式內的測試假設值。 3.
步行時間資料來自資料庫；若資料為人工估測，結果也只能視為示範。 4.
執行前需先建立一筆尚未過期的 `pending` 訂單。 5.
此腳本會寫入使用者、空堂及媒合結果資料。

### 15.4 `test_matching_results.py`

此檔案屬於媒合結果測試腳本。執行前請先閱讀程式碼，確認它使用的訂單、使用者及資料欄位均已存在。此類測試可能寫入
`matching_results`，請先備份資料庫。

------------------------------------------------------------------------

## 16. 常見問題排查

### 16.1 `sqlite3.OperationalError: no such table: users`

可能原因： 1. 資料庫尚未執行 `init_db.py`。 2. FastAPI
連線到另一個空資料庫。 3. `SOOCHOW_EATS_DB_PATH` 指向錯誤位置。

檢查方式：

``` powershell
# 檢查環境變數
echo $env:SOOCHOW_EATS_DB_PATH

# 檢查預設資料庫
Test-Path .\Soochow-EATs-main\backend\soochow_eats.db

# 查看檔案大小
Get-Item .\Soochow-EATs-main\backend\soochow_eats.db
```

確認資料庫路徑後，再決定是否需要初始化。若資料庫已有重要資料，先備份。

### 16.2 `GET /restaurants?campus=城中校區` 回傳 400

`campus` 參數只接受以下值：

``` text
shuangxi
downtown
```

正確範例：

``` text
GET /restaurants?campus=downtown
```

### 16.3 餐廳查詢回傳 409

若錯誤內容指出 `locations` 缺少 `campus` 欄位，請確認已執行：

``` powershell
python .\Soochow-EATs-main\backend\seed_campus_data_with_campus.py
```

### 16.4 菜單查詢沒有資料

可能原因： 1. 該餐廳目前沒有已匯入的菜單品項。 2.
菜單品項被設為不可供應。 3. 菜單匯入腳本找不到唯一對應的餐廳名稱。

可重新檢查 `seed_menu_items.py` 的匯入輸出，並改選有菜單資料的餐廳測試。

### 16.5 建立訂單回傳 400

請依錯誤內容檢查： 1. 餐點 ID 是否屬於所選餐廳。 2. 餐點是否仍可供應。
3. 送達地點 ID 是否存在。 4. 送達地點是否為校園地點。

### 16.6 建立訂單回傳 404

請確認發單者、餐廳及送達地點 ID 都存在，且發單者帳號與餐廳處於有效狀態。

### 16.7 接單或狀態更新回傳 409

通常代表訂單目前狀態不符合操作條件。例如： 1. 已接單的訂單再次接單。 2.
尚未接單就呼叫送達 API。 3. 尚未送達就呼叫完成 API。 4.
已接單的訂單嘗試取消。

請先執行 `GET /orders/{order_id}` 確認目前狀態。

### 16.8 Swagger 顯示 500

500 代表伺服器內部發生未預期錯誤。請查看執行 Uvicorn 的終端機，找到
`Traceback` 最後一行的例外訊息，再依實際錯誤排查。不要只根據 Swagger 的
`Internal Server Error` 猜測原因。

------------------------------------------------------------------------

## 17. 訂單狀態定義

本版沿用資料庫既有五種訂單狀態：

  狀態          中文說明         代表情境
  ------------- ---------------- ------------------------
  `pending`     待接單           發單者已發布訂單
  `accepted`    已接單／購餐中   接單者已承接，正在處理
  `delivered`   已送達           接單者已送達餐點
  `completed`   已完成           發單者確認收到餐點
  `cancelled`   已取消           待接單訂單被取消

目前沒有額外建立 `purchasing` 狀態。購餐中暫時歸類在 `accepted`。

------------------------------------------------------------------------

## 18. 展示影片建議流程

建議以兩個使用者完成一筆完整交易，再以另一筆訂單展示取消功能。

### 第一段：基本資料

1.  顯示校區清單。
2.  選擇校區並查詢餐廳。
3.  查詢餐廳菜單。
4.  建立發單者及接單者。
5.  顯示兩位使用者初始信用。

### 第二段：建立與承接訂單

1.  發單者建立訂單。
2.  顯示餐點明細、餐點小計及獎勵金。
3.  查詢待接訂單列表。
4.  接單者承接訂單。
5.  再次嘗試接單，展示系統拒絕重複承接。

### 第三段：完成交易

1.  將訂單更新為已送達。
2.  發單者確認完成。
3.  發單者評價接單者。
4.  接單者評價發單者。
5.  查詢雙方更新後的信用。

### 第四段：取消流程

1.  建立另一筆訂單。
2.  保持訂單為 `pending`。
3.  呼叫取消 API。
4.  查詢訂單，確認狀態為 `cancelled`。

------------------------------------------------------------------------

## 19. 目前實作限制與解讀提醒

1.  本版本以課堂專題及影片展示為目標，尚未具備正式服務所需的身分驗證與權限控管。
2.  API 的 `reviewer_id`、`runner_id` 等欄位由呼叫端提供，目前沒有 LINE
    身分驗證來確認呼叫者本人。
3.  目前的送達 API 沒有驗證呼叫者是否為該訂單接單者。
4.  目前的完成 API 沒有驗證呼叫者是否為發單者。
5.  訂單取消目前僅支援 `pending` 狀態。
6.  步行時間資料若為人工估測，不能當成實際導航時間。
7.  媒合測試腳本中的部分候選人位置、空堂與等餐時間為模擬或測試假設。
8.  信用統計口徑是目前 MVP
    的實作版本，後續仍可依團隊確認的正式規格調整。
9.  自動化整合測試通過代表測試案例中的 API
    流程符合預期，不代表已完成正式環境安全性、併發壓力或部署測試。

------------------------------------------------------------------------

## 20. 開發者每次啟動專案的快速檢查清單

第一次設定完成後，日常啟動可依序執行：

``` powershell
# 1. 切換到專案外層目錄
cd C:\Users\<使用者>\Downloads\Soochow-EATs-MVP-redo

# 2. 啟用虛擬環境
.\.venv\Scripts\Activate.ps1

# 3. 啟動 FastAPI
python -m uvicorn main:app --app-dir Soochow-EATs-main/backend --reload
```

接著開啟：

http://127.0.0.1:8000/docs

日常啟動時通常不需要重新執行資料庫初始化。只有在第一次建立資料庫或確認需要補建資料時，才執行對應的初始化或匯入腳本。

------------------------------------------------------------------------

**文件版本：** MVP 操作與測試說明\
**適用範圍：** Soochow EATs FastAPI 後端\
**資料庫：** SQLite\
**API 文件：** FastAPI Swagger UI
