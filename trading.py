import time
import threading
import uuid
from datetime import datetime

# 用于保护 pending_buys 并发修改的锁
_pending_buys_lock = threading.Lock()
from database import get_user_id, insert_order, update_order_status
from notification import DingTalkNotification
import math
import traceback
from crash_logger import log_crash

user_bots = {}


def send_order_notification(username, side, symbol, price, quantity, order_id, market_info=None, cost_info=None):
    """发送订单成交通知（异步执行，不阻塞主线程）
    
    Args:
        username: 用户名
        side: 订单方向 ('BUY' 或 'SELL')
        symbol: 交易对
        price: 成交价格
        quantity: 成交数量
        order_id: 订单号
        market_info: 市场信息（可选，由 exchange.get_notification_info() 提供）
        cost_info: 成本信息（可选，卖单时显示成本价）
    """
    if not username:
        return
    
    def _send():
        try:
            notifier = DingTalkNotification(username=username)
            side_emoji = "🟢" if side == 'BUY' else "🔴"
            side_text = "买" if side == 'BUY' else "卖"
            
            # 构建消息
            time_str = datetime.now().strftime("%H:%M:%S")
            msg = f"[{time_str}] {side_emoji} {symbol} {side_text} {price}"
            
            # 添加成本信息（卖单时显示）
            if cost_info:
                msg = f"{msg} ({cost_info})"
            
            msg = f"{msg}@{quantity} - {order_id}"
            
            # 添加市场信息
            if market_info:
                msg = f"[{market_info}] {msg}"
            
            notifier.send(msg)
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ⚠️ 发送钉钉通知失败: {e}")
    
    threading.Thread(target=_send, daemon=True).start()



def place_sell_order_with_retry(exchange, bot_data, config, buy_order_id, buy_price, 
                                 quantity, sell_price, current_price, log_prefix, 
                                 retry_count=0, max_retry=3):
    """挂卖单（带递归重试）
    
    Args:
        exchange: 交易所适配器
        bot_data: 机器人数据
        config: 配置
        buy_order_id: 买单ID
        buy_price: 买入价格
        quantity: 卖出数量
        sell_price: 卖出价格
        current_price: 当前价格
        log_prefix: 日志前缀
        retry_count: 当前重试次数
        max_retry: 最大重试次数
    
    Returns:
        bool: 是否成功
    """
    try:
        sell_order = exchange.order_limit_sell(
            quantity=quantity,
            price=f"{sell_price}",
            current_price=current_price,
            entry_price=buy_price
        )
        sell_order_id = str(sell_order.get('orderId') or sell_order.get('id'))
        print(f"{log_prefix} ✅ 卖单已挂 {sell_order_id}: 价格={sell_price}")
        
        # 更新 target_price 为卖单价格
        bot_data['target_price'] = sell_price
        
        # 添加到 pending_sells 跟踪列表
        bot_data.setdefault('pending_sells', []).append({
            'order_id': sell_order_id,
            'price': sell_price,
            'quantity': quantity,
            'buy_order_id': buy_order_id,
            'buy_price': buy_price,
            'reprice_count': 0,
            'original_order_id': sell_order_id  # 记录原始卖单号
        })
        
        # 插入卖单记录到数据库
        user_id = bot_data.get('user_id')
        if user_id:
            try:
                # 获取买单阶段的价格差值统计数据
                buy_min_diff = bot_data.get('buy_min_price_diff_percent')
                buy_max_diff = bot_data.get('buy_max_price_diff_percent')
                buy_avg_diff = bot_data.get('buy_avg_price_diff_percent')
                
                buy_min_diff_str = str(round(buy_min_diff, 4)) if buy_min_diff is not None else None
                buy_max_diff_str = str(round(buy_max_diff, 4)) if buy_max_diff is not None else None
                buy_avg_diff_str = str(round(buy_avg_diff, 4)) if buy_avg_diff is not None else None
                
                insert_order(
                    user_id=user_id,
                    symbol=config['symbol'],
                    price=str(sell_price),
                    quantity=str(quantity),
                    side='SELL',
                    status='NEW',
                    order_id=sell_order_id,
                    buy_price=str(buy_price),
                    exchange=config.get('exchange', 'unknown'),
                    fee=None,
                    offset_percent=str(config.get('offset_percent', 0)),
                    sell_offset_percent=str(config.get('sell_offset_percent', 0)),
                    interval=str(config.get('interval', 0)),
                    min_price_diff_percent=buy_min_diff_str,
                    max_price_diff_percent=buy_max_diff_str,
                    avg_price_diff_percent=buy_avg_diff_str
                )
                print(f"{log_prefix} 📝 卖单已记录到数据库 (买单差值: 最小={buy_min_diff_str}%, 最大={buy_max_diff_str}%, 平均={buy_avg_diff_str}%)")
                
                # 重置买单差值统计数据
                bot_data['buy_min_price_diff_percent'] = None
                bot_data['buy_max_price_diff_percent'] = None
                bot_data['buy_avg_price_diff_percent'] = None
            except Exception as db_e:
                print(f"{log_prefix} ⚠️ 卖单记录失败: {db_e}")
        
        # 挂卖单成功，清除错误和警告信息
        bot_data['last_error'] = None
        bot_data['last_error_time'] = None
        bot_data['last_warning'] = None
        return True
        
    except Exception as e:
        error_msg = str(e)
        error_type = type(e).__name__
        
        if retry_count < max_retry:
            print(f"{log_prefix} ⚠️ 挂卖单失败 [{retry_count + 1}/{max_retry}]: {e}，1秒后重试...")
            time.sleep(1)
            return place_sell_order_with_retry(
                exchange, bot_data, config, buy_order_id, buy_price,
                quantity, sell_price, current_price, log_prefix,
                retry_count + 1, max_retry
            )
        else:
            print(f"{log_prefix} ❌ 挂卖单失败，已重试{max_retry}次: {e}")
            bot_data['last_error'] = f"挂卖单失败 - {error_type}: {error_msg}"
            bot_data['error_count'] = bot_data.get('error_count', 0) + 1
            bot_data['last_error_time'] = datetime.now().isoformat()
            return False


