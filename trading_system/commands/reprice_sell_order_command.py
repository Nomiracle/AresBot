"""
改价卖单命令
"""

import math
from typing import TYPE_CHECKING
from .trading_command import TradingCommand
from ..domain import OrderState

if TYPE_CHECKING:
    from ..domain import TradingContext, OrderStateMachine
    from ..strategy import PriceCalculationStrategy


class RepriceSellOrderCommand(TradingCommand):
    """改价卖单命令"""
    
    def __init__(
        self,
        context: 'TradingContext',
        price_strategy: 'PriceCalculationStrategy',
        order_sm: 'OrderStateMachine',
        tick_size: float,
        price_decimals: int,
        step_size: float,
        qty_decimals: int,
        grad_index: int = 1
    ):
        """
        初始化改价卖单命令
        
        Args:
            context: 交易上下文
            price_strategy: 价格策略
            order_sm: 订单状态机
            tick_size: 价格步长
            price_decimals: 价格小数位
            step_size: 数量步长
            qty_decimals: 数量小数位
            grad_index: 梯度索引
        """
        self.context = context
        self.price_strategy = price_strategy
        self.order_sm = order_sm
        self.tick_size = tick_size
        self.price_decimals = price_decimals
        self.step_size = step_size
        self.qty_decimals = qty_decimals
        self.grad_index = grad_index
    
    def validate(self) -> tuple[bool, str | None]:
        """验证命令"""
        if not self.order_sm.can_reprice():
            return False, f"订单状态不允许改价: {self.order_sm.state}"
        
        if self.context.market.current_price is None:
            return False, "当前价格为空"
        
        if self.order_sm.info.buy_price is None:
            return False, "买入价格为空"
        
        return True, None
    
    def _calculate_dynamic_sell_offset(self) -> float:
        """计算动态卖出偏移"""
        offset_percent = self.context.config.offset_percent
        base_sell_offset = self.context.config.sell_offset_percent
        sell_decay_count = self.context.config.sell_decay_count
        reprice_count = self.order_sm.metrics.reprice_count
        
        # 判断是否使用衰减逻辑
        abs_buy_offset = abs(offset_percent)
        use_decay = sell_decay_count > 0 and abs_buy_offset > base_sell_offset
        
        # 计算目标卖价
        if use_decay and reprice_count < sell_decay_count:
            # 使用衰减逻辑
            A = abs(abs_buy_offset - base_sell_offset)
            decay_percent = 100.0 / sell_decay_count
            reduction = reprice_count * (decay_percent / 100.0) * A
            calculated_offset = abs_buy_offset - reduction
            
            if calculated_offset < base_sell_offset:
                dynamic_sell_offset = base_sell_offset
            else:
                dynamic_sell_offset = calculated_offset
        else:
            # 不使用衰减逻辑
            dynamic_sell_offset = base_sell_offset
        
        # 应用梯度调整
        dynamic_sell_offset = dynamic_sell_offset * self.grad_index
        
        return dynamic_sell_offset
    
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
        buy_price = self.order_sm.info.buy_price
        
        # 计算动态卖出偏移
        dynamic_sell_offset = self._calculate_dynamic_sell_offset()
        
        # 计算目标价格
        target_price = self.price_strategy.calculate_sell_price(
            buy_price=buy_price,
            offset_percent=dynamic_sell_offset,
            tick_size=self.tick_size,
            price_decimals=self.price_decimals,
            current_price=current_price,
            exchange=self.context.exchange
        )
        
        # 更新目标价格
        self.context.market.target_price = target_price
        
        # 检查是否需要改价
        if self._should_skip_reprice(target_price, current_price):
            return False
        
        # 状态转换到改价中
        if not self.order_sm.transition_to(OrderState.REPRICING, "开始改价"):
            return False
        
        # 标记正在改价的订单
        self.context.runtime.repricing_order_id = self.order_sm.info.order_id
        
        try:
            # 对齐数量
            aligned_qty = math.floor(self.order_sm.info.quantity / self.step_size) * self.step_size
            aligned_qty = round(aligned_qty, self.qty_decimals)
            
            # 调用交易所改价API
            resp = self.context.exchange.cancel_replace_order(
                side='SELL',
                order_type='LIMIT',
                quantity=aligned_qty,
                price=f"{target_price}",
                cancel_order_id=self.order_sm.info.order_id,
                timeInForce='GTC',
                current_price=current_price,
                entry_price=buy_price
            )
            
            # 提取新订单ID
            new_order_id = None
            if isinstance(resp, dict):
                new_order_data = resp.get('newOrderResponse', {})
                if isinstance(new_order_data, dict):
                    new_order_id = str(new_order_data.get('orderId') or new_order_data.get('id'))
            
            log_prefix = self.context.get_log_prefix()
            print(f"{log_prefix} 🔍 [改价卖单] 旧订单ID: {self.order_sm.info.order_id}, 新订单ID: {new_order_id}")
            
            # 如果订单ID变化，说明是取消+新建模式
            if new_order_id and new_order_id != self.order_sm.info.order_id:
                print(f"{log_prefix} 🔄 [改价卖单] 订单ID变化，创建新订单")
                
                # 保存旧订单的买单成交时间（用于止损）
                old_filled_at = self.order_sm.metrics.filled_at
                
                # 旧订单标记为已取消
                self.order_sm.transition_to(OrderState.CANCELLED, "改价时取消")
                
                # 创建新订单状态机
                from ..domain import OrderInfo, OrderStateMachine
                new_order_info = OrderInfo(
                    order_id=new_order_id,
                    symbol=self.order_sm.info.symbol,
                    side=self.order_sm.info.side,
                    price=target_price,
                    quantity=aligned_qty,
                    grid_index=self.order_sm.info.grid_index,
                    buy_price=self.order_sm.info.buy_price,  # 保留买入价格
                    buy_order_id=self.order_sm.info.buy_order_id  # 保留买单ID
                )
                new_order_sm = OrderStateMachine(new_order_info, OrderState.PENDING)
                new_order_sm.transition_to(OrderState.PLACED, "改价后新订单")
                
                # 传递买单成交时间到新订单（用于止损计时）
                if old_filled_at is not None:
                    new_order_sm.metrics.filled_at = old_filled_at
                    print(f"{log_prefix} 🕐 [改价卖单] 已传递买单成交时间: {old_filled_at}")
                
                # 添加新订单到管理器
                self.context.order_manager.add_order(new_order_sm)
                print(f"{log_prefix} ✅ [改价卖单] 已添加新订单: {new_order_id}, state={new_order_sm.state.name}")
            else:
                # 订单ID未变化（原子改单），只更新价格和状态
                self.order_sm.update_price(target_price)
                self.order_sm.transition_to(OrderState.PLACED, "改价成功")
                print(f"{log_prefix} ✅ [改价卖单] 原子改单成功，订单ID未变化")
            
            return True
            
        except Exception as e:
            # 改价失败，恢复状态
            self.order_sm.transition_to(OrderState.PLACED, f"改价失败: {e}")
            self.order_sm.metrics.record_error(str(e))
            raise
        finally:
            # 清除改价标记
            self.context.runtime.repricing_order_id = None
