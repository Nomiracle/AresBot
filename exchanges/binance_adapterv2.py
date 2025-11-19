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
        'active_sockets': set[str],  # 存放价格监控 socket_id
        'client': Client,  # 用于创建 listenKey
        'user_socket_id': Optional[str],  # 用户数据流 socket_id（全局唯一）
        'order_callbacks': List[Callable]  # 订单回调列表
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
                'client': self.client,
                'user_socket_id': None,
                'order_callbacks': []
            }

        cache_entry = _MANAGER_CACHE[self.key]
        self.manager: ThreadedWebsocketManager = cache_entry['manager']
        self.active_sockets: set = cache_entry['active_sockets']
        self.cache_client: Client = cache_entry['client']  # 复用同一个 client

        # 当前实例持有的 socket id（用于单独 stop）
        self.price_socket_id: Optional[str] = None
        self._order_callback: Optional[Callable] = None  # 当前实例的订单回调

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
        self._current_symbol = symbol.upper()  # 更新当前交易对（日志用）
        symbol = symbol.lower()  # WebSocket 流名称必须小写（如 zecusdt@ticker）

        def callback(msg):
            """解析币安行情消息"""
            print(f"{self._get_log_prefix()} 🔍 价格回调收到消息: {msg}")
            
            if msg.get('e') == 'error':
                print(f"{self._get_log_prefix()} ❌ 价格 WebSocket 错误: {msg}")
                return
            
            try:
                # 尝试多个可能的价格字段
                price = msg.get('c') or msg.get('p') or msg.get('price')
                if price is None:
                    print(f"{self._get_log_prefix()} ⚠️ 消息中未找到价格字段: {msg}")
                    return
                
                price = float(price)
                print(f"{self._get_log_prefix()} 💰 价格更新: {price}")
                on_price_update(price)
            except Exception as e:
                print(f"{self._get_log_prefix()} ❌ 解析价格失败: {e}, 消息: {msg}")

        try:
            print(f"{self._get_log_prefix()} 🆕 启动价格监控 (symbol: {symbol})")
            socket_id = self.manager.start_symbol_ticker_socket(
                callback=callback,
                symbol=symbol
            )
            self.price_socket_id = socket_id
            self.active_sockets.add(socket_id)
            print(f"{self._get_log_prefix()} ✅ 价格监控已启动 (socket_id: {socket_id})")
            return True
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 启动价格监控失败: {e}")
            import traceback
            traceback.print_exc()
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
        cache_entry = _MANAGER_CACHE[self.key]
        
        try:
            # 保存当前实例的回调
            self._order_callback = on_order_update
            
            # 检查是否已有用户数据流订阅
            if cache_entry['user_socket_id'] is not None:
                # 复用现有订阅，只需注册回调
                print(f"{self._get_log_prefix()} ♻️ 复用现有用户数据流订阅")
                cache_entry['order_callbacks'].append(on_order_update)
                return True
            
            # 创建新的用户数据流订阅
            print(f"{self._get_log_prefix()} 🆕 创建新的用户数据流订阅")
            
            def user_data_callback(msg):
                """解析币安用户数据消息并分发给所有回调"""
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
                        
                        # 分发给所有注册的回调
                        for callback in cache_entry['order_callbacks']:
                            try:
                                callback(event)
                            except Exception as cb_e:
                                print(f"{self._get_log_prefix()} ⚠️ 回调执行失败: {cb_e}")

                except Exception as e:
                    print(f"{self._get_log_prefix()} ❌ 解析用户消息失败: {e}")

            socket_id = self.manager.start_user_socket(callback=user_data_callback)
            cache_entry['user_socket_id'] = socket_id if socket_id else 'user_stream'
            cache_entry['order_callbacks'].append(on_order_update)
            print(f"{self._get_log_prefix()} ✅ 用户数据流订阅成功 (socket_id: {socket_id})")
            return True

        except BinanceAPIException as e:
            print(f"{self._get_log_prefix()} ❌ 启动订单监控失败 [API错误]: {e}")
            return False
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 启动订单监控失败: {e}")
            return False

    def stop_order_monitor(self) -> None:
        cache_entry = _MANAGER_CACHE[self.key]
        
        # 从回调列表中移除当前实例的回调
        if self._order_callback and self._order_callback in cache_entry['order_callbacks']:
            cache_entry['order_callbacks'].remove(self._order_callback)
            print(f"{self._get_log_prefix()} ✅ 已移除订单回调")
        
        # 如果没有剩余回调，关闭用户数据流
        if not cache_entry['order_callbacks'] and cache_entry['user_socket_id']:
            try:
                self.manager.stop_socket(cache_entry['user_socket_id'])
                cache_entry['user_socket_id'] = None
                print(f"{self._get_log_prefix()} ✅ 已关闭用户数据流")
            except Exception as e:
                print(f"{self._get_log_prefix()} ⚠️ 关闭用户数据流失败: {e}")
        
        self._order_callback = None

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