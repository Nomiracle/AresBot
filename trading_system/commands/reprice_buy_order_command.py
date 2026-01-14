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
            # 调试日志：显示跳过改价的原因
            cached_price = self.order_sm.info.price
            price_diff = abs(target_price - cached_price)
            log_prefix = self.context.get_log_prefix()
            if price_diff < self.tick_size:
                print(f"{log_prefix} ⏭️ 跳过改价[{self.order_sm.info.grid_index}] {self.order_sm.info.order_id}: 价格差异{price_diff:.6f} < tick_size{self.tick_size}")
            else:
                price_diff_percent = abs(target_price - current_price) / current_price * 100
                print(f"{log_prefix} ⏭️ 跳过改价[{self.order_sm.info.grid_index}] {self.order_sm.info.order_id}: 价格差异{price_diff_percent:.4f}% < 阈值{self.context.config.reprice_threshold_percent}%")
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
            
            log_prefix = self.context.get_log_prefix()
            print(f"{log_prefix} 🔍 [改价命令] 旧订单ID: {self.order_sm.info.order_id}, 新订单ID: {new_order_id}")
            
            # 如果订单ID变化，说明是取消+新建模式
            if new_order_id and new_order_id != self.order_sm.info.order_id:
                print(f"{log_prefix} 🔄 [改价命令] 订单ID变化，创建新订单")
                
                # 旧订单标记为已取消
                self.order_sm.transition_to(OrderState.CANCELLED, "改价时取消")
                
                # 创建新订单状态机
                from ..domain import OrderInfo, OrderStateMachine
                new_order_info = OrderInfo(
                    order_id=new_order_id,
                    symbol=self.order_sm.info.symbol,
                    side=self.order_sm.info.side,
                    price=target_price,
                    quantity=self.order_sm.info.quantity,
                    grid_index=self.order_sm.info.grid_index
                )
                new_order_sm = OrderStateMachine(new_order_info, OrderState.PENDING)
                new_order_sm.transition_to(OrderState.PLACED, "改价后新订单")
                
                # 添加新订单到管理器
                self.context.order_manager.add_order(new_order_sm)
                print(f"{log_prefix} ✅ [改价命令] 已添加新订单: {new_order_id}, state={new_order_sm.state.name}")
            else:
                # 订单ID未变化（原子改单），只更新价格和状态
                self.order_sm.update_price(target_price)
                self.order_sm.transition_to(OrderState.PLACED, "改价成功")
                print(f"{log_prefix} ✅ [改价命令] 原子改单成功，订单ID未变化")
            
            return True
            
        except Exception as e:
            # 改价失败，恢复状态
            self.order_sm.transition_to(OrderState.PLACED, f"改价失败: {e}")
            self.order_sm.metrics.record_error(str(e))
            raise
