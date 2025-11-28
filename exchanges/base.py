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
        """获取交易对当前价格（内部使用）"""
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
        """取消订单（内部使用）"""
        pass
    
    @abstractmethod
    def cancel_replace_order(self, symbol: str, side: str, order_type: str, 
                            quantity: float, price: str, cancel_order_id: str, **kwargs) -> Dict:
        """取消并替换订单（改价）"""
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
    
    @abstractmethod
    def start_ws(self, symbol: str, on_price_update: Callable[[float], None], 
                 on_order_update: Callable[[Dict], None]) -> bool:
        """启动 WebSocket 监听（价格和订单）
        
        Args:
            symbol: 交易对
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
