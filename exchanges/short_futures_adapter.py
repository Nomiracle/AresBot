"""
Short Futures Adapter - 做空适配器

继承 CcxtFuturesAdapter，重写必要方法实现做空功能：
- order_limit_buy() → 实际执行卖出开仓（做空）
- order_limit_sell() → 实际执行买入平仓

使用方式与 CcxtFuturesAdapter 完全相同，只是交易方向相反。
"""
import math
from datetime import datetime
from typing import Dict, List, Callable
from exchanges.ccxt_futures_adapter import CcxtBinanceFutures


class CcxtBinanceFuturesShort(CcxtBinanceFutures):
    """做空适配器（继承 CcxtFuturesAdapter）
    
    重写买卖方法，反转交易方向：
    - trading.py 调用 buy → 实际执行 sell（做空开仓）
    - trading.py 调用 sell → 实际执行 buy（做空平仓）
    """
    
    def _get_log_prefix(self) -> str:
        """重写日志前缀（标识为做空模式）"""
        api_key_short = self.api_key[:6] if self.api_key else "NOKEY"
        return f"[{datetime.now().isoformat()}] [SHORT-{api_key_short}-{self.symbol}]"
    
    # ====================== 核心：反转买卖方向 ======================
    
    def order_limit_buy(self, quantity: float, price: str, **kwargs) -> Dict:
        """限价买单 → 实际执行卖出开仓（做空）"""
        print(f"{self._get_log_prefix()} 📤 做空开仓: 数量={quantity}, 价格={price}")
        # 调用父类的 sell 方法
        result = super().order_limit_sell(quantity=quantity, price=price, **kwargs)
        print(f"{self._get_log_prefix()} ✅ 做空开仓成功: 订单ID={result.get('orderId')}")
        return result
    
    def order_limit_sell(self, quantity: float, price: str, **kwargs) -> Dict:
        """限价卖单 → 实际执行买入平仓"""
        print(f"{self._get_log_prefix()} 📥 做空平仓: 数量={quantity}, 价格={price}")
        # 调用父类的 buy 方法
        result = super().order_limit_buy(quantity=quantity, price=price, **kwargs)
        print(f"{self._get_log_prefix()} ✅ 做空平仓成功: 订单ID={result.get('orderId')}")
        return result
    
    # ====================== 价格计算反转 ======================
    
    def calculate_sell_price(self, buy_price, sell_offset_percent, tick_size, price_decimals, current_price=None):
        """计算平仓价格（做空时：平仓价 < 开仓价）"""
        sell_offset = sell_offset_percent / 100.0
        # 做空平仓：目标价 = 开仓价 * (1 - offset)
        raw_close_price = (current_price or buy_price) * (1 - sell_offset)
        
        # 最高保护价（开仓价 - 2倍手续费，确保盈利）
        max_price = buy_price * (1 - 2 * self.get_fee_rate())
        max_price = math.floor(max_price / tick_size) * tick_size if tick_size else max_price
        max_price = round(max_price, price_decimals)
        
        # 最终平仓价（取较小值，确保盈利）
        close_price = min(raw_close_price, max_price)
        close_price = math.ceil(close_price / tick_size) * tick_size if tick_size else close_price
        return round(close_price, price_decimals)
    
    def calculate_buy_target_price(self, current_price, offset_percent, tick_size, price_decimals):
        """计算开仓目标价格（做空时：开仓价 > 当前价）"""
        offset = offset_percent / 100.0
        # 做空开仓：目标价 = 当前价 * (1 - offset)
        # offset 通常为负数如 -0.1，所以 1 - (-0.001) = 1.001，卖出价高于当前价
        target_price = current_price * (1 - offset)
        
        # 按 tick_size 对齐（做空向上取整，确保能成交）
        if tick_size and tick_size > 0:
            target_price = math.ceil(target_price / tick_size) * tick_size
        
        target_price = round(target_price, price_decimals)
        return target_price
