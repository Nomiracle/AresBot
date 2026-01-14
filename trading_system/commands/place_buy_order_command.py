"""
下买单命令
"""

from typing import TYPE_CHECKING
from .trading_command import TradingCommand
from ..domain import OrderInfo, OrderStateMachine, OrderState, OrderSide

if TYPE_CHECKING:
    from ..domain import TradingContext
    from ..strategy import PriceCalculationStrategy


class PlaceBuyOrderCommand(TradingCommand):
    """下买单命令"""
    
    def __init__(
        self,
        context: 'TradingContext',
        price_strategy: 'PriceCalculationStrategy',
        grid_index: int,
        quantity: float,
        tick_size: float,
        price_decimals: int
    ):
        """
        初始化下买单命令
        
        Args:
            context: 交易上下文
            price_strategy: 价格策略
            grid_index: 网格索引
            quantity: 下单数量
            tick_size: 价格步长
            price_decimals: 价格小数位
        """
        self.context = context
        self.price_strategy = price_strategy
        self.grid_index = grid_index
        self.quantity = quantity
        self.tick_size = tick_size
        self.price_decimals = price_decimals
    
    def validate(self) -> tuple[bool, str | None]:
        """验证命令"""
        can_place, reason = self.context.can_place_order()
        if not can_place:
            return False, reason
        
        if self.context.market.current_price is None:
            return False, "当前价格为空"
        
        if self.quantity <= 0:
            return False, f"数量必须大于0: {self.quantity}"
        
        return True, None
    
    def execute(self) -> str:
        """
        执行下买单
        
        Returns:
            订单ID
        """
        # 计算目标价格
        target_price = self.price_strategy.calculate_buy_price(
            current_price=self.context.market.current_price,
            offset_percent=self.context.config.offset_percent,
            grid_index=self.grid_index,
            tick_size=self.tick_size,
            price_decimals=self.price_decimals,
            exchange=self.context.exchange
        )
        
        # 更新第一格的目标价格
        if self.grid_index == 1:
            self.context.market.target_price = target_price
        
        # 调用交易所下单
        order_result = self.context.exchange.order_limit_buy(
            quantity=self.quantity,
            price=f"{target_price}",
            current_price=self.context.market.current_price
        )
        
        order_id = str(order_result.get('orderId') or order_result.get('id'))
        
        # 创建订单信息
        order_info = OrderInfo(
            order_id=order_id,
            symbol=self.context.config.symbol,
            side=OrderSide.BUY,
            price=target_price,
            quantity=self.quantity,
            grid_index=self.grid_index
        )
        
        # 创建订单状态机
        order_sm = OrderStateMachine(order_info, OrderState.PENDING)
        order_sm.transition_to(OrderState.PLACED, "下单成功")
        
        # 添加到订单管理器
        self.context.order_manager.add_order(order_sm)
        
        return order_id
