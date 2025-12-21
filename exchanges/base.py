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
    
    def calculate_estimated_buy_price(self, sell_price: float, sell_offset_percent: float, tick_size: float, price_decimals: int, order: Optional[Dict] = None) -> float:
        """根据卖单价格反推估算的买入价格（用于恢复程序状态）
        
        默认实现（做多逻辑）：
        sell_price = buy_price * (1 + sell_offset)
        buy_price = sell_price / (1 + sell_offset)
        
        Args:
            sell_price: 当前挂出的卖单价格
            sell_offset_percent: 配置的卖出加价百分比
            tick_size: 价格最小跳动单位
            price_decimals: 价格小数位数
            order: 原始订单对象（可选），用于检查是否为虚拟订单等
            
        Returns:
            estimated_buy_price: 估算的原始买入价格
        """
        # 默认实现不使用 order 参数
        
        # 方案1: 假设卖价来自 raw_sell_price
        # sell_price ≈ buy_price * (1 + sell_offset/100)
        buy_price_from_raw = sell_price / (1 + sell_offset_percent / 100.0)
        
        # 方案2: 假设卖价来自 min_price (最低保护价, 默认按 2倍手续费保护)
        # min_price ≈ buy_price * (1 + 2*fee)
        # fee = 0.001 -> 1.002
        buy_price_from_min = sell_price / (1 + 2 * self.get_fee_rate())
        
        # 取较小值作为估算买入价 (更保守,确保不会低估)
        estimated_buy_price = min(buy_price_from_raw, buy_price_from_min)
        
        # 按 tick_size 向下对齐
        if tick_size and tick_size > 0:
            estimated_buy_price = math.floor(estimated_buy_price / tick_size) * tick_size
        
        return round(estimated_buy_price, price_decimals)
    
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
        
        if sell_price <= buy_price and tick_size:
            sell_price = round(buy_price + tick_size, price_decimals)

        return sell_price

    def get_fee_rate(self) -> float:
        """获取交易对的手续费率
        
        Returns:
            float: 手续费率，例如 0.001 表示 0.1%
        """
        return 0.001  # 默认 0.1% 手续费

    def calculate_buy_target_price(self, current_price, offset_percent, tick_size, price_decimals):
        """
        计算买单目标价格
        
        Args:
            current_price: 当前市场价格
            offset_percent: 偏移百分比（通常为负数，如 -0.1）
            tick_size: 价格步长
            price_decimals: 价格小数位数
        
        Returns:
            float: 对齐后的买单目标价格
        """
        offset = offset_percent / 100.0
        target_price = current_price * (1 + offset)
        
        # 按 tick_size 对齐（向下取整）
        if tick_size and tick_size > 0:
            target_price = math.floor(target_price / tick_size) * tick_size
        
        # 按小数位数对齐
        target_price = round(target_price, price_decimals)
        
        return target_price

    @staticmethod
    def calculate_atr(ohlcv: List, period: int = 14) -> float:
        """
        计算 ATR (Average True Range)
        
        Args:
            ohlcv: K线数据列表，每条 [timestamp, open, high, low, close, volume]
            period: ATR 周期（默认14）
        
        Returns:
            float: ATR 值
        """
        if len(ohlcv) < period + 1:
            raise ValueError(f"K线数据不足，需要至少 {period + 1} 条")
        
        true_ranges = []
        for i in range(1, len(ohlcv)):
            high = ohlcv[i][2]
            low = ohlcv[i][3]
            prev_close = ohlcv[i-1][4]
            
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            true_ranges.append(tr)
        
        return sum(true_ranges[-period:]) / period

    @staticmethod
    def get_atr_recommendation(atr: float, current_price: float) -> Dict:
        """
        根据 ATR 计算推荐参数
        
        Args:
            atr: ATR 绝对值
            current_price: 当前价格
        
        Returns:
            dict: 推荐参数
        """
        atr_percent = (atr / current_price) * 100
        
        # 推荐参数计算
        # offset: ATR% 的 15%，作为买单偏移（负值）
        # sell_offset: ATR% 的 40%，最低 0.2%（覆盖手续费）
        suggested_offset = -round(atr_percent * 0.15, 3)
        suggested_sell_offset = max(0.2, round(atr_percent * 0.4, 3))
        
        return {
            'atr': round(atr, 8),
            'atr_percent': round(atr_percent, 4),
            'current_price': current_price,
            'suggested_offset': suggested_offset,
            'suggested_sell_offset': suggested_sell_offset
        }