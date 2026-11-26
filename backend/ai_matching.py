"""Soochow EATs｜AI 智慧媒合、動態獎勵金與 Gemini 生成式 AI 引擎。"""
from __future__ import annotations

from datetime import datetime
import json
import os
import sqlite3
from uuid import uuid4

from google import genai
from google.genai import types

MIN_RUNNER_CREDIT = 2.0
DEFAULT_WAIT_MINUTES = 5.0
CORE_BUILDINGS = {"A棟", "B棟", "C棟", "H棟"}
REMOTE_BUILDINGS = {"R棟"}
GEMINI_MODELS = ["gemini-3.8-flash", "gemini-3.5-flash-lite"]


def get_walk_minutes(conn: sqlite3.Connection, from_loc_id: int, to_loc_id: int) -> float | None:
    """查詢兩地點間的預估步行分鐘數（walking_times 已含樓層補償）。"""
    if from_loc_id == to_loc_id:
        return 0.0
    row = conn.execute(
        """SELECT walking_minutes FROM walking_times
           WHERE from_location_id = ? AND to_location_id = ?""",
        (from_loc_id, to_loc_id),
    ).fetchone()
    return float(row["walking_minutes"]) if row is not None else None


def is_peak_or_urgent(now: datetime, deadline: datetime) -> tuple[bool, str]:
    """判斷是否啟動高壓/尖峰動態權重模式（11:50~12:30 或距離截止時間 <= 35 分鐘）。"""
    in_lunch_peak = (now.hour == 11 and now.minute >= 50) or (now.hour == 12 and now.minute <= 30)
    minutes_left = (deadline - now).total_seconds() / 60.0
    is_urgent = minutes_left <= 35.0

    if in_lunch_peak:
        return True, "午餐尖峰模式 (11:50~12:30)"
    if is_urgent:
        return True, "緊迫訂單滾動切換模式 (距截止 <= 35 分鐘)"
    return False, "一般常態模式"


def calculate_route_score(building: str | None, total_walk_minutes: float) -> float:
    """依簡報第 11 頁規則計算路線順路得分 (0~100)。"""
    if building in REMOTE_BUILDINGS:
        return 40.0
    if building in CORE_BUILDINGS:
        return 95.0
    score = 90.0 - max(0.0, total_walk_minutes - 3.0) * 3.0
    return round(max(60.0, min(90.0, score)), 2)


