"""Soochow EATs｜兩校區一次性初始化資料 (SQLite / Python 3.12)

使用方法：將本檔放在 backend/，與 database.py、soochow_eats.db 同一層：
    python seed_campus_data_complete.py

將資料匯入現有的 locations、restaurants、walking_times 三張表。
原本的 users、orders、menu_items 等其他資料表不會被改動。

資料可靠性：
- 建築名稱：東吳大學官方校區地圖 https://www-ch.scu.edu.tw/school_map
- 店家：東吳大學 115-1 校區餐廳營業時間（使用者提供的 PDF）
- 步行時間：供 AI 原型測試的「人工假設」，不是學校公布/現場實測/導航結果。
  請與組員實際走訪後修改 EDGE_MINUTES，或直接編輯 walking_times。
- 同一地點的既有資料、既有步行時間一律不覆蓋，方便安全重跑。
- 不產生跨校區步行時間，也不匯入未核實的菜單價格。
"""
from __future__ import annotations

import heapq
from contextlib import closing
from itertools import combinations
from database import get_connection

# (完整 location_name, building, floor, location_type, 路線節點)
# 建築主入口一律暫以 1F 為基準；B1 = -1。
SHUANGXI_LOCATIONS = [
    ("雙溪校區A棟", "A棟", 1, "campus", "A"),
    ("雙溪校區B棟", "B棟", 1, "campus", "B"),
    ("雙溪校區C棟", "C棟", 1, "campus", "C"),
    ("雙溪校區D棟", "D棟", 1, "campus", "D"),
    ("雙溪校區F棟", "F棟", 1, "campus", "F"),
    ("雙溪校區G棟", "G棟", 1, "campus", "G"),
    ("雙溪校區H棟", "H棟", 1, "campus", "H"),
    ("雙溪校區I棟", "I棟", 1, "campus", "I"),
    ("雙溪校區J棟", "J棟", 1, "campus", "J"),
    ("雙溪校區K棟", "K棟", 1, "campus", "K"),
    ("雙溪校區L棟", "L棟", 1, "campus", "L"),
    ("雙溪校區M棟", "M棟", 1, "campus", "M"),
    ("雙溪校區N棟", "N棟", 1, "campus", "N"),
    ("雙溪校區P棟", "P棟", 1, "campus", "P"),
    ("雙溪校區Q棟", "Q棟", 1, "campus", "Q"),
    ("雙溪校區R棟", "R棟", 1, "campus", "R"),
    ("雙溪校區S棟", "S棟", 1, "campus", "S"),
    ("雙溪校區柚芳樓前", "柚芳樓", 1, "restaurant", "Y"),
    # 根據校方 115-1 餐廳供餐公告
    ("雙溪校區B棟1F", "B棟", 1, "restaurant", "B"),
    ("雙溪校區B棟B1", "B棟", -1, "restaurant", "B"),
    ("雙溪校區D棟1F", "D棟", 1, "restaurant", "D"),
]

DOWNTOWN_LOCATIONS = [
    ("城中校區第一大樓", "第一大樓", 1, "campus", "1"),
    ("城中校區第二大樓", "第二大樓", 1, "campus", "2"),
    ("城中校區第三大樓", "第三大樓", 1, "campus", "3"),
    ("城中校區第四大樓", "第四大樓", 1, "campus", "4"),
    ("城中校區第五大樓", "第五大樓", 1, "campus", "5"),
    ("城中校區第六大樓", "第六大樓", 1, "campus", "6"),
    ("城中校區第六大樓1F", "第六大樓", 1, "restaurant", "6"),
    ("城中校區第六大樓2F", "第六大樓", 2, "restaurant", "6"),
    ("城中校區第六大樓3F", "第六大樓", 3, "restaurant", "6"),
]

