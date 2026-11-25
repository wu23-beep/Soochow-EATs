
import os
import sqlite3
from pathlib import Path

# 資料庫檔案的位置
DB_PATH = Path(__file__).resolve().parent / "soochow_eats.db"

# 建立資料庫連線
def get_connection():
    conn = sqlite3.connect(os.environ.get("SOOCHOW_EATS_DB_PATH") or DB_PATH)

    # 讓查詢結果可以使用欄位名稱
    conn.row_factory = sqlite3.Row

    # 啟用外鍵限制
    conn.execute("PRAGMA foreign_keys = ON")

    return conn
