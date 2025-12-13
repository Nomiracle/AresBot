"""
Base exchange adapter interface
所有交易所适配器需要实现这个基类
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Callable
import math


class BaseExchange(ABC):
    """交易所基类接口"""
    
    @abstractmethod
    def __init__(self, api_key: str, api_secret: str, symbol: str, testnet: bool = True):
        """初始化交易所客户端
        
        Args:
            api_key: API 密钥
            api_secret: API 密钥
            symbol: 交易对（如 BTCUSDT）
            testnet: 是否使用测试网
        """
        self.symbol = symbol
        pass
    
    @abstractmethod
    def ping(self) -> bool:
        """测试连接"""
        pass
    
    @abstractmethod
    def get_symbol_ticker(self) -> Dict:
        """获取交易对当前价格（内部使用）"""
        pass
    
    @abstractmethod
    def get_open_orders(self) -> List[Dict]:
        """获取未完成订单"""
        pass
    
    @abstractmethod
    def get_order(self, order_id: str) -> Dict:
        """查询订单状态"""
        pass
    
    @abstractmethod
    def order_limit_buy(self, quantity: float, price: str, **kwargs) -> Dict:
        """限价买单"""
        pass
    
    @abstractmethod
    def order_limit_sell(self, quantity: float, price: str, **kwargs) -> Dict:
        """限价卖单"""
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> Dict:
        """取消订单（内部使用）"""
        pass
    
    @abstractmethod
    def cancel_replace_order(self, side: str, order_type: str, 
                            quantity: float, price: str, cancel_order_id: str, **kwargs) -> Dict:
        """取消并替换订单（改价）"""
        pass
    
    @abstractmethod
    def get_trading_rules(self) -> Dict:
        """获取交易规则（精度信息）
        
        Returns:
            {
                'tick_size': float,      # 价格步长
                'price_decimals': int,   # 价格小数位数
                'step_size': float,      # 数量步长
                'qty_decimals': int      # 数量小数位数
            }
        """
        pass
    
    @abstractmethod
    def start_ws(self, on_price_update: Callable[[float], None], 
                 on_order_update: Callable[[Dict], None]) -> bool:
        """启动 WebSocket 监听（价格和订单）
        
        Args:
            on_price_update: 价格更新回调函数，参数为最新价格
            on_order_update: 订单更新回调函数，参数为订单事件字典
                {
                    'event_type': 'order_filled' | 'order_update',
                    'order_id': str,
                    'symbol': str,
                    'side': 'BUY' | 'SELL',
                    'status': 'FILLED' | 'PARTIALLY_FILLED' | ...,
                    'price': float,
                    'quantity': float
                }
            
        Returns:
            bool: 是否成功启动
        """
        pass
    
    @abstractmethod
    def stop_ws(self) -> None:
        """停止 WebSocket 监听（价格和订单）"""
        pass
    
    @abstractmethod
    def check_pending_orders(self, pending_orders: List[Dict]):
        """检查待处理订单的状态（用于 HTTP 轮询模式）
        
        Args:
            pending_orders: 待检查的订单列表，每个订单包含 order_id, symbol 等信息
            
        """
        pass

    def calculate_sell_price(self, buy_price, sell_offset_percent, tick_size, price_decimals, current_price=None):
        """计算卖出价格（带手续费保护）"""
        sell_offset = sell_offset_percent / 100.0
        raw_sell_price = (current_price or buy_price) * (1 + sell_offset)
        
        # 最低保护价（买入价 + 0.2% 手续费）
        min_price = buy_price * (1 + 2 * self.get_fee_rate())  # 买入价 + 2倍手续费
        min_price = math.ceil(min_price / tick_size) * tick_size if tick_size else min_price
        min_price = round(min_price, price_decimals)
        
        # 最终卖价
        sell_price = max(raw_sell_price, min_price)
        sell_price = math.floor(sell_price / tick_size) * tick_size if tick_size else sell_price
        return round(sell_price, price_decimals)

    def get_fee_rate(self) -> float:
        """获取交易对的手续费率
        
        Returns:
            float: 手续费率，例如 0.001 表示 0.1%
        """
        return 0.001  # 默认 0.1% 手续费