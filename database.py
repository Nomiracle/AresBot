import os
import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash
from config import DB_FILE
from crypto_utils import encrypt_data, decrypt_data
from contextlib import contextmanager
import queue
import threading


class SQLiteConnectionPool:
    """SQLite 连接池"""
    def __init__(self, database, max_connections=10, timeout=30):
        self.database = database
        self.max_connections = max_connections
        self.timeout = timeout
        self._pool = queue.Queue(maxsize=max_connections)
        self._lock = threading.Lock()
        self._created_connections = 0
        
    def _create_connection(self):
        """创建新的数据库连接"""
        conn = sqlite3.connect(self.database, check_same_thread=False)
        # 启用外键约束
        conn.execute("PRAGMA foreign_keys = ON")
        # 设置行工厂，使查询结果可以像字典一样访问
        conn.row_factory = sqlite3.Row
        return conn
    
    def get_connection(self):
        """从连接池获取连接"""
        try:
            # 尝试从池中获取现有连接
            conn = self._pool.get(block=False)
            return conn
        except queue.Empty:
            # 池中没有可用连接，检查是否可以创建新连接
            with self._lock:
                if self._created_connections < self.max_connections:
                    self._created_connections += 1
                    return self._create_connection()
            
            # 已达到最大连接数，等待可用连接
            try:
                conn = self._pool.get(timeout=self.timeout)
                return conn
            except queue.Empty:
                raise Exception(f"无法在 {self.timeout} 秒内获取数据库连接")
    
    def return_connection(self, conn):
        """将连接归还到连接池"""
        try:
            # 回滚任何未提交的事务
            conn.rollback()
            self._pool.put(conn, block=False)
        except queue.Full:
            # 池已满，关闭连接
            conn.close()
            with self._lock:
                self._created_connections -= 1
    
    def close_all(self):
        """关闭所有连接"""
        while not self._pool.empty():
            try:
                conn = self._pool.get(block=False)
                conn.close()
            except queue.Empty:
                break
        with self._lock:
            self._created_connections = 0
    
    @contextmanager
    def get_cursor(self):
        """上下文管理器：自动获取和归还连接"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            yield conn, cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            self.return_connection(conn)


# 创建全局连接池实例
db_pool = SQLiteConnectionPool(DB_FILE, max_connections=10)


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
                  credential_id INTEGER,
                  symbol TEXT NOT NULL,
                  offset_percent REAL NOT NULL,
                  sell_offset_percent REAL NOT NULL DEFAULT 0.5,
                  quantity REAL NOT NULL,
                  interval INTEGER NOT NULL,
                  testnet INTEGER DEFAULT 1,
                  simulate_trading INTEGER DEFAULT 1,
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY (user_id) REFERENCES users(id),
                  FOREIGN KEY (credential_id) REFERENCES api_credentials(id),
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
    
    try:
        c.execute("ALTER TABLE user_configs ADD COLUMN min_price_threshold REAL DEFAULT 0.15")
        print(f"[{datetime.now().isoformat()}] ✅ user_configs 表已添加 min_price_threshold 列")
    except sqlite3.OperationalError:
        pass  # 列已存在
    
    try:
        c.execute("ALTER TABLE user_configs ADD COLUMN market_close_threshold INTEGER DEFAULT 180")
        print(f"[{datetime.now().isoformat()}] ✅ user_configs 表已添加 market_close_threshold 列")
    except sqlite3.OperationalError:
        pass  # 列已存在
    
    try:
        c.execute("ALTER TABLE user_configs ADD COLUMN order_grid INTEGER DEFAULT 1")
        print(f"[{datetime.now().isoformat()}] ✅ user_configs 表已添加 order_grid 列")
    except sqlite3.OperationalError:
        pass  # 列已存在
    
    try:
        c.execute("ALTER TABLE user_configs ADD COLUMN sell_decay_count INTEGER DEFAULT 0")
        print(f"[{datetime.now().isoformat()}] ✅ user_configs 表已添加 sell_decay_count 列")
    except sqlite3.OperationalError:
        pass  # 列已存在
    
    try:
        c.execute("ALTER TABLE user_configs ADD COLUMN start_count INTEGER DEFAULT 0")
        print(f"[{datetime.now().isoformat()}] ✅ user_configs 表已添加 start_count 列")
    except sqlite3.OperationalError:
        pass  # 列已存在
    
    try:
        c.execute("ALTER TABLE user_configs ADD COLUMN stop_loss_delay INTEGER")
        print(f"[{datetime.now().isoformat()}] ✅ user_configs 表已添加 stop_loss_delay 列")
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
                  exchange TEXT,
                  fee TEXT,
                  timestamp TEXT NOT NULL,
                  updated_at TEXT,
                  FOREIGN KEY (user_id) REFERENCES users(id))''')
    
    # 为已存在的 orders 表添加 buy_price 列（如果不存在）
    try:
        c.execute("ALTER TABLE orders ADD COLUMN buy_price TEXT")
        print(f"[{datetime.now().isoformat()}] orders 表已添加 buy_price 列")
    except sqlite3.OperationalError:
        pass  # 列已存在

    # 添加 exchange 列（交易所）
    try:
        c.execute("ALTER TABLE orders ADD COLUMN exchange TEXT")
        print(f"[{datetime.now().isoformat()}] orders 表已添加 exchange 列")
    except sqlite3.OperationalError:
        pass

    # 添加 fee 列（手续费）
    try:
        c.execute("ALTER TABLE orders ADD COLUMN fee TEXT")
        print(f"[{datetime.now().isoformat()}] orders 表已添加 fee 列")
    except sqlite3.OperationalError:
        pass

    # 添加 updated_at 列（订单更新时间）
    try:
        c.execute("ALTER TABLE orders ADD COLUMN updated_at TEXT")
        print(f"[{datetime.now().isoformat()}] orders 表已添加 updated_at 列")
    except sqlite3.OperationalError:
        pass

    # 添加机器人参数字段
    try:
        c.execute("ALTER TABLE orders ADD COLUMN offset_percent TEXT")
        print(f"[{datetime.now().isoformat()}] orders 表已添加 offset_percent 列")
    except sqlite3.OperationalError:
        pass
    
    try:
        c.execute("ALTER TABLE orders ADD COLUMN sell_offset_percent TEXT")
        print(f"[{datetime.now().isoformat()}] orders 表已添加 sell_offset_percent 列")
    except sqlite3.OperationalError:
        pass
    
    try:
        c.execute("ALTER TABLE orders ADD COLUMN interval TEXT")
        print(f"[{datetime.now().isoformat()}] orders 表已添加 interval 列")
    except sqlite3.OperationalError:
        pass
    
    try:
        c.execute("ALTER TABLE orders ADD COLUMN min_price_diff_percent TEXT")
        print(f"[{datetime.now().isoformat()}] orders 表已添加 min_price_diff_percent 列")
    except sqlite3.OperationalError:
        pass
    
    try:
        c.execute("ALTER TABLE orders ADD COLUMN max_price_diff_percent TEXT")
        print(f"[{datetime.now().isoformat()}] orders 表已添加 max_price_diff_percent 列")
    except sqlite3.OperationalError:
        pass
    
    try:
        c.execute("ALTER TABLE orders ADD COLUMN avg_price_diff_percent TEXT")
        print(f"[{datetime.now().isoformat()}] orders 表已添加 avg_price_diff_percent 列")
    except sqlite3.OperationalError:
        pass
    
    # 添加卖单阶段的价格差值统计字段
    try:
        c.execute("ALTER TABLE orders ADD COLUMN sell_min_price_diff_percent TEXT")
        print(f"[{datetime.now().isoformat()}] orders 表已添加 sell_min_price_diff_percent 列")
    except sqlite3.OperationalError:
        pass
    
    try:
        c.execute("ALTER TABLE orders ADD COLUMN sell_max_price_diff_percent TEXT")
        print(f"[{datetime.now().isoformat()}] orders 表已添加 sell_max_price_diff_percent 列")
    except sqlite3.OperationalError:
        pass
    
    try:
        c.execute("ALTER TABLE orders ADD COLUMN sell_avg_price_diff_percent TEXT")
        print(f"[{datetime.now().isoformat()}] orders 表已添加 sell_avg_price_diff_percent 列")
    except sqlite3.OperationalError:
        pass

    # 新增：API凭证管理表
    c.execute('''CREATE TABLE IF NOT EXISTS api_credentials
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  alias TEXT NOT NULL,
                  exchange TEXT NOT NULL,
                  api_key TEXT NOT NULL,
                  api_secret TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY (user_id) REFERENCES users(id),
                  UNIQUE(user_id, alias))''')
    
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
        print(f"[{datetime.now().isoformat()}] trading_pairs 表已添加 exchanges 列")
    except sqlite3.OperationalError:
        pass  # 列已存在

    # 为user_configs表添加credential_id列(如果不存在)
    try:
        c.execute("ALTER TABLE user_configs ADD COLUMN credential_id INTEGER")
        print(f"[{datetime.now().isoformat()}] user_configs 表已添加 credential_id 列")
    except sqlite3.OperationalError:
        pass  # 列已存在
    
    # 为user_configs表添加created_at列(如果不存在)
    try:
        c.execute("ALTER TABLE user_configs ADD COLUMN created_at TEXT")
        print(f"[{datetime.now().isoformat()}] user_configs 表已添加 created_at 列")
    except sqlite3.OperationalError:
        pass  # 列已存在

    # 新增：系统配置表（存储钉钉webhook等配置）
    c.execute('''CREATE TABLE IF NOT EXISTS system_config
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  config_key TEXT NOT NULL,
                  config_value TEXT NOT NULL,
                  description TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY (user_id) REFERENCES users(id),
                  UNIQUE(user_id, config_key))''')

    try:
        c.execute("INSERT INTO users (username, password, created_at) VALUES (?, ?, ?)",
                  ('admin', generate_password_hash('admin123'), datetime.now().isoformat()))
        conn.commit()
        print(f"[{datetime.now().isoformat()}] 默认 admin 账号已创建（admin/admin123）")
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
    with db_pool.get_cursor() as (conn, c):
        c.execute("SELECT id FROM users WHERE username=?", (username,))
        result = c.fetchone()
        return result[0] if result else None


def save_user_config(username, config, config_name='default'):
    user_id = get_user_id(username)
    if not user_id:
        return False

    exchange = config.get('exchange', 'binance')
    credential_id = config.get('credential_id')
    
    if not credential_id:
        print(f"[{datetime.now().isoformat()}] ❌ 保存配置失败: 缺少credential_id")
        return False

    with db_pool.get_cursor() as (conn, c):
        c.execute("SELECT id FROM user_configs WHERE user_id=? AND config_name=?", (user_id, config_name))
        exists = c.fetchone()

        if exists:
            c.execute("""UPDATE user_configs
                         SET exchange=?, credential_id=?, symbol=?, offset_percent=?, sell_offset_percent=?,
                             quantity=?, interval=?, testnet=?, simulate_trading=?,
                             min_price_threshold=?, market_close_threshold=?, order_grid=?, sell_decay_count=?, stop_loss_delay=?, updated_at=?
                         WHERE user_id=? AND config_name=?""",
                      (exchange, credential_id, config['symbol'],
                       config['offset_percent'], config.get('sell_offset_percent', 0.5),
                       config['quantity'], config['interval'],
                       config.get('testnet', 1), config.get('simulate_trading', 1),
                       config.get('min_price_threshold', 0.15), config.get('market_close_threshold', 180),
                       config.get('order_grid', 1), config.get('sell_decay_count', 0), config.get('stop_loss_delay'),
                       datetime.now().isoformat(), user_id, config_name))
        else:
            c.execute("""INSERT INTO user_configs
                         (user_id, config_name, exchange, credential_id, symbol, offset_percent, sell_offset_percent, quantity, interval, testnet, simulate_trading, min_price_threshold, market_close_threshold, order_grid, sell_decay_count, stop_loss_delay, created_at, updated_at)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      (user_id, config_name, exchange, credential_id, config['symbol'],
                       config['offset_percent'], config.get('sell_offset_percent', 0.5),
                       config['quantity'], config['interval'],
                       config.get('testnet', 1), config.get('simulate_trading', 1),
                       config.get('min_price_threshold', 0.15), config.get('market_close_threshold', 180),
                       config.get('order_grid', 1), config.get('sell_decay_count', 0), config.get('stop_loss_delay'),
                       datetime.now().isoformat(), datetime.now().isoformat()))

    print(f"[{datetime.now().isoformat()}] ✅ 配置已保存到 DB (user={username}, config={config_name}, credential_id={credential_id})")
    return True


