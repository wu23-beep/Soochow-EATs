"""資資吱吱 MVP 後端 API。

此版本以影片展示為目標，沿用既有 SQLite 資料表，不新增或重建資料表。
啟動方式（在專案根目錄執行）：
    python -m uvicorn main:app --app-dir backend --reload
"""
from contextlib import closing
from datetime import datetime
import sqlite3

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from database import get_connection

app = FastAPI(title="Soochow EATs API", version="1.0.0")
VALID_STATUSES = {"pending", "accepted", "delivered", "completed", "cancelled"}


# ------------------------------
# API 請求資料格式
# ------------------------------
class UserCreate(BaseModel):
    line_user_id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)


class UserUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)


class OrderItemInput(BaseModel):
    item_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=99)
    special_request: str | None = Field(default=None, max_length=300)


class OrderCreate(BaseModel):
    requester_id: int = Field(gt=0)
    restaurant_id: int = Field(gt=0)
    delivery_location_id: int = Field(gt=0)
    deadline: str = Field(min_length=16, max_length=30)
    reward_amount: int = Field(default=0, ge=0, le=10000)
    note: str | None = Field(default=None, max_length=500)
    items: list[OrderItemInput] = Field(min_length=1, max_length=30)


class AcceptOrderInput(BaseModel):
    runner_id: int = Field(gt=0)


class ReviewInput(BaseModel):
    reviewer_id: int = Field(gt=0)
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=500)


# ------------------------------
# 共用資料庫及信用計算函式
# ------------------------------
def get_row_dict(row):
    """將 SQLite Row 轉成可回傳的字典。"""
    return dict(row) if row is not None else None


def calculate_user_credits(conn: sqlite3.Connection, user_id: int) -> dict:
    """依交接規格重算使用者的發單者及接單者信用。

    無交易或無評價樣本的指標暫以 1.0 作為冷啟動值，讓新使用者維持資料庫預設 5 分。
    指標皆限制在 0 到 1，最後依原公式換算成 0 到 5 分。
    """
    # 接單者：統計此人所有接單紀錄。
    runner_rows = conn.execute(
        """SELECT om.status, o.deadline, om.delivered_at
           FROM order_matches om
           JOIN orders o ON o.order_id = om.order_id
           WHERE om.runner_id = ?""",
        (user_id,),
    ).fetchall()

    runner_total = len(runner_rows)
    runner_completed = sum(row["status"] == "completed" for row in runner_rows)
    runner_not_cancelled = sum(row["status"] != "cancelled" for row in runner_rows)
    runner_delivered_rows = [
        row for row in runner_rows
        if row["delivered_at"] is not None
    ]

    rc = runner_completed / runner_total if runner_total else 1.0
    rn_runner = runner_not_cancelled / runner_total if runner_total else 1.0

    # 準時率以已有送達時間的訂單計算，送達時間不晚於訂單期限視為準時。
    on_time_count = 0
    for row in runner_delivered_rows:
        try:
            delivered_at = datetime.fromisoformat(row["delivered_at"])
            deadline = datetime.fromisoformat(row["deadline"])
            if delivered_at <= deadline:
                on_time_count += 1
        except (TypeError, ValueError):
            # 日期資料格式異常時不計為準時，避免錯誤提高信用。
            continue
    rt = (
        on_time_count / len(runner_delivered_rows)
        if runner_delivered_rows else 1.0
    )

    runner_ratings = conn.execute(
        """SELECT AVG(rating) AS avg_rating
           FROM reviews
           WHERE reviewee_id = ?
             AND reviewer_id IN (
                 SELECT requester_id FROM orders
                 WHERE order_id IN (
                     SELECT order_id FROM order_matches WHERE runner_id = ?
                 )
             )""",
        (user_id, user_id),
    ).fetchone()["avg_rating"]
    rv = (runner_ratings / 5.0) if runner_ratings is not None else 1.0

    # 發單者：統計此人建立的所有訂單。
    requester_rows = conn.execute(
        "SELECT order_id, status FROM orders WHERE requester_id = ?",
        (user_id,),
    ).fetchall()
    requester_total = len(requester_rows)
    requester_completed = sum(row["status"] == "completed" for row in requester_rows)
    requester_not_cancelled = sum(row["status"] != "cancelled" for row in requester_rows)

    rf = requester_completed / requester_total if requester_total else 1.0
    rn_requester = requester_not_cancelled / requester_total if requester_total else 1.0

    # 資訊完整度：餐廳、送達地點、期限及至少一筆餐點明細皆存在即為完整。
    complete_count = 0
    for row in requester_rows:
        item_count = conn.execute(
            "SELECT COUNT(*) FROM order_items WHERE order_id = ?",
            (row["order_id"],),
        ).fetchone()[0]
        required_count = conn.execute(
            """SELECT COUNT(*) FROM orders
               WHERE order_id = ? AND restaurant_id IS NOT NULL
                 AND delivery_location_id IS NOT NULL AND deadline IS NOT NULL""",
            (row["order_id"],),
        ).fetchone()[0]
        if required_count == 1 and item_count > 0:
            complete_count += 1
    ri = complete_count / requester_total if requester_total else 1.0

    requester_rating = conn.execute(
        """SELECT AVG(rating) AS avg_rating
           FROM reviews
           WHERE reviewee_id = ?
             AND reviewer_id IN (
                 SELECT runner_id FROM order_matches
                 WHERE order_id IN (SELECT order_id FROM orders WHERE requester_id = ?)
             )""",
        (user_id, user_id),
    ).fetchone()["avg_rating"]
    rv_requester = (requester_rating / 5.0) if requester_rating is not None else 1.0

    # 依規格書的雙向信用公式計算，並限制在 0 至 5 分。
    runner_credit = 5 * (0.35 * rc + 0.25 * rt + 0.20 * rn_runner + 0.20 * rv)
    requester_credit = 5 * (
        0.30 * rf + 0.25 * rn_requester + 0.20 * ri + 0.25 * rv_requester
    )
    runner_credit = max(0.0, min(5.0, runner_credit))
    requester_credit = max(0.0, min(5.0, requester_credit))

    conn.execute(
        """UPDATE users
           SET requester_credit = ?, runner_credit = ?
           WHERE user_id = ?""",
        (round(requester_credit, 2), round(runner_credit, 2), user_id),
    )
    return {
        "requester_credit": round(requester_credit, 2),
        "runner_credit": round(runner_credit, 2),
    }


