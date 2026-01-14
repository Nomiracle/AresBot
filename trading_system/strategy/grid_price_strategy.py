"""
网格价格策略实现
"""

from typing import TYPE_CHECKING
from .price_calculation_strategy import PriceCalculationStrategy

if TYPE_CHECKING:
    from ..infrastructure.exchange_adapter import ExchangeAdapter


class GridPriceStrategy(PriceCalculationStrategy):
    """网格价格策略"""
    
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
        
        网格买单价格 = 现价 * (1 + grid_index * offset_percent / 100)
        """
        grid_offset = grid_index * offset_percent
        return exchange.calculate_buy_target_price(
            current_price,
            grid_offset,
            tick_size,
            price_decimals
        )
    
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
        
        卖出价格 = 买入价 * (1 + offset_percent / 100)
        """
        return exchange.calculate_sell_price(
            buy_price,
            offset_percent,
            tick_size,
            price_decimals,
            current_price
        )
