"""Soochow EATs: interactively test creating an order and its items.

Run from the backend directory: python test_create_order.py
Uses the existing database.py and database tables; inserts a clearly labelled test user/order.
"""

from datetime import datetime, timedelta
from database import get_connection

TEST_LINE_ID = "test_soochow_eats_order_001"  # Not a real LINE user ID.


def choose(rows, title, format_row):
    if not rows:
        raise ValueError(f"沒有可用的{title}，請先確認匯入資料。")
    print(f"\n=== 選擇{title} ===")
    for i, row in enumerate(rows, 1):
        print(f"{i}. {format_row(row)}")
    while True:
        raw = input(f"輸入編號 (1-{len(rows)})，或輸入 q 離開：").strip()
        if raw.lower() == "q":
            raise KeyboardInterrupt
        if raw.isdigit() and 1 <= int(raw) <= len(rows):
            return rows[int(raw) - 1]
        print("編號無效，請重試。")


def positive_int(prompt, minimum=1):
    while True:
        raw = input(prompt).strip()
        if raw.isdigit() and int(raw) >= minimum:
            return int(raw)
        print(f"請輸入大於或等於 {minimum} 的整數。")


def main():
    conn = get_connection()
    try:
        campus = choose(
            [("shuangxi", "雙溪校區"), ("downtown", "城中校區")],
            "校區", lambda row: row[1]
        )[0]

        restaurants = conn.execute("""
            SELECT r.restaurant_id, r.restaurant_name, l.location_name
            FROM restaurants AS r
            JOIN locations AS l ON r.location_id = l.location_id
            WHERE l.campus = ? AND r.is_active = 1
            ORDER BY r.restaurant_name, r.restaurant_id
        """, (campus,)).fetchall()
        restaurant = choose(
            restaurants, "餐廳",
            lambda r: f"{r['restaurant_name']}（{r['location_name']}）"
        )

        menu = conn.execute("""
            SELECT item_id, item_name, price
            FROM menu_items
            WHERE restaurant_id = ? AND is_available = 1
            ORDER BY item_name, item_id
        """, (restaurant["restaurant_id"],)).fetchall()
        if not menu:
            print("\n這家店目前沒有已匯入的可售菜色。請改選另一家店。")
            return

        cart = {}  # item_id -> (name, quantity, unit_price)
        while True:
            item = choose(menu, "菜色", lambda m: f"{m['item_name']}：{m['price']} 元")
            qty = positive_int("購買數量：")
            item_id = item["item_id"]
            previous = cart.get(item_id)
            cart[item_id] = (
                item["item_name"],
                (previous[1] if previous else 0) + qty,
                item["price"],
            )
            if input("還要增加菜色嗎？(y/N)：").strip().lower() != "y":
                break

        # Restrict delivery locations to the same campus and campus buildings.
        locations = conn.execute("""
            SELECT location_id, location_name
            FROM locations
            WHERE campus = ? AND location_type = 'campus'
            ORDER BY location_name, location_id
        """, (campus,)).fetchall()
        if not locations:
            raise ValueError("這個校區沒有可選的送達地點，請先檢查 locations。")
        destination = choose(locations, "送達地點", lambda r: r["location_name"])

        reward = positive_int("代購獎勵金（元，可填 0）：", minimum=0)
        deadline = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        subtotal = sum(qty * price for _, qty, price in cart.values())
        print("\n=== 訂單確認 ===")
        print("餐廳：", restaurant["restaurant_name"])
        print("送達：", destination["location_name"])
        print("最晚送達時間（測試預設現在起 2 小時）：", deadline)
        for name, qty, price in cart.values():
            print(f" - {name} × {qty}（{price} 元/份）＝ {qty * price} 元")
        print(f"餐點合計 {subtotal} 元 + 獎勵金 {reward} 元 = {subtotal + reward} 元")
        if input("確認建立測試訂單？(輸入 yes 才會寫入)：").strip().lower() != "yes":
            print("已取消，沒有新增訂單。")
            return

        # All inserts form one transaction: an order never remains without its items.
        with conn:
            conn.execute("""
                INSERT OR IGNORE INTO users (line_user_id, display_name)
                VALUES (?, ?)
            """, (TEST_LINE_ID, "訂餐測試學生"))
            user = conn.execute(
                "SELECT user_id FROM users WHERE line_user_id = ?", (TEST_LINE_ID,)
            ).fetchone()
            cursor = conn.execute("""
                INSERT INTO orders
                    (requester_id, restaurant_id, delivery_location_id,
                     deadline, reward_amount, note)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                user["user_id"], restaurant["restaurant_id"],
                destination["location_id"], deadline, reward, "資料庫功能測試訂單"
            ))
            order_id = cursor.lastrowid
            for item_id, (_name, qty, price) in cart.items():
                conn.execute("""
                    INSERT INTO order_items (order_id, item_id, quantity, unit_price)
                    VALUES (?, ?, ?, ?)
                """, (order_id, item_id, qty, price))

        print(f"\n✅ 訂單 #{order_id} 建立成功！")
        result = conn.execute("""
            SELECT o.order_id, o.status, r.restaurant_name, l.location_name,
                   m.item_name, oi.quantity, oi.unit_price
            FROM orders AS o
            JOIN restaurants AS r ON o.restaurant_id = r.restaurant_id
            JOIN locations AS l ON o.delivery_location_id = l.location_id
            JOIN order_items AS oi ON o.order_id = oi.order_id
            JOIN menu_items AS m ON oi.item_id = m.item_id
            WHERE o.order_id = ?
            ORDER BY oi.order_item_id
        """, (order_id,)).fetchall()
        print("=== 從資料庫讀回的訂單 ===")
        for row in result:
            print(f"{row['item_name']} × {row['quantity']}，單價 {row['unit_price']} 元")
        print("訂單狀態：", result[0]["status"])

    except KeyboardInterrupt:
        print("\n操作已取消。")
    except (ValueError, Exception) as exc:
        print(f"\n❌ 操作未完成：{exc}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
