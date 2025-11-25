# binance_adapterv2.py - 简化版本
from typing import Dict, List, Optional, Callable
from binance import ThreadedWebsocketManager
from binance.client import Client
from binance.exceptions import BinanceAPIException
from datetime import datetime
import time
import threading

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
        self._price_callback: Optional[Callable] = None
        self._order_callback: Optional[Callable] = None
        self._user_socket_id: Optional[str] = None
        
        # 错误日志频率控制（2秒内同一错误只打印一次）
        self._error_log_cache: Dict[str, float] = {}
        self._error_log_interval = 2.0
        
        # 初始化锁
        self._init_lock = threading.Lock()
        
        # 重启重试计数
        self._price_retry_count = 0
        self._order_retry_count = 0
        self._max_retries = 3
        
        # 保存启动监控的线程
        self._price_monitor_thread: Optional[threading.Thread] = None
        self._order_monitor_thread: Optional[threading.Thread] = None
        
        # ReadLoopClosed 错误处理锁
        self._price_restart_lock = threading.Lock()
        self._order_restart_lock = threading.Lock()

    def _init_manager(self):
        """初始化 WebSocket 管理器"""
        with self._init_lock:
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
        except BinanceAPIException as e:
            print(f"Error: {e}")
            return False

    def _get_log_prefix(self) -> str:
        """生成日志前缀"""
        api_key_short = self.api_key[:6] if self.api_key else "NOKEY"
        return f"[{datetime.now().isoformat()}] [binance-{api_key_short}-{self._current_symbol}]"
    
    def _should_log_error(self, error_key: str) -> bool:
        """检查是否应该打印错误日志（频率控制）"""
        current_time = time.time()
        last_log_time = self._error_log_cache.get(error_key, 0)
        
        if current_time - last_log_time >= self._error_log_interval:
            self._error_log_cache[error_key] = current_time
            return True
        return False

    def _restart_price_monitor_async(self, symbol: str, on_price_update: Callable) -> None:
        """在后台线程中重启价格监控（避免线程安全问题）"""
        if self._price_retry_count < self._max_retries:
            self._price_retry_count += 1
            time.sleep(1)
            print(f"{self._get_log_prefix()} 🔄 价格监控重启 (第 {self._price_retry_count}/{self._max_retries} 次)")
            self.stop_price_monitor()
            self.start_price_monitor(symbol, on_price_update)
        else:
            print(f"{self._get_log_prefix()} ❌ 价格监控重试次数已达上限 ({self._max_retries})")

    def _restart_order_monitor_async(self, symbol: str, on_order_update: Callable) -> None:
        """在后台线程中重启订单监控（避免线程安全问题）"""
        if self._order_retry_count < self._max_retries:
            self._order_retry_count += 1
            time.sleep(1)
            print(f"{self._get_log_prefix()} 🔄 订单监控重启 (第 {self._order_retry_count}/{self._max_retries} 次)")
            self.stop_order_monitor()
            self.start_order_monitor(symbol, on_order_update)
        else:
            print(f"{self._get_log_prefix()} ❌ 订单监控重试次数已达上限 ({self._max_retries})")

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
        self._price_callback = on_price_update
        self._price_monitor_thread = threading.current_thread()

        def callback(msg):
            """解析币安行情消息"""

            
            if msg.get('e') == 'error':
                error_key = f"price_error_{msg.get('type', 'unknown')}"
                if self._should_log_error(error_key):
                    print(f"{self._get_log_prefix()} ❌ 价格 WebSocket 错误: {msg}")
                if msg.get('type') == 'ReadLoopClosed':
                    # 使用锁防止毫秒级别的多次回调同时触发重启
                    if self._price_restart_lock.acquire(blocking=False):
                        try:
                            print(f"{self._get_log_prefix()} 🔧 [DEBUG] 检测到 ReadLoopClosed 错误，准备重启价格监控")
                            print(f"{self._get_log_prefix()} 🔧 [DEBUG] 保存的线程: {self._price_monitor_thread}")
                            print(f"{self._get_log_prefix()} 🔧 [DEBUG] 线程存活状态: {self._price_monitor_thread.is_alive() if self._price_monitor_thread else 'None'}")
                            print(f"{self._get_log_prefix()} 🔧 [DEBUG] 当前重试次数: {self._price_retry_count}/{self._max_retries}")
                            
                            if self._price_monitor_thread and self._price_monitor_thread.is_alive():
                                # 使用保存的线程执行重启
                                print(f"{self._get_log_prefix()} 🔧 [DEBUG] 使用保存的线程引用创建新重启线程")
                                self._price_monitor_thread = threading.Thread(
                                    target=self._restart_price_monitor_async,
                                    args=(symbol, on_price_update),
                                    daemon=True
                                )
                                self._price_monitor_thread.start()
                                print(f"{self._get_log_prefix()} 🔧 [DEBUG] 新线程已启动: {self._price_monitor_thread}")
                            else:
                                # 如果保存的线程不存在或已结束，创建新线程
                                print(f"{self._get_log_prefix()} 🔧 [DEBUG] 保存的线程不存在或已结束，创建新线程")
                                new_thread = threading.Thread(
                                    target=self._restart_price_monitor_async,
                                    args=(symbol, on_price_update),
                                    daemon=True
                                )
                                new_thread.start()
                                print(f"{self._get_log_prefix()} 🔧 [DEBUG] 新线程已启动: {new_thread}")
                        finally:
                            # 延迟释放锁，防止毫秒级的重复触发
                            threading.Timer(0.5, self._price_restart_lock.release).start()
                    else:
                        print(f"{self._get_log_prefix()} 🔧 [DEBUG] ReadLoopClosed 错误处理正在进行中，跳过本次触发")
                return
            
            print(f"{self._get_log_prefix()} 🔍 价格回调收到消息: {msg}")
            
            try:
                price = msg.get('c')
                if price:
                    price = float(price)
                    print(f"{self._get_log_prefix()} 💰 价格更新: {price}")
                    if self._price_callback:
                        self._price_callback(price)
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
        if self.manager:
            try:
                self.manager.stop_socket('symbol_ticker_socket')
                print(f"{self._get_log_prefix()} ✅ 已关闭 symbol_ticker_socket 数据流")
            except Exception as e:
                print(f"{self._get_log_prefix()} ⚠️ 关闭 symbol_ticker_socket 流失败: {e}")
        self._price_callback = None

    # ====================== WebSocket 用户订单流 ======================
    def start_order_monitor(self, symbol: str, on_order_update: Callable[[Dict], None]) -> bool:
        self._current_symbol = symbol.upper()
        self._init_manager()
        self._order_monitor_thread = threading.current_thread()
        
        try:
            self._order_callback = on_order_update
            
            print(f"{self._get_log_prefix()} 🆕 创建新的用户数据流订阅")
            
            def user_data_callback(msg):
                """解析币安用户数据消息"""
                try:
                    msg_type = msg.get('e', 'unknown')
                    print(f"{self._get_log_prefix()} 🔍 收到用户消息类型: {msg_type}")

                    if msg_type == 'error':
                        error_key = f"user_error_{msg.get('type', 'unknown')}"
                        if self._should_log_error(error_key):
                            print(f"{self._get_log_prefix()} ❌ WebSocket错误: {msg}")

                        if msg.get('type') == 'ReadLoopClosed':
                            # 使用锁防止毫秒级别的多次回调同时触发重启
                            if self._order_restart_lock.acquire(blocking=False):
                                try:
                                    print(f"{self._get_log_prefix()} 🔧 [DEBUG] 检测到 ReadLoopClosed 错误，准备重启订单监控")
                                    print(f"{self._get_log_prefix()} 🔧 [DEBUG] 保存的线程: {self._order_monitor_thread}")
                                    print(f"{self._get_log_prefix()} 🔧 [DEBUG] 线程存活状态: {self._order_monitor_thread.is_alive() if self._order_monitor_thread else 'None'}")
                                    print(f"{self._get_log_prefix()} 🔧 [DEBUG] 当前重试次数: {self._order_retry_count}/{self._max_retries}")
                                    
                                    if self._order_monitor_thread and self._order_monitor_thread.is_alive():
                                        # 使用保存的线程执行重启
                                        print(f"{self._get_log_prefix()} 🔧 [DEBUG] 使用保存的线程引用创建新重启线程")
                                        self._order_monitor_thread = threading.Thread(
                                            target=self._restart_order_monitor_async,
                                            args=(symbol, on_order_update),
                                            daemon=True
                                        )
                                        self._order_monitor_thread.start()
                                        print(f"{self._get_log_prefix()} 🔧 [DEBUG] 新线程已启动: {self._order_monitor_thread}")
                                    else:
                                        # 如果保存的线程不存在或已结束，创建新线程
                                        print(f"{self._get_log_prefix()} 🔧 [DEBUG] 保存的线程不存在或已结束，创建新线程")
                                        new_thread = threading.Thread(
                                            target=self._restart_order_monitor_async,
                                            args=(symbol, on_order_update),
                                            daemon=True
                                        )
                                        new_thread.start()
                                        print(f"{self._get_log_prefix()} 🔧 [DEBUG] 新线程已启动: {new_thread}")
                                finally:
                                    # 延迟释放锁，防止毫秒级的重复触发
                                    threading.Timer(0.5, self._order_restart_lock.release).start()
                            else:
                                print(f"{self._get_log_prefix()} 🔧 [DEBUG] ReadLoopClosed 错误处理正在进行中，跳过本次触发")
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
                        
                        # 执行回调
                        if self._order_callback:
                            try:
                                self._order_callback(event)
                            except Exception as cb_e:
                                print(f"{self._get_log_prefix()} ⚠️ 回调执行失败: {cb_e}")

                except Exception as e:
                    print(f"{self._get_log_prefix()} ❌ 解析用户消息失败: {e}")

            socket_id = self.manager.start_user_socket(callback=user_data_callback)
            self._user_socket_id = socket_id if socket_id else 'user_stream'
            print(f"{self._get_log_prefix()} ✅ 用户数据流订阅成功 (socket_id: {socket_id})")
            return True

        except BinanceAPIException as e:
            print(f"{self._get_log_prefix()} ❌ 启动订单监控失败 [API错误]: {e}")
            return False
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 启动订单监控失败: {e}")
            return False

    def stop_order_monitor(self) -> None:
        try:
            if self.manager:
                self.manager.stop_socket('user_socket')
            print(f"{self._get_log_prefix()} ✅ 已关闭用户数据流")
        except Exception as e:
            print(f"{self._get_log_prefix()} ⚠️ 关闭用户数据流失败: {e}")
        self._order_callback = None