def fetch_order_detail(conn: sqlite3.Connection, order_id: int):
    """查詢訂單主檔、餐點明細及接單者。"""
    order = conn.execute(
        """SELECT o.order_id, o.requester_id, u.display_name AS requester_name,
                  o.restaurant_id, r.restaurant_name,
                  o.delivery_location_id, l.location_name AS delivery_location,
                  o.deadline, o.reward_amount, o.note, o.status, o.created_at,
                  om.runner_id, ru.display_name AS runner_name
           FROM orders o
           JOIN users u ON u.user_id = o.requester_id
           JOIN restaurants r ON r.restaurant_id = o.restaurant_id
           JOIN locations l ON l.location_id = o.delivery_location_id
           LEFT JOIN order_matches om ON om.order_id = o.order_id
               AND om.status IN ('accepted', 'delivered', 'completed')
           LEFT JOIN users ru ON ru.user_id = om.runner_id
           WHERE o.order_id = ?""",
        (order_id,),
    ).fetchone()
    if order is None:
        return None

    items = conn.execute(
        """SELECT oi.order_item_id, oi.item_id, mi.item_name,
                  oi.quantity, oi.unit_price, oi.special_request
           FROM order_items oi
           JOIN menu_items mi ON mi.item_id = oi.item_id
           WHERE oi.order_id = ? ORDER BY oi.order_item_id""",
        (order_id,),
    ).fetchall()

    result = dict(order)
    result["items"] = [dict(item) for item in items]
    result["subtotal"] = sum(item["quantity"] * item["unit_price"] for item in items)
    result["total_amount"] = result["subtotal"] + result["reward_amount"]
    return result


# ------------------------------
# 基礎與既有查詢 API
# ------------------------------
@app.get("/")
def home():
    return {"message": "Soochow EATs API 運作正常"}


@app.get("/campuses")
def get_campuses():
    return [
        {"id": "shuangxi", "name": "雙溪校區"},
        {"id": "downtown", "name": "城中校區"},
    ]


@app.get("/restaurants")
def get_restaurants(campus: str):
    if campus not in ("shuangxi", "downtown"):
        raise HTTPException(status_code=400, detail="無效的校區")

    with closing(get_connection()) as conn:
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(locations)").fetchall()
        }
        if "campus" not in columns:
            raise HTTPException(
                status_code=409,
                detail="locations 尚未建立 campus 欄位，請先執行校區資料匯入腳本",
            )
        rows = conn.execute(
            """SELECT r.restaurant_id, r.restaurant_name, l.location_name
               FROM restaurants r JOIN locations l ON l.location_id = r.location_id
               WHERE l.campus = ? AND r.is_active = 1
               ORDER BY r.restaurant_name""",
            (campus,),
        ).fetchall()
        return [dict(row) for row in rows]


