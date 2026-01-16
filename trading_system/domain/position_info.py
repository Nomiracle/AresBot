"""
持仓信息 - 不可变对象
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass(frozen=True)
class PositionInfo:
    """持仓信息（不可变）"""
    symbol: str
    side: str  # 'long' 或 'short'
    contracts: float  # 持仓数量（合约张数）
    entry_price: float  # 开仓均价
    unrealized_pnl: float = 0.0  # 未实现盈亏
    leverage: Optional[float] = None  # 杠杆倍数
    liquidation_price: Optional[float] = None  # 强平价格
    margin: Optional[float] = None  # 保证金
    info: Optional[Dict[str, Any]] = None  # 原始数据
    
    def __post_init__(self):
        """验证数据"""
        if self.side not in ('long', 'short'):
            raise ValueError(f"持仓方向必须是 'long' 或 'short': {self.side}")
        if self.contracts < 0:
            raise ValueError(f"持仓数量不能为负数: {self.contracts}")
        if self.entry_price <= 0:
            raise ValueError(f"开仓均价必须大于0: {self.entry_price}")
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PositionInfo':
        """从字典创建持仓信息"""
        return cls(
            symbol=data.get('symbol', ''),
            side=data.get('side', '').lower(),
            contracts=abs(float(data.get('contracts', 0) or data.get('info', {}).get('positionAmt', 0))),
            entry_price=float(data.get('entryPrice', 0) or data.get('info', {}).get('entryPrice', 0)),
            unrealized_pnl=float(data.get('unrealizedPnl', 0) or data.get('info', {}).get('unrealizedProfit', 0)),
            leverage=float(data.get('leverage')) if data.get('leverage') else None,
            liquidation_price=float(data.get('liquidationPrice')) if data.get('liquidationPrice') else None,
            margin=float(data.get('margin')) if data.get('margin') else None,
            info=data.get('info')
        )
