import sqlite3
import threading
from datetime import datetime, timedelta
from flask import request, jsonify, session, redirect, url_for, render_template
from werkzeug.security import check_password_hash, generate_password_hash
from exchanges.factory import ExchangeFactory

from config import DB_FILE
from database import (save_user_config, load_user_config, get_user_orders, get_user_id,
                     get_user_trading_pairs, add_trading_pair, delete_trading_pair, 
                     update_trading_pair)

from trading import trading_loop, user_bots


def register_routes(app):
    @app.route('/')
    def index():
        if 'user' not in session:
            return redirect(url_for('login'))
        return render_template('index.html', username=session['user'])

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            # 登录尝试表
            c.execute("CREATE TABLE IF NOT EXISTS login_attempts (username TEXT PRIMARY KEY, attempts INTEGER DEFAULT 0, blocked_until INTEGER)")
            # 读取封禁状态
            c.execute("SELECT attempts, blocked_until FROM login_attempts WHERE username=?", (username,))
            row = c.fetchone()
            attempts = row[0] if row else 0
            blocked_until = row[1] if row else None

            now_ts = int(datetime.utcnow().timestamp())
            if blocked_until and blocked_until > now_ts:
                # 仍在封禁期
                remaining = blocked_until - now_ts
                minutes = max(1, remaining // 60)
                conn.close()
                return render_template('login.html', error=f'尝试次数过多，请在 {minutes} 分钟后再试')

            # 正常验证用户
            c.execute("SELECT password FROM users WHERE username=?", (username,))
            result = c.fetchone()

            if result and check_password_hash(result[0], password):
                # 登录成功：清除尝试计数与封禁
                if row:
                    c.execute("UPDATE login_attempts SET attempts=0, blocked_until=NULL WHERE username=?", (username,))
                else:
                    c.execute("INSERT OR REPLACE INTO login_attempts(username, attempts, blocked_until) VALUES(?, 0, NULL)", (username,))
                conn.commit()
                conn.close()
                session['user'] = username
                return redirect(url_for('index'))

            # 登录失败：增加计数，达到3次则封禁10分钟
            attempts = attempts + 1
            if attempts >= 3:
                unblock_ts = int((datetime.utcnow() + timedelta(minutes=10)).timestamp())
                c.execute("INSERT OR REPLACE INTO login_attempts(username, attempts, blocked_until) VALUES(?, ?, ?)", (username, 0, unblock_ts))
                conn.commit()
                conn.close()
                return render_template('login.html', error='连续失败过多，已锁定 10 分钟')
            else:
                if row:
                    c.execute("UPDATE login_attempts SET attempts=? WHERE username=?", (attempts, username))
                else:
                    c.execute("INSERT INTO login_attempts(username, attempts, blocked_until) VALUES(?, ?, NULL)", (username, attempts))
                conn.commit()
                conn.close()
                return render_template('login.html', error='用户名或密码错误')

        return render_template('login.html')
    
    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')

            error = None
            if not username or not password:
                error = '用户名和密码不能为空'
            elif len(username) < 3:
                error = '用户名长度至少需要3位'
            elif len(password) < 6:
                error = '密码长度至少需要6位'
            elif password != confirm_password:
                error = '两次输入的密码不一致'

            if error:
                return render_template('register.html', error=error)

            try:
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                # 与 database.init_db 保持一致的 users 表结构（包含 created_at 非空列）
                c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, created_at TEXT NOT NULL)")
                # 用户数量限制：最多100个
                c.execute("SELECT COUNT(*) FROM users")
                row = c.fetchone()
                total_users = (row[0] if row else 0)
                if total_users >= 100:
                    conn.close()
                    return render_template('register.html', error='注册人数已达上限 (100)')
                # 检查是否已存在
                c.execute("SELECT id FROM users WHERE username=?", (username,))
                if c.fetchone():
                    conn.close()
                    return render_template('register.html', error='用户名已存在')

                hashed = generate_password_hash(password)
                from datetime import datetime
                c.execute("INSERT INTO users(username, password, created_at) VALUES(?, ?, ?)", (username, hashed, datetime.now().isoformat()))
                conn.commit()
                conn.close()

                session['user'] = username
                return redirect(url_for('index'))
            except Exception as e:
                try:
                    conn.close()
                except Exception:
                    pass
                return render_template('register.html', error='注册失败: ' + str(e))

        return render_template('register.html')
            

    @app.route('/logout')
    def logout():
        username = session.get('user')
        if username and username in user_bots:
            user_data = user_bots.get(username, {})
            bots = user_data.get('bots', {}) if isinstance(user_data, dict) else {}
            for b in bots.values():
                b['running'] = False
        session.pop('user', None)
        return redirect(url_for('login'))

    @app.route('/api/status')
    def api_status():
        if 'user' not in session:
            return jsonify({'running': False})
        username = session['user']
        user_data = user_bots.get(username, {})
        running = False
        symbol = '-'
        price = None
        target_price = '-'
        if isinstance(user_data, dict):
            for sym, b in user_data.get('bots', {}).items():
                if b.get('running'):
                    running = True
                    symbol = sym
                    price = b.get('current_price')
                    target_price = b.get('target_price', '-')
                    break
        return jsonify({'running': running, 'symbol': symbol, 'price': price, 'target_price': target_price})

    @app.route('/api/start', methods=['POST'])
    def api_start():
        if 'user' not in session:
            return jsonify({'success': False, 'message': '未授权'}), 401

        username = session['user']
        config = request.json or {}
        if not config.get('api_key') or not config.get('api_secret'):
            return jsonify({'success': False, 'message': 'API密钥不能为空'}), 400
        if not config.get('symbol'):
            return jsonify({'success': False, 'message': '缺少symbol'}), 400

        try:
            testnet = bool(config.get('testnet', 1))
            exchange_name = config.get('exchange', 'binance').lower()
            exchange = ExchangeFactory.create(
                exchange_name,
                config['api_key'],
                config['api_secret'],
                testnet=testnet
            )
            
            if not exchange:
                return jsonify({'success': False, 'message': f'不支持的交易所: {exchange_name}'}), 400

            exchange.ping()

            symbol = config['symbol']
            if username not in user_bots or not isinstance(user_bots.get(username), dict):
                user_bots[username] = {'bots': {}}
            if symbol in user_bots[username]['bots'] and user_bots[username]['bots'][symbol].get('running'):
                return jsonify({'success': False, 'message': '该交易对机器人已运行'})

            user_bots[username]['bots'][symbol] = {
                'running': True,
                'exchange': exchange,
                'config': config,
                'current_price': None,
                'target_price': None,
                'pending_buys': []
            }

            thread = threading.Thread(target=trading_loop, args=(username, symbol), daemon=True)
            thread.start()
            user_bots[username]['bots'][symbol]['thread'] = thread

            exchange_name = config.get('exchange', 'binance').upper()
            log_prefix = f"[{username}-{exchange_name}-{symbol}]"
            print(f"[{datetime.now().isoformat()}] {log_prefix} ▶️ 机器人已启动 (mode={'SIM' if config.get('simulate_trading',1)==1 else 'REAL'})")
            return jsonify({'success': True, 'message': f'{symbol} 机器人已启动 ({"模拟" if config.get("simulate_trading",1)==1 else "实盘"})'})
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ 启动失败: {e}")
            return jsonify({'success': False, 'message': f'启动失败: {str(e)}'}), 500

    @app.route('/api/stop', methods=['POST'])
    def api_stop():
        if 'user' not in session:
            return jsonify({'success': False, 'message': '未授权'}), 401

        username = session['user']
        # 停止该用户的所有机器人（兼容旧接口）
        user_data = user_bots.get(username, {})
        stopped_any = False
        if isinstance(user_data, dict):
            for b in user_data.get('bots', {}).values():
                if b.get('running'):
                    b['running'] = False
                    stopped_any = True
        if not stopped_any:
            return jsonify({'success': False, 'message': '机器人未在运行'})
        print(f"[{datetime.now().isoformat()}] [{username}-ALL-ALL] ◼️ 机器人停止请求")
        return jsonify({'success': True, 'message': '所有机器人已停止'})

    @app.route('/api/config/save', methods=['POST'])
    def api_save_config():
        if 'user' not in session:
            return jsonify({'success': False, 'message': '未授权'}), 401

        username = session['user']
        data = request.json
        config = data.get('config', data)  # 兼容旧格式
        config_name = data.get('config_name', 'default')
        
        if not config.get('api_key') or not config.get('api_secret'):
            return jsonify({'success': False, 'message': 'API密钥不能为空'}), 400

        if save_user_config(username, config, config_name):
            return jsonify({'success': True, 'message': f'配置 "{config_name}" 已加密保存到服务器'})
        else:
            return jsonify({'success': False, 'message': '保存失败'}), 500

    @app.route('/api/config/load')
    def api_load_config():
        if 'user' not in session:
            return jsonify({'success': False, 'message': '未授权'}), 401

        username = session['user']
        config_name = request.args.get('config_name', 'default')
        config = load_user_config(username, config_name)
        if config:
            return jsonify({'success': True, 'config': config})
        else:
            return jsonify({'success': False, 'message': '未找到已保存的配置'})
    
    @app.route('/api/configs')
    def api_configs_list():
        """获取用户的所有配置列表"""
        if 'user' not in session:
            return jsonify({'success': False, 'configs': []}), 401
        
        username = session['user']
        from database import get_user_config_list
        configs = get_user_config_list(username)
        return jsonify({'success': True, 'configs': configs})
    
    @app.route('/api/config/delete', methods=['POST'])
    def api_delete_config():
        """删除指定配置"""
        if 'user' not in session:
            return jsonify({'success': False, 'message': '未授权'}), 401
        
        username = session['user']
        config_name = request.json.get('config_name')
        
        if not config_name or config_name == 'default':
            return jsonify({'success': False, 'message': '不能删除 default 配置'}), 400
        
        from database import delete_user_config
        if delete_user_config(username, config_name):
            return jsonify({'success': True, 'message': f'配置 "{config_name}" 已删除'})
        else:
            return jsonify({'success': False, 'message': '删除失败'}), 500

    @app.route('/api/orders')
    def api_orders():
        if 'user' not in session:
            return jsonify({'orders': []}), 401

        username = session['user']
        order_list = get_user_orders(username)
        return jsonify({'orders': order_list})

    @app.route('/change_password', methods=['GET', 'POST'])
    def change_password():
        if 'user' not in session:
            return redirect(url_for('login'))

        username = session['user']
        message = None
        msg_type = None

        if request.method == 'POST':
            old_password = request.form['old_password']
            new_password = request.form['new_password']
            confirm_password = request.form['confirm_password']

            if new_password != confirm_password:
                message = '新密码和确认密码不一致！'
                msg_type = 'error'
            elif len(new_password) < 6:
                message = '新密码长度至少需要6位。'
                msg_type = 'error'
            else:
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT password FROM users WHERE username=?", (username,))
                result = c.fetchone()

                if result and check_password_hash(result[0], old_password):
                    new_hashed_password = generate_password_hash(new_password)
                    c.execute("UPDATE users SET password=? WHERE username=?", (new_hashed_password, username))
                    conn.commit()
                    conn.close()
                    message = '✅ 密码修改成功！请使用新密码重新登录。'
                    msg_type = 'success'
                    session.pop('user', None)
                    return render_template('change_password.html', username=username, message=message, type=msg_type)
                else:
                    conn.close()
                    message = '旧密码错误。'
                    msg_type = 'error'

        return render_template('change_password.html', username=username, message=message, type=msg_type)
    