def load_user_config(username, config_name='default'):
    user_id = get_user_id(username)
    if not user_id:
        return None

    with db_pool.get_cursor() as (conn, c):
        c.execute("""SELECT config_name, exchange, credential_id, symbol, 
                            offset_percent, sell_offset_percent, quantity, interval, 
                            testnet, simulate_trading, min_price_threshold, market_close_threshold, order_grid, sell_decay_count, stop_loss_delay
                     FROM user_configs WHERE user_id=? AND config_name=?""", (user_id, config_name))
        result = c.fetchone()

    if not result:
        return None

    credential_id = result[2]
    
    # 从 api_credentials 表获取密钥
    api_key = ''
    api_secret = ''
    if credential_id:
        credential = get_credential_by_id(user_id, credential_id)
        if credential:
            api_key = credential['api_key']
            api_secret = credential['api_secret']

    return {
        'config_name': result[0],
        'exchange': result[1],
        'credential_id': credential_id,
        'api_key': api_key,
        'api_secret': api_secret,
        'symbol': result[3],
        'offset_percent': result[4],
        'sell_offset_percent': result[5],
        'quantity': result[6],
        'interval': result[7],
        'testnet': result[8],
        'simulate_trading': result[9],
        'min_price_threshold': result[10] if result[10] is not None else 0.15,
        'market_close_threshold': result[11] if result[11] is not None else 180,
        'order_grid': result[12] if result[12] is not None else 1,
        'sell_decay_count': result[13] if result[13] is not None else 0,
        'stop_loss_delay': result[14]  # 新增字段
    }


