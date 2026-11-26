"""Soochow EATs AI 媒合、動態獎勵金與 Gemini 摘要自動化測試。

在專案根目錄執行：
    python backend/test_ai_api.py
"""
from datetime import datetime, timedelta
import os
from pathlib import Path
import sys
import tempfile

# 1. 設定臨時測試資料庫路徑，並將 backend 加入模組搜尋路徑
test_db = Path(tempfile.gettempdir()) / "soochow_eats_ai_api_test.db"
if test_db.exists():
    test_db.unlink()
os.environ["SOOCHOW_EATS_DB_PATH"] = str(test_db)

backend_dir = str(Path(__file__).resolve().parent)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# 2. 依序匯入並初始化資料庫、匯入雙校區與菜單
import init_db  # noqa: E402, F401
import seed_campus_data_with_campus  # noqa: E402
import seed_menu_items  # noqa: E402

seed_campus_data_with_campus.seed()
seed_menu_items.main()

from database import get_connection  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)
now = datetime.now()
deadline_str = (now + timedelta(minutes=50)).strftime("%Y-%m-%d %H:%M:%S")
avail_from = (now - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")

# 3. 查詢雙溪校區餐廳與地點 ID
res_resp = client.get("/restaurants?campus=shuangxi")
assert res_resp.status_code == 200, f"查詢餐廳失敗 ({res_resp.status_code})：{res_resp.text}"
restaurants = res_resp.json()
target_rest = next(r for r in restaurants if r["restaurant_name"] == "蛋白盒子")

with get_connection() as conn:
    loc_a = conn.execute("SELECT location_id FROM locations WHERE location_name = '雙溪校區A棟'").fetchone()["location_id"]
    loc_b = conn.execute("SELECT location_id FROM locations WHERE location_name = '雙溪校區B棟'").fetchone()["location_id"]
    loc_r = conn.execute("SELECT location_id FROM locations WHERE location_name = '雙溪校區R棟'").fetchone()["location_id"]
    menu_item = conn.execute(
        "SELECT item_id FROM menu_items WHERE restaurant_id = ? LIMIT 1",
        (target_rest["restaurant_id"],),
    ).fetchone()["item_id"]

# 4. 測試【動態獎勵金建議 API】
reward_a = client.post("/rewards/suggest", json={
    "restaurant_id": target_rest["restaurant_id"],
    "delivery_location_id": loc_a,
    "deadline": deadline_str,
}).json()
reward_r = client.post("/rewards/suggest", json={
    "restaurant_id": target_rest["restaurant_id"],
    "delivery_location_id": loc_r,
    "deadline": deadline_str,
}).json()

print("\n=== 1. 動態獎勵金建議測試 ===")
print(f"送達 A 棟建議獎勵：{reward_a['suggested_reward']} 元 | 原因：{reward_a['reasons']}")
print(f"送達 R 棟建議獎勵：{reward_r['suggested_reward']} 元 | 原因：{reward_r['reasons']}")
assert reward_r["suggested_reward"] > reward_a["suggested_reward"]

# 5. 建立發單者與 3 位模擬接單者
poster = client.post("/users", json={"line_user_id": "ai_test_poster", "display_name": "發單同學小明"}).json()
r1 = client.post("/users", json={"line_user_id": "ai_test_r1", "display_name": "順路小華(B棟/高信用)"}).json()
r2 = client.post("/users", json={"line_user_id": "ai_test_r2", "display_name": "順路小美(A棟/中信用)"}).json()
r3 = client.post("/users", json={"line_user_id": "ai_test_r3", "display_name": "趕課小強(空堂僅5分鐘)"}).json()

with get_connection() as conn, conn:
    conn.execute("UPDATE users SET runner_credit = 4.9 WHERE user_id = ?", (r1["user_id"],))
    conn.execute("UPDATE users SET runner_credit = 4.2 WHERE user_id = ?", (r2["user_id"],))
    conn.execute("UPDATE users SET runner_credit = 5.0 WHERE user_id = ?", (r3["user_id"],))

client.post("/users/availability", json={
    "user_id": r1["user_id"],
    "current_location_id": loc_b,
    "available_from": avail_from,
    "available_until": (now + timedelta(minutes=60)).strftime("%Y-%m-%d %H:%M:%S"),
    "willing_to_accept": 1,
})
client.post("/users/availability", json={
    "user_id": r2["user_id"],
    "current_location_id": loc_a,
    "available_from": avail_from,
    "available_until": (now + timedelta(minutes=45)).strftime("%Y-%m-%d %H:%M:%S"),
    "willing_to_accept": 1,
})
client.post("/users/availability", json={
    "user_id": r3["user_id"],
    "current_location_id": loc_b,
    "available_from": avail_from,
    "available_until": (now + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S"),
    "willing_to_accept": 1,
})

# 6. 建立測試訂單（蛋白盒子 -> 雙溪校區A棟）
order = client.post("/orders", json={
    "requester_id": poster["user_id"],
    "restaurant_id": target_rest["restaurant_id"],
    "delivery_location_id": loc_a,
    "deadline": deadline_str,
    "reward_amount": reward_a["suggested_reward"],
    "items": [{"item_id": menu_item, "quantity": 1}],
}).json()
order_id = order["order_id"]

# 7. 測試【訂單找人 AI 媒合 API + Gemini 推薦摘要】
match_res = client.post(f"/orders/{order_id}/match")
assert match_res.status_code == 200, match_res.text
match_data = match_res.json()

print("\n=== 2. 訂單找人 AI 三階段媒合結果 ===")
print(f"訂單 #{order_id} | 餐廳：{match_data['restaurant_name']} -> {match_data['delivery_location']}")
print(f"運作模式：{match_data['mode']} | 權重：{match_data['weights']}")
for rec in match_data["recommendations"]:
    print(
        f"第 {rec['rank_position']} 名：{rec['display_name']} | "
        f"預估耗時 {rec['t_total_minutes']} 分 | "
        f"信用 {rec['credit_score']} / 路線 {rec['route_score']} / 時間 {rec['time_score']} | "
        f"總分 {rec['final_score']}"
    )
print(f"AI 推薦摘要：{match_data['ai_summary']}")
assert match_data["candidate_count"] == 2

# 8. 測試【人找訂單 AI 順路推薦 API】
runner_rec = client.get(
    f"/runners/{r1['user_id']}/recommended-orders",
    params={"current_location_id": loc_b, "free_minutes": 60},
).json()
print("\n=== 3. 人找訂單 AI 順路推薦結果 ===")
print(f"接單者：{r1['display_name']} | 可接推薦訂單數：{runner_rec['count']}")
for o in runner_rec["recommended_orders"]:
    print(f"訂單 #{o['order_id']} | {o['restaurant_name']} -> {o['delivery_location']} | 獎勵金 {o['reward_amount']} 元 | 推薦分 {o['match_score']}")


# 9. 若有設定 GEMINI_API_KEY，額外測試自然語言發單解析
if os.environ.get("GEMINI_API_KEY"):
    nlp_resp = client.post("/ai/parse-order", json={
        "campus": "shuangxi",
        "text": "幫我去蛋白盒子買一份舒肥雞胸餐不要辣，送到雙溪校區A棟，獎勵金20元",
    })
    print("\n=== 4. Gemini 自然語言發單解析結果 ===")
    if nlp_resp.status_code == 200:
        print(nlp_resp.json()["parsed_order"])
    else:
        print(f"⚠️ Gemini 呼叫回傳狀態碼 {nlp_resp.status_code}：{nlp_resp.json()}")

print("\n✅ AI 媒合、動態獎勵金與 Gemini 整合測試全部通過！")