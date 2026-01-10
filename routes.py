import sqlite3
import threading
import time
from datetime import datetime, timedelta
from flask import request, jsonify, session, redirect, url_for, render_template
from werkzeug.security import check_password_hash, generate_password_hash
from exchanges.factory import ExchangeFactory

from config import DB_FILE
from database import (save_user_config, load_user_config, get_user_orders, get_user_profits, get_user_id,
                     get_user_trading_pairs, add_trading_pair, delete_trading_pair, 
                     update_trading_pair, get_user_credentials, add_credential,
                     delete_credential, update_credential, get_system_config, set_system_config)
from notification import DingTalkNotification

from trading import trading_loop, user_bots
from rate_limit_manager import check_and_adjust_rate_limit


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
                # 防止Session固定攻击：清除旧session并重新生成
                session.clear()
                session.modified = True
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

                # 为新用户创建默认配置
                from database import save_user_config
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
                print(f"[{datetime.now().isoformat()}] ✅ 新用户 {username} 注册成功，已创建默认配置")

                # 防止Session固定攻击：清除旧session并重新生成
                session.clear()
                session.modified = True
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
        # 用户登出时不停止机器人，机器人继续在后台运行
        print(f"[{datetime.now().isoformat()}] [{username}] 🚪 用户登出（机器人继续运行）")
        session.pop('user', None)
        return redirect(url_for('login'))

    def start_bot(username, config, user_id=None):
        """启动机器人的通用函数
        
        Args:
            username: 用户名
            config: 配置字典
            user_id: 用户ID（可选，如果不提供会自动获取）
        
        Returns:
            tuple: (success: bool, message: str, bot_data: dict or None)
        """
        try:
            if user_id is None:
                user_id = get_user_id(username)
            
            # 支持通过credential_id引用密钥
            credential_id = config.get('credential_id')
            if credential_id:
                from database import get_credential_by_id
                credential = get_credential_by_id(user_id, credential_id)
                if not credential:
                    return False, 'API凭证不存在', None
                api_key = credential['api_key']
                api_secret = credential['api_secret']
            else:
                api_key = config.get('api_key')
                api_secret = config.get('api_secret')
            
            if not api_key or not api_secret:
                return False, 'API密钥不能为空', None
            if not config.get('symbol'):
                return False, '缺少symbol', None

            testnet = bool(config.get('testnet', 1))
            exchange_name = config.get('exchange', 'binance').lower()
            symbol = config['symbol']
            # Polymarket/UpDown15m 阈值参数
            min_price_threshold = config.get('min_price_threshold')
            market_close_threshold = config.get('market_close_threshold')
            if min_price_threshold is not None:
                min_price_threshold = float(min_price_threshold)
            if market_close_threshold is not None:
                market_close_threshold = int(market_close_threshold)
            
            exchange = ExchangeFactory.create(
                exchange_name,
                api_key,
                api_secret,
                symbol=symbol,
                testnet=testnet,
                min_price_threshold=min_price_threshold,
                market_close_threshold=market_close_threshold,
                username=username
            )
            
            if not exchange:
                return False, f'不支持的交易所: {exchange_name}', None
                
            exchange.ping()
            
            # 只对币安交易所检查并调整API限制
            limit_msg = ""
            if exchange_name == 'binance':
                from trading import check_and_adjust_rate_limit
                can_start, limit_msg, adjusted_config = check_and_adjust_rate_limit(user_bots, config, api_key)
                if not can_start:
                    return False, f'API限制检查失败:\n{limit_msg}', None
                
                # 使用调整后的配置
                config = adjusted_config
                if limit_msg:
                    print(f"[{datetime.now().isoformat()}] {limit_msg}")
            
            # 创建机器人数据（遵循 api_start 的结构）
            bot_data = {
                'running': True,
                'exchange': exchange,
                'config': config,
                'current_price': None,
                'target_price': None,
                'pending_buys': [],
                'start_time': datetime.now()
            }
            
            # 启动交易线程
            from trading import trading_loop
            bot_key = f"{exchange_name}:{symbol}"
            
            if username not in user_bots or not isinstance(user_bots.get(username), dict):
                user_bots[username] = {'bots': {}}
                
            if bot_key in user_bots[username]['bots'] and user_bots[username]['bots'][bot_key].get('running'):
                return False, f'{exchange_name} 交易所的 {symbol} 机器人已运行', None
            
            user_bots[username]['bots'][bot_key] = bot_data
            
            thread = threading.Thread(target=trading_loop, args=(username, bot_key), daemon=True)
            thread.start()
            bot_data['thread'] = thread

            # 日志输出（遵循 api_start 的格式）
            exchange_name_display = config.get('exchange', 'binance').upper()
            log_prefix = f"[{username}-{exchange_name_display}-{symbol}]"
            print(f"[{datetime.now().isoformat()}] {log_prefix} ▶️ 机器人已启动 (mode={'SIM' if config.get('simulate_trading',1)==1 else 'REAL'})")
            
            # 递增启动次数
            from database import increment_start_count
            config_name = config.get('config_name', 'default')
            increment_start_count(username, config_name)
            
            # 构建返回消息（遵循 api_start 的格式）
            success_msg = f'{symbol} 机器人已启动 ({"模拟" if config.get("simulate_trading",1)==1 else "实盘"})'
            if limit_msg and '调整' in limit_msg:
                success_msg += '\n' + limit_msg
            
            return True, success_msg, bot_data
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ 启动失败: {e}")
            return False, f'启动失败: {str(e)}', None

    @app.route('/api/start', methods=['POST'])
    def api_start():
        if 'user' not in session:
            return jsonify({'success': False, 'message': '未授权'}), 401

        username = session['user']
        user_id = get_user_id(username)
        config = request.json or {}
        
        success, message, bot_data = start_bot(username, config, user_id)
        
        if success:
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'success': False, 'message': message}), 400

    @app.route('/api/stop', methods=['POST'])
    def api_stop():
        if 'user' not in session:
            return jsonify({'success': False, 'message': '未授权'}), 401

        username = session['user']
        # 停止该用户的所有机器人（兼容旧接口）
        user_data = user_bots.get(username, {})
        stopped_any = False
        stopped_bots = []
        if isinstance(user_data, dict):
            for symbol, b in user_data.get('bots', {}).items():
                if b.get('running'):
                    exchange_name = b.get('config', {}).get('exchange', 'binance').upper()
                    b['running'] = False
                    
                    # 停止监听器并清理连接
                    exchange = b.get('exchange')
                    if exchange:
                        try:
                            if hasattr(exchange, 'cleanup'):
                                exchange.cleanup()
                            else:
                                exchange.stop_ws()
                        except Exception as e:
                            print(f"[{datetime.now().isoformat()}] [{username}-{exchange_name}-{symbol}] ⚠️ 停止监听器时出错: {e}")
                    
                    stopped_any = True
                    stopped_bots.append(f"{exchange_name}-{symbol}")
                    print(f"[{datetime.now().isoformat()}] [{username}-{exchange_name}-{symbol}] ⏹️ 通过 /api/stop 停止")
        if not stopped_any:
            return jsonify({'success': False, 'message': '机器人未在运行'})
        print(f"[{datetime.now().isoformat()}] [{username}-ALL-ALL] ◼️ 停止了 {len(stopped_bots)} 个机器人: {', '.join(stopped_bots)}")
        return jsonify({'success': True, 'message': '所有机器人已停止'})

    @app.route('/api/config/save', methods=['POST'])
    def api_save_config():
        if 'user' not in session:
            return jsonify({'success': False, 'message': '未授权'}), 401

        username = session['user']
        data = request.json
        config = data.get('config', data)  # 兼容旧格式
        config_name = data.get('config_name', 'default')
        
        # 支持通过credential_id或直接传入api_key/api_secret
        credential_id = config.get('credential_id')
        if not credential_id:
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
    
    @app.route('/api/configs/all')
    def api_configs_all():
        """获取用户的所有配置详细信息（包含密钥别名和机器人状态）"""
        if 'user' not in session:
            return jsonify({'success': False, 'configs': []}), 401
        
        username = session['user']
        from database import get_user_config_list_with_details
        configs = get_user_config_list_with_details(username, include_default=True)
        
        # 为每个配置添加机器人状态信息
        for config in configs:
            exchange_name = config['exchange'].lower()
            symbol = config['symbol']
            bot_key = f"{exchange_name}:{symbol}"
            
            user_data = user_bots.get(username, {})
            bot = None
            if isinstance(user_data, dict):
                bot = user_data.get('bots', {}).get(bot_key)
            
            if bot:
                # 机器人存在，检查是否基于当前配置
                bot_config = bot.get('config', {})
                
                # 比较关键参数是否匹配
                is_same_config = (
                    bot_config.get('symbol') == config['symbol'] and
                    bot_config.get('exchange') == config['exchange'] and
                    bot_config.get('offset_percent') == config['offset_percent'] and
                    bot_config.get('sell_offset_percent') == config['sell_offset_percent'] and
                    bot_config.get('quantity') == config['quantity'] and
                    bot_config.get('interval') == config['interval'] and
                    bot_config.get('testnet') == config['testnet'] and
                    bot_config.get('simulate_trading') == config['simulate_trading']
                )
                
                if is_same_config:
                    # 基于当前配置的机器人 - 使用健康检查逻辑
                    is_running = bool(bot.get('running'))
                    
                    # 检查线程状态
                    thread = bot.get('thread')
                    thread_alive = thread.is_alive() if thread else False
                    
                    # 获取监听器状态
                    monitor_started = bot.get('monitor_started', False)
                    
                    # 获取错误和警告信息
                    last_error = bot.get('last_error')
                    last_warning = bot.get('last_warning')
                    
                    # 判断机器人健康状态
                    is_healthy = is_running and thread_alive and monitor_started and not last_error and not last_warning
                    
                    if is_running:
                        if is_healthy:
                            config['bot_status'] = '🟢 运行中'
                        else:
                            config['bot_status'] = '🟡 异常'
                    else:
                        config['bot_status'] = '🔴 已停止'
                    
                    config['bot_running'] = is_running
                    config['bot_healthy'] = is_healthy
                else:
                    # 机器人存在但配置不匹配
                    config['bot_status'] = '🔴 配置不匹配'
                    config['bot_running'] = False
                    config['bot_healthy'] = False
            else:
                # 机器人不存在
                config['bot_status'] = '🔴 未启动'
                config['bot_running'] = False
                config['bot_healthy'] = False
        
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

    @app.route('/api/profits')
    def api_profits():
        """获取盈利记录"""
        if 'user' not in session:
            return jsonify({'profits': [], 'total_profit': 0}), 401

        username = session['user']
        profits = get_user_profits(username)
        
        # 计算总盈利
        total_profit = sum(p['profit'] for p in profits)
        total_fee = sum(p['fee'] for p in profits)
        
        return jsonify({
            'profits': profits,
            'total_profit': round(total_profit, 6),
            'total_fee': round(total_fee, 6),
            'count': len(profits)
        })

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
                    # 防止Session固定攻击：清除所有session数据
                    session.clear()
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
        exchanges = data.get('exchanges', '').strip()
        
        if not symbol or not display_name:
            return jsonify({'success': False, 'message': '交易对和显示名称不能为空'})
        
        if add_trading_pair(username, symbol, display_name, exchanges):
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
            for bot_key, b in user_data.get('bots', {}).items():
                # 从 bot_key 中提取 symbol（格式: exchange:symbol）
                sym = b.get('config', {}).get('symbol', bot_key)
                
                # 检查线程状态
                thread = b.get('thread')
                thread_alive = thread.is_alive() if thread else False
                
                # 获取监听器状态
                monitor_started = b.get('monitor_started', False)
                order_monitor_enabled = b.get('order_monitor_enabled', False)
                
                # 获取pending_buys数量
                pending_buys_count = len(b.get('pending_buys', [])) + len(b.get('pending_sells', []))
                
                # 获取错误信息
                last_error = b.get('last_error')
                error_count = b.get('error_count', 0)
                last_error_time = b.get('last_error_time')
                
                # 获取警告信息
                last_warning = b.get('last_warning')
                warning_count = b.get('warning_count', 0)
                
                # 判断机器人健康状态
                is_running = bool(b.get('running'))
                is_healthy = is_running and thread_alive and monitor_started and not last_error and not last_warning
                
                # 状态描述
                if not is_running:
                    status_text = '已停止'
                elif not thread_alive:
                    status_text = '异常：线程已终止'
                elif not monitor_started:
                    status_text = '启动中...'
                elif last_error:
                    status_text = f'错误 (共{error_count}次)'
                elif last_warning:
                    status_text = f'警告 (共{warning_count}次)'
                else:
                    status_text = '正常运行'
                
                # 获取启动时间戳
                start_timestamp = None
                start_time = b.get('start_time')
                if start_time:
                    start_timestamp = int(start_time.timestamp() * 1000)
                
                # 获取币安API限制使用情况
                rate_limit_status = None
                exchange = b.get('exchange')
                if exchange and hasattr(exchange, 'get_rate_limit_status'):
                    try:
                        rate_limit_status = exchange.get_rate_limit_status()
                    except:
                        pass
                
                # 获取市场信息(适用于 BtcUpDown15m 等动态市场)
                market_info = None
                if exchange and hasattr(exchange, 'get_market_info'):
                    try:
                        market_info = exchange.get_market_info()
                    except:
                        pass
                
                # 获取市场剩余时间
                seconds_until_close = None
                if exchange and hasattr(exchange, 'get_seconds_until_market_close'):
                    try:
                        seconds_until_close = exchange.get_seconds_until_market_close()
                    except:
                        pass
                
                # 获取挂单价格列表
                pending_buys = b.get('pending_buys', [])
                pending_sells = b.get('pending_sells', [])
                buy_prices = [float(pb.get('price', 0)) for pb in pending_buys if pb.get('price')]
                sell_prices = [float(ps.get('price', 0)) for ps in pending_sells if ps.get('price')]
                
                bots.append({
                    'symbol': sym,
                    'running': is_running,
                    'healthy': is_healthy,
                    'status_text': status_text,
                    'current_price': b.get('current_price'),
                    'target_price': b.get('target_price'),
                    'config': b.get('config', {}),
                    'monitor_started': monitor_started,
                    'order_monitor_enabled': order_monitor_enabled,
                    'pending_buys_count': len(pending_buys),
                    'pending_sells_count': len(pending_sells),
                    'buy_prices': buy_prices,
                    'sell_prices': sell_prices,
                    'thread_alive': thread_alive,
                    'last_error': last_error,
                    'error_count': error_count,
                    'last_error_time': last_error_time,
                    'last_warning': last_warning,
                    'warning_count': warning_count,
                    'start_timestamp': start_timestamp,
                    'rate_limit_status': rate_limit_status,
                    'market_info': market_info,
                    'seconds_until_close': seconds_until_close,
                    'buy_min_price_diff_percent': b.get('buy_min_price_diff_percent'),
                    'buy_max_price_diff_percent': b.get('buy_max_price_diff_percent'),
                    'buy_avg_price_diff_percent': b.get('buy_avg_price_diff_percent'),
                    'sell_min_price_diff_percent': b.get('sell_min_price_diff_percent'),
                    'sell_max_price_diff_percent': b.get('sell_max_price_diff_percent'),
                    'sell_avg_price_diff_percent': b.get('sell_avg_price_diff_percent')
                })
        return jsonify({'success': True, 'bots': bots})

   

    @app.route('/api/bot/stop', methods=['POST'])
    def api_bot_stop():
        """删除机器人并取消所有订单"""
        if 'user' not in session:
            return jsonify({'success': False, 'message': '未授权'}), 401
        username = session['user']
        data = request.json or {}
        symbol = data.get('symbol')
        exchange_name = data.get('exchange', 'binance').lower()
        if not symbol:
            return jsonify({'success': False, 'message': '缺少symbol'}), 400
        bot_key = f"{exchange_name}:{symbol}"
        user_data = user_bots.get(username, {})
        bot = None
        if isinstance(user_data, dict):
            bot = user_data.get('bots', {}).get(bot_key)
        if not bot:
            return jsonify({'success': False, 'message': '机器人不存在'})
        
        exchange_name_upper = bot.get('config', {}).get('exchange', 'binance').upper()
        log_prefix = f"[{username}-{exchange_name_upper}-{symbol}]"
        
        # 停止机器人运行
        bot['running'] = False
        print(f"[{datetime.now().isoformat()}] {log_prefix} 🛑 停止机器人运行")
        
        # 获取交易所实例
        exchange = bot.get('exchange')
        if exchange:
            try:
                # 取消所有未完成订单
                print(f"[{datetime.now().isoformat()}] {log_prefix} 🔍 查询未完成订单...")
                open_orders = exchange.get_open_orders()
                if open_orders:
                    cancelled_count = 0
                    for order in open_orders:
                        try:
                            order_id = str(order.get('orderId') or order.get('id'))
                            exchange.cancel_order(order_id=order_id)
                            cancelled_count += 1
                            print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ 已取消订单: {order_id}")
                        except Exception as e:
                            print(f"[{datetime.now().isoformat()}] {log_prefix} ⚠️ 取消订单失败: {e}")
                    print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ 共取消 {cancelled_count} 笔订单")
                else:
                    print(f"[{datetime.now().isoformat()}] {log_prefix} ℹ️ 无未完成订单")
                
                # 停止监听器并清理连接
                if hasattr(exchange, 'cleanup'):
                    exchange.cleanup()
                else:
                    exchange.stop_ws()
                print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ 已停止监听器并清理连接")
            except Exception as e:
                print(f"[{datetime.now().isoformat()}] {log_prefix} ⚠️ 清理订单时出错: {e}")
        
        # 从内存中删除机器人
        if isinstance(user_data, dict) and 'bots' in user_data:
            if bot_key in user_data['bots']:
                del user_data['bots'][bot_key]
                print(f"[{datetime.now().isoformat()}] {log_prefix} 🗑️ 已从内存中删除机器人")
        
        return jsonify({'success': True, 'message': f'{symbol} 机器人已删除，所有订单已取消'})

    @app.route('/api/bots/batch_start', methods=['POST'])
    def api_bots_batch_start():
        """批量启动机器人"""
        if 'user' not in session:
            return jsonify({'success': False, 'message': '未授权'}), 401
        
        username = session['user']
        data = request.json or {}
        config_ids = data.get('config_ids', [])
        
        if not config_ids:
            return jsonify({'success': False, 'message': '请选择要启动的配置'}), 400
        
        from database import get_user_configs_by_ids
        configs = get_user_configs_by_ids(username, config_ids)
        
        if not configs:
            return jsonify({'success': False, 'message': '未找到选中的配置'}), 404
        
        success_count = 0
        error_messages = []
        
        for config in configs:
            try:
                # 加载完整配置
                from database import load_user_config
                full_config = load_user_config(username, config['config_name'])
                if not full_config:
                    error_messages.append(f"{config['config_name']}: 配置加载失败")
                    continue
                
                # 使用通用启动函数
                success, message, bot_data = start_bot(username, full_config)
                
                if success:
                    success_count += 1
                else:
                    error_messages.append(f"{config['config_name']}: {message}")
                    
            except Exception as e:
                error_messages.append(f"{config['config_name']}: {str(e)}")
                print(f"[{datetime.now().isoformat()}] 批量启动失败 - {config['config_name']}: {e}")
                import traceback
                traceback.print_exc()
        
        message = f"成功启动 {success_count}/{len(configs)} 个机器人"
        if error_messages:
            message += f"。失败: {', '.join(error_messages[:3])}"
            if len(error_messages) > 3:
                message += f" 等{len(error_messages)}个"
        
        return jsonify({'success': success_count > 0, 'message': message})

    @app.route('/api/bots/batch_stop', methods=['POST'])
    def api_bots_batch_stop():
        """批量停止机器人"""
        if 'user' not in session:
            return jsonify({'success': False, 'message': '未授权'}), 401
        
        username = session['user']
        data = request.json or {}
        config_ids = data.get('config_ids', [])
        
        if not config_ids:
            return jsonify({'success': False, 'message': '请选择要停止的配置'}), 400
        
        from database import get_user_configs_by_ids
        configs = get_user_configs_by_ids(username, config_ids)
        
        if not configs:
            return jsonify({'success': False, 'message': '未找到选中的配置'}), 404
        
        success_count = 0
        error_messages = []
        
        for config in configs:
            try:
                # 直接调用停止逻辑
                exchange_name = config['exchange'].lower()
                symbol = config['symbol']
                bot_key = f"{exchange_name}:{symbol}"
                
                user_data = user_bots.get(username, {})
                bot = None
                if isinstance(user_data, dict):
                    bot = user_data.get('bots', {}).get(bot_key)
                
                if not bot:
                    error_messages.append(f"{config['config_name']}: 机器人不存在")
                    continue
                
                # 停止机器人
                bot['running'] = False
                
                # 取消订单
                exchange = bot.get('exchange')
                if exchange:
                    try:
                        open_orders = exchange.get_open_orders()
                        if open_orders:
                            for order in open_orders:
                                try:
                                    order_id = str(order.get('orderId') or order.get('id'))
                                    exchange.cancel_order(order_id=order_id)
                                except Exception:
                                    pass
                    except Exception:
                        pass
                    
                    # 清理连接
                    if hasattr(exchange, 'cleanup'):
                        exchange.cleanup()
                    else:
                        exchange.stop_ws()
                
                # 从内存中删除
                if isinstance(user_data, dict) and 'bots' in user_data:
                    if bot_key in user_data['bots']:
                        del user_data['bots'][bot_key]
                
                success_count += 1
                    
            except Exception as e:
                error_messages.append(f"{config['config_name']}: {str(e)}")
                print(f"[{datetime.now().isoformat()}] 批量停止失败 - {config['config_name']}: {e}")
                import traceback
                traceback.print_exc()
        
        message = f"成功停止 {success_count}/{len(configs)} 个机器人"
        if error_messages:
            message += f"。失败: {', '.join(error_messages[:3])}"
            if len(error_messages) > 3:
                message += f" 等{len(error_messages)}个"
        
        return jsonify({'success': success_count > 0, 'message': message})

    @app.route('/api/configs/batch_delete', methods=['POST'])
    def api_configs_batch_delete():
        """批量删除配置"""
        if 'user' not in session:
            return jsonify({'success': False, 'message': '未授权'}), 401
        
        username = session['user']
        data = request.json or {}
        config_ids = data.get('config_ids', [])
        
        if not config_ids:
            return jsonify({'success': False, 'message': '请选择要删除的配置'}), 400
        
        from database import delete_user_configs_by_ids
        try:
            result = delete_user_configs_by_ids(username, config_ids)
            
            if result:
                print(f"[{datetime.now().isoformat()}] 批量删除配置成功: {result} 个")
                return jsonify({'success': True, 'message': f'成功删除 {result} 个配置'})
            else:
                print(f"[{datetime.now().isoformat()}] 批量删除配置失败: 没有配置被删除")
                return jsonify({'success': False, 'message': '删除失败'})
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] 批量删除配置异常: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'success': False, 'message': f'删除失败: {str(e)}'})

    @app.route('/api/bot/update', methods=['POST'])
    def api_bot_update():
        if 'user' not in session:
            return jsonify({'success': False, 'message': '未授权'}), 401
        username = session['user']
        data = request.json or {}
        symbol = data.get('symbol')
        exchange_name = data.get('exchange', 'binance').lower()
        if not symbol:
            return jsonify({'success': False, 'message': '缺少symbol'}), 400
        bot_key = f"{exchange_name}:{symbol}"
        user_data = user_bots.get(username, {})
        bot = None
        if isinstance(user_data, dict):
            bot = user_data.get('bots', {}).get(bot_key)
        if not bot:
            return jsonify({'success': False, 'message': '机器人不存在'})
        cfg = bot.get('config', {})
        for k in ['offset_percent', 'sell_offset_percent', 'sell_decay_count', 'quantity', 'interval', 'simulate_trading', 'testnet']:
            if k in data and data[k] is not None:
                cfg[k] = data[k]
        bot['config'] = cfg
        return jsonify({'success': True, 'message': f'{symbol} 配置已更新'})

    # API凭证管理路由
    @app.route('/api/credentials')
    def api_credentials():
        """获取用户的所有API凭证列表(不返回secret)"""
        if 'user' not in session:
            return jsonify({'success': False, 'credentials': []}), 401
        
        username = session['user']
        credentials = get_user_credentials(username)
        return jsonify({'success': True, 'credentials': credentials})

    @app.route('/api/credentials/add', methods=['POST'])
    def api_add_credential():
        """添加新的API凭证"""
        if 'user' not in session:
            return jsonify({'success': False, 'message': '未授权'}), 401
        
        username = session['user']
        data = request.json
        alias = data.get('alias', '').strip()
        exchange = data.get('exchange', '').strip().lower()
        api_key = data.get('api_key', '').strip()
        api_secret = data.get('api_secret', '').strip()
        
        if not alias or not exchange or not api_key or not api_secret:
            return jsonify({'success': False, 'message': '所有字段都不能为空'})
        
        credential_id = add_credential(username, alias, exchange, api_key, api_secret)
        if credential_id:
            return jsonify({'success': True, 'message': 'API凭证添加成功', 'credential_id': credential_id})
        else:
            return jsonify({'success': False, 'message': '别名已存在或添加失败'})

    @app.route('/api/credentials/delete', methods=['POST'])
    def api_delete_credential():
        """删除API凭证"""
        if 'user' not in session:
            return jsonify({'success': False, 'message': '未授权'}), 401
        
        username = session['user']
        credential_id = request.json.get('id')
        
        result = delete_credential(username, credential_id)
        if isinstance(result, dict):
            return jsonify(result)
        return jsonify({'success': False, 'message': '删除失败'})

    @app.route('/api/credentials/update', methods=['POST'])
    def api_update_credential():
        """更新API凭证"""
        if 'user' not in session:
            return jsonify({'success': False, 'message': '未授权'}), 401
        
        username = session['user']
        data = request.json
        credential_id = data.get('id')
        alias = data.get('alias', '').strip()
        exchange = data.get('exchange', '').strip() if data.get('exchange') else None
        api_key = data.get('api_key', '').strip() if data.get('api_key') else None
        api_secret = data.get('api_secret', '').strip() if data.get('api_secret') else None
        
        if not alias:
            return jsonify({'success': False, 'message': '别名不能为空'})
        
        # 如果提供了api_key,必须同时提供api_secret
        if (api_key and not api_secret) or (not api_key and api_secret):
            return jsonify({'success': False, 'message': 'API Key和Secret必须同时提供'})
        
        if update_credential(username, credential_id, alias, api_key, api_secret, exchange):
            return jsonify({'success': True, 'message': 'API凭证更新成功'})
        else:
            return jsonify({'success': False, 'message': '更新失败或别名已存在'})

    @app.route('/api/atr')
    def api_atr():
        """获取交易对的 ATR 数据和推荐参数"""
        import ccxt
        
        symbol = request.args.get('symbol', 'BTCUSDT')
        exchange_id = request.args.get('exchange', 'binance').lower()
        timeframe = request.args.get('timeframe', '1h')
        
        try:
            # 映射交易所名称到 ccxt 交易所 ID
            ccxt_exchange_map = {
                # Binance 现货
                'binance': 'binance',
                'native_binance_spot': 'binance',
                'ccxt_binance_spot': 'binance',
                'ccxt_binance': 'binance',
                # Binance 合约
                'binance_futures': 'binanceusdm',
                'native_binance_futures': 'binanceusdm',
                'ccxt_binance_futures': 'binanceusdm',
                'ccxt_binance_futures_short': 'binanceusdm',
                'ccxt_futures': 'binanceusdm',
                # Backpack
                'backpack': 'backpack',
                'native_backpack_spot': 'backpack',
                'bpx': 'backpack',
            }
            ccxt_id = ccxt_exchange_map.get(exchange_id, exchange_id)
            
            # 转换交易对格式 (BTCUSDT -> BTC/USDT 或 BTC/USDT:USDT)
            if '/' not in symbol and len(symbol) > 4:
                if symbol.endswith('USDT'):
                    base_symbol = symbol[:-4] + '/USDT'
                    # 合约交易所需要添加 :USDT 后缀
                    if ccxt_id == 'binanceusdm':
                        symbol = base_symbol + ':USDT'
                    else:
                        symbol = base_symbol
                elif symbol.endswith('USD'):
                    symbol = symbol[:-3] + '/USD'
            
            # 创建 ccxt 交易所实例
            exchange_class = getattr(ccxt, ccxt_id)
            exchange = exchange_class({'enableRateLimit': True})
            
            # 获取 K 线数据
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=64)
            
            if not ohlcv or len(ohlcv) < 15:
                return jsonify({'success': False, 'message': 'K线数据不足'})
            
            # 计算 ATR (Average True Range)
            period = 14
            true_ranges = []
            for i in range(1, len(ohlcv)):
                high = ohlcv[i][2]
                low = ohlcv[i][3]
                prev_close = ohlcv[i-1][4]
                
                tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
                true_ranges.append(tr)
            
            atr = sum(true_ranges[-period:]) / period
            current_price = float(ohlcv[-1][4])
            
            # 根据 ATR 计算推荐参数
            atr_percent = (atr / current_price) * 100
            
            # offset: ATR% 的 15%，作为买单偏移（负值）
            # sell_offset: ATR% 的 40%，最低 0.2%（覆盖手续费）
            suggested_offset = -round(atr_percent * 0.15, 3)
            suggested_sell_offset = max(0.2, round(atr_percent * 0.4, 3))
            
            return jsonify({
                'success': True,
                'symbol': symbol,
                'exchange': exchange_id,
                'timeframe': timeframe,
                'atr': round(atr, 8),
                'atr_percent': round(atr_percent, 4),
                'current_price': current_price,
                'suggested_offset': suggested_offset,
                'suggested_sell_offset': suggested_sell_offset
            })
            
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})

    @app.route('/api/exchanges')
    def api_exchanges():
        """获取支持的交易所列表
        
        从各交易所适配器的 get_exchange_info() 方法获取 id 和 name
        """
        # 获取工厂中注册的交易所类（通过 get_exchange_info 获取）
        id_map = ExchangeFactory.get_exchange_id_map()
        exchange_classes = {}
        for exchange_id, cls in id_map.items():
            exchange_classes[exchange_id] = cls
        
        # 从每个交易所类获取 exchange_info
        result = []
        seen_ids = set()
        
        for factory_name, cls in exchange_classes.items():
            try:
                # 直接调用类的 get_exchange_info 类方法
                exchange_info = _get_exchange_info_by_class(cls, factory_name)
                
                if exchange_info and exchange_info['id'] not in seen_ids:
                    seen_ids.add(exchange_info['id'])
                    result.append({
                        'value': factory_name,  # 工厂使用的名称
                        'id': exchange_info['id'],
                        'display_name': exchange_info['name']
                    })
            except Exception as e:
                print(f"获取交易所信息失败 {factory_name}: {e}")
        
        return jsonify({
            'success': True,
            'exchanges': result
        })
    
    def _get_exchange_info_by_class(cls, factory_name: str) -> dict:
        """根据交易所类获取 exchange_info
        
        直接调用类的 get_exchange_info 类方法
        """
        try:
            return cls.get_exchange_info()
        except Exception:
            return {'id': factory_name, 'name': factory_name}
    
    @app.route('/api/polymarket/search', methods=['GET'])
    def api_polymarket_search():
        """搜索 Polymarket 市场"""
        if 'user' not in session:
            return jsonify({'success': False, 'message': '未授权'}), 401
        
        keyword = request.args.get('keyword', '').strip()
        include_closed = request.args.get('include_closed', 'false').lower() == 'true'
        direct_slug = request.args.get('direct_slug', 'false').lower() == 'true'
        
        if not keyword:
            return jsonify({'success': False, 'message': '请输入搜索关键词'})
        
        try:
            import requests
            import re
            import datetime
            
            # 检查是否是 URL 或 slug
            slug = None
            
            # 特殊处理: 如果包含 btc-updown-15m,自动生成最新时间戳的 slug
            if 'btc-updown-15m' in keyword.lower():
                # 计算下一个 15 分钟时间戳
                now = datetime.datetime.now()
                current_minute = now.minute
                next_15min_mark = ((current_minute // 15) + 1) * 15
                
                if next_15min_mark >= 60:
                    next_time = now.replace(hour=now.hour + 1, minute=0, second=0, microsecond=0)
                else:
                    next_time = now.replace(minute=next_15min_mark, second=0, microsecond=0)
                
                timestamp = int(next_time.timestamp())
                slug = f"btc-updown-15m-{timestamp}"
                print(f"Auto-generated slug for latest market: {slug}")
            
            # 如果用户勾选了"直接使用 Slug 搜索",强制将输入作为 slug 处理
            elif direct_slug:
                slug = keyword
            else:
                # 自动检测是否是 URL 或 slug
                url_match = re.search(r'polymarket\.com/event/([a-z0-9\-]+)', keyword)
                if url_match:
                    slug = url_match.group(1)
                elif re.match(r'^[a-z0-9\-]+$', keyword) and len(keyword) > 20:
                    # 看起来像 slug
                    slug = keyword
            
            # 如果是 slug,直接通过 Gamma API 查询
            if slug:
                try:
                    slug_response = requests.get(f'https://gamma-api.polymarket.com/events?slug={slug}', timeout=10)
                    if slug_response.status_code == 200:
                        slug_events = slug_response.json()
                        if slug_events:
                            event = slug_events[0]
                            markets = event.get('markets', [])
                            
                            results = []
                            for market in markets:
                                market_data = {
                                    'question': market.get('question', event.get('title', 'N/A')),
                                    'condition_id': market.get('conditionId', ''),
                                    'description': event.get('description', ''),
                                    'active': event.get('active', False),
                                    'closed': event.get('closed', False),
                                    'tokens': market.get('tokens', [])
                                }
                                results.append(market_data)
                            
                            if results:
                                return jsonify({
                                    'success': True,
                                    'markets': results,
                                    'count': len(results),
                                    'total_searched': 1,
                                    'source': 'direct_slug'
                                })
                except Exception as e:
                    print(f"Slug search error: {e}")
            
            # 使用 Gamma API 获取市场数据(更全面)
            all_markets = []
            
            try:
                # 1. 从 Gamma API 获取事件数据(获取最多 500 个事件)
                gamma_response = requests.get('https://gamma-api.polymarket.com/events', 
                                             params={'limit': 1000}, 
                                             timeout=30)
                if gamma_response.status_code == 200:
                    gamma_events = gamma_response.json()
                    
                    # 将 Gamma API 格式转换为统一格式
                    for event in gamma_events:
                        # Gamma API 的事件可能包含多个市场
                        event_markets = event.get('markets', [])
                        
                        if event_markets:
                            # 如果有子市场,添加每个市场
                            for market in event_markets:
                                all_markets.append({
                                    'question': market.get('question', event.get('title', 'N/A')),
                                    'condition_id': market.get('conditionId', ''),
                                    'description': event.get('description', ''),
                                    'active': event.get('active', False),
                                    'closed': event.get('closed', False),
                                    'tokens': market.get('tokens', [])
                                })
                        else:
                            # 如果没有子市场,添加事件本身
                            all_markets.append({
                                'question': event.get('title', 'N/A'),
                                'condition_id': event.get('id', ''),
                                'description': event.get('description', ''),
                                'active': event.get('active', False),
                                'closed': event.get('closed', False),
                                'tokens': []
                            })
            except Exception as e:
                print(f"Gamma API error: {e}")
            
            # 2. 如果 Gamma API 返回的市场不够,补充 CLOB API 数据
            if len(all_markets) < 1000:
                try:
                    from py_clob_client.client import ClobClient
                    client = ClobClient("https://clob.polymarket.com")
                    
                    next_cursor = 'MA=='
                    max_pages = 5
                    
                    for page in range(max_pages):
                        response = client.get_markets(next_cursor=next_cursor)
                        
                        if isinstance(response, dict):
                            markets = response.get('data', [])
                            all_markets.extend(markets)
                            next_cursor = response.get('next_cursor')
                            
                            if not next_cursor:
                                break
                        else:
                            break
                except Exception as e:
                    print(f"CLOB API error: {e}")
            
            # 搜索匹配的市场
            keyword_lower = keyword.lower()
            results = []
            
            for market in all_markets:
                # 根据参数决定是否过滤已关闭的市场
                if not include_closed and market.get('closed', False):
                    continue
                
                question = market.get('question', '').lower()
                description = market.get('description', '').lower()
                
                if keyword_lower in question or keyword_lower in description:
                    tokens = market.get('tokens', [])
                    market_data = {
                        'question': market.get('question', 'N/A'),
                        'condition_id': market.get('condition_id', 'N/A'),
                        'description': market.get('description', '')[:200],
                        'active': market.get('active', False),
                        'closed': market.get('closed', False),
                        'tokens': []
                    }
                    
                    for token in tokens:
                        market_data['tokens'].append({
                            'outcome': token.get('outcome', 'Unknown'),
                            'token_id': token.get('token_id', 'N/A')
                        })
                    
                    results.append(market_data)
            
            return jsonify({
                'success': True,
                'markets': results,
                'count': len(results),
                'total_searched': len(all_markets)
            })
            
        except ImportError:
            return jsonify({
                'success': False,
                'message': '请先安装 py-clob-client: pip install py-clob-client'
            })
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'搜索失败: {str(e)}'
            })

    @app.route('/system_settings', methods=['GET', 'POST'])
    def system_settings():
        if 'user' not in session:
            return redirect(url_for('login'))
        
        username = session['user']
        message = None
        msg_type = None
        
        if request.method == 'POST':
            dingtalk_token = request.form.get('dingtalk_access_token', '').strip()
            if dingtalk_token:
                set_system_config(username, 'dingtalk_access_token', dingtalk_token, '钉钉机器人access_token')
                message = '设置保存成功'
                msg_type = 'success'
            else:
                message = 'Access Token 不能为空'
                msg_type = 'error'
        
        # 获取当前配置
        dingtalk_access_token = get_system_config(username, 'dingtalk_access_token')
        
        return render_template('system_settings.html', 
                             username=username,
                             dingtalk_access_token=dingtalk_access_token,
                             message=message,
                             msg_type=msg_type)

    @app.route('/api/test_dingtalk', methods=['POST'])
    def test_dingtalk():
        if 'user' not in session:
            return jsonify({'success': False, 'message': '未登录'})
        
        username = session['user']
        try:
            notifier = DingTalkNotification(username=username)
            if not notifier.webhook_url:
                return jsonify({'success': False, 'message': '钉钉access_token未配置'})
            
            result = notifier.send(f"🔔 测试通知\n这是来自 AresBot 的测试消息\n用户: {username}\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            if result:
                return jsonify({'success': True, 'message': '发送成功'})
            else:
                return jsonify({'success': False, 'message': '发送失败，请检查access_token和关键词设置'})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})