def get_user_config_list(username):
    """获取用户的所有配置名称"""
    user_id = get_user_id(username)
    if not user_id:
        return []
    
    with db_pool.get_cursor() as (conn, c):
        c.execute("""SELECT config_name FROM user_configs 
                     WHERE user_id=? AND config_name!='default' 
                     ORDER BY created_at DESC""", (user_id,))
        configs = c.fetchall()
    
    return [config[0] for config in configs]


def get_user_config_list_with_details(username, include_default=False):
    """获取用户的所有配置详细信息（包含密钥别名）"""
    user_id = get_user_id(username)
    if not user_id:
        return []
    
    with db_pool.get_cursor() as (conn, c):
        if include_default:
            # 包含 default 配置
            c.execute("""SELECT c.id, c.config_name, c.symbol, c.exchange, c.offset_percent, 
                               c.sell_offset_percent, c.quantity, c.interval, c.order_grid,
                               c.testnet, c.simulate_trading, c.start_count, 
                               c.min_price_threshold, c.market_close_threshold, c.sell_decay_count,
                               c.created_at, c.updated_at, cr.alias as credential_alias,c.stop_loss_delay
                         FROM user_configs c
                         LEFT JOIN api_credentials cr ON c.credential_id = cr.id
                         WHERE c.user_id=?
                         ORDER BY c.start_count DESC, c.created_at DESC""", (user_id,))
        else:
            # 不包含 default 配置
            c.execute("""SELECT c.id, c.config_name, c.symbol, c.exchange, c.offset_percent, 
                               c.sell_offset_percent, c.quantity, c.interval, c.order_grid,
                               c.testnet, c.simulate_trading, c.start_count, 
                               c.min_price_threshold, c.market_close_threshold, c.sell_decay_count,
                               c.created_at, c.updated_at, cr.alias as credential_alias,c.stop_loss_delay
                         FROM user_configs c
                         LEFT JOIN api_credentials cr ON c.credential_id = cr.id
                         WHERE c.user_id=? AND c.config_name!='default'
                         ORDER BY c.start_count DESC, c.created_at DESC""", (user_id,))
        configs = c.fetchall()
    
    return [
        {
            'id': cfg[0],
            'config_name': cfg[1],
            'symbol': cfg[2],
            'exchange': cfg[3],
            'offset_percent': cfg[4],
            'sell_offset_percent': cfg[5],
            'quantity': cfg[6],
            'interval': cfg[7],
            'order_grid': cfg[8],
            'testnet': cfg[9],
            'simulate_trading': cfg[10],
            'start_count': cfg[11] if cfg[11] is not None else 0,
            'min_price_threshold': cfg[12],
            'market_close_threshold': cfg[13],
            'sell_decay_count': cfg[14],
            'created_at': cfg[15],
            'updated_at': cfg[16],
            'credential_alias': cfg[17],
            'stop_loss_delay': cfg[18]
        }
        for cfg in configs
    ]


