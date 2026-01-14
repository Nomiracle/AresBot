"""
订单指标
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class OrderMetrics:
    """订单指标"""
    reprice_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    filled_at: Optional[datetime] = None
    error_message: Optional[str] = None
    
    def increment_reprice(self) -> None:
        """增加改价次数"""
        self.reprice_count += 1
        self.updated_at = datetime.now()
    
    def mark_filled(self) -> None:
        """标记为已成交"""
        self.filled_at = datetime.now()
        self.updated_at = datetime.now()
    
    def record_error(self, error: str) -> None:
        """记录错误"""
        self.error_message = error
        self.updated_at = datetime.now()