# (店名, 對應地點)；排除空櫃、影印店及非供餐服務
RESTAURANTS = [
    ("7-11便利商店（雙溪）", "雙溪校區B棟1F"),
    ("麥當勞", "雙溪校區B棟1F"),
    ("蛋白盒子", "雙溪校區B棟1F"),
    ("玩米食", "雙溪校區B棟1F"),
    ("吉吉村美食屋", "雙溪校區B棟1F"),
    ("包子商行", "雙溪校區B棟1F"),
    ("御喜自助餐", "雙溪校區B棟B1"),
    ("安鑫 BRUNCH", "雙溪校區B棟B1"),
    ("丼物園", "雙溪校區B棟B1"),
    ("四海遊龍", "雙溪校區B棟B1"),
    ("醬心獨辣", "雙溪校區B棟B1"),
    ("趙班長海苔飯捲", "雙溪校區B棟B1"),
    ("東吳涼麵", "雙溪校區B棟B1"),
    ("拉手", "雙溪校區B棟B1"),
    ("木子甜飲", "雙溪校區B棟B1"),
    ("路易莎", "雙溪校區D棟1F"),
    ("校車咖啡", "雙溪校區柚芳樓前"),
    ("7-11便利商店（城中）", "城中校區第六大樓1F"),
    ("沐達早餐", "城中校區第六大樓1F"),
    ("海音咖啡", "城中校區第六大樓1F"),
    ("林娘食堂", "城中校區第六大樓2F"),
    ("咖哩食堂", "城中校區第六大樓2F"),
    ("奕香咖啡", "城中校區第六大樓2F"),
    ("夠健康廚房", "城中校區第六大樓3F"),
    ("吃好食堂", "城中校區第六大樓3F"),
]

# 邊長數值為人工估測的校園動線「測試權重」（分鐘），非實測。
# 每一對建築間步行時間，是以這些假設路線邊做最短路徑運算產生。
# 請實測後修改；不想使用估計時間時，設 INCLUDE_ESTIMATED_WALKING_TIMES=False。
INCLUDE_ESTIMATED_WALKING_TIMES = True
SHUANGXI_EDGE_MINUTES = [
    ("A", "B", 2.5), ("A", "C", 2.0), ("B", "C", 2.0),
    ("B", "G", 2.5), ("B", "H", 3.0), ("B", "N", 3.5),
    ("B", "D", 5.0), ("B", "F", 4.0), ("B", "Y", 4.0),
    ("G", "H", 2.0), ("H", "N", 2.5), ("G", "D", 3.5),
    ("D", "R", 4.0), ("D", "M", 3.0), ("F", "M", 2.0),
    ("F", "I", 2.0), ("I", "J", 1.0), ("J", "K", 1.0),
    ("K", "L", 1.0), ("L", "M", 2.0), ("M", "N", 3.0),
    ("H", "P", 2.0), ("P", "Q", 1.0), ("Q", "R", 3.0),
    ("R", "S", 3.0), ("A", "Y", 3.0),
]
DOWNTOWN_EDGE_MINUTES = [
    ("1", "2", 2.0), ("1", "3", 2.0), ("2", "3", 2.0),
    ("3", "4", 1.0), ("4", "5", 2.5), ("2", "5", 3.0),
    ("2", "6", 2.5), ("1", "6", 3.0), ("3", "6", 3.0),
]
# 以 0.5 分鐘/層作為簡報提出的樓層補償；B1(-1) 至 1F(1) 視為一層。
FLOOR_PENALTY_PER_LEVEL = 0.5


def floor_steps(floor: int | None) -> int:
    if floor is None or floor == 1:
        return 0
    return -floor if floor < 0 else floor - 1


def build_graph(edges):
    graph = {}
    for a, b, mins in edges:
        graph.setdefault(a, []).append((b, mins))
        graph.setdefault(b, []).append((a, mins))
    return graph


def shortest_minutes(graph, start, end):
    if start == end:
        return 0.0
    heap = [(0.0, start)]
    best = {start: 0.0}
    while heap:
        cost, node = heapq.heappop(heap)
        if node == end:
            return cost
        if cost > best[node]:
            continue
        for nxt, weight in graph.get(node, []):
            new = cost + weight
            if new < best.get(nxt, float('inf')):
                best[nxt] = new
                heapq.heappush(heap, (new, nxt))
    raise ValueError(f"示範步行網路未連通：{start} -> {end}")