def get_user_configs_by_ids(username, config_ids):
    """根据ID列表获取用户配置"""
    user_id = get_user_id(username)
    if not user_id:
        return []
    
    with db_pool.get_cursor() as (conn, c):
        placeholders = ','.join(['?' for _ in config_ids])
        c.execute(f"""SELECT c.id, c.config_name, c.symbol, c.exchange, c.offset_percent, 
                           c.sell_offset_percent, c.quantity, c.interval, c.order_grid,
                           c.testnet, c.simulate_trading, c.start_count, c.credential_id,
                           c.min_price_threshold, c.market_close_threshold, c.sell_decay_count,
                           c.created_at, c.updated_at, cr.alias as credential_alias
                     FROM user_configs c
                     LEFT JOIN api_credentials cr ON c.credential_id = cr.id
                     WHERE c.user_id=? AND c.id IN ({placeholders})
                     ORDER BY c.start_count DESC, c.created_at DESC""", [user_id] + config_ids)
        configs = c.fetchall()
    
    return [
        {
            'id': cfg[0],
            'config_name': cfg[1],
            'symbol': cfg[2],
            'exchange': cfg[3],
            'offset_percent': cfg[4],
            'sell_offset_percent': cfg[5],
            'quantity': cfg[6],
            'interval': cfg[7],
            'order_grid': cfg[8],
            'testnet': cfg[9],
            'simulate_trading': cfg[10],
            'start_count': cfg[11] if cfg[11] is not None else 0,
            'min_price_threshold': cfg[12],
            'market_close_threshold': cfg[13],
            'sell_decay_count': cfg[14],
            'created_at': cfg[15],
            'updated_at': cfg[16],
            'credential_alias': cfg[17]
        }
        for cfg in configs
    ]


