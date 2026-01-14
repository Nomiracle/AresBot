"""
订单下单服务
"""

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..domain import TradingContext
    from ..strategy import PriceCalculationStrategy
    from ..commands import CommandExecutor


class OrderPlacementService:
    """订单下单服务"""
    
    def __init__(
        self,
        context: 'TradingContext',
        price_strategy: 'PriceCalculationStrategy',
        executor: 'CommandExecutor'
    ):
        """
        初始化下单服务
        
        Args:
            context: 交易上下文
            price_strategy: 价格策略
            executor: 命令执行器
        """
        self.context = context
        self.price_strategy = price_strategy
        self.executor = executor
    
    def place_buy_orders(
        self,
        count: int,
        start_grid_index: int,
        tick_size: float,
        price_decimals: int,
        step_size: float,
        qty_decimals: int
    ) -> list[str]:
        """
        批量下买单
        
        Args:
            count: 下单数量
            start_grid_index: 起始网格索引
            tick_size: 价格步长
            price_decimals: 价格小数位
            step_size: 数量步长
            qty_decimals: 数量小数位
            
        Returns:
            订单ID列表
        """
        from ..commands import PlaceBuyOrderCommand
        
        order_ids = []
        
        # 对齐下单数量
        aligned_quantity = math.floor(self.context.config.quantity / step_size) * step_size if step_size else self.context.config.quantity
        aligned_quantity = round(aligned_quantity, qty_decimals)
        
        for i in range(count):
            grid_index = start_grid_index + i
            
            # 检查是否正在处理买单成交
            if self.context.runtime.is_handling_buy_filled:
                print(f"{self.context.get_log_prefix()} ⏸️ 正在处理买单成交，跳过下单")
                break
            
            # 创建下单命令
            command = PlaceBuyOrderCommand(
                context=self.context,
                price_strategy=self.price_strategy,
                grid_index=grid_index,
                quantity=aligned_quantity,
                tick_size=tick_size,
                price_decimals=price_decimals
            )
            
            # 执行命令
            success, order_id, error = self.executor.execute(command)
            
            if success:
                order_ids.append(order_id)
                log_prefix = self.context.get_log_prefix()
                target_price = self.context.market.target_price if grid_index == 1 else None
                grid_offset = grid_index * self.context.config.offset_percent
                print(f"{log_prefix} ✅ 新买单[{grid_index}/{self.context.config.order_grid}] {order_id}: 价格={target_price}, 数量={aligned_quantity}, 偏移={grid_offset:.2f}%")
            else:
                log_prefix = self.context.get_log_prefix()
                print(f"{log_prefix} ❌ 下单失败: {error}")
                self.context.runtime.record_error(f"下单失败: {error}")
                break
        
        return order_ids
