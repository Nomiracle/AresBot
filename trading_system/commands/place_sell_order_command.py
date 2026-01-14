"""
下卖单命令
"""

import math
from typing import TYPE_CHECKING
from .trading_command import TradingCommand
from ..domain import OrderInfo, OrderStateMachine, OrderState, OrderSide

if TYPE_CHECKING:
    from ..domain import TradingContext
    from ..strategy import PriceCalculationStrategy


class PlaceSellOrderCommand(TradingCommand):
    """下卖单命令"""
    
    def __init__(
        self,
        context: 'TradingContext',
        price_strategy: 'PriceCalculationStrategy',
        buy_order_id: str,
        buy_price: float,
        quantity: float,
        tick_size: float,
        price_decimals: int,
        step_size: float,
        qty_decimals: int,
        dynamic_sell_offset: float
    ):
        """
        初始化下卖单命令
        
        Args:
            context: 交易上下文
            price_strategy: 价格策略
            buy_order_id: 买单ID
            buy_price: 买入价格
            quantity: 卖出数量
            tick_size: 价格步长
            price_decimals: 价格小数位
            step_size: 数量步长
            qty_decimals: 数量小数位
            dynamic_sell_offset: 动态卖出偏移
        """
        self.context = context
        self.price_strategy = price_strategy
        self.buy_order_id = buy_order_id
        self.buy_price = buy_price
        self.quantity = quantity
        self.tick_size = tick_size
        self.price_decimals = price_decimals
        self.step_size = step_size
        self.qty_decimals = qty_decimals
        self.dynamic_sell_offset = dynamic_sell_offset
    
    def validate(self) -> tuple[bool, str | None]:
        """验证命令"""
        if self.buy_price <= 0:
            return False, f"买入价格必须大于0: {self.buy_price}"
        
        if self.quantity <= 0:
            return False, f"数量必须大于0: {self.quantity}"
        
        return True, None
    
    def execute(self) -> str:
        """
        执行下卖单
        
        Returns:
            订单ID
        """
        # 计算卖出价格
        sell_price = self.price_strategy.calculate_sell_price(
            buy_price=self.buy_price,
            offset_percent=self.dynamic_sell_offset,
            tick_size=self.tick_size,
            price_decimals=self.price_decimals,
            current_price=self.context.market.current_price,
            exchange=self.context.exchange
        )
        
        # 更新目标价格
        self.context.market.target_price = sell_price
        
        # 对齐数量
        aligned_qty = math.floor(self.quantity / self.step_size) * self.step_size if self.step_size else self.quantity
        aligned_qty = round(aligned_qty, self.qty_decimals)
        
        if aligned_qty <= 0:
            raise ValueError(f"对齐后数量为0，无法挂卖单: quantity={self.quantity}, step_size={self.step_size}")
        
        # 调用交易所下单
        order_result = self.context.exchange.order_limit_sell(
            quantity=aligned_qty,
            price=f"{sell_price}",
            current_price=self.context.market.current_price,
            entry_price=self.buy_price
        )
        
        order_id = str(order_result.get('orderId') or order_result.get('id'))
        
        # 创建订单信息
        order_info = OrderInfo(
            order_id=order_id,
            symbol=self.context.config.symbol,
            side=OrderSide.SELL,
            price=sell_price,
            quantity=aligned_qty,
            buy_order_id=self.buy_order_id,
            buy_price=self.buy_price
        )
        
        # 创建订单状态机
        order_sm = OrderStateMachine(order_info, OrderState.PENDING)
        order_sm.transition_to(OrderState.PLACED, "挂卖单成功")
        
        # 添加到订单管理器
        self.context.order_manager.add_order(order_sm)
        
        return order_id