def handle_buy_order_filled(event, bot_data, exchange, config, tick_size, price_decimals, 
                            step_size, qty_decimals, log_prefix):
    """处理买单成交事件"""
    order_id = event['order_id']
    
    # 去重检查
    if order_id in bot_data.get('processed_filled_orders', set()):
        print(f"{log_prefix} ⏭️ [去重] 买单 {order_id} 已处理")
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
        print(f"{log_prefix} ⚠️ 买单 {order_id} 无法获取价格")
        bot_data.get('processed_filled_orders', set()).discard(order_id)
        return
    
    current_price = bot_data.get('current_price')

    # 计算动态卖出加价百分比
    offset_percent = config.get('offset_percent', -0.1)
    base_sell_offset = config.get('sell_offset_percent', 0.5)
    sell_decay_count = config.get('sell_decay_count', 0)
    
    # 判断是否使用衰减逻辑
    abs_buy_offset = abs(offset_percent)
    use_decay = sell_decay_count > 0 and abs_buy_offset > base_sell_offset
    
    # 调试日志:显示衰减判断条件
    print(f"{log_prefix} 🔍 衰减判断: sell_decay_count={sell_decay_count}, abs_buy_offset={abs_buy_offset:.4f}%, base_sell_offset={base_sell_offset:.4f}%, use_decay={use_decay}")
    
    if use_decay:
        # 使用衰减逻辑: 初始使用买入偏移绝对值作为卖出偏移
        dynamic_sell_offset = abs_buy_offset
        print(f"{log_prefix} 📊 启用衰减逻辑, 初始加价: {dynamic_sell_offset:.4f}% (买入偏移绝对值)")
    else:
        # 不使用衰减逻辑: 使用固定卖单偏移
        dynamic_sell_offset = base_sell_offset
        print(f"{log_prefix} 📊 使用固定卖单偏移加价: {dynamic_sell_offset:.4f}%")

    # 计算卖出价格
    sell_price = exchange.calculate_sell_price(
        buy_price, 
        dynamic_sell_offset,
        tick_size, 
        price_decimals,
        current_price=current_price
    )
    
    # 获取成交数量
    executed_qty = float(event.get('executedQty') or event.get('quantity', 0))
    if not executed_qty:
        for pb in bot_data.get('pending_buys', []):
            if pb['order_id'] == order_id:
                executed_qty = pb.get('quantity')
                break
    
    if not executed_qty:
        print(f"{log_prefix} ⚠️ 买单 {order_id} 无法获取数量")
        bot_data.get('processed_filled_orders', set()).discard(order_id)
        return
    
    # 检查手续费是否外部支付（如 BNB 抵扣）
    fee_paid_externally = event.get('feePaidExternally', False)
    if fee_paid_externally:
        # 外部支付手续费，不扣除币种数量，使用配置的固定挂单数量
        aligned_qty = math.floor(config['quantity'] / step_size) * step_size if step_size else config['quantity']
        aligned_qty = round(aligned_qty, qty_decimals)
        print(f"{log_prefix} 📊 外部支付手续费，使用固定数量: {aligned_qty}")
    else:
        # 从交易币种扣除手续费
        fee_rate = exchange.get_fee_rate() * 2
        actual_qty = executed_qty * (1 - fee_rate)
        print(f"{log_prefix} 📊 成交数量: {executed_qty}, 手续费率: {fee_rate*100}%, 扣除后: {actual_qty}")
        
        # 对齐卖出数量
        aligned_qty = math.floor(actual_qty / step_size) * step_size if step_size else actual_qty
        aligned_qty = round(aligned_qty, qty_decimals)
    
    if aligned_qty <= 0:
        print(f"{log_prefix} ❌ 对齐后数量为 0，无法挂卖单")
        bot_data.get('processed_filled_orders', set()).discard(order_id)
        return
    
    print(f"{log_prefix} ✅ 买单成交 {order_id}: 买价={buy_price}, 数量={aligned_qty}")
    
    # 发送钉钉通知
    market_info = exchange.get_notification_info() if hasattr(exchange, 'get_notification_info') else None
    send_order_notification(bot_data.get('username'), 'BUY', config['symbol'], buy_price, aligned_qty, order_id, market_info=market_info)
    
    # 加锁保护 pending_buys 的并发修改
    with _pending_buys_lock:
        # 获取成交订单的 grid_index
        filled_grid_index = 1
        for pb in bot_data.get('pending_buys', []):
            if pb['order_id'] == order_id:
                filled_grid_index = pb.get('grid_index', 1)
                break
        
        # 从 pending_buys 移除（买单已成交）
        bot_data['pending_buys'] = [
            pb for pb in bot_data.get('pending_buys', []) 
            if pb['order_id'] != order_id
        ]
        
        # 重新编号剩余买单的 grid_index（所有 grid_index > 成交的 grid_index 的订单都需要减1）
        for pb in bot_data.get('pending_buys', []):
            old_grid = pb.get('grid_index', 1)
            if old_grid > filled_grid_index:
                pb['grid_index'] = old_grid - 1
                print(f"{log_prefix} 🔄 买单 {pb['order_id']} grid_index: {old_grid} → {pb['grid_index']}")
    
    # 挂卖单（带重试）
    place_sell_order_with_retry(
        exchange, bot_data, config, order_id, buy_price,
        aligned_qty, sell_price, current_price, log_prefix
    )


def handle_reconnected(bot_data, exchange, log_prefix, on_order_update):
    """处理重连事件，同步订单状态"""
    print(f"{log_prefix} 🔄 WebSocket 已重连，同步订单状态...")
    
    # 同步买单状态
    pending_buys = bot_data.get('pending_buys', [])
    for pending_buy in pending_buys[:]:
        order_id = pending_buy.get('order_id')
        try:
            order_info = exchange.get_order(order_id)
            order_status = order_info.get('status')
            
            if order_status == 'FILLED':
                print(f"{log_prefix} ✅ 发现已成交买单 {order_id}")
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
                print(f"{log_prefix} ⏭️ 发现已取消买单 {order_id}")
                # 从 pending_buys 移除
                bot_data['pending_buys'] = [
                    pb for pb in bot_data.get('pending_buys', []) 
                    if pb['order_id'] != order_id
                ]
            elif order_status == 'EXPIRED':
                print(f"{log_prefix} ⏭️ 发现已过期买单 {order_id}")
                # 从 pending_buys 移除
                bot_data['pending_buys'] = [
                    pb for pb in bot_data.get('pending_buys', []) 
                    if pb['order_id'] != order_id
                ]
        except Exception as e:
            print(f"{log_prefix} ⚠️ 查询买单 {order_id} 失败: {e}")
    
    # 同步卖单状态
    pending_sells = bot_data.get('pending_sells', [])
    for pending_sell in pending_sells[:]:
        order_id = pending_sell.get('order_id')
        try:
            order_info = exchange.get_order(order_id)
            order_status = order_info.get('status')
            
            if order_status == 'FILLED':
                print(f"{log_prefix} ✅ 发现已成交卖单 {order_id}")
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
                print(f"{log_prefix} ⏭️ 发现已取消卖单 {order_id}")
                # 从 pending_sells 移除
                bot_data['pending_sells'] = [
                    ps for ps in bot_data.get('pending_sells', []) 
                    if ps['order_id'] != order_id
                ]
            elif order_status == 'EXPIRED':
                print(f"{log_prefix} ⏭️ 发现已过期卖单 {order_id}")
                # 从 pending_sells 移除
                bot_data['pending_sells'] = [
                    ps for ps in bot_data.get('pending_sells', []) 
                    if ps['order_id'] != order_id
                ]
        except Exception as e:
            print(f"{log_prefix} ⚠️ 查询卖单 {order_id} 失败: {e}")


