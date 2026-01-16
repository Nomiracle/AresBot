"""
订单同步服务
"""

from typing import TYPE_CHECKING, Dict, Any
from datetime import datetime
from ..domain import OrderInfo, OrderStateMachine, OrderState, OrderSide

if TYPE_CHECKING:
    from ..domain import TradingContext


class OrderSynchronizer:
    """订单同步服务 - 同步交易所订单状态"""
    
    def __init__(self, context: 'TradingContext'):
        """
        初始化同步服务
        
        Args:
            context: 交易上下文
        """
        self.context = context
    
    def sync_from_exchange(
        self,
        tick_size: float,
        price_decimals: int,
        step_size: float,
        qty_decimals: int
    ) -> list['PositionInfo']:
        """
        从交易所同步订单状态（v2版本：使用真实订单+持仓分离查询）
        
        Args:
            tick_size: 价格步长
            price_decimals: 价格小数位
            step_size: 数量步长
            qty_decimals: 数量小数位
            
        Returns:
            持仓列表（供编排器决策是否需要创建卖单）
        """
        log_prefix = self.context.get_log_prefix()
        
        try:
            # v2: 使用分离接口获取真实订单和持仓（返回实体类）
            exchange_orders = self.context.exchange.get_open_ordersv2()
            positions = self.context.exchange.get_open_positionv2()
            
            # 分离买单和卖单
            open_buy_orders = [o for o in exchange_orders if o.side == 'BUY']
            open_sell_orders = [o for o in exchange_orders if o.side == 'SELL']
            
            print(f"{log_prefix} 📊 [v2] 真实订单: {len(open_buy_orders)}笔买单, {len(open_sell_orders)}笔卖单 | 持仓: {len(positions)}个")
            
            # 同步买单
            self._sync_buy_orders(open_buy_orders, tick_size, price_decimals)
            
            # 同步卖单（v2需要考虑持仓状态）
            self._sync_sell_orders(open_sell_orders, tick_size, price_decimals, step_size, qty_decimals, positions)
            
            return positions
            
        except Exception as e:
            print(f"{log_prefix} ⚠️ 同步订单失败: {e}")
            return []
    
    def _sync_buy_orders(
        self,
        open_buy_orders: list['ExchangeOrder'],
        tick_size: float,
        price_decimals: int
    ) -> None:
        """同步买单（处理ExchangeOrder实体类）"""
        log_prefix = self.context.get_log_prefix()
        
        # 获取当前管理器中的买单
        managed_orders = self.context.order_manager.get_all_orders(OrderSide.BUY)
        managed_order_ids = {o.info.order_id for o in managed_orders}
        
        # 获取交易所的买单ID
        exchange_order_ids = {o.order_id for o in open_buy_orders}
        
        # 恢复缺失的买单
        missing_order_ids = exchange_order_ids - managed_order_ids
        if missing_order_ids:
            buy_offset_percent = abs(self.context.config.offset_percent)
            current_price = self.context.market.current_price
            
            for order in open_buy_orders:
                if order.order_id in missing_order_ids:
                    order_price = order.price
                    
                    # 根据订单价格计算 grid_index
                    grid_index = 1
                    if current_price and current_price > 0:
                        price_diff_percent = abs((current_price - order_price) / current_price * 100)
                        grid_index = max(1, min(self.context.config.order_grid, round(price_diff_percent / buy_offset_percent)))
                    
                    # 创建订单信息
                    order_info = OrderInfo(
                        order_id=order.order_id,
                        symbol=self.context.config.symbol,
                        side=OrderSide.BUY,
                        price=order_price,
                        quantity=order.quantity,
                        grid_index=grid_index
                    )
                    
                    # 创建订单状态机
                    order_sm = OrderStateMachine(order_info, OrderState.PLACED)
                    
                    # 添加到管理器
                    self.context.order_manager.add_order(order_sm)
                    
                    print(f"{log_prefix} ✅ 恢复买单 {order.order_id}，price={order_price}，grid_index={grid_index}")
            
            print(f"{log_prefix} ✅ 恢复 {len(missing_order_ids)} 笔买单")
        
        # 清理已取消/成交的买单
        removed_order_ids = managed_order_ids - exchange_order_ids
        for order_id in removed_order_ids:
            order_sm = self.context.order_manager.get_order(order_id)
            if order_sm and order_sm.state == OrderState.PLACED:
                self.context.order_manager.remove_order(order_id)
                print(f"{log_prefix} 🧹 清理已完成买单: {order_id}")
    
    def _sync_sell_orders(
        self,
        open_sell_orders: list['ExchangeOrder'],
        tick_size: float,
        price_decimals: int,
        step_size: float,
        qty_decimals: int,
        positions: list['PositionInfo'] = None
    ) -> None:
        """同步卖单（v2版本：支持持仓状态判断，处理实体类）
        
        Args:
            positions: 当前持仓列表（v2专用，用于判断是否有待平仓位）
        """
        log_prefix = self.context.get_log_prefix()
        
        # 获取当前管理器中的卖单
        managed_orders = self.context.order_manager.get_all_orders(OrderSide.SELL)
        managed_order_ids = {o.info.order_id for o in managed_orders}
        
        # 获取交易所的卖单ID
        exchange_order_ids = {o.order_id for o in open_sell_orders}
        
        # v2: 检查持仓状态（无挂单但有持仓时，记录状态供编排器决策）
        if positions is None:
            positions = []
        has_position = len(positions) > 0
        if has_position and len(open_sell_orders) == 0:
            print(f"{log_prefix} 📍 [v2] 无卖单但有持仓 (数量={len(positions)})，需要编排器创建平仓卖单")
        
        # 恢复缺失的卖单
        missing_order_ids = exchange_order_ids - managed_order_ids
        if missing_order_ids:
            sell_offset_percent = self.context.config.sell_offset_percent
            
            for order in open_sell_orders:
                if order.order_id in missing_order_ids:
                    sell_price = order.price
                    
                    # 从数据库读取买入价格
                    from database import get_order_buy_price
                    buy_price = get_order_buy_price(order.order_id)
                    
                    if not buy_price:
                        # 兜底方案：使用交易所适配器计算估算的买入价格
                        # 需要将实体类转换为字典格式供旧接口使用
                        order_dict = {
                            'orderId': order.order_id,
                            'price': order.price,
                            'origQty': order.quantity,
                            'info': order.info
                        }
                        buy_price = self.context.exchange.calculate_estimated_buy_price(
                            sell_price,
                            sell_offset_percent,
                            tick_size,
                            price_decimals,
                            order=order_dict
                        )
                        print(f"{log_prefix} ⚠️ 数据库无买入价格，使用估算值: {buy_price}")
                    else:
                        print(f"{log_prefix} ✅ 从数据库恢复买入价格: {buy_price}")
                    
                    # 创建订单信息
                    order_info = OrderInfo(
                        order_id=order.order_id,
                        symbol=self.context.config.symbol,
                        side=OrderSide.SELL,
                        price=sell_price,
                        quantity=order.quantity,
                        buy_price=buy_price
                    )
                    
                    # 创建订单状态机
                    order_sm = OrderStateMachine(order_info, OrderState.PLACED)
                    
                    # 添加到管理器
                    self.context.order_manager.add_order(order_sm)
                    
                    print(f"{log_prefix} ✅ 恢复卖单 {order.order_id}，buy_price={buy_price}")
            
            print(f"{log_prefix} ✅ 恢复 {len(missing_order_ids)} 笔卖单")
        
        # 清理已取消/成交的卖单（保留虚拟订单检查以防御未实现v2的交易所）
        if managed_order_ids and exchange_order_ids:
            now = datetime.now()
            cleanup_grace_seconds = 3.0
            removed_order_ids = managed_order_ids - exchange_order_ids
            for order_id in removed_order_ids:
                order_sm = self.context.order_manager.get_order(order_id)
                if order_sm and order_sm.state == OrderState.PLACED:
                    # 跳过虚拟订单（持仓映射的订单，如 pos_long_BTCUSDT）
                    if order_id.startswith('pos_'):
                        print(f"{log_prefix} ⏭️ 跳过虚拟订单清理: {order_id}")
                        continue
                    
                    # 新挂卖单可能尚未出现在交易所开放订单列表，给宽限期避免误清理
                    try:
                        created_at = order_sm.metrics.created_at
                        if created_at and (now - created_at).total_seconds() < cleanup_grace_seconds:
                            print(f"{log_prefix} ⏳ 卖单 {order_id} 刚创建，跳过清理")
                            continue
                    except Exception:
                        pass
                    self.context.order_manager.remove_order(order_id)
                    print(f"{log_prefix} 🧹 清理已完成卖单: {order_id}")
