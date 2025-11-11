import sys
import logging
from flask import Flask

from config import get_flask_secret_key,PORT
from database import init_db
from migrate_db import migrate_database
from routes import register_routes
from simple_logger import setup_logging

# 设置日志重定向（所有 print 输出会同时写入文件和控制台）
setup_logging(log_dir='logs', prefix='aresbot')

logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('binance').setLevel(logging.WARNING)

app = Flask(__name__)
app.secret_key = get_flask_secret_key()

# Session安全配置
app.config['SESSION_COOKIE_HTTPONLY'] = True  # 防止JavaScript访问cookie
app.config['SESSION_COOKIE_SECURE'] = False   # 生产环境应设为True(需要HTTPS)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax' # 防止CSRF攻击
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # session过期时间(秒)

register_routes(app)

if __name__ == '__main__':
    RECREATE_DB_ON_START = '--recreate-db' in sys.argv

    if len(sys.argv) == 1 or (len(sys.argv) == 2 and sys.argv[1] == '--recreate-db'):
        init_db(recreate=RECREATE_DB_ON_START)

        print("=" * 60)
        print("🔒 AresBot v3.0 - 启动中...")
        print("=" * 60)
        print("🌐 访问地址: http://localhost:"+str(PORT))
        print("👤 默认账户: admin / admin123")
        print("=" * 60)

        if RECREATE_DB_ON_START:
            print("✅ 数据库已重建（aresbot.db），包含 sell_offset_percent 与 simulate_trading 字段")
        else:
            print(f"ℹ️ 数据库 (aresbot.db) 已加载或创建，**旧数据被保留**。")
            print("ℹ️ 如需重建数据库，请在命令行中增加 '--recreate-db' 标志。")

        print("✅ 默认 simulate_trading = 1（模拟模式）")
        print("=" * 60)

        try:
            migrate_database()
        except Exception as e:
            print(f"\n❌ 迁移失败: {e}")
            print("请检查错误信息并重试")

    app.run(debug=False, host='0.0.0.0', port=PORT)
