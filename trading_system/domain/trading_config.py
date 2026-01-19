"""
交易配置 - 不可变对象
"""

from dataclasses import dataclass
from typing import List, Optional


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
    stop_loss_delay: int = 120
    min_price_threshold: float = 1.0
    
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

        if self.stop_loss_delay < 0:
            errors.append(f"stop_loss_delay必须>=0: {self.stop_loss_delay}")

        if self.min_price_threshold < 0:
            errors.append(f"min_price_threshold必须>=0: {self.min_price_threshold}")
        
        return errors
    
    @property
    def is_buy_enabled(self) -> bool:
        """是否启用买入"""
        return self.simulate_trading != 1