def reprice_buy_orders(open_buy_orders, aligned_quantity, bot_data, 
                       exchange, config, tick_size, price_decimals, log_prefix):
    """改价未完成买单（支持多格网格）"""
    current_price = bot_data.get('current_price')
    if not current_price:
        return
    
    offset_percent = config.get('offset_percent', -0.1)
    
    # 改价前先同步 grid_index：根据当前 grid_index 排序后重新分配连续的序号
    if bot_data.get('pending_buys'):
        # 按 grid_index 从小到大排序
        bot_data['pending_buys'].sort(key=lambda x: x.get('grid_index', 1))
        # 重新分配连续的 grid_index
        for idx, pb in enumerate(bot_data['pending_buys'], start=1):
            old_grid = pb.get('grid_index', idx)
            if old_grid != idx:
                pb['grid_index'] = idx
                print(f"{log_prefix} 🔄 改价前调整 买单 {pb['order_id']} grid_index: {old_grid} → {idx}")
    
    for order in open_buy_orders:
        order_id = str(order.get('orderId'))
        
        # 跳过已成交的订单（防止与成交回调并发冲突）
        if order_id in bot_data.get('processed_filled_orders', set()):
            print(f"{log_prefix} ⏭️ 订单 {order_id} 已成交，跳过改价")
            continue
        
        # 从 pending_buys 中获取该订单的 grid_index
        grid_index = 1  # 默认第1格
        for pb in bot_data.get('pending_buys', []):
            if pb['order_id'] == order_id:
                grid_index = pb.get('grid_index', 1)
                break
        
        # 根据 grid_index 计算目标价: 现价 * (1 + grid_index * offset_percent)
        grid_offset = grid_index * offset_percent
        target_price = exchange.calculate_buy_target_price(
            current_price,
            grid_offset,
            tick_size,
            price_decimals
        )
        
        # 第一格的目标价作为 bot_data 的 target_price
        if grid_index == 1:
            bot_data['target_price'] = target_price
        
        order_price = float(order.get('price', 0))
        if order_price == target_price:
            continue
        
        # 智能价格差异检查
        if should_skip_reprice(order_price, target_price, config, tick_size):
            price_diff_percent = abs(target_price - order_price) / order_price * 100
            absolute_diff = abs(target_price - order_price)
            print(f"{log_prefix} ⏭️ 买单[{grid_index}]价格差异 {price_diff_percent:.4f}%/{absolute_diff:.6f}，跳过改价")
            continue
        
        try:
            print(f"{log_prefix} 🔧 准备改价买单[{grid_index}]: {order_id}, 目标价={target_price:.6f}")
            resp = exchange.cancel_replace_order(
                side='BUY',
                order_type='LIMIT',
                quantity=aligned_quantity,
                price=f"{target_price}",
                cancel_order_id=str(order['orderId']),
                timeInForce='GTC',
                current_price=current_price
            )
            print(f"{log_prefix} ✅ 改价请求已完成: {order_id}")
            
            # 提取新订单ID
            new_order_id = None
            if isinstance(resp, dict):
                new_order_data = resp.get('newOrderResponse', {})
                if isinstance(new_order_data, dict):
                    new_order_id = str(new_order_data.get('orderId') or new_order_data.get('id'))
            
            # 更新或添加 pending_buys 中的订单
            if new_order_id == order_id:
                # editOrderWs 返回相同 ID，更新现有条目的价格
                for pb in bot_data.get('pending_buys', []):
                    if pb['order_id'] == order_id:
                        pb['price'] = target_price
                        break
                print(f"{log_prefix} ✅ 买单[{grid_index}]改价成功: {order_id}, 目标价格={target_price:.6f}/当前价格={current_price:.6f}")
            else:
                # 订单 ID 变化，添加新条目并移除旧条目
                bot_data.setdefault('pending_buys', []).append({
                    'order_id': new_order_id,
                    'price': target_price,
                    'quantity': aligned_quantity,
                    'symbol': config['symbol'],
                    'user_id': bot_data['user_id'],
                    'grid_index': grid_index
                })
                bot_data['pending_buys'] = [
                    pb for pb in bot_data.get('pending_buys', []) 
                    if pb['order_id'] != order_id
                ]
                print(f"{log_prefix} ✅ 买单[{grid_index}]改价成功: {order_id} → {new_order_id}, 目标价格={target_price:.6f}/当前价格={current_price:.6f}")
                
            # 改价成功，清除错误和警告信息
            bot_data['last_error'] = None
            bot_data['last_error_time'] = None
            bot_data['last_warning'] = None
        except Exception as e:
            error_msg = f"[{datetime.now().isoformat()}] {log_prefix} ❌ 改价失败 {order_id}: {e}\n"
            error_msg += ''.join(traceback.format_exception(type(e), e, e.__traceback__))
            print(error_msg)
            
            # 检查缓存中的待处理买单是否还存在
            # 如果改价失败,可能是订单已经成交或被取消,需要从缓存中移除
            try:
                current_open_orders = exchange.get_open_orders()
                open_order_ids = {str(o.get('orderId')) for o in current_open_orders if o.get('side') == 'BUY'}
                
                # 如果订单不在开放订单列表中,从缓存中移除
                if order_id not in open_order_ids:
                    bot_data['pending_buys'] = [
                        pb for pb in bot_data.get('pending_buys', []) 
                        if pb['order_id'] != order_id
                    ]
                    print(f"{log_prefix} 🧹 订单 {order_id} 不存在,已从缓存中移除")
            except Exception as check_error:
                print(f"{log_prefix} ⚠️ 检查订单状态失败: {check_error}")


