import time
from datetime import datetime
from database import get_user_id
import math
import traceback

user_bots = {}


def calculate_sell_price(buy_price, sell_offset_percent, tick_size, price_decimals, current_price=None):
    """计算卖出价格（带手续费保护）"""
    sell_offset = sell_offset_percent / 100.0
    raw_sell_price = (current_price or buy_price) * (1 + sell_offset)
    
    # 最低保护价（买入价 + 0.2% 手续费）
    min_price = buy_price * 1.002
    min_price = math.ceil(min_price / tick_size) * tick_size if tick_size else min_price
    min_price = round(min_price, price_decimals)
    
    # 最终卖价
    sell_price = max(raw_sell_price, min_price)
    sell_price = math.floor(sell_price / tick_size) * tick_size if tick_size else sell_price
    return round(sell_price, price_decimals)


def handle_buy_order_filled(event, bot_data, exchange, config, tick_size, price_decimals, 
                            step_size, qty_decimals, log_prefix):
    """处理买单成交事件"""
    order_id = event['order_id']
    
    # 去重检查
    if order_id in bot_data.get('processed_filled_orders', set()):
        print(f"[{datetime.now().isoformat()}] {log_prefix} ⏭️ [去重] 买单 {order_id} 已处理")
        return
    
    # 标记为已处理
    bot_data.setdefault('processed_filled_orders', set()).add(order_id)
    
    # 获取买入价格
    buy_price = float(event.get('price', 0))
    if not buy_price:
        for pb in bot_data.get('pending_buys', []):
            if pb['order_id'] == order_id:
                buy_price = pb.get('price')
                break
    
    if not buy_price:
        print(f"[{datetime.now().isoformat()}] {log_prefix} ⚠️ 买单 {order_id} 无法获取价格")
        bot_data.get('processed_filled_orders', set()).discard(order_id)
        return
    
    # 计算卖出价格
    sell_price = calculate_sell_price(
        buy_price, 
        config.get('sell_offset_percent', 0.5),
        tick_size, 
        price_decimals
    )
    
    # 获取成交数量
    executed_qty = float(event.get('executedQty') or event.get('quantity', 0))
    if not executed_qty:
        for pb in bot_data.get('pending_buys', []):
            if pb['order_id'] == order_id:
                executed_qty = pb.get('quantity')
                break
    
    if not executed_qty:
        print(f"[{datetime.now().isoformat()}] {log_prefix} ⚠️ 买单 {order_id} 无法获取数量")
        bot_data.get('processed_filled_orders', set()).discard(order_id)
        return
    
    # 考虑手续费扣除
    fee_rate = config.get('fee_rate', 0.002)  # 默认 0.2% 手续费
    actual_qty = executed_qty * (1 - fee_rate)
    print(f"[{datetime.now().isoformat()}] {log_prefix} 📊 成交数量: {executed_qty}, 手续费率: {fee_rate*100}%, 扣除后: {actual_qty}")
    
    # 对齐卖出数量
    aligned_qty = math.floor(actual_qty / step_size) * step_size if step_size else actual_qty
    aligned_qty = round(aligned_qty, qty_decimals)
    
    if aligned_qty <= 0:
        print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ 对齐后数量为 0，无法挂卖单")
        bot_data.get('processed_filled_orders', set()).discard(order_id)
        return
    
    print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ 买单成交 {order_id}: 买价={buy_price}, 数量={aligned_qty}")
    
    # 挂卖单
    try:
        sell_order = exchange.order_limit_sell(
            symbol=config['symbol'],
            quantity=aligned_qty,
            price=f"{sell_price}"
        )
        sell_order_id = str(sell_order.get('orderId') or sell_order.get('id'))
        print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ 卖单已挂 {sell_order_id}: 价格={sell_price}")
        
        # 从 pending_buys 移除
        bot_data['pending_buys'] = [
            pb for pb in bot_data.get('pending_buys', []) 
            if pb['order_id'] != order_id
        ]
        
        # 挂卖单成功，清除错误和警告信息
        bot_data['last_error'] = None
        bot_data['last_error_time'] = None
        bot_data['last_warning'] = None
    except Exception as e:
        error_msg = str(e)
        error_type = type(e).__name__
        print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ 挂卖单失败: {e}")
        
        # 保存挂卖单错误信息
        bot_data['last_error'] = f"挂卖单失败 - {error_type}: {error_msg}"
        bot_data['error_count'] = bot_data.get('error_count', 0) + 1
        bot_data['last_error_time'] = datetime.now().isoformat()


