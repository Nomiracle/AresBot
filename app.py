import sys
import logging
from flask import Flask

from config import get_flask_secret_key
from database import init_db
from routes import register_routes

logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('binance').setLevel(logging.WARNING)

app = Flask(__name__)
app.secret_key = get_flask_secret_key()

register_routes(app)

if __name__ == '__main__':
    RECREATE_DB_ON_START = '--recreate-db' in sys.argv

    if len(sys.argv) == 1 or (len(sys.argv) == 2 and sys.argv[1] == '--recreate-db'):
        init_db(recreate=RECREATE_DB_ON_START)

        print("=" * 60)
        print("🔒 AresBot v3.0 - 启动中...")
        print("=" * 60)
        print("🌐 访问地址: http://localhost:5000")
        print("👤 默认账户: admin / admin123")
        print("=" * 60)

        if RECREATE_DB_ON_START:
            print("✅ 数据库已重建（aresbot.db），包含 sell_offset_percent 与 simulate_trading 字段")
        else:
            print(f"ℹ️ 数据库 (aresbot.db) 已加载或创建，**旧数据被保留**。")
            print("ℹ️ 如需重建数据库，请在命令行中增加 '--recreate-db' 标志。")

        print("✅ 默认 simulate_trading = 1（模拟模式）")
        print("=" * 60)

    app.run(debug=False, host='0.0.0.0', port=5000)
