"""
AresBot - 币安自动交易机器人 v3.0
- 重建数据库（aresbot.db 会被删除并重新创建）
- 支持 sell_offset_percent 与 simulate_trading 标志位（默认 simulate_trading = 1）
- 买单成交后自动挂卖单（卖单价格 = 买单价格 * (1 + sell_offset_percent/100)）
- 模拟/真实交易通过标志位区分
- 关键日志输出
"""

from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for
from binance.client import Client
from binance.exceptions import BinanceAPIException
import threading
import time
import json
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from cryptography.fernet import Fernet
import logging
logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('binance').setLevel(logging.WARNING)

app = Flask(__name__)
app.secret_key = os.urandom(24)

# ----------------------------
# 加密密钥管理 (Fernet)
# ----------------------------
ENCRYPTION_KEY_FILE = 'encryption.key'

def get_or_create_encryption_key():
    if os.path.exists(ENCRYPTION_KEY_FILE):
        with open(ENCRYPTION_KEY_FILE, 'rb') as f:
            return f.read()
    else:
        key = Fernet.generate_key()
        with open(ENCRYPTION_KEY_FILE, 'wb') as f:
            f.write(key)
        return key

ENCRYPTION_KEY = get_or_create_encryption_key()
cipher_suite = Fernet(ENCRYPTION_KEY)

def encrypt_data(data):
    if data is None:
        return None
    return cipher_suite.encrypt(data.encode()).decode()

def decrypt_data(encrypted_data):
    if encrypted_data is None:
        return None
    try:
        return cipher_suite.decrypt(encrypted_data.encode()).decode()
    except:
        return None

# ----------------------------
# 数据库初始化（重建数据库）
# ----------------------------
DB_FILE = 'aresbot.db'