def run_ai_matching(
    conn: sqlite3.Connection,
    order_id: int,
    now: datetime | None = None,
    wait_minutes: float = DEFAULT_WAIT_MINUTES,
    save_to_db: bool = True,
) -> dict:
    """為指定訂單執行三階段 AI 智慧媒合，回傳排序後的候選接單者列表。"""
    now = now or datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    order = conn.execute(
        """SELECT o.order_id, o.requester_id, o.restaurant_id,
                  o.delivery_location_id, o.deadline, o.status,
                  r.restaurant_name, r.location_id AS restaurant_loc_id,
                  dl.location_name AS delivery_location_name,
                  dl.building AS delivery_building,
                  dl.campus AS campus
           FROM orders o
           JOIN restaurants r ON r.restaurant_id = o.restaurant_id
           JOIN locations dl ON dl.location_id = o.delivery_location_id
           WHERE o.order_id = ?""",
        (order_id,),
    ).fetchone()

    if order is None:
        raise ValueError("找不到指定訂單")
    if order["status"] != "pending":
        raise ValueError(f"訂單目前狀態為 {order['status']}，僅待接單 (pending) 訂單可執行媒合")

    deadline = datetime.fromisoformat(order["deadline"])
    if deadline <= now:
        raise ValueError("訂單已超過最晚送達期限")

    walk_rest_to_dest = get_walk_minutes(conn, order["restaurant_loc_id"], order["delivery_location_id"])
    if walk_rest_to_dest is None:
        raise ValueError("資料庫缺少餐廳至送達地點的步行時間資料")

    # 第一階段：硬性條件篩選
    avail_rows = conn.execute(
        """SELECT a.availability_id, a.user_id, a.current_location_id,
                  a.available_from, a.available_until,
                  u.display_name, u.runner_credit,
                  cl.location_name AS current_location_name,
                  cl.building AS current_building
           FROM user_availability a
           JOIN users u ON u.user_id = a.user_id
           JOIN locations cl ON cl.location_id = a.current_location_id
           WHERE a.willing_to_accept = 1
             AND u.account_status = 'active'
             AND u.user_id != ?
             AND u.runner_credit >= ?
             AND cl.campus = ?
             AND a.available_from <= ?
             AND a.available_until > ?
           ORDER BY a.availability_id DESC""",
        (order["requester_id"], MIN_RUNNER_CREDIT, order["campus"], now_str, now_str),
    ).fetchall()

    latest_avail = {}
    for row in avail_rows:
        latest_avail.setdefault(row["user_id"], row)

    high_pressure, mode_label = is_peak_or_urgent(now, deadline)
    wc, wr, wt = (0.3, 0.3, 0.4) if high_pressure else (0.4, 0.4, 0.2)

    candidates = []
    for cand in latest_avail.values():
        walk_curr_to_rest = get_walk_minutes(conn, cand["current_location_id"], order["restaurant_loc_id"])
        if walk_curr_to_rest is None:
            continue

        # 第二階段：任務總耗時估算 T_total
        t_total = round(walk_curr_to_rest + wait_minutes + walk_rest_to_dest, 2)

        avail_until = datetime.fromisoformat(cand["available_until"])
        effective_end = min(avail_until, deadline)
        t_free = round((effective_end - now).total_seconds() / 60.0, 2)

        if t_free <= 0 or t_total > t_free:
            continue

        # 第三階段：子項得分正規化 (0~100)
        s_credit = round((float(cand["runner_credit"]) / 5.0) * 100.0, 2)
        s_route = calculate_route_score(order["delivery_building"], walk_curr_to_rest + walk_rest_to_dest)
        s_time = round(max(0.0, min(100.0, ((t_free - t_total) / t_free) * 100.0)), 2)

        base_final = wc * s_credit + wr * s_route + wt * s_time

        past_same_shop = conn.execute(
            """SELECT COUNT(*) FROM order_matches om
               JOIN orders o ON o.order_id = om.order_id
               WHERE om.runner_id = ? AND o.restaurant_id = ? AND om.status = 'completed'""",
            (cand["user_id"], order["restaurant_id"]),
        ).fetchone()[0]
        familiarity_bonus = min(3.0, past_same_shop * 1.0)
        final_score = round(min(100.0, base_final + familiarity_bonus), 2)

        candidates.append({
            "candidate_user_id": cand["user_id"],
            "display_name": cand["display_name"],
            "current_location": cand["current_location_name"],
            "runner_credit": cand["runner_credit"],
            "t_total_minutes": t_total,
            "t_free_minutes": t_free,
            "credit_score": s_credit,
            "route_score": s_route,
            "time_score": s_time,
            "familiarity_bonus": familiarity_bonus,
            "final_score": final_score,
        })

    candidates.sort(key=lambda x: x["final_score"], reverse=True)

    batch_id = f"ai_{uuid4().hex[:12]}"
    for idx, item in enumerate(candidates, start=1):
        item["rank_position"] = idx
        if save_to_db:
            conn.execute(
                """INSERT INTO matching_results (
                       order_id, candidate_user_id, credit_score, route_score,
                       time_score, final_score, rank_position, recommendation_batch_id
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    order_id,
                    item["candidate_user_id"],
                    item["credit_score"],
                    item["route_score"],
                    item["time_score"],
                    item["final_score"],
                    idx,
                    batch_id,
                ),
            )

    return {
        "order_id": order_id,
        "restaurant_name": order["restaurant_name"],
        "delivery_location": order["delivery_location_name"],
        "mode": mode_label,
        "weights": {"W_C": wc, "W_R": wr, "W_T": wt},
        "recommendation_batch_id": batch_id if save_to_db and candidates else None,
        "candidate_count": len(candidates),
        "recommendations": candidates,
    }


def recommend_orders_for_runner(
    conn: sqlite3.Connection,
    runner_id: int,
    current_location_id: int,
    free_minutes: float,
    now: datetime | None = None,
    wait_minutes: float = DEFAULT_WAIT_MINUTES,
) -> list[dict]:
    """接單端「我要去買飯 / 順路找單」AI 推薦。"""
    now = now or datetime.now()
    user = conn.execute(
        "SELECT user_id, runner_credit, account_status FROM users WHERE user_id = ?",
        (runner_id,),
    ).fetchone()
    if user is None or user["account_status"] != "active":
        raise ValueError("找不到有效的接單者帳號")
    if user["runner_credit"] < MIN_RUNNER_CREDIT:
        return []

    curr_loc = conn.execute(
        "SELECT campus FROM locations WHERE location_id = ?",
        (current_location_id,),
    ).fetchone()
    if curr_loc is None:
        raise ValueError("無效的目前位置編號")

    pending_orders = conn.execute(
        """SELECT o.order_id, o.requester_id, o.restaurant_id, o.delivery_location_id,
                  o.deadline, o.reward_amount,
                  r.restaurant_name, r.location_id AS restaurant_loc_id,
                  dl.location_name AS delivery_location_name, dl.building AS delivery_building,
                  u.display_name AS requester_name, u.requester_credit
           FROM orders o
           JOIN restaurants r ON r.restaurant_id = o.restaurant_id
           JOIN locations dl ON dl.location_id = o.delivery_location_id
           JOIN users u ON u.user_id = o.requester_id
           WHERE o.status = 'pending'
             AND o.requester_id != ?
             AND dl.campus = ?""",
        (runner_id, curr_loc["campus"]),
    ).fetchall()

    recommended = []
    for o in pending_orders:
        deadline = datetime.fromisoformat(o["deadline"])
        if deadline <= now:
            continue
        w1 = get_walk_minutes(conn, current_location_id, o["restaurant_loc_id"])
        w2 = get_walk_minutes(conn, o["restaurant_loc_id"], o["delivery_location_id"])
        if w1 is None or w2 is None:
            continue

        t_total = round(w1 + wait_minutes + w2, 2)
        minutes_to_deadline = (deadline - now).total_seconds() / 60.0
        effective_free = min(free_minutes, minutes_to_deadline)
        if effective_free <= 0 or t_total > effective_free:
            continue

        high_pressure, _ = is_peak_or_urgent(now, deadline)
        wc, wr, wt = (0.3, 0.3, 0.4) if high_pressure else (0.4, 0.4, 0.2)

        s_credit = round((float(o["requester_credit"]) / 5.0) * 100.0, 2)
        s_route = calculate_route_score(o["delivery_building"], w1 + w2)
        s_time = round(max(0.0, min(100.0, ((effective_free - t_total) / effective_free) * 100.0)), 2)
        final_score = round(wc * s_credit + wr * s_route + wt * s_time, 2)

        recommended.append({
            "order_id": o["order_id"],
            "restaurant_name": o["restaurant_name"],
            "delivery_location": o["delivery_location_name"],
            "requester_name": o["requester_name"],
            "requester_credit": o["requester_credit"],
            "reward_amount": o["reward_amount"],
            "deadline": o["deadline"],
            "estimated_total_minutes": t_total,
            "match_score": final_score,
        })

    recommended.sort(key=lambda x: (x["match_score"], x["reward_amount"]), reverse=True)
    return recommended


def suggest_reward_amount(
    conn: sqlite3.Connection,
    restaurant_id: int,
    delivery_location_id: int,
    deadline_str: str,
    now: datetime | None = None,
) -> dict:
    """動態獎勵金建議 API。"""
    now = now or datetime.now()
    rest = conn.execute(
        "SELECT restaurant_name, location_id FROM restaurants WHERE restaurant_id = ?",
        (restaurant_id,),
    ).fetchone()
    dest = conn.execute(
        "SELECT location_name, building, floor, campus FROM locations WHERE location_id = ?",
        (delivery_location_id,),
    ).fetchone()
    if rest is None or dest is None:
        raise ValueError("找不到餐廳或送達地點")

    deadline = datetime.fromisoformat(deadline_str)
    walk_mins = get_walk_minutes(conn, rest["location_id"], delivery_location_id) or 5.0

    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    pending_cnt = conn.execute(
        """SELECT COUNT(*) FROM orders o
           JOIN locations l ON l.location_id = o.delivery_location_id
           WHERE o.status = 'pending' AND l.campus = ?""",
        (dest["campus"],),
    ).fetchone()[0]
    supply_cnt = conn.execute(
        """SELECT COUNT(DISTINCT a.user_id) FROM user_availability a
           JOIN locations l ON l.location_id = a.current_location_id
           WHERE a.willing_to_accept = 1 AND l.campus = ?
             AND a.available_from <= ? AND a.available_until > ?""",
        (dest["campus"], now_str, now_str),
    ).fetchone()[0]

    base_reward = 15
    reasons = ["基礎順路獎勵 15 元"]

    high_pressure, mode_label = is_peak_or_urgent(now, deadline)
    if high_pressure:
        base_reward += 5
        reasons.append(f"{mode_label} (+5 元)")

    if dest["building"] in REMOTE_BUILDINGS or walk_mins >= 8.0:
        base_reward += 5
        reasons.append("遠距離或偏遠大樓移動補償 (+5 元)")
    if dest["floor"] is not None and dest["floor"] >= 4:
        base_reward += 3
        reasons.append(f"高樓層 ({dest['floor']}F) 等待電梯補償 (+3 元)")

    if pending_cnt > supply_cnt:
        base_reward += 5
        reasons.append(f"目前供需吃緊 (待接 {pending_cnt} 單 / 可接 {supply_cnt} 人) (+5 元)")

    suggested = min(35, base_reward)
    return {
        "suggested_reward": suggested,
        "recommended_range": [max(10, suggested - 5), min(35, suggested + 5)],
        "estimated_walk_minutes": walk_mins,
        "supply_demand": {"pending_orders": pending_cnt, "available_runners": supply_cnt},
        "reasons": reasons,
    }


def generate_ai_recommendation_summary(match_result: dict) -> str:
    """【Gemini 結果解釋層】將三階段計算的前三名分數轉化為親切的口語推薦理由。"""
    candidates = match_result.get("recommendations", [])
    if not candidates:
        return "目前暫無符合時間與信用條件的順路接單者，建議適度調高獎勵金以吸引接單。"

    top = candidates[0]
    fallback_msg = (
        f"首推 {top['display_name']}（綜合推薦分 {top['final_score']} 分）！"
        f"目前位於{top['current_location']}，預估總耗時僅 {top['t_total_minutes']} 分鐘，"
        f"信用 {top['runner_credit']} 分且空堂充裕，最能準時送達。"
    )

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return fallback_msg

    client = genai.Client(api_key=api_key)
    prompt = (
        f"你是東吳大學校園代購平台 Soochow EATs 的 AI 媒合助手。"
        f"目前有一筆從「{match_result['restaurant_name']}」送到「{match_result['delivery_location']}」的訂單，"
        f"系統處於「{match_result['mode']}」。"
        f"以下是經過時間、路線與信用公式計算後的前三名候選接單者：{candidates[:3]}。"
        f"請用繁體中文、80字以內，向發單者推薦第1名接單者並簡述原因，語氣親切精簡，直接輸出推薦內容即可。"
    )

    for model_name in GEMINI_MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            if response.text:
                return response.text.strip()
        except Exception:
            continue

    return fallback_msg


def parse_natural_language_order(
    user_text: str,
    restaurants_list: list[dict],
    locations_list: list[dict],
) -> dict:
    """【Gemini 前端理解層】將學生在 LINE Bot 輸入的一句話解析為結構化訂單草稿。"""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("尚未設定 GEMINI_API_KEY 環境變數，無法使用自然語言解析功能")

    client = genai.Client(api_key=api_key)
    prompt = f"""
你是東吳大學校園代購平台的訂單解析助手。請根據使用者的自然語言輸入，從以下資料庫清單中匹配最接近的餐廳與送達地點。

【可選餐廳清單】：
{json.dumps(restaurants_list, ensure_ascii=False)}

【可選校園送達地點清單】：
{json.dumps(locations_list, ensure_ascii=False)}

【使用者輸入】：
「{user_text}」

請嚴格輸出 JSON 格式（不要加 markdown 標記），包含以下欄位：
- restaurant_id: 匹配到的餐廳整數 ID（若找不到填 null）
- restaurant_name: 匹配到的餐廳名稱
- delivery_location_id: 匹配到的送達地點整數 ID（若找不到填 null）
- delivery_location_name: 匹配到的送達地點名稱
- item_summary: 使用者想買的餐點與數量摘要（字串）
- reward_amount: 使用者提到的獎勵金整數（若未提到預設為 15）
- note: 特殊備註（如不要辣、去冰等，無則填 null）
"""
    last_error = None
    for model_name in GEMINI_MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
            return json.loads(response.text)
        except Exception as exc:
            last_error = exc
            continue

    raise RuntimeError(f"所有備援模型皆暫時無法回應：{last_error}")