@app.get("/restaurants/{restaurant_id}/menu")
def get_menu(restaurant_id: int):
    with closing(get_connection()) as conn:
        restaurant = conn.execute(
            "SELECT restaurant_id FROM restaurants WHERE restaurant_id = ? AND is_active = 1",
            (restaurant_id,),
        ).fetchone()
        if restaurant is None:
            raise HTTPException(status_code=404, detail="找不到餐廳")
        rows = conn.execute(
            """SELECT item_id, item_name, price, description
               FROM menu_items WHERE restaurant_id = ? AND is_available = 1
               ORDER BY item_name""",
            (restaurant_id,),
        ).fetchall()
        return [dict(row) for row in rows]


# ------------------------------
# 使用者 API
# ------------------------------
@app.post("/users", status_code=201)
def create_user(payload: UserCreate):
    with closing(get_connection()) as conn:
        try:
            with conn:
                cursor = conn.execute(
                    "INSERT INTO users (line_user_id, display_name) VALUES (?, ?)",
                    (payload.line_user_id, payload.display_name),
                )
                row = conn.execute(
                    "SELECT * FROM users WHERE user_id = ?", (cursor.lastrowid,)
                ).fetchone()
                return dict(row)
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="此 LINE 使用者已經註冊")


@app.get("/users/{user_id}")
def get_user(user_id: int):
    with closing(get_connection()) as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="找不到使用者")
        return dict(row)


@app.patch("/users/{user_id}")
def update_user(user_id: int, payload: UserUpdate):
    with closing(get_connection()) as conn, conn:
        cursor = conn.execute(
            "UPDATE users SET display_name = ? WHERE user_id = ?",
            (payload.display_name, user_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="找不到使用者")
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row)