def delete_user_configs_by_ids(username, config_ids):
    """批量删除用户配置"""
    user_id = get_user_id(username)
    if not user_id:
        return 0
    
    with db_pool.get_cursor() as (conn, c):
        placeholders = ','.join(['?' for _ in config_ids])
        c.execute(f"DELETE FROM user_configs WHERE user_id=? AND id IN ({placeholders})", 
                  [user_id] + config_ids)
        deleted = c.rowcount
    
    if deleted > 0:
        print(f"[{datetime.now().isoformat()}] ✅ 批量删除配置: {deleted} 个 (user={username})")
    return deleted


def get_user_config_list(username):
    """获取用户的所有配置列表"""
    user_id = get_user_id(username)
    if not user_id:
        return []

    with db_pool.get_cursor() as (conn, c):
        c.execute("""SELECT config_name, exchange, symbol, updated_at 
                     FROM user_configs WHERE user_id=? ORDER BY updated_at DESC""", (user_id,))
        configs = c.fetchall()

    config_list = [
        {
            'config_name': c[0],
            'exchange': c[1],
            'symbol': c[2],
            'updated_at': c[3]
        }
        for c in configs
    ]
    
    # 如果用户没有任何配置，自动创建default配置
    if not config_list:
        print(f"[{datetime.now().isoformat()}] ⚠️ 用户 {username} 没有配置，自动创建default配置")
        default_config = {
            'exchange': 'binance',
            'api_key': '',
            'api_secret': '',
            'symbol': 'BTCUSDT',
            'offset_percent': -0.1,
            'sell_offset_percent': 0.5,
            'quantity': 0.001,
            'interval': 1,
            'testnet': 1,
            'simulate_trading': 1
        }
        save_user_config(username, default_config, 'default')
        config_list = [{
            'config_name': 'default',
            'exchange': 'binance',
            'symbol': 'BTCUSDT',
            'updated_at': datetime.now().isoformat()
        }]
    
    return config_list


def increment_start_count(username, config_name='default'):
    """递增指定配置的启动次数"""
    user_id = get_user_id(username)
    if not user_id:
        return False
    
    with db_pool.get_cursor() as (conn, c):
        c.execute("UPDATE user_configs SET start_count = start_count + 1 WHERE user_id=? AND config_name=?", 
                  (user_id, config_name))
        updated = c.rowcount > 0
    
    if updated:
        print(f"[{datetime.now().isoformat()}] ✅ 配置启动次数已递增: {config_name} (user={username})")
    return updated


def delete_user_config(username, config_name):
    """删除指定的配置"""
    user_id = get_user_id(username)
    if not user_id or config_name == 'default':
        return False  # 不允许删除 default 配置

    with db_pool.get_cursor() as (conn, c):
        c.execute("DELETE FROM user_configs WHERE user_id=? AND config_name=?", (user_id, config_name))
        deleted = c.rowcount > 0

    if deleted:
        print(f"[{datetime.now().isoformat()}] ✅ 删除配置: {config_name} (user={username})")
    return deleted


def get_user_orders(username):
    user_id = get_user_id(username)
    if not user_id:
        return []

    with db_pool.get_cursor() as (conn, c):
        c.execute("""SELECT symbol, price, quantity, side, status, order_id, timestamp
                     FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 100""", (user_id,))
        orders = c.fetchall()

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


