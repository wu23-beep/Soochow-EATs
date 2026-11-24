
from database import get_connection
from datetime import datetime
from uuid import uuid4

conn = get_connection()

try:
    # 1. 找一筆等待接單的訂單
    order = conn.execute("""
        SELECT o.order_id, o.requester_id,
               r.restaurant_name
        FROM orders o
        JOIN restaurants r
            ON o.restaurant_id = r.restaurant_id
        WHERE o.status = 'pending'
        ORDER BY o.order_id DESC
        LIMIT 1
    """).fetchone()

    if order is None:
        print("沒有待接訂單。")
        print("請先執行 test_create_order.py 建立新訂單。")
        raise SystemExit

    print("=== AI 媒合資料庫測試 ===")
    print("訂單編號：", order["order_id"])
    print("餐廳：", order["restaurant_name"])

    # 2. 建立三位測試候選接單者
    candidates = [
        ("ai_runner_001", "測試小華", 4.5, 95, 80),
        ("ai_runner_002", "測試小美", 4.0, 95, 95),
        ("ai_runner_003", "測試小強", 5.0, 40, 90)
    ]

    results = []

    with conn:
        for line_id, name, credit, route, time in candidates:
            conn.execute("""
                INSERT OR IGNORE INTO users
                (line_user_id, display_name, runner_credit)
                VALUES (?, ?, ?)
            """, (line_id, name, credit))

            user = conn.execute("""
                SELECT user_id
                FROM users
                WHERE line_user_id = ?
            """, (line_id,)).fetchone()

            # 使用測試分數，不是真正 AI 推論
            credit_score = credit / 5 * 100

            now = datetime.now()

            if 11 <= now.hour < 13:
                wc, wr, wt = 0.3, 0.3, 0.4
            else:
                wc, wr, wt = 0.4, 0.4, 0.2

            final = (
                wc * credit_score
                + wr * route
                + wt * time
            )

            if user["user_id"] == order["requester_id"]:
                continue

            results.append({
                "user_id": user["user_id"],
                "name": name,
                "credit": credit_score,
                "route": route,
                "time": time,
                "final": round(final, 2)
            })

        # 3. 按照總分排序
        results.sort(
            key=lambda x: x["final"],
            reverse=True
        )

        batch_id = "test_" + uuid4().hex[:12]

        # 4. 將推薦結果寫入資料庫
        for rank, result in enumerate(results, start=1):
            conn.execute("""
                INSERT INTO matching_results (
                    order_id,
                    candidate_user_id,
                    credit_score,
                    route_score,
                    time_score,
                    final_score,
                    rank_position,
                    recommendation_batch_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order["order_id"],
                result["user_id"],
                result["credit"],
                result["route"],
                result["time"],
                result["final"],
                rank,
                batch_id
            ))

    # 5. 從資料庫重新讀取推薦結果
    saved = conn.execute("""
        SELECT
            m.rank_position,
            u.display_name,
            m.credit_score,
            m.route_score,
            m.time_score,
            m.final_score
        FROM matching_results m
        JOIN users u
            ON m.candidate_user_id = u.user_id
        WHERE m.recommendation_batch_id = ?
        ORDER BY m.rank_position
    """, (batch_id,)).fetchall()

    print("\n=== 推薦結果 ===")

    for row in saved:
        print(
            f"第 {row['rank_position']} 名："
            f"{row['display_name']} | "
            f"信用 {row['credit_score']:.0f} | "
            f"路線 {row['route_score']:.0f} | "
            f"時間 {row['time_score']:.0f} | "
            f"總分 {row['final_score']:.2f}"
        )

    print(f"\n成功儲存 {len(saved)} 筆 AI 推薦測試紀錄！")

finally:
    conn.close()
