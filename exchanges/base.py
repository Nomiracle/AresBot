"""
Base exchange adapter interface
所有交易所适配器需要实现这个基类
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Callable


class BaseExchange(ABC):
    """交易所基类接口"""
    
    @abstractmethod
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        """初始化交易所客户端"""
        pass
    
    @abstractmethod
    def ping(self) -> bool:
        """测试连接"""
        pass
    
    @abstractmethod
    def get_symbol_info(self, symbol: str) -> Dict:
        """获取交易对信息（精度、过滤器等）"""
        pass
    
    @abstractmethod
    def get_symbol_ticker(self, symbol: str) -> Dict:
        """获取交易对当前价格"""
        pass
    
    @abstractmethod
    def get_open_orders(self, symbol: str) -> List[Dict]:
        """获取未完成订单"""
        pass
    
    @abstractmethod
    def get_order(self, symbol: str, order_id: str) -> Dict:
        """查询订单状态"""
        pass
    
    @abstractmethod
    def order_limit_buy(self, symbol: str, quantity: float, price: str, **kwargs) -> Dict:
        """限价买单"""
        pass
    
    @abstractmethod
    def order_limit_sell(self, symbol: str, quantity: float, price: str, **kwargs) -> Dict:
        """限价卖单"""
        pass
    
    @abstractmethod
    def cancel_order(self, symbol: str, order_id: str) -> Dict:
        """取消订单"""
        pass
    
    @abstractmethod
    def cancel_replace_order(self, symbol: str, side: str, order_type: str, 
                            quantity: float, price: str, cancel_order_id: str, **kwargs) -> Dict:
        """取消并替换订单（改价）"""
        pass
    
    @abstractmethod
    def start_websocket(self, symbol: str, on_ticker: Callable, on_user: Optional[Callable] = None) -> Dict:
        """启动 WebSocket 连接（行情流 + 用户数据流）
        
        Returns:
            Dict with keys:
                - 'manager': WebSocket manager instance
                - 'ticker_enabled': bool
                - 'user_enabled': bool
        """
        pass
    
    @abstractmethod
    def stop_websocket(self, ws_manager) -> None:
        """停止 WebSocket 连接"""
        pass
    
    @abstractmethod
    def parse_ticker_message(self, msg: Dict) -> Optional[float]:
        """解析行情消息，返回最新价格"""
        pass
    
    @abstractmethod
    def parse_user_message(self, msg: Dict) -> Optional[Dict]:
        """解析用户数据消息，返回标准化的订单事件
        
        Returns:
            Dict with keys:
                - 'event_type': 'order_filled' | 'order_update' | 'error' | None
                - 'order_id': str
                - 'symbol': str
                - 'side': 'BUY' | 'SELL'
                - 'status': 'NEW' | 'FILLED' | 'PARTIALLY_FILLED' | ...
                - 'price': float (optional)
                - 'quantity': float (optional)
                - 'error_message': str (optional, for errors)
        """
        pass
    
    @abstractmethod
    def get_price_precision(self, symbol_info: Dict) -> tuple:
        """从交易对信息中提取价格精度
        
        Returns:
            (tick_size: float, price_decimals: int)
        """
        pass
    
    @abstractmethod
    def get_quantity_precision(self, symbol_info: Dict) -> tuple:
        """从交易对信息中提取数量精度
        
        Returns:
            (step_size: float, qty_decimals: int)
        """
        pass
