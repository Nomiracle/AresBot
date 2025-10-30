import time
from datetime import datetime
from binance.exceptions import BinanceAPIException
from binance import ThreadedWebsocketManager
from database import get_user_id, insert_order, update_order_status
import math

# 结构调整：支持每个用户多个交易对的机器人
# user_bots = {
#   username: {
#       'bots': {
#           symbol: { 'running': bool, 'client': Client, 'config': {...}, 'current_price': float, 'target_price': float, 'pending_buys': [...], 'thread': Thread }
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

    print(f"[{datetime.now().isoformat()}] ▶️ 交易循环已启动 (user={username}, symbol={symbol})")

    price_filter = None
    lot_filter = None
    tick_size = None
    step_size = None

    while bot_data.get('running'):
        try:
            config = bot_data['config']
            client = bot_data['client']
            user_id = get_user_id(username)

            # 只在第一次循环中查询交易精度与过滤规则
            if price_filter is None or lot_filter is None:
                info = client.get_symbol_info(symbol=config['symbol'])
                price_filter = next(f for f in info['filters'] if f['filterType'] == 'PRICE_FILTER')
                lot_filter = next(f for f in info['filters'] if f['filterType'] == 'LOT_SIZE')

                tick_size = float(price_filter['tickSize'])
                step_size = float(lot_filter['stepSize'])

                print(f"[{datetime.now().isoformat()}] 🎯 交易规则加载完成：tick_size={tick_size}, step_size={step_size}")

            # 启动 WebSocket（仅一次）：行情与用户数据
            if not bot_data.get('ws_started'):
                def _on_ticker_msg(msg):
                    try:
                        # ThreadedWebsocketManager symbol ticker returns {'s': 'SYMBOL', 'c': 'lastPrice', ...}
                        last_price = msg.get('c') or msg.get('p') or msg.get('price')
                        if last_price is not None:
                            bot_data['current_price'] = float(last_price)
                    except Exception as e:
                        print(f"[{datetime.now().isoformat()}] ❌ [WS TICKER ERR] {e}")

                def _on_user_msg(msg):
                    try:
                        # 处理订单更新（executionReport）
                        if msg.get('e') == 'executionReport':
                            side = msg.get('S')  # BUY/SELL
                            status = msg.get('X')  # NEW/PARTIALLY_FILLED/FILLED...
                            order_id = str(msg.get('i'))
                            symbol_ = msg.get('s')
                            price_str = msg.get('p') or '0'
                            qty_str = msg.get('q') or '0'

                            if side == 'BUY' and status == 'FILLED':
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
                                price_decimals = int(abs(math.log10(tick_size))) if tick_size else 2
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

                                qty_decimals = int(abs(math.log10(step_size))) if step_size else 6
                                aligned_sell_qty = math.floor(qty_val / step_size) * step_size if step_size else qty_val
                                aligned_sell_qty = round(aligned_sell_qty, qty_decimals)

                                try:
                                    sell_order = client.order_limit_sell(
                                        symbol=symbol_,
                                        quantity=aligned_sell_qty,
                                        price=f"{aligned_sell_price}",
                                        timeInForce='GTC'
                                    )
                                    sell_order_id = str(sell_order.get('orderId'))
                                    insert_order(user_id, symbol_, str(aligned_sell_price), str(aligned_sell_qty),
                                                 'SELL', 'PLACED', sell_order_id)
                                    update_order_status(order_id, 'FILLED')
                                    print(f"[{datetime.now().isoformat()}] ✅ [WS] 买单 {order_id} 成交，自动挂卖单 {sell_order_id} @ {aligned_sell_price}")
                                except BinanceAPIException as e:
                                    print(f"[{datetime.now().isoformat()}] ❌ [WS SELL ERR] 卖单下单异常: {e}")
                                except Exception as e:
                                    print(f"[{datetime.now().isoformat()}] ❌ [WS SELL ERR] 卖单下单错误: {e}")

                                # 从 pending_buys 移除
                                bot_data['pending_buys'] = [pb for pb in bot_data.get('pending_buys', []) if pb['order_id'] != order_id]

                    except Exception as e:
                        print(f"[{datetime.now().isoformat()}] ❌ [WS USER ERR] {e}")

                try:
                    twm = ThreadedWebsocketManager(api_key=getattr(client, 'API_KEY', None), api_secret=getattr(client, 'API_SECRET', None))
                    twm.start()
                    # 行情：单币对 ticker
                    twm.start_symbol_ticker_socket(callback=_on_ticker_msg, symbol=config['symbol'])
                    # 用户数据：订单回报
                    twm.start_user_socket(callback=_on_user_msg)
                    bot_data['twm'] = twm
                    bot_data['ws_started'] = True
                    print(f"[{datetime.now().isoformat()}] ✅ WebSocket 已启动 (ticker + user_stream)")
                except Exception as e:
                    print(f"[{datetime.now().isoformat()}] ❌ WebSocket 启动失败: {e}")

            # 当前价格与目标价格
            current_price = float(bot_data.get('current_price') or client.get_symbol_ticker(symbol=config['symbol'])['price'])
            offset = config['offset_percent'] / 100.0
            target_price = current_price * (1 + offset)

            # 按 Binance 限制对齐价格精度
            aligned_price = math.floor(target_price / tick_size) * tick_size
            aligned_price = round(aligned_price, int(abs(math.log10(tick_size))))

            # 数量对齐
            quantity = float(config['quantity'])
            aligned_quantity = math.floor(quantity / step_size) * step_size
            aligned_quantity = round(aligned_quantity, int(abs(math.log10(step_size))))

            bot_data['current_price'] = current_price
            bot_data['target_price'] = aligned_price
            target_price = aligned_price

            is_buy_enabled = (config.get('simulate_trading', 1) != 1)
            print(f"[{datetime.now().isoformat()}] {username} - {config['symbol']} - 当前价: ${current_price} -> 计划挂买价: ${target_price}（数量: {aligned_quantity}）. 是否可以下单: {is_buy_enabled}")

            # 默认无未完成订单集合，便于后续流程判断
            open_buy_orders = []
            open_sell_orders = []

            try:
                open_orders = client.get_open_orders(symbol=config['symbol'])

                if open_orders:
                    # 区分买卖方向：不动 SELL；BUY 改为“价格替换”而非取消重下
                    open_buy_orders = [o for o in open_orders if str(o.get('side')) == 'BUY']
                    open_sell_orders = [o for o in open_orders if str(o.get('side')) == 'SELL']

                    if open_buy_orders:
                        open_ids = ', '.join([str(o['orderId']) for o in open_buy_orders])
                        print(f"[{datetime.now().isoformat()}] 🔁 [REPRICE] 检测到 {len(open_buy_orders)} 笔未完成买单 (ID: {open_ids})，尝试直接替换为新价格 {target_price}。")

                        for order in open_buy_orders:
                            try:
                                buy_price_str = f"{target_price}"
                                # 优先使用 python-binance 的 cancelReplace 接口
                                replace_fn = getattr(client, 'order_cancel_replace', None) or getattr(client, 'cancel_replace_order', None)
                                if replace_fn:
                                    resp = replace_fn(
                                        symbol=config['symbol'],
                                        side='BUY',
                                        type='LIMIT',
                                        timeInForce='GTC',
                                        quantity=aligned_quantity,
                                        price=buy_price_str,
                                        cancelOrderId=order['orderId'],
                                        cancelReplaceMode='STOP_ON_FAILURE'
                                    )
                                    new_part = resp.get('newOrderResult') if isinstance(resp, dict) else None
                                    new_order_id = str((new_part or {}).get('orderId') or order.get('orderId'))
                                    print(f"[{datetime.now().isoformat()}] ✅ [REPRICE] 订单 {order['orderId']} 已替换为新价格 {buy_price_str}，新订单ID={new_order_id}")

                                    # 同步 pending_buys 中的 order_id 与价格
                                    updated = []
                                    for p in bot_data.get('pending_buys', []):
                                        if p['order_id'] == str(order['orderId']):
                                            p['order_id'] = new_order_id
                                            p['price'] = float(buy_price_str)
                                        updated.append(p)
                                    bot_data['pending_buys'] = updated
                                else:
                                    print(f"[{datetime.now().isoformat()}] ⚠️ [REPRICE] 客户端未提供 cancelReplace 方法，跳过替换。")

                            except BinanceAPIException as e:
                                print(f"[{datetime.now().isoformat()}] ❌ [REPRICE ERR] 订单 {order['orderId']} 替换价格异常: {e}")
                            except Exception as e:
                                print(f"[{datetime.now().isoformat()}] ❌ [REPRICE ERR] 订单 {order['orderId']} 替换价格错误: {e}")

                    if open_sell_orders:
                        sell_ids = ', '.join([str(o['orderId']) for o in open_sell_orders])
                        print(f"[{datetime.now().isoformat()}] 📌 [CHECK] 保留 {len(open_sell_orders)} 笔未完成卖单 (ID: {sell_ids})。")
                else:
                    print(f"[{datetime.now().isoformat()}] ✅ [CHECK] 未发现未完成订单。")

            except BinanceAPIException as e:
                print(f"[{datetime.now().isoformat()}] ❌ [CHECK ERR] 查询未完成订单异常: {e}")
                time.sleep(config.get('interval', 1))
                continue
            except Exception as e:
                print(f"[{datetime.now().isoformat()}] ❌ [CHECK ERR] 查询未完成订单错误: {e}")
                time.sleep(config.get('interval', 1))
                continue

            # 只有在没有未完成买/卖单且没有待跟踪的买单时，才允许挂新买单
            has_pending_buys = bool(bot_data.get('pending_buys', []))
            can_place_buy = (not open_buy_orders) and (not open_sell_orders) and (not has_pending_buys)

            if not can_place_buy:
                print(f"[{datetime.now().isoformat()}] ⏭️ [SKIP] 存在未完成订单或待跟踪买单，跳过本次买单挂单。")
            else:
                try:
                    buy_price_str = f"{target_price}"
                    print(f"[{datetime.now().isoformat()}] ➡️ [EXECUTE] 尝试下新限价买单: 方向=BUY, 价格={buy_price_str}, 数量={config['quantity']}")

                    if is_buy_enabled:
                        order = client.order_limit_buy(
                            symbol=config['symbol'],
                            quantity=aligned_quantity,
                            price=buy_price_str,
                            timeInForce='GTC'
                        )
                        real_order_id = str(order.get('orderId') or order.get('orderId'))

                        insert_order(user_id, config['symbol'], buy_price_str, str(config['quantity']),
                                    'BUY', 'PLACED', real_order_id)

                        print(f"[{datetime.now().isoformat()}] ✅ [SUCCESS] 真实买单已下。**新订单ID={real_order_id}**，已写入 DB，等待撮合...")

                        bot_data.setdefault('pending_buys', []).append({
                            'order_id': real_order_id,
                            'price': float(buy_price_str),
                            'quantity': aligned_quantity,
                            'symbol': config['symbol'],
                            'user_id': user_id
                        })
                    else:
                        print(f"[{datetime.now().isoformat()}] ⏸️ [SWITCH OFF] 下单逻辑被禁用 (enable_buy_logic=False)，跳过本次挂单操作。")

                except BinanceAPIException as e:
                    print(f"[{datetime.now().isoformat()}] ❌ [FAILURE] Binance 下单异常: {e} (Symbol: {config['symbol']})")
                except Exception as e:
                    print(f"[{datetime.now().isoformat()}] ❌ [FAILURE] 下单错误: {e}")

            # 取消原先基于 REST 的订单状态轮询，改由 WS 用户数据流驱动

            time.sleep(config.get('interval', 1))

        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [LOOP ERR] 交易循环主流程错误: {e}")
            time.sleep(1)

    print(f"[{datetime.now().isoformat()}] ◼️ 交易循环已停止 (user={username}, symbol={symbol})")
