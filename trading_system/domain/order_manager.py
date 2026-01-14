"""
订单管理器
"""

from threading import Lock
from typing import Dict, List, Optional
from .order_state_machine import OrderStateMachine
from .order_state import OrderSide, OrderState


class OrderManager:
    """订单管理器 - 管理所有订单状态机"""
    
    def __init__(self):
        self._orders: Dict[str, OrderStateMachine] = {}
        self._lock = Lock()
    
    def add_order(self, order_sm: OrderStateMachine) -> None:
        """
        添加订单
        
        Args:
            order_sm: 订单状态机
        """
        with self._lock:
            self._orders[order_sm.info.order_id] = order_sm
    
    def get_order(self, order_id: str) -> Optional[OrderStateMachine]:
        """
        获取订单
        
        Args:
            order_id: 订单ID
            
        Returns:
            订单状态机或None
        """
        with self._lock:
            return self._orders.get(order_id)
    
    def remove_order(self, order_id: str) -> None:
        """
        移除订单
        
        Args:
            order_id: 订单ID
        """
        with self._lock:
            self._orders.pop(order_id, None)
    
    def get_active_orders(self, side: Optional[OrderSide] = None) -> List[OrderStateMachine]:
        """
        获取活跃订单
        
        Args:
            side: 订单方向（可选）
            
        Returns:
            活跃订单列表
        """
        with self._lock:
            orders = [
                order for order in self._orders.values()
                if order.is_active()
            ]
            
            if side is not None:
                orders = [o for o in orders if o.info.side == side]
            
            return orders
    
    def get_all_orders(self, side: Optional[OrderSide] = None) -> List[OrderStateMachine]:
        """
        获取所有订单
        
        Args:
            side: 订单方向（可选）
            
        Returns:
            所有订单列表
        """
        with self._lock:
            orders = list(self._orders.values())
            
            if side is not None:
                orders = [o for o in orders if o.info.side == side]
            
            return orders
    
    def cleanup_terminal_orders(self) -> int:
        """
        清理终态订单
        
        Returns:
            清理的订单数量
        """
        with self._lock:
            terminal_ids = [
                order_id for order_id, order in self._orders.items()
                if order.is_terminal()
            ]
            
            for order_id in terminal_ids:
                del self._orders[order_id]
            
            return len(terminal_ids)
    
    def get_order_count(self, side: Optional[OrderSide] = None, state: Optional[OrderState] = None) -> int:
        """
        获取订单数量
        
        Args:
            side: 订单方向（可选）
            state: 订单状态（可选）
            
        Returns:
            订单数量
        """
        with self._lock:
            orders = list(self._orders.values())
            
            if side is not None:
                orders = [o for o in orders if o.info.side == side]
            
            if state is not None:
                orders = [o for o in orders if o.state == state]
            
            return len(orders)
