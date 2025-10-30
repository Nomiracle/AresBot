"""
Backpack (BPX) 交易所适配器
基于 bpx-py SDK
"""
from datetime import datetime
from typing import Dict, List, Optional, Callable
import math
from .base import BaseExchange

try:
    from bpx.account import Account
    from bpx.public import Public
except ImportError:
    print("⚠️ 请安装 bpx-py: pip install bpx-py")
    Account = None
    Public = None


class BackpackAdapter(BaseExchange):
    """Backpack 交易所适配器"""
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        """初始化 Backpack 客户端
        
        Args:
            api_key: API 公钥
            api_secret: API 私钥
            testnet: 是否使用测试网（Backpack 暂不支持测试网，此参数保留）
        """
        if Account is None or Public is None:
            raise ImportError("请先安装 bpx-py: pip install bpx-py")
        
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        
        # 初始化账户客户端（私有 API）
        self.account = Account(
            public_key=api_key,
            secret_key=api_secret,
            debug=False,
            window=5000
        )
        
        # 初始化公共客户端（公共 API）
        self.public = Public()
        
        # 缓存市场信息
        self._markets_cache = None
        
        print(f"[{datetime.now().isoformat()}] ✅ [Backpack] 适配器初始化成功")
    
    def ping(self) -> bool:
        """测试连接"""
        try:
            result = self.public.get_ping()
            return result is not None
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Backpack] Ping 失败: {e}")
            return False
    
    def _get_markets(self) -> List[Dict]:
        """获取所有市场信息（带缓存）"""
        if self._markets_cache is None:
            try:
                self._markets_cache = self.public.get_markets()
            except Exception as e:
                print(f"[{datetime.now().isoformat()}] ❌ [Backpack] 获取市场信息失败: {e}")
                return []
        return self._markets_cache or []
    
    def _convert_symbol(self, symbol: str) -> str:
        """转换交易对格式
        
        Binance 格式: BTCUSDT
        Backpack 格式: BTC_USDT
        """
        # 如果已经是 Backpack 格式，直接返回
        if '_' in symbol:
            return symbol
        
        # 尝试常见的转换
        # BTCUSDT -> BTC_USDT
        # ETHUSDC -> ETH_USDC
        # SOLUSDC -> SOL_USDC
        common_quotes = ['USDT', 'USDC', 'USD', 'BTC', 'ETH']
        for quote in common_quotes:
            if symbol.endswith(quote):
                base = symbol[:-len(quote)]
                return f"{base}_{quote}"
        
        # 如果无法识别，返回原值
        print(f"[{datetime.now().isoformat()}] ⚠️ [Backpack] 无法转换交易对格式: {symbol}")
        return symbol
    
    def get_symbol_info(self, symbol: str) -> Dict:
        """获取交易对信息"""
        try:
            bpx_symbol = self._convert_symbol(symbol)
            markets = self._get_markets()
            
            for market in markets:
                if market.get('symbol') == bpx_symbol:
                    return market
            
            print(f"[{datetime.now().isoformat()}] ⚠️ [Backpack] 交易对 {bpx_symbol} 不存在")
            return None
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Backpack] 获取交易对信息失败 ({symbol}): {e}")
            return None
    
    def get_symbol_ticker(self, symbol: str) -> Dict:
        """获取交易对当前价格"""
        try:
            bpx_symbol = self._convert_symbol(symbol)
            ticker = self.public.get_ticker(bpx_symbol)
            
            if ticker and 'lastPrice' in ticker:
                return {
                    'symbol': bpx_symbol,
                    'price': ticker['lastPrice']
                }
            return None
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Backpack] 获取价格失败 ({symbol}): {e}")
            return None
    
    def get_open_orders(self, symbol: str) -> List[Dict]:
        """获取未完成订单"""
        try:
            bpx_symbol = self._convert_symbol(symbol)
            orders = self.account.get_open_orders(bpx_symbol)
            
            # 转换为统一格式
            result = []
            for order in orders or []:
                result.append({
                    'orderId': order.get('id'),
                    'symbol': order.get('symbol'),
                    'side': 'BUY' if order.get('side') == 'Bid' else 'SELL',
                    'price': order.get('price'),
                    'origQty': order.get('quantity'),
                    'executedQty': order.get('executedQuantity', '0'),
                    'status': self._convert_order_status(order.get('status')),
                    'type': order.get('orderType'),
                    'timeInForce': order.get('timeInForce')
                })
            return result
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Backpack] 获取未完成订单失败 ({symbol}): {e}")
            return []
    
    def get_order(self, symbol: str, order_id: str) -> Dict:
        """查询订单状态"""
        try:
            bpx_symbol = self._convert_symbol(symbol)
            order = self.account.get_open_order(bpx_symbol, order_id)
            
            if order:
                return {
                    'orderId': order.get('id'),
                    'symbol': order.get('symbol'),
                    'side': 'BUY' if order.get('side') == 'Bid' else 'SELL',
                    'price': order.get('price'),
                    'origQty': order.get('quantity'),
                    'executedQty': order.get('executedQuantity', '0'),
                    'status': self._convert_order_status(order.get('status')),
                    'type': order.get('orderType')
                }
            return None
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Backpack] 查询订单失败 ({symbol}, {order_id}): {e}")
            return None
    
    def order_limit_buy(self, symbol: str, quantity: float, price: str, **kwargs) -> Dict:
        """限价买单"""
        try:
            bpx_symbol = self._convert_symbol(symbol)
            time_in_force = kwargs.get('timeInForce', 'GTC')
            
            result = self.account.execute_order(
                symbol=bpx_symbol,
                side='Bid',  # Backpack 使用 Bid/Ask
                order_type='Limit',
                quantity=str(quantity),
                price=price,
                time_in_force=time_in_force
            )
            
            if result:
                return {
                    'orderId': result.get('id'),
                    'symbol': bpx_symbol,
                    'side': 'BUY',
                    'price': price,
                    'origQty': str(quantity),
                    'status': 'NEW'
                }
            return None
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Backpack] 限价买单失败 ({symbol}): {e}")
            raise
    
    def order_limit_sell(self, symbol: str, quantity: float, price: str, **kwargs) -> Dict:
        """限价卖单"""
        try:
            bpx_symbol = self._convert_symbol(symbol)
            time_in_force = kwargs.get('timeInForce', 'GTC')
            
            result = self.account.execute_order(
                symbol=bpx_symbol,
                side='Ask',  # Backpack 使用 Bid/Ask
                order_type='Limit',
                quantity=str(quantity),
                price=price,
                time_in_force=time_in_force
            )
            
            if result:
                return {
                    'orderId': result.get('id'),
                    'symbol': bpx_symbol,
                    'side': 'SELL',
                    'price': price,
                    'origQty': str(quantity),
                    'status': 'NEW'
                }
            return None
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Backpack] 限价卖单失败 ({symbol}): {e}")
            raise
    
    def cancel_order(self, symbol: str, order_id: str) -> Dict:
        """取消订单"""
        try:
            bpx_symbol = self._convert_symbol(symbol)
            result = self.account.cancel_order(bpx_symbol, order_id)
            return result or {'success': True}
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Backpack] 取消订单失败 ({symbol}, {order_id}): {e}")
            raise
    
    def cancel_replace_order(self, symbol: str, side: str, order_type: str, 
                            quantity: float, price: str, cancel_order_id: str, **kwargs) -> Dict:
        """取消并替换订单（改价）
        
        Backpack 不支持原子性的 cancel_replace，需要分两步：
        1. 取消旧订单
        2. 下新订单
        """
        try:
            # 1. 取消旧订单
            self.cancel_order(symbol, cancel_order_id)
            
            # 2. 下新订单
            if side == 'BUY':
                new_order = self.order_limit_buy(symbol, quantity, price, **kwargs)
            else:
                new_order = self.order_limit_sell(symbol, quantity, price, **kwargs)
            
            # 返回格式兼容 Binance
            return {
                'cancelResult': 'SUCCESS',
                'newOrderResponse': new_order
            }
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Backpack] 改价失败 ({symbol}): {e}")
            raise
    
    def start_websocket(self, symbol: str, on_ticker: Callable, on_user: Optional[Callable] = None) -> Dict:
        """启动 WebSocket 连接
        
        注意：Backpack 的 WebSocket 实现可能与 Binance 不同
        这里返回一个标记，表示不支持 WebSocket，使用 REST 轮询
        """
        print(f"[{datetime.now().isoformat()}] ℹ️ [Backpack] WebSocket 暂不支持，将使用 REST 轮询")
        
        return {
            'manager': None,
            'ticker_enabled': False,
            'user_enabled': False
        }
    
    def stop_websocket(self, ws_manager) -> None:
        """停止 WebSocket 连接"""
        # Backpack 暂不支持 WebSocket
        pass
    
    def parse_ticker_message(self, msg: Dict) -> Optional[float]:
        """解析行情消息"""
        try:
            if 'lastPrice' in msg:
                return float(msg['lastPrice'])
            if 'c' in msg:  # 兼容 Binance 格式
                return float(msg['c'])
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Backpack] 解析行情消息失败: {e}")
        return None
    
    def parse_user_message(self, msg: Dict) -> Optional[Dict]:
        """解析用户数据消息"""
        # Backpack 使用 REST 轮询，不需要解析 WebSocket 消息
        return None
    
    def get_price_precision(self, symbol_info: Dict) -> tuple:
        """提取价格精度"""
        if not symbol_info:
            print(f"[{datetime.now().isoformat()}] ⚠️ [Backpack] symbol_info 无效，使用默认价格精度")
            return 0.01, 2
        
        try:
            # Backpack 使用 filters 字段
            filters = symbol_info.get('filters', {})
            price_filter = filters.get('price', {})
            
            tick_size = float(price_filter.get('tickSize', 0.01))
            if tick_size > 0:
                price_decimals = int(abs(math.log10(tick_size)))
                return tick_size, price_decimals
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ⚠️ [Backpack] 解析价格精度失败: {e}")
        
        return 0.01, 2
    
    def get_quantity_precision(self, symbol_info: Dict) -> tuple:
        """提取数量精度"""
        if not symbol_info:
            print(f"[{datetime.now().isoformat()}] ⚠️ [Backpack] symbol_info 无效，使用默认数量精度")
            return 0.000001, 6
        
        try:
            # Backpack 使用 filters 字段
            filters = symbol_info.get('filters', {})
            quantity_filter = filters.get('quantity', {})
            
            step_size = float(quantity_filter.get('stepSize', 0.000001))
            if step_size > 0:
                qty_decimals = int(abs(math.log10(step_size)))
                return step_size, qty_decimals
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ⚠️ [Backpack] 解析数量精度失败: {e}")
        
        return 0.000001, 6
    
    def _convert_order_status(self, bpx_status: str) -> str:
        """转换订单状态为统一格式"""
        status_map = {
            'Open': 'NEW',
            'Filled': 'FILLED',
            'PartiallyFilled': 'PARTIALLY_FILLED',
            'Cancelled': 'CANCELED',
            'Expired': 'EXPIRED'
        }
        return status_map.get(bpx_status, bpx_status)
    
    def get_account(self):
        """获取原始账户客户端（用于扩展功能）"""
        return self.account
    
    def get_public(self):
        """获取原始公共客户端（用于扩展功能）"""
        return self.public
