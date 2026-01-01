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
        
        # WebSocket 状态
        self._ws_market = None
        self._ws_user = None
        self._ws_market_thread = None
        self._ws_user_thread = None
        self._ws_market_active = False
        self._ws_user_active = False
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
            
            # 检查余额和授权
            self._check_balance_and_allowance()
            
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

    def _check_balance_and_allowance(self):
        """检查账户余额和授权状态"""
        try:
            # 获取余额信息
            balance_allowance = self.client.get_balance_allowance()
            
            balance = float(balance_allowance.get('balance', 0))
            allowance = float(balance_allowance.get('allowance', 0))
            
            print(f"{self._get_log_prefix()} 💰 余额: ${balance:.2f} USDC")
            print(f"{self._get_log_prefix()} 🔓 授权额度: ${allowance:.2f} USDC")
            
            if balance < 1:
                print(f"{self._get_log_prefix()} ⚠️ 余额不足 $1 USDC")
            
            if allowance < 1:
                print(f"{self._get_log_prefix()} ⚠️ 未授权或授权额度不足")
                print(f"{self._get_log_prefix()} 💡 请访问 https://polymarket.com 完成 'Approve Tokens' 步骤")
                
        except Exception as e:
            print(f"{self._get_log_prefix()} ⚠️ 无法检查余额/授权: {e}")

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
            print(f"{self._get_log_prefix()} ❌ 查询订单失败: {e}")
            raise
    
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
            print(f"{self._get_log_prefix()} ❌ 获取交易规则失败: {e}")
            # 返回默认值
            return {
                'tick_size': 0.001,
                'price_decimals': 3,
                'step_size': 0.01,
                'qty_decimals': 2
            }
    
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
        return 0.001  # 0.1% Taker费率
    
    def subscribe_market_ws(self, callback: Callable = None):
        """订阅市场数据 WebSocket
        
        Args:
            callback: 市场数据更新回调函数
        """
        if self._ws_market_active:
            print(f"{self._get_log_prefix()} ⚠️ 市场 WebSocket 已在运行")
            return
        
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
            print(f"{self._get_log_prefix()} ❌ 市场 WebSocket 错误: {error}")
            print(f"{self._get_log_prefix()} 错误类型: {type(error)}")
            import traceback
            traceback.print_exc()
        
        def on_close(ws, close_status_code, close_msg):
            print(f"{self._get_log_prefix()} 🔌 市场 WebSocket 已关闭")
            print(f"{self._get_log_prefix()} 状态码: {close_status_code}, 消息: {close_msg}")
            self._ws_market_active = False
        
        def on_open(ws):
            print(f"{self._get_log_prefix()} ✅ 市场 WebSocket 已连接")
            # 订阅市场数据 - 市场频道不需要认证
            subscribe_msg = {
                "assets_ids": [self.symbol],
                "type": "market"
            }
            print(f"{self._get_log_prefix()} 📡 发送订阅消息: {subscribe_msg}")
            ws.send(json.dumps(subscribe_msg))
            print(f"{self._get_log_prefix()} 📡 已订阅市场: {self.symbol}")
            
            # 启动心跳线程
            def ping_loop():
                while self._ws_market_active:
                    try:
                        ws.send("PING")
                        time.sleep(10)
                    except Exception as e:
                        print(f"{self._get_log_prefix()} ❌ PING 失败: {e}")
                        break
            
            ping_thread = threading.Thread(target=ping_loop, daemon=True)
            ping_thread.start()
        
        def run_ws():
            ws_url = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
            print(f"{self._get_log_prefix()} 🔗 正在连接到: {ws_url}")
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
        print(f"{self._get_log_prefix()} 🚀 市场 WebSocket 已启动")
    
    def subscribe_user_ws(self, callback: Callable = None):
        """订阅用户订单 WebSocket
        
        Args:
            callback: 订单更新回调函数
        """
        if self._ws_user_active:
            print(f"{self._get_log_prefix()} ⚠️ 用户 WebSocket 已在运行")
            return
        
        self._ws_user_active = True
        self._ws_user_callback = callback
        
        
        def on_message(ws, message):
            try:
                # 忽略 PONG 响应
                if message == "PONG":
                    return
                    
                data = json.loads(message)
                event_type = data.get('event_type')
                
                # Order Message: PLACEMENT/UPDATE/CANCELLATION
                if event_type == 'order':
                    order_type = data.get('type')  # PLACEMENT/UPDATE/CANCELLATION
                    print(f"{self._get_log_prefix()} � 订单事件: {order_type}")
                    
                    event = {
                        'event_type': 'order',
                        'type': order_type,
                        'order_id': data.get('id'),
                        'symbol': data.get('asset_id'),
                        'market': data.get('market'),
                        'side': data.get('side', '').upper(),
                        'price': float(data.get('price', 0)),
                        'original_size': float(data.get('original_size', 0)),
                        'size_matched': float(data.get('size_matched', 0)),
                        'outcome': data.get('outcome'),
                        'timestamp': data.get('timestamp')
                    }
                    
                    if callback:
                        callback(event)
                
                # Trade Message: MATCHED/MINED/CONFIRMED/RETRYING/FAILED
                elif event_type == 'trade':
                    trade_status = data.get('status')
                    print(f"{self._get_log_prefix()} 💱 交易事件: {trade_status}")
                    
                    event = {
                        'event_type': 'trade',
                        'trade_id': data.get('id'),
                        'symbol': data.get('asset_id'),
                        'market': data.get('market'),
                        'side': data.get('side', '').upper(),
                        'status': trade_status,
                        'price': float(data.get('price', 0)),
                        'size': float(data.get('size', 0)),
                        'outcome': data.get('outcome'),
                        'taker_order_id': data.get('taker_order_id'),
                        'maker_orders': data.get('maker_orders', []),
                        'matchtime': data.get('matchtime'),
                        'timestamp': data.get('timestamp')
                    }
                    
                    if callback:
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
            print(f"{self._get_log_prefix()} ❌ 用户 WebSocket 错误: {error}")
            print(f"{self._get_log_prefix()} 错误类型: {type(error)}")
            import traceback
            traceback.print_exc()
        
        def on_close(ws, close_status_code, close_msg):
            print(f"{self._get_log_prefix()} 🔌 用户 WebSocket 已关闭")
            print(f"{self._get_log_prefix()} 状态码: {close_status_code}, 消息: {close_msg}")
            self._ws_user_active = False
        
        def on_open(ws):
            print(f"{self._get_log_prefix()} ✅ 用户 WebSocket 已连接")
            # 订阅用户订单 - markets 参数必须存在(可以为空数组)
            subscribe_msg = {
                "markets": [self.symbol],
                "type": "user",
                "auth": {
                    "apiKey": self.api_creds.api_key,
                    "secret": self.api_creds.api_secret,
                    "passphrase": self.api_creds.api_passphrase
                }
            }
            print(f"{self._get_log_prefix()} 📡 发送订阅消息 (带认证)")
            ws.send(json.dumps(subscribe_msg))
            print(f"{self._get_log_prefix()} 📡 已订阅用户订单")
            
            # 启动心跳线程
            def ping_loop():
                while self._ws_user_active:
                    try:
                        ws.send("PING")
                        time.sleep(10)
                    except Exception as e:
                        print(f"{self._get_log_prefix()} ❌ PING 失败: {e}")
                        break
            
            ping_thread = threading.Thread(target=ping_loop, daemon=True)
            ping_thread.start()
        
        def run_ws():
            ws_url = "wss://ws-subscriptions-clob.polymarket.com/ws/user"
            print(f"{self._get_log_prefix()} 🔗 正在连接到: {ws_url}")
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
        print(f"{self._get_log_prefix()} 🚀 用户 WebSocket 已启动")
    
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
