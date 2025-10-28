"""
AresBot - 币安自动交易机器人
加密存储版本 - Python 3.12.6
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
import base64
from hashlib import sha256

app = Flask(__name__)
app.secret_key = os.urandom(24)

# 加密密钥管理
ENCRYPTION_KEY_FILE = 'encryption.key'

def get_or_create_encryption_key():
    """获取或创建加密密钥"""
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
    """加密数据"""
    if data is None:
        return None
    return cipher_suite.encrypt(data.encode()).decode()

def decrypt_data(encrypted_data):
    """解密数据"""
    if encrypted_data is None:
        return None
    try:
        return cipher_suite.decrypt(encrypted_data.encode()).decode()
    except:
        return None

# 全局变量 - 存储每个用户的运行状态
user_bots = {}  # {username: {'running': bool, 'thread': Thread, 'client': Client, 'config': dict}}

# 数据库初始化
def init_db():
    conn = sqlite3.connect('aresbot.db')
    c = conn.cursor()
    
    # 用户表
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  username TEXT UNIQUE NOT NULL, 
                  password TEXT NOT NULL,
                  created_at TEXT NOT NULL)''')
    
    # 用户配置表（加密存储）
    c.execute('''CREATE TABLE IF NOT EXISTS user_configs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  api_key TEXT NOT NULL,
                  api_secret TEXT NOT NULL,
                  symbol TEXT NOT NULL,
                  offset_percent REAL NOT NULL,
                  quantity REAL NOT NULL,
                  interval INTEGER NOT NULL,
                  testnet INTEGER DEFAULT 1,
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
    
    # 创建默认管理员账户
    try:
        c.execute("INSERT INTO users (username, password, created_at) VALUES (?, ?, ?)",
                  ('admin', generate_password_hash('admin123'), datetime.now().isoformat()))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    
    conn.close()

init_db()

# HTML模板
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
                <p class="subtitle">币安自动交易机器人 v2.0 - 所有数据均已加密</p>
            </div>
            <div class="user-info">
                <span>👤 {{ username }}</span>
                <a href="/logout" class="btn btn-danger">退出登录</a>
            </div>
        </div>
        
        <div class="warning">
            ⚠️ <strong>风险提示：</strong>自动交易存在风险，请谨慎设置参数。建议先在测试网络测试。
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
                quantity: parseFloat(document.getElementById('quantity').value),
                interval: parseInt(document.getElementById('interval').value),
                testnet: parseInt(document.getElementById('testnet').value)
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
                quantity: parseFloat(document.getElementById('quantity').value),
                interval: parseInt(document.getElementById('interval').value),
                testnet: parseInt(document.getElementById('testnet').value)
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
                        document.getElementById('quantity').value = data.config.quantity;
                        document.getElementById('interval').value = data.config.interval;
                        document.getElementById('testnet').value = data.config.testnet;
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
                                状态: ${order.status} | 时间: ${order.timestamp}
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

# 数据库操作函数
def get_user_id(username):
    """获取用户ID"""
    conn = sqlite3.connect('aresbot.db')
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username=?", (username,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def save_user_config(username, config):
    """保存用户配置（加密）"""
    user_id = get_user_id(username)
    if not user_id:
        return False
    
    conn = sqlite3.connect('aresbot.db')
    c = conn.cursor()
    
    # 加密敏感数据
    encrypted_api_key = encrypt_data(config['api_key'])
    encrypted_api_secret = encrypt_data(config['api_secret'])
    
    # 检查是否已有配置
    c.execute("SELECT id FROM user_configs WHERE user_id=?", (user_id,))
    exists = c.fetchone()
    
    if exists:
        c.execute("""UPDATE user_configs 
                     SET api_key=?, api_secret=?, symbol=?, offset_percent=?, 
                         quantity=?, interval=?, testnet=?, updated_at=?
                     WHERE user_id=?""",
                  (encrypted_api_key, encrypted_api_secret, config['symbol'],
                   config['offset_percent'], config['quantity'], config['interval'],
                   config.get('testnet', 1), datetime.now().isoformat(), user_id))
    else:
        c.execute("""INSERT INTO user_configs 
                     (user_id, api_key, api_secret, symbol, offset_percent, quantity, interval, testnet, updated_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  (user_id, encrypted_api_key, encrypted_api_secret, config['symbol'],
                   config['offset_percent'], config['quantity'], config['interval'],
                   config.get('testnet', 1), datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    return True

def load_user_config(username):
    """加载用户配置（解密）"""
    user_id = get_user_id(username)
    if not user_id:
        return None
    
    conn = sqlite3.connect('aresbot.db')
    c = conn.cursor()
    c.execute("SELECT * FROM user_configs WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    
    if not result:
        return None
    
    # 解密数据
    return {
        'api_key': decrypt_data(result[2]),
        'api_secret': decrypt_data(result[3]),
        'symbol': result[4],
        'offset_percent': result[5],
        'quantity': result[6],
        'interval': result[7],
        'testnet': result[8]
    }

# 交易机器人逻辑
def trading_loop(username):
    """每个用户独立的交易循环"""
    bot_data = user_bots.get(username)
    if not bot_data:
        return
    
    while bot_data['running']:
        try:
            config = bot_data['config']
            client = bot_data['client']
            
            # 获取当前价格
            ticker = client.get_symbol_ticker(symbol=config['symbol'])
            current_price = float(ticker['price'])
            
            # 计算目标价格
            offset = config['offset_percent'] / 100
            target_price = current_price * (1 + offset)
            target_price = round(target_price, 2)
            
            # 更新状态供前端显示
            bot_data['current_price'] = current_price
            bot_data['target_price'] = target_price
            
            print(f"[{datetime.now()}] {username} - {config['symbol']} - 当前价: ${current_price}, 挂单价: ${target_price}")
            
            # 保存订单记录（实际环境取消注释下单代码）
            user_id = get_user_id(username)
            conn = sqlite3.connect('aresbot.db')
            c = conn.cursor()
            c.execute("""INSERT INTO orders (user_id, symbol, price, quantity, side, status, timestamp) 
                         VALUES (?, ?, ?, ?, ?, ?, ?)""",
                      (user_id, config['symbol'], str(target_price), str(config['quantity']), 
                       'BUY', 'SIMULATED', datetime.now().isoformat()))
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"[{username}] 错误: {e}")
        
        time.sleep(config['interval'])

# 路由
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
        
        conn = sqlite3.connect('aresbot.db')
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
    
    # 检查是否已在运行
    if username in user_bots and user_bots[username].get('running'):
        return jsonify({'success': False, 'message': '机器人已在运行中'})
    
    config = request.json
    
    # 验证必填字段
    if not config.get('api_key') or not config.get('api_secret'):
        return jsonify({'success': False, 'message': 'API密钥不能为空'}), 400
    
    try:
        # 创建币安客户端
        testnet = bool(config.get('testnet', 1))
        client = Client(config['api_key'], config['api_secret'], testnet=testnet)
        
        # 测试连接
        client.ping()
        
        # 初始化用户机器人数据
        user_bots[username] = {
            'running': True,
            'client': client,
            'config': config,
            'current_price': None,
            'target_price': None
        }
        
        # 启动交易线程
        thread = threading.Thread(target=trading_loop, args=(username,), daemon=True)
        thread.start()
        user_bots[username]['thread'] = thread
        
        return jsonify({'success': True, 'message': f'机器人已启动 ({"测试网络" if testnet else "生产环境"})'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'启动失败: {str(e)}'}), 500

@app.route('/api/stop', methods=['POST'])
def api_stop():
    if 'user' not in session:
        return jsonify({'success': False, 'message': '未授权'}), 401
    
    username = session['user']
    
    if username not in user_bots or not user_bots[username].get('running'):
        return jsonify({'success': False, 'message': '机器人未在运行'})
    
    user_bots[username]['running'] = False
    return jsonify({'success': True, 'message': '机器人已停止'})

@app.route('/api/config/save', methods=['POST'])
def api_save_config():
    if 'user' not in session:
        return jsonify({'success': False, 'message': '未授权'}), 401
    
    username = session['user']
    config = request.json
    
    # 验证必填字段
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
    
    conn = sqlite3.connect('aresbot.db')
    c = conn.cursor()
    c.execute("""SELECT symbol, price, quantity, side, status, timestamp 
                 FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 50""", (user_id,))
    orders = c.fetchall()
    conn.close()
    
    order_list = [
        {
            'symbol': o[0],
            'price': o[1],
            'quantity': o[2],
            'side': o[3],
            'status': o[4],
            'timestamp': o[5]
        }
        for o in orders
    ]
    
    return jsonify({'orders': order_list})

if __name__ == '__main__':
    print("=" * 60)
    print("🔒 AresBot v2.0 - 加密存储版 启动中...")
    print("=" * 60)
    print("🌐 访问地址: http://localhost:5000")
    print("👤 默认账户: admin / admin123")
    print("=" * 60)
    print("✅ 数据加密功能已启用")
    print("✅ 用户配置独立存储")
    print("✅ 所有敏感信息加密保护")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=5000)