def should_skip_reprice(current_price, target_price, config, tick_size):
    """判断是否应该跳过改价
    
    Args:
        current_price: 当前价格
        target_price: 目标价格
        config: 配置字典
        tick_size: 价格步长
        
    Returns:
        bool: True表示应该跳过改价， False 表示执行改价
    """

    if abs(target_price - current_price) <= tick_size:
        return False
    
    # 否则使用原来的逻辑：检查价格差异百分比
    price_diff_percent = abs(target_price - current_price) / current_price * 100
    reprice_threshold = config.get('reprice_threshold_percent', 0.01)
    
    return price_diff_percent < reprice_threshold


def reprice_sell_orders(open_sell_orders, bot_data, exchange, config, tick_size, 
                        price_decimals, step_size, qty_decimals, log_prefix):
    """动态调整卖单价格"""
    current_price = bot_data.get('current_price')
    if not current_price:
        return
    
    for grad_index, sell_order in enumerate(open_sell_orders, 1):  # 从 1 开始
        sell_order_id = str(sell_order['orderId'])
        current_sell_price = float(sell_order['price'])
        
        # 获取对应的买入价和改价次数
        buy_price = None
        reprice_count = 0
        for ps in bot_data.get('pending_sells', []):
            if ps.get('order_id') == sell_order_id:
                buy_price = ps.get('buy_price')
                reprice_count = ps.get('reprice_count', 0)
                break
        
        if not buy_price:
            continue
        
        # 获取配置参数
        offset_percent = config.get('offset_percent', -0.1)
        base_sell_offset = config.get('sell_offset_percent', 0.5)
        sell_decay_count = config.get('sell_decay_count', 0)
        
        # 判断是否使用衰减逻辑
        abs_buy_offset = abs(offset_percent)
        use_decay = sell_decay_count > 0 and abs_buy_offset > base_sell_offset
        
        # 计算目标卖价
        if use_decay and reprice_count < sell_decay_count:
            # 使用衰减逻辑: 每次改价递减 (100/sell_decay_count)% 的差值
            A = abs(abs_buy_offset - base_sell_offset)
            decay_percent = 100.0 / sell_decay_count  # 计算递减百分比
            reduction = reprice_count * (decay_percent / 100.0) * A
            calculated_offset = abs_buy_offset - reduction
            
            # 如果计算值小于实际卖出偏移,使用实际卖出偏移
            if calculated_offset < base_sell_offset:
                dynamic_sell_offset = base_sell_offset
                print(f"{log_prefix} 📊 改价{reprice_count+1}: 计算值{calculated_offset:.4f}% < 基础{base_sell_offset}%, 使用基础偏移")
            else:
                dynamic_sell_offset = calculated_offset
                print(f"{log_prefix} 📊 改价{reprice_count+1}: 使用衰减偏移 {dynamic_sell_offset:.4f}% (递减{decay_percent:.1f}%)")
        else:
            # 不使用衰减逻辑或已达到衰减次数上限: 使用实际卖出偏移
            dynamic_sell_offset = base_sell_offset
        
        # 应用 grad_index 梯度调整
        dynamic_sell_offset = dynamic_sell_offset * grad_index
        
        target_sell_price = exchange.calculate_sell_price(
            buy_price,
            dynamic_sell_offset,
            tick_size,
            price_decimals,
            current_price
        )
        bot_data['target_price'] = target_sell_price   
        
        # 智能价格差异检查
        if should_skip_reprice(current_sell_price, target_sell_price, config, tick_size):
            price_diff_percent = abs(target_sell_price - current_sell_price) / current_sell_price * 100
            absolute_diff = abs(target_sell_price - current_sell_price)
            print(f"{log_prefix} ⏭️ 卖单 {sell_order_id} 价格差异 {price_diff_percent:.4f}%/{absolute_diff:.6f}，跳过改价")
            continue
        
        try:
            aligned_qty = math.floor(float(sell_order['origQty']) / step_size) * step_size
            aligned_qty = round(aligned_qty, qty_decimals)
            
            # 标记正在改价的订单，防止 WebSocket 事件误清理 pending_sells
            bot_data['repricing_order_id'] = sell_order_id
            
            resp = exchange.cancel_replace_order(
                side='SELL',
                order_type='LIMIT',
                quantity=aligned_qty,
                price=f"{target_sell_price}",
                cancel_order_id=sell_order_id,
                timeInForce='GTC',
                current_price=bot_data.get('current_price'),
                entry_price=buy_price
            )
            
            # 提取新订单ID
            new_order_id = None
            if isinstance(resp, dict):
                new_order_data = resp.get('newOrderResponse', {})
                if isinstance(new_order_data, dict):
                    new_order_id = str(new_order_data.get('orderId') or new_order_data.get('id'))
            
            # 更新或添加 pending_sells 中的订单
            if new_order_id == sell_order_id:
                # editOrderWs 返回相同 ID，更新现有条目的价格和改价次数
                for ps in bot_data.get('pending_sells', []):
                    if ps['order_id'] == sell_order_id:
                        ps['price'] = target_sell_price
                        ps['reprice_count'] = reprice_count + 1  # 增加改价次数
                        break
                print(f"{log_prefix} ✅ 卖单改价成功: {sell_order_id}, 目标价格={target_sell_price:.6f}/当前价格={bot_data['current_price']:.6f}, 改价次数={reprice_count + 1}")
            else:
                # 订单 ID 变化，添加新条目并移除旧条目
                # 获取原始卖单号
                original_order_id = None
                for ps in bot_data.get('pending_sells', []):
                    if ps['order_id'] == sell_order_id:
                        original_order_id = ps.get('original_order_id', sell_order_id)
                        break
                
                bot_data.setdefault('pending_sells', []).append({
                    'order_id': new_order_id,
                    'price': target_sell_price,
                    'quantity': aligned_qty,
                    'symbol': config['symbol'],
                    'user_id': bot_data['user_id'],
                    'buy_price': buy_price,
                    'reprice_count': reprice_count + 1,  # 增加改价次数
                    'original_order_id': original_order_id  # 保持原始卖单号不变
                })
                bot_data['pending_sells'] = [
                    ps for ps in bot_data.get('pending_sells', []) 
                    if ps['order_id'] != sell_order_id
                ]
                print(f"{log_prefix} ✅ 卖单改价成功: {sell_order_id} → {new_order_id}, 目标价格={target_sell_price:.6f}/当前价格={bot_data['current_price']:.6f}, 改价次数={reprice_count + 1}，原始卖单号={original_order_id}")
                
            # 改价成功，清除错误和警告信息
            bot_data['last_error'] = None
            bot_data['last_error_time'] = None
            bot_data['last_warning'] = None
        except Exception as e:
            print(f"{log_prefix} ❌ 卖单改价失败 {sell_order_id}: {e}")
            
            # 检查缓存中的待处理卖单是否还存在
            # 如果改价失败,可能是订单已经成交或被取消,需要从缓存中移除
            try:
                current_open_orders = exchange.get_open_orders()
                open_order_ids = {str(o.get('orderId')) for o in current_open_orders if o.get('side') == 'SELL'}
                
                # 如果订单不在开放订单列表中,从缓存中移除
                if sell_order_id not in open_order_ids:
                    bot_data['pending_sells'] = [
                        ps for ps in bot_data.get('pending_sells', []) 
                        if ps['order_id'] != sell_order_id
                    ]
                    print(f"{log_prefix} 🧹 订单 {sell_order_id} 不存在,已从缓存中移除")
            except Exception as check_error:
                print(f"{log_prefix} ⚠️ 检查订单状态失败: {check_error}")
        finally:
            # 清除改价标记
            bot_data['repricing_order_id'] = None


