"""
市场状态
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class MarketState:
    """市场状态"""
    current_price: Optional[float] = None
    target_price: Optional[float] = None
    
    # 买单阶段价格差值统计
    buy_min_diff: Optional[float] = None
    buy_max_diff: Optional[float] = None
    buy_avg_diff: Optional[float] = None
    
    # 卖单阶段价格差值统计
    sell_min_diff: Optional[float] = None
    sell_max_diff: Optional[float] = None
    sell_avg_diff: Optional[float] = None
    
    last_update: Optional[datetime] = None
    
    def update_price(self, price: float) -> None:
        """
        更新当前价格
        
        Args:
            price: 新价格
        """
        self.current_price = price
        self.last_update = datetime.now()
    
    def is_stale(self, max_age_seconds: int = 60) -> bool:
        """
        检查价格是否过期
        
        Args:
            max_age_seconds: 最大有效期（秒）
            
        Returns:
            是否过期
        """
        if self.last_update is None:
            return True
        
        age = datetime.now() - self.last_update
        return age > timedelta(seconds=max_age_seconds)
    
    def reset_buy_stats(self) -> None:
        """重置买单统计"""
        self.buy_min_diff = None
        self.buy_max_diff = None
        self.buy_avg_diff = None
    
    def reset_sell_stats(self) -> None:
        """重置卖单统计"""
        self.sell_min_diff = None
        self.sell_max_diff = None
        self.sell_avg_diff = None
    
    def update_buy_stats(self, min_diff: Optional[float], avg_diff: Optional[float], max_diff: Optional[float]) -> None:
        """更新买单统计"""
        self.buy_min_diff = min_diff
        self.buy_avg_diff = avg_diff
        self.buy_max_diff = max_diff
    
    def update_sell_stats(self, min_diff: Optional[float], avg_diff: Optional[float], max_diff: Optional[float]) -> None:
        """更新卖单统计"""
        self.sell_min_diff = min_diff
        self.sell_avg_diff = avg_diff
        self.sell_max_diff = max_diff
