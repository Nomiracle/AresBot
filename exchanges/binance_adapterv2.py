# binance_adapterv2.py - 简化版本
from typing import Dict, List, Optional, Callable
from binance import AsyncClient, BinanceSocketManager
from binance.client import Client
from binance.exceptions import BinanceAPIException
from datetime import datetime
import time
import threading
import math
import asyncio

from .base import BaseExchange


class NativeBinanceSpot(BaseExchange):
    def __init__(self, api_key: str, api_secret: str, symbol: str, testnet: bool = True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.symbol = symbol.upper()
        self.testnet = testnet

        self.client = Client(api_key, api_secret, testnet=testnet)
        
        # WebSocket 管理器（实例变量）
        self.async_client: Optional[AsyncClient] = None
        self.manager: Optional[BinanceSocketManager] = None
        self.price_socket_id: Optional[str] = None
        self._user_socket_id: Optional[str] = None
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        
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
        self.get_fee_rate()

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
        return f"[{datetime.now().isoformat()}] [binance-{api_key_short}-{self.symbol}]"
    
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
        
        event = {'event_type': 'reconnected', 'symbol': self.symbol}
        # 执行回调
        if on_order_update:
            try:
                on_order_update(event)
            except Exception as cb_e:
                print(f"{self._get_log_prefix()} ⚠️ 回调执行失败: {cb_e}")




    def _get_symbol_info(self) -> Dict:
        """获取交易对信息（内部使用）"""
        info = self.client.get_symbol_info(self.symbol)
        return info or {}

    def get_symbol_ticker(self) -> Dict:
        return self.client.get_symbol_ticker(symbol=self.symbol)

    def get_open_orders(self) -> List[Dict]:
        return self.client.get_open_orders(symbol=self.symbol)

    def get_order(self, order_id: str) -> Dict:
        return self.client.get_order(symbol=self.symbol, orderId=order_id)

    def order_limit_buy(self, quantity: float, price: str, **kwargs) -> Dict:
        return self.client.order_limit_buy(
            symbol=self.symbol,
            quantity=quantity,
            price=price,
            timeInForce=kwargs.get('timeInForce', 'GTC')
        )

    def order_limit_sell(self, quantity: float, price: str, **kwargs) -> Dict:
        return self.client.order_limit_sell(
            symbol=self.symbol,
            quantity=quantity,
            price=price,
            timeInForce=kwargs.get('timeInForce', 'GTC')
        )

    def cancel_order(self, order_id: str) -> Dict:
        return self.client.cancel_order(symbol=self.symbol, orderId=order_id)

    def cancel_replace_order(self, side: str, order_type: str,
                             quantity: float, price: str, cancel_order_id: str, **kwargs) -> Dict:
        # 提取并移除已处理的参数，避免重复传入
        time_in_force = kwargs.pop('timeInForce', 'GTC')
        cancel_replace_mode = kwargs.pop('cancelReplaceMode', 'STOP_ON_FAILURE')
        
        return self.client.cancel_replace_order(
            symbol=self.symbol,
            side=side,
            type=order_type,
            quantity=quantity,
            price=price,
            cancelOrderId=cancel_order_id,
            timeInForce=time_in_force,
            cancelReplaceMode=cancel_replace_mode
        )

    def _get_price_precision(self, symbol_info: Dict) -> tuple:
        """提取价格精度（内部使用）"""
        if not symbol_info or 'filters' not in symbol_info:
            return 0.01, 2
        for f in symbol_info['filters']:
            if f['filterType'] == 'PRICE_FILTER':
                tick = float(f['tickSize'])
                decimals = len(str(tick).split('.')[-1].rstrip('0'))
                return tick, decimals
        return 0.01, 2

    def _get_quantity_precision(self, symbol_info: Dict) -> tuple:
        """提取数量精度（内部使用）"""
        if not symbol_info or 'filters' not in symbol_info:
            return 0.001, 3
        for f in symbol_info['filters']:
            if f['filterType'] == 'LOT_SIZE':
                step = float(f['stepSize'])
                decimals = len(str(step).split('.')[-1].rstrip('0'))
                return step, decimals
        return 0.001, 3

    def get_trading_rules(self) -> Dict:
        """获取交易规则（精度信息）"""
        symbol_info = self._get_symbol_info()
        tick_size, price_decimals = self._get_price_precision(symbol_info)
        step_size, qty_decimals = self._get_quantity_precision(symbol_info)
        return {
            'tick_size': tick_size,
            'price_decimals': price_decimals,
            'step_size': step_size,
            'qty_decimals': qty_decimals
        }

    # ====================== WebSocket 监控 ======================
    def _start_ws_in_thread(self, on_price_update: Callable[[float], None], 
                           on_order_update: Callable[[Dict], None]) -> None:
        """在线程中启动 WebSocket 监听（价格和订单）"""

        # 启动价格监控
        async def price_callback(msg):
            """解析币安行情消息"""
            try:
                # print(f"{self._get_log_prefix()} 🔍 收到行情消息: {msg}")
                if msg.get('e') == 'error':
                    error_key = f"price_error_{msg.get('type', 'unknown')}"
                    if self._should_log_error(error_key):
                        print(f"{self._get_log_prefix()} ❌ 价格 WebSocket 错误: {msg}")
                        # 使用锁防止毫秒级别的多次回调同时触发重启
                        if self._price_restart_lock.acquire(blocking=False):
                            try: 
                                self._restart_ws_async(on_price_update, on_order_update)
                            finally:
                                # 延迟释放锁，防止毫秒级的重复触发
                                threading.Timer(0.5, self._price_restart_lock.release).start()
                    return

                price = msg.get('c')
                if price and on_price_update:
                    price = float(price)
                    # 在线程池中执行同步回调,避免阻塞事件循环
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, on_price_update, price)
            except Exception as e:
                print(f"{self._get_log_prefix()} ❌ 解析价格失败: {e}")

        # 启动订单监控
        # https://developers.binance.com/docs/binance-spot-api-docs/user-data-stream#order-update
        async def user_data_callback(msg):
            """解析币安用户数据消息"""
            try:
                msg_type = msg.get('e', 'unknown')
                # print(f"{self._get_log_prefix()} 🔍 收到用户消息: {msg}")

                if msg_type == 'error':
                    error_key = f"user_error_{msg.get('type', 'unknown')}"
                    if self._should_log_error(error_key):
                        print(f"{self._get_log_prefix()} ❌ 币安用户数据 WebSocket 错误: {msg}")                    
                        # 使用锁防止毫秒级别的多次回调同时触发重启
                        if self._order_restart_lock.acquire(blocking=False):
                            try: 
                                self._restart_ws_async(on_price_update, on_order_update)
                            finally:
                                # 延迟释放锁，防止毫秒级的重复触发
                                threading.Timer(0.5, self._order_restart_lock.release).start()
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

                    # N: 手续费资产类型 (如 'BNB', 'USDT' 等)
                    # 如果用 BNB 支付手续费，则不从交易币种中扣除
                    commission_asset = msg.get('N')
                    fee_paid_externally = (commission_asset == 'BNB')
                    
                    event = {
                        'event_type': event_type,
                        'order_id': order_id,
                        'symbol': msg.get('s'),
                        'side': msg.get('S'),
                        'status': order_status,
                        'price': msg.get('p'),
                        'quantity': msg.get('q'),
                        'executedQty': msg.get('z'),
                        'lastExecutedQty': msg.get('l'),
                        'feePaidExternally': fee_paid_externally  # 手续费是否外部支付（不扣币）
                    }
                    
                    # 执行回调
                    if on_order_update:
                        try:
                            # 在线程池中执行同步回调,避免阻塞事件循环
                            loop = asyncio.get_event_loop()
                            await loop.run_in_executor(None, on_order_update, event)
                        except Exception as cb_e:
                            print(f"{self._get_log_prefix()} ⚠️ 回调执行失败: {cb_e}")

            except Exception as e:
                print(f"{self._get_log_prefix()} ❌ 解析用户消息失败: {e}")

        async def run_websocket():
            """异步运行 WebSocket 连接"""
            try:
                # 创建异步客户端
                self.async_client = await AsyncClient.create(
                    api_key=self.api_key,
                    api_secret=self.api_secret,
                    testnet=self.testnet
                )
                self.manager = BinanceSocketManager(self.async_client)

                print(f"{self._get_log_prefix()} 🆕 启动 WebSocket 监控 (symbol: {self.symbol})")
                
                # 创建任务来处理两个 WebSocket - 立即开始接收,避免队列积压
                async def handle_price_socket():
                    # 启动价格监控并立即开始接收
                    price_socket = self.manager.symbol_ticker_socket(symbol=self.symbol)
                    async with price_socket as ps:
                        while self._ws_thread_running:
                            try:
                                msg = await ps.recv()
                                # 使用 create_task 非阻塞处理,避免队列积压
                                asyncio.create_task(price_callback(msg))
                            except Exception as e:
                                print(f"{self._get_log_prefix()} ❌ 价格 socket 错误: {e}")
                                if self._ws_thread_running:
                                    await asyncio.sleep(1)
                                else:
                                    break
                
                async def handle_user_socket():
                    # 启动订单监控并立即开始接收
                    user_socket = self.manager.user_socket()
                    async with user_socket as us:
                        while self._ws_thread_running:
                            try:
                                msg = await us.recv()
                                # 使用 create_task 非阻塞处理,避免队列积压
                                asyncio.create_task(user_data_callback(msg))
                            except Exception as e:
                                print(f"{self._get_log_prefix()} ❌ 用户数据 socket 错误: {e}")
                                if self._ws_thread_running:
                                    await asyncio.sleep(1)
                                else:
                                    break
                
                # 同时运行两个 socket
                await asyncio.gather(
                    handle_price_socket(),
                    handle_user_socket()
                )
                
                print(f"{self._get_log_prefix()} 🛑 WebSocket 监控收到停止信号,准备退出...")
                
            except Exception as e:
                print(f"{self._get_log_prefix()} ❌ WebSocket 运行错误: {e}")
                import traceback
                traceback.print_exc()
            finally:
                if self.async_client:
                    await self.async_client.close_connection()
        
        # 启动价格和订单监控
        try:
            # 创建新的事件循环
            self._event_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._event_loop)
            
            # 运行 WebSocket
            self._event_loop.run_until_complete(run_websocket())

        except BinanceAPIException as e:
            print(f"{self._get_log_prefix()} ❌ 启动 WebSocket 监控失败 [API错误]: {e}")
            self._ws_thread_running = False
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 启动 WebSocket 监控失败: {e}")
            import traceback
            traceback.print_exc()
            self._ws_thread_running = False
        finally:
            # 清理事件循环
            if self._event_loop:
                try:
                    self._event_loop.close()
                except Exception as e:
                    print(f"{self._get_log_prefix()} ⚠️ 关闭事件循环失败: {e}")
                self._event_loop = None

    def start_ws(self, on_price_update: Callable[[float], None], 
                 on_order_update: Callable[[Dict], None]) -> bool:
        """启动 WebSocket 监听（价格和订单）- 在独立线程中运行"""
        with self._ws_thread_lock:
            # 如果线程已在运行，先停止
            if self._ws_thread_running:
                print(f"{self._get_log_prefix()} ⚠️ WebSocket 线程已在运行，先停止...")
                self.stop_ws()
            
            # 设置运行标志
            self._ws_thread_running = True
            
            # 创建并启动线程
            self._ws_thread = threading.Thread(
                target=self._start_ws_in_thread,
                args=(on_price_update, on_order_update),
                daemon=True,
                name=f"BinanceWS-{self.symbol}"
            )
            self._ws_thread.start()
            print(f"{self._get_log_prefix()} 🚀 WebSocket 监控线程已启动 (线程名: {self._ws_thread.name})")
            
            # 等待一小段时间确保线程启动
            time.sleep(0.5)
            
            return True

    def stop_ws(self) -> None:
        """完全关闭 WebSocket 管理器和所有连接"""
        try:
            print(f"{self._get_log_prefix()} 🔌 开始清理 WebSocket 连接...")
            
            # 设置停止标志,让 WebSocket 线程自己退出
            self._ws_thread_running = False
            
            # 等待线程停止
            if self._ws_thread and self._ws_thread.is_alive():
                print(f"{self._get_log_prefix()} 🛑 等待 WebSocket 线程停止...")
                self._ws_thread.join(timeout=5)
                if self._ws_thread.is_alive():
                    print(f"{self._get_log_prefix()} ⚠️ WebSocket 线程未能在5秒内停止")
                else:
                    print(f"{self._get_log_prefix()} ✅ WebSocket 线程已停止")
            self._ws_thread = None
            
            # 清理引用(实际清理在 WebSocket 线程的 finally 块中完成)
            self.manager = None
            self.async_client = None
            self._event_loop = None
            
            print(f"{self._get_log_prefix()} ✅ 清理完成")
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 清理过程出错: {e}")
            import traceback
            traceback.print_exc()

    def check_pending_orders(self, pending_orders: List[Dict]):
        """检查待处理订单的状态（用于 HTTP 轮询模式）
        
        Args:
            pending_orders: 待检查的订单列表，每个订单包含 order_id, symbol 等信息
        
        Note:
            BinanceAdapter 使用 WebSocket 实时监控订单，不需要轮询
            此方法为满足基类接口要求而实现，实际不使用
        """
        # WebSocket 模式下不需要轮询检查订单
        # 订单更新会通过 start_order_monitor 的回调实时推送
        pass

    def _get_trade_fee(self, symbol: str) -> Dict[str, float]:
        """获取交易对的手续费率（带缓存）
        
        Args:
            symbol: 交易对，如 'BTCUSDT'
            
        Returns:
            {'maker_fee': 0.001, 'taker_fee': 0.001}
        """
        symbol = symbol.upper()
        
        with self._fee_cache_lock:
            if symbol in self._fee_cache:
                return self._fee_cache[symbol]
        
        try:
            fee_info = self.client.get_trade_fee(symbol=symbol)
            if fee_info and len(fee_info) > 0:
                maker_fee = float(fee_info[0].get('makerCommission', 0.001))
                taker_fee = float(fee_info[0].get('takerCommission', 0.001))
            else:
                # 默认费率
                maker_fee = 0.001
                taker_fee = 0.001
                
            fee_data = {'maker_fee': maker_fee, 'taker_fee': taker_fee}
            
            with self._fee_cache_lock:
                self._fee_cache[symbol] = fee_data
                
            print(f"{self._get_log_prefix()} 💰 获取 {symbol} 费率: maker={maker_fee*100}%, taker={taker_fee*100}%")
            return fee_data
            
        except Exception as e:
            print(f"{self._get_log_prefix()} ⚠️ 获取费率失败，使用默认值: {e}")
            return {'maker_fee': 0.001, 'taker_fee': 0.001}

    def calculate_sell_price(self, buy_price, sell_offset_percent, tick_size, price_decimals, current_price=None):
        """计算卖出价格（基于实际账户费率）
        
        Args:
            buy_price: 买入价格
            sell_offset_percent: 卖出偏移百分比
            tick_size: 价格步长
            price_decimals: 价格小数位数
            current_price: 当前价格（可选，用于动态定价）
            
        Returns:
            float: 对齐后的卖出价格
        """
        sell_offset = sell_offset_percent / 100.0
        raw_sell_price = (current_price or buy_price) * (1 + sell_offset)
        
        # 获取实际费率（买入+卖出双边费率）
        fee_data = self._get_trade_fee(self.symbol)
        # 使用 taker 费率（市价单）或 maker 费率（限价单）
        total_fee_rate = fee_data['maker_fee'] * 2  # 买卖双边
        
        # 最低保护价（买入价 + 双边手续费）
        min_price = buy_price * (1 + total_fee_rate)
        min_price = math.ceil(min_price / tick_size) * tick_size if tick_size else min_price
        min_price = round(min_price, price_decimals)
        
        # 最终卖价（向上取整确保不低于目标价）
        sell_price = max(raw_sell_price, min_price)
        sell_price = math.ceil(sell_price / tick_size) * tick_size if tick_size else sell_price
        sell_price = round(sell_price, price_decimals)
        
        # 确保卖价至少高于买价一个 tick_size（防止手续费为0时无利润）
        if sell_price <= buy_price and tick_size:
            sell_price = round(buy_price + tick_size, price_decimals)
        
        return sell_price


    def get_fee_rate(self) -> float:
        """获取交易对的手续费率（重写基类方法）"""
        fee_data = self._get_trade_fee(self.symbol)
        return fee_data['maker_fee']
