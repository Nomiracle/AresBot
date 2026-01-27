"""
Short Futures Adapter - 做空适配器

继承 CcxtFuturesAdapter，重写必要方法实现做空功能：
- order_limit_buy() → 实际执行卖出开仓（做空）
- order_limit_sell() → 实际执行买入平仓

使用方式与 CcxtFuturesAdapter 完全相同，只是交易方向相反。
"""
import asyncio
import math
from datetime import datetime
from typing import Dict, List, Callable
from .ccxt_binance_futures_adapter import CcxtBinanceFutures


class CcxtBinanceFuturesShort(CcxtBinanceFutures):
    """做空适配器（继承 CcxtFuturesAdapter）
    
    重写买卖方法，反转交易方向：
    - trading.py 调用 buy → 实际执行 sell（做空开仓）
    - trading.py 调用 sell → 实际执行 buy（做空平仓）
    """
    
    def _get_log_prefix(self) -> str:
        """重写日志前缀（标识为做空模式）"""
        api_key_short = self.api_key[:6] if self.api_key else "NOKEY"
        return f"[{datetime.now().isoformat()}] [SHORT-{api_key_short}-{self.symbol}]"
    
    @classmethod
    def get_exchange_info(cls) -> Dict:
        """获取交易所信息（类方法）"""
        return {
            'id': 'ccxt_binance_futures_short',
            'name': '币安-合约-做空',
            'description': 'Binance Futures Short Trading (CCXT)'
        }
    
    # ====================== 核心：反转买卖方向 ======================
    
    def order_limit_buy(self, quantity: float, price: str, **kwargs) -> Dict:
        """合约限价买单（做空开仓）
        
        Args:
            quantity: 下单数量
            price: 目标价格
            **kwargs: 
                current_price: 当前价格（可选，用于价格方向检查）
                timeInForce: 订单有效期
        
        方向检查：做空开仓 = 卖出，目标价应该 >= 当前价（挂高价等待反弹）
        """
        try:
            target_price = float(price)
            
            # 价格方向检查（如果传入了 current_price）
            current_price = kwargs.get('current_price')
            if current_price is not None:
                try:
                    current_price = float(current_price)
                    # 做空开仓：卖出应该挂高价（>= 当前价），等待价格上涨到目标价时成交
                    if target_price < current_price: 
                        raise ValueError(
                            f"做空开仓价格方向错误: 目标价={target_price:.6f} 明显低于当前价={current_price:.6f}，"
                            f"做空开仓应该挂高价等待反弹（目标价 >= 当前价）"
                        )
                except ValueError:
                    raise  # 重新抛出价格方向错误
                except Exception as check_e:
                    print(f"{self._get_log_prefix()} ⚠️ 价格检查失败（继续下单）: {check_e}")
            
            o = self.client.create_limit_sell_order(
                self._market_symbol,
                quantity,
                target_price,
                params={"timeInForce": kwargs.get("timeInForce", "GTC")}
            )
            return {"orderId": str(o.get("id")), "id": str(o.get("id")), **(o or {})}
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 下买单失败: {e}")
            raise

    def order_limit_sell(self, quantity: float, price: str, **kwargs) -> Dict:
        """合约限价卖单（做空平仓）
        
        Args:
            quantity: 下单数量
            price: 目标价格
            **kwargs:
                current_price: 当前价格（可选，用于价格方向检查）
                entry_price: 开仓价格（可选，用于盈利检查）
                timeInForce: 订单有效期
        
        方向检查：
        1. 做空平仓 = 买入，目标价应该 <= 当前价（挂低价等待回落）
        """
        try:
            target_price = float(price)
            print(f"{self._get_log_prefix()} ℹ️ 做空平仓不做盈利校验: target_price={target_price}")
            
            # 价格方向检查（如果传入了 current_price 或 entry_price）
            current_price = kwargs.get('current_price')
            entry_price = kwargs.get('entry_price')
            
            if current_price is not None or entry_price is not None:
                try:
                    # 检查1：做空平仓应该挂低价（<= 当前价）
                    if current_price is not None:
                        current_price = float(current_price)
                        if target_price > current_price:
                            raise ValueError(
                                f"做空平仓价格方向错误: 目标价={target_price:.6f} 明显高于当前价={current_price:.6f}，"
                                f"做空平仓应该挂低价等待回落（目标价 <= 当前价）"
                            )
                except ValueError:
                    raise  # 重新抛出价格方向错误
                except Exception as check_e:
                    print(f"{self._get_log_prefix()} ⚠️ 价格检查失败（继续下单）: {check_e}")
            
            o = self.client.create_limit_buy_order(
                self._market_symbol,
                quantity,
                target_price,
                params={"timeInForce": kwargs.get("timeInForce", "GTC")}
            )
            return {"orderId": str(o.get("id")), "id": str(o.get("id")), **(o or {})}
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 下卖单失败: {e}")
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
        
        # 虚拟订单（持仓映射）：跳过取消，直接下新单
        if self._is_virtual_order(cancel_order_id):
            print(f"{self._get_log_prefix()} 📍 虚拟订单 {cancel_order_id}，直接下新单")
            
            # 虚拟订单价格方向检查（如果传入了 current_price）
            current_price = kwargs.get('current_price')
            if current_price is not None:
                try:
                    target_price = float(price)
                    current_price = float(current_price)
                    
                    if str(side).upper() == "BUY":
                        # BUY = 做空开仓，应该挂高价
                        if target_price < current_price:
                            raise ValueError(
                                f"虚拟订单开仓价格错误: 目标价={target_price:.6f} < 当前价={current_price:.6f}，"
                                f"做空开仓应该挂高价（>= 当前价）"
                            )
                    else:
                        # SELL = 做空平仓，应该挂低价
                        if target_price > current_price:
                            raise ValueError(
                                f"虚拟订单平仓价格错误: 目标价={target_price:.6f} > 当前价={current_price:.6f}，"
                                f"做空平仓应该挂低价（<= 当前价）"
                            )
                except ValueError:
                    raise  # 重新抛出价格方向错误
                except Exception as check_e:
                    print(f"{self._get_log_prefix()} ⚠️ 虚拟订单价格检查失败（继续下单）: {check_e}")
            
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

                original_side = side
                if original_side == "BUY":
                    side = "sell"  # 小写，父类会转大写
                elif original_side == "SELL":
                    side = "buy"

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
                
                # 检查是否为超过修改次数限制的错误
                error_str = str(e)
                if "-5026" in error_str or "Exceed maximum modify order limit" in error_str:
                    print(f"{self._get_log_prefix()} ⚠️ 检测到超过修改次数限制，回退到取消+新建模式")
                else:
                    print(f"{self._get_log_prefix()} 🔄 editOrderWs 失败，回退到取消+新建模式")
        
        # 回退到取消+新建模式（或直接使用此模式）
        try:
            # 步骤1: 取消原订单
            print(f"{self._get_log_prefix()} 🚫 步骤1: 取消订单 {cancel_order_id}")
            cancel_result = self.cancel_order(cancel_order_id)
            print(f"{self._get_log_prefix()} ✅ 订单取消成功: {cancel_order_id}")
            
            # 步骤2: 创建新订单
            print(f"{self._get_log_prefix()} 📝 步骤2: 创建新订单 price={price}, quantity={quantity}")
            
            # 做空策略：需要反转 side
            original_side = side
            if original_side == "BUY":
                new_order = self.order_limit_buy(quantity=quantity, price=price, **kwargs)
            else:
                new_order = self.order_limit_sell(quantity=quantity, price=price, **kwargs)
            
            new_order_id = str(new_order.get('orderId') or new_order.get('id'))
            print(f"{self._get_log_prefix()} ✅ 新订单创建成功: {new_order_id}")
            
            # 返回标准格式的结果
            return {
                "cancelResult": "SUCCESS",
                "newOrderResult": "SUCCESS", 
                "newOrderResponse": new_order
            }
            
        except Exception as fallback_error:
            print(f"{self._get_log_prefix()} ❌ 取消+新建模式失败: {fallback_error}")
            raise fallback_error
    
    # ====================== 订单相关：反转 side ======================
    
    def get_open_orders(self) -> List[Dict]:
        """获取未完成订单（反转 side，使 trading.py 逻辑兼容做空）
        
        做空策略中：
        - 实际 SELL 订单（开仓）→ 返回为 BUY（对应 trading.py 的 open_buy_orders）
        - 实际 BUY 订单（平仓）→ 返回为 SELL（对应 trading.py 的 open_sell_orders）
        - 虚拟订单也需要反转：父类生成的是做多语义，需要转换为做空语义
          空单持仓 → 父类生成 BUY → 反转为 SELL（平仓单）
        """
        orders = super().get_open_orders()
        
        # 反转每个订单的 side（包括虚拟订单）
        for order in orders:
            original_side = str(order.get('side', '')).upper()
            if original_side == 'BUY':
                order['side'] = 'SELL'
            elif original_side == 'SELL':
                order['side'] = 'BUY'
        
        return orders
    
    def get_open_ordersv2(self) -> List['ExchangeOrder']:
        """获取真实未完成订单（v2专用，不含虚拟订单，反转side）
        
        只返回真实的开放订单，不做持仓映射，但需要反转side以兼容做空逻辑
        """
        from trading_system.domain import ExchangeOrder
        from dataclasses import replace
        
        orders = super().get_open_ordersv2()
        
        # 反转每个订单的 side（使用dataclass的replace创建新实例）
        reversed_orders = []
        for order in orders:
            new_side = 'SELL' if order.side == 'BUY' else 'BUY'
            reversed_orders.append(replace(order, side=new_side))
        
        return reversed_orders
    
    def get_open_positionv2(self) -> List['PositionInfo']:
        """获取当前活跃仓位（v2专用）
        
        返回当前持仓信息，做空适配器直接复用父类
        """
        return super().get_open_positionv2()
    
    def _process_order_event(self, o: Dict, on_order_update):
        """处理订单事件（反转 side，使 trading.py 逻辑兼容做空）
        
        做空策略中：
        - 实际 SELL 订单（开仓）→ 事件中 side 改为 BUY
        - 实际 BUY 订单（平仓）→ 事件中 side 改为 SELL
        """
        # 反转 side 后调用父类处理
        original_side = str(o.get("side", "")).upper()
        if original_side == "BUY":
            o["side"] = "sell"  # 小写，父类会转大写
        elif original_side == "SELL":
            o["side"] = "buy"
        
        super()._process_order_event(o, on_order_update)
    
    
    # _position_to_virtual_orders 不需要重写
    # 父类生成的虚拟订单 side 已经正确（空单→BUY平仓，多单→SELL平仓）
    # 会在 get_open_orders 中统一反转，避免双重反转导致抵消
    
    # ====================== 价格计算反转 ======================
    
    def calculate_sell_price(self, buy_price, sell_offset_percent, tick_size, price_decimals, current_price=None):
        """计算平仓价格（做空时：平仓价 < 开仓价）"""
        sell_offset = sell_offset_percent / 100.0
        # 做空平仓：目标价 = 开仓价 * (1 - offset)
        raw_close_price = (current_price or buy_price) * (1 - sell_offset)
        
        # 最高保护价（开仓价 - 2倍手续费，确保盈利）
        max_price = buy_price * (1 - 2 * self.get_fee_rate())
        max_price = math.floor(max_price / tick_size) * tick_size if tick_size else max_price
        max_price = round(max_price, price_decimals)
        
        # 最终平仓价（取较小值，确保盈利）
        close_price = min(raw_close_price, max_price)
        close_price = math.ceil(close_price / tick_size) * tick_size if tick_size else close_price
        return round(close_price, price_decimals)
    
    def calculate_buy_target_price(self, current_price, offset_percent, tick_size, price_decimals):
        """计算开仓目标价格（做空时：开仓价 > 当前价）"""
        offset = offset_percent / 100.0
        # 做空开仓：目标价 = 当前价 * (1 - offset)
        # offset 通常为负数如 -0.1，所以 1 - (-0.001) = 1.001，卖出价高于当前价
        target_price = current_price * (1 - offset)
        
        # 按 tick_size 对齐（做空向上取整，确保能成交）
        if tick_size and tick_size > 0:
            target_price = math.ceil(target_price / tick_size) * tick_size
        
        target_price = round(target_price, price_decimals)
        return target_price
    
    def calculate_price_diff_stats(self, current_price: float, target_price: float, 
                                   min_diff: float, max_diff: float, 
                                   avg_diff: float) -> list:
        """计算价格差值统计 (做空逻辑)
        
        做空交易所的差值计算与做多相反:
        - 差值 = (目标价 - 现价) / 现价 * 100
        - 开仓(卖出): 目标价 > 现价, diff > 0, 越小越接近成交
        - 平仓(买入): 目标价 < 现价, diff < 0, 绝对值越小越接近成交
        
        Args:
            current_price: 当前市场价格
            target_price: 目标挂单价格
            min_diff: 当前最小差值 (可为 None)
            max_diff: 当前最大差值 (可为 None)
            avg_diff: 当前平均差值 (可为 None)
        
        Returns:
            [新最小差值, 新平均差值, 新最大差值]
        """
        if not target_price or current_price <= 0:
            return [min_diff, avg_diff, max_diff]
        
        # 做空计算差值百分比: (目标价 - 现价) / 现价 * 100 (与做多相反)
        price_diff_percent = ((target_price - current_price) / current_price) * 100
        
        # 更新最小差值(绝对值最小)
        if min_diff is None:
            new_min = price_diff_percent
        else:
            new_min = price_diff_percent if abs(price_diff_percent) < abs(min_diff) else min_diff
        
        # 更新最大差值(绝对值最大)
        if max_diff is None:
            new_max = price_diff_percent
        else:
            new_max = price_diff_percent if abs(price_diff_percent) > abs(max_diff) else max_diff
        
        # 更新平均差值(移动平均)
        if avg_diff is None:
            new_avg = price_diff_percent
        else:
            new_avg = (avg_diff + price_diff_percent) / 2
        
        return [new_min, new_avg, new_max]
