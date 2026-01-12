# ccxt_futures_adapter.py - 使用 ccxt pro WebSocket 实现的币安合约适配器
from __future__ import annotations

import asyncio
import math
import threading
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

import ccxt.pro as ccxtpro
import ccxt

from .base import BaseExchange


class CcxtBinanceFutures(BaseExchange):
    """使用 ccxt 实现的币安合约交易适配器"""

    def __init__(self, api_key: str, api_secret: str, symbol: str, testnet: bool = True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.symbol = symbol.upper()
        self.testnet = testnet

        self._market_symbol = self._to_ccxt_symbol(symbol)
        # 同步客户端（用于 REST 调用）
        self.client = self._create_sync_client(api_key, api_secret, testnet)
        # 异步客户端（用于 WebSocket）
        self._ws_client: Optional[ccxtpro.binance] = None

        # 监控线程
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_running = False
        self._monitor_lock = threading.Lock()
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None

        # 价格去重
        self._last_price: Optional[float] = None
        self._last_price_lock = threading.Lock()

        # 缓存交易规则
        self._symbol_info_cache: Optional[Dict] = None

        # 费率缓存
        self._fee_cache: Dict[str, Dict[str, float]] = {}
        self._fee_cache_lock = threading.Lock()

        # 重试计数
        self._retry_count = 0

        # 持仓缓存（通过 watchPositions 更新）
        self._positions_cache: List[Dict] = []
        self._positions_lock = threading.Lock()

        # WS 方法可用性标记（失败后禁用避免重复尝试）
        self._ws_fetch_orders_enabled = True

    def _to_ccxt_symbol(self, symbol: str) -> str:
        """将 BTCUSDT 转换为 ccxt 格式 BTC/USDT:USDT（合约）"""
        s = symbol.strip().upper()
        if "/" in s:
            # 已经是 ccxt 格式
            if ":USDT" not in s:
                return f"{s}:USDT"
            return s
        # BTCUSDT -> BTC/USDT:USDT
        if s.endswith("USDT") and len(s) > 4:
            base = s[:-4]
            return f"{base}/USDT:USDT"
        return s

    def _create_sync_client(self, api_key: str, api_secret: str, testnet: bool):
        """创建 ccxt binance 合约同步客户端（用于 REST 调用）"""
        client = ccxt.binance({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "timeout": 15000,
            "options": {
                "defaultType": "future",
                "fetchCurrencies": False,
                "adjustForTimeDifference": True,
            },
        })
        if testnet:
            client.set_sandbox_mode(True)
        try:
            client.options["defaultType"] = "future"
            client.options["fetchCurrencies"] = False
        except Exception:
            pass
        return client

    def _create_ws_client(self, api_key: str, api_secret: str, testnet: bool):
        """创建 ccxt pro binance 合约异步客户端（用于 WebSocket）"""
        client = ccxtpro.binanceusdm({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {
                "defaultType": "future",
                "fetchCurrencies": False,
                "adjustForTimeDifference": True,
            },
        })
        if testnet:
            client.set_sandbox_mode(True)
        try:
            client.options["defaultType"] = "future"
            client.options["fetchCurrencies"] = False
        except Exception:
            pass
        return client

    def _get_log_prefix(self) -> str:
        api_key_short = self.api_key[:6] if self.api_key else "NOKEY"
        return f"[{datetime.now().isoformat()}] [ccxt-futures-{api_key_short}-{self.symbol}]"

    def ping(self) -> bool:
        try:
            self.client.load_markets()
            return True
        except Exception as e:
            print(f"{self._get_log_prefix()} Error: {e}")
            return False

    @classmethod
    def get_exchange_info(cls) -> Dict:
        """获取交易所信息（类方法）"""
        return {
            'id': 'ccxt_binance_futures',
            'name': '币安-合约',
            'description': 'Binance Futures Trading (CCXT)'
        }

    def _get_symbol_info(self) -> Dict:
        """获取合约交易对信息（内部使用）"""
        if self._symbol_info_cache:
            return self._symbol_info_cache

        try:
            markets = self.client.load_markets()
            info = markets.get(self._market_symbol, {})
            if info:
                self._symbol_info_cache = info
            return info
        except Exception as e:
            print(f"{self._get_log_prefix()} ⚠️ 获取合约交易对信息失败: {e}")
            return {}

    def get_symbol_ticker(self) -> Dict:
        """获取合约当前价格"""
        try:
            t = self.client.fetch_ticker(self._market_symbol)
            price = t.get("last") or t.get("close")
            return {"symbol": self.symbol, "price": str(price) if price is not None else None}
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 获取价格失败: {e}")
            raise

    def get_open_orders(self) -> List[Dict]:
        """获取合约未完成订单（优先使用 WebSocket，失败回退到 REST）
        
        特殊逻辑：如果没有挂单但有持仓，将持仓映射为虚拟订单
        - 多单持仓 → 虚拟卖单（等待平仓）
        - 空单持仓 → 虚拟买单（等待平仓）
        """
        orders = []
        
        # 优先使用 fetchOpenOrdersWs（WebSocket 方式），失败后禁用
        if self._ws_fetch_orders_enabled and self._ws_client and self._event_loop and self._event_loop.is_running():
            try:
                print(f"{self._get_log_prefix()} 🔍 [WS] 查询未完成订单: symbol={self._market_symbol}")
                future = asyncio.run_coroutine_threadsafe(
                    self._ws_client.fetch_open_orders_ws(self._market_symbol),
                    self._event_loop
                )
                orders = future.result(timeout=10)
                print(f"{self._get_log_prefix()} 🔍 [WS] 查询到 {len(orders)} 笔未完成订单")
                orders = self._adapt_orders(orders)
            except Exception as e:
                print(f"{self._get_log_prefix()} ⚠️ fetchOpenOrdersWs 失败，后续使用 REST: {e}")
                self._ws_fetch_orders_enabled = False
                orders = []
        
        # 回退到 REST API
        if not orders:
            try:
                print(f"{self._get_log_prefix()} 🔍 [REST] 查询未完成订单: symbol={self._market_symbol}")
                raw_orders = self.client.fetch_open_orders(self._market_symbol)
                print(f"{self._get_log_prefix()} 🔍 [REST] 查询到 {len(raw_orders)} 笔未完成订单")
                orders = self._adapt_orders(raw_orders)
            except Exception as e:
                print(f"{self._get_log_prefix()} ❌ 获取未完成订单失败: {e}")
                return []
        
        # 如果没有挂单，检查持仓并映射为虚拟订单
        if not orders:
            orders = self._position_to_virtual_orders()
        
        return orders

    def _position_to_virtual_orders(self) -> List[Dict]:
        """将持仓映射为虚拟订单
        - 多单持仓 → 虚拟卖单
        - 空单持仓 → 虚拟买单
        """
        try:
            positions = self.get_position()
            if not positions:
                return []
            
            virtual_orders = []
            for pos in positions:
                pos_qty = abs(float(pos.get('contracts', 0) or pos.get('info', {}).get('positionAmt', 0)))
                pos_side = pos.get('side', '').lower()
                entry_price = float(pos.get('entryPrice', 0) or pos.get('info', {}).get('entryPrice', 0))
                
                if pos_qty <= 0 or entry_price <= 0:
                    continue
                
                if pos_side == 'long':
                    # 多单持仓 → 虚拟卖单
                    virtual_orders.append({
                        "orderId": f"pos_long_{self.symbol}",
                        "id": f"pos_long_{self.symbol}",
                        "symbol": self.symbol,
                        "side": "SELL",
                        "price": str(entry_price),
                        "origQty": str(pos_qty),
                        "executedQty": "0",
                        "status": "NEW",
                        "info": {"virtual": True, "from_position": True, "entry_price": entry_price},
                    })
                    print(f"{self._get_log_prefix()} 📍 多单持仓映射为虚拟卖单: 数量={pos_qty}, 入场价={entry_price}")
                elif pos_side == 'short':
                    # 空单持仓 → 虚拟买单
                    virtual_orders.append({
                        "orderId": f"pos_short_{self.symbol}",
                        "id": f"pos_short_{self.symbol}",
                        "symbol": self.symbol,
                        "side": "BUY",
                        "price": str(entry_price),
                        "origQty": str(pos_qty),
                        "executedQty": "0",
                        "status": "NEW",
                        "info": {"virtual": True, "from_position": True, "entry_price": entry_price},
                    })
                    print(f"{self._get_log_prefix()} 📍 空单持仓映射为虚拟买单: 数量={pos_qty}, 入场价={entry_price}")
            
            return virtual_orders
        except Exception as e:
            print(f"{self._get_log_prefix()} ⚠️ 持仓映射失败: {e}")
            return []

    def _adapt_orders(self, orders: List) -> List[Dict]:
        """将 ccxt 订单格式转换为统一格式"""
        adapted = []
        for o in orders:
            status = self._map_status(o.get("status"))
            adapted.append({
                "orderId": str(o.get("id")),
                "id": str(o.get("id")),
                "symbol": self.symbol,
                "side": str(o.get("side", "")).upper(),
                "price": str(o.get("price") or 0),
                "origQty": str(o.get("amount") or 0),
                "executedQty": str(o.get("filled") or 0),
                "status": status,
                "info": o.get("info"),
            })
        return adapted

    def get_order(self, order_id: str) -> Dict:
        """查询合约订单状态"""
        try:
            o = self.client.fetch_order(order_id, self._market_symbol)
            status = self._map_status(o.get("status"))
            return {
                "orderId": str(o.get("id")),
                "id": str(o.get("id")),
                "symbol": self.symbol,
                "side": str(o.get("side", "")).upper(),
                "price": str(o.get("price") or 0),
                "origQty": str(o.get("amount") or 0),
                "executedQty": str(o.get("filled") or 0),
                "status": status,
                "info": o.get("info"),
            }
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 查询订单失败: {e}")
            raise

    def _map_status(self, status: object) -> str:
        """将 ccxt 状态映射为 Binance 风格状态"""
        s = str(status or "").lower()
        if s in {"canceled", "cancelled"}:
            return "CANCELED"
        if s in {"closed", "filled"}:
            return "FILLED"
        if s in {"open"}:
            return "NEW"
        if s in {"expired"}:
            return "EXPIRED"
        return s.upper()

    def order_limit_buy(self, quantity: float, price: str, **kwargs) -> Dict:
        """合约限价买单（做多开仓）"""
        try:
            o = self.client.create_limit_buy_order(
                self._market_symbol,
                quantity,
                float(price),
                params={"timeInForce": kwargs.get("timeInForce", "GTC")}
            )
            return {"orderId": str(o.get("id")), "id": str(o.get("id")), **(o or {})}
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 下买单失败: {e}")
            raise

    def order_limit_sell(self, quantity: float, price: str, **kwargs) -> Dict:
        """合约限价卖单（做多平仓）"""
        try:
            o = self.client.create_limit_sell_order(
                self._market_symbol,
                quantity,
                float(price),
                params={"timeInForce": kwargs.get("timeInForce", "GTC")}
            )
            return {"orderId": str(o.get("id")), "id": str(o.get("id")), **(o or {})}
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 下卖单失败: {e}")
            raise

    def cancel_order(self, order_id: str) -> Dict:
        """取消合约订单"""
        try:
            o = self.client.cancel_order(order_id, self._market_symbol)
            return {"orderId": str(o.get("id")), "id": str(o.get("id")), **(o or {})}
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 取消订单失败 (order_id={order_id}): {e}")
            raise

    def _is_virtual_order(self, order_id: str) -> bool:
        """检查是否为虚拟订单（由持仓映射生成）"""
        return str(order_id).startswith("pos_long_") or str(order_id).startswith("pos_short_")

    def cancel_replace_order(
        self,
        side: str,
        order_type: str,
        quantity: float,
        price: str,
        cancel_order_id: str,
        **kwargs,
    ) -> Dict:
        """取消并替换订单（优先使用 editOrderWs 原子操作，失败则回退到取消+新建）"""
        
        # 虚拟订单（持仓映射）：跳过取消，直接下新单
        if self._is_virtual_order(cancel_order_id):
            print(f"{self._get_log_prefix()} 📍 虚拟订单 {cancel_order_id}，直接下新单")
            if str(side).upper() == "BUY":
                new_order = self.order_limit_buy(quantity=quantity, price=price, **kwargs)
            else:
                new_order = self.order_limit_sell(quantity=quantity, price=price, **kwargs)
            return {
                "cancelResult": "SUCCESS",
                "newOrderResult": "SUCCESS",
                "newOrderResponse": new_order,
            }
        
        # 尝试使用 editOrderWs（WebSocket 原子改单）
        if self._ws_client and self._event_loop and self._event_loop.is_running():
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._ws_client.edit_order_ws(
                        id=cancel_order_id,
                        symbol=self._market_symbol,
                        type='limit',
                        side=side.lower(),
                        amount=quantity,
                        price=float(price)
                    ),
                    self._event_loop
                )
                result = future.result(timeout=10)  # 10秒超时
                new_order_id = str(result.get('id') or result.get('orderId'))
                print(f"{self._get_log_prefix()} ✅ editOrderWs 改单成功: {cancel_order_id} → {new_order_id}")
                return {
                    "cancelResult": "SUCCESS",
                    "newOrderResult": "SUCCESS",
                    "newOrderResponse": {
                        "orderId": new_order_id,
                        "id": new_order_id,
                        **result
                    },
                }
            except Exception as e:
                print(f"{self._get_log_prefix()} ❌ editOrderWs 失败 (order_id={cancel_order_id}): {e}")
                raise

    def calculate_estimated_buy_price(self, sell_price: float, sell_offset_percent: float, tick_size: float, price_decimals: int, order: Optional[Dict] = None) -> float:
        """根据卖单价格反推估算的买入价格
        
        对于合约虚拟订单（持仓映射的平仓单），直接返回入场价格（entry_price）
        """
        # 1. 如果是虚拟订单，直接从 order info 中获取入场价
        if order:
            order_id = str(order.get('orderId') or order.get('id', ''))
            if self._is_virtual_order(order_id):
                # 尝试从 info 中获取 entry_price
                info = order.get('info', {})
                entry_price = info.get('entry_price')
                
                # 如果 info 中没有，尝试直接从 price 字段获取（虚拟订单的 price 就是 entry_price）
                if not entry_price and order.get('price'):
                    entry_price = float(order['price'])
                
                if entry_price:
                    print(f"{self._get_log_prefix()} 📍 虚拟订单 {order_id}，直接使用入场价作为估算买入价: {entry_price}")
                    return float(entry_price)

        # 2. 如果不是虚拟订单：优先从当前持仓获取开仓价（entryPrice）
        try:
            positions = self.get_position()
            if positions:
                pos = positions[0]
                entry_price = float(pos.get('entryPrice', 0) or pos.get('info', {}).get('entryPrice', 0))
                if entry_price:
                    entry_price = round(float(entry_price), price_decimals)
                    print(f"{self._get_log_prefix()} 📍 非虚拟订单，使用当前持仓开仓价作为估算买入价: {entry_price}")
                    return float(entry_price)
        except Exception as e:
            print(f"{self._get_log_prefix()} ⚠️ 非虚拟订单查询持仓开仓价失败，回退默认反推逻辑: {e}")

        # 3. 回退：调用父类的默认反推逻辑
        return super().calculate_estimated_buy_price(sell_price, sell_offset_percent, tick_size, price_decimals, order)

    def _get_price_precision(self, symbol_info: Dict) -> Tuple[float, int]:
        """从合约交易对信息中提取价格精度（内部使用）"""
        prec = (symbol_info or {}).get("precision", {})
        limits = (symbol_info or {}).get("limits", {})
        
        # 调试日志
        print(f"{self._get_log_prefix()} 🔍 precision={prec}, limits={limits}")
        
        # ccxt 的 precision.price 可能是小数位数（如 2）或 tick_size（如 0.01）
        price_prec = prec.get("price")
        
        if price_prec is not None:
            if price_prec >= 1:
                # 是小数位数
                price_decimals = int(price_prec)
                tick_size = 10 ** (-price_decimals)
            else:
                # 是 tick_size 本身
                tick_size = float(price_prec)
                # 计算小数位数
                price_decimals = max(0, -int(math.floor(math.log10(tick_size) + 1e-9)))
        else:
            # 默认值
            price_decimals = 2
            tick_size = 0.01
        
        print(f"{self._get_log_prefix()} 🔍 计算结果: tick_size={tick_size}, price_decimals={price_decimals}")
        return float(tick_size), price_decimals

    def _get_quantity_precision(self, symbol_info: Dict) -> Tuple[float, int]:
        """从合约交易对信息中提取数量精度（内部使用）"""
        prec = (symbol_info or {}).get("precision", {})
        
        # ccxt 的 precision.amount 可能是小数位数（如 3）或 step_size（如 0.001）
        amount_prec = prec.get("amount")
        
        if amount_prec is not None:
            if amount_prec >= 1:
                # 是小数位数
                qty_decimals = int(amount_prec)
                step_size = 10 ** (-qty_decimals)
            else:
                # 是 step_size 本身
                step_size = float(amount_prec)
                # 计算小数位数
                qty_decimals = max(0, -int(math.floor(math.log10(step_size) + 1e-9)))
        else:
            # 默认值
            qty_decimals = 3
            step_size = 0.001
        
        print(f"{self._get_log_prefix()} 🔍 数量精度: amount_prec={amount_prec}, step_size={step_size}, qty_decimals={qty_decimals}")
        return float(step_size), qty_decimals

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

    # ====================== WebSocket 监控（ccxt pro 真正 WS） ======================
    
    def _process_order_event(self, o: Dict, on_order_update: Callable[[Dict], None]):
        """处理单个订单事件（子类可重写以修改 side 等字段）"""
        order_id = str(o.get("id"))
        raw_status = o.get("status")
        status = self._map_status(raw_status)
        side = str(o.get("side", "")).upper()
        price = o.get("price")
        amount = o.get("amount")
        filled = o.get("filled")

        # 打印所有订单事件
        print(f"{self._get_log_prefix()} 📨 订单事件: id={order_id}, status={raw_status}->{status}, side={side}, price={price}, amount={amount}, filled={filled}")

        # 合约手续费从 USDT 扣除
        fee_paid_externally = True

        if status == "CANCELED":
            if on_order_update:
                on_order_update({
                    "event_type": "order_cancelled",
                    "order_id": order_id,
                    "symbol": self.symbol,
                    "side": side,
                    "status": status,
                })
        elif status == "FILLED":
            # 订单成交后，清空持仓缓存，强制下次查询使用 REST API 获取最新持仓
            with self._positions_lock:
                self._positions_cache = []
            print(f"{self._get_log_prefix()} 🔄 订单成交，已清空持仓缓存，下次查询将获取最新持仓")
            
            if on_order_update:
                on_order_update({
                    "event_type": "order_filled",
                    "order_id": order_id,
                    "symbol": self.symbol,
                    "side": side,
                    "status": "FILLED",
                    "price": str(price or 0),
                    "quantity": str(amount or 0),
                    "executedQty": str(filled or 0),
                    "feePaidExternally": fee_paid_externally,
                })
        else:
            # NEW 或其他状态也通知
            if on_order_update:
                on_order_update({
                    "event_type": "order_update",
                    "order_id": order_id,
                    "symbol": self.symbol,
                    "side": side,
                    "status": status,
                    "price": str(price or 0),
                    "quantity": str(amount or 0),
                    "executedQty": str(filled or 0),
                })
    
    def start_ws(
        self,
        on_price_update: Callable[[float], None],
        on_order_update: Callable[[Dict], None],
    ) -> bool:
        """启动 WebSocket 监控（使用 ccxt pro 的 watchTicker / watchOrders）"""
        with self._monitor_lock:
            if self._monitor_running:
                return True
            self._monitor_running = True

        def _run_ws_loop():
            prefix = self._get_log_prefix()
            print(f"{prefix} 🚀 WebSocket 监控线程已启动（ccxt pro）")

            # 创建新的事件循环
            self._event_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._event_loop)

            # 创建异步客户端
            self._ws_client = self._create_ws_client(self.api_key, self.api_secret, self.testnet)

            async def watch_ticker():
                """watch_bids_asks 实时价格推送（使用 bookTicker 流，更新更快）"""
                update_count = 0
                msg_count = 0  # WebSocket 消息计数
                last_log_time = time.time()
                start_time = time.time()
                while self._monitor_running:
                    try:
                        # 使用 watch_bids_asks (bookTicker) 获取更快的价格更新
                        bids_asks = await self._ws_client.watch_bids_asks([self._market_symbol])
                        msg_count += 1
                        ba = bids_asks.get(self._market_symbol, {})
                        # 使用 bid 和 ask 的中间价作为当前价格
                        bid = ba.get("bid")
                        ask = ba.get("ask")
                        if bid is not None and ask is not None:
                            p = (float(bid) + float(ask)) / 2
                            with self._last_price_lock:
                                price_changed = self._last_price is None or abs(p - self._last_price) > 1e-12
                                if price_changed:
                                    self._last_price = p
                                    update_count += 1
                                
                                # 每 10 秒打印一次日志，包含速率统计
                                now = time.time()
                                if now - last_log_time >= 10:
                                    elapsed = now - start_time
                                    msg_rate = msg_count / elapsed if elapsed > 0 else 0
                                    change_rate = update_count / elapsed if elapsed > 0 else 0
                                    print(f"{self._get_log_prefix()} 📊 价格={p:.2f} (bid={bid}, ask={ask}) | WS消息: {msg_count}条 ({msg_rate:.1f}/秒) | 价格变化: {update_count}次 ({change_rate:.2f}/秒)")
                                    last_log_time = now
                                
                                if price_changed and on_price_update:
                                    on_price_update(p)
                    except Exception as e:
                        if self._monitor_running:
                            print(f"{self._get_log_prefix()} ⚠️ watch_bids_asks 错误: {e}")
                            await asyncio.sleep(1)

            async def watch_orders():
                """监听订单更新（watchOrders）"""
                while self._monitor_running:
                    try:
                        orders = await self._ws_client.watch_orders(self._market_symbol)
                        for o in orders:
                            self._process_order_event(o, on_order_update)
                    except Exception as e:
                        if self._monitor_running:
                            print(f"{self._get_log_prefix()} ⚠️ watchOrders 错误: {e}")
                            import traceback
                            traceback.print_exc()
                            await asyncio.sleep(1)

            async def watch_positions():
                """监听持仓更新（watchPositions）"""
                while self._monitor_running:
                    try:
                        positions = await self._ws_client.watch_positions([self._market_symbol])
                        
                        # 打印原始报文
                        print(f"{self._get_log_prefix()} 📦 [WS] 持仓原始报文: {positions}")
                        
                        # 过滤当前交易对且有持仓的
                        filtered = [p for p in positions if float(p.get('contracts', 0)) != 0]
                        with self._positions_lock:
                            self._positions_cache = filtered
                        if filtered:
                            pos = filtered[0]
                            print(f"{self._get_log_prefix()} 📍 [WS] 持仓更新: side={pos.get('side')}, qty={pos.get('contracts')}, entry={pos.get('entryPrice')}")
                    except Exception as e:
                        if self._monitor_running:
                            print(f"{self._get_log_prefix()} ⚠️ watchPositions 错误: {e}")
                            await asyncio.sleep(1)

            async def run_all():
                """watchTicker、watchOrders、watchPositions 并行运行"""
                try:
                    await asyncio.gather(watch_ticker(), watch_orders(), watch_positions())
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    print(f"{self._get_log_prefix()} ❌ WebSocket 运行错误: {e}")
                finally:
                    if self._ws_client:
                        await self._ws_client.close()

            try:
                self._event_loop.run_until_complete(run_all())
            except Exception as e:
                print(f"{self._get_log_prefix()} ❌ 事件循环错误: {e}")
            finally:
                if self._event_loop:
                    self._event_loop.close()
                    self._event_loop = None
                print(f"{self._get_log_prefix()} ◼️ WebSocket 监控线程已停止")

        self._monitor_thread = threading.Thread(target=_run_ws_loop, daemon=True, name=f"CcxtFuturesWS-{self.symbol}")
        self._monitor_thread.start()
        time.sleep(0.5)  # 等待线程启动
        return True

    def stop_ws(self) -> None:
        """停止 WebSocket 监控"""
        print(f"{self._get_log_prefix()} 🛑 停止WebSocket监控...")
        
        # 先设置停止标志，让循环自然退出
        with self._monitor_lock:
            self._monitor_running = False

        # 优雅关闭：先关闭 WebSocket 客户端，让任务自然结束
        if self._event_loop and self._event_loop.is_running() and self._ws_client:
            print(f"{self._get_log_prefix()} 🔧 关闭WebSocket客户端...")
            
            async def close_ws():
                try:
                    await self._ws_client.close()
                except:
                    pass
            
            future = asyncio.run_coroutine_threadsafe(close_ws(), self._event_loop)
            try:
                future.result(timeout=3)  # 等待最多3秒
            except:
                pass

        if self._monitor_thread and self._monitor_thread.is_alive():
            print(f"{self._get_log_prefix()} 🔧 等待监控线程结束...")
            self._monitor_thread.join(timeout=5)
            if self._monitor_thread.is_alive():
                print(f"{self._get_log_prefix()} ⚠️ 监控线程未能在5秒内停止")
            else:
                print(f"{self._get_log_prefix()} ✅ 监控线程已停止")
        self._monitor_thread = None

        # 重置价格缓存
        with self._last_price_lock:
            self._last_price = None
        
        # 重置持仓缓存
        with self._positions_lock:
            self._positions_cache = []
        
        print(f"{self._get_log_prefix()} ✅ WebSocket监控已停止")

    def check_pending_orders(self, pending_orders: List[Dict]):
        """检查待处理订单的状态（用于 HTTP 轮询模式）"""
        for o in pending_orders or []:
            order_id = o.get("order_id")
            if not order_id:
                continue
            try:
                self.get_order(str(order_id))
            except Exception:
                pass

    # ====================== 费率相关 ======================
    def _get_trade_fee(self, symbol: str) -> Dict[str, float]:
        """获取合约交易对的手续费率（带缓存）"""
        symbol = symbol.upper()

        with self._fee_cache_lock:
            if symbol in self._fee_cache:
                return self._fee_cache[symbol]

        # 尝试从API获取费率
        try:
            # 使用 fetchTradingFee 方法获取精确费率
            fee_info = self.client.fetchTradingFee(symbol=self._market_symbol)
            maker_fee = float(fee_info.get("maker", 0.0002))
            taker_fee = float(fee_info.get("taker", 0.0004))
            print(f"{self._get_log_prefix()} 🔍 从API fetchTradingFee 获取合约费率: maker={maker_fee}, taker={taker_fee}")
        except Exception as e:
            print(f"{self._get_log_prefix()} ⚠️ fetchTradingFee 失败，使用默认值: {e}")
            # 合约默认费率: maker 0.02%, taker 0.04%
            maker_fee = 0.0002
            taker_fee = 0.0004

        fee_data = {"maker_fee": maker_fee, "taker_fee": taker_fee}

        with self._fee_cache_lock:
            self._fee_cache[symbol] = fee_data

        print(f"{self._get_log_prefix()} 💰 获取 {symbol} 合约费率: maker={maker_fee*100}%, taker={taker_fee*100}%")
        return fee_data


    def get_fee_rate(self) -> float:
        """获取交易对的手续费率（重写基类方法）"""
        fee_data = self._get_trade_fee(self.symbol)
        return fee_data["maker_fee"]

    # ====================== 合约特有方法（可选使用） ======================
    def set_leverage(self, leverage: int) -> Dict:
        """设置杠杆倍数"""
        try:
            return self.client.set_leverage(leverage, self._market_symbol)
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 设置杠杆失败: {e}")
            raise

    def set_margin_type(self, margin_type: str) -> Dict:
        """设置保证金模式 ('isolated' 或 'cross')"""
        try:
            return self.client.set_margin_mode(margin_type.lower(), self._market_symbol)
        except Exception as e:
            # 保证金类型无需更改
            if "No need to change" in str(e) or "-4046" in str(e):
                print(f"{self._get_log_prefix()} ℹ️ 保证金模式已是 {margin_type}")
                return {"msg": "No need to change margin type"}
            print(f"{self._get_log_prefix()} ❌ 设置保证金模式失败: {e}")
            raise

    def get_position(self) -> List[Dict]:
        """获取当前持仓（优先使用 WS 缓存，失败回退到 REST）"""
        # 优先使用 WebSocket 缓存
        with self._positions_lock:
            if self._positions_cache:
                return self._positions_cache.copy()
        
        # 回退到 REST API
        try:
            positions = self.client.fetch_positions([self._market_symbol])
            return [p for p in positions if float(p.get("contracts", 0)) != 0]
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 获取持仓失败: {e}")
            return []

    def get_account_balance(self) -> Dict:
        """获取合约账户余额"""
        try:
            balance = self.client.fetch_balance()
            usdt = balance.get("USDT", {})
            return {
                "asset": "USDT",
                "balance": float(usdt.get("total", 0)),
                "availableBalance": float(usdt.get("free", 0)),
            }
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 获取余额失败: {e}")
            return {"asset": "USDT", "balance": 0, "availableBalance": 0}