def seed():
    with closing(get_connection()) as conn, conn:
        needed = {'locations', 'restaurants', 'walking_times'}
        existing_tables = {
            r['name'] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if not needed <= existing_tables:
            raise RuntimeError(f"尚未建好資料表：{', '.join(sorted(needed - existing_tables))}。請先執行 init_db.py。")

        # 在既有 locations 表中安全增加校區欄位，不重建其他資料表
        cols = {r['name'] for r in conn.execute('PRAGMA table_info(locations)').fetchall()}
        if 'campus' not in cols:
            conn.execute('ALTER TABLE locations ADD COLUMN campus TEXT')
        # 既有資料若名稱已有校區前綴，亦可自動補上校區
        conn.execute("UPDATE locations SET campus='shuangxi' WHERE campus IS NULL AND location_name LIKE '雙溪校區%'")
        conn.execute("UPDATE locations SET campus='downtown' WHERE campus IS NULL AND location_name LIKE '城中校區%'")

        added_locs = added_restaurants = added_times = 0
        all_locations = SHUANGXI_LOCATIONS + DOWNTOWN_LOCATIONS
        loc_ids = {}
        for name, building, floor, kind, _node in all_locations:
            campus = 'shuangxi' if name.startswith('雙溪校區') else 'downtown'
            row = conn.execute("SELECT location_id FROM locations WHERE location_name=?", (name,)).fetchone()
            if row is None:
                cur = conn.execute(
                    "INSERT INTO locations (location_name, building, floor, location_type, campus) VALUES (?,?,?,?,?)",
                    (name, building, floor, kind, campus)
                )
                loc_ids[name] = cur.lastrowid
                added_locs += 1
            else:
                loc_ids[name] = row['location_id']
                conn.execute("UPDATE locations SET campus=? WHERE location_id=? AND campus IS NULL", (campus, row['location_id']))

        for restaurant, loc_name in RESTAURANTS:
            loc_id = loc_ids[loc_name]
            row = conn.execute(
                "SELECT restaurant_id FROM restaurants WHERE restaurant_name=? AND location_id=?",
                (restaurant, loc_id)
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO restaurants (restaurant_name, location_id, address, is_active) VALUES (?,?,NULL,1)",
                    (restaurant, loc_id)
                )
                added_restaurants += 1

        if INCLUDE_ESTIMATED_WALKING_TIMES:
            for location_group, edges in (
                (SHUANGXI_LOCATIONS, SHUANGXI_EDGE_MINUTES),
                (DOWNTOWN_LOCATIONS, DOWNTOWN_EDGE_MINUTES),
            ):
                graph = build_graph(edges)
                # 每個校區內所有不同的地點兩兩配對，且建立雙向紀錄
                for origin, target in combinations(location_group, 2):
                    o_name, _o_building, o_floor, _o_type, o_node = origin
                    t_name, _t_building, t_floor, _t_type, t_node = target
                    base = shortest_minutes(graph, o_node, t_node)
                    extra = FLOOR_PENALTY_PER_LEVEL * (
                        floor_steps(o_floor) + floor_steps(t_floor)
                    )
                    # 對於同一棟不同樓層，以樓層差直接估計
                    if o_node == t_node:
                        def level(f):
                            return 0 if f is None else f
                        # B1 (-1) 和 1F (1) 差一層，2F 和 1F 也是一層
                        def actual_level(f):
                            return 0 if f == -1 else (1 if f is None else f)
                        extra = FLOOR_PENALTY_PER_LEVEL * abs(actual_level(o_floor) - actual_level(t_floor))
                    estimate = round(base + extra, 1)
                    for a_name, b_name in ((o_name, t_name), (t_name, o_name)):
                        already = conn.execute(
                            "SELECT 1 FROM walking_times WHERE from_location_id=? AND to_location_id=?",
                            (loc_ids[a_name], loc_ids[b_name])
                        ).fetchone()
                        if already is None:
                            conn.execute(
                                "INSERT INTO walking_times (from_location_id, to_location_id, walking_minutes) VALUES (?,?,?)",
                                (loc_ids[a_name], loc_ids[b_name], estimate)
                            )
                            added_times += 1

        print("✅ Soochow EATs 初始資料匯入完成")
        print(f"本次新增：地點 {added_locs}、餐飲店家 {added_restaurants}、估計步行紀錄 {added_times}")
        for table in ('locations', 'restaurants', 'walking_times'):
            total = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            print(f'{table}: 總計 {total} 筆')
        print("locations 已包含 campus 欄位（shuangxi / downtown）。")
        print("注意：步行時間為原型測試假設，非實測；同校區內雙向估計，沒有跨校區路線。")
        print("不會覆蓋既有資料；尚未匯入菜單 menu_items 或店家營業時段。")


if __name__ == '__main__':
    seed()
