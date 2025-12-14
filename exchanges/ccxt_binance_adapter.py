# ccxt_binance_adapter.py - 使用 ccxt pro WebSocket 实现的币安现货适配器
from __future__ import annotations

import asyncio
import math
import threading
import time
import traceback
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

import ccxt.pro as ccxtpro
import ccxt

from .base import BaseExchange


class CcxtBinanceAdapter(BaseExchange):
    """使用 ccxt 实现的币安现货交易适配器
    
    交易所名称: ccxt-binance
    """

    def __init__(self, api_key: str, api_secret: str, symbol: str, testnet: bool = True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.symbol = symbol.upper()
        self.testnet = testnet

        self._market_symbol = self._to_ccxt_symbol(symbol)
        
        # 同步客户端（用于 REST 调用）
        print(f"{self._get_log_prefix()} 🔧 初始化同步客户端...")
        self.client = self._create_sync_client(api_key, api_secret, testnet)
        print(f"{self._get_log_prefix()} ✅ 同步客户端初始化完成")
        
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
        
        # 错误日志频率控制
        self._error_log_cache: Dict[str, float] = {}
        self._error_log_interval = 2.0
        
        # 初始化时获取费率
        print(f"{self._get_log_prefix()} 🔧 获取交易费率...")
        self.get_fee_rate()
        print(f"{self._get_log_prefix()} ✅ 初始化完成, symbol={self.symbol}, market_symbol={self._market_symbol}")

    def _to_ccxt_symbol(self, symbol: str) -> str:
        """将 BTCUSDT 转换为 ccxt 格式 BTC/USDT（现货）"""
        s = symbol.strip().upper()
        if "/" in s:
            # 已经是 ccxt 格式
            return s
        # BTCUSDT -> BTC/USDT
        if s.endswith("USDT") and len(s) > 4:
            base = s[:-4]
            return f"{base}/USDT"
        return s

    def _create_sync_client(self, api_key: str, api_secret: str, testnet: bool):
        """创建 ccxt binance 现货同步客户端（用于 REST 调用）"""
        print(f"{self._get_log_prefix()} 🔧 创建同步客户端: testnet={testnet}")
        client = ccxt.binance({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "timeout": 15000,
            "options": {
                "defaultType": "spot",
                "fetchCurrencies": False,
                "adjustForTimeDifference": True,
            },
        })
        if testnet:
            client.set_sandbox_mode(True)
            print(f"{self._get_log_prefix()} 🔧 已启用沙盒模式(testnet)")
        return client

    def _create_ws_client(self, api_key: str, api_secret: str, testnet: bool):
        """创建 ccxt pro binance 现货异步客户端（用于 WebSocket）"""
        print(f"{self._get_log_prefix()} 🔧 创建WebSocket客户端: testnet={testnet}")
        client = ccxtpro.binance({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {
                "defaultType": "spot",
                "fetchCurrencies": False,
                "adjustForTimeDifference": True,
            },
        })
        if testnet:
            client.set_sandbox_mode(True)
            print(f"{self._get_log_prefix()} 🔧 WebSocket客户端已启用沙盒模式")
        return client

    def _get_log_prefix(self) -> str:
        """生成日志前缀"""
        api_key_short = self.api_key[:6] if self.api_key else "NOKEY"
        return f"[{datetime.now().isoformat()}] [ccxt-binance-{api_key_short}-{self.symbol}]"

    def _should_log_error(self, error_key: str) -> bool:
        """检查是否应该打印错误日志（频率控制）"""
        current_time = time.time()
        last_log_time = self._error_log_cache.get(error_key, 0)
        
        if current_time - last_log_time >= self._error_log_interval:
            self._error_log_cache[error_key] = current_time
            return True
        return False

    def ping(self) -> bool:
        """测试连接"""
        print(f"{self._get_log_prefix()} 🔍 执行ping测试...")
        try:
            self.client.load_markets()
            print(f"{self._get_log_prefix()} ✅ ping成功")
            return True
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ ping失败: {e}")
            traceback.print_exc()
            return False

    def _get_symbol_info(self) -> Dict:
        """获取现货交易对信息（内部使用）"""
        if self._symbol_info_cache:
            print(f"{self._get_log_prefix()} 🔍 使用缓存的交易对信息")
            return self._symbol_info_cache

        print(f"{self._get_log_prefix()} 🔍 获取交易对信息: {self._market_symbol}")
        try:
            markets = self.client.load_markets()
            info = markets.get(self._market_symbol, {})
            if info:
                self._symbol_info_cache = info
                print(f"{self._get_log_prefix()} ✅ 获取交易对信息成功: precision={info.get('precision')}, limits={info.get('limits')}")
            else:
                print(f"{self._get_log_prefix()} ⚠️ 未找到交易对: {self._market_symbol}")
            return info
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 获取交易对信息失败: {e}")
            traceback.print_exc()
            return {}

    def get_symbol_ticker(self) -> Dict:
        """获取现货当前价格"""
        print(f"{self._get_log_prefix()} 🔍 获取价格: {self._market_symbol}")
        try:
            t = self.client.fetch_ticker(self._market_symbol)
            price = t.get("last") or t.get("close")
            result = {"symbol": self.symbol, "price": str(price) if price is not None else None}
            print(f"{self._get_log_prefix()} ✅ 当前价格: {price}")
            return result
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 获取价格失败: {e}")
            traceback.print_exc()
            raise

    def get_open_orders(self) -> List[Dict]:
        """获取现货未完成订单（优先使用 WebSocket，失败回退到 REST）"""
        # 优先使用 fetchOpenOrdersWs（WebSocket 方式）
        if self._ws_client and self._event_loop and self._event_loop.is_running():
            try:
                print(f"{self._get_log_prefix()} 🔍 [WS] 查询未完成订单: {self._market_symbol}")
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
            print(f"{self._get_log_prefix()} 🔍 [REST] 查询未完成订单: {self._market_symbol}")
            orders = self.client.fetch_open_orders(self._market_symbol)
            print(f"{self._get_log_prefix()} 🔍 [REST] 查询到 {len(orders)} 笔未完成订单")
            return self._adapt_orders(orders)
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 获取未完成订单失败: {e}")
            traceback.print_exc()
            return []

    def _adapt_orders(self, orders: List) -> List[Dict]:
        """将 ccxt 订单格式转换为统一格式"""
        adapted = []
        for o in orders:
            status = self._map_status(o.get("status"))
            order_data = {
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
            adapted.append(order_data)
            print(f"{self._get_log_prefix()} 📋 订单: id={order_data['orderId']}, side={order_data['side']}, price={order_data['price']}, qty={order_data['origQty']}, status={status}")
        print(f"{self._get_log_prefix()} ✅ 获取到{len(adapted)}个未完成订单")
        return adapted

    def get_order(self, order_id: str) -> Dict:
        """查询现货订单状态"""
        print(f"{self._get_log_prefix()} 🔍 查询订单: {order_id}")
        try:
            o = self.client.fetch_order(order_id, self._market_symbol)
            status = self._map_status(o.get("status"))
            result = {
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
            print(f"{self._get_log_prefix()} ✅ 订单状态: id={order_id}, status={status}, filled={result['executedQty']}")
            return result
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 查询订单失败: {e}")
            traceback.print_exc()
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
        """现货限价买单"""
        print(f"{self._get_log_prefix()} 📤 下买单: quantity={quantity}, price={price}, kwargs={kwargs}")
        try:
            o = self.client.create_limit_buy_order(
                self._market_symbol,
                quantity,
                float(price),
                params={"timeInForce": kwargs.get("timeInForce", "GTC")}
            )
            order_id = str(o.get("id"))
            print(f"{self._get_log_prefix()} ✅ 买单成功: orderId={order_id}")
            print(f"{self._get_log_prefix()} 🔍 订单详情: {o}")
            return {"orderId": order_id, "id": order_id, **(o or {})}
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 下买单失败: {e}")
            traceback.print_exc()
            raise

    def order_limit_sell(self, quantity: float, price: str, **kwargs) -> Dict:
        """现货限价卖单"""
        print(f"{self._get_log_prefix()} 📤 下卖单: quantity={quantity}, price={price}, kwargs={kwargs}")
        try:
            o = self.client.create_limit_sell_order(
                self._market_symbol,
                quantity,
                float(price),
                params={"timeInForce": kwargs.get("timeInForce", "GTC")}
            )
            order_id = str(o.get("id"))
            print(f"{self._get_log_prefix()} ✅ 卖单成功: orderId={order_id}")
            print(f"{self._get_log_prefix()} 🔍 订单详情: {o}")
            return {"orderId": order_id, "id": order_id, **(o or {})}
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 下卖单失败: {e}")
            traceback.print_exc()
            raise

    def cancel_order(self, order_id: str) -> Dict:
        """取消现货订单"""
        print(f"{self._get_log_prefix()} 🗑️ 取消订单: {order_id}")
        try:
            o = self.client.cancel_order(order_id, self._market_symbol)
            print(f"{self._get_log_prefix()} ✅ 取消订单成功: {order_id}")
            return {"orderId": str(o.get("id")), "id": str(o.get("id")), **(o or {})}
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 取消订单失败: {e}")
            traceback.print_exc()
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
        print(f"{self._get_log_prefix()} 🔄 取消并替换订单: cancel_id={cancel_order_id}, side={side}, qty={quantity}, price={price}")
        
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
            print(f"{self._get_log_prefix()} ✅ 旧订单已取消")
        except Exception as e:
            # 订单可能已成交或已取消，忽略
            print(f"{self._get_log_prefix()} ⚠️ 取消旧订单失败（可能已成交）: {e}")

        # 创建新订单
        if str(side).upper() == "BUY":
            new_order = self.order_limit_buy(quantity=quantity, price=price, **kwargs)
        else:
            new_order = self.order_limit_sell(quantity=quantity, price=price, **kwargs)

        print(f"{self._get_log_prefix()} ✅ 新订单已创建: {new_order.get('orderId')}")
        return {
            "cancelResult": "SUCCESS",
            "newOrderResult": "SUCCESS",
            "newOrderResponse": new_order,
        }

    def _get_price_precision(self, symbol_info: Dict) -> Tuple[float, int]:
        """从现货交易对信息中提取价格精度（内部使用）"""
        prec = (symbol_info or {}).get("precision", {})
        limits = (symbol_info or {}).get("limits", {})
        
        # 调试日志
        print(f"{self._get_log_prefix()} 🔍 价格精度信息: precision={prec}, limits={limits}")
        
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
        
        print(f"{self._get_log_prefix()} 🔍 价格精度计算结果: tick_size={tick_size}, price_decimals={price_decimals}")
        return float(tick_size), price_decimals

    def _get_quantity_precision(self, symbol_info: Dict) -> Tuple[float, int]:
        """从现货交易对信息中提取数量精度（内部使用）"""
        prec = (symbol_info or {}).get("precision", {})
        qty_decimals = int(prec.get("amount") or 3)
        step_size = 10 ** (-qty_decimals)
        print(f"{self._get_log_prefix()} 🔍 数量精度: qty_decimals={qty_decimals}, step_size={step_size}")
        return float(step_size), qty_decimals

    def get_trading_rules(self) -> Dict:
        """获取交易规则（精度信息）"""
        print(f"{self._get_log_prefix()} 🔍 获取交易规则...")
        symbol_info = self._get_symbol_info()
        tick_size, price_decimals = self._get_price_precision(symbol_info)
        step_size, qty_decimals = self._get_quantity_precision(symbol_info)
        rules = {
            'tick_size': tick_size,
            'price_decimals': price_decimals,
            'step_size': step_size,
            'qty_decimals': qty_decimals
        }
        print(f"{self._get_log_prefix()} ✅ 交易规则: {rules}")
        return rules

    # ====================== WebSocket 监控（ccxt pro 真正 WS） ======================
    def start_ws(
        self,
        on_price_update: Callable[[float], None],
        on_order_update: Callable[[Dict], None],
    ) -> bool:
        """启动 WebSocket 监控（使用 ccxt pro 的 watchTicker / watchOrders）"""
        print(f"{self._get_log_prefix()} 🚀 准备启动WebSocket监控...")
        
        with self._monitor_lock:
            if self._monitor_running:
                print(f"{self._get_log_prefix()} ⚠️ WebSocket监控已在运行")
                return True
            self._monitor_running = True

        def _run_ws_loop():
            prefix = self._get_log_prefix()
            print(f"{prefix} 🚀 WebSocket 监控线程已启动（ccxt pro）")

            # 创建新的事件循环
            self._event_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._event_loop)
            print(f"{self._get_log_prefix()} 🔧 事件循环已创建")

            # 创建异步客户端
            self._ws_client = self._create_ws_client(self.api_key, self.api_secret, self.testnet)
            print(f"{self._get_log_prefix()} ✅ WebSocket客户端已创建")

            async def watch_ticker():
                """watchTicker 实时价格推送"""
                print(f"{self._get_log_prefix()} 🔌 启动价格监控: {self._market_symbol}")
                update_count = 0
                msg_count = 0
                last_log_time = time.time()
                start_time = time.time()
                
                while self._monitor_running:
                    try:
                        ticker = await self._ws_client.watch_ticker(self._market_symbol)
                        msg_count += 1
                        price = ticker.get("last") or ticker.get("close")
                        
                        if price is not None:
                            p = float(price)
                            with self._last_price_lock:
                                price_changed = self._last_price is None or abs(p - self._last_price) > 1e-12
                                if price_changed:
                                    self._last_price = p
                                    update_count += 1
                                
                                # 每 10 秒打印一次日志
                                now = time.time()
                                if now - last_log_time >= 10:
                                    elapsed = now - start_time
                                    msg_rate = msg_count / elapsed if elapsed > 0 else 0
                                    change_rate = update_count / elapsed if elapsed > 0 else 0
                                    print(f"{self._get_log_prefix()} 📊 价格={p} | WS消息: {msg_count}条 ({msg_rate:.1f}/秒) | 价格变化: {update_count}次 ({change_rate:.2f}/秒)")
                                    last_log_time = now
                                
                                if price_changed and on_price_update:
                                    on_price_update(p)
                    except asyncio.CancelledError:
                        print(f"{self._get_log_prefix()} 🛑 价格监控被取消")
                        break
                    except Exception as e:
                        if self._monitor_running:
                            error_key = f"watch_ticker_{type(e).__name__}"
                            if self._should_log_error(error_key):
                                print(f"{self._get_log_prefix()} ⚠️ watchTicker 错误: {e}")
                                traceback.print_exc()
                            await asyncio.sleep(1)

            async def watch_orders():
                """监听订单更新（watchOrders）"""
                print(f"{self._get_log_prefix()} 🔌 启动订单监控: {self._market_symbol}")
                
                while self._monitor_running:
                    try:
                        orders = await self._ws_client.watch_orders(self._market_symbol)
                        print(f"{self._get_log_prefix()} 📨 收到订单更新: {len(orders)}条")
                        
                        for o in orders:
                            order_id = str(o.get("id"))
                            raw_status = o.get("status")
                            status = self._map_status(raw_status)
                            side = str(o.get("side", "")).upper()
                            price = o.get("price")
                            amount = o.get("amount")
                            filled = o.get("filled")
                            fee = o.get("fee", {})

                            # 打印详细订单事件
                            print(f"{self._get_log_prefix()} 📨 订单事件详情:")
                            print(f"    - order_id: {order_id}")
                            print(f"    - status: {raw_status} -> {status}")
                            print(f"    - side: {side}")
                            print(f"    - price: {price}")
                            print(f"    - amount: {amount}")
                            print(f"    - filled: {filled}")
                            print(f"    - fee: {fee}")
                            print(f"    - raw: {o}")

                            # 现货手续费判断
                            # 如果用 BNB 支付手续费，则不从交易币种中扣除
                            fee_currency = fee.get("currency", "") if fee else ""
                            fee_paid_externally = (fee_currency == "BNB")
                            print(f"    - fee_currency: {fee_currency}, fee_paid_externally: {fee_paid_externally}")

                            if status == "CANCELED":
                                print(f"{self._get_log_prefix()} 🗑️ 订单已取消: {order_id}")
                                if on_order_update:
                                    on_order_update({
                                        "event_type": "order_cancelled",
                                        "order_id": order_id,
                                        "symbol": self.symbol,
                                        "side": side,
                                        "status": status,
                                    })
                            elif status == "FILLED":
                                print(f"{self._get_log_prefix()} ✅ 订单已成交: {order_id}")
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
                                print(f"{self._get_log_prefix()} 📋 订单状态更新: {order_id} -> {status}")
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
                    except asyncio.CancelledError:
                        print(f"{self._get_log_prefix()} 🛑 订单监控被取消")
                        break
                    except Exception as e:
                        if self._monitor_running:
                            error_key = f"watch_orders_{type(e).__name__}"
                            if self._should_log_error(error_key):
                                print(f"{self._get_log_prefix()} ⚠️ watchOrders 错误: {e}")
                                traceback.print_exc()
                            await asyncio.sleep(1)

            async def run_all():
                """watchTicker 和 watchOrders 并行运行"""
                print(f"{self._get_log_prefix()} 🔌 启动并行监控任务...")
                try:
                    await asyncio.gather(watch_ticker(), watch_orders())
                except asyncio.CancelledError:
                    print(f"{self._get_log_prefix()} 🛑 监控任务被取消")
                except Exception as e:
                    print(f"{self._get_log_prefix()} ❌ WebSocket 运行错误: {e}")
                    traceback.print_exc()
                finally:
                    print(f"{self._get_log_prefix()} 🔌 关闭WebSocket客户端...")
                    if self._ws_client:
                        await self._ws_client.close()
                    print(f"{self._get_log_prefix()} ✅ WebSocket客户端已关闭")

            try:
                self._event_loop.run_until_complete(run_all())
            except Exception as e:
                print(f"{self._get_log_prefix()} ❌ 事件循环错误: {e}")
                traceback.print_exc()
            finally:
                if self._event_loop:
                    self._event_loop.close()
                    self._event_loop = None
                print(f"{self._get_log_prefix()} ◼️ WebSocket 监控线程已停止")

        self._monitor_thread = threading.Thread(target=_run_ws_loop, daemon=True, name=f"CcxtBinanceWS-{self.symbol}")
        self._monitor_thread.start()
        print(f"{self._get_log_prefix()} ✅ WebSocket监控线程已启动: {self._monitor_thread.name}")
        time.sleep(0.5)  # 等待线程启动
        return True

    def stop_ws(self) -> None:
        """停止 WebSocket 监控"""
        print(f"{self._get_log_prefix()} 🛑 停止WebSocket监控...")
        
        with self._monitor_lock:
            self._monitor_running = False

        # 尝试取消事件循环中的任务
        if self._event_loop and self._event_loop.is_running():
            print(f"{self._get_log_prefix()} 🔧 停止事件循环...")
            self._event_loop.call_soon_threadsafe(self._event_loop.stop)

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
        
        print(f"{self._get_log_prefix()} ✅ WebSocket监控已停止")

    def check_pending_orders(self, pending_orders: List[Dict]):
        """检查待处理订单的状态（用于 HTTP 轮询模式）
        
        Note:
            使用 WebSocket 实时监控订单时，此方法不需要实际操作
            保留此方法是为了满足基类接口要求
        """
        if not pending_orders:
            return
            
        print(f"{self._get_log_prefix()} 🔍 检查{len(pending_orders)}个待处理订单...")
        for o in pending_orders:
            order_id = o.get("order_id")
            if not order_id:
                continue
            try:
                self.get_order(str(order_id))
            except Exception as e:
                print(f"{self._get_log_prefix()} ⚠️ 检查订单{order_id}失败: {e}")

    # ====================== 费率相关 ======================
    def _get_trade_fee(self, symbol: str) -> Dict[str, float]:
        """获取现货交易对的手续费率（带缓存）"""
        symbol = symbol.upper()
        print(f"{self._get_log_prefix()} 🔍 获取交易费率: {symbol}")

        with self._fee_cache_lock:
            if symbol in self._fee_cache:
                cached = self._fee_cache[symbol]
                print(f"{self._get_log_prefix()} 🔍 使用缓存费率: {cached}")
                return cached

        # 尝试从API获取费率
        try:
            # ccxt 获取交易费率
            markets = self.client.load_markets()
            market = markets.get(self._market_symbol, {})
            maker_fee = float(market.get("maker", 0.001))
            taker_fee = float(market.get("taker", 0.001))
            print(f"{self._get_log_prefix()} 🔍 从市场信息获取费率: maker={maker_fee}, taker={taker_fee}")
        except Exception as e:
            print(f"{self._get_log_prefix()} ⚠️ 获取费率失败，使用默认值: {e}")
            # 现货默认费率: maker 0.1%, taker 0.1%
            maker_fee = 0.001
            taker_fee = 0.001

        fee_data = {"maker_fee": maker_fee, "taker_fee": taker_fee}

        with self._fee_cache_lock:
            self._fee_cache[symbol] = fee_data

        print(f"{self._get_log_prefix()} 💰 {symbol} 现货费率: maker={maker_fee*100}%, taker={taker_fee*100}%")
        return fee_data

    def calculate_sell_price(self, buy_price, sell_offset_percent, tick_size, price_decimals, current_price=None):
        """计算卖出价格（基于实际账户费率）"""
        print(f"{self._get_log_prefix()} 🔍 计算卖出价格: buy_price={buy_price}, offset={sell_offset_percent}%, tick={tick_size}, decimals={price_decimals}, current={current_price}")
        
        sell_offset = sell_offset_percent / 100.0
        raw_sell_price = (current_price or buy_price) * (1 + sell_offset)

        fee_data = self._get_trade_fee(self.symbol)
        total_fee_rate = fee_data["maker_fee"] * 2  # 买卖双边

        min_price = buy_price * (1 + total_fee_rate)
        min_price = math.ceil(min_price / tick_size) * tick_size if tick_size else min_price
        min_price = round(min_price, price_decimals)

        sell_price = max(raw_sell_price, min_price)
        sell_price = math.ceil(sell_price / tick_size) * tick_size if tick_size else sell_price
        sell_price = round(sell_price, price_decimals)

        if sell_price <= buy_price and tick_size:
            sell_price = round(buy_price + tick_size, price_decimals)

        print(f"{self._get_log_prefix()} ✅ 计算结果: raw={raw_sell_price}, min={min_price}, final={sell_price}")
        return sell_price

    def get_fee_rate(self) -> float:
        """获取交易对的手续费率（重写基类方法）"""
        fee_data = self._get_trade_fee(self.symbol)
        return fee_data["maker_fee"]

    # ====================== 现货特有方法（可选使用） ======================
    def get_account_balance(self, asset: str = "USDT") -> Dict:
        """获取现货账户余额"""
        print(f"{self._get_log_prefix()} 🔍 获取账户余额: {asset}")
        try:
            balance = self.client.fetch_balance()
            asset_balance = balance.get(asset, {})
            result = {
                "asset": asset,
                "balance": float(asset_balance.get("total", 0)),
                "availableBalance": float(asset_balance.get("free", 0)),
            }
            print(f"{self._get_log_prefix()} ✅ 余额: total={result['balance']}, available={result['availableBalance']}")
            return result
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 获取余额失败: {e}")
            traceback.print_exc()
            return {"asset": asset, "balance": 0, "availableBalance": 0}
