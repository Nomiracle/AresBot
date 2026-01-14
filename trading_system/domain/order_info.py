"""
订单信息 - 不可变对象
"""

from dataclasses import dataclass
from typing import Optional
from .order_state import OrderSide


@dataclass(frozen=True)
class OrderInfo:
    """订单信息（不可变）"""
    order_id: str
    symbol: str
    side: OrderSide
    price: float
    quantity: float
    grid_index: int = 1
    buy_order_id: Optional[str] = None
    buy_price: Optional[float] = None
    
    def __post_init__(self):
        """验证数据"""
        if self.price <= 0:
            raise ValueError(f"价格必须大于0: {self.price}")
        if self.quantity <= 0:
            raise ValueError(f"数量必须大于0: {self.quantity}")
        if self.grid_index < 1:
            raise ValueError(f"网格索引必须>=1: {self.grid_index}")
