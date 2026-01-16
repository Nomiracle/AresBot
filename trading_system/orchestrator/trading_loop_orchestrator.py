"""
交易循环编排器 - 主循环控制器
"""

import time
import math
import traceback
from datetime import datetime
from typing import Optional, Dict, Any

from ..domain import (
    TradingContext, OrderInfo, OrderStateMachine, 
    OrderState, OrderSide
)
from ..strategy import PriceCalculationStrategy, GridPriceStrategy
from ..commands import (
    CommandExecutor, PlaceSellOrderCommand
)
from ..services import (
    NotificationService, OrderPlacementService,
    OrderRepricingService, OrderSynchronizer
)
from ..infrastructure import TradingEventBus


class TradingLoopOrchestrator:
    """交易循环编排器 - 协调所有组件完成交易逻辑"""
    
    def __init__(self, context: TradingContext):
        """
        初始化编排器
        
        Args:
            context: 交易上下文
        """
        self.context = context
        self.event_bus = TradingEventBus()
        
        # 初始化策略
        self.price_strategy: PriceCalculationStrategy = GridPriceStrategy()
        
        # 初始化命令执行器
        self.executor = CommandExecutor()
        
        # 初始化服务
        self.notification_service = NotificationService(context.username)
        self.placement_service = OrderPlacementService(context, self.price_strategy, self.executor)
        self.repricing_service = OrderRepricingService(context, self.price_strategy, self.executor)
        self.synchronizer = OrderSynchronizer(context)
        
        # 交易规则（延迟初始化）
        self.tick_size: Optional[float] = None
        self.price_decimals: Optional[int] = None
        self.step_size: Optional[float] = None
        self.qty_decimals: Optional[int] = None
        
        # 是否已恢复订单
        self._orders_recovered = False

        # 止损幂等保护（记录已触发止损的卖单ID）
        self._stop_loss_triggered_sell_orders: set[str] = set()
    
    def run(self) -> None:
        """启动交易循环"""
        log_prefix = self.context.get_log_prefix()
        print(f"{log_prefix} ▶️ 交易循环已启动")
        
        try:
            self._initialize()
            self._run_loop()
        except Exception as fatal_error:
            from crash_logger import log_crash
            log_crash(fatal_error, context=log_prefix)
            
            error_msg = f"{log_prefix} 💥 交易循环致命错误:\n"
            error_msg += ''.join(traceback.format_exception(type(fatal_error), fatal_error, fatal_error.__traceback__))
            print(error_msg)
            
            self.context.runtime.record_error(f"致命错误: {type(fatal_error).__name__}: {str(fatal_error)}")
            self.context.stop_trading()
        
        print(f"{log_prefix} ◼️ 交易循环已停止")
    
    def _initialize(self) -> None:
        """初始化"""
        log_prefix = self.context.get_log_prefix()
        
        # 获取交易规则
        try:
            rules = self.context.exchange.get_trading_rules()
            self.tick_size = rules['tick_size']
            self.price_decimals = rules['price_decimals']
            self.step_size = rules['step_size']
            self.qty_decimals = rules['qty_decimals']
            print(f"{log_prefix} ✅ 交易规则: tick_size={self.tick_size}, price_decimals={self.price_decimals}, step_size={self.step_size}, qty_decimals={self.qty_decimals}")
        except Exception as e:
            self.tick_size, self.price_decimals = 0.01, 2
            self.step_size, self.qty_decimals = 0.000001, 6
            print(f"{log_prefix} ⚠️ 获取交易规则失败，使用默认值: {e}")
        
        # 订阅事件
        self.event_bus.subscribe('price_update', self._on_price_update)
        self.event_bus.subscribe('order_update', self._on_order_update)
        
        # 启动WebSocket监听
        self.context.exchange.start_ws(
            on_price_update=lambda price: self.event_bus.publish('price_update', {'price': price}),
            on_order_update=lambda event: self.event_bus.publish('order_update', event)
        )
        
        self.context.runtime.monitor_started = True
        self.context.start_trading()
    
    def _run_loop(self) -> None:
        """主循环"""
        log_prefix = self.context.get_log_prefix()
        
        while self.context.runtime.running:
            try:
                # 检查价格是否就绪
                if self.context.market.current_price is None:
                    self.context.runtime.record_warning("监听器未更新价格")
                    time.sleep(self.context.config.interval)
                    continue
                
                # 清除警告
                if self.context.runtime.last_error or self.context.runtime.last_warning:
                    self.context.runtime.clear_error()
                    self.context.runtime.clear_warning()
                
                # 查询开放订单并同步订单状态
                try:
                    # 同步订单状态（首次会恢复订单，返回持仓信息）
                    positions = self.synchronizer.sync_from_exchange(
                        self.tick_size, self.price_decimals,
                        self.step_size, self.qty_decimals
                    )
                    
                    # 标记首次恢复完成
                    if not self._orders_recovered:
                        self._orders_recovered = True
                    
                    # 处理无挂单但有持仓的情况
                    self._handle_positions_without_orders(positions)
                    
                    # 改价订单
                    self.repricing_service.reprice_buy_orders(self.tick_size, self.price_decimals)
                    self.repricing_service.reprice_sell_orders(
                        self.tick_size, self.price_decimals,
                        self.step_size, self.qty_decimals
                    )

                    # 卖单止损检查
                    self._check_sell_stop_loss()
                    
                    # 调整网格（取消超范围订单）
                    self._adjust_grid()
                    
                    # 修复grid_index重复
                    self._fix_duplicate_grid_index()
                    
                    # 补单
                    if self.context.needs_more_orders() and not self.context.runtime.is_placing_order:
                        self._place_missing_orders()
                    
                except Exception as e:
                    print(f"{log_prefix} ⚠️ 查询订单失败: {e}")
                
                time.sleep(self.context.config.interval)
                
            except Exception as e:
                error_msg = str(e)
                error_type = type(e).__name__
                print(f"{log_prefix} ❌ 循环错误: {e}")
                traceback.print_exc()
                
                self.context.runtime.record_error(f"{error_type}: {error_msg}")
                time.sleep(1)
    
    def _on_price_update(self, event: Dict[str, Any]) -> None:
        """价格更新事件处理"""
        price = event.get('price')
        if price is None:
            return
        
        self.context.update_market_price(price)
        
        # 计算价格差值统计
        target_price = self.context.market.target_price
        if target_price and price > 0:
            # 判断当前是买单还是卖单阶段
            buy_orders = self.context.order_manager.get_active_orders(OrderSide.BUY)
            is_buy_phase = len(buy_orders) > 0
            
            if is_buy_phase:
                # 买单阶段统计
                new_min, new_avg, new_max = self.context.exchange.calculate_price_diff_stats(
                    price, target_price,
                    self.context.market.buy_min_diff,
                    self.context.market.buy_max_diff,
                    self.context.market.buy_avg_diff
                )
                self.context.market.update_buy_stats(new_min, new_avg, new_max)
            else:
                # 卖单阶段统计
                new_min, new_avg, new_max = self.context.exchange.calculate_price_diff_stats(
                    price, target_price,
                    self.context.market.sell_min_diff,
                    self.context.market.sell_max_diff,
                    self.context.market.sell_avg_diff
                )
                self.context.market.update_sell_stats(new_min, new_avg, new_max)
    
    def _on_order_update(self, event: Dict[str, Any]) -> None:
        """订单更新事件处理"""
        log_prefix = self.context.get_log_prefix()
        
        # 过滤其他交易对
        if event.get('symbol') != self.context.config.symbol:
            return
        
        event_type = event.get('event_type')
        print(f"{log_prefix} 📥 收到订单事件: {event}")
        
        # 重连事件
        if event_type == 'reconnected':
            self._handle_reconnected()
            return
        
        # 市场刷新事件
        if event_type == 'refresh_market':
            self._handle_market_refresh(event)
            return
        
        # 错误事件
        if event_type == 'error':
            print(f"{log_prefix} ❌ {event.get('error_message')}")
            return
        
        # 订单取消
        if event_type == 'order_cancelled':
            self._handle_order_cancelled(event)
            return
        
        # 买单成交
        if event_type == 'order_filled' and event.get('side') == 'BUY':
            self._handle_buy_filled(event)
            return
        
        # 卖单成交
        if event_type == 'order_filled' and event.get('side') == 'SELL':
            self._handle_sell_filled(event)
            return
    
    def _handle_reconnected(self) -> None:
        """处理重连事件"""
        log_prefix = self.context.get_log_prefix()
        print(f"{log_prefix} 🔄 WebSocket 已重连，同步订单状态...")
        
        self.synchronizer.sync_from_exchange(
            self.tick_size, self.price_decimals,
            self.step_size, self.qty_decimals
        )
    
    def _handle_market_refresh(self, event: Dict[str, Any]) -> None:
        """处理市场刷新事件"""
        log_prefix = self.context.get_log_prefix()
        old_slug = event.get('old_slug')
        new_slug = event.get('new_slug')
        print(f"{log_prefix} 🔄 市场已切换: {old_slug} → {new_slug}")
        
        # 清除订单
        old_buys = self.context.order_manager.get_order_count(OrderSide.BUY)
        old_sells = self.context.order_manager.get_order_count(OrderSide.SELL)
        
        # 清空订单管理器
        for order in self.context.order_manager.get_all_orders():
            self.context.order_manager.remove_order(order.info.order_id)
        
        # 重置价格
        old_price = self.context.market.current_price
        self.context.market.current_price = None
        
        print(f"{log_prefix} 🧹 已清除缓存订单: {old_buys} 笔买单, {old_sells} 笔卖单, 旧价格: {old_price}")
    
    def _handle_order_cancelled(self, event: Dict[str, Any]) -> None:
        """处理订单取消事件"""
        log_prefix = self.context.get_log_prefix()
        order_id = event.get('order_id')
        
        # 检查是否正在改价中
        if self.context.runtime.repricing_order_id == order_id:
            print(f"{log_prefix} ⏭️ 订单 {order_id} 正在改价中，跳过清理")
            return
        
        # 从订单管理器移除
        order_sm = self.context.order_manager.get_order(order_id)
        if order_sm:
            order_sm.transition_to(OrderState.CANCELLED, "订单已取消")
            self.context.order_manager.remove_order(order_id)
            side_text = "买单" if event.get('side') == 'BUY' else "卖单"
            print(f"{log_prefix} ⏭️ {side_text}取消 {order_id}")
    
    def _handle_buy_filled(self, event: Dict[str, Any]) -> None:
        """处理买单成交事件"""
        log_prefix = self.context.get_log_prefix()
        order_id = event.get('order_id')
        
        # 去重检查
        if self.context.runtime.is_order_processed(order_id):
            print(f"{log_prefix} ⏭️ [去重] 买单 {order_id} 已处理")
            return
        
        # 标记已处理
        self.context.runtime.mark_order_processed(order_id)
        
        # 设置禁止下单标志
        self.context.runtime.is_handling_buy_filled = True
        print(f"{log_prefix} 🔒 设置禁止下单标志")
        
        try:
            # 获取订单状态机
            order_sm = self.context.order_manager.get_order(order_id)
            if not order_sm:
                # 兜底：成交事件可能先于下单返回/本地入库，按递增延迟重试获取
                for i in range(1, 11):
                    time.sleep(i * 0.1)
                    order_sm = self.context.order_manager.get_order(order_id)
                    if order_sm:
                        break
            if not order_sm:
                print(f"{log_prefix} ⚠️ 买单 {order_id} 未找到")
                return
            
            # 更新状态
            order_sm.transition_to(OrderState.FILLED, "订单成交")

            entry_filled_at = order_sm.metrics.filled_at
            
            buy_price = order_sm.info.price
            executed_qty = float(event.get('executedQty') or event.get('quantity', 0))
            
            # 检查手续费是否外部支付
            fee_paid_externally = event.get('feePaidExternally', False)
            if fee_paid_externally:
                aligned_qty = math.floor(self.context.config.quantity / self.step_size) * self.step_size if self.step_size else self.context.config.quantity
                aligned_qty = round(aligned_qty, self.qty_decimals)
                print(f"{log_prefix} 📊 外部支付手续费，使用固定数量: {aligned_qty}")
            else:
                fee_rate = self.context.exchange.get_fee_rate() * 2
                actual_qty = executed_qty * (1 - fee_rate)
                print(f"{log_prefix} 📊 成交数量: {executed_qty}, 手续费率: {fee_rate*100}%, 扣除后: {actual_qty}")
                
                aligned_qty = math.floor(actual_qty / self.step_size) * self.step_size if self.step_size else actual_qty
                aligned_qty = round(aligned_qty, self.qty_decimals)
            
            if aligned_qty <= 0:
                print(f"{log_prefix} ❌ 对齐后数量为 0，无法挂卖单")
                return
            
            print(f"{log_prefix} ✅ 买单成交 {order_id}: 买价={buy_price}, 数量={aligned_qty}")
            
            # 发送通知
            market_info = self.context.exchange.get_notification_info() if hasattr(self.context.exchange, 'get_notification_info') else None
            self.notification_service.send_order_notification(
                'BUY', self.context.config.symbol, buy_price, aligned_qty, order_id, market_info=market_info
            )
            
            # 从订单管理器移除买单
            self.context.order_manager.remove_order(order_id)
            
            # 计算动态卖出偏移
            dynamic_sell_offset = self._calculate_dynamic_sell_offset()
            
            # 挂卖单
            self._place_sell_order(order_id, buy_price, aligned_qty, dynamic_sell_offset, entry_filled_at)
            
        finally:
            # 清除禁止下单标志
            self.context.runtime.is_handling_buy_filled = False
            print(f"{log_prefix} 🔓 清除禁止下单标志")
    
    def _handle_sell_filled(self, event: Dict[str, Any]) -> None:
        """处理卖单成交事件"""
        log_prefix = self.context.get_log_prefix()
        order_id = event.get('order_id')
        
        # 获取订单状态机
        order_sm = self.context.order_manager.get_order(order_id)
        if not order_sm:
            # 兜底：成交事件可能先于下单返回/本地入库，按递增延迟重试获取
            for i in range(1, 11):
                time.sleep(i * 0.1)
                order_sm = self.context.order_manager.get_order(order_id)
                if order_sm:
                    break
        buy_price = order_sm.info.buy_price if order_sm else None
        
        # 更新状态
        if order_sm:
            order_sm.transition_to(OrderState.FILLED, "订单成交")
            self.context.order_manager.remove_order(order_id)
        
        print(f"{log_prefix} ✅ 卖单成交 {order_id}")
        
        # 发送通知
        sell_price = event.get('price', 0)
        sell_qty = event.get('executedQty') or event.get('quantity', 0)
        market_info = self.context.exchange.get_notification_info() if hasattr(self.context.exchange, 'get_notification_info') else None
        cost_info = f"成本:{buy_price}" if buy_price else None
        self.notification_service.send_order_notification(
            'SELL', self.context.config.symbol, sell_price, sell_qty, order_id,
            market_info=market_info, cost_info=cost_info
        )
        
        # 更新数据库
        self._update_sell_order_in_db(event, order_id)
    
    def _calculate_dynamic_sell_offset(self) -> float:
        """计算动态卖出偏移"""
        offset_percent = self.context.config.offset_percent
        base_sell_offset = self.context.config.sell_offset_percent
        sell_decay_count = self.context.config.sell_decay_count
        
        abs_buy_offset = abs(offset_percent)
        use_decay = sell_decay_count > 0 and abs_buy_offset > base_sell_offset
        
        log_prefix = self.context.get_log_prefix()
        print(f"{log_prefix} 🔍 衰减判断: sell_decay_count={sell_decay_count}, abs_buy_offset={abs_buy_offset:.4f}%, base_sell_offset={base_sell_offset:.4f}%, use_decay={use_decay}")
        
        if use_decay:
            dynamic_sell_offset = abs_buy_offset
            print(f"{log_prefix} 📊 启用衰减逻辑, 初始加价: {dynamic_sell_offset:.4f}% (买入偏移绝对值)")
        else:
            dynamic_sell_offset = base_sell_offset
            print(f"{log_prefix} 📊 使用固定卖单偏移加价: {dynamic_sell_offset:.4f}%")
        
        return dynamic_sell_offset
    
    def _place_sell_order(self, buy_order_id: str, buy_price: float, quantity: float, dynamic_sell_offset: float, entry_filled_at: Optional[datetime]) -> None:
        """挂卖单"""
        log_prefix = self.context.get_log_prefix()
        
        # 创建挂卖单命令
        command = PlaceSellOrderCommand(
            context=self.context,
            price_strategy=self.price_strategy,
            buy_order_id=buy_order_id,
            buy_price=buy_price,
            quantity=quantity,
            tick_size=self.tick_size,
            price_decimals=self.price_decimals,
            step_size=self.step_size,
            qty_decimals=self.qty_decimals,
            dynamic_sell_offset=dynamic_sell_offset
        )
        
        # 执行命令（带重试）
        max_retry = 3
        for retry in range(max_retry):
            success, order_id, error = self.executor.execute(command)
            
            if success:
                print(f"{log_prefix} ✅ 卖单已挂 {order_id}: 价格={self.context.market.target_price}")

                # 记录买单成交时间到卖单（用于止损：距离成交时间）
                if entry_filled_at is not None:
                    sell_sm = self.context.order_manager.get_order(order_id)
                    if sell_sm:
                        sell_sm.metrics.filled_at = entry_filled_at
                
                # 插入数据库
                self._insert_sell_order_to_db(order_id, buy_price, quantity)
                
                # 清除错误
                self.context.runtime.clear_error()
                self.context.runtime.clear_warning()
                break
            else:
                if retry < max_retry - 1:
                    print(f"{log_prefix} ⚠️ 挂卖单失败 [{retry + 1}/{max_retry}]: {error}，1秒后重试...")
                    time.sleep(1)
                else:
                    print(f"{log_prefix} ❌ 挂卖单失败，已重试{max_retry}次: {error}")
                    self.context.runtime.record_error(f"挂卖单失败: {error}")

    def _is_short_mode(self) -> bool:
        """判断是否为做空模式（用于止损亏损百分比计算）"""
        try:
            info = self.context.exchange.get_exchange_info() if hasattr(self.context.exchange, 'get_exchange_info') else {}
            exchange_id = str((info or {}).get('id', '')).lower()
            return 'short' in exchange_id
        except Exception:
            return False

    def _calculate_loss_percent(self, entry_price: float, current_price: float, is_short: bool) -> Optional[float]:
        """计算亏损百分比（只返回亏损，不返回盈利；单位：百分比）"""
        try:
            if entry_price <= 0 or current_price <= 0:
                return None

            if is_short:
                # 做空：价格上涨为亏损
                loss = (current_price - entry_price) / entry_price * 100
            else:
                # 做多：价格下跌为亏损
                loss = (entry_price - current_price) / entry_price * 100

            return max(0.0, float(loss))
        except Exception:
            return None

    def _check_sell_stop_loss(self) -> None:
        """检查卖单止损：超时或亏损达到阈值则取消挂单并抛售"""
        log_prefix = self.context.get_log_prefix()

        stop_loss_delay = self.context.config.stop_loss_delay
        min_price_threshold = self.context.config.min_price_threshold

        # 任意一个配置存在才启用止损检查
        if stop_loss_delay is None and min_price_threshold is None:
            return

        current_price = self.context.market.current_price
        if current_price is None or current_price <= 0:
            return

        is_short = self._is_short_mode()
        now = datetime.now()

        sell_orders = self.context.order_manager.get_active_orders(OrderSide.SELL)
        for order_sm in sell_orders:
            sell_order_id = order_sm.info.order_id

            if sell_order_id in self._stop_loss_triggered_sell_orders:
                continue

            entry_price = order_sm.info.buy_price
            if entry_price is None:
                continue

            # 条件A：距离成交时间（买单成交时间写入到卖单 metrics.filled_at）
            hit_by_time = False
            if stop_loss_delay is not None:
                filled_at = order_sm.metrics.filled_at
                if filled_at is not None:
                    try:
                        elapsed = (now - filled_at).total_seconds()
                        hit_by_time = elapsed > float(stop_loss_delay)
                    except Exception:
                        hit_by_time = False

            # 条件B：亏损百分比
            hit_by_loss = False
            loss_percent = None
            if min_price_threshold is not None:
                loss_percent = self._calculate_loss_percent(float(entry_price), float(current_price), is_short)
                if loss_percent is not None:
                    hit_by_loss = loss_percent >= float(min_price_threshold)

            if not (hit_by_time or hit_by_loss):
                continue

            reason = ""
            if hit_by_time and hit_by_loss:
                reason = f"超时+亏损({loss_percent:.4f}%)"
            elif hit_by_time:
                reason = "超时"
            else:
                reason = f"亏损({loss_percent:.4f}%)"

            print(f"{log_prefix} 🛡️ 触发卖单止损 {sell_order_id}: {reason}，开始取消挂单并抛售")

            # 幂等标记：先标记，避免取消/下单过程异常导致下一轮重复触发
            self._stop_loss_triggered_sell_orders.add(sell_order_id)

            try:
                # 1) 取消挂单
                try:
                    self.context.exchange.cancel_order(sell_order_id)
                except Exception as cancel_e:
                    print(f"{log_prefix} ⚠️ 止损取消卖单失败 {sell_order_id}: {cancel_e}")

                # 本地移除，避免后续循环重复处理
                self.context.order_manager.remove_order(sell_order_id)

                # 2) 市价抛售（统一使用限价单按当前价近似市价）
                qty = float(order_sm.info.quantity)
                if qty <= 0:
                    return

                order_result = self.context.exchange.order_limit_sell(
                    quantity=qty,
                    price=f"{float(current_price)}",
                    current_price=float(current_price),
                    entry_price=float(entry_price)
                )

                stop_loss_order_id = str((order_result or {}).get('orderId') or (order_result or {}).get('id'))
                if not stop_loss_order_id:
                    raise RuntimeError("止损卖单返回的订单ID为空")

                # 将止损卖单纳入幂等，避免下一轮再次对该卖单重复触发止损
                self._stop_loss_triggered_sell_orders.add(stop_loss_order_id)

                # 将止损卖单加入订单管理器，确保成交事件能取到 buy_price 等信息
                stop_loss_order_info = OrderInfo(
                    order_id=stop_loss_order_id,
                    symbol=self.context.config.symbol,
                    side=OrderSide.SELL,
                    price=float(current_price),
                    quantity=qty,
                    buy_order_id=order_sm.info.buy_order_id,
                    buy_price=float(entry_price)
                )
                stop_loss_order_sm = OrderStateMachine(stop_loss_order_info, OrderState.PENDING)
                stop_loss_order_sm.transition_to(OrderState.PLACED, "止损抛售")
                self.context.order_manager.add_order(stop_loss_order_sm)

                # 写入数据库（显式传入价格，避免修改 market 状态）
                self._insert_sell_order_to_db(stop_loss_order_id, float(entry_price), qty, sell_price=float(current_price))

            except Exception as e:
                print(f"{log_prefix} ❌ 卖单止损执行失败 {sell_order_id}: {e}")
    
    def _insert_sell_order_to_db(self, order_id: str, buy_price: float, quantity: float, sell_price: Optional[float] = None) -> None:
        """插入卖单到数据库"""
        log_prefix = self.context.get_log_prefix()
        
        try:
            from database import insert_order
            
            # 获取买单阶段的价格差值统计数据
            buy_min_diff_str = str(round(self.context.market.buy_min_diff, 4)) if self.context.market.buy_min_diff is not None else None
            buy_max_diff_str = str(round(self.context.market.buy_max_diff, 4)) if self.context.market.buy_max_diff is not None else None
            buy_avg_diff_str = str(round(self.context.market.buy_avg_diff, 4)) if self.context.market.buy_avg_diff is not None else None
            
            insert_order(
                user_id=self.context.user_id,
                symbol=self.context.config.symbol,
                price=str(sell_price if sell_price is not None else self.context.market.target_price),
                quantity=str(quantity),
                side='SELL',
                status='NEW',
                order_id=order_id,
                buy_price=str(buy_price),
                exchange=self.context.config.exchange,
                fee=None,
                offset_percent=str(self.context.config.offset_percent),
                sell_offset_percent=str(self.context.config.sell_offset_percent),
                interval=str(self.context.config.interval),
                min_price_diff_percent=buy_min_diff_str,
                max_price_diff_percent=buy_max_diff_str,
                avg_price_diff_percent=buy_avg_diff_str
            )
            print(f"{log_prefix} 📝 卖单已记录到数据库 (买单差值: 最小={buy_min_diff_str}%, 最大={buy_max_diff_str}%, 平均={buy_avg_diff_str}%)")
            
            # 重置买单差值统计数据
            self.context.market.reset_buy_stats()
            
        except Exception as db_e:
            print(f"{log_prefix} ⚠️ 卖单记录失败: {db_e}")
    
    def _update_sell_order_in_db(self, event: Dict[str, Any], order_id: str) -> None:
        """更新卖单到数据库"""
        log_prefix = self.context.get_log_prefix()
        
        try:
            from database import update_order_status
            
            fee = event.get('fee') or event.get('commission')
            filled_price = float(event.get('price', 0)) if event.get('price') else None
            
            # 获取卖单阶段的价格差值统计数据
            sell_min_diff_str = str(round(self.context.market.sell_min_diff, 4)) if self.context.market.sell_min_diff is not None else None
            sell_max_diff_str = str(round(self.context.market.sell_max_diff, 4)) if self.context.market.sell_max_diff is not None else None
            sell_avg_diff_str = str(round(self.context.market.sell_avg_diff, 4)) if self.context.market.sell_avg_diff is not None else None
            
            update_order_status(
                order_id, 'FILLED',
                fee=fee,
                price=filled_price,
                sell_min_diff=sell_min_diff_str,
                sell_max_diff=sell_max_diff_str,
                sell_avg_diff=sell_avg_diff_str
            )
            print(f"{log_prefix} 📝 卖单状态已更新: FILLED, 订单ID={order_id}, 成交价格={filled_price}, 卖单差值: 最小={sell_min_diff_str}%, 最大={sell_max_diff_str}%, 平均={sell_avg_diff_str}%")
            
            # 重置卖单差值统计数据
            self.context.market.reset_sell_stats()
            
        except Exception as db_e:
            print(f"{log_prefix} ⚠️ 更新卖单状态失败: {db_e}")
    
    def _adjust_grid(self) -> None:
        """调整网格（取消超范围订单）"""
        log_prefix = self.context.get_log_prefix()
        
        buy_orders = self.context.order_manager.get_active_orders(OrderSide.BUY)
        sell_orders = self.context.order_manager.get_active_orders(OrderSide.SELL)
        
        # 计算需要保留的买单数量
        max_buy_orders = self.context.config.order_grid - len(sell_orders)
        
        if len(buy_orders) > max_buy_orders:
            # 按grid_index降序排序
            buy_orders_sorted = sorted(buy_orders, key=lambda x: x.info.grid_index, reverse=True)
            orders_to_keep = buy_orders_sorted[:max_buy_orders]
            orders_to_cancel = buy_orders_sorted[max_buy_orders:]
            orders_to_cancel.sort(key=lambda x: x.info.grid_index)
            
            keep_indices = [o.info.grid_index for o in orders_to_keep]
            cancel_indices = [o.info.grid_index for o in orders_to_cancel]
            print(f"{log_prefix} 📊 网格调整: 保留{len(orders_to_keep)}个订单(grid_index={keep_indices}), 取消{len(orders_to_cancel)}个订单(grid_index={cancel_indices})")
            
            for order_sm in orders_to_cancel:
                try:
                    self.context.exchange.cancel_order(order_sm.info.order_id)
                    print(f"{log_prefix} ✅ 取消超范围订单: {order_sm.info.order_id}, grid_index={order_sm.info.grid_index}")
                    
                    order_sm.transition_to(OrderState.CANCELLED, "超出网格范围")
                    self.context.order_manager.remove_order(order_sm.info.order_id)
                except Exception as e:
                    print(f"{log_prefix} ⚠️ 取消订单失败 {order_sm.info.order_id}: {e}")
    
    def _fix_duplicate_grid_index(self) -> None:
        """修复grid_index重复"""
        log_prefix = self.context.get_log_prefix()
        
        buy_orders = self.context.order_manager.get_active_orders(OrderSide.BUY)
        
        # 检查重复
        grid_index_map = {}
        for order_sm in buy_orders:
            grid_idx = order_sm.info.grid_index
            if grid_idx not in grid_index_map:
                grid_index_map[grid_idx] = []
            grid_index_map[grid_idx].append(order_sm)
        
        duplicates = {idx: orders for idx, orders in grid_index_map.items() if len(orders) > 1}
        if duplicates:
            print(f"{log_prefix} 🔍 发现 grid_index 重复: {list(duplicates.keys())}")
            
            # 重新分配grid_index
            buy_orders.sort(key=lambda x: x.info.grid_index)
            for idx, order_sm in enumerate(buy_orders, start=1):
                old_grid_index = order_sm.info.grid_index
                if old_grid_index != idx:
                    object.__setattr__(order_sm.info, 'grid_index', idx)
                    print(f"{log_prefix} 🔄 订单 {order_sm.info.order_id} grid_index: {old_grid_index} → {idx}")
    
    def _place_missing_orders(self) -> None:
        """补挂缺失的订单"""
        log_prefix = self.context.get_log_prefix()
        
        if not self.context.config.is_buy_enabled:
            return
        
        # 计算缺少的数量
        buy_orders = self.context.order_manager.get_active_orders(OrderSide.BUY)
        sell_orders = self.context.order_manager.get_active_orders(OrderSide.SELL)
        
        total_qty = sum(o.info.quantity for o in buy_orders) + sum(o.info.quantity for o in sell_orders)
        target_qty = self.context.config.order_grid * self.context.config.quantity
        missing_qty = target_qty - total_qty
        
        if missing_qty <= 0:
            return
        
        # 计算需要补挂的订单数
        orders_to_add = math.floor(missing_qty / self.context.config.quantity) if self.context.config.quantity > 0 else 0
        
        # 获取当前最大的grid_index
        max_grid_index = max([o.info.grid_index for o in buy_orders], default=0)
        
        print(f"{log_prefix} 🔍 补单计算: 缺少数量={missing_qty:.6g}, 需补单={orders_to_add}笔, max_grid_index={max_grid_index}")
        
        # 设置下单标志
        self.context.runtime.is_placing_order = True
        
        try:
            self.placement_service.place_buy_orders(
                count=orders_to_add,
                start_grid_index=max_grid_index + 1,
                tick_size=self.tick_size,
                price_decimals=self.price_decimals,
                step_size=self.step_size,
                qty_decimals=self.qty_decimals
            )
            
            # 清除错误
            self.context.runtime.clear_error()
            self.context.runtime.clear_warning()
            
        except Exception as e:
            print(f"{log_prefix} ❌ 补单失败: {e}")
            self.context.runtime.record_error(f"补单失败: {e}")
        finally:
            self.context.runtime.is_placing_order = False
    
    def _handle_positions_without_orders(self, positions: list) -> None:
        """处理持仓与卖单数量不匹配的情况，创建平仓卖单"""
        from ..domain import OrderSide
        
        log_prefix = self.context.get_log_prefix()
        
        if not positions:
            return
        
        # 计算持仓总数量
        total_position_qty = sum(position.contracts for position in positions)
        
        # 计算卖单总数量
        sell_orders = self.context.order_manager.get_all_orders(OrderSide.SELL)
        total_sell_qty = sum(order.info.quantity for order in sell_orders)
        
        # 如果持仓总数量小于等于卖单总数量，无需创建卖单
        if total_position_qty <= total_sell_qty:
            return
        
        # 需要创建的卖单数量 = 持仓总数量 - 卖单总数量
        missing_qty = total_position_qty - total_sell_qty
        
        print(f"{log_prefix} 📍 持仓总量={total_position_qty}, 卖单总量={total_sell_qty}, 需补卖单数量={missing_qty}")
        
        # 为持仓创建卖单，直到补足差额
        remaining_qty = missing_qty
        for position in positions:
            if remaining_qty <= 0:
                break
            
            try:
                buy_price = position.entry_price
                quantity = min(position.contracts, remaining_qty)
                sell_offset_percent = self.context.config.sell_offset_percent
                
                buy_order_id = f"position_{position.symbol}_{position.side}"
                
                print(f"{log_prefix} 📝 为持仓创建平仓卖单: symbol={position.symbol}, side={position.side}, qty={quantity}, entry_price={buy_price}")
                
                self._place_sell_order(buy_order_id, buy_price, quantity, sell_offset_percent, None)
                
                remaining_qty -= quantity
                
            except Exception as e:
                print(f"{log_prefix} ❌ 为持仓创建卖单失败: {e}")
