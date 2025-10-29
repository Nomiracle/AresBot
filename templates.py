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
            <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
            <h3>🔑 账户安全</h3>
            <a href="/change_password" class="btn btn-warning" style="width: auto;">重置我的密码</a>
        </div>
    </div>

    <script>
        let currentTab = 'trading';

        function switchTab(tabName) {
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));

            document.getElementById(tabName + '-tab').classList.add('active');
            event.target.classList.add('active');
            currentTab = tabName;

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

        window.onload = function() {
            fetch('/api/config/load')
                .then(r => r.json())
                .then(data => {
                    if(data.success) {
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

CHANGE_PASSWORD_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>AresBot - 重置密码</title>
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
        .box {
            background: white;
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            width: 100%;
            max-width: 450px;
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
            margin-top: 10px;
        }
        .btn:hover { background: #5568d3; }
        .btn-secondary { background: #ccc; color: #333; }
        .btn-secondary:hover { background: #bbb; }
        .message {
            margin-bottom: 15px;
            padding: 10px;
            border-radius: 6px;
            text-align: center;
        }
        .success { background: #d4edda; color: #155724; }
        .error { background: #f8d7da; color: #721c24; }
    </style>
</head>
<body>
    <div class="box">
        <h1>🔑 重置密码 (用户: {{ username }})</h1>
        {% if message %}
        <div class="message {{ type }}">{{ message }}</div>
        {% endif %}
        <form method="POST">
            <div class="input-group">
                <label>旧密码</label>
                <input type="password" name="old_password" required>
            </div>
            <div class="input-group">
                <label>新密码</label>
                <input type="password" name="new_password" required>
            </div>
            <div class="input-group">
                <label>确认新密码</label>
                <input type="password" name="confirm_password" required>
            </div>
            <button type="submit" class="btn">提交修改</button>
        </form>
        <a href="/" class="btn btn-secondary">返回控制台</a>
    </div>
</body>
</html>
'''
