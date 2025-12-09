import time
from datetime import datetime
from database import get_user_id
import math
import traceback

user_bots = {}


def calculate_buy_target_price(current_price, offset_percent, tick_size, price_decimals):
    """
    计算买单目标价格
    
    Args:
        current_price: 当前市场价格
        offset_percent: 偏移百分比（通常为负数，如 -0.1）
        tick_size: 价格步长
        price_decimals: 价格小数位数
    
    Returns:
        float: 对齐后的买单目标价格
    """
    offset = offset_percent / 100.0
    target_price = current_price * (1 + offset)
    
    # 按 tick_size 对齐（向下取整）
    if tick_size and tick_size > 0:
        target_price = math.floor(target_price / tick_size) * tick_size
    
    # 按小数位数对齐
    target_price = round(target_price, price_decimals)
    
    return target_price





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
    sell_price = exchange.calculate_sell_price(
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
    
    # 检查手续费是否外部支付（如 BNB 抵扣）
    fee_paid_externally = event.get('feePaidExternally', False)
    if fee_paid_externally:
        # 外部支付手续费，不扣除币种数量，使用配置的固定挂单数量
        aligned_qty = math.floor(config['quantity'] / step_size) * step_size if step_size else config['quantity']
        aligned_qty = round(aligned_qty, qty_decimals)
        print(f"[{datetime.now().isoformat()}] {log_prefix} 📊 外部支付手续费，使用固定数量: {aligned_qty}")
    else:
        # 从交易币种扣除手续费
        fee_rate = exchange.get_fee_rate() * 2
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
            quantity=aligned_qty,
            price=f"{sell_price}"
        )
        sell_order_id = str(sell_order.get('orderId') or sell_order.get('id'))
        print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ 卖单已挂 {sell_order_id}: 价格={sell_price}")
        
        # 更新 target_price 为卖单价格
        bot_data['target_price'] = sell_price
        
        # 从 pending_buys 移除
        bot_data['pending_buys'] = [
            pb for pb in bot_data.get('pending_buys', []) 
            if pb['order_id'] != order_id
        ]
        
        # 添加到 pending_sells 跟踪列表
        bot_data.setdefault('pending_sells', []).append({
            'order_id': sell_order_id,
            'price': sell_price,
            'quantity': aligned_qty,
            'buy_order_id': order_id,
            'buy_price': buy_price
        })
        
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


def handle_reconnected(bot_data, exchange, log_prefix, on_order_update):
    """处理重连事件，同步订单状态"""
    print(f"[{datetime.now().isoformat()}] {log_prefix} 🔄 WebSocket 已重连，同步订单状态...")
    
    # 同步买单状态
    pending_buys = bot_data.get('pending_buys', [])
    for pending_buy in pending_buys[:]:
        order_id = pending_buy.get('order_id')
        try:
            order_info = exchange.get_order(order_id)
            order_status = order_info.get('status')
            
            if order_status == 'FILLED':
                print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ 发现已成交买单 {order_id}")
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
            elif order_status == 'CANCELED':
                print(f"[{datetime.now().isoformat()}] {log_prefix} ⏭️ 发现已取消买单 {order_id}")
                # 从 pending_buys 移除
                bot_data['pending_buys'] = [
                    pb for pb in bot_data.get('pending_buys', []) 
                    if pb['order_id'] != order_id
                ]
            elif order_status == 'EXPIRED':
                print(f"[{datetime.now().isoformat()}] {log_prefix} ⏭️ 发现已过期买单 {order_id}")
                # 从 pending_buys 移除
                bot_data['pending_buys'] = [
                    pb for pb in bot_data.get('pending_buys', []) 
                    if pb['order_id'] != order_id
                ]
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] {log_prefix} ⚠️ 查询买单 {order_id} 失败: {e}")
    
    # 同步卖单状态
    pending_sells = bot_data.get('pending_sells', [])
    for pending_sell in pending_sells[:]:
        order_id = pending_sell.get('order_id')
        try:
            order_info = exchange.get_order(order_id)
            order_status = order_info.get('status')
            
            if order_status == 'FILLED':
                print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ 发现已成交卖单 {order_id}")
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
            elif order_status == 'CANCELED':
                print(f"[{datetime.now().isoformat()}] {log_prefix} ⏭️ 发现已取消卖单 {order_id}")
                # 从 pending_sells 移除
                bot_data['pending_sells'] = [
                    ps for ps in bot_data.get('pending_sells', []) 
                    if ps['order_id'] != order_id
                ]
            elif order_status == 'EXPIRED':
                print(f"[{datetime.now().isoformat()}] {log_prefix} ⏭️ 发现已过期卖单 {order_id}")
                # 从 pending_sells 移除
                bot_data['pending_sells'] = [
                    ps for ps in bot_data.get('pending_sells', []) 
                    if ps['order_id'] != order_id
                ]
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] {log_prefix} ⚠️ 查询卖单 {order_id} 失败: {e}")


