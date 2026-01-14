"""
价格计算策略接口
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..infrastructure.exchange_adapter import ExchangeAdapter


class PriceCalculationStrategy(ABC):
    """价格计算策略接口"""
    
    @abstractmethod
    def calculate_buy_price(
        self,
        current_price: float,
        offset_percent: float,
        grid_index: int,
        tick_size: float,
        price_decimals: int,
        exchange: 'ExchangeAdapter'
    ) -> float:
        """
        计算买入价格
        
        Args:
            current_price: 当前价格
            offset_percent: 偏移百分比
            grid_index: 网格索引
            tick_size: 价格步长
            price_decimals: 价格小数位
            exchange: 交易所适配器
            
        Returns:
            买入价格
        """
        pass
    
    @abstractmethod
    def calculate_sell_price(
        self,
        buy_price: float,
        offset_percent: float,
        tick_size: float,
        price_decimals: int,
        current_price: float,
        exchange: 'ExchangeAdapter'
    ) -> float:
        """
        计算卖出价格
        
        Args:
            buy_price: 买入价格
            offset_percent: 偏移百分比
            tick_size: 价格步长
            price_decimals: 价格小数位
            current_price: 当前价格
            exchange: 交易所适配器
            
        Returns:
            卖出价格
        """
        pass
