"""
Polymarket 交易所适配器
基于 py-clob-client SDK
"""
from datetime import datetime
from typing import Dict, List, Optional, Callable
import math
import time
import threading
from .base import BaseExchange

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import OrderArgs, MarketOrderArgs, OrderType, OpenOrderParams, BookParams
    from py_clob_client.order_builder.constants import BUY, SELL
except ImportError:
    print("⚠️ 请安装 py-clob-client: pip install py-clob-client")
    ClobClient = None
    OrderArgs = None
    MarketOrderArgs = None
    OrderType = None
    OpenOrderParams = None
    BookParams = None
    BUY = None
    SELL = None


class NativePolymarketSpot(BaseExchange):
    """Polymarket 交易所适配器"""
    
    def __init__(self, api_key: str, api_secret: str, symbol: str, testnet: bool = True):
        """初始化 Polymarket 客户端
        
        Args:
            api_key: 钱包地址
            api_secret: 私钥 (Private Key, 0x开头的十六进制字符串)
            symbol: 交易对/市场ID (token_id)
            testnet: 是否使用测试网 (Polymarket主网为Polygon链)
        
        注意:
        - api_key: 钱包地址 (0x开头)
        - api_secret: 钱包私钥 (0x开头的十六进制字符串)
        - symbol: Polymarket的token_id (可从市场API获取)
        """
        if ClobClient is None:
            raise ImportError("请先安装 py-clob-client: pip install py-clob-client")
        
        self.api_key = api_key
        self.api_secret = api_secret
        self.symbol = symbol
        self.testnet = testnet
        
        # Polymarket 配置
        self.host = "https://clob.polymarket.com"
        self.chain_id = 137  # Polygon 主网
        
        # 监听器状态
        self._price_monitor_active = False
        self._order_monitor_active = False
        self._price_poll_thread = None
        self._order_poll_thread = None
        self._on_price_callback = None
        self._on_order_callback = None
        
        try:
            # 使用标准EOA模式
            self.client = ClobClient(
                self.host,
                key=api_secret,  # 使用私钥
                chain_id=self.chain_id,
                signature_type=0  # 标准EOA签名
            )
            
            # 设置API凭证
            self.client.set_api_creds(self.client.create_or_derive_api_creds())
            
            # 缓存市场信息
            self._markets_cache = None
            self._trading_rules_cache = None
            
            print(f"[{datetime.now().isoformat()}] ✅ [Polymarket] 客户端初始化成功")
            
        except Exception as e:
            raise ValueError(f"Polymarket 初始化失败: {str(e)}")
        
        print(f"[{datetime.now().isoformat()}] ✅ [Polymarket] 适配器初始化成功")

    def ping(self) -> bool:
        """测试连接"""
        try:
            ok = self.client.get_ok()
            return ok.get('status') == 'ok' if isinstance(ok, dict) else True
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Polymarket] ping 失败: {e}")
            return False
    
    def get_symbol_ticker(self) -> Dict:
        """获取交易对当前价格"""
        try:
            # 获取中间价
            midpoint = self.client.get_midpoint(self.symbol)
            
            # 获取买卖价
            buy_price = self.client.get_price(self.symbol, side="BUY")
            sell_price = self.client.get_price(self.symbol, side="SELL")
            
            return {
                'symbol': self.symbol,
                'price': midpoint,
                'bidPrice': buy_price,
                'askPrice': sell_price,
                'lastPrice': midpoint
            }
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Polymarket] 获取价格失败: {e}")
            raise
    
    def get_order(self, order_id: str) -> Dict:
        """查询订单状态"""
        try:
            # Polymarket使用get_orders查询订单
            orders = self.client.get_orders(OpenOrderParams())
            
            for order in orders:
                if order.get('id') == order_id:
                    return self._normalize_order(order)
            
            # 如果在开放订单中找不到,可能已成交或取消
            # 尝试从交易历史查询
            trades = self.client.get_trades()
            for trade in trades:
                if trade.get('order_id') == order_id:
                    return {
                        'orderId': order_id,
                        'status': 'FILLED',
                        'side': trade.get('side', '').upper(),
                        'price': float(trade.get('price', 0)),
                        'executedQty': float(trade.get('size', 0)),
                        'origQty': float(trade.get('size', 0))
                    }
            
            # 订单不存在或已取消
            return {
                'orderId': order_id,
                'status': 'CANCELED',
                'side': 'UNKNOWN',
                'price': 0,
                'executedQty': 0,
                'origQty': 0
            }
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Polymarket] 查询订单失败: {e}")
            raise
    
    def _normalize_order(self, order: Dict) -> Dict:
        """标准化订单格式"""
        status_map = {
            'LIVE': 'NEW',
            'MATCHED': 'FILLED',
            'CANCELLED': 'CANCELED',
            'EXPIRED': 'EXPIRED'
        }
        
        return {
            'orderId': order.get('id'),
            'status': status_map.get(order.get('status', '').upper(), 'UNKNOWN'),
            'side': order.get('side', '').upper(),
            'price': float(order.get('price', 0)),
            'executedQty': float(order.get('size_matched', 0)),
            'origQty': float(order.get('original_size', 0)),
            'symbol': order.get('asset_id', self.symbol)
        }
    
    def order_limit_buy(self, quantity: float, price: str, **kwargs) -> Dict:
        """限价买单"""
        try:
            order = OrderArgs(
                token_id=self.symbol,
                price=float(price),
                size=quantity,
                side=BUY
            )
            
            signed = self.client.create_order(order)
            resp = self.client.post_order(signed, OrderType.GTC)
            
            return {
                'orderId': resp.get('orderID'),
                'status': 'NEW',
                'side': 'BUY',
                'price': float(price),
                'origQty': quantity,
                'executedQty': 0
            }
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Polymarket] 限价买单失败: {e}")
            raise
    
    def order_limit_sell(self, quantity: float, price: str, **kwargs) -> Dict:
        """限价卖单"""
        try:
            order = OrderArgs(
                token_id=self.symbol,
                price=float(price),
                size=quantity,
                side=SELL
            )
            
            signed = self.client.create_order(order)
            resp = self.client.post_order(signed, OrderType.GTC)
            
            return {
                'orderId': resp.get('orderID'),
                'status': 'NEW',
                'side': 'SELL',
                'price': float(price),
                'origQty': quantity,
                'executedQty': 0
            }
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Polymarket] 限价卖单失败: {e}")
            raise
    
    def cancel_order(self, order_id: str) -> Dict:
        """取消订单"""
        try:
            resp = self.client.cancel(order_id)
            return {
                'orderId': order_id,
                'status': 'CANCELED'
            }
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Polymarket] 取消订单失败: {e}")
            raise
    
    def cancel_replace_order(self, side: str, order_type: str, 
                            quantity: float, price: str, cancel_order_id: str, **kwargs) -> Dict:
        """取消并替换订单"""
        try:
            # Polymarket不支持原子性的cancel_replace,需要分两步
            # 1. 取消旧订单
            self.cancel_order(cancel_order_id)
            
            # 2. 创建新订单
            time.sleep(0.1)  # 短暂延迟确保取消完成
            
            if side.upper() == 'BUY':
                return self.order_limit_buy(quantity, price, **kwargs)
            else:
                return self.order_limit_sell(quantity, price, **kwargs)
                
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Polymarket] 改价失败: {e}")
            raise
    
    def get_trading_rules(self) -> Dict:
        """获取交易规则"""
        if self._trading_rules_cache:
            return self._trading_rules_cache
        
        try:
            # Polymarket的价格范围是0-1 (概率)
            # 最小价格单位通常是0.001 (0.1%)
            rules = {
                'tick_size': 0.001,      # 价格步长 0.1%
                'price_decimals': 3,     # 价格小数位数
                'step_size': 0.01,       # 数量步长
                'qty_decimals': 2        # 数量小数位数
            }
            
            self._trading_rules_cache = rules
            return rules
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Polymarket] 获取交易规则失败: {e}")
            # 返回默认值
            return {
                'tick_size': 0.001,
                'price_decimals': 3,
                'step_size': 0.01,
                'qty_decimals': 2
            }
    
    def start_ws(self, on_price_update: Callable[[float], None], 
                 on_order_update: Callable[[Dict], None]) -> bool:
        """启动价格和订单监听 (HTTP轮询模式)"""
        self._on_price_callback = on_price_update
        self._on_order_callback = on_order_update
        
        # 启动价格监听线程
        if not self._price_monitor_active:
            self._price_monitor_active = True
            self._price_poll_thread = threading.Thread(
                target=self._price_poll_loop,
                daemon=True
            )
            self._price_poll_thread.start()
            print(f"[{datetime.now().isoformat()}] ✅ [Polymarket] 价格监听已启动 (HTTP轮询)")
        
        # 启动订单监听线程
        if not self._order_monitor_active:
            self._order_monitor_active = True
            self._order_poll_thread = threading.Thread(
                target=self._order_poll_loop,
                daemon=True
            )
            self._order_poll_thread.start()
            print(f"[{datetime.now().isoformat()}] ✅ [Polymarket] 订单监听已启动 (HTTP轮询)")
        
        return True
    
    def stop_ws(self) -> None:
        """停止监听"""
        self._price_monitor_active = False
        self._order_monitor_active = False
        
        if self._price_poll_thread:
            self._price_poll_thread.join(timeout=2)
        if self._order_poll_thread:
            self._order_poll_thread.join(timeout=2)
        
        print(f"[{datetime.now().isoformat()}] 🔌 [Polymarket] 监听已停止")
    
    def _price_poll_loop(self):
        """价格轮询循环"""
        last_price = None
        
        while self._price_monitor_active:
            try:
                ticker = self.get_symbol_ticker()
                current_price = float(ticker.get('price', 0))
                
                if current_price > 0 and current_price != last_price:
                    if self._on_price_callback:
                        self._on_price_callback(current_price)
                    last_price = current_price
                
                time.sleep(2)  # 每2秒轮询一次
                
            except Exception as e:
                print(f"[{datetime.now().isoformat()}] ❌ [Polymarket] 价格轮询错误: {e}")
                time.sleep(5)
    
    def _order_poll_loop(self):
        """订单轮询循环"""
        known_orders = set()
        
        while self._order_monitor_active:
            try:
                orders = self.client.get_orders(OpenOrderParams())
                
                for order in orders:
                    order_id = order.get('id')
                    status = order.get('status', '').upper()
                    
                    # 检测订单状态变化
                    if order_id not in known_orders:
                        known_orders.add(order_id)
                    
                    # 如果订单已成交或取消,触发回调
                    if status in ['MATCHED', 'CANCELLED', 'EXPIRED']:
                        if self._on_order_callback:
                            normalized = self._normalize_order(order)
                            event = {
                                'event_type': 'order_filled' if status == 'MATCHED' else 'order_update',
                                'order_id': order_id,
                                'symbol': self.symbol,
                                'side': normalized['side'],
                                'status': normalized['status'],
                                'price': normalized['price'],
                                'quantity': normalized['origQty']
                            }
                            self._on_order_callback(event)
                        
                        known_orders.discard(order_id)
                
                time.sleep(3)  # 每3秒轮询一次
                
            except Exception as e:
                print(f"[{datetime.now().isoformat()}] ❌ [Polymarket] 订单轮询错误: {e}")
                time.sleep(5)
    
    def check_pending_orders(self, pending_orders: List[Dict]):
        """检查待处理订单状态 (HTTP轮询模式)"""
        if not pending_orders:
            return
        
        try:
            # 获取所有开放订单
            open_orders = self.client.get_orders(OpenOrderParams())
            open_order_ids = {order.get('id') for order in open_orders}
            
            # 检查每个待处理订单
            for pending in pending_orders:
                order_id = pending.get('order_id')
                if not order_id:
                    continue
                
                # 如果订单不在开放列表中,可能已成交或取消
                if order_id not in open_order_ids:
                    order_info = self.get_order(order_id)
                    
                    if order_info['status'] == 'FILLED' and self._on_order_callback:
                        event = {
                            'event_type': 'order_filled',
                            'order_id': order_id,
                            'symbol': self.symbol,
                            'side': order_info['side'],
                            'status': 'FILLED',
                            'price': order_info['price'],
                            'quantity': order_info['executedQty']
                        }
                        self._on_order_callback(event)
                        
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Polymarket] 检查订单失败: {e}")
    
    def get_fee_rate(self) -> float:
        """获取手续费率
        
        Polymarket的手续费结构:
        - Maker: -0.02% (返佣)
        - Taker: 0.1%
        
        Returns:
            float: 手续费率 (使用Taker费率作为保守估计)
        """
        return 0.001  # 0.1% Taker费率
