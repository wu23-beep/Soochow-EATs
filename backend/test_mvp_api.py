"""資資吱吱 MVP API 整合測試，所有資料均寫入臨時 SQLite 資料庫。

在專案根目錄執行：
    python backend/test_mvp_api.py
"""
import os
import tempfile
from pathlib import Path
import runpy

# 必須在匯入 database.py 與 main.py 前指定臨時資料庫路徑。
test_db = Path(tempfile.gettempdir()) / "soochow_eats_mvp_api_test.db"
if test_db.exists():
    test_db.unlink()
os.environ["SOOCHOW_EATS_DB_PATH"] = str(test_db)

# 使用專案原本的建表程式，不自行改寫資料庫 schema。
runpy.run_path(str(Path(__file__).with_name("init_db.py")))

from database import get_connection  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402

# 建立影片展示會用到的最少量測試地點、餐廳與菜單。
with get_connection() as conn:
    conn.execute("ALTER TABLE locations ADD COLUMN campus TEXT")
    conn.execute(
        "INSERT INTO locations (location_name, building, floor, location_type, campus) VALUES (?, ?, ?, ?, ?)",
        ("測試校園 A 棟", "A棟", 1, "campus", "shuangxi"),
    )
    conn.execute(
        "INSERT INTO locations (location_name, building, floor, location_type, campus) VALUES (?, ?, ?, ?, ?)",
        ("測試餐廳位置", "B棟", 1, "restaurant", "shuangxi"),
    )
    conn.execute(
        "INSERT INTO restaurants (restaurant_name, location_id) VALUES (?, ?)",
        ("測試便當店", 2),
    )
    conn.execute(
        "INSERT INTO menu_items (restaurant_id, item_name, price) VALUES (?, ?, ?)",
        (1, "雞腿便當", 100),
    )

client = TestClient(app)

# 建立發單者及接單者。
requester_response = client.post("/users", json={"line_user_id": "demo_requester", "display_name": "展示發單者"})
assert requester_response.status_code == 201, requester_response.text
requester_id = requester_response.json()["user_id"]

runner_response = client.post("/users", json={"line_user_id": "demo_runner", "display_name": "展示接單者"})
assert runner_response.status_code == 201, runner_response.text
runner_id = runner_response.json()["user_id"]

# 建立訂單，後端應自行從菜單取得單價。
order_response = client.post("/orders", json={
    "requester_id": requester_id,
    "restaurant_id": 1,
    "delivery_location_id": 1,
    "deadline": "2099-12-31 23:59:59",
    "reward_amount": 20,
    "note": "不要辣",
    "items": [{"item_id": 1, "quantity": 2}],
})
assert order_response.status_code == 201, order_response.text
order_id = order_response.json()["order_id"]

# 查詢訂單，確認金額與狀態。
order_detail = client.get(f"/orders/{order_id}").json()
assert order_detail["status"] == "pending"
assert order_detail["subtotal"] == 200
assert order_detail["total_amount"] == 220

# 接單成功後，第二次接單應被拒絕。
accept_response = client.post(f"/orders/{order_id}/accept", json={"runner_id": runner_id})
assert accept_response.status_code == 200, accept_response.text
second_accept = client.post(f"/orders/{order_id}/accept", json={"runner_id": runner_id})
assert second_accept.status_code == 409, second_accept.text

# 依序送達、完成及雙向評價。
deliver_response = client.post(f"/orders/{order_id}/deliver")
assert deliver_response.status_code == 200, deliver_response.text
complete_response = client.post(f"/orders/{order_id}/complete")
assert complete_response.status_code == 200, complete_response.text

requester_review = client.post(f"/orders/{order_id}/reviews", json={
    "reviewer_id": requester_id, "rating": 5, "comment": "送餐順利"
})
assert requester_review.status_code == 201, requester_review.text
runner_review = client.post(f"/orders/{order_id}/reviews", json={
    "reviewer_id": runner_id, "rating": 4, "comment": "溝通順利"
})
assert runner_review.status_code == 201, runner_review.text
assert runner_review.json()["updated_credit"]["requester_credit"] == 4.75
assert requester_review.json()["updated_credit"]["runner_credit"] == 5.0

# 確認最終狀態及雙方信用均有數值。
final_order = client.get(f"/orders/{order_id}").json()
assert final_order["status"] == "completed"
assert final_order["runner_id"] == runner_id
assert client.get(f"/users/{requester_id}/credits").status_code == 200
assert client.get(f"/users/{runner_id}/credits").status_code == 200

# 再建立一筆訂單，確認待接單狀態可以取消。
cancel_response = client.post("/orders", json={
    "requester_id": requester_id,
    "restaurant_id": 1,
    "delivery_location_id": 1,
    "deadline": "2099-12-31 23:59:59",
    "reward_amount": 0,
    "items": [{"item_id": 1, "quantity": 1}],
})
assert cancel_response.status_code == 201, cancel_response.text
cancel_order_id = cancel_response.json()["order_id"]
cancel_result = client.post(f"/orders/{cancel_order_id}/cancel")
assert cancel_result.status_code == 200, cancel_result.text
assert client.get(f"/orders/{cancel_order_id}").json()["status"] == "cancelled"

print("MVP API 整合測試全部通過：使用者、發單、查詢、接單防重複、送達、完成、取消、雙向評價、信用更新。")
