"""
订单状态机
"""

from threading import Lock
from typing import Optional
from .order_state import OrderState
from .order_info import OrderInfo
from .order_metrics import OrderMetrics


class OrderStateMachine:
    """订单状态机 - 管理订单生命周期"""
    
    # 允许的状态转换
    _ALLOWED_TRANSITIONS = {
        OrderState.PENDING: {OrderState.PLACED, OrderState.FAILED},
        OrderState.PLACED: {OrderState.FILLED, OrderState.CANCELLED, OrderState.REPRICING, OrderState.FAILED},
        OrderState.REPRICING: {OrderState.PLACED, OrderState.CANCELLED, OrderState.FAILED},
        OrderState.FILLED: set(),
        OrderState.CANCELLED: set(),
        OrderState.FAILED: set(),
    }
    
    def __init__(self, info: OrderInfo, initial_state: OrderState = OrderState.PENDING):
        """
        初始化订单状态机
        
        Args:
            info: 订单信息
            initial_state: 初始状态
        """
        self.info = info
        self.state = initial_state
        self.metrics = OrderMetrics()
        self._lock = Lock()
    
    def transition_to(self, new_state: OrderState, reason: str = "") -> bool:
        """
        状态转换
        
        Args:
            new_state: 新状态
            reason: 转换原因
            
        Returns:
            是否转换成功
        """
        with self._lock:
            if new_state not in self._ALLOWED_TRANSITIONS.get(self.state, set()):
                return False
            
            old_state = self.state
            self.state = new_state
            
            # 更新指标
            if new_state == OrderState.FILLED:
                self.metrics.mark_filled()
            
            return True
    
    def is_terminal(self) -> bool:
        """是否为终态"""
        return self.state in {OrderState.FILLED, OrderState.CANCELLED, OrderState.FAILED}
    
    def is_active(self) -> bool:
        """是否为活跃状态"""
        return self.state == OrderState.PLACED
    
    def can_reprice(self) -> bool:
        """是否可以改价"""
        return self.state == OrderState.PLACED
    
    def update_price(self, new_price: float) -> None:
        """
        更新价格（改价后）
        
        Args:
            new_price: 新价格
        """
        with self._lock:
            # 创建新的OrderInfo（因为是frozen的）
            object.__setattr__(self, 'info', OrderInfo(
                order_id=self.info.order_id,
                symbol=self.info.symbol,
                side=self.info.side,
                price=new_price,
                quantity=self.info.quantity,
                grid_index=self.info.grid_index,
                buy_order_id=self.info.buy_order_id,
                buy_price=self.info.buy_price
            ))
            self.metrics.increment_reprice()
