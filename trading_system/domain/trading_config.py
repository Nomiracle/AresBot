"""
交易配置 - 不可变对象
"""

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class TradingConfig:
    """交易配置（不可变）"""
    symbol: str
    exchange: str
    quantity: float
    interval: int
    offset_percent: float
    sell_offset_percent: float
    order_grid: int = 1
    sell_decay_count: int = 0
    reprice_threshold_percent: float = 0.01
    simulate_trading: int = 0
    
    def validate(self) -> List[str]:
        """
        验证配置
        
        Returns:
            错误列表（空列表表示验证通过）
        """
        errors = []
        
        if not self.symbol:
            errors.append("symbol不能为空")
        
        if not self.exchange:
            errors.append("exchange不能为空")
        
        if self.quantity <= 0:
            errors.append(f"quantity必须大于0: {self.quantity}")
        
        if self.interval <= 0:
            errors.append(f"interval必须大于0: {self.interval}")
        
        if self.order_grid < 1:
            errors.append(f"order_grid必须>=1: {self.order_grid}")
        
        if self.sell_decay_count < 0:
            errors.append(f"sell_decay_count必须>=0: {self.sell_decay_count}")
        
        if self.reprice_threshold_percent < 0:
            errors.append(f"reprice_threshold_percent必须>=0: {self.reprice_threshold_percent}")
        
        return errors
    
    @property
    def is_buy_enabled(self) -> bool:
        """是否启用买入"""
        return self.simulate_trading != 1
