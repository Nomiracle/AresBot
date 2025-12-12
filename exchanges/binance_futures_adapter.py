# binance_futures_adapter.py - 币安合约适配器
from typing import Dict, List, Optional, Callable
from binance import ThreadedWebsocketManager
from binance.client import Client
from binance.exceptions import BinanceAPIException
from datetime import datetime
import time
import threading
import math

from .base import BaseExchange


class BinanceFuturesAdapter(BaseExchange):
    """币安合约交易适配器"""
    
    def __init__(self, api_key: str, api_secret: str, symbol: str, testnet: bool = True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.symbol = symbol.upper()
        self.testnet = testnet

        self.client = Client(api_key, api_secret, testnet=testnet)
        
        # WebSocket 管理器（实例变量）
        self.manager: Optional[ThreadedWebsocketManager] = None
        self.price_socket_id: Optional[str] = None
        self._user_socket_id: Optional[str] = None
        
        # 全局线程变量
        self._ws_thread: Optional[threading.Thread] = None
        self._ws_thread_running = False
        self._ws_thread_lock = threading.Lock()
        
        # 错误日志频率控制（2秒内同一错误只打印一次）
        self._error_log_cache: Dict[str, float] = {}
        self._error_log_interval = 2.0
        
        # 初始化锁
        self._init_lock = threading.Lock()
        
        # 重启重试计数
        self._retry_count = 0
        
        # ReadLoopClosed 错误处理锁
        self._order_restart_lock = threading.Lock()
        self._price_restart_lock = threading.Lock()
        
        # 账户费率缓存 (symbol -> {maker_fee, taker_fee})
        self._fee_cache: Dict[str, Dict[str, float]] = {}
        self._fee_cache_lock = threading.Lock()
        
        # 合约特有：缓存交易规则
        self._symbol_info_cache: Optional[Dict] = None
        
        self.get_fee_rate()

    def ping(self) -> bool:
        try:
            self.client.futures_ping()
            return True
        except BinanceAPIException as e:
            print(f"Error: {e}")
            return False

    def _get_log_prefix(self) -> str:
        """生成日志前缀"""
        api_key_short = self.api_key[:6] if self.api_key else "NOKEY"
        return f"[{datetime.now().isoformat()}] [binance-futures-{api_key_short}-{self.symbol}]"
    
    def _should_log_error(self, error_key: str) -> bool:
        """检查是否应该打印错误日志（频率控制）"""
        current_time = time.time()
        last_log_time = self._error_log_cache.get(error_key, 0)
        
        if current_time - last_log_time >= self._error_log_interval:
            self._error_log_cache[error_key] = current_time
            return True
        return False

    def _restart_ws_async(self, on_price_update: Callable, on_order_update: Callable) -> None:
        """在后台线程中重启 WebSocket 监控（避免线程安全问题）"""
        time.sleep(0.01)
        self._retry_count = self._retry_count + 1
        print(f"{self._get_log_prefix()} 🔄 WebSocket 监控重启 (第 {self._retry_count} 次)")
        self.stop_ws()
        self.start_ws(on_price_update, on_order_update)
        
        event = {'event_type': 'reconnected'}
        if on_order_update:
            try:
                on_order_update(event)
            except Exception as cb_e:
                print(f"{self._get_log_prefix()} ⚠️ 回调执行失败: {cb_e}")

    def get_symbol_info(self) -> Dict:
        """获取合约交易对信息"""
        if self._symbol_info_cache:
            return self._symbol_info_cache
            
        try:
            exchange_info = self.client.futures_exchange_info()
            for s in exchange_info.get('symbols', []):
                if s['symbol'] == self.symbol:
                    self._symbol_info_cache = s
                    return s
        except Exception as e:
            print(f"{self._get_log_prefix()} ⚠️ 获取合约交易对信息失败: {e}")
        return {}

    def get_symbol_ticker(self) -> Dict:
        """获取合约当前价格"""
        return self.client.futures_symbol_ticker(symbol=self.symbol)

    def get_open_orders(self) -> List[Dict]:
        """获取合约未完成订单"""
        return self.client.futures_get_open_orders(symbol=self.symbol)

    def get_order(self, order_id: str) -> Dict:
        """查询合约订单状态"""
        return self.client.futures_get_order(symbol=self.symbol, orderId=order_id)

    def order_limit_buy(self, quantity: float, price: str, **kwargs) -> Dict:
        """合约限价买单（做多开仓）"""
        return self.client.futures_create_order(
            symbol=self.symbol,
            side='BUY',
            type='LIMIT',
            quantity=quantity,
            price=price,
            timeInForce=kwargs.get('timeInForce', 'GTC')
        )

    def order_limit_sell(self, quantity: float, price: str, **kwargs) -> Dict:
        """合约限价卖单（做多平仓）"""
        return self.client.futures_create_order(
            symbol=self.symbol,
            side='SELL',
            type='LIMIT',
            quantity=quantity,
            price=price,
            timeInForce=kwargs.get('timeInForce', 'GTC')
        )

    def cancel_order(self, order_id: str) -> Dict:
        """取消合约订单"""
        return self.client.futures_cancel_order(symbol=self.symbol, orderId=order_id)

    def cancel_replace_order(self, side: str, order_type: str,
                             quantity: float, price: str, cancel_order_id: str, **kwargs) -> Dict:
        """取消并替换订单（合约无原子操作，拆分为取消+新建）"""
        time_in_force = kwargs.pop('timeInForce', 'GTC')
        
        # 先取消旧订单
        try:
            self.client.futures_cancel_order(symbol=self.symbol, orderId=cancel_order_id)
        except BinanceAPIException as e:
            # 订单可能已成交或已取消，忽略 -2011 错误
            if e.code != -2011:
                raise
        
        # 创建新订单
        new_order = self.client.futures_create_order(
            symbol=self.symbol,
            side=side,
            type=order_type,
            quantity=quantity,
            price=price,
            timeInForce=time_in_force
        )
        
        # 返回格式与现货 cancel_replace_order 兼容
        return {
            'cancelResult': 'SUCCESS',
            'newOrderResult': 'SUCCESS',
            'newOrderResponse': new_order
        }

    def get_price_precision(self, symbol_info: Dict) -> tuple:
        """从合约交易对信息中提取价格精度"""
        if not symbol_info or 'filters' not in symbol_info:
            return 0.0, 0
        for f in symbol_info['filters']:
            if f['filterType'] == 'PRICE_FILTER':
                tick = float(f['tickSize'])
                decimals = len(str(tick).split('.')[-1].rstrip('0'))
                return tick, decimals
        return 0.0, 0

    def get_quantity_precision(self, symbol_info: Dict) -> tuple:
        """从合约交易对信息中提取数量精度"""
        if not symbol_info or 'filters' not in symbol_info:
            return 0.0, 0
        for f in symbol_info['filters']:
            if f['filterType'] == 'LOT_SIZE':
                step = float(f['stepSize'])
                decimals = len(str(step).split('.')[-1].rstrip('0'))
                return step, decimals
        return 0.0, 0

    # ====================== WebSocket 监控 ======================
    def _start_ws_in_thread(self, on_price_update: Callable[[float], None], 
                           on_order_update: Callable[[Dict], None]) -> None:
        """在线程中启动合约 WebSocket 监听（价格和订单）"""

        def price_callback(msg):
            """解析合约行情消息"""
            try:
                if msg.get('e') == 'error':
                    error_key = f"price_error_{msg.get('type', 'unknown')}"
                    if self._should_log_error(error_key):
                        print(f"{self._get_log_prefix()} ❌ 价格 WebSocket 错误: {msg}")
                        if self._price_restart_lock.acquire(blocking=False):
                            try: 
                                self._restart_ws_async(on_price_update, on_order_update)
                            finally:
                                threading.Timer(0.5, self._price_restart_lock.release).start()
                    return

                # 合约 mark price 消息格式
                if msg.get('e') == 'markPriceUpdate':
                    price = float(msg.get('p', 0))
                    if price and on_price_update:
                        on_price_update(price)
                    return
                
                # 合约 ticker 消息格式
                price = msg.get('c')
                if price:
                    price = float(price)
                    if on_price_update:
                        on_price_update(price)
                else:
                    print(f"{self._get_log_prefix()} ⚠️ 消息中未找到价格字段: {list(msg.keys())}")
            except Exception as e:
                print(f"{self._get_log_prefix()} ❌ 解析价格失败: {e}")

        def user_data_callback(msg):
            """解析合约用户数据消息"""
            try:
                msg_type = msg.get('e', 'unknown')

                if msg_type == 'error':
                    error_key = f"user_error_{msg.get('type', 'unknown')}"
                    if self._should_log_error(error_key):
                        print(f"{self._get_log_prefix()} ❌ 合约用户数据 WebSocket 错误: {msg}")                    
                        if self._order_restart_lock.acquire(blocking=False):
                            try: 
                                self._restart_ws_async(on_price_update, on_order_update)
                            finally:
                                threading.Timer(0.5, self._order_restart_lock.release).start()
                    return

                # 合约订单更新事件: ORDER_TRADE_UPDATE
                if msg_type == 'ORDER_TRADE_UPDATE':
                    order_data = msg.get('o', {})
                    order_status = order_data.get('X')
                    order_id = str(order_data.get('i'))
                    print(f"{self._get_log_prefix()} 📨 收到订单事件: ID={order_id}, 状态={order_status}")

                    if order_status == 'FILLED':
                        event_type = 'order_filled'
                    elif order_status == 'CANCELED':
                        event_type = 'order_cancelled'
                    else:
                        event_type = 'order_update'

                    # 合约手续费从 USDT 扣除，不影响币种数量
                    fee_paid_externally = True
                    
                    event = {
                        'event_type': event_type,
                        'order_id': order_id,
                        'symbol': order_data.get('s'),
                        'side': order_data.get('S'),
                        'status': order_status,
                        'price': order_data.get('p'),
                        'quantity': order_data.get('q'),
                        'executedQty': order_data.get('z'),
                        'lastExecutedQty': order_data.get('l'),
                        'feePaidExternally': fee_paid_externally
                    }
                    
                    if on_order_update:
                        try:
                            on_order_update(event)
                        except Exception as cb_e:
                            print(f"{self._get_log_prefix()} ⚠️ 回调执行失败: {cb_e}")

            except Exception as e:
                print(f"{self._get_log_prefix()} ❌ 解析用户消息失败: {e}")

        try:
            self.manager = ThreadedWebsocketManager(
                api_key=self.api_key,
                api_secret=self.api_secret,
                testnet=self.testnet
            )
            self.manager.start()

            print(f"{self._get_log_prefix()} 🆕 启动合约 WebSocket 监控 (symbol: {self.symbol})")
            
            # 启动合约价格监控 (使用 symbol ticker)
            price_socket_id = self.manager.start_symbol_ticker_futures_socket(
                callback=price_callback,
                symbol=self.symbol
            )
            self.price_socket_id = price_socket_id
            print(f"{self._get_log_prefix()} ✅ 合约价格监控已启动 (socket_id: {price_socket_id})")
            
            # 启动合约用户数据监控
            order_socket_id = self.manager.start_futures_user_socket(callback=user_data_callback)
            self._user_socket_id = order_socket_id if order_socket_id else 'futures_user_stream'
            print(f"{self._get_log_prefix()} ✅ 合约订单监控已启动 (socket_id: {order_socket_id})")
            
            print(f"{self._get_log_prefix()} 🔄 WebSocket 监控线程进入运行循环...")
            loop_count = 0
            while self._ws_thread_running:
                time.sleep(1)
                loop_count += 1
                if loop_count % 30 == 0:
                    print(f"{self._get_log_prefix()} 💓 WebSocket 监控线程运行中 (已运行 {loop_count} 秒)")
            
            print(f"{self._get_log_prefix()} 🛑 WebSocket 监控线程收到停止信号,准备退出...")

        except BinanceAPIException as e:
            print(f"{self._get_log_prefix()} ❌ 启动 WebSocket 监控失败 [API错误]: {e}")
            self._ws_thread_running = False
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 启动 WebSocket 监控失败: {e}")
            import traceback
            traceback.print_exc()
            self._ws_thread_running = False

    def start_ws(self, on_price_update: Callable[[float], None], 
                 on_order_update: Callable[[Dict], None]) -> bool:
        """启动 WebSocket 监听（价格和订单）- 在独立线程中运行"""
        with self._ws_thread_lock:
            if self._ws_thread_running:
                print(f"{self._get_log_prefix()} ⚠️ WebSocket 线程已在运行，先停止...")
                self.stop_ws()
            
            self._ws_thread_running = True
            
            self._ws_thread = threading.Thread(
                target=self._start_ws_in_thread,
                args=(on_price_update, on_order_update),
                daemon=True,
                name=f"BinanceFuturesWS-{self.symbol}"
            )
            self._ws_thread.start()
            print(f"{self._get_log_prefix()} 🚀 WebSocket 监控线程已启动 (线程名: {self._ws_thread.name})")
            
            time.sleep(0.5)
            
            return True

    def stop_ws(self) -> None:
        """完全关闭 WebSocket 管理器和所有连接"""
        try:
            print(f"{self._get_log_prefix()} 🔌 开始清理 WebSocket 连接...")
            
            self._ws_thread_running = False
            if self._ws_thread and self._ws_thread.is_alive():
                print(f"{self._get_log_prefix()} 🛑 等待 WebSocket 线程停止...")
                self._ws_thread.join(timeout=3)
                if self._ws_thread.is_alive():
                    print(f"{self._get_log_prefix()} ⚠️ WebSocket 线程未能在3秒内停止")
                else:
                    print(f"{self._get_log_prefix()} ✅ WebSocket 线程已停止")
            self._ws_thread = None
            
            if self.manager:
                try:
                    if self.price_socket_id:
                        self.manager.stop_socket(self.price_socket_id)
                        print(f"{self._get_log_prefix()} ✅ 已停止价格 socket: {self.price_socket_id}")
                        self.price_socket_id = None
                except Exception as e:
                    print(f"{self._get_log_prefix()} ⚠️ 停止价格 socket 失败: {e}")
                
                try:
                    self.manager.stop_socket('futures_user_socket')
                    print(f"{self._get_log_prefix()} ✅ 已停止用户数据 socket")
                except Exception as e:
                    print(f"{self._get_log_prefix()} ⚠️ 停止用户数据 socket 失败: {e}")
                
                try:
                    print(f"{self._get_log_prefix()} 🛑 正在关闭 WebSocket 管理器...")
                    self.manager.stop()
                    self.manager = None
                    print(f"{self._get_log_prefix()} ✅ WebSocket 管理器已完全关闭")
                except Exception as e:
                    print(f"{self._get_log_prefix()} ⚠️ 关闭 WebSocket 管理器失败: {e}")
            
            print(f"{self._get_log_prefix()} ✅ 清理完成")
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 清理过程出错: {e}")
            import traceback
            traceback.print_exc()

    def check_pending_orders(self, pending_orders: List[Dict]):
        """检查待处理订单的状态（用于 HTTP 轮询模式）"""
        pass

    def _get_trade_fee(self, symbol: str) -> Dict[str, float]:
        """获取合约交易对的手续费率（带缓存）"""
        symbol = symbol.upper()
        
        with self._fee_cache_lock:
            if symbol in self._fee_cache:
                return self._fee_cache[symbol]
        
        try:
            # 合约默认费率: maker 0.02%, taker 0.04%
            maker_fee = 0.0002
            taker_fee = 0.0004
                
            fee_data = {'maker_fee': maker_fee, 'taker_fee': taker_fee}
            
            with self._fee_cache_lock:
                self._fee_cache[symbol] = fee_data
                
            print(f"{self._get_log_prefix()} 💰 获取 {symbol} 合约费率: maker={maker_fee*100}%, taker={taker_fee*100}%")
            return fee_data
            
        except Exception as e:
            print(f"{self._get_log_prefix()} ⚠️ 获取费率失败，使用默认值: {e}")
            return {'maker_fee': 0.0002, 'taker_fee': 0.0004}

    def calculate_sell_price(self, buy_price, sell_offset_percent, tick_size, price_decimals, current_price=None):
        """计算卖出价格（基于实际账户费率）"""
        sell_offset = sell_offset_percent / 100.0
        raw_sell_price = (current_price or buy_price) * (1 + sell_offset)
        
        fee_data = self._get_trade_fee(self.symbol)
        total_fee_rate = fee_data['maker_fee'] * 2
        
        min_price = buy_price * (1 + total_fee_rate)
        min_price = math.ceil(min_price / tick_size) * tick_size if tick_size else min_price
        min_price = round(min_price, price_decimals)
        
        sell_price = max(raw_sell_price, min_price)
        sell_price = math.ceil(sell_price / tick_size) * tick_size if tick_size else sell_price
        sell_price = round(sell_price, price_decimals)
        
        if sell_price <= buy_price and tick_size:
            sell_price = round(buy_price + tick_size, price_decimals)
        
        return sell_price

    def get_fee_rate(self) -> float:
        """获取交易对的手续费率（重写基类方法）"""
        fee_data = self._get_trade_fee(self.symbol)
        return fee_data['maker_fee']

    # ====================== 合约特有方法（可选使用） ======================
    def set_leverage(self, leverage: int) -> Dict:
        """设置杠杆倍数
        
        Args:
            leverage: 杠杆倍数 (1-125)
        """
        return self.client.futures_change_leverage(symbol=self.symbol, leverage=leverage)
    
    def set_margin_type(self, margin_type: str) -> Dict:
        """设置保证金模式
        
        Args:
            margin_type: 'ISOLATED' (逐仓) 或 'CROSSED' (全仓)
        """
        try:
            return self.client.futures_change_margin_type(symbol=self.symbol, marginType=margin_type)
        except BinanceAPIException as e:
            # -4046: 保证金类型无需更改
            if e.code == -4046:
                print(f"{self._get_log_prefix()} ℹ️ 保证金模式已是 {margin_type}")
                return {'msg': 'No need to change margin type'}
            raise
    
    def get_position(self) -> List[Dict]:
        """获取当前持仓"""
        positions = self.client.futures_position_information(symbol=self.symbol)
        return [p for p in positions if float(p.get('positionAmt', 0)) != 0]
    
    def get_account_balance(self) -> Dict:
        """获取合约账户余额"""
        balances = self.client.futures_account_balance()
        for b in balances:
            if b['asset'] == 'USDT':
                return {
                    'asset': 'USDT',
                    'balance': float(b['balance']),
                    'availableBalance': float(b['availableBalance'])
                }
        return {'asset': 'USDT', 'balance': 0, 'availableBalance': 0}