def handle_reconnected(event, bot_data, exchange, config, tick_size, price_decimals,
                       step_size, qty_decimals, log_prefix, on_order_update):
    """处理重连事件，同步订单状态"""
    print(f"[{datetime.now().isoformat()}] {log_prefix} 🔄 WebSocket 已重连，同步订单状态...")
    
    pending_buys = bot_data.get('pending_buys', [])
    for pending_buy in pending_buys[:]:
        order_id = pending_buy.get('order_id')
        try:
            order_info = exchange.get_order(config['symbol'], order_id)
            order_status = order_info.get('status')
            
            if order_status == 'FILLED':
                print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ 发现已成交订单 {order_id}")
                # 构造成交事件
                filled_event = {
                    'event_type': 'order_filled',
                    'order_id': str(order_info.get('orderId')),
                    'symbol': order_info.get('symbol'),
                    'side': order_info.get('side'),
                    'status': order_status,
                    'price': order_info.get('price'),
                    'quantity': order_info.get('origQty'),
                    'executedQty': order_info.get('executedQty')
                }
                on_order_update(filled_event)
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] {log_prefix} ⚠️ 查询订单 {order_id} 失败: {e}")


def reprice_buy_orders(open_buy_orders, target_price, aligned_quantity, bot_data, 
                       exchange, config, log_prefix):
    """改价未完成买单"""
    for order in open_buy_orders:
        current_price = float(order.get('price', 0))
        if current_price == target_price:
            continue
        
        try:
            resp = exchange.cancel_replace_order(
                symbol=config['symbol'],
                side='BUY',
                order_type='LIMIT',
                quantity=aligned_quantity,
                price=f"{target_price}",
                cancel_order_id=str(order['orderId']),
                timeInForce='GTC'
            )
            
            # 提取新订单ID
            new_order_id = None
            if isinstance(resp, dict):
                new_order_data = resp.get('newOrderResponse', {})
                if isinstance(new_order_data, dict):
                    new_order_id = str(new_order_data.get('orderId') or new_order_data.get('id'))
            
            if new_order_id and new_order_id != str(order['orderId']):
                print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ 改价成功: {order['orderId']} → {new_order_id}, 价格={target_price}")
                
                # 更新 pending_buys
                for p in bot_data.get('pending_buys', []):
                    if p['order_id'] == str(order['orderId']):
                        p['order_id'] = new_order_id
                        p['price'] = float(target_price)
                        break
                
                # 改价成功，清除错误和警告信息
                bot_data['last_error'] = None
                bot_data['last_error_time'] = None
                bot_data['last_warning'] = None
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ 改价失败 {order['orderId']}: {e}")


def reprice_sell_orders(open_sell_orders, bot_data, exchange, config, tick_size, 
                        price_decimals, step_size, qty_decimals, log_prefix):
    """动态调整卖单价格"""
    current_price = bot_data.get('current_price')
    if not current_price:
        return
    
    for sell_order in open_sell_orders:
        sell_order_id = str(sell_order['orderId'])
        current_sell_price = float(sell_order['price'])
        
        # 获取对应的买入价
        buy_price = None
        for pb in bot_data.get('pending_buys', []):
            if pb.get('sell_order_id') == sell_order_id:
                buy_price = pb.get('buy_price')
                break
        
        if not buy_price:
            continue
        
        # 计算目标卖价
        target_sell_price = calculate_sell_price(
            buy_price,
            config.get('sell_offset_percent', 0.5),
            tick_size,
            price_decimals,
            current_price
        )
        
        # 价格差异超过阈值才改价
        price_diff_percent = abs(target_sell_price - current_sell_price) / current_sell_price * 100
        if price_diff_percent < config.get('reprice_threshold_percent', 0.1):
            continue
        
        try:
            aligned_qty = math.floor(float(sell_order['origQty']) / step_size) * step_size
            aligned_qty = round(aligned_qty, qty_decimals)
            
            resp = exchange.cancel_replace_order(
                symbol=config['symbol'],
                side='SELL',
                order_type='LIMIT',
                quantity=aligned_qty,
                price=f"{target_sell_price}",
                cancel_order_id=sell_order_id,
                timeInForce='GTC'
            )
            
            print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ 卖单改价: {sell_order_id}, {current_sell_price} → {target_sell_price}")
            
            # 卖单改价成功，清除错误和警告信息
            bot_data['last_error'] = None
            bot_data['last_error_time'] = None
            bot_data['last_warning'] = None
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ 卖单改价失败 {sell_order_id}: {e}")


