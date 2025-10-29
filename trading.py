import time
from datetime import datetime
from binance.exceptions import BinanceAPIException
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

            ticker = client.get_symbol_ticker(symbol=config['symbol'])

            # 只在第一次循环中查询交易精度与过滤规则
            if price_filter is None or lot_filter is None:
                info = client.get_symbol_info(symbol=config['symbol'])
                price_filter = next(f for f in info['filters'] if f['filterType'] == 'PRICE_FILTER')
                lot_filter = next(f for f in info['filters'] if f['filterType'] == 'LOT_SIZE')

                tick_size = float(price_filter['tickSize'])
                step_size = float(lot_filter['stepSize'])

                print(f"[{datetime.now().isoformat()}] 🎯 交易规则加载完成：tick_size={tick_size}, step_size={step_size}")

            # 当前价格与目标价格
            current_price = float(ticker['price'])
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

            try:
                open_orders = client.get_open_orders(symbol=config['symbol'])

                if open_orders:
                    open_ids = ', '.join([str(o['orderId']) for o in open_orders])
                    print(f"[{datetime.now().isoformat()}] ⚠️ [CHECK] 发现 {len(open_orders)} 笔未完成订单 (ID: {open_ids})，准备**取消并重新挂单**。")

                    for order in open_orders:
                        try:
                            client.cancel_order(symbol=config['symbol'], orderId=order['orderId'])
                            print(f"[{datetime.now().isoformat()}] ✅ [CANCEL] 成功取消订单 ID: {order['orderId']}")

                            bot_data['pending_buys'] = [
                                p for p in bot_data.get('pending_buys', [])
                                if p['order_id'] != str(order['orderId'])
                            ]

                        except BinanceAPIException as e:
                            print(f"[{datetime.now().isoformat()}] ❌ [CANCEL ERR] 取消订单 ID: {order['orderId']} 异常: {e}")
                        except Exception as e:
                            print(f"[{datetime.now().isoformat()}] ❌ [CANCEL ERR] 取消订单 ID: {order['orderId']} 错误: {e}")
                else:
                    print(f"[{datetime.now().isoformat()}] ✅ [CHECK] 未发现未完成订单，准备执行**限价买单**。")

            except BinanceAPIException as e:
                print(f"[{datetime.now().isoformat()}] ❌ [CHECK ERR] 查询未完成订单异常: {e}")
                time.sleep(config.get('interval', 1))
                continue
            except Exception as e:
                print(f"[{datetime.now().isoformat()}] ❌ [CHECK ERR] 查询未完成订单错误: {e}")
                time.sleep(config.get('interval', 1))
                continue

            try:
                buy_price_str = f"{target_price}"
                print(f"[{datetime.now().isoformat()}] ➡️ [EXECUTE] 尝试下新限价买单: 方向=BUY, 价格={buy_price_str}, 数量={config['quantity']}")

                if is_buy_enabled:
                    order = client.order_limit_buy(
                        symbol=config['symbol'],
                        quantity=config['quantity'],
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
                        'quantity': config['quantity'],
                        'symbol': config['symbol'],
                        'user_id': user_id
                    })
                else:
                    print(f"[{datetime.now().isoformat()}] ⏸️ [SWITCH OFF] 下单逻辑被禁用 (enable_buy_logic=False)，跳过本次挂单操作。")

            except BinanceAPIException as e:
                print(f"[{datetime.now().isoformat()}] ❌ [FAILURE] Binance 下单异常: {e} (Symbol: {config['symbol']})")
            except Exception as e:
                print(f"[{datetime.now().isoformat()}] ❌ [FAILURE] 下单错误: {e}")

            pending = bot_data.get('pending_buys', [])
            if pending:
                remaining = []
                for pb in pending:
                    try:
                        order_info = client.get_order(symbol=pb['symbol'], orderId=int(pb['order_id']))
                        status = order_info.get('status')

                        print(f"[{datetime.now().isoformat()}] 🔄 [POLL] 轮询订单 {pb['order_id']} 状态: {status}")

                        if status == 'FILLED':
                            buy_price = float(order_info.get('price')) if order_info.get('price') else pb['price']
                            if not buy_price:
                                buy_price = pb['price']

                            sell_offset = config.get('sell_offset_percent', 0.5) / 100.0
                            sell_price = round(buy_price * (1 + sell_offset), 2)

                            try:
                                sell_order = client.order_limit_sell(
                                    symbol=pb['symbol'],
                                    quantity=pb['quantity'],
                                    price=f"{sell_price:.2f}",
                                    timeInForce='GTC'
                                )
                                sell_order_id = str(sell_order.get('orderId'))

                                insert_order(pb['user_id'], pb['symbol'], str(sell_price), str(pb['quantity']),
                                           'SELL', 'PLACED', sell_order_id)
                                update_order_status(pb['order_id'], 'FILLED')

                                print(f"[{datetime.now().isoformat()}] ✅ [FILLED] 买单 {pb['order_id']} 已成交，自动挂卖单 **{sell_order_id}** @ {sell_price}")
                            except BinanceAPIException as e:
                                print(f"[{datetime.now().isoformat()}] ❌ [SELL ERR] 卖单下单异常: {e}")
                            except Exception as e:
                                print(f"[{datetime.now().isoformat()}] ❌ [SELL ERR] 卖单下单错误: {e}")
                        else:
                            remaining.append(pb)
                    except BinanceAPIException as e:
                        print(f"[{datetime.now().isoformat()}] ❌ [POLL ERR] 查询订单 {pb['order_id']} 状态异常: {e}")
                        remaining.append(pb)
                    except Exception as e:
                        print(f"[{datetime.now().isoformat()}] ❌ [POLL ERR] 轮询订单错误: {e}")
                        remaining.append(pb)

                bot_data['pending_buys'] = remaining

            time.sleep(config.get('interval', 1))

        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [LOOP ERR] 交易循环主流程错误: {e}")
            time.sleep(1)

    print(f"[{datetime.now().isoformat()}] ◼️ 交易循环已停止 (user={username}, symbol={symbol})")
