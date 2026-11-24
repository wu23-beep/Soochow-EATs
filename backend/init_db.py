
from database import get_connection

conn = get_connection()

# 建立使用者資料表
conn.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    line_user_id TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    requester_credit REAL NOT NULL DEFAULT 5.0
        CHECK(requester_credit BETWEEN 0 AND 5),
    runner_credit REAL NOT NULL DEFAULT 5.0
        CHECK(runner_credit BETWEEN 0 AND 5),
    account_status TEXT NOT NULL DEFAULT 'active'
        CHECK(account_status IN ('active', 'suspended')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
""")

# 1. 地點資料表
conn.execute("""
CREATE TABLE IF NOT EXISTS locations (
    location_id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_name TEXT NOT NULL,
    building TEXT,
    floor INTEGER,
    location_type TEXT NOT NULL
        CHECK(location_type IN ('campus', 'restaurant', 'other'))
)
""")

# 2. 餐廳資料表
conn.execute("""
CREATE TABLE IF NOT EXISTS restaurants (
    restaurant_id INTEGER PRIMARY KEY AUTOINCREMENT,
    restaurant_name TEXT NOT NULL,
    location_id INTEGER NOT NULL,
    address TEXT,
    is_active INTEGER NOT NULL DEFAULT 1
        CHECK(is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (location_id)
        REFERENCES locations(location_id)
)
""")

# 3. 菜色資料表
conn.execute("""
CREATE TABLE IF NOT EXISTS menu_items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    restaurant_id INTEGER NOT NULL,
    item_name TEXT NOT NULL,
    price INTEGER NOT NULL CHECK(price >= 0),
    description TEXT,
    is_available INTEGER NOT NULL DEFAULT 1
        CHECK(is_available IN (0, 1)),

    FOREIGN KEY (restaurant_id)
        REFERENCES restaurants(restaurant_id)
)
""")

# 4. 訂單資料表
conn.execute("""
CREATE TABLE IF NOT EXISTS orders (
    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
    requester_id INTEGER NOT NULL,
    restaurant_id INTEGER NOT NULL,
    delivery_location_id INTEGER NOT NULL,
    deadline TEXT NOT NULL,
    reward_amount INTEGER NOT NULL DEFAULT 0
        CHECK(reward_amount >= 0),
    note TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN (
            'pending',
            'accepted',
            'delivered',
            'completed',
            'cancelled'
        )),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (requester_id)
        REFERENCES users(user_id),

    FOREIGN KEY (restaurant_id)
        REFERENCES restaurants(restaurant_id),

    FOREIGN KEY (delivery_location_id)
        REFERENCES locations(location_id)
)
""")

# 5. 訂單明細資料表
conn.execute("""
CREATE TABLE IF NOT EXISTS order_items (
    order_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL
        CHECK(quantity > 0),
    unit_price INTEGER NOT NULL
        CHECK(unit_price >= 0),
    special_request TEXT,

    FOREIGN KEY (order_id)
        REFERENCES orders(order_id),

    FOREIGN KEY (item_id)
        REFERENCES menu_items(item_id)
)
""")

# 6. 接單紀錄資料表
conn.execute("""
CREATE TABLE IF NOT EXISTS order_matches (
    match_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    runner_id INTEGER NOT NULL,
    accepted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    delivered_at TEXT,
    status TEXT NOT NULL DEFAULT 'accepted'
        CHECK(status IN (
            'accepted',
            'delivered',
            'completed',
            'cancelled'
        )),

    FOREIGN KEY (order_id)
        REFERENCES orders(order_id),

    FOREIGN KEY (runner_id)
        REFERENCES users(user_id)
)
""")

# 同一筆訂單，同時間只能有一筆有效接單紀錄
conn.execute("""
CREATE UNIQUE INDEX IF NOT EXISTS
idx_one_active_match_per_order
ON order_matches(order_id)
WHERE status IN ('accepted', 'delivered', 'completed')
""")

# 7. 評價紀錄資料表
conn.execute("""
CREATE TABLE IF NOT EXISTS reviews (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    reviewer_id INTEGER NOT NULL,
    reviewee_id INTEGER NOT NULL,
    rating INTEGER NOT NULL
        CHECK(rating BETWEEN 1 AND 5),
    comment TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (order_id)
        REFERENCES orders(order_id),

    FOREIGN KEY (reviewer_id)
        REFERENCES users(user_id),

    FOREIGN KEY (reviewee_id)
        REFERENCES users(user_id),

    CHECK(reviewer_id != reviewee_id),
    UNIQUE(order_id, reviewer_id)
)
""")

# 8. 使用者可接單時段資料表
conn.execute("""
CREATE TABLE IF NOT EXISTS user_availability (
    availability_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    current_location_id INTEGER NOT NULL,
    available_from TEXT NOT NULL,
    available_until TEXT NOT NULL,
    willing_to_accept INTEGER NOT NULL DEFAULT 0
        CHECK(willing_to_accept IN (0, 1)),

    CHECK(available_until > available_from),

    FOREIGN KEY (user_id)
        REFERENCES users(user_id),

    FOREIGN KEY (current_location_id)
        REFERENCES locations(location_id)
)
""")

# 9. 步行時間資料表
conn.execute("""
CREATE TABLE IF NOT EXISTS walking_times (
    walking_time_id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_location_id INTEGER NOT NULL,
    to_location_id INTEGER NOT NULL,
    walking_minutes REAL NOT NULL
        CHECK(walking_minutes >= 0),

    FOREIGN KEY (from_location_id)
        REFERENCES locations(location_id),

    FOREIGN KEY (to_location_id)
        REFERENCES locations(location_id),

    UNIQUE(from_location_id, to_location_id)
)
""")

# 10. AI 智慧媒合結果資料表
conn.execute("""
CREATE TABLE IF NOT EXISTS matching_results (
    result_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    candidate_user_id INTEGER NOT NULL,

    credit_score REAL NOT NULL
        CHECK(credit_score BETWEEN 0 AND 100),

    route_score REAL NOT NULL
        CHECK(route_score BETWEEN 0 AND 100),

    time_score REAL NOT NULL
        CHECK(time_score BETWEEN 0 AND 100),

    final_score REAL NOT NULL
        CHECK(final_score BETWEEN 0 AND 100),

    rank_position INTEGER NOT NULL
        CHECK(rank_position > 0),

    recommendation_batch_id TEXT NOT NULL,
    calculated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (order_id)
        REFERENCES orders(order_id),

    FOREIGN KEY (candidate_user_id)
        REFERENCES users(user_id),

    UNIQUE(recommendation_batch_id, order_id, candidate_user_id)
)
""")

conn.commit()
conn.close()

print("11 張資料表已就緒。")
