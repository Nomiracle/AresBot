import sqlite3
import threading
from datetime import datetime
from flask import request, jsonify, session, redirect, url_for, render_template
from werkzeug.security import check_password_hash, generate_password_hash
from binance.client import Client

from config import DB_FILE
from database import save_user_config, load_user_config, get_user_orders, get_user_id

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
            c.execute("SELECT password FROM users WHERE username=?", (username,))
            result = c.fetchone()
            conn.close()

            if result and check_password_hash(result[0], password):
                session['user'] = username
                return redirect(url_for('index'))
            return render_template('login.html', error='用户名或密码错误')

        return render_template('login.html')
            

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

            client.ping()

            user_bots[username] = {
                'running': True,
                'client': client,
                'config': config,
                'current_price': None,
                'target_price': None,
                'pending_buys': []
            }

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
