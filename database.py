import os
import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash
from config import DB_FILE
from crypto_utils import encrypt_data, decrypt_data

def init_db(recreate=False):
    if recreate and os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
            print(f"[{datetime.now().isoformat()}] ✅ 旧数据库 {DB_FILE} 已删除，准备重建。")
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ 无法删除旧数据库: {e}")

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    db_existed = not recreate and os.path.exists(DB_FILE)

    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  password TEXT NOT NULL,
                  created_at TEXT NOT NULL)''')

    c.execute('''CREATE TABLE IF NOT EXISTS user_configs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  config_name TEXT NOT NULL DEFAULT 'default',
                  exchange TEXT NOT NULL DEFAULT 'binance',
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
                  FOREIGN KEY (user_id) REFERENCES users(id),
                  UNIQUE(user_id, config_name))''')
    
    # 为已存在的表添加新列（如果不存在）
    try:
        c.execute("ALTER TABLE user_configs ADD COLUMN config_name TEXT NOT NULL DEFAULT 'default'")
        print(f"[{datetime.now().isoformat()}] ✅ user_configs 表已添加 config_name 列")
    except sqlite3.OperationalError:
        pass  # 列已存在
    
    try:
        c.execute("ALTER TABLE user_configs ADD COLUMN exchange TEXT NOT NULL DEFAULT 'binance'")
        print(f"[{datetime.now().isoformat()}] ✅ user_configs 表已添加 exchange 列")
    except sqlite3.OperationalError:
        pass  # 列已存在

    c.execute('''CREATE TABLE IF NOT EXISTS orders
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  symbol TEXT NOT NULL,
                  price TEXT NOT NULL,
                  quantity TEXT NOT NULL,
                  side TEXT NOT NULL,
                  status TEXT NOT NULL,
                  order_id TEXT,
                  buy_price TEXT,
                  timestamp TEXT NOT NULL,
                  FOREIGN KEY (user_id) REFERENCES users(id))''')
    
    # 为已存在的 orders 表添加 buy_price 列（如果不存在）
    try:
        c.execute("ALTER TABLE orders ADD COLUMN buy_price TEXT")
        print(f"[{datetime.now().isoformat()}] ✅ orders 表已添加 buy_price 列")
    except sqlite3.OperationalError:
        pass  # 列已存在

    # 新增：交易对管理表
    c.execute('''CREATE TABLE IF NOT EXISTS trading_pairs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  symbol TEXT NOT NULL,
                  display_name TEXT NOT NULL,
                  exchanges TEXT DEFAULT 'binance,backpack',
                  created_at TEXT NOT NULL,
                  FOREIGN KEY (user_id) REFERENCES users(id),
                  UNIQUE(user_id, symbol))''')
    
    # 为已存在的表添加 exchanges 列（如果不存在）
    try:
        c.execute("ALTER TABLE trading_pairs ADD COLUMN exchanges TEXT DEFAULT 'binance,backpack'")
        print(f"[{datetime.now().isoformat()}] ✅ trading_pairs 表已添加 exchanges 列")
    except sqlite3.OperationalError:
        pass  # 列已存在

    try:
        c.execute("INSERT INTO users (username, password, created_at) VALUES (?, ?, ?)",
                  ('admin', generate_password_hash('admin123'), datetime.now().isoformat()))
        conn.commit()
        print(f"[{datetime.now().isoformat()}] ✅ 默认 admin 账号已创建（admin/admin123）")
    except sqlite3.IntegrityError:
        pass

    # 为 admin 用户添加默认交易对
    try:
        c.execute("SELECT id FROM users WHERE username=?", ('admin',))
        admin_id = c.fetchone()[0]
        default_pairs = [
            ('BTCUSDT', 'BTC/USDT'),
            ('ETHUSDT', 'ETH/USDT'),
            ('BNBUSDT', 'BNB/USDT'),
            ('ADAUSDT', 'ADA/USDT'),
            ('SOLUSDT', 'SOL/USDT')
        ]
        for symbol, name in default_pairs:
            try:
                c.execute("INSERT INTO trading_pairs (user_id, symbol, display_name, created_at) VALUES (?, ?, ?, ?)",
                         (admin_id, symbol, name, datetime.now().isoformat()))
            except sqlite3.IntegrityError:
                pass
        conn.commit()
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] ⚠️ 添加默认交易对失败: {e}")

    conn.close()
    print(f"[{datetime.now().isoformat()}] ✅ 数据库初始化完成：{DB_FILE}")


def get_user_id(username):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username=?", (username,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None


def save_user_config(username, config, config_name='default'):
    user_id = get_user_id(username)
    if not user_id:
        return False

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    encrypted_api_key = encrypt_data(config['api_key'])
    encrypted_api_secret = encrypt_data(config['api_secret'])
    exchange = config.get('exchange', 'binance')

    c.execute("SELECT id FROM user_configs WHERE user_id=? AND config_name=?", (user_id, config_name))
    exists = c.fetchone()

    if exists:
        c.execute("""UPDATE user_configs
                     SET exchange=?, api_key=?, api_secret=?, symbol=?, offset_percent=?, sell_offset_percent=?,
                         quantity=?, interval=?, testnet=?, simulate_trading=?, updated_at=?
                     WHERE user_id=? AND config_name=?""",
                  (exchange, encrypted_api_key, encrypted_api_secret, config['symbol'],
                   config['offset_percent'], config.get('sell_offset_percent', 0.5),
                   config['quantity'], config['interval'],
                   config.get('testnet', 1), config.get('simulate_trading', 1),
                   datetime.now().isoformat(), user_id, config_name))
    else:
        c.execute("""INSERT INTO user_configs
                     (user_id, config_name, exchange, api_key, api_secret, symbol, offset_percent, sell_offset_percent, quantity, interval, testnet, simulate_trading, updated_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  (user_id, config_name, exchange, encrypted_api_key, encrypted_api_secret, config['symbol'],
                   config['offset_percent'], config.get('sell_offset_percent', 0.5),
                   config['quantity'], config['interval'],
                   config.get('testnet', 1), config.get('simulate_trading', 1),
                   datetime.now().isoformat()))

    conn.commit()
    conn.close()
    print(f"[{datetime.now().isoformat()}] ✅ 配置已保存到 DB (user={username}, config={config_name})")
    return True


def load_user_config(username, config_name='default'):
    user_id = get_user_id(username)
    if not user_id:
        return None

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""SELECT config_name, exchange, api_key, api_secret, symbol, 
                        offset_percent, sell_offset_percent, quantity, interval, 
                        testnet, simulate_trading
                 FROM user_configs WHERE user_id=? AND config_name=?""", (user_id, config_name))
    result = c.fetchone()
    conn.close()

    if not result:
        return None

    return {
        'config_name': result[0],
        'exchange': result[1],
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


def get_user_config_list(username):
    """获取用户的所有配置列表"""
    user_id = get_user_id(username)
    if not user_id:
        return []

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""SELECT config_name, exchange, symbol, updated_at 
                 FROM user_configs WHERE user_id=? ORDER BY updated_at DESC""", (user_id,))
    configs = c.fetchall()
    conn.close()

    return [
        {
            'config_name': c[0],
            'exchange': c[1],
            'symbol': c[2],
            'updated_at': c[3]
        }
        for c in configs
    ]


def delete_user_config(username, config_name):
    """删除指定的配置"""
    user_id = get_user_id(username)
    if not user_id or config_name == 'default':
        return False  # 不允许删除 default 配置

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM user_configs WHERE user_id=? AND config_name=?", (user_id, config_name))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()

    if deleted:
        print(f"[{datetime.now().isoformat()}] ✅ 删除配置: {config_name} (user={username})")
    return deleted


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


def insert_order(user_id, symbol, price, quantity, side, status, order_id, buy_price=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""INSERT INTO orders (user_id, symbol, price, quantity, side, status, order_id, buy_price, timestamp)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
              (user_id, symbol, price, quantity, side, status, order_id, buy_price, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def update_order_status(order_id, status):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""UPDATE orders SET status=? WHERE order_id=?""", (status, order_id))
    conn.commit()
    conn.close()


def get_order_buy_price(order_id):
    """根据卖单 order_id 查询对应的买入价格"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""SELECT buy_price FROM orders WHERE order_id=? AND side='SELL'""", (order_id,))
    result = c.fetchone()
    conn.close()
    return float(result[0]) if result and result[0] else None


# 新增：交易对管理功能
def get_user_trading_pairs(username):
    """获取用户的交易对列表"""
    user_id = get_user_id(username)
    if not user_id:
        return []

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""SELECT id, symbol, display_name, exchanges, created_at
                 FROM trading_pairs WHERE user_id=? ORDER BY id ASC""", (user_id,))
    pairs = c.fetchall()
    conn.close()

    return [
        {
            'id': p[0],
            'symbol': p[1],
            'display_name': p[2],
            'exchanges': p[3] or 'binance,backpack',  # 默认支持所有交易所
            'created_at': p[4]
        }
        for p in pairs
    ]


def add_trading_pair(username, symbol, display_name):
    """添加交易对"""
    user_id = get_user_id(username)
    if not user_id:
        return False

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("""INSERT INTO trading_pairs (user_id, symbol, display_name, created_at)
                     VALUES (?, ?, ?, ?)""",
                  (user_id, symbol.upper(), display_name, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        print(f"[{datetime.now().isoformat()}] ✅ 添加交易对: {symbol} ({display_name})")
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False


def delete_trading_pair(username, pair_id):
    """删除交易对"""
    user_id = get_user_id(username)
    if not user_id:
        return False

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM trading_pairs WHERE id=? AND user_id=?", (pair_id, user_id))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()

    if deleted:
        print(f"[{datetime.now().isoformat()}] ✅ 删除交易对 ID: {pair_id}")
    return deleted


def update_trading_pair(username, pair_id, symbol, display_name, exchanges=None):
    """更新交易对"""
    user_id = get_user_id(username)
    if not user_id:
        return False

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        if exchanges is not None:
            c.execute("""UPDATE trading_pairs SET symbol=?, display_name=?, exchanges=?
                         WHERE id=? AND user_id=?""",
                      (symbol.upper(), display_name, exchanges, pair_id, user_id))
        else:
            c.execute("""UPDATE trading_pairs SET symbol=?, display_name=?
                         WHERE id=? AND user_id=?""",
                      (symbol.upper(), display_name, pair_id, user_id))
        updated = c.rowcount > 0
        conn.commit()
        conn.close()
        
        if updated:
            print(f"[{datetime.now().isoformat()}] ✅ 更新交易对 ID {pair_id}: {symbol} ({display_name})")
        return updated
    except sqlite3.IntegrityError:
        conn.close()
        return False