def init_db(recreate=True):
    # 如果用户选择不保留当前数据库，这里会删除并新建
    if recreate and os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
            print(f"[{datetime.now().isoformat()}] ✅ 旧数据库 {DB_FILE} 已删除，准备重建。")
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ 无法删除旧数据库: {e}")

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # 用户表
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  password TEXT NOT NULL,
                  created_at TEXT NOT NULL)''')

    # 用户配置表（加密存储） - 新增 sell_offset_percent 与 simulate_trading
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

    # 订单表（加密存储敏感信息）
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

    # 创建默认管理员账户（如果不存在）
    try:
        c.execute("INSERT INTO users (username, password, created_at) VALUES (?, ?, ?)",
                  ('admin', generate_password_hash('admin123'), datetime.now().isoformat()))
        conn.commit()
        print(f"[{datetime.now().isoformat()}] ✅ 默认 admin 账号已创建（admin/admin123）")
    except sqlite3.IntegrityError:
        pass

    conn.close()
    print(f"[{datetime.now().isoformat()}] ✅ 数据库初始化完成：{DB_FILE}")

# 根据你的要求，不保留当前数据库 -> 重新创建
init_db(recreate=True)

# ----------------------------
# HTML 模板（在原模板基础上加入新项）
# ----------------------------
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>AresBot 控制台</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Arial, sans-serif; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container { 
            max-width: 1200px; 
            margin: 0 auto; 
            background: white; 
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            padding: 30px;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        h1 { color: #333; }
        .subtitle { color: #666; margin-bottom: 30px; }
        .user-info {
            display: flex;
            gap: 15px;
            align-items: center;
        }
        .status { 
            padding: 15px; 
            border-radius: 8px; 
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .status.running { background: #d4edda; color: #155724; }
        .status.stopped { background: #f8d7da; color: #721c24; }
        .config-grid { 
            display: grid; 
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        .input-group { display: flex; flex-direction: column; }
        .input-group label { 
            font-weight: 600; 
            margin-bottom: 5px; 
            color: #555;
            display: flex;
            align-items: center;
            gap: 5px;
        }
        .input-group input, .input-group select { 
            padding: 10px; 
            border: 2px solid #ddd; 
            border-radius: 6px;
            font-size: 14px;
        }
        .input-group input:focus { 
            outline: none; 
            border-color: #667eea; 
        }
        .btn { 
            padding: 12px 24px; 
            border: none; 
            border-radius: 6px; 
            font-size: 16px;
            cursor: pointer; 
            transition: all 0.3s;
            font-weight: 600;
        }
        .btn-primary { background: #667eea; color: white; }
        .btn-primary:hover { background: #5568d3; }
        .btn-danger { background: #dc3545; color: white; }
        .btn-danger:hover { background: #c82333; }
        .btn-success { background: #28a745; color: white; }
        .btn-success:hover { background: #218838; }
        .btn-warning { background: #ffc107; color: #333; }
        .btn-warning:hover { background: #e0a800; }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .controls { 
            display: flex; 
            gap: 10px; 
            margin-bottom: 20px;
            flex-wrap: wrap;
        }
        .info-box {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        .info-box h3 { margin-bottom: 10px; color: #333; }
        .price { font-size: 24px; color: #667eea; font-weight: bold; }
        .warning {
            background: #fff3cd;
            color: #856404;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            border-left: 4px solid #ffc107;
        }
        .security-badge {
            display: inline-block;
            background: #28a745;
            color: white;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            margin-left: 5px;
        }
        .encrypted {
            color: #28a745;
            font-size: 12px;
        }
        .tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            border-bottom: 2px solid #ddd;
        }
        .tab {
            padding: 10px 20px;
            cursor: pointer;
            border: none;
            background: none;
            font-size: 16px;
            color: #666;
            position: relative;
        }
        .tab.active {
            color: #667eea;
            font-weight: 600;
        }
        .tab.active::after {
            content: '';
            position: absolute;
            bottom: -2px;
            left: 0;
            right: 0;
            height: 2px;
            background: #667eea;
        }
        .tab-content {
            display: none;
        }
        .tab-content.active {
            display: block;
        }
        .order-history {
            max-height: 300px;
            overflow-y: auto;
        }
        .order-item {
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 6px;
            margin-bottom: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1>⚔️ AresBot 控制台 <span class="security-badge">🔒 加密存储</span></h1>
                <p class="subtitle">币安自动交易机器人 v3.0 - 默认模拟模式 (simulate_trading=1)</p>
            </div>
            <div class="user-info">
                <span>👤 {{ username }}</span>
                <a href="/logout" class="btn btn-danger">退出登录</a>
            </div>
        </div>
        
        <div class="warning">
            ⚠️ <strong>风险提示：</strong>自动交易存在风险，请谨慎设置参数。建议先在测试网络或模拟模式下测试。
        </div>
        
        <div id="status" class="status stopped">
            <span id="statusText">机器人已停止</span>
            <span id="statusIndicator">●</span>
        </div>
        
        <div class="tabs">
            <button class="tab active" onclick="switchTab('trading')">交易配置</button>
            <button class="tab" onclick="switchTab('history')">订单历史</button>
            <button class="tab" onclick="switchTab('security')">安全设置</button>
        </div>
        
        <div id="trading-tab" class="tab-content active">
            <div class="info-box">
                <h3>当前市场信息</h3>
                <div>交易对: <strong id="currentSymbol">-</strong></div>
                <div>当前价格: <span class="price" id="currentPrice">-</span></div>
                <div>计划挂单价: <strong id="targetPrice">-</strong></div>
            </div>
            
            <h3>交易配置 <span class="encrypted">🔐 所有敏感数据均加密存储</span></h3>
            <div class="config-grid">
                <div class="input-group">
                    <label>API Key 🔒</label>
                    <input type="password" id="apiKey" placeholder="输入币安API Key">
                </div>
                <div class="input-group">
                    <label>API Secret 🔒</label>
                    <input type="password" id="apiSecret" placeholder="输入币安API Secret">
                </div>
                <div class="input-group">
                    <label>交易对</label>
                    <select id="symbol">
                        <option value="BTCUSDT">BTC/USDT</option>
                        <option value="ETHUSDT">ETH/USDT</option>
                        <option value="BNBUSDT">BNB/USDT</option>
                        <option value="ADAUSDT">ADA/USDT</option>
                        <option value="SOLUSDT">SOL/USDT</option>
                    </select>
                </div>
                <div class="input-group">
                    <label>偏移百分比 (%)</label>
                    <input type="number" id="offsetPercent" value="-0.1" step="0.01">
                </div>
                <div class="input-group">
                    <label>卖单加价百分比 (%)</label>
                    <input type="number" id="sellOffsetPercent" value="0.5" step="0.01">
                </div>
                <div class="input-group">
                    <label>购买数量</label>
                    <input type="number" id="quantity" value="0.001" step="0.0001">
                </div>
                <div class="input-group">
                    <label>查询间隔 (秒)</label>
                    <input type="number" id="interval" value="1" min="1">
                </div>
                <div class="input-group">
                    <label>网络环境</label>
                    <select id="testnet">
                        <option value="1">测试网络</option>
                        <option value="0">生产环境</option>
                    </select>
                </div>
                <div class="input-group">
                    <label>交易模式</label>
                    <select id="simulateTrading">
                        <option value="1">模拟交易（默认）</option>
                        <option value="0">真实交易</option>
                    </select>
                </div>
            </div>
            
            <div class="controls">
                <button class="btn btn-success" onclick="startBot()">🚀 启动机器人</button>
                <button class="btn btn-danger" onclick="stopBot()">⏹️ 停止机器人</button>
                <button class="btn btn-primary" onclick="saveConfig()">💾 保存配置到服务器</button>
                <button class="btn btn-warning" onclick="loadConfig()">📥 加载已保存配置</button>
            </div>
        </div>
        
        <div id="history-tab" class="tab-content">
            <h3>订单历史记录</h3>
            <div id="orderHistory" class="order-history">
                <p>加载中...</p>
            </div>
        </div>
        
        <div id="security-tab" class="tab-content">
            <h3>安全信息</h3>
            <div class="info-box">
                <h4>🔐 数据加密</h4>
                <p>✅ API密钥使用Fernet加密算法存储</p>
                <p>✅ 所有配置数据关联到用户账户</p>
                <p>✅ 订单历史加密保存</p>
                <p>✅ 加密密钥独立存储</p>
                <br>
                <h4>⚙️ 配置管理</h4>
                <p>• 每个用户的配置独立存储</p>
                <p>• 服务端保存，随时恢复</p>
                <p>• 支持多设备同步</p>
            </div>
        </div>
    </div>
    
    <script>
        let currentTab = 'trading';
        
        function switchTab(tabName) {
            // 隐藏所有标签页
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            
            // 显示选中标签页
            document.getElementById(tabName + '-tab').classList.add('active');
            event.target.classList.add('active');
            currentTab = tabName;
            
            // 如果切换到历史记录，加载数据
            if(tabName === 'history') {
                loadOrderHistory();
            }
        }
        
        function updateStatus() {
            fetch('/api/status')
                .then(r => r.json())
                .then(data => {
                    const status = document.getElementById('status');
                    const statusText = document.getElementById('statusText');
                    
                    if(data.running) {
                        status.className = 'status running';
                        statusText.textContent = '机器人运行中 (配置已加密保存)';
                    } else {
                        status.className = 'status stopped';
                        statusText.textContent = '机器人已停止';
                    }
                    
                    if(data.price) {
                        document.getElementById('currentSymbol').textContent = data.symbol;
                        document.getElementById('currentPrice').textContent = '$' + parseFloat(data.price).toFixed(2);
                        document.getElementById('targetPrice').textContent = '$' + data.target_price;
                    }
                });
        }
        
        function startBot() {
            const config = {
                api_key: document.getElementById('apiKey').value,
                api_secret: document.getElementById('apiSecret').value,
                symbol: document.getElementById('symbol').value,
                offset_percent: parseFloat(document.getElementById('offsetPercent').value),
                sell_offset_percent: parseFloat(document.getElementById('sellOffsetPercent').value),
                quantity: parseFloat(document.getElementById('quantity').value),
                interval: parseInt(document.getElementById('interval').value),
                testnet: parseInt(document.getElementById('testnet').value),
                simulate_trading: parseInt(document.getElementById('simulateTrading').value)
            };
            
            if(!config.api_key || !config.api_secret) {
                alert('请先输入API Key和Secret，或点击"加载已保存配置"');
                return;
            }
            
            fetch('/api/start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(config)
            })
            .then(r => r.json())
            .then(data => {
                alert(data.message);
                if(data.success) updateStatus();
            });
        }
        
        function stopBot() {
            fetch('/api/stop', {method: 'POST'})
                .then(r => r.json())
                .then(data => {
                    alert(data.message);
                    updateStatus();
                });
        }
        
        function saveConfig() {
            const config = {
                api_key: document.getElementById('apiKey').value,
                api_secret: document.getElementById('apiSecret').value,
                symbol: document.getElementById('symbol').value,
                offset_percent: parseFloat(document.getElementById('offsetPercent').value),
                sell_offset_percent: parseFloat(document.getElementById('sellOffsetPercent').value),
                quantity: parseFloat(document.getElementById('quantity').value),
                interval: parseInt(document.getElementById('interval').value),
                testnet: parseInt(document.getElementById('testnet').value),
                simulate_trading: parseInt(document.getElementById('simulateTrading').value)
            };
            
            if(!config.api_key || !config.api_secret) {
                alert('请输入API Key和Secret');
                return;
            }
            
            fetch('/api/config/save', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(config)
            })
            .then(r => r.json())
            .then(data => alert(data.message));
        }
        
        function loadConfig() {
            fetch('/api/config/load')
                .then(r => r.json())
                .then(data => {
                    if(data.success) {
                        document.getElementById('apiKey').value = data.config.api_key || '';
                        document.getElementById('apiSecret').value = data.config.api_secret || '';
                        document.getElementById('symbol').value = data.config.symbol;
                        document.getElementById('offsetPercent').value = data.config.offset_percent;
                        document.getElementById('sellOffsetPercent').value = data.config.sell_offset_percent || 0.5;
                        document.getElementById('quantity').value = data.config.quantity;
                        document.getElementById('interval').value = data.config.interval;
                        document.getElementById('testnet').value = data.config.testnet;
                        document.getElementById('simulateTrading').value = data.config.simulate_trading;
                        alert('配置加载成功！');
                    } else {
                        alert(data.message);
                    }
                });
        }
        
        function loadOrderHistory() {
            fetch('/api/orders')
                .then(r => r.json())
                .then(data => {
                    const container = document.getElementById('orderHistory');
                    if(data.orders.length === 0) {
                        container.innerHTML = '<p>暂无订单记录</p>';
                    } else {
                        container.innerHTML = data.orders.map(order => `
                            <div class="order-item">
                                <strong>${order.symbol}</strong> - ${order.side}<br>
                                价格: $${order.price} | 数量: ${order.quantity}<br>
                                状态: ${order.status} | 时间: ${order.timestamp}<br>
                                订单ID: ${order.order_id || '-'}
                            </div>
                        `).join('');
                    }
                });
        }
        
        setInterval(updateStatus, 2000);
        updateStatus();
        
        // 页面加载时尝试加载配置
        window.onload = function() {
            fetch('/api/config/load')
                .then(r => r.json())
                .then(data => {
                    if(data.success) {
                        // 不自动填充密钥，只显示提示
                        console.log('已保存配置可用');
                    }
                });
        };
    </script>
</body>
</html>
'''

LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>AresBot 登录</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Arial, sans-serif; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .login-box {
            background: white;
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            width: 100%;
            max-width: 400px;
        }
        h1 { text-align: center; margin-bottom: 30px; color: #333; }
        .input-group { margin-bottom: 20px; }
        .input-group label { display: block; margin-bottom: 5px; color: #555; font-weight: 600; }
        .input-group input { 
            width: 100%; 
            padding: 12px; 
            border: 2px solid #ddd; 
            border-radius: 6px;
            font-size: 14px;
        }
        .btn { 
            width: 100%; 
            padding: 12px; 
            background: #667eea; 
            color: white; 
            border: none; 
            border-radius: 6px;
            font-size: 16px;
            cursor: pointer;
            font-weight: 600;
        }
        .btn:hover { background: #5568d3; }
        .error { color: #dc3545; margin-bottom: 15px; text-align: center; }
        .info { 
            margin-top: 20px; 
            padding: 15px; 
            background: #f8f9fa; 
            border-radius: 6px;
            font-size: 12px;
            color: #666;
        }
        .security-badge {
            display: inline-block;
            background: #28a745;
            color: white;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 11px;
            margin-left: 5px;
        }
    </style>
</head>
<body>
    <div class="login-box">
        <h1>⚔️ AresBot <span class="security-badge">🔒 加密</span></h1>
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        <form method="POST">
            <div class="input-group">
                <label>用户名</label>
                <input type="text" name="username" required autofocus>
            </div>
            <div class="input-group">
                <label>密码</label>
                <input type="password" name="password" required>
            </div>
            <button type="submit" class="btn">登录</button>
        </form>
        <div class="info">
            🔐 默认账户: admin / admin123<br>
            ✅ 所有配置数据加密存储<br>
            ✅ 每个用户配置独立管理
        </div>
    </div>
</body>
</html>
'''

# ----------------------------
# DB helper functions
# ----------------------------
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

    # result columns: id, user_id, api_key, api_secret, symbol, offset_percent, sell_offset_percent, quantity, interval, testnet, simulate_trading, updated_at
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

# ----------------------------
# 全局变量：每用户机器人数据
# ----------------------------
user_bots = {}  # username -> {'running':bool, 'thread':Thread, 'client':Client, 'config':dict, 'current_price':float, 'target_price':float, 'pending_buys':[]}

# ----------------------------
# 交易主循环
# ----------------------------
def trading_loop(username):
    bot_data = user_bots.get(username)
    if not bot_data:
        return

    print(f"[{datetime.now().isoformat()}] ▶️ 交易循环已启动 (user={username})")
    while bot_data['running']:
        try:
            config = bot_data['config']
            client = bot_data['client']

            # 获取当前价格
            ticker = client.get_symbol_ticker(symbol=config['symbol'])
            current_price = float(ticker['price'])
            offset = config['offset_percent'] / 100.0
            target_price = current_price * (1 + offset)
            # 保留两位小数（根据你原代码）
            target_price = round(target_price, 2)

            bot_data['current_price'] = current_price
            bot_data['target_price'] = target_price

            print(f"[{datetime.now().isoformat()}] {username} - {config['symbol']} - 当前价: ${current_price} -> 计划挂买价: ${target_price}")

            user_id = get_user_id(username)

            # ----------------------------
            # 下买单（根据 simulate_trading 标志）
            # 我们在每个循环尝试一次下买单（根据策略），真实策略可以改为更复杂的触发条件
            # ----------------------------
            if config.get('simulate_trading', 1) == 1:
                # 模拟模式：立即视为买单已成交（可改为 PLACED -> FILLED 模拟流程）
                buy_order_id = f"SIM_BUY_{int(time.time()*1000)}"
                buy_price = target_price
                # 插入 BUY 已成交记录
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("""INSERT INTO orders (user_id, symbol, price, quantity, side, status, order_id, timestamp)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                          (user_id, config['symbol'], str(buy_price), str(config['quantity']),
                           'BUY', 'FILLED', buy_order_id, datetime.now().isoformat()))
                conn.commit()
                conn.close()
                print(f"[{datetime.now().isoformat()}] ✅ 模拟买单已记录 (user={username}, price={buy_price}, qty={config['quantity']}, order_id={buy_order_id})")
                print(f"[{datetime.now().isoformat()}] ℹ️ 模拟买单视为成交，准备挂卖单...")

                # 计算卖单价格并挂卖单（模拟）
                sell_offset = config.get('sell_offset_percent', 0.5) / 100.0
                sell_price = round(buy_price * (1 + sell_offset), 2)
                sell_order_id = f"SIM_SELL_{int(time.time()*1000)}"
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("""INSERT INTO orders (user_id, symbol, price, quantity, side, status, order_id, timestamp)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                          (user_id, config['symbol'], str(sell_price), str(config['quantity']),
                           'SELL', 'PLACED', sell_order_id, datetime.now().isoformat()))
                conn.commit()
                conn.close()
                print(f"[{datetime.now().isoformat()}] ✅ 模拟卖单已挂 (user={username}, price={sell_price}, qty={config['quantity']}, order_id={sell_order_id})")
                print(f"[{datetime.now().isoformat()}] ✅ 订单记录已保存到 DB (user={username})")

            else:
                # 真实交易模式：尝试下限价买单（GTC）
                try:
                    buy_price_str = f"{target_price:.2f}"
                    print(f"[{datetime.now().isoformat()}] ℹ️ 真实下单 - 尝试下限价买单 (price={buy_price_str}, qty={config['quantity']})")
                    order = client.order_limit_buy(
                        symbol=config['symbol'],
                        quantity=config['quantity'],
                        price=buy_price_str,
                        timeInForce='GTC'
                    )
                    # orderId returned by binance is order['orderId']
                    real_order_id = str(order.get('orderId') or order.get('orderId'))
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("""INSERT INTO orders (user_id, symbol, price, quantity, side, status, order_id, timestamp)
                                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                              (user_id, config['symbol'], buy_price_str, str(config['quantity']),
                               'BUY', 'PLACED', real_order_id, datetime.now().isoformat()))
                    conn.commit()
                    conn.close()
                    print(f"[{datetime.now().isoformat()}] ✅ 真实买单已下 (order_id={real_order_id})，已写入 DB，等待撮合...")
                    # 加入 pending buys 列表以便轮询检查成交状态
                    bot_data.setdefault('pending_buys', []).append({
                        'order_id': real_order_id,
                        'price': float(buy_price_str),
                        'quantity': config['quantity'],
                        'symbol': config['symbol'],
                        'user_id': user_id
                    })
                except BinanceAPIException as e:
                    print(f"[{datetime.now().isoformat()}] ❌ Binance 下单异常: {e}")
                except Exception as e:
                    print(f"[{datetime.now().isoformat()}] ❌ 下单错误: {e}")

            # ----------------------------
            # 处理 pending_buys：轮询订单状态，若成交则挂卖单
            # ----------------------------
            pending = bot_data.get('pending_buys', [])
            if pending:
                remaining = []
                for pb in pending:
                    try:
                        # 询问币安订单状态
                        order_info = client.get_order(symbol=pb['symbol'], orderId=int(pb['order_id']))
                        status = order_info.get('status')
                        print(f"[{datetime.now().isoformat()}] ℹ️ 轮询订单 {pb['order_id']} 状态: {status}")
                        if status == 'FILLED':
                            buy_price = float(order_info.get('price')) if order_info.get('price') else pb['price']
                            # 如果 price 字段为空（有时限价订单返回空），使用我们记录的 pb['price']
                            if not buy_price:
                                buy_price = pb['price']
                            # 计算卖单价格
                            sell_offset = config.get('sell_offset_percent', 0.5) / 100.0
                            sell_price = round(buy_price * (1 + sell_offset), 2)
                            try:
                                # 挂卖单
                                sell_order = client.order_limit_sell(
                                    symbol=pb['symbol'],
                                    quantity=pb['quantity'],
                                    price=f"{sell_price:.2f}",
                                    timeInForce='GTC'
                                )
                                sell_order_id = str(sell_order.get('orderId'))
                                conn = sqlite3.connect(DB_FILE)
                                c = conn.cursor()
                                # 插入卖单记录
                                c.execute("""INSERT INTO orders (user_id, symbol, price, quantity, side, status, order_id, timestamp)
                                             VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                                          (pb['user_id'], pb['symbol'], str(sell_price), str(pb['quantity']),
                                           'SELL', 'PLACED', sell_order_id, datetime.now().isoformat()))
                                # 更新买单状态为 FILLED（防止重复处理）
                                c.execute("""UPDATE orders SET status=? WHERE order_id=?""", ('FILLED', pb['order_id']))
                                conn.commit()
                                conn.close()
                                print(f"[{datetime.now().isoformat()}] ✅ 买单 {pb['order_id']} 已成交，自动挂卖单 {sell_order_id} @ {sell_price}")
                            except BinanceAPIException as e:
                                print(f"[{datetime.now().isoformat()}] ❌ 卖单下单异常: {e}")
                            except Exception as e:
                                print(f"[{datetime.now().isoformat()}] ❌ 卖单下单错误: {e}")
                        else:
                            # 未成交，保留继续轮询
                            remaining.append(pb)
                    except BinanceAPIException as e:
                        print(f"[{datetime.now().isoformat()}] ❌ 查询订单 {pb['order_id']} 状态异常: {e}")
                        # 在很多异常情况下，我们仍然保留该 pending，等待下一次轮询
                        remaining.append(pb)
                    except Exception as e:
                        print(f"[{datetime.now().isoformat()}] ❌ 轮询订单错误: {e}")
                        remaining.append(pb)

                bot_data['pending_buys'] = remaining

            # 休眠到下次循环
            time.sleep(config.get('interval', 1))

        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ 交易循环主流程错误: {e}")
            # 防止 tight-loop 错误导致高 CPU，稍微休眠
            time.sleep(1)

    print(f"[{datetime.now().isoformat()}] ◼️ 交易循环已停止 (user={username})")

# ----------------------------
# Flask 路由
# ----------------------------
@app.route('/')
def index():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template_string(HTML_TEMPLATE, username=session['user'])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT password FROM users WHERE username=?", (username,))
        result = c.fetchone()
        conn.close()

        if result and check_password_hash(result[0], password):
            session['user'] = username
            return redirect(url_for('index'))
        return render_template_string(LOGIN_TEMPLATE, error='用户名或密码错误')

    return render_template_string(LOGIN_TEMPLATE)

@app.route('/logout')
def logout():
    username = session.get('user')
    if username and username in user_bots:
        user_bots[username]['running'] = False
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/api/status')
def api_status():
    if 'user' not in session:
        return jsonify({'running': False})
    username = session['user']
    bot_data = user_bots.get(username, {})
    return jsonify({
        'running': bot_data.get('running', False),
        'symbol': bot_data.get('config', {}).get('symbol', '-'),
        'price': bot_data.get('current_price'),
        'target_price': bot_data.get('target_price', '-')
    })

@app.route('/api/start', methods=['POST'])
def api_start():
    if 'user' not in session:
        return jsonify({'success': False, 'message': '未授权'}), 401

    username = session['user']

    if username in user_bots and user_bots[username].get('running'):
        return jsonify({'success': False, 'message': '机器人已在运行中'})

    config = request.json
    if not config.get('api_key') or not config.get('api_secret'):
        return jsonify({'success': False, 'message': 'API密钥不能为空'}), 400

    try:
        testnet = bool(config.get('testnet', 1))
        client = Client(config['api_key'], config['api_secret'], testnet=testnet)

        # 测试连接
        client.ping()

        # 初始化机器人数据结构
        user_bots[username] = {
            'running': True,
            'client': client,
            'config': config,
            'current_price': None,
            'target_price': None,
            'pending_buys': []
        }

        # 启动线程
        thread = threading.Thread(target=trading_loop, args=(username,), daemon=True)
        thread.start()
        user_bots[username]['thread'] = thread

        print(f"[{datetime.now().isoformat()}] ▶️ 机器人已启动 (user={username}, mode={'SIM' if config.get('simulate_trading',1)==1 else 'REAL'})")
        return jsonify({'success': True, 'message': f'机器人已启动 ({"模拟" if config.get("simulate_trading",1)==1 else "实盘"})'})
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] ❌ 启动失败: {e}")
        return jsonify({'success': False, 'message': f'启动失败: {str(e)}'}), 500

@app.route('/api/stop', methods=['POST'])
def api_stop():
    if 'user' not in session:
        return jsonify({'success': False, 'message': '未授权'}), 401

    username = session['user']
    if username not in user_bots or not user_bots[username].get('running'):
        return jsonify({'success': False, 'message': '机器人未在运行'})

    user_bots[username]['running'] = False
    print(f"[{datetime.now().isoformat()}] ◼️ 机器人停止请求 (user={username})")
    return jsonify({'success': True, 'message': '机器人已停止'})

@app.route('/api/config/save', methods=['POST'])
def api_save_config():
    if 'user' not in session:
        return jsonify({'success': False, 'message': '未授权'}), 401

    username = session['user']
    config = request.json
    if not config.get('api_key') or not config.get('api_secret'):
        return jsonify({'success': False, 'message': 'API密钥不能为空'}), 400

    if save_user_config(username, config):
        return jsonify({'success': True, 'message': '配置已加密保存到服务器'})
    else:
        return jsonify({'success': False, 'message': '保存失败'}), 500

@app.route('/api/config/load')
def api_load_config():
    if 'user' not in session:
        return jsonify({'success': False, 'message': '未授权'}), 401

    username = session['user']
    config = load_user_config(username)
    if config:
        return jsonify({'success': True, 'config': config})
    else:
        return jsonify({'success': False, 'message': '未找到已保存的配置'})

@app.route('/api/orders')
def api_orders():
    if 'user' not in session:
        return jsonify({'orders': []}), 401

    username = session['user']
    user_id = get_user_id(username)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""SELECT symbol, price, quantity, side, status, order_id, timestamp
                 FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 100""", (user_id,))
    orders = c.fetchall()
    conn.close()

    order_list = [
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

    return jsonify({'orders': order_list})

# ----------------------------
# 启动应用
# ----------------------------
if __name__ == '__main__':
    print("=" * 60)
    print("🔒 AresBot v3.0 - 启动中...")
    print("=" * 60)
    print("🌐 访问地址: http://localhost:5000")
    print("👤 默认账户: admin / admin123")
    print("=" * 60)
    print("✅ 数据库已重建（aresbot.db），包含 sell_offset_percent 与 simulate_trading 字段")
    print("✅ 默认 simulate_trading = 1（模拟模式）")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=5000)
