import os
import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash
from config import DB_FILE
from crypto_utils import encrypt_data, decrypt_data

def init_db(recreate=True):
    if recreate and os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
            print(f"[{datetime.now().isoformat()}] ✅ 旧数据库 {DB_FILE} 已删除，准备重建。")
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ 无法删除旧数据库: {e}")

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  password TEXT NOT NULL,
                  created_at TEXT NOT NULL)''')

    c.execute('''CREATE TABLE IF NOT EXISTS user_configs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  api_key TEXT NOT NULL,
                  api_secret TEXT NOT NULL,
                  symbol TEXT NOT NULL,
                  offset_percent REAL NOT NULL,
                  sell_offset_percent REAL NOT NULL DEFAULT 0.5,
                  quantity REAL NOT NULL,
                  interval INTEGER NOT NULL,
                  testnet INTEGER DEFAULT 1,
                  simulate_trading INTEGER DEFAULT 1,
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY (user_id) REFERENCES users(id))''')

    c.execute('''CREATE TABLE IF NOT EXISTS orders
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  symbol TEXT NOT NULL,
                  price TEXT NOT NULL,
                  quantity TEXT NOT NULL,
                  side TEXT NOT NULL,
                  status TEXT NOT NULL,
                  order_id TEXT,
                  timestamp TEXT NOT NULL,
                  FOREIGN KEY (user_id) REFERENCES users(id))''')

    try:
        c.execute("INSERT INTO users (username, password, created_at) VALUES (?, ?, ?)",
                  ('admin', generate_password_hash('admin123'), datetime.now().isoformat()))
        conn.commit()
        print(f"[{datetime.now().isoformat()}] ✅ 默认 admin 账号已创建（admin/admin123）")
    except sqlite3.IntegrityError:
        pass

    conn.close()
    print(f"[{datetime.now().isoformat()}] ✅ 数据库初始化完成：{DB_FILE}")


def get_user_id(username):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username=?", (username,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None


def save_user_config(username, config):
    user_id = get_user_id(username)
    if not user_id:
        return False

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    encrypted_api_key = encrypt_data(config['api_key'])
    encrypted_api_secret = encrypt_data(config['api_secret'])

    c.execute("SELECT id FROM user_configs WHERE user_id=?", (user_id,))
    exists = c.fetchone()

    if exists:
        c.execute("""UPDATE user_configs
                     SET api_key=?, api_secret=?, symbol=?, offset_percent=?, sell_offset_percent=?,
                         quantity=?, interval=?, testnet=?, simulate_trading=?, updated_at=?
                     WHERE user_id=?""",
                  (encrypted_api_key, encrypted_api_secret, config['symbol'],
                   config['offset_percent'], config.get('sell_offset_percent', 0.5),
                   config['quantity'], config['interval'],
                   config.get('testnet', 1), config.get('simulate_trading', 1),
                   datetime.now().isoformat(), user_id))
    else:
        c.execute("""INSERT INTO user_configs
                     (user_id, api_key, api_secret, symbol, offset_percent, sell_offset_percent, quantity, interval, testnet, simulate_trading, updated_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  (user_id, encrypted_api_key, encrypted_api_secret, config['symbol'],
                   config['offset_percent'], config.get('sell_offset_percent', 0.5),
                   config['quantity'], config['interval'],
                   config.get('testnet', 1), config.get('simulate_trading', 1),
                   datetime.now().isoformat()))

    conn.commit()
    conn.close()
    print(f"[{datetime.now().isoformat()}] ✅ 配置已保存到 DB (user={username})")
    return True


def load_user_config(username):
    user_id = get_user_id(username)
    if not user_id:
        return None

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM user_configs WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()

    if not result:
        return None

    return {
        'api_key': decrypt_data(result[2]),
        'api_secret': decrypt_data(result[3]),
        'symbol': result[4],
        'offset_percent': result[5],
        'sell_offset_percent': result[6],
        'quantity': result[7],
        'interval': result[8],
        'testnet': result[9],
        'simulate_trading': result[10]
    }


def get_user_orders(username):
    user_id = get_user_id(username)
    if not user_id:
        return []

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""SELECT symbol, price, quantity, side, status, order_id, timestamp
                 FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 100""", (user_id,))
    orders = c.fetchall()
    conn.close()

    return [
        {
            'symbol': o[0],
            'price': o[1],
            'quantity': o[2],
            'side': o[3],
            'status': o[4],
            'order_id': o[5],
            'timestamp': o[6]
        }
        for o in orders
    ]


def insert_order(user_id, symbol, price, quantity, side, status, order_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""INSERT INTO orders (user_id, symbol, price, quantity, side, status, order_id, timestamp)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
              (user_id, symbol, price, quantity, side, status, order_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def update_order_status(order_id, status):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""UPDATE orders SET status=? WHERE order_id=?""", (status, order_id))
    conn.commit()
    conn.close()
