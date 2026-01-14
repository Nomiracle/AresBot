"""
运行时状态
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Set


@dataclass
class RuntimeState:
    """运行时状态"""
    running: bool = False
    is_placing_order: bool = False
    is_handling_buy_filled: bool = False
    monitor_started: bool = False
    
    last_error: Optional[str] = None
    error_count: int = 0
    last_error_time: Optional[datetime] = None
    
    last_warning: Optional[str] = None
    warning_count: int = 0
    
    processed_filled_orders: Set[str] = field(default_factory=set)
    repricing_order_id: Optional[str] = None
    
    def record_error(self, error: str) -> None:
        """
        记录错误
        
        Args:
            error: 错误信息
        """
        self.last_error = error
        self.error_count += 1
        self.last_error_time = datetime.now()
    
    def clear_error(self) -> None:
        """清除错误"""
        self.last_error = None
        self.last_error_time = None
    
    def record_warning(self, warning: str) -> None:
        """
        记录警告
        
        Args:
            warning: 警告信息
        """
        self.last_warning = warning
        self.warning_count += 1
    
    def clear_warning(self) -> None:
        """清除警告"""
        self.last_warning = None
    
    def mark_order_processed(self, order_id: str) -> None:
        """
        标记订单已处理
        
        Args:
            order_id: 订单ID
        """
        self.processed_filled_orders.add(order_id)
    
    def is_order_processed(self, order_id: str) -> bool:
        """
        检查订单是否已处理
        
        Args:
            order_id: 订单ID
            
        Returns:
            是否已处理
        """
        return order_id in self.processed_filled_orders
