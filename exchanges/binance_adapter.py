"""
Binance 交易所适配器
封装所有币安特定的 API 调用与 WebSocket 逻辑
"""
import math
from datetime import datetime
from typing import Dict, List, Optional, Callable
from binance.client import Client
from binance.exceptions import BinanceAPIException
from binance import ThreadedWebsocketManager

from .base import BaseExchange


class BinanceAdapter(BaseExchange):
    """币安交易所适配器"""
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        """初始化币安客户端"""
        self.client = Client(api_key, api_secret, testnet=testnet)
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        
        # 监听器状态
        self._price_monitor_active = False
        self._order_monitor_active = False
        self._ws_manager = None
        self._on_price_callback = None
        self._on_order_callback = None
    
    def ping(self) -> bool:
        """测试连接"""
        try:
            self.client.ping()
            return True
        except Exception:
            return False
    
    def get_symbol_info(self, symbol: str) -> Dict:
        """获取交易对信息"""
        try:
            result = self.client.get_symbol_info(symbol=symbol)
            if not result:
                print(f"[{datetime.now().isoformat()}] ⚠️ [Binance] 交易对 {symbol} 不存在或无效")
            return result
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Binance] 获取交易对信息失败 ({symbol}): {e}")
            return None
    
    def get_symbol_ticker(self, symbol: str) -> Dict:
        """获取交易对当前价格"""
        return self.client.get_symbol_ticker(symbol=symbol)
    
    def get_open_orders(self, symbol: str) -> List[Dict]:
        """获取未完成订单"""
        return self.client.get_open_orders(symbol=symbol)
    
    def get_order(self, symbol: str, order_id: str) -> Dict:
        """查询订单状态"""
        return self.client.get_order(symbol=symbol, orderId=int(order_id))
    
    def order_limit_buy(self, symbol: str, quantity: float, price: str, **kwargs) -> Dict:
        """限价买单"""
        return self.client.order_limit_buy(
            symbol=symbol,
            quantity=quantity,
            price=price,
            timeInForce=kwargs.get('timeInForce', 'GTC')
        )
    
    def order_limit_sell(self, symbol: str, quantity: float, price: str, **kwargs) -> Dict:
        """限价卖单"""
        return self.client.order_limit_sell(
            symbol=symbol,
            quantity=quantity,
            price=price,
            timeInForce=kwargs.get('timeInForce', 'GTC')
        )
    
    def cancel_order(self, symbol: str, order_id: str) -> Dict:
        """取消订单"""
        return self.client.cancel_order(symbol=symbol, orderId=int(order_id))
    
    def cancel_replace_order(self, symbol: str, side: str, order_type: str, 
                            quantity: float, price: str, cancel_order_id: str, **kwargs) -> Dict:
        """取消并替换订单（改价）"""
        # 优先使用 python-binance 的 cancelReplace 接口
        replace_fn = getattr(self.client, 'order_cancel_replace', None) or getattr(self.client, 'cancel_replace_order', None)
        
        if replace_fn:
            return replace_fn(
                symbol=symbol,
                side=side,
                type=order_type,
                timeInForce=kwargs.get('timeInForce', 'GTC'),
                quantity=quantity,
                price=price,
                cancelOrderId=cancel_order_id,
                cancelReplaceMode=kwargs.get('cancelReplaceMode', 'STOP_ON_FAILURE')
            )
        else:
            # 兼容旧版库：直接调用底层 POST
            raw_post = getattr(self.client, '_post', None)
            if raw_post:
                return raw_post(
                    'order/cancelReplace', True,
                    data={
                        'symbol': symbol,
                        'side': side,
                        'type': order_type,
                        'timeInForce': kwargs.get('timeInForce', 'GTC'),
                        'quantity': quantity,
                        'price': price,
                        'cancelOrderId': cancel_order_id,
                        'cancelReplaceMode': kwargs.get('cancelReplaceMode', 'STOP_ON_FAILURE')
                    }
                )
            else:
                raise NotImplementedError("当前 python-binance 版本不支持 cancelReplace")
    
    def start_websocket(self, symbol: str, on_ticker: Callable, on_user: Optional[Callable] = None) -> Dict:
        """启动 WebSocket 连接"""
        result = {
            'manager': None,
            'ticker_enabled': False,
            'user_enabled': False
        }
        
        try:
            # 创建 TWM
            if self.api_key and self.api_secret:
                twm = ThreadedWebsocketManager(api_key=self.api_key, api_secret=self.api_secret)
            else:
                twm = ThreadedWebsocketManager()
            
            twm.start()
            result['manager'] = twm
            
            # 启动行情流（公开流）
            twm.start_symbol_ticker_socket(callback=on_ticker, symbol=symbol)
            result['ticker_enabled'] = True
            print(f"[{datetime.now().isoformat()}] ✅ [Binance] 行情流已启动 ({symbol})")
            
            # 启动用户数据流（需要认证）
            if on_user and self.api_key and self.api_secret:
                try:
                    # 创建包装回调函数，过滤不匹配的交易对
                    def filtered_on_user(msg):
                        try:
                            # 检查消息中的交易对是否匹配
                            msg_symbol = msg.get('s')  # 币安用户数据流中交易对字段为 's'
                            if msg_symbol and msg_symbol != symbol:
                                # 交易对不匹配，丢弃此消息
                                print(f"[{datetime.now().isoformat()}] 🔇 [Binance] 丢弃不匹配交易对的消息: {msg_symbol} (期望: {symbol})")
                                return
                            # 交易对匹配或消息中没有交易对字段，调用原始回调
                            on_user(msg)
                        except Exception as e:
                            print(f"[{datetime.now().isoformat()}] ❌ [Binance] 用户数据回调过滤错误: {e}")
                    
                    twm.start_user_socket(callback=filtered_on_user)
                    result['user_enabled'] = True
                    print(f"[{datetime.now().isoformat()}] ✅ [Binance] 用户数据流已启动")
                except BinanceAPIException as e:
                    print(f"[{datetime.now().isoformat()}] ⚠️ [Binance] 用户数据流启动失败 (API错误: {e.status_code if hasattr(e, 'status_code') else 'unknown'} - {e.message if hasattr(e, 'message') else str(e)})")
                except Exception as e:
                    print(f"[{datetime.now().isoformat()}] ❌ [Binance] 用户数据流启动失败 ({type(e).__name__}: {e})")
            
            return result
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Binance] WebSocket 启动失败: {e}")
            return result
    
    def stop_websocket(self, ws_manager) -> None:
        """停止 WebSocket 连接"""
        if ws_manager:
            try:
                ws_manager.stop()
            except Exception as e:
                print(f"[{datetime.now().isoformat()}] ⚠️ [Binance] WebSocket 停止失败: {e}")
    
    def parse_ticker_message(self, msg: Dict) -> Optional[float]:
        """解析币安行情消息"""
        try:
            # Binance symbol ticker: {'s': 'SYMBOL', 'c': 'lastPrice', ...}
            last_price = msg.get('c') or msg.get('p') or msg.get('price')
            if last_price is not None:
                return float(last_price)
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Binance] 解析行情消息失败: {e}")
        return None
    
    def parse_user_message(self, msg: Dict) -> Optional[Dict]:
        """解析币安用户数据消息"""
        try:
            # 错误消息
            if msg.get('e') == 'error':
                return {
                    'event_type': 'error',
                    'error_message': f"{msg.get('type')}: {msg.get('m')}"
                }
            
            # 订单更新（executionReport）
            if msg.get('e') == 'executionReport':
                order_status = msg.get('X')  # NEW/PARTIALLY_FILLED/FILLED/CANCELED...
                order_id = str(msg.get('i'))
                
                # 🔍 调试日志：记录所有订单事件
                print(f"[{datetime.now().isoformat()}] 📨 [Binance] 收到订单事件: ID={order_id}, 状态={order_status}, 方向={msg.get('S')}")
                
                # 只有完全成交的订单才触发 order_filled 事件
                event_type = 'order_filled' if order_status == 'FILLED' else 'order_update'
                
                return {
                    'event_type': event_type,
                    'order_id': order_id,
                    'symbol': msg.get('s'),
                    'side': msg.get('S'),  # BUY/SELL
                    'status': order_status,
                    'price': msg.get('p'),  # 订单价格
                    'quantity': msg.get('q'),  # 订单数量
                    'executedQty': msg.get('z'),  # 累计成交数量（重要：用于计算卖单数量）
                    'lastExecutedQty': msg.get('l')  # 本次成交数量
                }
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Binance] 解析用户消息失败: {e}")
        return None
    
    def get_price_precision(self, symbol_info: Dict) -> tuple:
        """提取价格精度"""
        if not symbol_info or 'filters' not in symbol_info:
            print(f"[{datetime.now().isoformat()}] ⚠️ [Binance] symbol_info 无效，使用默认价格精度")
            return 0.01, 2  # 默认值
            
        price_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'PRICE_FILTER'), None)
        if price_filter:
            tick_size = float(price_filter['tickSize'])
            price_decimals = int(abs(math.log10(tick_size)))
            return tick_size, price_decimals
        return 0.01, 2  # 默认值
    
    def get_quantity_precision(self, symbol_info: Dict) -> tuple:
        """提取数量精度"""
        if not symbol_info or 'filters' not in symbol_info:
            print(f"[{datetime.now().isoformat()}] ⚠️ [Binance] symbol_info 无效，使用默认数量精度")
            return 0.000001, 6  # 默认值
            
        lot_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
        if lot_filter:
            step_size = float(lot_filter['stepSize'])
            qty_decimals = int(abs(math.log10(step_size)))
            return step_size, qty_decimals
        return 0.000001, 6  # 默认值
    
    def get_client(self):
        """获取原始客户端（用于兼容旧代码）"""
        return self.client
    
    def start_price_monitor(self, symbol: str, on_price_update: Callable[[float], None]) -> bool:
        """启动价格监听（使用 WebSocket）"""
        try:
            if self._price_monitor_active:
                print(f"[{datetime.now().isoformat()}] ⚠️ [Binance] 价格监听已在运行")
                return True
            
            self._on_price_callback = on_price_update
            
            # 创建 WebSocket 管理器（如果还没有）
            if not self._ws_manager:
                if self.api_key and self.api_secret:
                    self._ws_manager = ThreadedWebsocketManager(api_key=self.api_key, api_secret=self.api_secret)
                else:
                    self._ws_manager = ThreadedWebsocketManager()
                self._ws_manager.start()
            
            # 定义内部回调函数
            def _on_ticker_msg(msg):
                try:
                    price = self.parse_ticker_message(msg)
                    if price is not None and self._on_price_callback:
                        self._on_price_callback(price)
                except Exception as e:
                    print(f"[{datetime.now().isoformat()}] ❌ [Binance] 价格回调错误: {e}")
            
            # 启动行情流
            self._ws_manager.start_symbol_ticker_socket(callback=_on_ticker_msg, symbol=symbol)
            self._price_monitor_active = True
            print(f"[{datetime.now().isoformat()}] ✅ [Binance] 价格监听已启动 ({symbol})")
            return True
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Binance] 启动价格监听失败: {e}")
            return False
    
    def stop_price_monitor(self) -> None:
        """停止价格监听"""
        self._price_monitor_active = False
        self._on_price_callback = None
        print(f"[{datetime.now().isoformat()}] ⏹️ [Binance] 价格监听已停止")
    
    def start_order_monitor(self, symbol: str, on_order_update: Callable[[Dict], None]) -> bool:
        """启动订单监听（使用 WebSocket）"""
        try:
            if self._order_monitor_active:
                print(f"[{datetime.now().isoformat()}] ⚠️ [Binance] 订单监听已在运行")
                return True
            
            if not self.api_key or not self.api_secret:
                print(f"[{datetime.now().isoformat()}] ⚠️ [Binance] 缺少 API 密钥，无法启动订单监听")
                return False
            
            self._on_order_callback = on_order_update
            
            # 创建 WebSocket 管理器（如果还没有）
            if not self._ws_manager:
                self._ws_manager = ThreadedWebsocketManager(api_key=self.api_key, api_secret=self.api_secret)
                self._ws_manager.start()
            
            # 定义内部回调函数（带交易对过滤）
            def _on_user_msg(msg):
                try:
                    # 🔒 关键修复：过滤交易对
                    msg_symbol = msg.get('s')  # 币安用户数据流中交易对字段为 's'
                    if msg_symbol and msg_symbol != symbol:
                        # 交易对不匹配，丢弃此消息
                        print(f"[{datetime.now().isoformat()}] 🔇 [Binance] 丢弃不匹配交易对的订单消息: {msg_symbol} (期望: {symbol})")
                        return
                    
                    event = self.parse_user_message(msg)
                    if event and self._on_order_callback:
                        self._on_order_callback(event)
                except Exception as e:
                    print(f"[{datetime.now().isoformat()}] ❌ [Binance] 订单回调错误: {e}")
            
            # 启动用户数据流
            try:
                self._ws_manager.start_user_socket(callback=_on_user_msg)
                self._order_monitor_active = True
                print(f"[{datetime.now().isoformat()}] ✅ [Binance] 订单监听已启动")
                return True
            except BinanceAPIException as e:
                print(f"[{datetime.now().isoformat()}] ❌ [Binance] 订单监听启动失败 (API错误): {e}")
                return False
                
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Binance] 启动订单监听失败: {e}")
            return False
    
    def stop_order_monitor(self) -> None:
        """停止订单监听"""
        self._order_monitor_active = False
        self._on_order_callback = None
        
        # 如果价格监听也停止了，关闭整个 WebSocket 管理器
        if not self._price_monitor_active and self._ws_manager:
            try:
                self._ws_manager.stop()
                self._ws_manager = None
                print(f"[{datetime.now().isoformat()}] ⏹️ [Binance] WebSocket 管理器已关闭")
            except Exception as e:
                print(f"[{datetime.now().isoformat()}] ⚠️ [Binance] 关闭 WebSocket 失败: {e}")
        
        print(f"[{datetime.now().isoformat()}] ⏹️ [Binance] 订单监听已停止")
    
    def check_pending_orders(self, pending_orders: List[Dict]):
        """检查待处理订单（Binance 使用 WebSocket，此方法返回空列表）"""
        # Binance 通过 WebSocket 实时推送订单更新，不需要轮询

