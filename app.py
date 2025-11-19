import sys
import logging
import threading
import traceback
from datetime import datetime
from flask import Flask, jsonify

from config import get_flask_secret_key,PORT
from database import init_db
from migrate_db import migrate_database
from routes import register_routes
from simple_logger import setup_logging

# 设置日志重定向（所有 print 输出会同时写入文件和控制台）
setup_logging(log_dir='logs', prefix='aresbot')

# ========== 全局异常捕获（三层防护） ==========

# 1. 主进程未处理异常钩子
def global_exception_handler(exc_type, exc_value, exc_traceback):
    """捕获主线程的未处理异常"""
    if issubclass(exc_type, KeyboardInterrupt):
        # 用户手动 Ctrl+C，正常退出
        print(f"[{datetime.now().isoformat()}] ⚠️ 收到 KeyboardInterrupt，程序退出")
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    error_msg = f"[{datetime.now().isoformat()}] ❌ 主进程未处理异常:\n"
    error_msg += ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    print(error_msg)
    
    # 调用默认钩子（让程序正常退出）
    sys.__excepthook__(exc_type, exc_value, exc_traceback)

sys.excepthook = global_exception_handler

# 2. 线程未处理异常钩子（Python 3.8+）
def thread_exception_handler(args):
    """捕获所有线程内的未处理异常"""
    exc_type, exc_value, exc_traceback, thread = args
    error_msg = f"[{datetime.now().isoformat()}] ❌ 线程异常 (线程: {thread.name}):\n"
    error_msg += ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    print(error_msg)

threading.excepthook = thread_exception_handler

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

# 请求日志中间件
@app.before_request
def log_request():
    """记录所有请求路径"""
    from flask import request
    print(f"[{datetime.now().isoformat()}] 📥 {request.method} {request.path}")

# 3. Flask 路由全局异常处理器
@app.errorhandler(Exception)
def handle_exception(e):
    """捕获所有路由内的未处理异常（排除HTTP异常）"""
    from werkzeug.exceptions import HTTPException
    
    # 如果是HTTP异常（如404、405等），直接返回，不记录日志
    if isinstance(e, HTTPException):
        print(f"[{datetime.now().isoformat()}] ⚠️ HTTP {e.code}: {e.name}")
        return e
    
    # 只记录真正的服务器错误
    error_msg = f"[{datetime.now().isoformat()}] ❌ Flask 路由异常:\n"
    error_msg += traceback.format_exc()
    print(error_msg)
    
    # 返回 JSON 错误响应（避免暴露堆栈给前端）
    return jsonify({
        'success': False,
        'message': f'服务器内部错误: {type(e).__name__}'
    }), 500

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
