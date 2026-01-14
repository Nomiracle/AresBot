"""
订单改价服务
"""

from typing import TYPE_CHECKING
from ..domain import OrderSide

if TYPE_CHECKING:
    from ..domain import TradingContext
    from ..strategy import PriceCalculationStrategy
    from ..commands import CommandExecutor


class OrderRepricingService:
    """订单改价服务"""
    
    def __init__(
        self,
        context: 'TradingContext',
        price_strategy: 'PriceCalculationStrategy',
        executor: 'CommandExecutor'
    ):
        """
        初始化改价服务
        
        Args:
            context: 交易上下文
            price_strategy: 价格策略
            executor: 命令执行器
        """
        self.context = context
        self.price_strategy = price_strategy
        self.executor = executor
    
    def reprice_buy_orders(
        self,
        tick_size: float,
        price_decimals: int
    ) -> int:
        """
        改价买单
        
        Args:
            tick_size: 价格步长
            price_decimals: 价格小数位
            
        Returns:
            改价成功的订单数量
        """
        from ..commands import RepriceBuyOrderCommand
        
        # 获取活跃买单
        active_orders = self.context.order_manager.get_active_orders(OrderSide.BUY)
        
        # 按grid_index排序并重新分配连续序号
        active_orders.sort(key=lambda x: x.info.grid_index)
        for idx, order_sm in enumerate(active_orders, start=1):
            if order_sm.info.grid_index != idx:
                old_grid = order_sm.info.grid_index
                object.__setattr__(order_sm.info, 'grid_index', idx)
                log_prefix = self.context.get_log_prefix()
                print(f"{log_prefix} 🔄 改价前调整 买单 {order_sm.info.order_id} grid_index: {old_grid} → {idx}")
        
        success_count = 0
        
        for order_sm in active_orders:
            # 跳过已成交的订单
            if self.context.runtime.is_order_processed(order_sm.info.order_id):
                log_prefix = self.context.get_log_prefix()
                print(f"{log_prefix} ⏭️ 订单 {order_sm.info.order_id} 已成交，跳过改价")
                continue
            
            # 创建改价命令
            command = RepriceBuyOrderCommand(
                context=self.context,
                price_strategy=self.price_strategy,
                order_sm=order_sm,
                tick_size=tick_size,
                price_decimals=price_decimals
            )
            
            # 执行命令
            success, result, error = self.executor.execute(command)
            
            if success and result:
                success_count += 1
                log_prefix = self.context.get_log_prefix()
                print(f"{log_prefix} ✅ 买单[{order_sm.info.grid_index}]改价成功: {order_sm.info.order_id}, 目标价格={order_sm.info.price:.6f}/当前价格={self.context.market.current_price:.6f}")
            elif error:
                log_prefix = self.context.get_log_prefix()
                print(f"{log_prefix} ❌ 改价失败 {order_sm.info.order_id}: {error}")
        
        return success_count
    
    def reprice_sell_orders(
        self,
        tick_size: float,
        price_decimals: int,
        step_size: float,
        qty_decimals: int
    ) -> int:
        """
        改价卖单
        
        Args:
            tick_size: 价格步长
            price_decimals: 价格小数位
            step_size: 数量步长
            qty_decimals: 数量小数位
            
        Returns:
            改价成功的订单数量
        """
        from ..commands import RepriceSellOrderCommand
        
        # 获取活跃卖单
        active_orders = self.context.order_manager.get_active_orders(OrderSide.SELL)
        
        success_count = 0
        
        for grad_index, order_sm in enumerate(active_orders, start=1):
            # 创建改价命令
            command = RepriceSellOrderCommand(
                context=self.context,
                price_strategy=self.price_strategy,
                order_sm=order_sm,
                tick_size=tick_size,
                price_decimals=price_decimals,
                step_size=step_size,
                qty_decimals=qty_decimals,
                grad_index=grad_index
            )
            
            # 执行命令
            success, result, error = self.executor.execute(command)
            
            if success and result:
                success_count += 1
                log_prefix = self.context.get_log_prefix()
                print(f"{log_prefix} ✅ 卖单改价成功: {order_sm.info.order_id}, 目标价格={order_sm.info.price:.6f}/当前价格={self.context.market.current_price:.6f}, 改价次数={order_sm.metrics.reprice_count}")
            elif error:
                log_prefix = self.context.get_log_prefix()
                print(f"{log_prefix} ❌ 卖单改价失败 {order_sm.info.order_id}: {error}")
        
        return success_count
