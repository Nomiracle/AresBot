"""
交易上下文 - 聚合根
"""

from threading import RLock
from typing import Optional, TYPE_CHECKING
from .trading_config import TradingConfig
from .market_state import MarketState
from .runtime_state import RuntimeState
from .order_manager import OrderManager
from .order_state import OrderSide

if TYPE_CHECKING:
    from ..infrastructure.exchange_adapter import ExchangeAdapter


class TradingContext:
    """交易上下文 - 聚合根"""
    
    def __init__(
        self,
        username: str,
        user_id: str,
        config: TradingConfig,
        exchange: 'ExchangeAdapter'
    ):
        """
        初始化交易上下文
        
        Args:
            username: 用户名
            user_id: 用户ID
            config: 交易配置
            exchange: 交易所适配器
        """
        self.username = username
        self.user_id = user_id
        self.config = config
        self.exchange = exchange
        
        self.market = MarketState()
        self.runtime = RuntimeState()
        self.order_manager = OrderManager()
        
        self._lock = RLock()
    
    def update_market_price(self, price: float) -> None:
        """
        更新市场价格
        
        Args:
            price: 新价格
        """
        with self._lock:
            self.market.update_price(price)
    
    def get_current_price(self) -> Optional[float]:
        """
        获取当前价格
        
        Returns:
            当前价格或None
        """
        with self._lock:
            return self.market.current_price
    
    def can_place_order(self) -> tuple[bool, str]:
        """
        检查是否可以下单
        
        Returns:
            (是否可以, 原因)
        """
        with self._lock:
            if not self.runtime.running:
                return False, "交易未启动"
            
            # 注意：不检查 is_placing_order，因为该标志在外层（_place_missing_orders）设置
            # 用于防止并发补单，而不是阻止单个下单命令的执行
            
            if self.runtime.is_handling_buy_filled:
                return False, "正在处理买单成交"
            
            if self.market.current_price is None:
                return False, "价格未就绪"
            
            if self.market.is_stale():
                return False, "价格已过期"
            
            return True, "可以下单"
    
    def needs_more_orders(self) -> bool:
        """
        检查是否需要补单
        
        Returns:
            是否需要补单
        """
        with self._lock:
            # 计算当前总持仓数量
            buy_orders = self.order_manager.get_active_orders(OrderSide.BUY)
            sell_orders = self.order_manager.get_active_orders(OrderSide.SELL)
            
            total_qty = sum(o.info.quantity for o in buy_orders)
            total_qty += sum(o.info.quantity for o in sell_orders)
            
            target_qty = self.config.order_grid * self.config.quantity
            
            return total_qty < target_qty
    
    def start_trading(self) -> None:
        """启动交易"""
        with self._lock:
            self.runtime.running = True
            self.runtime.clear_error()
            self.runtime.clear_warning()
    
    def stop_trading(self) -> None:
        """停止交易"""
        with self._lock:
            self.runtime.running = False
    
    def get_log_prefix(self) -> str:
        """
        获取日志前缀
        
        Returns:
            日志前缀
        """
        exchange_prefix = self.exchange._get_log_prefix() if hasattr(self.exchange, '_get_log_prefix') else ""
        return f"{exchange_prefix}[{self.username}][v2]"