def trading_loop(username, bot_key):
    """交易主循环"""
    user_data = user_bots.get(username)
    if not user_data:
        return
    bot_data = user_data.get('bots', {}).get(bot_key)
    if not bot_data:
        return

    exchange = bot_data.get('exchange')
    if not exchange:
        print(f"[{datetime.now().isoformat()}] ❌ [{username}-{bot_key}] 交易所实例不存在，无法启动交易循环")
        return
    
    # 使用交易所的 _get_log_prefix 方法生成日志前缀
    log_prefix = f"{exchange._get_log_prefix()}[{username}]"
    print(f"{log_prefix} ▶️ 交易循环已启动")
    
    # 顶层异常捕获 - 确保任何未预期的崩溃都能被记录
    try:
        _trading_loop_inner(username, bot_key, bot_data, log_prefix)
    except Exception as fatal_error:
        # 记录到崩溃日志文件(即使标准输出失败也能记录)
        log_crash(fatal_error, context=log_prefix)
        
        # 打印到标准输出
        error_msg = f"{log_prefix} 💥 交易循环致命错误:\n"
        error_msg += ''.join(traceback.format_exception(type(fatal_error), fatal_error, fatal_error.__traceback__))
        print(error_msg)
        
        # 更新机器人状态
        bot_data['last_error'] = f"致命错误: {type(fatal_error).__name__}: {str(fatal_error)}"
        bot_data['last_error_time'] = datetime.now().isoformat()
        bot_data['running'] = False