def reprice_buy_orders(open_buy_orders, target_price, aligned_quantity, bot_data, 
                       exchange, config, log_prefix):
    """改价未完成买单"""
    for order in open_buy_orders:
        current_price = float(order.get('price', 0))
        if current_price == target_price:
            continue
        
        # 计算价格差异百分比
        price_diff_percent = abs(target_price - current_price) / current_price * 100
        if price_diff_percent < 0.01:
            print(f"[{datetime.now().isoformat()}] {log_prefix} ⏭️ 买单价格差异 {price_diff_percent:.4f}% < 0.01%，跳过改价")
            continue
        
        try:
            resp = exchange.cancel_replace_order(
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
            
            existing_ids = {p['order_id'] for p in bot_data.get('pending_buys', [])}
            if new_order_id not in existing_ids:
                bot_data.setdefault('pending_buys', []).append({
                    'order_id': new_order_id,
                    'price': target_price,
                    'quantity': aligned_quantity,
                    'symbol': config['symbol'],
                    'user_id': bot_data['user_id']
                })
                print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ 改价成功: {order['orderId']} → {new_order_id}, 目标价格={target_price:.6f}/当前价格={bot_data['current_price']:.6f}，本地缓存买单：{bot_data.get('pending_buys', [])}")
                
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
        for ps in bot_data.get('pending_sells', []):
            if ps.get('order_id') == sell_order_id:
                buy_price = ps.get('buy_price')
                break
        
        if not buy_price:
            continue
        # 计算目标卖价
        target_sell_price = exchange.calculate_sell_price(
            buy_price,
            config.get('sell_offset_percent', 0.5),
            tick_size,
            price_decimals,
            current_price
        )
        bot_data['target_price'] = target_sell_price   
        
        # 价格差异超过阈值才改价
        price_diff_percent = abs(target_sell_price - current_sell_price) / current_sell_price * 100
        # 首先检查是否小于 0.01%
        if price_diff_percent < 0.01:
            print(f"[{datetime.now().isoformat()}] {log_prefix} ⏭️ 卖单价格差异 {price_diff_percent:.4f}% < 0.01%，跳过改价")
            continue
        
        try:
            aligned_qty = math.floor(float(sell_order['origQty']) / step_size) * step_size
            aligned_qty = round(aligned_qty, qty_decimals)
            
            resp = exchange.cancel_replace_order(
                side='SELL',
                order_type='LIMIT',
                quantity=aligned_qty,
                price=f"{target_sell_price}",
                cancel_order_id=sell_order_id,
                timeInForce='GTC'
            )
            
            # 提取新订单ID
            new_order_id = None
            if isinstance(resp, dict):
                new_order_data = resp.get('newOrderResponse', {})
                if isinstance(new_order_data, dict):
                    new_order_id = str(new_order_data.get('orderId') or new_order_data.get('id'))
            
            existing_ids = {p['order_id'] for p in bot_data.get('pending_sells', [])}
            if new_order_id not in existing_ids:
                bot_data.setdefault('pending_sells', []).append({
                    'order_id': new_order_id,
                    'price': target_sell_price,
                    'quantity': aligned_qty,
                    'symbol': config['symbol'],
                    'user_id': bot_data['user_id'],
                    'buy_price': buy_price  # 保留原买入价，用于后续改价计算
                })
                print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ 卖单改价成功: {sell_order_id} → {new_order_id}, 目标价格={target_sell_price:.6f}/当前价格={bot_data['current_price']:.6f}，本地缓存卖单：{bot_data.get('pending_sells', [])}")
                
            # 改价成功，清除错误和警告信息
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
    bot_data.setdefault('pending_sells', [])
    
    # 初始化错误和警告信息
    bot_data['last_error'] = None
    bot_data['error_count'] = 0
    bot_data['last_error_time'] = None
    bot_data['last_warning'] = None
    bot_data['warning_count'] = 0
    user_id = get_user_id(username)
    bot_data['user_id'] = user_id

    while bot_data.get('running'):
        try:
            exchange = bot_data.get('exchange')
            config = bot_data.get('config', {})


            if not exchange or not config:
                time.sleep(1)
                continue

            # 获取交易规则（仅一次）
            if tick_size is None:
                try:
                    symbol_info = exchange.get_symbol_info()
                    tick_size, price_decimals = exchange.get_price_precision(symbol_info)
                    step_size, qty_decimals = exchange.get_quantity_precision(symbol_info)
                except Exception as e:
                    tick_size, price_decimals = 0.01, 2
                    step_size, qty_decimals = 0.000001, 6
                    print(f"[{datetime.now().isoformat()}] {log_prefix} ⚠️ 获取交易规则失败，使用默认值")

            # 启动监听（仅一次）
            if not bot_data.get('monitor_started'):
                def _on_price_update(price: float):
                    # print(f"[{datetime.now().isoformat()}] {log_prefix} 💰 价格更新回调被调用: {price}")
                    bot_data['current_price'] = price
                    # print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ bot_data['current_price'] 已更新为: {bot_data['current_price']}")

                def _on_order_update(event: dict):
                    try:
                        # 过滤其他交易对的订单事件
                        if event.get('symbol') != config['symbol']:
                            print(f"[{datetime.now().isoformat()}] {log_prefix} 🔇 忽略其他交易对事件: {event.get('symbol')}")
                            return

                        event_type = event.get('event_type')
                        print(f"[{datetime.now().isoformat()}] {log_prefix} 📥 收到订单事件: {event}")
                        
                        # 重连事件
                        if event_type == 'reconnected':
                            handle_reconnected(bot_data, exchange, log_prefix, _on_order_update)
                            return
                        
                        # 错误事件
                        if event_type == 'error':
                            print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ {event.get('error_message')}")
                            return
                        
                        # 订单取消
                        if event_type == 'order_cancelled':
                            order_id = event.get('order_id')
                            if event.get('side') == 'BUY':
                                bot_data['pending_buys'] = [
                                    pb for pb in bot_data.get('pending_buys', []) 
                                    if pb['order_id'] != order_id
                                ]
                                print(f"[{datetime.now().isoformat()}] {log_prefix} ⏭️ 买单取消 {order_id}")
                            elif event.get('side') == 'SELL':
                                bot_data['pending_sells'] = [
                                    ps for ps in bot_data.get('pending_sells', []) 
                                    if ps['order_id'] != order_id
                                ]
                                print(f"[{datetime.now().isoformat()}] {log_prefix} ⏭️ 卖单取消 {order_id}")
                            return
                        
                        # 买单成交
                        if event_type == 'order_filled' and event.get('side') == 'BUY':
                            handle_buy_order_filled(event, bot_data, exchange, config, 
                                                   tick_size, price_decimals, step_size, 
                                                   qty_decimals, log_prefix)
                        
                        # 卖单成交
                        if event_type == 'order_filled' and event.get('side') == 'SELL':
                            order_id = event.get('order_id')
                            # 从 pending_sells 移除
                            bot_data['pending_sells'] = [
                                ps for ps in bot_data.get('pending_sells', []) 
                                if ps['order_id'] != order_id
                            ]
                            print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ 卖单成交 {order_id}")
                    except Exception as e:
                        print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ 订单回调错误: {e}")
                        traceback.print_exc()

                exchange.start_ws(_on_price_update, _on_order_update)
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

            # 对齐下单数量
            aligned_quantity = math.floor(config['quantity'] / step_size) * step_size if step_size else config['quantity']
            aligned_quantity = round(aligned_quantity, qty_decimals)

            # 查询未完成订单
            open_orders = []
            open_buy_orders = []
            open_sell_orders = []
            query_success = False
            
            try:
                open_orders = exchange.get_open_orders()
                open_buy_orders = [o for o in open_orders if str(o.get('side')) == 'BUY']
                open_sell_orders = [o for o in open_orders if str(o.get('side')) == 'SELL']
                query_success = True

                # 恢复 pending_buys 和 pending_sells（仅启动时）
                if not pending_buys_recovered:
                    if not bot_data.get('pending_buys', []) and open_buy_orders:
                        for order in open_buy_orders:
                            bot_data.setdefault('pending_buys', []).append({
                                'order_id': str(order['orderId']),
                                'price': float(order['price']),
                                'quantity': float(order['origQty']),
                                'symbol': config['symbol'],
                                'user_id': user_id
                            })
                        print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ 恢复 {len(open_buy_orders)} 笔买单")
                    
                    if not bot_data.get('pending_sells', []) and open_sell_orders:
                        sell_offset_percent = config.get('sell_offset_percent', 0.5)
                        for order in open_sell_orders:
                            sell_price = float(order['price'])                            
                            # 方案1: 假设卖价来自 raw_sell_price
                            # sell_price ≈ buy_price * (1 + sell_offset/100)
                            # buy_price ≈ sell_price / (1 + sell_offset/100)
                            buy_price_from_raw = sell_price / (1 + sell_offset_percent / 100.0)
                            
                            # 方案2: 假设卖价来自 min_price (最低保护价)
                            # min_price ≈ buy_price * 1.002
                            # buy_price ≈ sell_price / 1.002
                            buy_price_from_min = sell_price / 1.002
                            
                            # 取较小值作为估算买入价 (更保守,确保不会低估)
                            estimated_buy_price = min(buy_price_from_raw, buy_price_from_min)
                            
                            # 按 tick_size 向下对齐
                            if tick_size and tick_size > 0:
                                estimated_buy_price = math.floor(estimated_buy_price / tick_size) * tick_size
                            
                            estimated_buy_price = round(estimated_buy_price, price_decimals)
                            
                            bot_data.setdefault('pending_sells', []).append({
                                'order_id': str(order['orderId']),
                                'price': sell_price,
                                'quantity': float(order['origQty']),
                                'buy_price': estimated_buy_price  # 反推的买入价
                            })
                            print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ 恢复 {order['orderId']}，buy_price={estimated_buy_price}")
                        print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ 恢复 {len(open_sell_orders)} 笔卖单")
                    
                    pending_buys_recovered = True

                # 改价买单
                if open_buy_orders:
                    # 计算买单目标价
                    target_price = calculate_buy_target_price(
                        current_price,
                        config.get('offset_percent', -0.5),
                        tick_size,
                        price_decimals
                    )
                    bot_data['target_price'] = target_price
                    
                    reprice_buy_orders(open_buy_orders, target_price, aligned_quantity, 
                                     bot_data, exchange, config, log_prefix)

                # 同步 pending_sells 状态（清理已成交或取消的卖单）
                # 注意: 只有当查询到卖单时才清理,避免API延迟导致误清理
                if bot_data.get('pending_sells') and open_sell_orders:
                    open_sell_order_ids = {str(o['orderId']) for o in open_sell_orders}
                    pending_sell_ids = {ps['order_id'] for ps in bot_data['pending_sells']}
                    removed_ids = pending_sell_ids - open_sell_order_ids
                    if removed_ids:
                        bot_data['pending_sells'] = [
                            ps for ps in bot_data['pending_sells'] 
                            if ps['order_id'] not in removed_ids
                        ]
                        print(f"[{datetime.now().isoformat()}] {log_prefix} 🔄 清理已完成卖单: {removed_ids}")
                
                # 动态调整卖单（默认禁用）
                if open_sell_orders:       
                    reprice_sell_orders(open_sell_orders, bot_data, exchange, config, 
                                      tick_size, price_decimals, step_size, qty_decimals, log_prefix)

            except Exception as e:
                print(f"[{datetime.now().isoformat()}] {log_prefix} ⚠️ 查询订单失败: {e}")
                # 查询失败时不下单，避免重复挂单
                query_success = False

            # 下新单（要求查询成功、没有未完成订单、没有待处理买单、没有待处理卖单、没有正在下单）
            has_pending_buys = bool(bot_data.get('pending_buys', []))
            has_pending_sells = bool(bot_data.get('pending_sells', []))
            if query_success and not open_orders and not has_pending_buys and not has_pending_sells and not bot_data.get('is_placing_order'):
                is_buy_enabled = (config.get('simulate_trading', 1) != 1)
                if is_buy_enabled:
                    # 计算买单目标价
                    target_price = calculate_buy_target_price(
                        current_price,
                        config.get('offset_percent', -0.1),
                        tick_size,
                        price_decimals
                    )
                    bot_data['target_price'] = target_price
                    
                    bot_data['is_placing_order'] = True
                    try:
                        order = exchange.order_limit_buy(
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