# 在 register_routes 函数末尾添加以下路由：

    @app.route('/api/trading_pairs')
    def api_trading_pairs():
        if 'user' not in session:
            return jsonify({'success': False, 'pairs': []}), 401
        
        username = session['user']
        pairs = get_user_trading_pairs(username)
        return jsonify({'success': True, 'pairs': pairs})

    @app.route('/api/trading_pairs/add', methods=['POST'])
    def api_add_trading_pair():
        if 'user' not in session:
            return jsonify({'success': False, 'message': '未授权'}), 401
        
        username = session['user']
        data = request.json
        symbol = data.get('symbol', '').strip().upper()
        display_name = data.get('display_name', '').strip()
        
        if not symbol or not display_name:
            return jsonify({'success': False, 'message': '交易对和显示名称不能为空'})
        
        if add_trading_pair(username, symbol, display_name):
            return jsonify({'success': True, 'message': '交易对添加成功'})
        else:
            return jsonify({'success': False, 'message': '交易对已存在或添加失败'})

    @app.route('/api/trading_pairs/delete', methods=['POST'])
    def api_delete_trading_pair():
        if 'user' not in session:
            return jsonify({'success': False, 'message': '未授权'}), 401
        
        username = session['user']
        pair_id = request.json.get('id')
        
        if delete_trading_pair(username, pair_id):
            return jsonify({'success': True, 'message': '交易对删除成功'})
        else:
            return jsonify({'success': False, 'message': '删除失败'})

    @app.route('/api/trading_pairs/update', methods=['POST'])
    def api_update_trading_pair():
        if 'user' not in session:
            return jsonify({'success': False, 'message': '未授权'}), 401
        
        username = session['user']
        data = request.json
        pair_id = data.get('id')
        symbol = data.get('symbol', '').strip().upper()
        display_name = data.get('display_name', '').strip()
        exchanges = data.get('exchanges')  # 可选参数
        
        if not symbol or not display_name:
            return jsonify({'success': False, 'message': '交易对和显示名称不能为空'})
        
        if update_trading_pair(username, pair_id, symbol, display_name, exchanges):
            return jsonify({'success': True, 'message': '交易对更新成功'})
        else:
            return jsonify({'success': False, 'message': '更新失败或交易对已存在'})

    @app.route('/api/bots')
    def api_bots():
        if 'user' not in session:
            return jsonify({'success': False, 'bots': []}), 401
        username = session['user']
        user_data = user_bots.get(username, {})
        bots = []
        if isinstance(user_data, dict):
            for sym, b in user_data.get('bots', {}).items():
                bots.append({
                    'symbol': sym,
                    'running': bool(b.get('running')),
                    'current_price': b.get('current_price'),
                    'target_price': b.get('target_price'),
                    'config': b.get('config', {})
                })
        return jsonify({'success': True, 'bots': bots})

    @app.route('/api/bot/start', methods=['POST'])
    def api_bot_start():
        if 'user' not in session:
            return jsonify({'success': False, 'message': '未授权'}), 401
        username = session['user']
        config = request.json or {}
        if not config or not config.get('symbol'):
            return jsonify({'success': False, 'message': '缺少symbol'}), 400
        if not config.get('api_key') or not config.get('api_secret'):
            return jsonify({'success': False, 'message': 'API密钥不能为空'}), 400
        try:
            testnet = bool(config.get('testnet', 1))
            exchange_name = config.get('exchange', 'binance').lower()
            exchange = ExchangeFactory.create(
                exchange_name,
                config['api_key'],
                config['api_secret'],
                testnet=testnet
            )
            
            if not exchange:
                return jsonify({'success': False, 'message': f'不支持的交易所: {exchange_name}'}), 400
                
            exchange.ping()
            symbol = config['symbol']
            if username not in user_bots or not isinstance(user_bots.get(username), dict):
                user_bots[username] = {'bots': {}}
            if symbol in user_bots[username]['bots'] and user_bots[username]['bots'][symbol].get('running'):
                return jsonify({'success': False, 'message': '该交易对机器人已运行'})
            user_bots[username]['bots'][symbol] = {
                'running': True,
                'exchange': exchange,
                'config': config,
                'current_price': None,
                'target_price': None,
                'pending_buys': []
            }
            thread = threading.Thread(target=trading_loop, args=(username, symbol), daemon=True)
            thread.start()
            user_bots[username]['bots'][symbol]['thread'] = thread
            return jsonify({'success': True, 'message': f'{symbol} 机器人已启动'})
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] 启动失败: {e}")
            return jsonify({'success': False, 'message': f'启动失败: {str(e)}'}), 500

    @app.route('/api/bot/stop', methods=['POST'])
    def api_bot_stop():
        if 'user' not in session:
            return jsonify({'success': False, 'message': '未授权'}), 401
        username = session['user']
        data = request.json or {}
        symbol = data.get('symbol')
        if not symbol:
            return jsonify({'success': False, 'message': '缺少symbol'}), 400
        user_data = user_bots.get(username, {})
        bot = None
        if isinstance(user_data, dict):
            bot = user_data.get('bots', {}).get(symbol)
        if not bot or not bot.get('running'):
            return jsonify({'success': False, 'message': '机器人未在运行'})
        bot['running'] = False
        return jsonify({'success': True, 'message': f'{symbol} 机器人已停止'})

    @app.route('/api/bot/update', methods=['POST'])
    def api_bot_update():
        if 'user' not in session:
            return jsonify({'success': False, 'message': '未授权'}), 401
        username = session['user']
        data = request.json or {}
        symbol = data.get('symbol')
        if not symbol:
            return jsonify({'success': False, 'message': '缺少symbol'}), 400
        user_data = user_bots.get(username, {})
        bot = None
        if isinstance(user_data, dict):
            bot = user_data.get('bots', {}).get(symbol)
        if not bot:
            return jsonify({'success': False, 'message': '机器人不存在'})
        cfg = bot.get('config', {})
        for k in ['offset_percent', 'sell_offset_percent', 'quantity', 'interval', 'simulate_trading', 'testnet']:
            if k in data and data[k] is not None:
                cfg[k] = data[k]
        bot['config'] = cfg
        return jsonify({'success': True, 'message': f'{symbol} 配置已更新'})