def _trading_loop_inner(username, bot_key, bot_data, log_prefix):
    """交易主循环内部实现"""

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
    bot_data['username'] = username

    while bot_data.get('running'):
        try:
            exchange = bot_data.get('exchange')
            config = bot_data.get('config', {})
            log_prefix = f"{exchange._get_log_prefix()}[{username}]"

            if not exchange or not config:
                time.sleep(1)
                continue

            # 获取交易规则（仅一次）
            if tick_size is None:
                try:
                    rules = exchange.get_trading_rules()
                    print(f"{log_prefix} 🔍 原始交易规则: {rules}")
                    tick_size = rules['tick_size']
                    price_decimals = rules['price_decimals']
                    step_size = rules['step_size']
                    qty_decimals = rules['qty_decimals']
                    print(f"{log_prefix} ✅ 交易规则: tick_size={tick_size}, price_decimals={price_decimals}, step_size={step_size}, qty_decimals={qty_decimals}")
                except Exception as e:
                    tick_size, price_decimals = 0.01, 2
                    step_size, qty_decimals = 0.000001, 6
                    print(f"{log_prefix} ⚠️ 获取交易规则失败，使用默认值: {e}")

            # 启动监听（仅一次）
            if not bot_data.get('monitor_started'):
                def _on_price_update(price: float):
                    # print(f"{log_prefix} 💰 价格更新回调被调用: {price}")
                    bot_data['current_price'] = price
                    # print(f"{log_prefix} ✅ bot_data['current_price'] 已更新为: {bot_data['current_price']}")
                    
                    # 使用交易所适配器的方法计算价格差值统计(买卖分开)
                    target_price = bot_data.get('target_price')
                    if target_price and price > 0:
                        # 判断当前是买单还是卖单阶段
                        # 如果有待成交的买单,说明是买单阶段;否则是卖单阶段
                        pending_buys = bot_data.get('pending_buys', [])
                        is_buy_phase = len(pending_buys) > 0
                        
                        if is_buy_phase:
                            # 买单阶段统计
                            min_diff = bot_data.get('buy_min_price_diff_percent')
                            max_diff = bot_data.get('buy_max_price_diff_percent')
                            avg_diff = bot_data.get('buy_avg_price_diff_percent')
                            
                            new_min, new_avg, new_max = exchange.calculate_price_diff_stats(
                                price, target_price, min_diff, max_diff, avg_diff
                            )
                            
                            bot_data['buy_min_price_diff_percent'] = new_min
                            bot_data['buy_avg_price_diff_percent'] = new_avg
                            bot_data['buy_max_price_diff_percent'] = new_max
                        else:
                            # 卖单阶段统计
                            min_diff = bot_data.get('sell_min_price_diff_percent')
                            max_diff = bot_data.get('sell_max_price_diff_percent')
                            avg_diff = bot_data.get('sell_avg_price_diff_percent')
                            
                            new_min, new_avg, new_max = exchange.calculate_price_diff_stats(
                                price, target_price, min_diff, max_diff, avg_diff
                            )
                            
                            bot_data['sell_min_price_diff_percent'] = new_min
                            bot_data['sell_avg_price_diff_percent'] = new_avg
                            bot_data['sell_max_price_diff_percent'] = new_max

                def _on_order_update(event: dict):
                    try:
                        # 过滤其他交易对的订单事件
                        if event.get('symbol') != config['symbol']:
                            print(f"{log_prefix} 🔇 忽略其他交易对事件: {event.get('symbol')}/{config['symbol']}")
                            return

                        event_type = event.get('event_type')
                        print(f"{log_prefix} 📥 收到订单事件: {event}")
                        
                        # 在处理每个事件前记录,方便定位崩溃点
                        print(f"{log_prefix} 🔄 开始处理事件类型: {event_type}")
                        
                        # 重连事件
                        if event_type == 'reconnected':
                            handle_reconnected(bot_data, exchange, log_prefix, _on_order_update)
                            return
                        
                        # 市场刷新事件（UpDown15m 市场切换）
                        if event_type == 'refresh_market':
                            old_slug = event.get('old_slug')
                            new_slug = event.get('new_slug')
                            print(f"{log_prefix} 🔄 市场已切换: {old_slug} → {new_slug}")
                            # 清除旧市场的缓存订单
                            old_buys = len(bot_data.get('pending_buys', []))
                            old_sells = len(bot_data.get('pending_sells', []))
                            bot_data['pending_buys'] = []
                            bot_data['pending_sells'] = []
                            # 重置价格，等待新市场价格推送
                            old_price = bot_data.get('current_price')
                            bot_data['current_price'] = None
                            print(f"{log_prefix} 🧹 已清除缓存订单: {old_buys} 笔买单, {old_sells} 笔卖单, 旧价格: {old_price}")
                            return
                        
                        # 错误事件
                        if event_type == 'error':
                            print(f"{log_prefix} ❌ {event.get('error_message')}")
                            return
                        
                        # 订单取消
                        if event_type == 'order_cancelled':
                            order_id = event.get('order_id')
                            # 检查是否正在改价中，如果是则跳过清理（改价会自己处理）
                            repricing_order_id = bot_data.get('repricing_order_id')
                            if repricing_order_id == order_id:
                                print(f"{log_prefix} ⏭️ 订单 {order_id} 正在改价中，跳过清理")
                                return
                            
                            if event.get('side') == 'BUY':
                                bot_data['pending_buys'] = [
                                    pb for pb in bot_data.get('pending_buys', []) 
                                    if pb['order_id'] != order_id
                                ]
                                print(f"{log_prefix} ⏭️ 买单取消 {order_id}")
                            elif event.get('side') == 'SELL':
                                bot_data['pending_sells'] = [
                                    ps for ps in bot_data.get('pending_sells', []) 
                                    if ps['order_id'] != order_id
                                ]
                                print(f"{log_prefix} ⏭️ 卖单取消 {order_id}")
                            return
                        
                        # 买单成交
                        if event_type == 'order_filled' and event.get('side') == 'BUY':
                            # 设置禁止下单标志
                            bot_data['is_handling_buy_filled'] = True
                            print(f"{log_prefix} 🔒 设置禁止下单标志")
                            try:
                                handle_buy_order_filled(event, bot_data, exchange, config, 
                                                       tick_size, price_decimals, step_size, 
                                                       qty_decimals, log_prefix)
                            finally:
                                # 清除禁止下单标志
                                bot_data['is_handling_buy_filled'] = False
                                print(f"{log_prefix} 🔓 清除禁止下单标志")
                        
                        # 卖单成交
                        if event_type == 'order_filled' and event.get('side') == 'SELL':
                            order_id = event.get('order_id')
                            # 先获取成本价和原始卖单号（从 pending_sells 中查找）
                            buy_price = None
                            original_order_id = None
                            for ps in bot_data.get('pending_sells', []):
                                if ps['order_id'] == order_id:
                                    buy_price = ps.get('buy_price')
                                    original_order_id = ps.get('original_order_id', order_id)
                                    break
                            
                            # 从 pending_sells 移除
                            bot_data['pending_sells'] = [
                                ps for ps in bot_data.get('pending_sells', []) 
                                if ps['order_id'] != order_id
                            ]
                            print(f"{log_prefix} ✅ 卖单成交 {order_id}")
                            
                            # 发送钉钉通知（包含成本价）
                            sell_price = event.get('price', 0)
                            sell_qty = event.get('executedQty') or event.get('quantity', 0)
                            market_info = exchange.get_notification_info() if hasattr(exchange, 'get_notification_info') else None
                            cost_info = f"成本:{buy_price}" if buy_price else None
                            send_order_notification(bot_data.get('username'), 'SELL', config['symbol'], sell_price, sell_qty, order_id, market_info=market_info, cost_info=cost_info)
                            
                            # 更新数据库订单状态
                            try:
                                # 尝试从事件中获取手续费和成交价格
                                fee = event.get('fee') or event.get('commission')
                                filled_price = float(event.get('price', 0)) if event.get('price') else None
                                
                                # 获取卖单阶段的价格差值统计数据
                                sell_min_diff = bot_data.get('sell_min_price_diff_percent')
                                sell_max_diff = bot_data.get('sell_max_price_diff_percent')
                                sell_avg_diff = bot_data.get('sell_avg_price_diff_percent')
                                
                                sell_min_diff_str = str(round(sell_min_diff, 4)) if sell_min_diff is not None else None
                                sell_max_diff_str = str(round(sell_max_diff, 4)) if sell_max_diff is not None else None
                                sell_avg_diff_str = str(round(sell_avg_diff, 4)) if sell_avg_diff is not None else None
                                
                                update_order_status(
                                    original_order_id, 'FILLED', 
                                    fee=fee, 
                                    price=filled_price,
                                    sell_min_diff=sell_min_diff_str,
                                    sell_max_diff=sell_max_diff_str,
                                    sell_avg_diff=sell_avg_diff_str
                                )
                                print(f"{log_prefix} 📝 卖单状态已更新: FILLED, 当前订单ID={order_id}, 原始订单ID={original_order_id}, 成交价格={filled_price}, 卖单差值: 最小={sell_min_diff_str}%, 最大={sell_max_diff_str}%, 平均={sell_avg_diff_str}%")
                                
                                # 重置卖单差值统计数据,为下一次交易做准备
                                bot_data['sell_min_price_diff_percent'] = None
                                bot_data['sell_max_price_diff_percent'] = None
                                bot_data['sell_avg_price_diff_percent'] = None
                            except Exception as db_e:
                                print(f"{log_prefix} ⚠️ 更新卖单状态失败: {db_e}")
                    except Exception as e:
                        print(f"{log_prefix} ❌ 订单回调错误: {e}")
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
                open_buy_orders = [o for o in open_orders if str(o.get('side')).upper() == 'BUY']
                open_sell_orders = [o for o in open_orders if str(o.get('side')).upper() == 'SELL']
                query_success = True
                current_price = bot_data.get('current_price')
                # 恢复 pending_buys 和 pending_sells（仅启动时）
                if not pending_buys_recovered:
                    print(f"{log_prefix} 🔍 启动恢复检查: open_buy_orders={len(open_buy_orders)}, open_sell_orders={len(open_sell_orders)}, pending_buys={len(bot_data.get('pending_buys', []))}, pending_sells={len(bot_data.get('pending_sells', []))}")
                    if not bot_data.get('pending_buys', []) and open_buy_orders:
                        buy_offset_percent = config.get('buy_offset_percent', 0.5)
                        order_grid = config.get('order_grid', 1)
                        
                        for order in open_buy_orders:
                            order_price = float(order['price'])
                            
                            # 根据订单价格计算 grid_index
                            # grid_index = 1 对应 buy_offset_percent
                            # grid_index = 2 对应 buy_offset_percent * 2，以此类推
                            grid_index = 1
                            if current_price and current_price > 0:
                                price_diff_percent = abs((current_price - order_price) / current_price * 100)
                                grid_index = max(1, min(order_grid, round(price_diff_percent / buy_offset_percent)))
                            
                            bot_data.setdefault('pending_buys', []).append({
                                'order_id': str(order['orderId']),
                                'price': order_price,
                                'quantity': float(order['origQty']),
                                'symbol': config['symbol'],
                                'user_id': user_id,
                                'grid_index': grid_index
                            })
                            print(f"{log_prefix} ✅ 恢复买单 {order['orderId']}，price={order_price}，grid_index={grid_index}")
                        print(f"{log_prefix} ✅ 恢复 {len(open_buy_orders)} 笔买单")
                    
                    if not bot_data.get('pending_sells', []) and open_sell_orders:
                        sell_offset_percent = config.get('sell_offset_percent', 0.5)
                        for order in open_sell_orders:
                            sell_order_id = str(order['orderId'])
                            sell_price = float(order['price'])
                            
                            # 优先从数据库读取买入价格
                            from database import get_order_buy_price
                            buy_price = get_order_buy_price(sell_order_id)
                            
                            if buy_price:
                                print(f"{log_prefix} ✅ 从数据库恢复买入价格: {buy_price}")
                            else:
                                # 兜底方案：使用交易所适配器计算估算的买入价格
                                # 适配器内部处理了做多/做空的逻辑差异
                                buy_price = exchange.calculate_estimated_buy_price(
                                    sell_price, 
                                    sell_offset_percent, 
                                    tick_size, 
                                    price_decimals,
                                    order=order
                                )
                                print(f"{log_prefix} ⚠️ 数据库无买入价格，使用估算值: {buy_price}")
                            
                            bot_data.setdefault('pending_sells', []).append({
                                'order_id': sell_order_id,
                                'price': sell_price,
                                'quantity': float(order['origQty']),
                                'buy_price': buy_price
                            })
                            print(f"{log_prefix} ✅ 恢复卖单 {sell_order_id}，buy_price={buy_price}")
                        print(f"{log_prefix} ✅ 恢复 {len(open_sell_orders)} 笔卖单")
                    
                    pending_buys_recovered = True

                # 改价买单
                if open_buy_orders:
                    reprice_buy_orders(open_buy_orders, aligned_quantity, bot_data, 
                                     exchange, config, tick_size, price_decimals, log_prefix)

                # 同步 pending_sells 状态（清理已成交或取消的卖单）
                # 注意: 只有当查询到卖单时才清理,避免API延迟导致误清理
                if bot_data.get('pending_sells') and open_sell_orders:
                    # 检查是否只返回虚拟订单
                    virtual_orders = [o for o in open_sell_orders if o.get('info', {}).get('virtual', False)]
                    if len(virtual_orders) == len(open_sell_orders) and len(open_sell_orders) > 0:
                        print(f"{log_prefix} ⚠️ 检测到只返回虚拟订单 {[o['orderId'] for o in virtual_orders]}，跳过 pending_sells 清理")
                    else:
                        open_sell_order_ids = {str(o['orderId']) for o in open_sell_orders}
                        pending_sell_ids = {ps['order_id'] for ps in bot_data['pending_sells']}
                        removed_ids = pending_sell_ids - open_sell_order_ids
                        if removed_ids:
                            bot_data['pending_sells'] = [
                                ps for ps in bot_data['pending_sells'] 
                                if ps['order_id'] not in removed_ids
                            ]
                            print(f"{log_prefix} 🔄 清理已完成卖单: {removed_ids}")
                
                # 动态调整卖单（默认禁用）
                if open_sell_orders:       
                    reprice_sell_orders(open_sell_orders, bot_data, exchange, config, 
                                      tick_size, price_decimals, step_size, qty_decimals, log_prefix)

            except Exception as e:
                print(f"{log_prefix} ⚠️ 查询订单失败: {e}")
                # 查询失败时不下单，避免重复挂单
                query_success = False

            # 补挂买单逻辑（要求查询成功、没有正在下单、总持仓数量不足）
            order_grid = config.get('order_grid', 1)
            is_placing_order = bot_data.get('is_placing_order', False)
            
            # 计算当前总持仓数量（pending_buys + pending_sells 的数量之和）
            pending_buys = bot_data.get('pending_buys', [])
            pending_sells = bot_data.get('pending_sells', [])
            pending_buys_qty = sum(pb.get('quantity', 0) for pb in pending_buys)
            pending_sells_qty = sum(ps.get('quantity', 0) for ps in pending_sells)
            total_pending_qty = pending_buys_qty + pending_sells_qty
            target_qty = order_grid * aligned_quantity
            need_more_orders = total_pending_qty < target_qty
            
            # 调试日志:当数量超标时显示详细信息
            if total_pending_qty > target_qty:
                buy_orders = [f"{pb['order_id']}({pb.get('quantity', 0)})" for pb in pending_buys]
                sell_orders = [f"{ps['order_id']}({ps.get('quantity', 0)})" for ps in pending_sells]
                print(f"{log_prefix} 🔍 持仓超标详情:")
                print(f"  pending_buys({len(pending_buys)}笔): {buy_orders}")
                print(f"  pending_sells({len(pending_sells)}笔): {sell_orders}")
                print(f"  total={total_pending_qty:.6g}, target={target_qty:.6g}")
            
            # 取消超出 order_grid 的订单（在 query_success 时立即执行）
            if query_success:
                pending_buys = bot_data.get('pending_buys', [])
                pending_sells = bot_data.get('pending_sells', [])
                
                # 计算需要保留的买单数量
                max_buy_orders = order_grid - len(pending_sells)
                orders_to_cancel = []
                if len(pending_buys) > max_buy_orders:
                    # 按grid_index降序排序，保留序号大的订单
                    pending_buys_sorted = sorted(pending_buys, key=lambda x: x.get('grid_index', 1), reverse=True)
                    # 保留前max_buy_orders个订单，取消其余的
                    orders_to_keep = pending_buys_sorted[:max_buy_orders]
                    orders_to_cancel = pending_buys_sorted[max_buy_orders:]
                    # 按grid_index升序排序，优先取消序号小的订单
                    orders_to_cancel.sort(key=lambda x: x.get('grid_index', 1))
                    
                    # 打印保留和取消的grid_index
                    keep_indices = [pb.get('grid_index', 1) for pb in orders_to_keep]
                    cancel_indices = [pb.get('grid_index', 1) for pb in orders_to_cancel]
                    print(f"{log_prefix} 📊 网格调整: 保留{len(orders_to_keep)}个订单(grid_index={keep_indices}), 取消{len(orders_to_cancel)}个订单(grid_index={cancel_indices})")
                if orders_to_cancel:
                    print(f"{log_prefix} 🔍 发现 {len(orders_to_cancel)} 笔超出网格范围的订单，准备取消 (max_buy_orders={max_buy_orders})")
                    for pb in orders_to_cancel:
                        try:
                            exchange.cancel_order(pb['order_id'])
                            print(f"{log_prefix} ✅ 取消超范围订单: {pb['order_id']}, grid_index={pb.get('grid_index')}")
                            bot_data['pending_buys'] = [
                                p for p in bot_data.get('pending_buys', []) 
                                if p['order_id'] != pb['order_id']
                            ]
                        except Exception as e:
                            print(f"{log_prefix} ⚠️ 取消订单失败 {pb['order_id']}: {e}")
            
            # 下单前检查和修复 grid_index（在 query_success 且不在下单中时执行）
            if query_success and not is_placing_order:
                # 检查 grid_index 重复
                pending_buys = bot_data.get('pending_buys', [])
                grid_index_map = {}
                for pb in pending_buys:
                    grid_idx = pb.get('grid_index', 1)
                    if grid_idx not in grid_index_map:
                        grid_index_map[grid_idx] = []
                    grid_index_map[grid_idx].append(pb)
                
                # 找出重复的 grid_index
                duplicates = {idx: orders for idx, orders in grid_index_map.items() if len(orders) > 1}
                if duplicates:
                    print(f"{log_prefix} 🔍 发现 grid_index 重复: {list(duplicates.keys())}")
                    
                    # 直接重新分配 grid_index，后续改价会自动调整到正确价格
                    pending_buys = bot_data.get('pending_buys', [])
                    for idx, pb in enumerate(pending_buys, start=1):
                        old_grid_index = pb.get('grid_index', 1)
                        pb['grid_index'] = idx
                        if old_grid_index != idx:
                            print(f"{log_prefix} 🔄 订单 {pb['order_id']} grid_index: {old_grid_index} → {idx}")
                    
                    bot_data['pending_buys'] = pending_buys
            
            if query_success and not is_placing_order and need_more_orders:
                is_buy_enabled = (config.get('simulate_trading', 1) != 1)
                if is_buy_enabled:
                    offset_percent = config.get('offset_percent', -0.1)
                    
                    # 计算需要补挂的买单数量（按缺少的总数量计算，而不是补齐所有网格）
                    missing_qty = target_qty - total_pending_qty
                    orders_to_add = math.ceil(missing_qty / aligned_quantity) if aligned_quantity > 0 else 0
                    
                    # 获取当前最大的 grid_index
                    max_grid_index = 0
                    for pb in bot_data.get('pending_buys', []):
                        max_grid_index = max(max_grid_index, pb.get('grid_index', 0))
                    
                    print(f"{log_prefix} 🔍 补单计算: 缺少数量={missing_qty:.6g}, 需补单={orders_to_add}笔, max_grid_index={max_grid_index}")
                    
                    bot_data['is_placing_order'] = True
                    try:
                        # 只补挂缺少数量对应的买单
                        for i in range(orders_to_add):
                            grid_index = max_grid_index + 1 + i
                            # 计算每格买单目标价: 现价 * (1 + grid_index * offset_percent)
                            grid_offset = grid_index * offset_percent
                            target_price = exchange.calculate_buy_target_price(
                                current_price,
                                grid_offset,
                                tick_size,
                                price_decimals
                            )
                            
                            # 第一格的目标价作为 bot_data 的 target_price
                            if grid_index == 1:
                                bot_data['target_price'] = target_price
                            
                            # 检查是否正在处理买单成交（禁止下单）
                            if bot_data.get('is_handling_buy_filled', False):
                                print(f"{log_prefix} ⏸️ 正在处理买单成交，跳过下单")
                                continue
                            
                            order = exchange.order_limit_buy(
                                quantity=aligned_quantity,
                                price=f"{target_price}",
                                current_price=current_price
                            )
                            order_id = str(order.get('orderId') or order.get('id'))
                            print(f"{log_prefix} ✅ 新买单[{grid_index}/{order_grid}] {order_id}: 价格={target_price}, 数量={aligned_quantity}, 偏移={grid_offset:.2f}%")

                            with _pending_buys_lock:
                                bot_data.setdefault('pending_buys', []).append({
                                    'order_id': order_id,
                                    'price': target_price,
                                    'quantity': aligned_quantity,
                                    'symbol': config['symbol'],
                                    'user_id': user_id,
                                    'grid_index': grid_index
                                })
                        
                        # 下单成功，清除错误和警告信息
                        bot_data['last_error'] = None
                        bot_data['last_error_time'] = None
                        bot_data['last_warning'] = None
                    except Exception as e:
                        error_msg = str(e)
                        error_type = type(e).__name__
                        print(f"{log_prefix} ❌ 下单失败: {e}")
                        
                        # 保存下单错误信息
                        bot_data['last_error'] = f"下单失败 - {error_type}: {error_msg}"
                        bot_data['error_count'] = bot_data.get('error_count', 0) + 1
                        bot_data['last_error_time'] = datetime.now().isoformat()
                    finally:
                        bot_data['is_placing_order'] = False
            else:
                # 打印跳过下单的原因
                skip_reasons = []
                if not query_success:
                    skip_reasons.append("查询失败")
                if not need_more_orders:
                    skip_reasons.append(f"持仓已满({total_pending_qty:.6g}/{target_qty:.6g})")
                if is_placing_order:
                    skip_reasons.append("正在下单中")
                if skip_reasons:
                    print(f"{log_prefix} ⏸️ 跳过下单: {', '.join(skip_reasons)}")

            time.sleep(config.get('interval', 1))

        except Exception as e:
            error_msg = str(e)
            error_type = type(e).__name__
            print(f"{log_prefix} ❌ 循环错误: {e}")
            traceback.print_exc()
            
            # 保存错误信息到 bot_data
            bot_data['last_error'] = f"{error_type}: {error_msg}"
            bot_data['error_count'] = bot_data.get('error_count', 0) + 1
            bot_data['last_error_time'] = datetime.now().isoformat()
            
            time.sleep(1)

    print(f"{log_prefix} ◼️ 交易循环已停止")
