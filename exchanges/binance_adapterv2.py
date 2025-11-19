# binance_adapterv2.py
import hashlib
from typing import Dict, List, Optional, Callable, Any
from binance import ThreadedWebsocketManager
from binance.client import Client
from binance.exceptions import BinanceAPIException
import time
import json
from datetime import datetime

from .base import BaseExchange

# 全局缓存：避免重复创建 ThreadedWebsocketManager 实例
_MANAGER_CACHE: Dict[str, Dict[str, Any]] = {}
"""
{
    hash_key: {
        'manager': ThreadedWebsocketManager,
        'active_sockets': set[str],  # 存放 start_user_stream 返回的 socket_id
        'client': Client  # 用于创建 listenKey
    }
}
"""


def _get_manager_key(api_key: str, api_secret: str, testnet: bool) -> str:
    """生成全局唯一的 manager 标识"""
    raw = f"{api_key}|{api_secret}|{testnet}"
    return hashlib.md5(raw.encode()).hexdigest()


class BinanceAdapter(BaseExchange):
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self._current_symbol = "UNKNOWN"  # 当前交易对，用于日志

        self.client = Client(api_key, api_secret, testnet=testnet)
        self.key = _get_manager_key(api_key, api_secret, testnet)

        if self.key not in _MANAGER_CACHE:
            manager = ThreadedWebsocketManager(
                api_key=api_key,
                api_secret=api_secret,
                testnet=testnet
            )
            manager.start()
            _MANAGER_CACHE[self.key] = {
                'manager': manager,
                'active_sockets': set(),
                'client': self.client
            }

        cache_entry = _MANAGER_CACHE[self.key]
        self.manager: ThreadedWebsocketManager = cache_entry['manager']
        self.active_sockets: set = cache_entry['active_sockets']
        self.cache_client: Client = cache_entry['client']  # 复用同一个 client

        # 当前实例持有的 socket id（用于单独 stop）
        self.price_socket_id: Optional[str] = None
        self.order_socket_id: Optional[str] = None

    def ping(self) -> bool:
        try:
            self.client.ping()
            return True
        except:
            return False

    def _get_log_prefix(self) -> str:
        """生成日志前缀：[交易对-API_KEY前6位]"""
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
        return self.client.cancel_replace_order(
            symbol=symbol.upper(),
            side=side,
            type=order_type,
            quantity=quantity,
            price=price,
            cancelOrderId=cancel_order_id,
            **kwargs
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
        self._current_symbol = symbol.upper()  # 更新当前交易对
        symbol = symbol.lower()

        def callback(msg):
            """解析币安行情消息"""
            if msg.get('e') == 'error':
                print(f"{self._get_log_prefix()} ❌ 价格 WebSocket 错误: {msg}")
                return
            price = float(msg['c'])  # 最新成交价
            on_price_update(price)

        try:
            socket_id = self.manager.start_symbol_ticker_socket(
                callback=callback,
                symbol=symbol
            )
            self.price_socket_id = socket_id
            self.active_sockets.add(socket_id)
            return True
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 启动价格监控失败: {e}")
            return False

    def stop_price_monitor(self) -> None:
        if self.price_socket_id and self.price_socket_id in self.active_sockets:
            try:
                self.manager.stop_socket(self.price_socket_id)
            except:
                pass
            self.active_sockets.discard(self.price_socket_id)
            self.price_socket_id = None

    # ====================== WebSocket 用户订单流 ======================
    def start_order_monitor(self, symbol: str, on_order_update: Callable[[Dict], None]) -> bool:
        self._current_symbol = symbol.upper()  # 更新当前交易对
        try:
            # 创建 listenKey（用户数据流）
            listen_key = self.cache_client.stream_get_listen_key()
            stream_name = f"{listen_key}"

            def user_data_callback(msg):
                """解析币安用户数据消息"""
                try:
                    # 🔍 调试：记录所有收到的消息类型
                    msg_type = msg.get('e', 'unknown')
                    print(f"{self._get_log_prefix()} 🔍 收到用户消息类型: {msg_type}")

                    # 错误消息
                    if msg.get('e') == 'error':
                        print(f"{self._get_log_prefix()} ❌ WebSocket错误: {msg.get('type')}: {msg.get('m')}")
                        return

                    # 订单更新（executionReport）
                    if msg.get('e') == 'executionReport':
                        order_status = msg.get('X')  # NEW/PARTIALLY_FILLED/FILLED/CANCELED...
                        order_id = str(msg.get('i'))

                        # 🔍 调试日志：记录所有订单事件
                        print(f"{self._get_log_prefix()} 📨 收到订单事件: ID={order_id}, 状态={order_status}, 方向={msg.get('S')}")

                        # 根据订单状态确定事件类型
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
                            'side': msg.get('S'),  # BUY/SELL
                            'status': order_status,
                            'price': msg.get('p'),  # 订单价格
                            'quantity': msg.get('q'),  # 订单数量
                            'executedQty': msg.get('z'),  # 累计成交数量（重要：用于计算卖单数量）
                            'lastExecutedQty': msg.get('l')  # 本次成交数量
                        }
                        on_order_update(event)

                except Exception as e:
                    print(f"{self._get_log_prefix()} ❌ 解析用户消息失败: {e}")

            socket_id = self.manager.start_user_socket(callback=user_data_callback)
            self.order_socket_id = socket_id
            self.active_sockets.add(socket_id)

            # 保持 listenKey 活跃（每30分钟续期一次）
            def keep_alive():
                while self.order_socket_id in self.active_sockets:
                    try:
                        self.cache_client.stream_keepalive(listen_key)
                    except:
                        pass
                    time.sleep(1800)  # 30分钟

            import threading
            threading.Thread(target=keep_alive, daemon=True).start()
            return True

        except BinanceAPIException as e:
            print(f"{self._get_log_prefix()} ❌ 启动订单监控失败 [API错误]: {e}")
            return False
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 启动订单监控失败: {e}")
            return False

    def stop_order_monitor(self) -> None:
        if self.order_socket_id and self.order_socket_id in self.active_sockets:
            try:
                self.manager.stop_socket(self.order_socket_id)
            except:
                pass
            self.active_sockets.discard(self.order_socket_id)
            self.order_socket_id = None

            # 可选：关闭 listenKey
            try:
                self.cache_client.stream_close(self.cache_client.stream_get_listen_key())
            except:
                pass

    def check_pending_orders(self, pending_orders: List[Dict]):
        """HTTP 轮询 fallback（某些场景下可能使用）"""
        for order in pending_orders:
            symbol = order['symbol']
            order_id = order['order_id']
            try:
                info = self.get_order(symbol, order_id)
                # 这里可以触发回调或更新本地状态
                pass
            except:
                pass

    # 可选：程序退出时清理所有 manager
    @staticmethod
    def shutdown_all():
        for entry in _MANAGER_CACHE.values():
            manager: ThreadedWebsocketManager = entry['manager']
            for sock_id in list(entry['active_sockets']):
                try:
                    manager.stop_socket(sock_id)
                except:
                    pass
            manager.stop()
        _MANAGER_CACHE.clear()