def get_user_profits(username):
    """获取用户的盈利记录（卖单成交后计算盈利）"""
    user_id = get_user_id(username)
    if not user_id:
        return []

    with db_pool.get_cursor() as (conn, c):
        c.execute("""
            SELECT symbol, price, quantity, buy_price, fee, exchange, timestamp, updated_at, order_id,
                   offset_percent, sell_offset_percent, interval, 
                   min_price_diff_percent, max_price_diff_percent, avg_price_diff_percent,
                   sell_min_price_diff_percent, sell_max_price_diff_percent, sell_avg_price_diff_percent
            FROM orders 
            WHERE user_id=? AND side='SELL' AND status IN ('FILLED', 'order_filled')
            ORDER BY id DESC
        """, (user_id,))
        orders = c.fetchall()

    profits = []
    for o in orders:
        symbol = o[0]
        sell_price = float(o[1]) if o[1] else 0
        quantity = float(o[2]) if o[2] else 0
        buy_price = float(o[3]) if o[3] else 0
        fee = float(o[4]) if o[4] else 0
        exchange = o[5] or 'unknown'
        timestamp = o[6] or ''
        updated_at = o[7] or timestamp
        order_id = o[8] or ''
        offset_percent = o[9] if len(o) > 9 else None
        sell_offset_percent = o[10] if len(o) > 10 else None
        interval = o[11] if len(o) > 11 else None
        # 买单阶段差值统计
        min_price_diff_percent = o[12] if len(o) > 12 else None
        max_price_diff_percent = o[13] if len(o) > 13 else None
        avg_price_diff_percent = o[14] if len(o) > 14 else None
        # 卖单阶段差值统计
        sell_min_price_diff_percent = o[15] if len(o) > 15 else None
        sell_max_price_diff_percent = o[16] if len(o) > 16 else None
        sell_avg_price_diff_percent = o[17] if len(o) > 17 else None

        # 计算盈利
        # 做空交易所：盈利 = (开仓价 - 平仓价) * 数量 = (buy_price - sell_price) * quantity
        # 做多交易所：盈利 = (卖出价 - 买入价) * 数量 = (sell_price - buy_price) * quantity
        if buy_price > 0:
            is_short = 'short' in exchange.lower()
            if is_short:
                # 做空：开仓价(buy_price) > 平仓价(sell_price) 时盈利
                profit = (buy_price - sell_price) * quantity - fee
                profit_percent = ((buy_price - sell_price) / buy_price) * 100
            else:
                # 做多：卖出价 > 买入价 时盈利
                profit = (sell_price - buy_price) * quantity - fee
                profit_percent = ((sell_price - buy_price) / buy_price) * 100
        else:
            profit = 0
            profit_percent = 0

        profits.append({
            'symbol': symbol,
            'exchange': exchange,
            'buy_price': buy_price,
            'sell_price': sell_price,
            'quantity': quantity,
            'fee': fee,
            'profit': round(profit, 6),
            'profit_percent': round(profit_percent, 4),
            'timestamp': timestamp,
            'updated_at': updated_at,
            'order_id': order_id,
            'offset_percent': offset_percent,
            'sell_offset_percent': sell_offset_percent,
            'interval': interval,
            'min_price_diff_percent': min_price_diff_percent,
            'max_price_diff_percent': max_price_diff_percent,
            'avg_price_diff_percent': avg_price_diff_percent,
            'sell_min_price_diff_percent': sell_min_price_diff_percent,
            'sell_max_price_diff_percent': sell_max_price_diff_percent,
            'sell_avg_price_diff_percent': sell_avg_price_diff_percent
        })

    return profits


