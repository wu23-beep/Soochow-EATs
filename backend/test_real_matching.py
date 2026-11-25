"""Soochow EATs：以 SQLite 地點、空堂、步行時間做規則式媒合測試。
用法：放在 backend/，先建立一筆 pending 訂單，再執行 python test_real_matching.py。
測試候選人的空堂和位置為模擬資料；真實接單意願應由 LINE Bot 更新。
"""
from contextlib import closing
from datetime import datetime, timedelta
from uuid import uuid4
from database import get_connection

WAIT_MINUTES = 5.0  # 測試假設，之後可依餐廳調整
MIN_CREDIT = 2.0


def walk_minutes(conn, start_id, end_id):
    if start_id == end_id:
        return 0.0
    row = conn.execute("""
        SELECT walking_minutes FROM walking_times
        WHERE from_location_id = ? AND to_location_id = ?
    """, (start_id, end_id)).fetchone()
    return float(row["walking_minutes"]) if row else None


def main():
    now = datetime.now()
    with closing(get_connection()) as conn:
        order = conn.execute("""
            SELECT o.order_id, o.requester_id, o.deadline,
                   o.delivery_location_id, r.restaurant_name,
                   r.location_id AS restaurant_location_id,
                   l.campus AS campus
            FROM orders o
            JOIN restaurants r ON r.restaurant_id = o.restaurant_id
            JOIN locations l ON l.location_id = r.location_id
            WHERE o.status = 'pending'
            ORDER BY o.order_id DESC LIMIT 1
        """).fetchone()
        if not order:
            print("沒有待接訂單。請先執行 python test_create_order.py。")
            return

        try:
            deadline = datetime.fromisoformat(order["deadline"])
        except (ValueError, TypeError):
            print("訂單 deadline 格式不正確，請使用 YYYY-MM-DD HH:MM:SS")
            return
        if deadline <= now:
            print("最新待接訂單已過送達期限，請建立新的測試訂單。")
            return

        # 模擬三個自願接單的候選人：從同校區且有步行資料的地點選出
        locations = conn.execute("""
            SELECT location_id, location_name FROM locations
            WHERE campus = ? AND location_type = 'campus'
            ORDER BY location_id
        """, (order["campus"],)).fetchall()
        possible = [l for l in locations
                    if walk_minutes(conn, l["location_id"], order["restaurant_location_id"]) is not None]
        if not possible:
            print("找不到該校區能走到餐廳的地點，請檢查 walking_times。")
            return
        delivery_walk = walk_minutes(conn, order["restaurant_location_id"], order["delivery_location_id"])
        if delivery_walk is None:
            print("缺少餐廳到送達地點的步行時間；請補 walking_times。")
            return

        print(f"訂單 #{order['order_id']}｜{order['restaurant_name']}｜{order['campus']}")
        print("以下為模擬候選人的位置與空堂，時間與步行資料會由 SQLite 查出。")
        candidate_specs = [("demo_runner_a", "測試接單者A", 4.5),
                           ("demo_runner_b", "測試接單者B", 4.0),
                           ("demo_runner_c", "測試接單者C", 3.5)]
        with conn:
            for i, (line_id, name, credit) in enumerate(candidate_specs):
                conn.execute("""
                    INSERT OR IGNORE INTO users
                    (line_user_id, display_name, runner_credit)
                    VALUES (?, ?, ?)
                """, (line_id, name, credit))
                user = conn.execute("SELECT user_id FROM users WHERE line_user_id=?", (line_id,)).fetchone()
                if user["user_id"] == order["requester_id"]:
                    continue
                loc = possible[i % len(possible)]
                conn.execute("""
                    INSERT INTO user_availability
                    (user_id, current_location_id, available_from, available_until, willing_to_accept)
                    VALUES (?, ?, ?, ?, 1)
                """, (user["user_id"], loc["location_id"],
                      (now - timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S'),
                      (now + timedelta(minutes=90 - i * 15)).strftime('%Y-%m-%d %H:%M:%S')))

        availabilities = conn.execute("""
            SELECT a.*, u.display_name, u.runner_credit, l.location_name
            FROM user_availability a
            JOIN users u ON u.user_id = a.user_id
            JOIN locations l ON l.location_id = a.current_location_id
            WHERE a.willing_to_accept = 1
              AND u.account_status = 'active'
              AND u.user_id != ?
              AND u.runner_credit >= ?
              AND l.campus = ?
              AND a.available_from <= ? AND a.available_until > ?
            ORDER BY a.availability_id DESC
        """, (order["requester_id"], MIN_CREDIT, order["campus"],
              now.strftime('%Y-%m-%d %H:%M:%S'), now.strftime('%Y-%m-%d %H:%M:%S'))).fetchall()

        # 同一使用者可能有多筆空堂紀錄；這裡採用最新一筆有效資料
        latest = {}
        for a in availabilities:
            latest.setdefault(a["user_id"], a)
        results = []
        peak = (now.hour == 11 and now.minute >= 50) or (now.hour == 12 and now.minute <= 30)
        wc, wr, wt = (0.3, 0.3, 0.4) if peak else (0.4, 0.4, 0.2)
        for a in latest.values():
            leg1 = walk_minutes(conn, a["current_location_id"], order["restaurant_location_id"])
            if leg1 is None:
                continue
            total = leg1 + WAIT_MINUTES + delivery_walk
            end = min(datetime.fromisoformat(a["available_until"]), deadline)
            available = (end - now).total_seconds() / 60.0
            if available <= 0 or total > available:
                continue
            credit_score = a["runner_credit"] / 5 * 100
            # 簡單路線評分：行走越短越高，非實測 AI 模型
            route_score = max(0.0, 100.0 - (leg1 + delivery_walk) * 5.0)
            time_score = max(0.0, min(100.0, (available - total) / available * 100))
            final_score = wc * credit_score + wr * route_score + wt * time_score
            results.append((a["user_id"], a["display_name"], a["location_name"],
                            credit_score, route_score, time_score, final_score, total))
        results.sort(key=lambda x: x[6], reverse=True)
        if not results:
            print("沒有符合時間／位置／信用門檻的候選者。")
            return

        batch_id = "realtest_" + uuid4().hex[:12]
        with conn:
            for rank, result in enumerate(results, 1):
                uid, name, loc, credit, route, time_score, final, total = result
                conn.execute("""
                    INSERT INTO matching_results
                    (order_id, candidate_user_id, credit_score, route_score,
                     time_score, final_score, rank_position, recommendation_batch_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (order["order_id"], uid, credit, route,
                      time_score, final, rank, batch_id))
        print("\n推薦排名（規則式媒合測試）")
        for rank, result in enumerate(results, 1):
            print(f"第 {rank} 名｜{result[1]}｜位置 {result[2]}｜預估 {result[7]:.1f} 分鐘｜總分 {result[6]:.1f}")
        print(f"已儲存 {len(results)} 筆結果，批次：{batch_id}")


if __name__ == "__main__":
    main()
