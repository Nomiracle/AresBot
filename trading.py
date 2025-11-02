import time
from datetime import datetime
from database import get_user_id, insert_order, update_order_status, get_order_buy_price
import math
import traceback

# 结构调整：支持每个用户多个交易对的机器人
# user_bots = {
#   username: {
#       'bots': {
#           symbol: { 'running': bool, 'exchange': BaseExchange, 'config': {...}, 'current_price': float, 'target_price': float, 'pending_buys': [...], 'thread': Thread }
#       }
#   }
# }
user_bots = {}


def trading_loop(username, symbol):
    user_data = user_bots.get(username)
    if not user_data:
        return
    bot_data = user_data.get('bots', {}).get(symbol)
    if not bot_data:
        return

    # 获取交易所名称（从配置或默认为 binance）
    exchange_name = bot_data.get('config', {}).get('exchange', 'binance').upper()
    
    # 日志前缀：[用户-交易所-交易对]
    log_prefix = f"[{username}-{exchange_name}-{symbol}]"
    
    print(f"[{datetime.now().isoformat()}] {log_prefix} ▶️ 交易循环已启动")

    tick_size = None
    step_size = None
    price_decimals = None
    qty_decimals = None
    
    # 标记是否已恢复 pending_buys
    pending_buys_recovered = False

    while bot_data.get('running'):
        try:
            # 调试：检查 bot_data 是否仍然有效
            if not bot_data:
                print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ [DEBUG] bot_data 为 None，退出循环")
                break
            
            running_status = bot_data.get('running')
            if not running_status:
                print(f"[{datetime.now().isoformat()}] {log_prefix} ⏹️ [DEBUG] running 状态为 False，正常退出循环")
                break
            
            config = bot_data['config']
            exchange = bot_data['exchange']
            user_id = get_user_id(username)

            # 只在第一次循环中查询交易精度与过滤规则
            if tick_size is None or step_size is None:
                try:
                    info = exchange.get_symbol_info(symbol=config['symbol'])
                    if info:
                        tick_size, price_decimals = exchange.get_price_precision(info)
                        step_size, qty_decimals = exchange.get_quantity_precision(info)
                        print(f"[{datetime.now().isoformat()}] {log_prefix} 🎯 交易规则加载完成：tick_size={tick_size}, step_size={step_size}")
                    else:
                        # 使用默认精度
                        tick_size, price_decimals = 0.01, 2
                        step_size, qty_decimals = 0.000001, 6
                        print(f"[{datetime.now().isoformat()}] {log_prefix} ⚠️ 无法获取交易规则，使用默认精度")
                except Exception as e:
                    # 使用默认精度
                    tick_size, price_decimals = 0.01, 2
                    step_size, qty_decimals = 0.000001, 6
                    print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ 获取交易规则失败: {e}，使用默认精度")
                    traceback.print_exc()

            # 启动价格和订单监听（仅一次）
            if not bot_data.get('monitor_started'):
                # 价格更新回调
                def _on_price_update(price: float):
                    bot_data['current_price'] = price
                
                # 订单更新回调
                def _on_order_update(event: dict):
                    try:
                        # 处理错误
                        if event.get('event_type') == 'error':
                            print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ [订单监听错误] {event.get('error_message')}")
                            return
                        
                        # 处理买单成交
                        if event.get('event_type') == 'order_filled' and event.get('side') == 'BUY':
                            order_id = event['order_id']
                            symbol_ = event['symbol']
                            price_str = event.get('price') or '0'
                            qty_str = event.get('quantity') or '0'
                            
                            # 🔒 去重检查：确保同一个买单只处理一次
                            # 如果订单ID不在 pending_buys 中，说明已经处理过了，跳过
                            is_pending = any(pb['order_id'] == order_id for pb in bot_data.get('pending_buys', []))
                            if not is_pending:
                                print(f"[{datetime.now().isoformat()}] {log_prefix} ⏭️ [去重] 买单 {order_id} 已处理过，跳过重复事件")
                                return
                            
                            # 买单成交 -> 自动挂卖单（按精度对齐）
                            try:
                                buy_price = float(price_str) if float(price_str) > 0 else None
                            except Exception:
                                buy_price = None
                            # 如果订单里没有价格（市价单情况），回退 pending 记录
                            if not buy_price:
                                for pb in bot_data.get('pending_buys', []):
                                    if pb['order_id'] == order_id:
                                        buy_price = pb.get('price')
                                        break
                            if not buy_price:
                                return

                            # 计算卖出价格
                            sell_offset = config.get('sell_offset_percent', 0.5) / 100.0
                            raw_sell_price = buy_price * (1 + sell_offset)
                            aligned_sell_price = math.floor(raw_sell_price / tick_size) * tick_size if tick_size else raw_sell_price
                            aligned_sell_price = round(aligned_sell_price, price_decimals)

                            # 获取实际成交数量（考虑手续费扣除）
                            print(f"[{datetime.now().isoformat()}] {log_prefix} 📊 [卖单数量计算] 开始计算卖单数量...")
                            
                            # 优先使用订单事件中的实际成交数量
                            executed_qty = None
                            try:
                                # 尝试从事件中获取 executedQty（实际成交数量，已扣除手续费）
                                if 'executedQty' in event:
                                    executed_qty = float(event['executedQty'])
                                    print(f"[{datetime.now().isoformat()}] {log_prefix} 📊 [卖单数量计算] 从事件中获取 executedQty: {executed_qty}")
                                elif qty_str and float(qty_str) > 0:
                                    executed_qty = float(qty_str)
                                    print(f"[{datetime.now().isoformat()}] {log_prefix} 📊 [卖单数量计算] 从事件中获取 quantity: {executed_qty}")
                            except Exception as e:
                                print(f"[{datetime.now().isoformat()}] {log_prefix} ⚠️ [卖单数量计算] 解析事件数量失败: {e}")
                            
                            # 如果事件中没有数量，从 pending_buys 中获取
                            if executed_qty is None:
                                for pb in bot_data.get('pending_buys', []):
                                    if pb['order_id'] == order_id:
                                        executed_qty = float(pb.get('quantity'))
                                        print(f"[{datetime.now().isoformat()}] {log_prefix} 📊 [卖单数量计算] 从 pending_buys 获取数量: {executed_qty}")
                                        break
                            
                            if executed_qty is None:
                                print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ [卖单数量计算] 无法获取成交数量，跳过挂卖单")
                                return
                            
                            # 考虑手续费扣除（假设手续费为 0.1%，实际到账 99.9%）
                            # 大多数交易所买入时手续费从成交金额中扣除，实际到账数量会少一些
                            fee_rate = config.get('fee_rate', 0.001)  # 默认 0.1% 手续费
                            actual_qty = executed_qty * (1 - fee_rate)
                            print(f"[{datetime.now().isoformat()}] {log_prefix} 📊 [卖单数量计算] 成交数量: {executed_qty}, 手续费率: {fee_rate*100}%, 扣除手续费后: {actual_qty}")
                            
                            # 按精度对齐（向下取整，确保不超过实际持仓）
                            if step_size and step_size > 0:
                                aligned_sell_qty = math.floor(actual_qty / step_size) * step_size
                                aligned_sell_qty = round(aligned_sell_qty, qty_decimals)
                            else:
                                aligned_sell_qty = round(actual_qty, qty_decimals)
                            
                            print(f"[{datetime.now().isoformat()}] {log_prefix} 📊 [卖单数量计算] 精度对齐后: {aligned_sell_qty} (step_size={step_size})")
                            
                            # 检查卖单数量是否有效
                            if aligned_sell_qty <= 0:
                                print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ [卖单数量计算] 对齐后数量为 0，无法挂卖单")
                                return

                            sell_success = False
                            try:
                                print(f"[{datetime.now().isoformat()}] {log_prefix} ➡️ [挂卖单] 价格={aligned_sell_price}, 数量={aligned_sell_qty}")
                                sell_order = exchange.order_limit_sell(
                                    symbol=symbol_,
                                    quantity=aligned_sell_qty,
                                    price=f"{aligned_sell_price}",
                                    timeInForce='GTC'
                                )
                                # 兼容不同交易所：Binance用'orderId'，Backpack用'id'
                                sell_order_id = str(sell_order.get('orderId') or sell_order.get('id'))
                                insert_order(user_id, symbol_, str(aligned_sell_price), str(aligned_sell_qty),
                                             'SELL', 'PLACED', sell_order_id, buy_price=str(buy_price))
                                update_order_status(order_id, 'FILLED')
                                sell_success = True
                                print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ 买单 {order_id} 成交 @ {buy_price}，自动挂卖单 {sell_order_id} @ {aligned_sell_price}，数量 {aligned_sell_qty}")
                            except Exception as e:
                                print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ [卖单错误] 卖单下单错误: {e}，将保留 pending_buy 以便重试")

                            # 只有卖单成功才从 pending_buys 移除
                            if sell_success:
                                bot_data['pending_buys'] = [pb for pb in bot_data.get('pending_buys', []) if pb['order_id'] != order_id]
                            else:
                                print(f"[{datetime.now().isoformat()}] {log_prefix} ⚠️ 买单 {order_id} 已成交但卖单下单失败，保留在 pending_buys 中等待重试")

                    except Exception as e:
                        print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ [订单回调错误] {e}")
                        traceback.print_exc()
                
                try:
                    # 启动价格监听
                    price_ok = exchange.start_price_monitor(config['symbol'], _on_price_update)
                    
                    # 启动订单监听
                    order_ok = exchange.start_order_monitor(config['symbol'], _on_order_update)
                    
                    bot_data['monitor_started'] = True
                    bot_data['order_monitor_enabled'] = order_ok
                    
                    if price_ok:
                        print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ 价格监听已启动")
                    if order_ok:
                        print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ 订单监听已启动")
                    else:
                        print(f"[{datetime.now().isoformat()}] {log_prefix} ℹ️ 订单监听未启用，将使用轮询模式")
                        
                except Exception as e:
                    print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ 启动监听失败: {e}")

            # 获取当前价格（由监听器更新）
            current_price = bot_data.get('current_price')
            if not current_price:
                # 监听器未提供价格，跳过本次循环
                print(f"[{datetime.now().isoformat()}] {log_prefix} ⚠️ 监听器未更新价格，跳过本次循环")
                time.sleep(config.get('interval', 1))
                continue
            
            offset = config['offset_percent'] / 100.0
            target_price = current_price * (1 + offset)

            # 按 Binance 限制对齐价格精度
            if tick_size and tick_size > 0:
                aligned_price = math.floor(target_price / tick_size) * tick_size
                aligned_price = round(aligned_price, int(abs(math.log10(tick_size))))
            else:
                aligned_price = round(target_price, 2)
                print(f"[{datetime.now().isoformat()}] {log_prefix} ⚠️ tick_size 无效，使用默认精度")

            # 数量对齐
            quantity = float(config['quantity'])
            if step_size and step_size > 0:
                aligned_quantity = math.floor(quantity / step_size) * step_size
                aligned_quantity = round(aligned_quantity, int(abs(math.log10(step_size))))
            else:
                aligned_quantity = round(quantity, 6)
                print(f"[{datetime.now().isoformat()}] {log_prefix} ⚠️ step_size 无效，使用默认精度")

            bot_data['current_price'] = current_price
            bot_data['target_price'] = aligned_price
            target_price = aligned_price

            is_buy_enabled = (config.get('simulate_trading', 1) != 1)
            print(f"[{datetime.now().isoformat()}] {log_prefix} 当前价: ${current_price} -> 计划挂买价: ${target_price}（数量: {aligned_quantity}）. 是否可以下单: {is_buy_enabled}")

            # 默认无未完成订单集合，便于后续流程判断
            open_buy_orders = []
            open_sell_orders = []

            try:
                open_orders = exchange.get_open_orders(symbol=config['symbol'])

                if open_orders:
                    # 区分买卖方向：不动 SELL；BUY 改为“价格替换”而非取消重下
                    open_buy_orders = [o for o in open_orders if str(o.get('side')) == 'BUY']
                    open_sell_orders = [o for o in open_orders if str(o.get('side')) == 'SELL']
                    
                    # 机器人启动时恢复 pending_buys：如果 pending_buys 为空且有未完成买单，则恢复
                    if not pending_buys_recovered and not bot_data.get('pending_buys', []) and open_buy_orders:
                        print(f"[{datetime.now().isoformat()}] {log_prefix} 🔄 [RECOVER] 检测到 {len(open_buy_orders)} 笔未完成买单，正在恢复到 pending_buys...")
                        for order in open_buy_orders:
                            bot_data.setdefault('pending_buys', []).append({
                                'order_id': str(order['orderId']),
                                'price': float(order['price']),
                                'quantity': float(order['origQty']),
                                'symbol': config['symbol'],
                                'user_id': user_id,
                                'created_at': 0  # 恢复的订单设为 0，立即可查询
                            })
                        print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ [RECOVER] 已恢复 {len(open_buy_orders)} 笔买单到 pending_buys")
                        pending_buys_recovered = True

                    if open_buy_orders:
                        open_ids = ', '.join([str(o['orderId']) for o in open_buy_orders])
                        print(f"[{datetime.now().isoformat()}] {log_prefix} 🔁 [REPRICE] 检测到 {len(open_buy_orders)} 笔未完成买单 (ID: {open_ids})，尝试直接替换为新价格 {target_price}。")

                        for order in open_buy_orders:
                            try:
                                buy_price_str = f"{target_price}"
                                
                                # 检查替换价格是否与当前挂单价格一致
                                current_order_price = float(order.get('price', 0))
                                if current_order_price == target_price:
                                    print(f"[{datetime.now().isoformat()}] {log_prefix} ⏭️ [REPRICE SKIP] 订单 {order['orderId']} 当前价格 {current_order_price} 与目标价格 {target_price} 一致，跳过替换")
                                    continue
                                
                                # 使用适配器的 cancel_replace_order 方法
                                try:
                                    resp = exchange.cancel_replace_order(
                                        symbol=config['symbol'],
                                        side='BUY',
                                        order_type='LIMIT',
                                        quantity=aligned_quantity,
                                        price=buy_price_str,
                                        cancel_order_id=str(order['orderId']),
                                        timeInForce='GTC',
                                        cancelReplaceMode='STOP_ON_FAILURE'
                                    )
                                    # 提取新订单ID：newOrderResponse 包含新订单信息
                                    new_order_id = None
                                    if isinstance(resp, dict):
                                        # Binance cancelReplace 响应结构：
                                        # newOrderResult: 'SUCCESS' (字符串状态)
                                        # newOrderResponse: {...} (新订单详情)
                                        new_order_data = resp.get('newOrderResponse', {})
                                        if isinstance(new_order_data, dict):
                                            # 兼容不同交易所：Binance用'orderId'，Backpack用'id'
                                            new_order_id = str(new_order_data.get('orderId') or new_order_data.get('id') or order['orderId'])
                                        else:
                                            # 回退：尝试顶层 orderId 或 id
                                            new_order_id = str(resp.get('orderId') or resp.get('id') or order['orderId'])
                                    else:
                                        # 非字典响应，保持原订单ID
                                        new_order_id = str(order['orderId'])
                                        print(f"[{datetime.now().isoformat()}] ⚠️ [REPRICE] 响应非字典类型，无法提取新订单ID，保持原ID")
                                    
                                    # 只有成功提取到新订单ID才更新 pending_buys
                                    if new_order_id and new_order_id != str(order['orderId']):
                                        print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ [REPRICE] 订单 {order['orderId']} 已替换为新价格 {buy_price_str}，新订单ID={new_order_id}")
                                        
                                        # 同步 pending_buys 中的 order_id 与价格
                                        updated = []
                                        for p in bot_data.get('pending_buys', []):
                                            if p['order_id'] == str(order['orderId']):
                                                p['order_id'] = new_order_id
                                                p['price'] = float(buy_price_str)
                                            updated.append(p)
                                        bot_data['pending_buys'] = updated
                                        
                                        # 更新数据库：标记旧订单为已替换，插入新订单
                                        update_order_status(str(order['orderId']), 'REPLACED')
                                        insert_order(user_id, config['symbol'], buy_price_str, str(aligned_quantity),
                                                    'BUY', 'PLACED', new_order_id)
                                    else:
                                        # 无法获取新订单ID，从pending_buys中移除以避免永久阻塞
                                        print(f"[{datetime.now().isoformat()}] {log_prefix} ⚠️ [REPRICE] 订单 {order['orderId']} 价格更新为 {buy_price_str}，但未获取到新订单ID，从pending_buys中移除")
                                        bot_data['pending_buys'] = [p for p in bot_data.get('pending_buys', []) if p['order_id'] != str(order['orderId'])]
                                        update_order_status(str(order['orderId']), 'CANCELLED')
                                except Exception as e:
                                    print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ [REPRICE ERR] 订单 {order['orderId']} 替换价格错误: {e}")
                                    # 替换失败，从pending_buys中移除以避免永久阻塞
                                    bot_data['pending_buys'] = [p for p in bot_data.get('pending_buys', []) if p['order_id'] != str(order['orderId'])]
                                    update_order_status(str(order['orderId']), 'FAILED')
                            except Exception as e:
                                print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ [REPRICE ERR] 订单 {order['orderId']} 外层错误: {e}")
                                # 外层错误也需要从pending_buys中移除以避免永久阻塞
                                bot_data['pending_buys'] = [p for p in bot_data.get('pending_buys', []) if p['order_id'] != str(order['orderId'])]
                                update_order_status(str(order['orderId']), 'FAILED')

                    if open_sell_orders:
                        sell_ids = ', '.join([str(o['orderId']) for o in open_sell_orders])
                        print(f"[{datetime.now().isoformat()}] {log_prefix} 📌 [CHECK] 检测到 {len(open_sell_orders)} 笔未完成卖单 (ID: {sell_ids})，正在检查是否需要调整价格...")
                        
                        # 对每个卖单，根据实时价格计算目标卖价并决定是否修改
                        for sell_order in open_sell_orders:
                            try:
                                sell_order_id = str(sell_order['orderId'])
                                current_sell_price = float(sell_order.get('price', 0))
                                sell_quantity = float(sell_order.get('origQty', 0))
                                
                                # 从数据库中查找对应的买入价格
                                buy_price = get_order_buy_price(sell_order_id)
                                
                                if not buy_price:
                                    # 如果数据库中没有记录买入价格（可能是旧订单），使用反推方式
                                    sell_offset = config.get('sell_offset_percent', 0.5) / 100.0
                                    buy_price = current_sell_price / (1 + sell_offset)
                                    print(f"[{datetime.now().isoformat()}] {log_prefix} ⚠️ [SELL CHECK] 订单 {sell_order_id} 未找到买入价格记录，使用反推价格 {buy_price}")
                                
                                # 根据实时价格计算新的目标卖价
                                sell_offset = config.get('sell_offset_percent', 0.5) / 100.0
                                raw_target_sell_price = current_price * (1 + sell_offset)
                                
                                # 对齐价格精度
                                price_decimals = int(abs(math.log10(tick_size))) if tick_size else 2
                                target_sell_price = math.floor(raw_target_sell_price / tick_size) * tick_size if tick_size else raw_target_sell_price
                                target_sell_price = round(target_sell_price, price_decimals)
                                
                                # 计算最低可接受卖价（买入价 + 0.2% 手续费保护）
                                min_acceptable_price = buy_price * 1.002
                                min_acceptable_price = math.ceil(min_acceptable_price / tick_size) * tick_size if tick_size else min_acceptable_price
                                min_acceptable_price = round(min_acceptable_price, price_decimals)
                                
                                print(f"[{datetime.now().isoformat()}] {log_prefix} 🔍 [SELL CHECK] 订单 {sell_order_id}: 买入价={buy_price}, 当前卖价={current_sell_price}, 目标卖价={target_sell_price}, 最低可接受价={min_acceptable_price}")
                                
                                # 判断是否需要修改卖单价格
                                if target_sell_price > min_acceptable_price:
                                    # 目标价格高于最低可接受价格，可以修改
                                    if abs(target_sell_price - current_sell_price) < tick_size * 0.5:
                                        # 价格变化太小，跳过
                                        print(f"[{datetime.now().isoformat()}] {log_prefix} ⏭️ [SELL SKIP] 订单 {sell_order_id} 价格变化太小，跳过修改")
                                        continue
                                    
                                    # 使用 cancel_replace 修改卖单价格
                                    try:
                                        # 对齐数量精度
                                        qty_decimals = int(abs(math.log10(step_size))) if step_size else 6
                                        aligned_sell_qty = math.floor(sell_quantity / step_size) * step_size if step_size else sell_quantity
                                        aligned_sell_qty = round(aligned_sell_qty, qty_decimals)
                                        
                                        resp = exchange.cancel_replace_order(
                                            symbol=config['symbol'],
                                            side='SELL',
                                            order_type='LIMIT',
                                            quantity=aligned_sell_qty,
                                            price=f"{target_sell_price}",
                                            cancel_order_id=sell_order_id,
                                            timeInForce='GTC',
                                            cancelReplaceMode='STOP_ON_FAILURE'
                                        )
                                        
                                        # 提取新订单ID
                                        new_order_id = None
                                        if isinstance(resp, dict):
                                            new_order_data = resp.get('newOrderResponse', {})
                                            if isinstance(new_order_data, dict):
                                                new_order_id = str(new_order_data.get('orderId') or new_order_data.get('id') or sell_order_id)
                                            else:
                                                new_order_id = str(resp.get('orderId') or resp.get('id') or sell_order_id)
                                        else:
                                            new_order_id = sell_order_id
                                        
                                        print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ [SELL REPRICE] 卖单 {sell_order_id} 价格已从 {current_sell_price} 更新为 {target_sell_price}，新订单ID={new_order_id}")
                                        
                                        # 更新数据库
                                        if new_order_id != sell_order_id:
                                            update_order_status(sell_order_id, 'REPLACED')
                                            insert_order(user_id, config['symbol'], f"{target_sell_price}", str(aligned_sell_qty),
                                                        'SELL', 'PLACED', new_order_id, buy_price=str(buy_price))
                                    except Exception as e:
                                        print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ [SELL REPRICE ERR] 修改卖单 {sell_order_id} 价格失败: {e}")
                                else:
                                    # 目标价格低于最低可接受价格，保持不变
                                    print(f"[{datetime.now().isoformat()}] {log_prefix} 📌 [SELL KEEP] 订单 {sell_order_id} 目标价格 {target_sell_price} 低于最低可接受价格 {min_acceptable_price}，保持当前价格 {current_sell_price}")
                            
                            except Exception as e:
                                print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ [SELL CHECK ERR] 检查卖单错误: {e}")
                                traceback.print_exc()
                else:
                    print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ [CHECK] 未发现交易所未完成订单。")

            except Exception as e:
                print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ [CHECK ERR] 查询未完成订单错误: {e}")
                time.sleep(config.get('interval', 1))
                continue

            # 🔍 优化：只有当 open_orders 为空但 pending_buys 有数据时，才需要查询订单状态
            # 原因：如果 open_orders 有数据，说明订单还在交易所，会通过改价逻辑或 WebSocket 处理
            #      如果 open_orders 为空但 pending_buys 有数据，说明订单可能已成交，需要主动查询确认
            has_pending_buys = bool(bot_data.get('pending_buys', []))
            if not open_buy_orders and has_pending_buys:
                pending_count = len(bot_data.get('pending_buys', []))
                print(f"[{datetime.now().isoformat()}] {log_prefix} 🔍 [CHECK] 交易所无未完成买单，但存在 {pending_count} 笔待跟踪买单，检查是否成交...")
                
                # 如果订单监听未启用，使用 adapter 的轮询方法检查订单状态
                if not bot_data.get('order_monitor_enabled'):
                    # 调用 adapter 的 check_pending_orders 方法
                    # 订单成交会通过 _on_order_update 回调处理，回调中会自动挂卖单并从 pending_buys 移除
                    exchange.check_pending_orders(bot_data.get('pending_buys', []))
                
                time.sleep(config.get('interval', 1))
                continue

            # 只有在没有未完成买/卖单，且没有待跟踪买单时，才允许挂新买单
            can_place_buy = (not open_buy_orders) and (not open_sell_orders) and (not has_pending_buys)

            if not can_place_buy:
                skip_reasons = []
                if open_buy_orders:
                    skip_reasons.append(f"{len(open_buy_orders)}笔未完成买单")
                if open_sell_orders:
                    skip_reasons.append(f"{len(open_sell_orders)}笔未完成卖单")
                if has_pending_buys:
                    skip_reasons.append(f"{len(bot_data.get('pending_buys', []))}笔待跟踪买单")
                reason_text = "、".join(skip_reasons)
                print(f"[{datetime.now().isoformat()}] {log_prefix} ⏭️ [SKIP] 存在{reason_text}，跳过本次买单挂单。")
            else:
                try:
                    buy_price_str = f"{target_price}"
                    print(f"[{datetime.now().isoformat()}] {log_prefix} ➡️ [EXECUTE] 尝试下新限价买单: 方向=BUY, 价格={buy_price_str}, 数量={config['quantity']}")

                    if is_buy_enabled:
                        order = exchange.order_limit_buy(
                            symbol=config['symbol'],
                            quantity=aligned_quantity,
                            price=buy_price_str,
                            timeInForce='GTC'
                        )
                        # 兼容不同交易所：Binance用'orderId'，Backpack用'id'
                        real_order_id = str(order.get('orderId') or order.get('id'))

                        insert_order(user_id, config['symbol'], buy_price_str, str(config['quantity']),
                                    'BUY', 'PLACED', real_order_id)

                        print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ [SUCCESS] 真实买单已下。**新订单ID={real_order_id}**，已写入 DB，等待撮合...")

                        bot_data.setdefault('pending_buys', []).append({
                            'order_id': real_order_id,
                            'price': float(buy_price_str),
                            'quantity': aligned_quantity,
                            'symbol': config['symbol'],
                            'user_id': user_id,
                            'created_at': datetime.now().timestamp()  # 记录创建时间
                        })
                    else:
                        print(f"[{datetime.now().isoformat()}] {log_prefix} ⏸️ [SWITCH OFF] 下单逻辑被禁用 (enable_buy_logic=False)，跳过本次挂单操作。")

                except Exception as e:
                    print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ [FAILURE] 下单错误: {e}")

            time.sleep(config.get('interval', 1))

        except Exception as e:
            print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ [LOOP ERR] 交易循环主流程错误: {e}")
            print(f"[{datetime.now().isoformat()}] {log_prefix} 📋 [TRACEBACK]")
            traceback.print_exc()
            time.sleep(1)

    # 循环结束，打印退出原因
    final_running = bot_data.get('running') if bot_data else None
    print(f"[{datetime.now().isoformat()}] {log_prefix} ◼️ 交易循环已停止")
    print(f"[{datetime.now().isoformat()}] {log_prefix} 📊 [DEBUG] 退出时状态: bot_data存在={bot_data is not None}, running={final_running}")