def trading_loop(username, symbol):
    """交易主循环"""
    user_data = user_bots.get(username)
    if not user_data:
        return
    bot_data = user_data.get('bots', {}).get(symbol)
    if not bot_data:
        return

    exchange_name = bot_data.get('config', {}).get('exchange', 'binance').upper()
    log_prefix = f"[{username}-{exchange_name}-{symbol}]"
    print(f"[{datetime.now().isoformat()}] {log_prefix} ▶️ 交易循环已启动")

    # 初始化
    tick_size = price_decimals = step_size = qty_decimals = None
    pending_buys_recovered = False
    bot_data['is_placing_order'] = False
    bot_data.setdefault('processed_filled_orders', set())
    
    # 初始化错误和警告信息
    bot_data['last_error'] = None
    bot_data['error_count'] = 0
    bot_data['last_error_time'] = None
    bot_data['last_warning'] = None
    bot_data['warning_count'] = 0

    while bot_data.get('running'):
        try:
            exchange = bot_data.get('exchange')
            config = bot_data.get('config', {})
            user_id = get_user_id(username)

            if not exchange or not config:
                time.sleep(1)
                continue

            # 获取交易规则（仅一次）
            if tick_size is None:
                try:
                    symbol_info = exchange.get_symbol_info(config['symbol'])
                    tick_size, price_decimals = exchange.get_price_precision(symbol_info)
                    step_size, qty_decimals = exchange.get_quantity_precision(symbol_info)
                except Exception as e:
                    tick_size, price_decimals = 0.01, 2
                    step_size, qty_decimals = 0.000001, 6
                    print(f"[{datetime.now().isoformat()}] {log_prefix} ⚠️ 获取交易规则失败，使用默认值")

            # 启动监听（仅一次）
            if not bot_data.get('monitor_started'):
                def _on_price_update(price: float):
                    print(f"[{datetime.now().isoformat()}] {log_prefix} 💰 价格更新回调被调用: {price}")
                    bot_data['current_price'] = price
                    print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ bot_data['current_price'] 已更新为: {bot_data['current_price']}")

                def _on_order_update(event: dict):
                    try:
                        event_type = event.get('event_type')
                        print(f"[{datetime.now().isoformat()}] {log_prefix} 📥 收到订单事件: {event}")
                        
                        # 重连事件
                        if event_type == 'reconnected':
                            handle_reconnected(event, bot_data, exchange, config, tick_size, 
                                             price_decimals, step_size, qty_decimals, 
                                             log_prefix, _on_order_update)
                            return
                        
                        # 错误事件
                        if event_type == 'error':
                            print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ {event.get('error_message')}")
                            return
                        
                        # 订单取消
                        if event_type == 'order_cancelled' and event.get('side') == 'BUY':
                            order_id = event.get('order_id')
                            bot_data['pending_buys'] = [
                                pb for pb in bot_data.get('pending_buys', []) 
                                if pb['order_id'] != order_id
                            ]
                            print(f"[{datetime.now().isoformat()}] {log_prefix} ⏭️ 订单取消 {order_id}")
                            return
                        
                        # 买单成交
                        if event_type == 'order_filled' and event.get('side') == 'BUY':
                            handle_buy_order_filled(event, bot_data, exchange, config, 
                                                   tick_size, price_decimals, step_size, 
                                                   qty_decimals, log_prefix)
                    except Exception as e:
                        print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ 订单回调错误: {e}")
                        traceback.print_exc()

                exchange.start_price_monitor(config['symbol'], _on_price_update)
                exchange.start_order_monitor(config['symbol'], _on_order_update)
                bot_data['monitor_started'] = True

            # 获取当前价格
            current_price = bot_data.get('current_price')
            if not current_price:
                warning_msg = "监听器未更新价格"
                bot_data['last_warning'] = warning_msg
                bot_data['warning_count'] = bot_data.get('warning_count', 0) + 1
                time.sleep(config.get('interval', 1))
                continue
            
            # 循环正常运行，清除错误和警告信息
            if bot_data.get('last_error') or bot_data.get('last_warning'):
                bot_data['last_error'] = None
                bot_data['last_error_time'] = None
                bot_data['last_warning'] = None

            offset = config.get('offset_percent', -0.1) / 100.0
            target_price = current_price * (1 + offset)
            target_price = math.floor(target_price / tick_size) * tick_size if tick_size else target_price
            target_price = round(target_price, price_decimals)
            bot_data['target_price'] = target_price

            # 对齐下单数量
            aligned_quantity = math.floor(config['quantity'] / step_size) * step_size if step_size else config['quantity']
            aligned_quantity = round(aligned_quantity, qty_decimals)

            # 查询未完成订单
            open_orders = []
            open_buy_orders = []
            open_sell_orders = []
            query_success = False
            
            try:
                open_orders = exchange.get_open_orders(symbol=config['symbol'])
                open_buy_orders = [o for o in open_orders if str(o.get('side')) == 'BUY']
                open_sell_orders = [o for o in open_orders if str(o.get('side')) == 'SELL']
                query_success = True

                # 恢复 pending_buys（仅启动时）
                if not pending_buys_recovered and not bot_data.get('pending_buys', []) and open_buy_orders:
                    for order in open_buy_orders:
                        bot_data.setdefault('pending_buys', []).append({
                            'order_id': str(order['orderId']),
                            'price': float(order['price']),
                            'quantity': float(order['origQty']),
                            'symbol': config['symbol'],
                            'user_id': user_id
                        })
                    print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ 恢复 {len(open_buy_orders)} 笔买单")
                    pending_buys_recovered = True

                # 改价买单
                if open_buy_orders:
                    reprice_buy_orders(open_buy_orders, target_price, aligned_quantity, 
                                     bot_data, exchange, config, log_prefix)

                # 动态调整卖单（默认禁用）
                if open_sell_orders:
                    reprice_sell_orders(open_sell_orders, bot_data, exchange, config, 
                                      tick_size, price_decimals, step_size, qty_decimals, log_prefix)

            except Exception as e:
                print(f"[{datetime.now().isoformat()}] {log_prefix} ⚠️ 查询订单失败: {e}")
                # 查询失败时不下单，避免重复挂单
                query_success = False

            # 下新单（要求查询成功、没有未完成订单、没有待处理买单、没有正在下单）
            has_pending_buys = bool(bot_data.get('pending_buys', []))
            if query_success and not open_orders and not has_pending_buys and not bot_data.get('is_placing_order'):
                is_buy_enabled = (config.get('simulate_trading', 1) != 1)
                if is_buy_enabled:
                    bot_data['is_placing_order'] = True
                    try:
                        order = exchange.order_limit_buy(
                            symbol=config['symbol'],
                            quantity=aligned_quantity,
                            price=f"{target_price}"
                        )
                        order_id = str(order.get('orderId') or order.get('id'))
                        print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ 新买单 {order_id}: 价格={target_price}, 数量={aligned_quantity}")

                        bot_data.setdefault('pending_buys', []).append({
                            'order_id': order_id,
                            'price': target_price,
                            'quantity': aligned_quantity,
                            'symbol': config['symbol'],
                            'user_id': user_id
                        })
                        
                        # 下单成功，清除错误和警告信息
                        bot_data['last_error'] = None
                        bot_data['last_error_time'] = None
                        bot_data['last_warning'] = None
                    except Exception as e:
                        error_msg = str(e)
                        error_type = type(e).__name__
                        print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ 下单失败: {e}")
                        
                        # 保存下单错误信息
                        bot_data['last_error'] = f"下单失败 - {error_type}: {error_msg}"
                        bot_data['error_count'] = bot_data.get('error_count', 0) + 1
                        bot_data['last_error_time'] = datetime.now().isoformat()
                    finally:
                        bot_data['is_placing_order'] = False

            time.sleep(config.get('interval', 1))

        except Exception as e:
            error_msg = str(e)
            error_type = type(e).__name__
            print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ 循环错误: {e}")
            traceback.print_exc()
            
            # 保存错误信息到 bot_data
            bot_data['last_error'] = f"{error_type}: {error_msg}"
            bot_data['error_count'] = bot_data.get('error_count', 0) + 1
            bot_data['last_error_time'] = datetime.now().isoformat()
            
            time.sleep(1)

    print(f"[{datetime.now().isoformat()}] {log_prefix} ◼️ 交易循环已停止")
