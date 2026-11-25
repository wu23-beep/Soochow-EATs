
from database import get_connection

conn = get_connection()

try:
    # 1. 查詢等待接單的訂單
    orders = conn.execute("""
        SELECT o.order_id, o.requester_id,
               u.display_name, r.restaurant_name
        FROM orders o
        JOIN users u ON o.requester_id = u.user_id
        JOIN restaurants r ON o.restaurant_id = r.restaurant_id
        WHERE o.status = 'pending'
        ORDER BY o.order_id
    """).fetchall()

    if not orders:
        print("目前沒有待接訂單，請先建立測試訂單。")
        raise SystemExit

    print("=== 待接訂單 ===")
    for order in orders:
        print(
            f"訂單 #{order['order_id']} | "
            f"{order['display_name']} | "
            f"{order['restaurant_name']}"
        )

    order_id = int(input("\n請輸入要測試的訂單編號："))

    order = next(
        (o for o in orders if o["order_id"] == order_id),
        None
    )

    if order is None:
        print("訂單不存在或已經被接單。")
        raise SystemExit

    # 2. 建立測試接單者
    with conn:
        conn.execute("""
            INSERT OR IGNORE INTO users
            (line_user_id, display_name)
            VALUES (?, ?)
        """, ("test_runner_001", "測試接單者"))

    runner = conn.execute("""
        SELECT user_id
        FROM users
        WHERE line_user_id = ?
    """, ("test_runner_001",)).fetchone()

    runner_id = runner["user_id"]
    requester_id = order["requester_id"]

    if runner_id == requester_id:
        print("發單者不能接自己的訂單。")
        raise SystemExit

    confirm = input(
        "\n要模擬接單、完成及雙向評價嗎？(yes/no)："
    )

    if confirm.lower() != "yes":
        print("已取消測試。")
        raise SystemExit

    # 3. 執行完整交易
    with conn:
        cursor = conn.execute("""
            UPDATE orders
            SET status = 'accepted'
            WHERE order_id = ? AND status = 'pending'
        """, (order_id,))

        if cursor.rowcount != 1:
            raise ValueError("訂單已無法接單")

        # 建立接單紀錄
        cursor = conn.execute("""
            INSERT INTO order_matches
            (order_id, runner_id, status)
            VALUES (?, ?, 'accepted')
        """, (order_id, runner_id))

        match_id = cursor.lastrowid

        print("接單資料已建立")

        # 4. 模擬餐點送達
        conn.execute("""
            UPDATE order_matches
            SET status = 'delivered',
                delivered_at = CURRENT_TIMESTAMP
            WHERE match_id = ?
        """, (match_id,))

        conn.execute("""
            UPDATE orders
            SET status = 'delivered'
            WHERE order_id = ?
        """, (order_id,))

        print("餐點已送達")

        # 5. 完成訂單
        conn.execute("""
            UPDATE order_matches
            SET status = 'completed'
            WHERE match_id = ?
        """, (match_id,))

        conn.execute("""
            UPDATE orders
            SET status = 'completed'
            WHERE order_id = ?
        """, (order_id,))

        print("訂單已完成")

        # 6. 發單者評價接單者
        conn.execute("""
            INSERT INTO reviews
            (order_id, reviewer_id, reviewee_id,
             rating, comment)
            VALUES (?, ?, ?, ?, ?)
        """, (
            order_id, requester_id, runner_id,
            5, "送餐準時，服務很好"
        ))

        # 7. 接單者評價發單者
        conn.execute("""
            INSERT INTO reviews
            (order_id, reviewer_id, reviewee_id,
             rating, comment)
            VALUES (?, ?, ?, ?, ?)
        """, (
            order_id, runner_id, requester_id,
            5, "交易順利，溝通良好"
        ))

    # 8. 查詢最終結果
    result = conn.execute("""
        SELECT status
        FROM orders
        WHERE order_id = ?
    """, (order_id,)).fetchone()

    reviews = conn.execute("""
        SELECT COUNT(*) AS total
        FROM reviews
        WHERE order_id = ?
    """, (order_id,)).fetchone()

    print("\n=== 測試完成 ===")
    print("訂單編號：", order_id)
    print("訂單狀態：", result["status"])
    print("雙向評價數量：", reviews["total"])

except Exception as e:
    print("測試失敗：", e)
    raise

finally:
    conn.close()
