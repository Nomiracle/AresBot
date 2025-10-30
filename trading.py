import time
from datetime import datetime
from database import get_user_id, insert_order, update_order_status
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

    price_filter = None
    lot_filter = None
    tick_size = None
    step_size = None
    
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
            if price_filter is None or lot_filter is None:
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

            # 启动 WebSocket（仅一次）：行情与用户数据
            if not bot_data.get('ws_started'):
                def _on_ticker_msg(msg):
                    try:
                        # 使用适配器解析行情消息
                        price = exchange.parse_ticker_message(msg)
                        if price is not None:
                            bot_data['current_price'] = price
                    except Exception as e:
                        print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ [WS TICKER ERR] {e}")

                def _on_user_msg(msg):
                    try:
                        # 使用适配器解析用户消息
                        event = exchange.parse_user_message(msg)
                        if not event:
                            return
                        
                        # 处理错误
                        if event.get('event_type') == 'error':
                            print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ [WS USER ERROR] {event.get('error_message')}")
                            return
                        
                        # 处理买单成交
                        if event.get('event_type') == 'order_filled' and event.get('side') == 'BUY':
                            order_id = event['order_id']
                            symbol_ = event['symbol']
                            price_str = event.get('price') or '0'
                            qty_str = event.get('quantity') or '0'
                            
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

                            sell_offset = config.get('sell_offset_percent', 0.5) / 100.0
                            raw_sell_price = buy_price * (1 + sell_offset)
                            aligned_sell_price = math.floor(raw_sell_price / tick_size) * tick_size if tick_size else raw_sell_price
                            aligned_sell_price = round(aligned_sell_price, price_decimals)

                            try:
                                qty_val = float(qty_str) if float(qty_str) > 0 else None
                            except Exception:
                                qty_val = None
                            if qty_val is None:
                                for pb in bot_data.get('pending_buys', []):
                                    if pb['order_id'] == order_id:
                                        qty_val = float(pb.get('quantity'))
                                        break
                            if qty_val is None:
                                return

                            aligned_sell_qty = math.floor(qty_val / step_size) * step_size if step_size else qty_val
                            aligned_sell_qty = round(aligned_sell_qty, qty_decimals)

                            sell_success = False
                            try:
                                sell_order = exchange.order_limit_sell(
                                    symbol=symbol_,
                                    quantity=aligned_sell_qty,
                                    price=f"{aligned_sell_price}",
                                    timeInForce='GTC'
                                )
                                sell_order_id = str(sell_order.get('orderId'))
                                insert_order(user_id, symbol_, str(aligned_sell_price), str(aligned_sell_qty),
                                             'SELL', 'PLACED', sell_order_id)
                                update_order_status(order_id, 'FILLED')
                                sell_success = True
                                print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ [WS] 买单 {order_id} 成交，自动挂卖单 {sell_order_id} @ {aligned_sell_price}")
                            except Exception as e:
                                print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ [WS SELL ERR] 卖单下单错误: {e}，将保留 pending_buy 以便重试")

                            # 只有卖单成功才从 pending_buys 移除
                            if sell_success:
                                bot_data['pending_buys'] = [pb for pb in bot_data.get('pending_buys', []) if pb['order_id'] != order_id]
                            else:
                                print(f"[{datetime.now().isoformat()}] {log_prefix} ⚠️ [WS] 买单 {order_id} 已成交但卖单下单失败，保留在 pending_buys 中等待重试")

                    except Exception as e:
                        print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ [WS USER ERR] {e}")
                        traceback.print_exc()

                try:
                    # 使用适配器启动 WebSocket
                    ws_result = exchange.start_websocket(
                        symbol=config['symbol'],
                        on_ticker=_on_ticker_msg,
                        on_user=_on_user_msg
                    )
                    
                    bot_data['twm'] = ws_result['manager']
                    bot_data['ws_started'] = True
                    bot_data['ws_user_enabled'] = ws_result['user_enabled']
                    
                    if not ws_result['user_enabled']:
                        print(f"[{datetime.now().isoformat()}] {log_prefix} ℹ️ 用户数据流未启用，将使用 REST 轮询作为回退方案")
                except Exception as e:
                    print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ WebSocket 启动失败: {e}")

            # 当前价格与目标价格
            current_price = bot_data.get('current_price')
            if not current_price:
                try:
                    ticker = exchange.get_symbol_ticker(symbol=config['symbol'])
                    if ticker and 'price' in ticker:
                        current_price = float(ticker['price'])
                    else:
                        print(f"[{datetime.now().isoformat()}] {log_prefix} ⚠️ 无法获取当前价格，跳过本次循环")
                        time.sleep(config.get('interval', 1))
                        continue
                except Exception as e:
                    print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ 获取价格失败: {e}")
                    traceback.print_exc()
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
                                'user_id': user_id
                            })
                        print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ [RECOVER] 已恢复 {len(open_buy_orders)} 笔买单到 pending_buys")
                        pending_buys_recovered = True

                    if open_buy_orders:
                        open_ids = ', '.join([str(o['orderId']) for o in open_buy_orders])
                        print(f"[{datetime.now().isoformat()}] {log_prefix} 🔁 [REPRICE] 检测到 {len(open_buy_orders)} 笔未完成买单 (ID: {open_ids})，尝试直接替换为新价格 {target_price}。")

                        for order in open_buy_orders:
                            try:
                                buy_price_str = f"{target_price}"
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
                                            new_order_id = str(new_order_data.get('orderId', order['orderId']))
                                        else:
                                            # 回退：尝试顶层 orderId
                                            new_order_id = str(resp.get('orderId', order['orderId']))
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
                                        print(f"[{datetime.now().isoformat()}] {log_prefix} ⚠️ [REPRICE] 订单 {order['orderId']} 价格更新为 {buy_price_str}，但未获取到新订单ID")
                                except Exception as e:
                                    print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ [REPRICE ERR] 订单 {order['orderId']} 替换价格错误: {e}")
                            except Exception as e:
                                print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ [REPRICE ERR] 订单 {order['orderId']} 外层错误: {e}")

                    if open_sell_orders:
                        sell_ids = ', '.join([str(o['orderId']) for o in open_sell_orders])
                        print(f"[{datetime.now().isoformat()}] {log_prefix} 📌 [CHECK] 保留 {len(open_sell_orders)} 笔未完成卖单 (ID: {sell_ids})。")
                else:
                    print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ [CHECK] 未发现未完成订单。")

            except Exception as e:
                print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ [CHECK ERR] 查询未完成订单错误: {e}")
                time.sleep(config.get('interval', 1))
                continue

            # 只有在没有未完成买/卖单且没有待跟踪的买单时，才允许挂新买单
            has_pending_buys = bool(bot_data.get('pending_buys', []))
            can_place_buy = (not open_buy_orders) and (not open_sell_orders) and (not has_pending_buys)

            if not can_place_buy:
                print(f"[{datetime.now().isoformat()}] {log_prefix} ⏭️ [SKIP] 存在未完成订单或待跟踪买单，跳过本次买单挂单。")
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
                        real_order_id = str(order.get('orderId') or order.get('orderId'))

                        insert_order(user_id, config['symbol'], buy_price_str, str(config['quantity']),
                                    'BUY', 'PLACED', real_order_id)

                        print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ [SUCCESS] 真实买单已下。**新订单ID={real_order_id}**，已写入 DB，等待撮合...")

                        bot_data.setdefault('pending_buys', []).append({
                            'order_id': real_order_id,
                            'price': float(buy_price_str),
                            'quantity': aligned_quantity,
                            'symbol': config['symbol'],
                            'user_id': user_id
                        })
                    else:
                        print(f"[{datetime.now().isoformat()}] {log_prefix} ⏸️ [SWITCH OFF] 下单逻辑被禁用 (enable_buy_logic=False)，跳过本次挂单操作。")

                except Exception as e:
                    print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ [FAILURE] 下单错误: {e}")

            # 当用户数据流不可用时，使用 REST 轮询作为回退，确保买单成交后能挂卖单
            if not bot_data.get('ws_user_enabled'):
                pending = bot_data.get('pending_buys', [])
                if pending:
                    remaining = []
                    for pb in pending:
                        try:
                            order_info = exchange.get_order(symbol=pb['symbol'], orderId=pb['order_id'])
                            status = order_info.get('status')

                            if status == 'FILLED':
                                buy_price = float(order_info.get('price')) if order_info.get('price') else pb['price']
                                if not buy_price:
                                    buy_price = pb['price']

                                sell_offset = config.get('sell_offset_percent', 0.5) / 100.0
                                raw_sell_price = buy_price * (1 + sell_offset)

                                price_decimals = int(abs(math.log10(tick_size))) if tick_size else 2
                                aligned_sell_price = math.floor(raw_sell_price / tick_size) * tick_size if tick_size else raw_sell_price
                                aligned_sell_price = round(aligned_sell_price, price_decimals)

                                sell_qty = float(pb['quantity'])
                                qty_decimals = int(abs(math.log10(step_size))) if step_size else 6
                                aligned_sell_qty = math.floor(sell_qty / step_size) * step_size if step_size else sell_qty
                                aligned_sell_qty = round(aligned_sell_qty, qty_decimals)

                                sell_success = False
                                try:
                                    sell_order = exchange.order_limit_sell(
                                        symbol=pb['symbol'],
                                        quantity=aligned_sell_qty,
                                        price=f"{aligned_sell_price}",
                                        timeInForce='GTC'
                                    )
                                    sell_order_id = str(sell_order.get('orderId'))

                                    insert_order(pb['user_id'], pb['symbol'], str(aligned_sell_price), str(aligned_sell_qty),
                                                 'SELL', 'PLACED', sell_order_id)
                                    update_order_status(pb['order_id'], 'FILLED')
                                    sell_success = True

                                    print(f"[{datetime.now().isoformat()}] {log_prefix} ✅ [REST-FALLBACK] 买单 {pb['order_id']} 成交，自动挂卖单 {sell_order_id} @ {aligned_sell_price}")
                                except Exception as e:
                                    print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ [SELL ERR] 卖单下单错误: {e}，将保留 pending_buy 以便重试")
                                
                                # 只有卖单成功才不加入 remaining（即移除），失败则保留以便重试
                                if not sell_success:
                                    remaining.append(pb)
                                    print(f"[{datetime.now().isoformat()}] {log_prefix} ⚠️ [REST-FALLBACK] 买单 {pb['order_id']} 已成交但卖单下单失败，保留在 pending_buys 中等待重试")
                            else:
                                remaining.append(pb)
                        except Exception as e:
                            print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ [POLL ERR] 轮询订单错误: {e}")
                            remaining.append(pb)

                    bot_data['pending_buys'] = remaining

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