def insert_order(user_id, symbol, price, quantity, side, status, order_id, buy_price=None, exchange=None, fee=None, 
                 offset_percent=None, sell_offset_percent=None, interval=None, min_price_diff_percent=None,
                 max_price_diff_percent=None, avg_price_diff_percent=None):
    with db_pool.get_cursor() as (conn, c):
        c.execute("""INSERT INTO orders (user_id, symbol, price, quantity, side, status, order_id, buy_price, exchange, fee, 
                     offset_percent, sell_offset_percent, interval, min_price_diff_percent, max_price_diff_percent, avg_price_diff_percent, 
                     timestamp, updated_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  (user_id, symbol, price, quantity, side, status, order_id, buy_price, exchange, fee, 
                   offset_percent, sell_offset_percent, interval, min_price_diff_percent, max_price_diff_percent, avg_price_diff_percent,
                   datetime.now().isoformat(), datetime.now().isoformat()))


def update_order_status(order_id, status, fee=None, price=None, sell_min_diff=None, sell_max_diff=None, sell_avg_diff=None):
    """更新订单状态
    
    Args:
        order_id: 订单ID
        status: 订单状态
        fee: 手续费(可选)
        price: 价格(可选)
        sell_min_diff: 卖单最小差值(可选)
        sell_max_diff: 卖单最大差值(可选)
        sell_avg_diff: 卖单平均差值(可选)
    """
    with db_pool.get_cursor() as (conn, c):
        # 构建更新字段
        update_fields = ["status=?", "updated_at=?"]
        update_values = [status, datetime.now().isoformat()]
        
        if fee is not None:
            update_fields.append("fee=?")
            update_values.append(fee)
        
        if price is not None:
            update_fields.append("price=?")
            update_values.append(str(price))
        
        if sell_min_diff is not None:
            update_fields.append("sell_min_price_diff_percent=?")
            update_values.append(sell_min_diff)
        
        if sell_max_diff is not None:
            update_fields.append("sell_max_price_diff_percent=?")
            update_values.append(sell_max_diff)
        
        if sell_avg_diff is not None:
            update_fields.append("sell_avg_price_diff_percent=?")
            update_values.append(sell_avg_diff)
        
        update_values.append(order_id)
        
        sql = f"UPDATE orders SET {', '.join(update_fields)} WHERE order_id=?"
        c.execute(sql, tuple(update_values))


def get_order_buy_price(order_id):
    """根据卖单 order_id 查询对应的买入价格"""
    with db_pool.get_cursor() as (conn, c):
        c.execute("""SELECT buy_price FROM orders WHERE order_id=? AND side='SELL'""", (order_id,))
        result = c.fetchone()
        return float(result[0]) if result and result[0] else None


# 新增：交易对管理功能
def get_user_trading_pairs(username):
    """获取用户的交易对列表"""
    user_id = get_user_id(username)
    if not user_id:
        return []

    with db_pool.get_cursor() as (conn, c):
        c.execute("""SELECT id, symbol, display_name, exchanges, created_at
                     FROM trading_pairs WHERE user_id=? ORDER BY id ASC""", (user_id,))
        pairs = c.fetchall()

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


def add_trading_pair(username, symbol, display_name, exchanges=None):
    """添加交易对"""
    user_id = get_user_id(username)
    if not user_id:
        return False

    with db_pool.get_cursor() as (conn, c):
        try:
            c.execute("""INSERT INTO trading_pairs (user_id, symbol, display_name, exchanges, created_at)
                         VALUES (?, ?, ?, ?, ?)""",
                      (user_id, symbol.upper(), display_name, exchanges, datetime.now().isoformat()))
            pair_id = c.lastrowid
            print(f"[{datetime.now().isoformat()}] ✅ 添加交易对: {symbol} (支持交易所: {exchanges})")
            return pair_id
        except sqlite3.IntegrityError:
            return False


def delete_trading_pair(username, pair_id):
    """删除交易对"""
    user_id = get_user_id(username)
    if not user_id:
        return False

    with db_pool.get_cursor() as (conn, c):
        c.execute("DELETE FROM trading_pairs WHERE id=? AND user_id=?", (pair_id, user_id))
        deleted = c.rowcount > 0

    if deleted:
        print(f"[{datetime.now().isoformat()}] ✅ 删除交易对 ID: {pair_id}")
    return deleted


def update_trading_pair(username, pair_id, symbol, display_name, exchanges=None):
    """更新交易对"""
    user_id = get_user_id(username)
    if not user_id:
        return False

    with db_pool.get_cursor() as (conn, c):
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
            
            if updated:
                print(f"[{datetime.now().isoformat()}] ✅ 更新交易对 ID {pair_id}: {symbol} ({display_name})")
            return updated
        except sqlite3.IntegrityError:
            return False


# API凭证管理功能
def get_user_credentials(username):
    """获取用户的所有API凭证列表(不返回secret)"""
    user_id = get_user_id(username)
    if not user_id:
        return []

    with db_pool.get_cursor() as (conn, c):
        c.execute("""SELECT id, alias, exchange, api_key, created_at, updated_at
                     FROM api_credentials WHERE user_id=? ORDER BY created_at DESC""", (user_id,))
        creds = c.fetchall()

    return [
        {
            'id': cr[0],
            'alias': cr[1],
            'exchange': cr[2],
            'api_key': decrypt_data(cr[3]),  # 解密后返回
            'created_at': cr[4],
            'updated_at': cr[5]
        }
        for cr in creds
    ]


def add_credential(username, alias, exchange, api_key, api_secret):
    """添加API凭证"""
    user_id = get_user_id(username)
    if not user_id:
        return False

    with db_pool.get_cursor() as (conn, c):
        try:
            encrypted_api_key = encrypt_data(api_key)
            encrypted_api_secret = encrypt_data(api_secret)
            now = datetime.now().isoformat()
            
            c.execute("""INSERT INTO api_credentials (user_id, alias, exchange, api_key, api_secret, created_at, updated_at)
                         VALUES (?, ?, ?, ?, ?, ?, ?)""",
                      (user_id, alias, exchange, encrypted_api_key, encrypted_api_secret, now, now))
            credential_id = c.lastrowid
            print(f"[{datetime.now().isoformat()}] ✅ 添加API凭证: {alias} ({exchange})")
            return credential_id
        except sqlite3.IntegrityError:
            return False


def delete_credential(username, credential_id):
    """删除API凭证"""
    user_id = get_user_id(username)
    if not user_id:
        return False

    with db_pool.get_cursor() as (conn, c):
        # 检查是否有配置在使用此凭证
        c.execute("SELECT COUNT(*) FROM user_configs WHERE credential_id=?", (credential_id,))
        count = c.fetchone()[0]
        if count > 0:
            print(f"[{datetime.now().isoformat()}] ❌ 无法删除凭证 ID {credential_id}: 有 {count} 个配置正在使用")
            return False
        
        c.execute("DELETE FROM api_credentials WHERE id=? AND user_id=?", (credential_id, user_id))
        deleted = c.rowcount > 0

    if deleted:
        print(f"[{datetime.now().isoformat()}] ✅ 删除API凭证 ID: {credential_id}")
        return {'success': True, 'message': f'API凭证删除成功 ID: {credential_id}'}
    return {'success': False, 'message': '删除失败'}


def update_credential(username, credential_id, alias, api_key=None, api_secret=None, exchange=None):
    """更新API凭证(可选择性更新key、secret和exchange)"""
    user_id = get_user_id(username)
    if not user_id:
        return False

    with db_pool.get_cursor() as (conn, c):
        try:
            now = datetime.now().isoformat()
            
            if api_key and api_secret:
                # 更新完整信息（包括可选的exchange）
                encrypted_api_key = encrypt_data(api_key)
                encrypted_api_secret = encrypt_data(api_secret)
                if exchange:
                    c.execute("""UPDATE api_credentials SET alias=?, exchange=?, api_key=?, api_secret=?, updated_at=?
                             WHERE id=? AND user_id=?""",
                              (alias, exchange, encrypted_api_key, encrypted_api_secret, now, credential_id, user_id))
                else:
                    c.execute("""UPDATE api_credentials SET alias=?, api_key=?, api_secret=?, updated_at=?
                             WHERE id=? AND user_id=?""",
                              (alias, encrypted_api_key, encrypted_api_secret, now, credential_id, user_id))
            elif exchange:
                # 更新别名和交易所
                c.execute("""UPDATE api_credentials SET alias=?, exchange=?, updated_at=?
                         WHERE id=? AND user_id=?""",
                          (alias, exchange, now, credential_id, user_id))
            else:
                # 只更新别名
                c.execute("""UPDATE api_credentials SET alias=?, updated_at=?
                         WHERE id=? AND user_id=?""",
                          (alias, now, credential_id, user_id))
        
            updated = c.rowcount > 0
            
            if updated:
                print(f"[{datetime.now().isoformat()}] ✅ 更新API凭证 ID {credential_id}: {alias}")
            return updated
        except sqlite3.IntegrityError:
            return False


def get_credential_by_id(user_id, credential_id):
    """根据ID获取凭证(包含解密后的key和secret)"""
    with db_pool.get_cursor() as (conn, c):
        c.execute("""SELECT alias, exchange, api_key, api_secret
                     FROM api_credentials WHERE id=? AND user_id=?""", (credential_id, user_id))
        result = c.fetchone()

    if not result:
        return None

    return {
        'alias': result[0],
        'exchange': result[1],
        'api_key': decrypt_data(result[2]),
        'api_secret': decrypt_data(result[3])
    }


# 系统配置管理功能
def get_system_config(username, config_key):
    """获取用户的系统配置值"""
    user_id = get_user_id(username)
    if not user_id:
        return None
        
    with db_pool.get_cursor() as (conn, c):
        c.execute("SELECT config_value FROM system_config WHERE user_id=? AND config_key=?", (user_id, config_key))
        result = c.fetchone()
        return result[0] if result else None


def set_system_config(username, config_key, config_value, description=None):
    """设置用户的系统配置值"""
    user_id = get_user_id(username)
    if not user_id:
        return False
        
    with db_pool.get_cursor() as (conn, c):
        now = datetime.now().isoformat()
        c.execute("SELECT id FROM system_config WHERE user_id=? AND config_key=?", (user_id, config_key))
        exists = c.fetchone()
        
        if exists:
            c.execute("""UPDATE system_config SET config_value=?, updated_at=? WHERE user_id=? AND config_key=?""",
                      (config_value, now, user_id, config_key))
        else:
            c.execute("""INSERT INTO system_config (user_id, config_key, config_value, description, created_at, updated_at)
                         VALUES (?, ?, ?, ?, ?, ?)""",
                      (user_id, config_key, config_value, description, now, now))
        
        print(f"[{now}] ✅ 系统配置已保存: {config_key} (user={username})")
        return True


def delete_system_config(username, config_key):
    """删除用户的系统配置"""
    user_id = get_user_id(username)
    if not user_id:
        return False
        
    with db_pool.get_cursor() as (conn, c):
        c.execute("DELETE FROM system_config WHERE user_id=? AND config_key=?", (user_id, config_key))
        deleted = c.rowcount > 0
        
    if deleted:
        print(f"[{datetime.now().isoformat()}] ✅ 系统配置已删除: {config_key} (user={username})")
    return deleted