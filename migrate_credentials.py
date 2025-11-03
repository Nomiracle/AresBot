"""
数据迁移脚本: 将user_configs中的api_key和api_secret迁移到api_credentials表
"""
import sqlite3
from datetime import datetime
from config import DB_FILE
from crypto_utils import decrypt_data, encrypt_data

def migrate_credentials():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    print(f"[{datetime.now().isoformat()}] 开始迁移API凭证...")
    
    # 1. 检查user_configs表是否有api_key和api_secret列
    c.execute("PRAGMA table_info(user_configs)")
    columns = [col[1] for col in c.fetchall()]
    
    if 'api_key' not in columns or 'api_secret' not in columns:
        print(f"[{datetime.now().isoformat()}] user_configs表中没有api_key或api_secret列,无需迁移")
        conn.close()
        return
    
    # 2. 获取所有配置中的唯一api_key/api_secret组合
    c.execute("""
        SELECT DISTINCT user_id, exchange, api_key, api_secret 
        FROM user_configs 
        WHERE api_key IS NOT NULL AND api_secret IS NOT NULL 
        AND api_key != '' AND api_secret != ''
    """)
    configs = c.fetchall()
    
    print(f"[{datetime.now().isoformat()}] 找到 {len(configs)} 个需要迁移的配置")
    
    migrated_count = 0
    credential_map = {}  # 用于记录 (user_id, exchange, api_key) -> credential_id 的映射
    
    # 3. 为每个唯一的api_key/api_secret创建credential记录
    for user_id, exchange, encrypted_api_key, encrypted_api_secret in configs:
        if not encrypted_api_key or not encrypted_api_secret:
            continue
            
        try:
            # 解密以获取原始密钥(用于生成别名)
            api_key = decrypt_data(encrypted_api_key)
            
            # 生成唯一键用于去重
            unique_key = (user_id, exchange, encrypted_api_key)
            
            if unique_key in credential_map:
                # 已经迁移过这个密钥
                continue
            
            # 生成别名: 交易所名称 + 密钥前8位
            alias = f"{exchange.upper()}-{api_key[:8]}"
            
            # 检查别名是否已存在,如果存在则添加序号
            c.execute("SELECT COUNT(*) FROM api_credentials WHERE user_id=? AND alias LIKE ?", 
                     (user_id, f"{alias}%"))
            count = c.fetchone()[0]
            if count > 0:
                alias = f"{alias}-{count + 1}"
            
            # 插入到api_credentials表
            now = datetime.now().isoformat()
            c.execute("""
                INSERT INTO api_credentials 
                (user_id, alias, exchange, api_key, api_secret, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, alias, exchange, encrypted_api_key, encrypted_api_secret, now, now))
            
            credential_id = c.lastrowid
            credential_map[unique_key] = credential_id
            migrated_count += 1
            
            print(f"[{datetime.now().isoformat()}] ✓ 创建凭证: user_id={user_id}, alias={alias}, credential_id={credential_id}")
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ✗ 迁移失败: user_id={user_id}, exchange={exchange}, error={e}")
            continue
    
    print(f"[{datetime.now().isoformat()}] 成功创建 {migrated_count} 个API凭证")
    
    # 4. 更新user_configs表,设置credential_id
    c.execute("""
        SELECT id, user_id, exchange, api_key, api_secret 
        FROM user_configs 
        WHERE api_key IS NOT NULL AND api_secret IS NOT NULL
        AND api_key != '' AND api_secret != ''
    """)
    all_configs = c.fetchall()
    
    updated_count = 0
    for config_id, user_id, exchange, encrypted_api_key, encrypted_api_secret in all_configs:
        unique_key = (user_id, exchange, encrypted_api_key)
        if unique_key in credential_map:
            credential_id = credential_map[unique_key]
            c.execute("UPDATE user_configs SET credential_id=? WHERE id=?", 
                     (credential_id, config_id))
            updated_count += 1
    
    print(f"[{datetime.now().isoformat()}] 更新了 {updated_count} 个配置的credential_id")
    
    # 5. 创建新表(不包含api_key和api_secret列)
    print(f"[{datetime.now().isoformat()}] 重建user_configs表...")
    
    # 备份旧表
    c.execute("ALTER TABLE user_configs RENAME TO user_configs_backup")
    
    # 创建新表
    c.execute('''CREATE TABLE user_configs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  config_name TEXT NOT NULL DEFAULT 'default',
                  exchange TEXT NOT NULL DEFAULT 'binance',
                  credential_id INTEGER,
                  symbol TEXT NOT NULL,
                  offset_percent REAL NOT NULL,
                  sell_offset_percent REAL DEFAULT 0.5,
                  quantity REAL NOT NULL,
                  interval INTEGER NOT NULL,
                  testnet INTEGER DEFAULT 1,
                  simulate_trading INTEGER DEFAULT 1,
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY (user_id) REFERENCES users(id),
                  FOREIGN KEY (credential_id) REFERENCES api_credentials(id),
                  UNIQUE(user_id, config_name))''')
    
    # 复制数据到新表
    c.execute("""
        INSERT INTO user_configs 
        (id, user_id, config_name, exchange, credential_id, symbol, offset_percent, 
         sell_offset_percent, quantity, interval, testnet, simulate_trading, updated_at)
        SELECT id, user_id, config_name, exchange, credential_id, symbol, offset_percent,
               sell_offset_percent, quantity, interval, testnet, simulate_trading, updated_at
        FROM user_configs_backup
    """)
    
    # 删除备份表
    c.execute("DROP TABLE user_configs_backup")
    
    conn.commit()
    print(f"[{datetime.now().isoformat()}] ✅ 迁移完成! api_key和api_secret列已删除")
    
    # 6. 显示迁移结果统计
    c.execute("SELECT COUNT(*) FROM api_credentials")
    total_credentials = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM user_configs WHERE credential_id IS NOT NULL")
    configs_with_cred = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM user_configs WHERE credential_id IS NULL")
    configs_without_cred = c.fetchone()[0]
    
    print(f"\n迁移统计:")
    print(f"  - API凭证总数: {total_credentials}")
    print(f"  - 已关联凭证的配置: {configs_with_cred}")
    print(f"  - 未关联凭证的配置: {configs_without_cred}")
    
    if configs_without_cred > 0:
        print(f"\n⚠️  警告: 有 {configs_without_cred} 个配置没有关联API凭证,需要用户重新选择密钥")
    
    conn.close()

if __name__ == '__main__':
    try:
        migrate_credentials()
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] ❌ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
