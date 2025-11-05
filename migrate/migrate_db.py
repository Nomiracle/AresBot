import sqlite3
from datetime import datetime
from config import DB_FILE

def migrate_database():
    """安全地迁移数据库，添加新表而不删除旧数据"""
    print("=" * 60)
    print("🔄 开始数据库迁移...")
    print("=" * 60)
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 检查 trading_pairs 表是否已存在
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trading_pairs'")
    table_exists = c.fetchone() is not None
    
    if table_exists:
        print("✅ trading_pairs 表已存在，跳过创建")
    else:
        print("📝 创建 trading_pairs 表...")
        c.execute('''CREATE TABLE IF NOT EXISTS trading_pairs
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER NOT NULL,
                      symbol TEXT NOT NULL,
                      display_name TEXT NOT NULL,
                      created_at TEXT NOT NULL,
                      FOREIGN KEY (user_id) REFERENCES users(id),
                      UNIQUE(user_id, symbol))''')
        print("✅ trading_pairs 表创建成功")
    
    # 为所有现有用户添加默认交易对
    c.execute("SELECT id, username FROM users")
    users = c.fetchall()
    
    default_pairs = [
        ('BTCUSDT', 'BTC/USDT'),
        ('ETHUSDT', 'ETH/USDT'),
        ('BNBUSDT', 'BNB/USDT'),
        ('ADAUSDT', 'ADA/USDT'),
        ('SOLUSDT', 'SOL/USDT')
    ]
    
    for user_id, username in users:
        print(f"\n👤 为用户 {username} (ID: {user_id}) 添加默认交易对...")
        added_count = 0
        
        for symbol, display_name in default_pairs:
            try:
                c.execute("INSERT INTO trading_pairs (user_id, symbol, display_name, created_at) VALUES (?, ?, ?, ?)",
                         (user_id, symbol, display_name, datetime.now().isoformat()))
                added_count += 1
            except sqlite3.IntegrityError:
                # 交易对已存在，跳过
                pass
        
        if added_count > 0:
            print(f"  ✅ 成功添加 {added_count} 个交易对")
        else:
            print(f"  ℹ️  交易对已存在，无需添加")
    
    conn.commit()
    conn.close()
    
    print("\n" + "=" * 60)
    print("✅ 数据库迁移完成！")
    print("=" * 60)
    print("📊 迁移摘要:")
    print(f"  • 保留了所有用户数据")
    print(f"  • 保留了所有配置数据")
    print(f"  • 保留了所有订单历史")
    print(f"  • 新增了交易对管理功能")
    print("=" * 60)

