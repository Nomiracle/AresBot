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
            api_key: Polymarket Proxy Wallet 地址 (网站右上角显示的地址)
            api_secret: 私钥 (Private Key, 0x开头的十六进制字符串)
            symbol: 交易对/市场ID (token_id)
            testnet: 是否使用测试网 (Polymarket主网为Polygon链)
        
        注意:
        - api_key: Polymarket 网站显示的 Proxy Wallet 地址 (已完成授权)
        - api_secret: 你的 MetaMask 私钥 (0x开头的十六进制字符串)
        - symbol: Polymarket的token_id (可从市场API获取)
        - 使用 signature_type=2 (Proxy Wallet 模式)
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
        try:
            # 初始化Polymarket客户端
            host = "https://clob.polymarket.com"
            chain_id = 137  # Polygon主网
            
            # ClobClient 需要私钥来进行签名和认证
            # key 参数应该是私钥(不带 0x 前缀)
            private_key = api_secret
            if private_key.startswith('0x'):
                private_key = private_key[2:]  # 移除 0x 前缀
            
            self.client = ClobClient(
                host=host,
                key=private_key,
                chain_id=chain_id,
                signature_type=2,  # Proxy Wallet 模式 (使用 Polymarket 网站的 Proxy Wallet)
                funder=api_key  # Polymarket 网站显示的 Proxy Wallet 地址
            )
            
            # 设置 API 凭证用于 Level 2 认证
            try:
                api_creds = self.client.create_or_derive_api_creds()
                self.client.set_api_creds(api_creds)
                print(f"[{datetime.now().isoformat()}] 🔐 [Polymarket] API 凭证已设置")
            except Exception as cred_error:
                print(f"[{datetime.now().isoformat()}] ⚠️ [Polymarket] API 凭证设置失败: {cred_error}")
                # 继续执行,某些操作可能不需要 Level 2 认证
            print(f"[{datetime.now().isoformat()}] ✅ [Polymarket] 客户端初始化成功")
            print(f"[{datetime.now().isoformat()}] 📍 [Polymarket] 钱包地址: {api_key}")
            
            # 检查余额和授权
            self._check_balance_and_allowance()
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Polymarket] 初始化失败: {e}")
            import traceback
            traceback.print_exc()
            raise
        
        print(f"[{datetime.now().isoformat()}] ✅ [Polymarket] 适配器初始化成功")

    def _check_balance_and_allowance(self):
        """检查账户余额和授权状态"""
        try:
            # 获取余额信息
            balance_allowance = self.client.get_balance_allowance()
            
            balance = float(balance_allowance.get('balance', 0))
            allowance = float(balance_allowance.get('allowance', 0))
            
            print(f"[{datetime.now().isoformat()}] 💰 [Polymarket] 余额: ${balance:.2f} USDC")
            print(f"[{datetime.now().isoformat()}] 🔓 [Polymarket] 授权额度: ${allowance:.2f} USDC")
            
            if balance < 1:
                print(f"[{datetime.now().isoformat()}] ⚠️ [Polymarket] 余额不足 $1 USDC")
            
            if allowance < 1:
                print(f"[{datetime.now().isoformat()}] ⚠️ [Polymarket] 未授权或授权额度不足")
                print(f"[{datetime.now().isoformat()}] 💡 [Polymarket] 请访问 https://polymarket.com 完成 'Approve Tokens' 步骤")
                
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ⚠️ [Polymarket] 无法检查余额/授权: {e}")

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
            # 获取中间价 - 返回格式: {'mid': '0.51'}
            midpoint_data = self.client.get_midpoint(self.symbol)
            midpoint = float(midpoint_data.get('mid', 0))
            
            # 获取买卖价 - 返回格式: {'price': '0.5'}
            buy_price_data = self.client.get_price(self.symbol, side="BUY")
            buy_price = float(buy_price_data.get('price', 0))
            
            sell_price_data = self.client.get_price(self.symbol, side="SELL")
            sell_price = float(sell_price_data.get('price', 0))
            
            result = {
                'symbol': self.symbol,
                'price': midpoint,
                'bidPrice': buy_price,
                'askPrice': sell_price,
                'lastPrice': midpoint
            }
            
            print(f"[{datetime.now().isoformat()}] 📊 [Polymarket] 价格: mid={midpoint}, bid={buy_price}, ask={sell_price}")
            return result
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Polymarket] 获取价格失败: {e}")
            import traceback
            traceback.print_exc()
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
    
    def get_open_orders(self) -> list:
        """获取所有未完成订单"""
        try:
            print(f"[{datetime.now().isoformat()}] 🔍 [Polymarket] 查询未完成订单...")
            orders = self.client.get_orders(OpenOrderParams())
            
            open_orders = []
            for order in orders:
                status = order.get('status', '').upper()
                if status == 'LIVE':  # 只返回活跃订单
                    normalized = self._normalize_order(order)
                    open_orders.append(normalized)
            
            print(f"[{datetime.now().isoformat()}] ✅ [Polymarket] 找到 {len(open_orders)} 个未完成订单")
            return open_orders
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Polymarket] 查询未完成订单失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
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
            print(f"[{datetime.now().isoformat()}] 📝 [Polymarket] 创建限价买单: price={price}, quantity={quantity}")
            
            order = OrderArgs(
                token_id=self.symbol,
                price=float(price),
                size=quantity,
                side=BUY
            )
            
            print(f"[{datetime.now().isoformat()}] 🔏 [Polymarket] 签名订单...")
            signed = self.client.create_order(order)
            
            print(f"[{datetime.now().isoformat()}] 📤 [Polymarket] 提交订单...")
            resp = self.client.post_order(signed, OrderType.GTC)
            
            order_id = resp.get('orderID')
            print(f"[{datetime.now().isoformat()}] ✅ [Polymarket] 买单创建成功: orderID={order_id}")
            
            return {
                'orderId': order_id,
                'status': 'NEW',
                'side': 'BUY',
                'price': float(price),
                'origQty': quantity,
                'executedQty': 0
            }
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Polymarket] 限价买单失败: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def order_limit_sell(self, quantity: float, price: str, **kwargs) -> Dict:
        """限价卖单"""
        try:
            print(f"[{datetime.now().isoformat()}] 📝 [Polymarket] 创建限价卖单: price={price}, quantity={quantity}")
            
            order = OrderArgs(
                token_id=self.symbol,
                price=float(price),
                size=quantity,
                side=SELL
            )
            
            print(f"[{datetime.now().isoformat()}] 🔏 [Polymarket] 签名订单...")
            signed = self.client.create_order(order)
            
            print(f"[{datetime.now().isoformat()}] 📤 [Polymarket] 提交订单...")
            resp = self.client.post_order(signed, OrderType.GTC)
            
            order_id = resp.get('orderID')
            print(f"[{datetime.now().isoformat()}] ✅ [Polymarket] 卖单创建成功: orderID={order_id}")
            
            return {
                'orderId': order_id,
                'status': 'NEW',
                'side': 'SELL',
                'price': float(price),
                'origQty': quantity,
                'executedQty': 0
            }
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Polymarket] 限价卖单失败: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def cancel_order(self, order_id: str) -> Dict:
        """取消订单"""
        try:
            print(f"[{datetime.now().isoformat()}] 🚫 [Polymarket] 取消订单: orderID={order_id}")
            resp = self.client.cancel(order_id)
            print(f"[{datetime.now().isoformat()}] ✅ [Polymarket] 订单已取消: orderID={order_id}")
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
                import traceback
                traceback.print_exc()
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
