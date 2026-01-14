"""
改价买单命令
"""

from typing import TYPE_CHECKING
from .trading_command import TradingCommand
from ..domain import OrderState

if TYPE_CHECKING:
    from ..domain import TradingContext, OrderStateMachine
    from ..strategy import PriceCalculationStrategy


class RepriceBuyOrderCommand(TradingCommand):
    """改价买单命令"""
    
    def __init__(
        self,
        context: 'TradingContext',
        price_strategy: 'PriceCalculationStrategy',
        order_sm: 'OrderStateMachine',
        tick_size: float,
        price_decimals: int
    ):
        """
        初始化改价买单命令
        
        Args:
            context: 交易上下文
            price_strategy: 价格策略
            order_sm: 订单状态机
            tick_size: 价格步长
            price_decimals: 价格小数位
        """
        self.context = context
        self.price_strategy = price_strategy
        self.order_sm = order_sm
        self.tick_size = tick_size
        self.price_decimals = price_decimals
    
    def validate(self) -> tuple[bool, str | None]:
        """验证命令"""
        if not self.order_sm.can_reprice():
            return False, f"订单状态不允许改价: {self.order_sm.state}"
        
        if self.context.market.current_price is None:
            return False, "当前价格为空"
        
        return True, None
    
    def _should_skip_reprice(self, target_price: float, current_price: float) -> bool:
        """判断是否应该跳过改价"""
        # 检查目标价格是否与缓存价格一致
        cached_price = self.order_sm.info.price
        if abs(target_price - cached_price) < self.tick_size:
            return True
        
        # 检查价格差异百分比
        if abs(target_price - current_price) <= self.tick_size:
            return False
        
        price_diff_percent = abs(target_price - current_price) / current_price * 100
        reprice_threshold = self.context.config.reprice_threshold_percent
        
        return price_diff_percent < reprice_threshold
    
    def execute(self) -> bool:
        """
        执行改价
        
        Returns:
            是否改价成功
        """
        current_price = self.context.market.current_price
        
        # 计算目标价格
        target_price = self.price_strategy.calculate_buy_price(
            current_price=current_price,
            offset_percent=self.context.config.offset_percent,
            grid_index=self.order_sm.info.grid_index,
            tick_size=self.tick_size,
            price_decimals=self.price_decimals,
            exchange=self.context.exchange
        )
        
        # 更新第一格的目标价格
        if self.order_sm.info.grid_index == 1:
            self.context.market.target_price = target_price
        
        # 检查是否需要改价
        if self._should_skip_reprice(target_price, current_price):
            return False
        
        # 状态转换到改价中
        if not self.order_sm.transition_to(OrderState.REPRICING, "开始改价"):
            return False
        
        try:
            # 调用交易所改价API
            resp = self.context.exchange.cancel_replace_order(
                side='BUY',
                order_type='LIMIT',
                quantity=self.order_sm.info.quantity,
                price=f"{target_price}",
                cancel_order_id=self.order_sm.info.order_id,
                timeInForce='GTC',
                current_price=current_price
            )
            
            # 提取新订单ID
            new_order_id = None
            if isinstance(resp, dict):
                new_order_data = resp.get('newOrderResponse', {})
                if isinstance(new_order_data, dict):
                    new_order_id = str(new_order_data.get('orderId') or new_order_data.get('id'))
            
            # 更新订单价格
            self.order_sm.update_price(target_price)
            
            # 如果订单ID变化，需要更新
            if new_order_id and new_order_id != self.order_sm.info.order_id:
                # 移除旧订单
                self.context.order_manager.remove_order(self.order_sm.info.order_id)
                # 更新订单ID
                object.__setattr__(self.order_sm.info, 'order_id', new_order_id)
                # 重新添加
                self.context.order_manager.add_order(self.order_sm)
            
            # 状态转换回已下单
            self.order_sm.transition_to(OrderState.PLACED, "改价成功")
            
            return True
            
        except Exception as e:
            # 改价失败，恢复状态
            self.order_sm.transition_to(OrderState.PLACED, f"改价失败: {e}")
            self.order_sm.metrics.record_error(str(e))
            raise
