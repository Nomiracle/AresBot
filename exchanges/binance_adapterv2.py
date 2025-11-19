# binance_adapterv2.py - 简化版本
from typing import Dict, List, Optional, Callable
from binance import ThreadedWebsocketManager
from binance.client import Client
from binance.exceptions import BinanceAPIException
from datetime import datetime

from .base import BaseExchange


class BinanceAdapter(BaseExchange):
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self._current_symbol = "UNKNOWN"

        self.client = Client(api_key, api_secret, testnet=testnet)
        
        # WebSocket 管理器（实例变量）
        self.manager: Optional[ThreadedWebsocketManager] = None
        self.price_socket_id: Optional[str] = None
        self._order_callback: Optional[Callable] = None
        self._order_callbacks: List[Callable] = []
        self._user_socket_id: Optional[str] = None

    def _init_manager(self):
        """初始化 WebSocket 管理器"""
        if self.manager is None:
            self.manager = ThreadedWebsocketManager(
                api_key=self.api_key,
                api_secret=self.api_secret,
                testnet=self.testnet
            )
            self.manager.start()

    def ping(self) -> bool:
        try:
            self.client.ping()
            return True
        except:
            return False

    def _get_log_prefix(self) -> str:
        """生成日志前缀"""
        api_key_short = self.api_key[:6] if self.api_key else "NOKEY"
        return f"[{datetime.now().isoformat()}] [binance-{api_key_short}-{self._current_symbol}]"

    def get_symbol_info(self, symbol: str) -> Dict:
        info = self.client.get_symbol_info(symbol.upper())
        return info or {}

    def get_symbol_ticker(self, symbol: str) -> Dict:
        return self.client.get_symbol_ticker(symbol=symbol.upper())

    def get_open_orders(self, symbol: str) -> List[Dict]:
        return self.client.get_open_orders(symbol=symbol.upper())

    def get_order(self, symbol: str, order_id: str) -> Dict:
        return self.client.get_order(symbol=symbol.upper(), orderId=order_id)

    def order_limit_buy(self, symbol: str, quantity: float, price: str, **kwargs) -> Dict:
        return self.client.order_limit_buy(
            symbol=symbol.upper(),
            quantity=quantity,
            price=price,
            timeInForce=kwargs.get('timeInForce', 'GTC')
        )

    def order_limit_sell(self, symbol: str, quantity: float, price: str, **kwargs) -> Dict:
        return self.client.order_limit_sell(
            symbol=symbol.upper(),
            quantity=quantity,
            price=price,
            timeInForce=kwargs.get('timeInForce', 'GTC')
        )

    def cancel_order(self, symbol: str, order_id: str) -> Dict:
        return self.client.cancel_order(symbol=symbol.upper(), orderId=order_id)

    def cancel_replace_order(self, symbol: str, side: str, order_type: str,
                             quantity: float, price: str, cancel_order_id: str, **kwargs) -> Dict:
        # 提取并移除已处理的参数，避免重复传入
        time_in_force = kwargs.pop('timeInForce', 'GTC')
        cancel_replace_mode = kwargs.pop('cancelReplaceMode', 'STOP_ON_FAILURE')
        
        return self.client.cancel_replace_order(
            symbol=symbol.upper(),
            side=side,
            type=order_type,
            quantity=quantity,
            price=price,
            cancelOrderId=cancel_order_id,
            timeInForce=time_in_force,
            cancelReplaceMode=cancel_replace_mode
        )

    def get_price_precision(self, symbol_info: Dict) -> tuple:
        if not symbol_info or 'filters' not in symbol_info:
            return 0.0, 0
        for f in symbol_info['filters']:
            if f['filterType'] == 'PRICE_FILTER':
                tick = float(f['tickSize'])
                decimals = len(str(tick).split('.')[-1].rstrip('0'))
                return tick, decimals
        return 0.0, 0

    def get_quantity_precision(self, symbol_info: Dict) -> tuple:
        if not symbol_info or 'filters' not in symbol_info:
            return 0.0, 0
        for f in symbol_info['filters']:
            if f['filterType'] == 'LOT_SIZE':
                step = float(f['stepSize'])
                decimals = len(str(step).split('.')[-1].rstrip('0'))
                return step, decimals
        return 0.0, 0

    # ====================== WebSocket 价格监控 ======================
    def start_price_monitor(self, symbol: str, on_price_update: Callable[[float], None]) -> bool:
        self._current_symbol = symbol.upper()
        self._init_manager()

        def callback(msg):
            """解析币安行情消息"""
            print(f"{self._get_log_prefix()} 🔍 价格回调收到消息: {msg}")
            
            if msg.get('e') == 'error':
                print(f"{self._get_log_prefix()} ❌ 价格 WebSocket 错误: {msg}")
                return
            
            try:
                price = msg.get('c')
                if price:
                    price = float(price)
                    print(f"{self._get_log_prefix()} 💰 价格更新: {price}")
                    on_price_update(price)
                else:
                    print(f"{self._get_log_prefix()} ⚠️ 消息中未找到价格字段: {list(msg.keys())}")
            except Exception as e:
                print(f"{self._get_log_prefix()} ❌ 解析价格失败: {e}")

        try:
            print(f"{self._get_log_prefix()} 🆕 启动价格监控 (symbol: {symbol})")
            socket_id = self.manager.start_symbol_ticker_socket(
                callback=callback,
                symbol=symbol
            )
            self.price_socket_id = socket_id
            print(f"{self._get_log_prefix()} ✅ 价格监控已启动 (socket_id: {socket_id})")
            return True
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 启动价格监控失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def stop_price_monitor(self) -> None:
        if self.price_socket_id and self.manager:
            try:
                self.manager.stop_socket(self.price_socket_id)
            except:
                pass
            self.price_socket_id = None

    # ====================== WebSocket 用户订单流 ======================
    def start_order_monitor(self, symbol: str, on_order_update: Callable[[Dict], None]) -> bool:
        self._current_symbol = symbol.upper()
        self._init_manager()
        
        try:
            self._order_callback = on_order_update
            
            # 如果已有用户数据流，直接添加回调
            if self._user_socket_id is not None:
                print(f"{self._get_log_prefix()} ♻️ 复用现有用户数据流订阅")
                self._order_callbacks.append(on_order_update)
                return True
            
            print(f"{self._get_log_prefix()} 🆕 创建新的用户数据流订阅")
            
            def user_data_callback(msg):
                """解析币安用户数据消息"""
                try:
                    msg_type = msg.get('e', 'unknown')
                    print(f"{self._get_log_prefix()} 🔍 收到用户消息类型: {msg_type}")

                    if msg_type == 'error':
                        print(f"{self._get_log_prefix()} ❌ WebSocket错误: {msg}")
                        return

                    if msg_type == 'executionReport':
                        order_status = msg.get('X')
                        order_id = str(msg.get('i'))
                        print(f"{self._get_log_prefix()} 📨 收到订单事件: ID={order_id}, 状态={order_status}")

                        if order_status == 'FILLED':
                            event_type = 'order_filled'
                        elif order_status == 'CANCELED':
                            event_type = 'order_cancelled'
                        else:
                            event_type = 'order_update'

                        event = {
                            'event_type': event_type,
                            'order_id': order_id,
                            'symbol': msg.get('s'),
                            'side': msg.get('S'),
                            'status': order_status,
                            'price': msg.get('p'),
                            'quantity': msg.get('q'),
                            'executedQty': msg.get('z'),
                            'lastExecutedQty': msg.get('l')
                        }
                        
                        # 分发给所有回调
                        for callback in self._order_callbacks:
                            try:
                                callback(event)
                            except Exception as cb_e:
                                print(f"{self._get_log_prefix()} ⚠️ 回调执行失败: {cb_e}")

                except Exception as e:
                    print(f"{self._get_log_prefix()} ❌ 解析用户消息失败: {e}")

            socket_id = self.manager.start_user_socket(callback=user_data_callback)
            self._user_socket_id = socket_id if socket_id else 'user_stream'
            self._order_callbacks.append(on_order_update)
            print(f"{self._get_log_prefix()} ✅ 用户数据流订阅成功 (socket_id: {socket_id})")
            return True

        except BinanceAPIException as e:
            print(f"{self._get_log_prefix()} ❌ 启动订单监控失败 [API错误]: {e}")
            return False
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 启动订单监控失败: {e}")
            return False

    def stop_order_monitor(self) -> None:
        if self._order_callback and self._order_callback in self._order_callbacks:
            self._order_callbacks.remove(self._order_callback)
            print(f"{self._get_log_prefix()} ✅ 已移除订单回调")
        
        if not self._order_callbacks and self._user_socket_id and self.manager:
            try:
                if self._user_socket_id != 'user_stream':
                    self.manager.stop_socket(self._user_socket_id)
                self._user_socket_id = None
                print(f"{self._get_log_prefix()} ✅ 已关闭用户数据流")
            except Exception as e:
                print(f"{self._get_log_prefix()} ⚠️ 关闭用户数据流失败: {e}")
        
        self._order_callback = None

    def check_pending_orders(self, pending_orders: List[Dict]):
        """HTTP 轮询 fallback"""
        for order in pending_orders:
            symbol = order['symbol']
            order_id = order['order_id']
            try:
                info = self.get_order(symbol, order_id)
            except:
                pass

    @staticmethod
    def shutdown_all():
        """清理所有 manager"""
        pass
