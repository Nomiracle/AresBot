"""
Polymarket 交易所适配器
基于 py-clob-client SDK
"""
from datetime import datetime
from typing import Dict, List, Optional, Callable
import math
import time
import threading
import json
import websocket
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
    
    # 默认最低价格阈值
    DEFAULT_MIN_PRICE_THRESHOLD = 0.15
    
    def __init__(self, api_key: str, api_secret: str, symbol: str, testnet: bool = True, min_price_threshold: float = None):
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
        
        # 最低价格阈值
        self.min_price_threshold = min_price_threshold if min_price_threshold is not None else self.DEFAULT_MIN_PRICE_THRESHOLD
        
        # Polymarket 配置
        self.host = "https://clob.polymarket.com"
        self.chain_id = 137  # Polygon 主网
        
        # WebSocket 状态
        self._ws_market = None
        self._ws_user = None
        self._ws_market_thread = None
        self._ws_user_thread = None
        self._ws_market_active = False
        self._ws_user_active = False
        
        # 已处理的成交订单 ID 集合（用于去重）
        self._filled_order_ids = set()
        self._filled_order_ids_lock = threading.Lock()
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
                self.api_creds = self.client.create_or_derive_api_creds()
                self.client.set_api_creds(self.api_creds)
                print(f"{self._get_log_prefix()} 🔐 API 凭证已设置")
            except Exception as cred_error:
                print(f"{self._get_log_prefix()} ⚠️ API 凭证设置失败: {cred_error}")
                # 继续执行,某些操作可能不需要 Level 2 认证
            print(f"{self._get_log_prefix()} ✅ 客户端初始化成功")
            print(f"{self._get_log_prefix()} 📍 钱包地址: {api_key}")
            
            
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 初始化失败: {e}")
            import traceback
            traceback.print_exc()
            raise
        
        print(f"{self._get_log_prefix()} ✅ 适配器初始化成功")

    def _get_log_prefix(self) -> str:
        """生成日志前缀"""
        api_key_short = self.api_key[:6] if self.api_key else "NOKEY"
        return f"[{datetime.now().isoformat()}] [polymarket-{api_key_short}-{self.symbol}]"



    def ping(self) -> bool:
        """测试连接"""
        try:
            ok = self.client.get_ok()
            return ok.get('status') == 'ok' if isinstance(ok, dict) else True
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ ping 失败: {e}")
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
            
            print(f"{self._get_log_prefix()} 📊 价格: mid={midpoint}, bid={buy_price}, ask={sell_price}")
            return result
            
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 获取价格失败: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def get_order(self, order_id: str) -> Dict:
        """查询订单状态
        
        使用 CLOB API: GET /data/order/<order_hash>
        """
        try:
            # 使用 py-clob-client 的 get_order 方法直接查询单个订单
            order = self.client.get_order(order_id)
            
            if order:
                return self._normalize_order(order)
            else:
                # 订单不存在
                return {
                    'orderId': order_id,
                    'status': 'NOT_FOUND',
                    'side': 'UNKNOWN',
                    'price': 0,
                    'executedQty': 0,
                    'origQty': 0
                }
            
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 查询订单失败: {e}")
            # 如果查询失败，返回未知状态而不是抛出异常
            return {
                'orderId': order_id,
                'status': 'UNKNOWN',
                'side': 'UNKNOWN',
                'price': 0,
                'executedQty': 0,
                'origQty': 0,
                'error': str(e)
            }
    
    def get_open_orders(self) -> list:
        """获取所有未完成订单"""
        try:
            print(f"{self._get_log_prefix()} 🔍 查询未完成订单...")
            orders = self.client.get_orders(OpenOrderParams())
            
            open_orders = []
            for order in orders:
                status = order.get('status', '').upper()
                if status == 'LIVE':  # 只返回活跃订单
                    normalized = self._normalize_order(order)
                    open_orders.append(normalized)
            
            print(f"{self._get_log_prefix()} ✅ 找到 {len(open_orders)} 个未完成订单")
            return open_orders
            
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 查询未完成订单失败: {e}")
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
            # 价格检查：低于阈值拒绝下单
            if float(price) < self.min_price_threshold:
                error_msg = f"价格 {price} 低于最低限制 {self.min_price_threshold}，拒绝下单"
                print(f"{self._get_log_prefix()} ⛔ {error_msg}")
                raise ValueError(error_msg)
            
            print(f"{self._get_log_prefix()} 📝 创建限价买单: token_id={self.symbol}, price={price}, quantity={quantity}")
            
            order = OrderArgs(
                token_id=self.symbol,
                price=float(price),
                size=quantity,
                side=BUY
            )
            
            print(f"{self._get_log_prefix()} 🔏 签名订单...")
            signed = self.client.create_order(order)
            
            print(f"{self._get_log_prefix()} 📤 提交订单...")
            resp = self.client.post_order(signed, OrderType.GTC)
            
            order_id = resp.get('orderID')
            print(f"{self._get_log_prefix()} ✅ 买单创建成功: orderID={order_id}")
            
            return {
                'orderId': order_id,
                'status': 'NEW',
                'side': 'BUY',
                'price': float(price),
                'origQty': quantity,
                'executedQty': 0
            }
            
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 限价买单失败: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def order_limit_sell(self, quantity: float, price: str, **kwargs) -> Dict:
        """限价卖单"""
        try:
            # 在下卖单前检查 token 余额
            print(f"{self._get_log_prefix()} 🔍 检查 Conditional Token 余额...")
            self._check_token_balance(quantity)
            
            print(f"{self._get_log_prefix()} 📝 创建限价卖单: token_id={self.symbol}, price={price}, quantity={quantity}")
            
            order = OrderArgs(
                token_id=self.symbol,
                price=float(price),
                size=quantity,
                side=SELL
            )
            
            print(f"{self._get_log_prefix()} 🔏 签名订单...")
            signed = self.client.create_order(order)
            
            print(f"{self._get_log_prefix()} 📤 提交订单...")
            resp = self.client.post_order(signed, OrderType.GTC)
            
            order_id = resp.get('orderID')
            print(f"{self._get_log_prefix()} ✅ 卖单创建成功: orderID={order_id}")
            
            return {
                'orderId': order_id,
                'status': 'NEW',
                'side': 'SELL',
                'price': float(price),
                'origQty': quantity,
                'executedQty': 0
            }
            
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 限价卖单失败: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def _check_token_balance(self, required_quantity: float, max_wait: int = 30):
        """检查/等待 token 余额达到要求
        
        Args:
            required_quantity: 需要的 token 数量
            max_wait: 最多等待时间（秒）
            
        Raises:
            ValueError: 超时后余额仍不足
        """
        from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
        
        start_time = time.time()
        token_balance = 0.0
        
        while time.time() - start_time < max_wait:
            try:
                params = BalanceAllowanceParams(
                    asset_type=AssetType.CONDITIONAL,
                    token_id=self.symbol
                )
                balance_result = self.client.get_balance_allowance(params)
                token_balance_raw = float(balance_result.get('balance', 0))
                token_balance = token_balance_raw / 1_000_000
                
                print(f"{self._get_log_prefix()} 📊 Token 余额: {token_balance:.2f}/{required_quantity}")
                
                # 余额足够则返回
                if token_balance >= required_quantity * 0.99:  # 允许 1% 误差
                    print(f"{self._get_log_prefix()} ✅ Token 余额充足!")
                    return token_balance
                
                # 刷新缓存
                try:
                    self.client.update_balance_allowance(params)
                except:
                    pass
                
                time.sleep(1)
                
            except Exception as e:
                print(f"{self._get_log_prefix()} ⚠️ 查询余额失败: {e}")
                time.sleep(1)
        
        # 超时
        error_msg = f"Token 余额不足: {token_balance:.2f}/{required_quantity} (等待 {max_wait}s)"
        print(f"{self._get_log_prefix()} ❌ {error_msg}")
        raise ValueError(error_msg)
    
    def cancel_order(self, order_id: str) -> Dict:
        """取消订单"""
        try:
            print(f"{self._get_log_prefix()} 🚫 取消订单: orderID={order_id}")
            resp = self.client.cancel(order_id)
            print(f"{self._get_log_prefix()} ✅ 订单已取消: orderID={order_id}")
            return {
                'orderId': order_id,
                'status': 'CANCELED'
            }
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 取消订单失败: {e}")
            raise
    
    def cancel_replace_order(self, side: str, order_type: str, 
                            quantity: float, price: str, cancel_order_id: str, **kwargs) -> Dict:
        """取消并替换订单"""
        try:
            print(f"{self._get_log_prefix()} 🔄 开始改价: orderID={cancel_order_id}, side={side}, new_price={price}, quantity={quantity}")
            
            # Polymarket不支持原子性的cancel_replace,需要分两步
            # 1. 取消旧订单
            print(f"{self._get_log_prefix()} 🚫 改价步骤1: 取消旧订单 {cancel_order_id}")
            self.cancel_order(cancel_order_id)
            
            # 2. 创建新订单
            time.sleep(0.1)  # 短暂延迟确保取消完成
            
            print(f"{self._get_log_prefix()} 📝 改价步骤2: 创建新订单 price={price}, quantity={quantity}")
            if side.upper() == 'BUY':
                new_order = self.order_limit_buy(quantity, price, **kwargs)
            else:
                new_order = self.order_limit_sell(quantity, price, **kwargs)
            
            print(f"{self._get_log_prefix()} ✅ 改价完成: 旧订单={cancel_order_id}, 新订单={new_order.get('orderId')}")
            
            # 返回 Binance 兼容的格式,包含 newOrderResponse
            return {
                'newOrderResponse': new_order
            }
                
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 改价失败: orderID={cancel_order_id}, error={e}")
            raise
    
    def get_trading_rules(self) -> Dict:
        """获取交易规则"""        
        try:
            # Polymarket的价格范围是0-1 (概率)
            # 最小价格单位通常是0.001 (0.1%)
            return {
                'tick_size': 0.01,
                'price_decimals': 2,
                'step_size': 0.01,
                'qty_decimals': 2
            }
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 获取交易规则失败: {e}")
            
    
    def start_ws(self, on_price_update: Callable[[float], None], 
                 on_order_update: Callable[[Dict], None]) -> bool:
        """启动价格和订单监听 (WebSocket 模式)"""
        
        # 市场数据回调包装
        def market_callback(data):
            try:
                # 处理列表格式的数据
                if isinstance(data, list):
                    # 如果是列表，遍历每个元素
                    for item in data:
                        if isinstance(item, dict):
                            process_market_data(item)
                elif isinstance(data, dict):
                    # 如果是字典，直接处理
                    process_market_data(data)
                    
            except Exception as e:
                print(f"{self._get_log_prefix()} ❌ 处理价格更新失败: {e}")
                import traceback
                traceback.print_exc()
        
        def process_market_data(data):
            """处理单个市场数据项"""
            # 只处理 price_change 事件
            event_type = data.get('event_type')
            
            if event_type == 'price_change':
                # 解析 price_changes 数组
                price_changes = data.get('price_changes', [])
                
                for change in price_changes:
                    asset_id = change.get('asset_id')
                    
                    # 只处理当前交易的 token
                    if asset_id == self.symbol:
                        # 使用 best_bid 和 best_ask 计算中间价
                        best_bid_str = change.get('best_bid', '0')
                        best_ask_str = change.get('best_ask', '0')
                        
                        # 转换为浮点数
                        try:
                            best_bid = float(best_bid_str) if best_bid_str else 0
                            best_ask = float(best_ask_str) if best_ask_str else 0
                        except (ValueError, TypeError):
                            best_bid = 0
                            best_ask = 0
                        
                        if best_bid > 0 and best_ask > 0:
                            mid_price = (best_bid + best_ask) / 2
                        elif best_bid > 0:
                            mid_price = best_bid
                        elif best_ask > 0:
                            mid_price = best_ask
                        else:
                            # 使用价格字段作为后备
                            try:
                                mid_price = float(change.get('price', 0))
                            except (ValueError, TypeError):
                                mid_price = 0
                        
                        if mid_price > 0 and on_price_update:
                            # print(f"{self._get_log_prefix()} 💰 价格更新: {mid_price} (bid={best_bid}, ask={best_ask})")
                            on_price_update(mid_price)
                        break
        
        # 订单更新回调包装
        def order_callback(event):
            try:
                if on_order_update:
                    on_order_update(event)
            except Exception as e:
                print(f"{self._get_log_prefix()} ❌ 处理订单更新失败: {e}")
        
        # 启动 WebSocket 订阅
        self.subscribe_market_ws(callback=market_callback)
        self.subscribe_user_ws(callback=order_callback)
        
        print(f"{self._get_log_prefix()} ✅ WebSocket 监听已启动")
        return True
    
    def stop_ws(self) -> None:
        """停止监听"""
        # 停止 WebSocket 连接
        self.unsubscribe_market_ws()
        self.unsubscribe_user_ws()
        
        print(f"{self._get_log_prefix()} 🔌 监听已停止")
    
    def check_pending_orders(self, pending_orders: List[Dict]):
        """检查待处理订单的状态
        
        注意: 使用 WebSocket 模式时,订单更新会通过 WebSocket 实时推送,
        不需要主动轮询检查。此方法保留用于兼容基类接口。
        
        Args:
            pending_orders: 待检查的订单列表
        """
        # WebSocket 模式下订单更新会自动推送,无需主动检查
        pass
    
    def get_fee_rate(self) -> float:
        """获取手续费率
        
        Polymarket的手续费结构:
        - Maker: -0.02% (返佣)
        - Taker: 0.1%
        
        Returns:
            float: 手续费率 (使用Taker费率作为保守估计)
        """
        return 0.0  # 0.1% Taker费率
    
    def subscribe_market_ws(self, callback: Callable = None):
        """订阅市场数据 WebSocket
        
        Args:
            callback: 市场数据更新回调函数
        """
        if self._ws_market_active:
            print(f"{self._get_log_prefix()} ⚠️ 市场 WebSocket 已在运行")
            return
        
        # 生成唯一 ID 用于区分不同的 WebSocket 连接
        import uuid
        ws_id = str(uuid.uuid4())[:8]
        
        self._ws_market_active = True
        self._ws_market_callback = callback
        
        def on_message(ws, message):
            try:
                # 忽略 PONG 响应
                if message == "PONG":
                    return
                    
                data = json.loads(message)
                # print(f"{self._get_log_prefix()} 📊 市场数据: {data}")
                
                if callback:
                    callback(data)
                    
            except json.JSONDecodeError:
                # 非 JSON 消息,可能是心跳响应
                pass
            except Exception as e:
                print(f"{self._get_log_prefix()} ❌ 处理市场消息失败: {e}")
        
        def on_error(ws, error):
            print(f"{self._get_log_prefix()} ❌ 市场 WebSocket[{ws_id}] 错误: {error}")
            print(f"{self._get_log_prefix()} 错误类型: {type(error)}")
            import traceback
            traceback.print_exc()
        
        def on_close(ws, close_status_code, close_msg):
            print(f"{self._get_log_prefix()} 🔌 市场 WebSocket[{ws_id}] 已关闭")
            print(f"{self._get_log_prefix()} 状态码: {close_status_code}, 消息: {close_msg}")
            self._ws_market_active = False
        
        def on_open(ws):
            print(f"{self._get_log_prefix()} ✅ 市场 WebSocket[{ws_id}] 已连接")
            # 订阅市场数据 - 市场频道不需要认证
            subscribe_msg = {
                "assets_ids": [self.symbol],
                "type": "market"
            }
            print(f"{self._get_log_prefix()} 📡 发送订阅消息: {subscribe_msg}")
            ws.send(json.dumps(subscribe_msg))
            print(f"{self._get_log_prefix()} 📡 已订阅市场: {self.symbol}")
            # 心跳由 run_forever(ping_interval=10) 自动处理，无需自定义 ping_loop
        
        def run_ws():
            ws_url = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
            print(f"{self._get_log_prefix()} 🔗 市场 WebSocket[{ws_id}] 正在连接到: {ws_url}")
            self._ws_market = websocket.WebSocketApp(
                ws_url,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
                on_open=on_open
            )
            # 添加超时和重连配置
            self._ws_market.run_forever(
                ping_interval=10,
                ping_timeout=5,
                reconnect=3
            )
        
        self._ws_market_thread = threading.Thread(target=run_ws, daemon=True)
        self._ws_market_thread.start()
        print(f"{self._get_log_prefix()} 🚀 市场 WebSocket[{ws_id}] 已启动")
    
    def _is_order_already_filled(self, order_id: str) -> bool:
        """检查订单是否已经处理过成交事件（用于去重）
        
        Args:
            order_id: 订单 ID
        
        Returns:
            bool: 如果已处理过返回 True，否则返回 False 并将其加入已处理集合
        """
        if not order_id:
            return False
        
        with self._filled_order_ids_lock:
            if order_id in self._filled_order_ids:
                return True
            self._filled_order_ids.add(order_id)
            
            # 防止内存泄漏：限制集合大小为 1000
            if len(self._filled_order_ids) > 1000:
                # 移除一半的旧记录（简单策略）
                to_remove = list(self._filled_order_ids)[:500]
                for oid in to_remove:
                    self._filled_order_ids.discard(oid)
            
            return False
    
    def clear_filled_order_ids(self):
        """清空已处理的成交订单 ID 集合（市场切换时调用）"""
        with self._filled_order_ids_lock:
            self._filled_order_ids.clear()
            print(f"{self._get_log_prefix()} 🧹 已清空成交订单去重缓存")
    
    def _process_order_event(self, data: dict, symbol: str = None) -> dict:
        """处理订单事件
        
        Args:
            data: 订单事件数据
            symbol: 用于事件的 symbol 字段,如果为 None 则使用 self.symbol
        
        Returns:
            dict: 处理后的事件字典,如果不需要回调则返回 None
        """
        order_type = data.get('type')  # PLACEMENT/UPDATE/CANCELLATION
        print(f"{self._get_log_prefix()} 📋 订单事件: {order_type}")
        
        order_id = data.get('id')
        asset_id = str(data.get('asset_id'))  # 确保是字符串格式
        side = data.get('side', '').upper()
        price = float(data.get('price', 0))
        original_size = float(data.get('original_size', 0))
        size_matched = float(data.get('size_matched', 0))
        
        # 使用传入的 symbol 或默认使用 self.symbol
        event_symbol = symbol if symbol is not None else self.symbol
        print(f"{self._get_log_prefix()} {asset_id}/{self.symbol}/{symbol}，event_symbol: {event_symbol}")
        
        # 转换为 trading.py 期望的格式
        if order_type == 'CANCELLATION':
            # 订单取消事件
            event = {
                'event_type': 'order_cancelled',
                'order_id': order_id,
                'symbol': event_symbol,
                'side': side
            }
            print(f"{self._get_log_prefix()} ❌ 订单取消: {order_id}")
            return event
        
        elif order_type == 'PLACEMENT':
            # 订单创建事件 - 暂不处理,等待成交或取消
            print(f"{self._get_log_prefix()} ➕ 订单创建: {order_id}")
            return None
        
        elif order_type == 'UPDATE':
            # 订单更新事件 - 检查是否完全成交
            if size_matched >= original_size and original_size > 0:
                # 去重检查：防止同一订单的 order_filled 事件被重复处理
                if self._is_order_already_filled(order_id):
                    print(f"{self._get_log_prefix()} ⚠️ 订单成交事件重复(order UPDATE)，跳过: {order_id}")
                    return None
                
                # 完全成交
                event = {
                    'event_type': 'order_filled',
                    'order_id': order_id,
                    'symbol': event_symbol,
                    'side': side,
                    'price': price,
                    'quantity': original_size,
                    'executedQty': size_matched
                }
                print(f"{self._get_log_prefix()} ✅ 订单成交: {order_id}, 数量: {size_matched}/{original_size}")
                return event
            else:
                # 部分成交或其他更新 - 暂不处理
                print(f"{self._get_log_prefix()} 🔄 订单更新: {order_id}, 已成交: {size_matched}/{original_size}")
                return None
        
        else:
            print(f"{self._get_log_prefix()} ❓ 未知订单类型: {order_type}")
            return None
    
    def _process_trade_event(self, data: dict, symbol: str = None) -> dict:
        """处理交易事件
        
        Trade 事件在以下情况触发:
        - 市价单被匹配 ("MATCHED")
        - 用户的限价单被包含在交易中 ("MATCHED")
        - 交易状态变更 ("MINED", "CONFIRMED", "RETRYING", "FAILED")
        
        Args:
            data: 交易事件数据
            symbol: 用于事件的 symbol 字段,如果为 None 则使用 self.symbol
        
        Returns:
            dict: 处理后的事件字典,如果不需要回调则返回 None
        """
        trade_id = data.get('id')
        status = data.get('status')  # MATCHED/MINED/CONFIRMED/RETRYING/FAILED
        taker_order_id = data.get('taker_order_id')
        asset_id = str(data.get('asset_id', ''))
        side = data.get('side', '').upper()
        price = float(data.get('price', 0))
        size = float(data.get('size', 0))
        outcome = data.get('outcome')
        market = data.get('market')  # condition_id
        trader_side = data.get('trader_side')  # TAKER/MAKER
        match_time = data.get('match_time')
        transaction_hash = data.get('transaction_hash')
        maker_orders = data.get('maker_orders', [])
        
        # 使用传入的 symbol 或默认使用 self.symbol
        event_symbol = symbol if symbol is not None else self.symbol
        
        print(f"{self._get_log_prefix()} 💱 Trade事件: status={status}, side={side}, size={size}, price={price}, outcome={outcome}, trader_side={trader_side}")
        print(f"{self._get_log_prefix()} 💱 Trade详情: trade_id={trade_id}, taker_order_id={taker_order_id[:16] if taker_order_id else None}...")
        
        if status == 'MATCHED':
            # 判断是 TAKER 还是 MAKER
            if trader_side == 'MAKER':
                # 作为 Maker：我的限价单被别人吃掉
                # 需要从 maker_orders 中找到我的订单
                my_maker_address = self.api_key.lower()  # Proxy Wallet 地址
                my_orders = [
                    order for order in maker_orders 
                    if order.get('maker_address', '').lower() == my_maker_address
                ]
                
                if my_orders:
                    # 可能有多个订单被匹配，逐个返回事件
                    # 这里只处理第一个，如果需要处理多个可以改为返回列表
                    for my_order in my_orders:
                        my_order_id = my_order.get('order_id')
                        my_matched_amount = float(my_order.get('matched_amount', 0))
                        my_price = float(my_order.get('price', 0))
                        my_side = my_order.get('side', '').upper()
                        my_outcome = my_order.get('outcome')
                        
                        # 去重检查：防止同一订单的 order_filled 事件被重复处理
                        if self._is_order_already_filled(my_order_id):
                            print(f"{self._get_log_prefix()} ⚠️ 订单成交事件重复(trade MAKER)，跳过: {my_order_id[:16]}...")
                            continue
                        
                        print(f"{self._get_log_prefix()} ✅ 订单成交(Maker): order_id={my_order_id[:16]}..., {my_side} {my_matched_amount}@{my_price}, outcome={my_outcome}")
                        
                        # 如果是买单成交，等待 token 余额更新后再回调
                        if my_side == 'BUY':
                            try:
                                print(f"{self._get_log_prefix()} ⏳ 等待 Token 余额更新...")
                                self._check_token_balance(my_matched_amount)
                                print(f"{self._get_log_prefix()} ✅ Token 余额已更新，触发回调")
                            except Exception as e:
                                print(f"{self._get_log_prefix()} ⚠️ 等待余额超时，仍触发回调: {e}")
                        
                        event = {
                            'event_type': 'order_filled',
                            'trade_id': trade_id,
                            'order_id': my_order_id,
                            'taker_order_id': taker_order_id,
                            'symbol': event_symbol,
                            'side': my_side,
                            'price': my_price,
                            'quantity': my_matched_amount,
                            'size': my_matched_amount,
                            'executedQty': my_matched_amount,
                            'outcome': my_outcome,
                            'market': market,
                            'trader_side': 'MAKER',
                            'match_time': match_time,
                            'maker_orders': maker_orders
                        }
                        return event  # 返回第一个匹配的订单事件
                else:
                    print(f"{self._get_log_prefix()} ⚠️ Maker 交易但未找到我的订单, my_address={my_maker_address}")
                    return None
            else:
                # 作为 Taker：我主动吃单
                # 去重检查：防止同一订单的 order_filled 事件被重复处理
                if self._is_order_already_filled(taker_order_id):
                    print(f"{self._get_log_prefix()} ⚠️ 订单成交事件重复(trade TAKER)，跳过: {taker_order_id[:16] if taker_order_id else None}...")
                    return None
                
                print(f"{self._get_log_prefix()} ✅ 订单成交(Taker): {trade_id}, {side} {size}@{price}")
                
                # 如果是买单成交，等待 token 余额更新后再回调
                if side == 'BUY':
                    try:
                        print(f"{self._get_log_prefix()} ⏳ 等待 Token 余额更新...")
                        self._check_token_balance(size)
                        print(f"{self._get_log_prefix()} ✅ Token 余额已更新，触发回调")
                    except Exception as e:
                        print(f"{self._get_log_prefix()} ⚠️ 等待余额超时，仍触发回调: {e}")
                
                event = {
                    'event_type': 'order_filled',
                    'trade_id': trade_id,
                    'order_id': taker_order_id,
                    'taker_order_id': taker_order_id,
                    'symbol': event_symbol,
                    'side': side,
                    'price': price,
                    'quantity': size,
                    'size': size,
                    'executedQty': size,
                    'outcome': outcome,
                    'market': market,
                    'trader_side': 'TAKER',
                    'match_time': match_time,
                    'maker_orders': maker_orders
                }
                return event
        
        else:
            # 其他状态 (MINED/CONFIRMED/RETRYING/FAILED 等) - 仅打印日志
            print(f"{self._get_log_prefix()} � Trade状态更新: {status}, trade_id={trade_id}")
            return None
    
    def subscribe_user_ws(self, callback: Callable = None):
        """订阅用户订单 WebSocket
        
        Args:
            callback: 订单更新回调函数
        """
        if self._ws_user_active:
            print(f"{self._get_log_prefix()} ⚠️ 用户 WebSocket 已在运行")
            return
        
        # 生成唯一 ID 用于区分不同的 WebSocket 连接
        import uuid
        ws_id = str(uuid.uuid4())[:8]
        
        self._ws_user_active = True
        self._ws_user_callback = callback
        
        
        def on_message(ws, message):
            try:
                print(f"{self._get_log_prefix()} 📡 用户WS[{ws_id}] 收到消息: {message}")
                # 忽略 PONG 响应
                if message == "PONG":
                    return
                    
                data = json.loads(message)
                event_type = data.get('event_type')
                
                # Order Message: PLACEMENT/UPDATE/CANCELLATION
                if event_type == 'order':
                    event = self._process_order_event(data)
                    if event and callback:
                        callback(event)
                
                # Trade Message: MATCHED/MINED/CONFIRMED/RETRYING/FAILED
                elif event_type == 'trade':
                    event = self._process_trade_event(data)
                    if event and callback:
                        callback(event)
                else:
                    # 其他类型的消息
                    print(f"{self._get_log_prefix()} 📬 用户消息: {event_type}")
                        
            except json.JSONDecodeError:
                # 非 JSON 消息,可能是心跳响应
                pass
            except Exception as e:
                print(f"{self._get_log_prefix()} ❌ 处理订单消息失败: {e}")
                import traceback
                traceback.print_exc()
        
        def on_error(ws, error):
            print(f"{self._get_log_prefix()} ❌ 用户WS[{ws_id}] 错误: {error}")
            print(f"{self._get_log_prefix()} 错误类型: {type(error)}")
            import traceback
            traceback.print_exc()
        
        def on_close(ws, close_status_code, close_msg):
            print(f"{self._get_log_prefix()} 🔌 用户WS[{ws_id}] 已关闭")
            print(f"{self._get_log_prefix()} 状态码: {close_status_code}, 消息: {close_msg}")
            self._ws_user_active = False
        
        def on_open(ws):
            # 检测是否为重连
            is_reconnect = self._ws_user_connected_once if hasattr(self, '_ws_user_connected_once') else False
            self._ws_user_connected_once = True
            
            if is_reconnect:
                print(f"{self._get_log_prefix()} 🔄 用户WS[{ws_id}] 重连成功")
            else:
                print(f"{self._get_log_prefix()} ✅ 用户WS[{ws_id}] 已连接")
            
            # 获取 condition_id (如果有的话)
            markets_to_subscribe = []
            if hasattr(self, 'condition_id') and self.condition_id:
                markets_to_subscribe = [self.condition_id]
                print(f"{self._get_log_prefix()} 📋 订阅市场: {self.condition_id}")
            else:
                print(f"{self._get_log_prefix()} 📋 订阅所有市场 (无 condition_id)")
            
            # 订阅用户订单 - markets 参数为条件 ID 数组
            subscribe_msg = {
                "auth": {
                    "apiKey": self.api_creds.api_key,
                    "secret": self.api_creds.api_secret,
                    "passphrase": self.api_creds.api_passphrase
                },
                "markets": markets_to_subscribe,
                "type": "user"
            }
            print(f"{self._get_log_prefix()} 📡 发送用户订阅消息 (带认证)，subscribe_msg：{subscribe_msg}")
            ws.send(json.dumps(subscribe_msg))
            print(f"{self._get_log_prefix()} 📡 已订阅用户订单")
            
            # 如果是重连，发送 reconnected 事件给 trading.py 触发订单状态同步
            if is_reconnect and callback:
                reconnect_event = {
                    'event_type': 'reconnected',
                    'symbol': self.outcome if hasattr(self, 'outcome') else self.symbol
                }
                callback(reconnect_event)
                print(f"{self._get_log_prefix()} 📤 已发送 reconnected 事件，触发订单状态同步")
        
        def run_ws():
            ws_url = "wss://ws-subscriptions-clob.polymarket.com/ws/user"
            print(f"{self._get_log_prefix()} 🔗 用户WS[{ws_id}] 正在连接到: {ws_url}")
            self._ws_user = websocket.WebSocketApp(
                ws_url,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
                on_open=on_open
            )
            # 添加超时和重连配置
            self._ws_user.run_forever(
                ping_interval=10,
                ping_timeout=5,
                reconnect=3
            )
        
        self._ws_user_thread = threading.Thread(target=run_ws, daemon=True)
        self._ws_user_thread.start()
        print(f"{self._get_log_prefix()} 🚀 用户WS[{ws_id}] 已启动")
    
    def unsubscribe_market_ws(self):
        """取消订阅市场数据 WebSocket"""
        self._ws_market_active = False
        if self._ws_market:
            self._ws_market.close()
        print(f"{self._get_log_prefix()} 🔌 市场 WebSocket 已停止")
    
    def unsubscribe_user_ws(self):
        """取消订阅用户订单 WebSocket"""
        self._ws_user_active = False
        if self._ws_user:
            self._ws_user.close()
        print(f"{self._get_log_prefix()} 🔌 用户 WebSocket 已停止")


    def calculate_sell_price(self, buy_price, sell_offset_percent, tick_size, price_decimals, current_price=None):
        """计算卖出价格（带手续费保护）"""
        sell_offset = sell_offset_percent / 100.0
        raw_sell_price = (current_price or buy_price) + sell_offset
        
        # 最低保护价（买入价 + 0.2% 手续费）
        min_price = buy_price * (1 + 2 * self.get_fee_rate())  # 买入价 + 2倍手续费
        
        # 最终卖价
        sell_price = max(raw_sell_price, min_price)
        sell_price = math.floor(sell_price / tick_size) * tick_size if tick_size else sell_price
        
        if sell_price <= buy_price and tick_size:
            sell_price = round(buy_price + tick_size, price_decimals)
        
        # 确保价格落在 0-1 区间（概率范围）
        sell_price = max(0.01, min(0.99, sell_price))

        return sell_price

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
        target_price = current_price + offset
        
        # 按 tick_size 对齐（向下取整）
        if tick_size and tick_size > 0:
            target_price = math.floor(target_price / tick_size) * tick_size
        
        # 按小数位数对齐
        target_price = round(target_price, price_decimals)
        
        # 确保价格落在 0-1 区间（概率范围）
        target_price = max(0.01, min(0.99, target_price))
        
        return target_price
