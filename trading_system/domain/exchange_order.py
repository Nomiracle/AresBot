"""
交易所订单信息 - 不可变对象（用于v2接口）
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass(frozen=True)
class ExchangeOrder:
    """交易所订单信息（不可变）"""
    order_id: str
    symbol: str
    side: str  # 'BUY' 或 'SELL'
    price: float
    quantity: float  # 原始数量
    executed_qty: float = 0.0  # 已成交数量
    status: str = 'NEW'  # 订单状态
    order_type: str = 'LIMIT'  # 订单类型
    time_in_force: str = 'GTC'  # 有效期
    created_time: Optional[int] = None  # 创建时间戳
    updated_time: Optional[int] = None  # 更新时间戳
    info: Optional[Dict[str, Any]] = None  # 原始数据
    
    def __post_init__(self):
        """验证数据"""
        if self.side not in ('BUY', 'SELL'):
            raise ValueError(f"订单方向必须是 'BUY' 或 'SELL': {self.side}")
        if self.price <= 0:
            raise ValueError(f"价格必须大于0: {self.price}")
        if self.quantity <= 0:
            raise ValueError(f"数量必须大于0: {self.quantity}")
        if self.executed_qty < 0:
            raise ValueError(f"已成交数量不能为负数: {self.executed_qty}")
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExchangeOrder':
        """从字典创建订单信息"""
        return cls(
            order_id=str(data.get('orderId') or data.get('id')),
            symbol=data.get('symbol', ''),
            side=str(data.get('side', '')).upper(),
            price=float(data.get('price', 0)),
            quantity=float(data.get('origQty', 0) or data.get('amount', 0)),
            executed_qty=float(data.get('executedQty', 0) or data.get('filled', 0)),
            status=str(data.get('status', 'NEW')).upper(),
            order_type=str(data.get('type', 'LIMIT')).upper(),
            time_in_force=str(data.get('timeInForce', 'GTC')).upper(),
            created_time=data.get('time') or data.get('timestamp'),
            updated_time=data.get('updateTime') or data.get('lastTradeTimestamp'),
            info=data.get('info') or data
        )
    
    @property
    def remaining_qty(self) -> float:
        """剩余未成交数量"""
        return max(0.0, self.quantity - self.executed_qty)
    
    @property
    def is_filled(self) -> bool:
        """是否完全成交"""
        return self.status == 'FILLED' or self.executed_qty >= self.quantity
    
    @property
    def is_active(self) -> bool:
        """是否为活跃订单"""
        return self.status in ('NEW', 'PARTIALLY_FILLED')
