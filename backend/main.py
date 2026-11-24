
from contextlib import closing

from fastapi import FastAPI, HTTPException
from database import get_connection

app = FastAPI(title="Soochow EATs API")


# 1. 確認 API 是否正常運作
@app.get("/")
def home():
    return {
        "message": "Soochow EATs API 運作正常"
    }


# 2. 查詢所有校區
@app.get("/campuses")
def get_campuses():
    return [
        {"id": "shuangxi", "name": "雙溪校區"},
        {"id": "downtown", "name": "城中校區"}
    ]


# 3. 根據校區查詢餐廳
@app.get("/restaurants")
def get_restaurants(campus: str):
    if campus not in ("shuangxi", "downtown"):
        raise HTTPException(
            status_code=400,
            detail="無效的校區"
        )

    with closing(get_connection()) as conn:
        rows = conn.execute("""
            SELECT
                r.restaurant_id,
                r.restaurant_name,
                l.location_name
            FROM restaurants r
            JOIN locations l
              ON r.location_id = l.location_id
            WHERE l.campus = ?
              AND r.is_active = 1
            ORDER BY r.restaurant_name
        """, (campus,)).fetchall()

        return [dict(row) for row in rows]


# 4. 查詢指定餐廳的菜單
@app.get("/restaurants/{restaurant_id}/menu")
def get_menu(restaurant_id: int):
    with closing(get_connection()) as conn:
        restaurant = conn.execute("""
            SELECT restaurant_id
            FROM restaurants
            WHERE restaurant_id = ?
              AND is_active = 1
        """, (restaurant_id,)).fetchone()

        if restaurant is None:
            raise HTTPException(
                status_code=404,
                detail="找不到餐廳"
            )

        rows = conn.execute("""
            SELECT item_id, item_name, price
            FROM menu_items
            WHERE restaurant_id = ?
              AND is_available = 1
            ORDER BY item_name
        """, (restaurant_id,)).fetchall()

        return [dict(row) for row in rows]
