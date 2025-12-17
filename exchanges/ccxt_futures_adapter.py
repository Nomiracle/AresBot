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


class CcxtFuturesAdapter(BaseExchange):
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
        """获取合约未完成订单（优先使用 WebSocket，失败回退到 REST）"""
        # 优先使用 fetchOpenOrdersWs（WebSocket 方式）
        if self._ws_client and self._event_loop and self._event_loop.is_running():
            try:
                print(f"{self._get_log_prefix()} 🔍 [WS] 查询未完成订单: symbol={self._market_symbol}")
                future = asyncio.run_coroutine_threadsafe(
                    self._ws_client.fetch_open_orders_ws(self._market_symbol),
                    self._event_loop
                )
                orders = future.result(timeout=10)
                print(f"{self._get_log_prefix()} 🔍 [WS] 查询到 {len(orders)} 笔未完成订单")
                return self._adapt_orders(orders)
            except Exception as e:
                print(f"{self._get_log_prefix()} ⚠️ fetchOpenOrdersWs 失败，回退到 REST: {e}")
        
        # 回退到 REST API
        try:
            print(f"{self._get_log_prefix()} 🔍 [REST] 查询未完成订单: symbol={self._market_symbol}")
            orders = self.client.fetch_open_orders(self._market_symbol)
            print(f"{self._get_log_prefix()} 🔍 [REST] 查询到 {len(orders)} 笔未完成订单")
            return self._adapt_orders(orders)
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 获取未完成订单失败: {e}")
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
            print(f"{self._get_log_prefix()} ❌ 取消订单失败: {e}")
            raise

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
                print(f"{self._get_log_prefix()} ⚠️ editOrderWs 失败，回退到取消+新建: {e}")
        
        # 回退：先取消旧订单，再创建新订单
        try:
            self.cancel_order(cancel_order_id)
        except Exception as e:
            # 订单可能已成交或已取消，忽略
            print(f"{self._get_log_prefix()} ⚠️ 取消旧订单失败（可能已成交）: {e}")

        # 创建新订单
        if str(side).upper() == "BUY":
            new_order = self.order_limit_buy(quantity=quantity, price=price, **kwargs)
        else:
            new_order = self.order_limit_sell(quantity=quantity, price=price, **kwargs)

        return {
            "cancelResult": "SUCCESS",
            "newOrderResult": "SUCCESS",
            "newOrderResponse": new_order,
        }

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
                """watchTicker 实时价格推送"""
                update_count = 0
                msg_count = 0  # WebSocket 消息计数
                last_log_time = time.time()
                start_time = time.time()
                while self._monitor_running:
                    try:
                        ticker = await self._ws_client.watch_ticker(self._market_symbol)
                        msg_count += 1  # 每收到一条消息就计数
                        price = ticker.get("last") or ticker.get("close")
                        if price is not None:
                            p = float(price)
                            with self._last_price_lock:
                                price_changed = self._last_price is None or abs(p - self._last_price) > 1e-12
                                if price_changed:
                                    old_price = self._last_price
                                    self._last_price = p
                                    update_count += 1
                                
                                # 每 10 秒打印一次日志，包含速率统计
                                now = time.time()
                                if now - last_log_time >= 10:
                                    elapsed = now - start_time
                                    msg_rate = msg_count / elapsed if elapsed > 0 else 0
                                    change_rate = update_count / elapsed if elapsed > 0 else 0
                                    print(f"{self._get_log_prefix()} 📊 价格={p} | WS消息: {msg_count}条 ({msg_rate:.1f}/秒) | 价格变化: {update_count}次 ({change_rate:.2f}/秒)")
                                    last_log_time = now
                                
                                if price_changed and on_price_update:
                                    on_price_update(p)
                    except Exception as e:
                        if self._monitor_running:
                            print(f"{self._get_log_prefix()} ⚠️ watchTicker 错误: {e}")
                            await asyncio.sleep(1)

            async def watch_orders():
                """监听订单更新（watchOrders）"""
                while self._monitor_running:
                    try:
                        orders = await self._ws_client.watch_orders(self._market_symbol)
                        for o in orders:
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
                    except Exception as e:
                        if self._monitor_running:
                            print(f"{self._get_log_prefix()} ⚠️ watchOrders 错误: {e}")
                            import traceback
                            traceback.print_exc()
                            await asyncio.sleep(1)

            async def run_all():
                """watchTicker 和 watchOrders 并行运行"""
                try:
                    await asyncio.gather(watch_ticker(), watch_orders())
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
        with self._monitor_lock:
            self._monitor_running = False

        # 尝试取消事件循环中的任务
        if self._event_loop and self._event_loop.is_running():
            self._event_loop.call_soon_threadsafe(self._event_loop.stop)

        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=5)
        self._monitor_thread = None

        # 重置价格缓存
        with self._last_price_lock:
            self._last_price = None

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

        # 合约默认费率: maker 0.02%, taker 0.04%
        maker_fee = 0.0002
        taker_fee = 0.0004

        fee_data = {"maker_fee": maker_fee, "taker_fee": taker_fee}

        with self._fee_cache_lock:
            self._fee_cache[symbol] = fee_data

        print(f"{self._get_log_prefix()} 💰 获取 {symbol} 合约费率: maker={maker_fee*100}%, taker={taker_fee*100}%")
        return fee_data

    def calculate_sell_price(self, buy_price, sell_offset_percent, tick_size, price_decimals, current_price=None):
        """计算卖出价格（基于实际账户费率）"""
        sell_offset = sell_offset_percent / 100.0
        raw_sell_price = (current_price or buy_price) * (1 + sell_offset)

        fee_data = self._get_trade_fee(self.symbol)
        total_fee_rate = fee_data["maker_fee"] * 2

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
        """获取当前持仓"""
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
