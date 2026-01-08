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
    
    @classmethod
    @abstractmethod
    def get_exchange_info(cls) -> Dict:
        """获取交易所信息（类方法）
        
        Returns:
            {
                'id': str,          # 交易所ID，格式: 交易所-市场-方向（如 'binance-spot', 'binance-futures-short'）
                'name': str,        # 中文名称，包含交易所、市场、方向信息（如 '币安-现货', '币安-合约-做空'）
                'description': str  # 交易所描述信息
            }
        """
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
    
    def calculate_price_diff_stats(self, current_price: float, target_price: float, 
                                   min_diff: Optional[float], max_diff: Optional[float], 
                                   avg_diff: Optional[float]) -> List[float]:
        """计算价格差值统计 (做多逻辑)
        
        默认实现适用于做多交易所:
        - 差值 = (现价 - 目标价) / 现价 * 100
        - 买单: 目标价 < 现价, diff > 0, 越小越接近成交
        - 卖单: 目标价 > 现价, diff < 0, 绝对值越小越接近成交
        
        Args:
            current_price: 当前市场价格
            target_price: 目标挂单价格
            min_diff: 当前最小差值 (可为 None)
            max_diff: 当前最大差值 (可为 None)
            avg_diff: 当前平均差值 (可为 None)
        
        Returns:
            [新最小差值, 新平均差值, 新最大差值]
        """
        if not target_price or current_price <= 0:
            return [min_diff, avg_diff, max_diff]
        
        # 计算差值百分比: (现价 - 目标价) / 现价 * 100
        price_diff_percent = ((current_price - target_price) / current_price) * 100
        
        # 更新最小差值(绝对值最小)
        if min_diff is None:
            new_min = price_diff_percent
        else:
            new_min = price_diff_percent if abs(price_diff_percent) < abs(min_diff) else min_diff
        
        # 更新最大差值(绝对值最大)
        if max_diff is None:
            new_max = price_diff_percent
        else:
            new_max = price_diff_percent if abs(price_diff_percent) > abs(max_diff) else max_diff
        
        # 更新平均差值(移动平均)
        if avg_diff is None:
            new_avg = price_diff_percent
        else:
            new_avg = (avg_diff + price_diff_percent) / 2
        
        return [new_min, new_avg, new_max]
    
    def get_notification_info(self) -> str:
        """获取通知消息的附加信息
        
        默认实现返回类名,子类可以重写此方法提供自定义信息
        例如: UpDown15m 可以返回当前市场的 slug
        
        Returns:
            str: 附加信息字符串
        """
        return self.__class__.__name__