# ------------------------------
# 訂單建立、查詢及流程 API
# ------------------------------
@app.post("/orders", status_code=201)
def create_order(payload: OrderCreate):
    try:
        datetime.fromisoformat(payload.deadline)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="deadline 必須是有效日期時間，例如 2026-11-25 12:30:00",
        )

    data = payload.model_dump()
    with closing(get_connection()) as conn:
        try:
            with conn:
                requester = conn.execute(
                    "SELECT user_id FROM users WHERE user_id = ? AND account_status = 'active'",
                    (data["requester_id"],),
                ).fetchone()
                restaurant = conn.execute(
                    "SELECT restaurant_id FROM restaurants WHERE restaurant_id = ? AND is_active = 1",
                    (data["restaurant_id"],),
                ).fetchone()
                location = conn.execute(
                    "SELECT location_id FROM locations WHERE location_id = ? AND location_type = 'campus'",
                    (data["delivery_location_id"],),
                ).fetchone()
                if requester is None:
                    raise HTTPException(status_code=404, detail="找不到有效的發單者")
                if restaurant is None:
                    raise HTTPException(status_code=404, detail="找不到有效的餐廳")
                if location is None:
                    raise HTTPException(status_code=400, detail="送達地點不存在或不是校園地點")

                # 價格一律由資料庫菜單讀取，避免前端自行傳入價格。
                verified_items = []
                for item in data["items"]:
                    menu_item = conn.execute(
                        """SELECT item_id, price FROM menu_items
                           WHERE item_id = ? AND restaurant_id = ? AND is_available = 1""",
                        (item["item_id"], data["restaurant_id"]),
                    ).fetchone()
                    if menu_item is None:
                        raise HTTPException(
                            status_code=400,
                            detail=f"餐點 {item['item_id']} 不存在、未供應或不屬於所選餐廳",
                        )
                    verified_items.append((item, menu_item["price"]))

                cursor = conn.execute(
                    """INSERT INTO orders
                       (requester_id, restaurant_id, delivery_location_id,
                        deadline, reward_amount, note)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (data["requester_id"], data["restaurant_id"],
                     data["delivery_location_id"], data["deadline"],
                     data["reward_amount"], data.get("note")),
                )
                order_id = cursor.lastrowid
                for item, unit_price in verified_items:
                    conn.execute(
                        """INSERT INTO order_items
                           (order_id, item_id, quantity, unit_price, special_request)
                           VALUES (?, ?, ?, ?, ?)""",
                        (order_id, item["item_id"], item["quantity"],
                         unit_price, item.get("special_request")),
                    )
        except HTTPException:
            raise
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=400, detail=f"訂單資料不符合資料庫限制：{exc}")

    return {"order_id": order_id, "status": "pending", "message": "訂單建立成功"}


@app.get("/orders")
def list_orders(
    requester_id: int | None = Query(default=None, gt=0),
    status: str | None = None,
):
    if status is not None and status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="無效的訂單狀態")

    sql = """SELECT o.order_id, o.requester_id, u.display_name AS requester_name,
                    r.restaurant_name, l.location_name AS delivery_location,
                    o.deadline, o.reward_amount, o.status, o.created_at
             FROM orders o
             JOIN users u ON u.user_id = o.requester_id
             JOIN restaurants r ON r.restaurant_id = o.restaurant_id
             JOIN locations l ON l.location_id = o.delivery_location_id
             WHERE 1 = 1"""
    params = []
    if requester_id is not None:
        sql += " AND o.requester_id = ?"
        params.append(requester_id)
    if status is not None:
        sql += " AND o.status = ?"
        params.append(status)
    sql += " ORDER BY o.order_id DESC"

    with closing(get_connection()) as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


@app.get("/orders/{order_id}")
def get_order(order_id: int):
    with closing(get_connection()) as conn:
        order = fetch_order_detail(conn, order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="找不到訂單")
        return order


@app.post("/orders/{order_id}/accept")
def accept_order(order_id: int, payload: AcceptOrderInput):
    """接單時以 BEGIN IMMEDIATE 鎖定寫入交易，避免同筆訂單被重複承接。"""
    with closing(get_connection()) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            order = conn.execute(
                "SELECT requester_id, status FROM orders WHERE order_id = ?",
                (order_id,),
            ).fetchone()
            if order is None:
                raise HTTPException(status_code=404, detail="找不到訂單")
            if order["status"] != "pending":
                raise HTTPException(status_code=409, detail="此訂單已被接單或已無法承接")
            if order["requester_id"] == payload.runner_id:
                raise HTTPException(status_code=400, detail="發單者不能接自己的訂單")

            runner = conn.execute(
                "SELECT user_id FROM users WHERE user_id = ? AND account_status = 'active'",
                (payload.runner_id,),
            ).fetchone()
            if runner is None:
                raise HTTPException(status_code=404, detail="找不到有效的接單者")

            cursor = conn.execute(
                "UPDATE orders SET status = 'accepted' WHERE order_id = ? AND status = 'pending'",
                (order_id,),
            )
            if cursor.rowcount != 1:
                raise HTTPException(status_code=409, detail="此訂單已被其他人接走")

            conn.execute(
                "INSERT INTO order_matches (order_id, runner_id, status) VALUES (?, ?, 'accepted')",
                (order_id, payload.runner_id),
            )
            conn.commit()
        except HTTPException:
            conn.rollback()
            raise
        except sqlite3.IntegrityError:
            conn.rollback()
            raise HTTPException(status_code=409, detail="此訂單已有有效接單紀錄")
        except sqlite3.OperationalError:
            conn.rollback()
            raise HTTPException(status_code=409, detail="資料庫正在處理其他接單，請稍後重試")

    return {"order_id": order_id, "runner_id": payload.runner_id, "status": "accepted", "message": "接單成功"}


@app.post("/orders/{order_id}/deliver")
def mark_order_delivered(order_id: int):
    """接單者完成購餐後，將訂單更新為已送達。"""
    with closing(get_connection()) as conn:
        try:
            with conn:
                cursor = conn.execute(
                    "UPDATE orders SET status = 'delivered' WHERE order_id = ? AND status = 'accepted'",
                    (order_id,),
                )
                if cursor.rowcount != 1:
                    exists = conn.execute("SELECT order_id FROM orders WHERE order_id = ?", (order_id,)).fetchone()
                    if exists is None:
                        raise HTTPException(status_code=404, detail="找不到訂單")
                    raise HTTPException(status_code=409, detail="只有已接單的訂單可以更新為已送達")
                conn.execute(
                    """UPDATE order_matches SET status = 'delivered', delivered_at = CURRENT_TIMESTAMP
                       WHERE order_id = ? AND status = 'accepted'""",
                    (order_id,),
                )
        except HTTPException:
            raise
    return {"order_id": order_id, "status": "delivered", "message": "訂單已更新為送達"}


@app.post("/orders/{order_id}/complete")
def complete_order(order_id: int):
    """發單者確認收到餐點後完成訂單，並重算雙方信用。"""
    with closing(get_connection()) as conn:
        try:
            with conn:
                order = conn.execute(
                    "SELECT requester_id, status FROM orders WHERE order_id = ?",
                    (order_id,),
                ).fetchone()
                if order is None:
                    raise HTTPException(status_code=404, detail="找不到訂單")
                if order["status"] != "delivered":
                    raise HTTPException(status_code=409, detail="只有已送達的訂單可以完成")
                match = conn.execute(
                    "SELECT runner_id FROM order_matches WHERE order_id = ? AND status = 'delivered'",
                    (order_id,),
                ).fetchone()
                if match is None:
                    raise HTTPException(status_code=409, detail="找不到有效的送達紀錄")

                conn.execute("UPDATE orders SET status = 'completed' WHERE order_id = ?", (order_id,))
                conn.execute(
                    "UPDATE order_matches SET status = 'completed' WHERE order_id = ? AND status = 'delivered'",
                    (order_id,),
                )
                requester_credit = calculate_user_credits(conn, order["requester_id"])
                runner_credit = calculate_user_credits(conn, match["runner_id"])
        except HTTPException:
            raise

    return {
        "order_id": order_id,
        "status": "completed",
        "credits": {
            "requester": requester_credit,
            "runner": runner_credit,
        },
        "message": "訂單完成",
    }


@app.post("/orders/{order_id}/cancel")
def cancel_order(order_id: int):
    """MVP 先只允許待接單訂單取消，避免處理已接單後的複雜責任歸屬。"""
    with closing(get_connection()) as conn:
        with conn:
            cursor = conn.execute(
                "UPDATE orders SET status = 'cancelled' WHERE order_id = ? AND status = 'pending'",
                (order_id,),
            )
            if cursor.rowcount != 1:
                exists = conn.execute("SELECT order_id FROM orders WHERE order_id = ?", (order_id,)).fetchone()
                if exists is None:
                    raise HTTPException(status_code=404, detail="找不到訂單")
                raise HTTPException(status_code=409, detail="目前只有待接單訂單可以取消")
            row = conn.execute("SELECT requester_id FROM orders WHERE order_id = ?", (order_id,)).fetchone()
            requester_credit = calculate_user_credits(conn, row["requester_id"])
    return {"order_id": order_id, "status": "cancelled", "requester_credit": requester_credit["requester_credit"]}


# ------------------------------
# 雙向評價及信用查詢 API
# ------------------------------
@app.post("/orders/{order_id}/reviews", status_code=201)
def create_review(order_id: int, payload: ReviewInput):
    with closing(get_connection()) as conn:
        try:
            with conn:
                order = conn.execute(
                    "SELECT requester_id, status FROM orders WHERE order_id = ?",
                    (order_id,),
                ).fetchone()
                if order is None:
                    raise HTTPException(status_code=404, detail="找不到訂單")
                if order["status"] != "completed":
                    raise HTTPException(status_code=409, detail="訂單完成後才能互評")

                match = conn.execute(
                    "SELECT runner_id FROM order_matches WHERE order_id = ? AND status = 'completed'",
                    (order_id,),
                ).fetchone()
                if match is None:
                    raise HTTPException(status_code=409, detail="找不到完成的接單紀錄")

                if payload.reviewer_id == order["requester_id"]:
                    reviewee_id = match["runner_id"]
                elif payload.reviewer_id == match["runner_id"]:
                    reviewee_id = order["requester_id"]
                else:
                    raise HTTPException(status_code=403, detail="只有訂單雙方可以評價")

                conn.execute(
                    """INSERT INTO reviews
                       (order_id, reviewer_id, reviewee_id, rating, comment)
                       VALUES (?, ?, ?, ?, ?)""",
                    (order_id, payload.reviewer_id, reviewee_id,
                     payload.rating, payload.comment),
                )
                updated_credit = calculate_user_credits(conn, reviewee_id)
        except HTTPException:
            raise
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="此使用者已經評價過這筆訂單")

    return {
        "order_id": order_id,
        "reviewer_id": payload.reviewer_id,
        "reviewee_id": reviewee_id,
        "rating": payload.rating,
        "updated_credit": updated_credit,
        "message": "評價成功",
    }


@app.get("/users/{user_id}/credits")
def get_user_credits(user_id: int):
    with closing(get_connection()) as conn:
        user = conn.execute(
            "SELECT user_id, requester_credit, runner_credit FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if user is None:
            raise HTTPException(status_code=404, detail="找不到使用者")
        return dict(user)
