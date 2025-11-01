"""
Backpack (BPX) 交易所适配器
基于 bpx-py SDK
"""
from datetime import datetime
from typing import Dict, List, Optional, Callable
import math
from .base import BaseExchange

try:
    from bpx.account import Account
    from bpx.public import Public
except ImportError:
    print("⚠️ 请安装 bpx-py: pip install bpx-py")
    Account = None
    Public = None


class BackpackAdapter(BaseExchange):
    """Backpack 交易所适配器"""
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        """初始化 Backpack 客户端
        
        Args:
            api_key: API 公钥 (Base58 格式)
            api_secret: API 私钥 (Base64 编码的 Ed25519 私钥)
            testnet: 是否使用测试网（Backpack 暂不支持测试网，此参数保留）
        
        注意：
        - public_key: Backpack 账户的公钥，格式如 "5xN..."
        - secret_key: 必须是 base64 编码的私钥字符串
        """
        if Account is None or Public is None:
            raise ImportError("请先安装 bpx-py: pip install bpx-py")
        
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        
        try:
            # 初始化账户客户端（私有 API）
            # secret_key 必须是 base64 编码的字符串
            self.account = Account(
                public_key=api_key,
                secret_key=api_secret,
                debug=False,
                window=5000
            )
            
            # 初始化公共客户端（公共 API）
            self.public = Public()
            
            # 缓存市场信息
            self._markets_cache = None
            
            print(f"[{datetime.now().isoformat()}] ✅ [Backpack] 客户端初始化成功")
            
        except Exception as e:
            error_msg = str(e)
            if "Incorrect padding" in error_msg or "Invalid base64" in error_msg:
                raise ValueError(
                    f"Backpack API Secret 格式错误！\n"
                    f"错误: {error_msg}\n"
                    f"请确保 API Secret 是 base64 编码的私钥。\n"
                    f"提示：在 Backpack 后台生成 API 密钥时，会提供 base64 格式的 Secret Key。"
                )
            raise
        
        print(f"[{datetime.now().isoformat()}] ✅ [Backpack] 适配器初始化成功")
    
    def ping(self) -> bool:
        """测试连接"""
        try:
            result = self.public.get_ping()
            return result is not None
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Backpack] Ping 失败: {e}")
            return False
    
    def _get_markets(self) -> List[Dict]:
        """获取所有市场信息（带缓存）"""
        if self._markets_cache is None:
            try:
                self._markets_cache = self.public.get_markets()
            except Exception as e:
                print(f"[{datetime.now().isoformat()}] ❌ [Backpack] 获取市场信息失败: {e}")
                return []
        return self._markets_cache or []
    
    def _check_api_error(self, result, operation: str = "API调用") -> bool:
        """检查API响应是否包含错误
        
        Args:
            result: API响应结果
            operation: 操作描述，用于日志
            
        Returns:
            True 如果是错误响应，False 如果正常
        """
        if isinstance(result, dict) and 'code' in result and 'message' in result:
            error_code = result.get('code')
            error_msg = result.get('message')
            print(f"[{datetime.now().isoformat()}] ❌ [Backpack] {operation}失败: {error_code} - {error_msg}")
            
            # 针对常见错误给出建议
            if error_code == 'INSUFFICIENT_FUNDS':
                print(f"[{datetime.now().isoformat()}] 💡 [Backpack] 账户余额不足，请充值")
            elif error_code == 'INVALID_CLIENT_REQUEST' and 'signature' in error_msg.lower():
                print(f"[{datetime.now().isoformat()}] 💡 [Backpack] 签名错误，请检查 API 密钥配置")
            elif 'unauthorized' in error_msg.lower():
                print(f"[{datetime.now().isoformat()}] 💡 [Backpack] 认证失败，请检查 API 密钥")
            elif 'rate limit' in error_msg.lower():
                print(f"[{datetime.now().isoformat()}] 💡 [Backpack] API 请求频率超限，请稍后重试")
            
            return True
        return False
    
    def _convert_symbol(self, symbol: str) -> str:
        """转换交易对格式
        
        Binance 格式: BTCUSDT, ETHUSD
        Backpack 格式: BTC_USDC, ETH_USDC
        
        注意：
        - Backpack 只支持 USDC 作为计价货币
        - 前端显示 USD，但 API 使用 USDC
        - 自动将 USDT 和 USD 转换为 USDC
        """
        # 如果已经是 Backpack 格式，检查是否需要转换计价货币
        if '_' in symbol:
            parts = symbol.split('_')
            if len(parts) == 2:
                base, quote = parts
                # USD 或 USDT 转换为 USDC
                if quote in ['USD', 'USDT']:
                    converted = f"{base}_USDC"
                    print(f"[{datetime.now().isoformat()}] 🔄 [Backpack] 转换计价货币: {symbol} -> {converted}")
                    return converted
            return symbol
        
        # Backpack 使用 USDC，将 USDT 和 USD 都转换为 USDC
        # BTCUSDT -> BTC_USDC
        # BTCUSD -> BTC_USDC (前端显示 USD，API 用 USDC)
        # ETHUSDT -> ETH_USDC
        if symbol.endswith('USDT'):
            base = symbol[:-4]  # 移除 USDT
            return f"{base}_USDC"
        
        if symbol.endswith('USD'):
            base = symbol[:-3]  # 移除 USD
            return f"{base}_USDC"
        
        # 处理已经是 USDC 的情况
        # BTCUSDC -> BTC_USDC
        if symbol.endswith('USDC'):
            base = symbol[:-4]
            return f"{base}_USDC"
        
        # 如果无法识别，返回原值
        print(f"[{datetime.now().isoformat()}] ⚠️ [Backpack] 无法转换交易对格式: {symbol}")
        print(f"[{datetime.now().isoformat()}] 💡 [Backpack] 提示: Backpack 只支持 USDC 计价，请使用如 BTCUSDC 或 BTCUSD 格式")
        return symbol
    
    def get_symbol_info(self, symbol: str) -> Dict:
        """获取交易对信息"""
        try:
            bpx_symbol = self._convert_symbol(symbol)
            markets = self._get_markets()
            
            for market in markets:
                if market.get('symbol') == bpx_symbol:
                    return market
                print(f"[{datetime.now().isoformat()}] ⚠️ [Backpack] 交易对 {market.get('symbol')} 不存在：{bpx_symbol}")
            
            print(f"[{datetime.now().isoformat()}] ⚠️ [Backpack] 交易对 {bpx_symbol} 不存在")
            return None
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Backpack] 获取交易对信息失败 ({symbol}): {e}")
            return None
    
    def get_symbol_ticker(self, symbol: str) -> Dict:
        """获取交易对实时价格
        
        优先使用订单簿获取最实时的买一价格，失败则使用 ticker 的最新成交价
        """
        try:
            bpx_symbol = self._convert_symbol(symbol)
            
            # 方法1: 尝试从订单簿获取买一价格（最实时）
            try:
                depth = self.public.get_depth(bpx_symbol)
                if depth and 'asks' in depth and len(depth['asks']) > 0:
                    # 卖一价格 [price, quantity] - 这是买入时的最低价格
                    best_ask = depth['asks'][0][0]
                    print(f"[{datetime.now().isoformat()}] 💰 [Backpack] 从订单簿获取实时价格(卖一): {best_ask}")
                    return {
                        'symbol': bpx_symbol,
                        'price': best_ask
                    }
            except AttributeError:
                # get_depth 方法不存在，继续使用 ticker
                print(f"[{datetime.now().isoformat()}] ℹ️ [Backpack] SDK 不支持 get_depth，使用 ticker")
            except Exception as depth_error:
                print(f"[{datetime.now().isoformat()}] ⚠️ [Backpack] 获取订单簿失败: {depth_error}，回退到 ticker")
            
            # 方法2: 使用 ticker 的最新成交价（实时价格）
            ticker = self.public.get_ticker(bpx_symbol)
            
            # 检查是否是错误响应
            if self._check_api_error(ticker, "获取价格"):
                return None
            
            if ticker and 'lastPrice' in ticker:
                price_value = ticker['lastPrice']
                print(f"[{datetime.now().isoformat()}] 💰 [Backpack] 从 ticker 获取实时价格(最新成交): {price_value}")
                return {
                    'symbol': bpx_symbol,
                    'price': price_value
                }
            else:
                print(f"[{datetime.now().isoformat()}] ⚠️ [Backpack] ticker 响应中没有 'lastPrice' 字段")
                if ticker:
                    print(f"[{datetime.now().isoformat()}] 🔍 [Backpack] ticker 可用字段: {list(ticker.keys()) if isinstance(ticker, dict) else 'N/A'}")
            return None
        except Exception as e:
            import traceback
            print(f"[{datetime.now().isoformat()}] ❌ [Backpack] 获取价格失败 ({symbol}): {e}")
            print(f"[{datetime.now().isoformat()}] 📋 [Backpack] 错误堆栈:\n{traceback.format_exc()}")
            return None
    
    def get_open_orders(self, symbol: str) -> List[Dict]:
        """获取未完成订单"""
        import time
        
        bpx_symbol = self._convert_symbol(symbol)
        
        # 重试机制
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Backpack API 需要使用 symbol 参数名
                orders = self.account.get_open_orders(symbol=bpx_symbol)
                break  # 成功则跳出循环
            except Exception as e:
                error_msg = str(e)
                if 'SSL' in error_msg or 'Connection' in error_msg:
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2  # 2, 4, 6 秒
                        print(f"[{datetime.now().isoformat()}] ⚠️ [Backpack] SSL/连接错误，{wait_time}秒后重试 ({attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                    else:
                        print(f"[{datetime.now().isoformat()}] ❌ [Backpack] 重试{max_retries}次后仍失败")
                        return []
                else:
                    # 非网络错误，直接抛出
                    raise
        
        try:
            # 调试：打印原始订单数据
            print(f"[{datetime.now().isoformat()}] 🔍 [Backpack] 原始订单数据类型: {type(orders)}")
            print(f"[{datetime.now().isoformat()}] 🔍 [Backpack] 原始订单数据长度: {len(orders) if isinstance(orders, list) else 'N/A'}")
            
            # 检查返回数据格式
            if orders is None or not orders:
                print(f"[{datetime.now().isoformat()}] ℹ️ [Backpack] 订单数据为空")
                return []
            
            # 检查是否是 API 错误响应
            if isinstance(orders, dict) and 'code' in orders and 'message' in orders:
                error_code = orders.get('code')
                error_msg = orders.get('message')
                print(f"[{datetime.now().isoformat()}] ❌ [Backpack] API 错误响应:")
                print(f"[{datetime.now().isoformat()}]    错误代码: {error_code}")
                print(f"[{datetime.now().isoformat()}]    错误信息: {error_msg}")
                
                # 根据错误类型给出具体建议
                if error_code == 'INVALID_CLIENT_REQUEST' and 'signature' in error_msg.lower():
                    print(f"[{datetime.now().isoformat()}] 💡 [Backpack] 签名错误，可能原因:")
                    print(f"[{datetime.now().isoformat()}]    1. API Secret 格式不正确（需要 base64 格式）")
                    print(f"[{datetime.now().isoformat()}]    2. API Key 和 Secret 不匹配")
                    print(f"[{datetime.now().isoformat()}]    3. 服务器时间不同步")
                    print(f"[{datetime.now().isoformat()}]    4. API 密钥已过期或被禁用")
                elif 'unauthorized' in error_msg.lower():
                    print(f"[{datetime.now().isoformat()}] 💡 [Backpack] 认证失败，请检查 API 密钥")
                elif 'rate limit' in error_msg.lower():
                    print(f"[{datetime.now().isoformat()}] 💡 [Backpack] API 请求频率超限")
                
                return []
            
            # 确保是列表
            if not isinstance(orders, list):
                print(f"[{datetime.now().isoformat()}] ⚠️ [Backpack] 订单数据不是列表，转换中")
                orders = [orders]
            
            # 转换为统一格式
            result = []
            for i, order in enumerate(orders):
                print(f"[{datetime.now().isoformat()}] 🔍 [Backpack] 处理订单 {i}")
                
                # 确保 order 是字典
                if not isinstance(order, dict):
                    print(f"[{datetime.now().isoformat()}] ⚠️ [Backpack] 订单 {i} 不是字典: {type(order)}")
                    continue
                
                # 调试：打印订单的所有字段
                print(f"[{datetime.now().isoformat()}] 🔍 [Backpack] 订单 {i} 字段: {list(order.keys())}")
                
                # ⚠️ 关键修复：只处理 Open 状态的订单，过滤已成交/已取消的订单
                order_status = order.get('status')
                if order_status != 'Open':
                    print(f"[{datetime.now().isoformat()}] ⏭️ [Backpack] 订单 {i} 状态为 {order_status}，跳过（非 Open 状态）")
                    continue
                
                # 获取订单 ID（尝试多个可能的字段名）
                order_id = order.get('id') or order.get('orderId') or order.get('order_id')
                print(f"[{datetime.now().isoformat()}] 🔍 [Backpack] 订单 {i} ID 获取:")
                print(f"[{datetime.now().isoformat()}]    - order.get('id') = {order.get('id')}")
                print(f"[{datetime.now().isoformat()}]    - order.get('orderId') = {order.get('orderId')}")
                print(f"[{datetime.now().isoformat()}]    - order.get('order_id') = {order.get('order_id')}")
                print(f"[{datetime.now().isoformat()}]    - 最终 order_id = {order_id}")
                
                # 如果 ID 仍为 None，打印完整订单数据
                if order_id is None:
                    print(f"[{datetime.now().isoformat()}] ❌ [Backpack] 订单 {i} ID 为 None!")
                    print(f"[{datetime.now().isoformat()}] 📋 [Backpack] 完整订单数据: {order}")
                
                converted_order = {
                    'orderId': order_id,
                    'symbol': order.get('symbol'),
                    'side': 'BUY' if order.get('side') == 'Bid' else 'SELL',
                    'price': order.get('price'),
                    'origQty': order.get('quantity'),
                    'executedQty': order.get('executedQuantity', '0'),
                    'status': self._convert_order_status(order.get('status')),
                    'type': order.get('orderType'),
                    'timeInForce': order.get('timeInForce')
                }
                
                print(f"[{datetime.now().isoformat()}] 🔍 [Backpack] 转换后订单 {i}: {converted_order}")
                result.append(converted_order)
            
            if result:
                print(f"[{datetime.now().isoformat()}] ✅ [Backpack] 找到 {len(result)} 个未完成订单")
            return result
            
        except Exception as e:
            import traceback
            print(f"[{datetime.now().isoformat()}] ❌ [Backpack] 获取未完成订单失败 ({symbol}): {e}")
            print(f"[{datetime.now().isoformat()}] 📋 [Backpack] 错误堆栈:\n{traceback.format_exc()}")
            return []
    
    def get_order(self, symbol: str, orderId: str) -> Dict:
        """查询订单状态"""
        try:
            bpx_symbol = self._convert_symbol(symbol)
            order = self.account.get_open_order(symbol=bpx_symbol, order_id=orderId)
            
            # 检查是否是错误响应
            if self._check_api_error(order, "查询订单"):
                return None
            
            if order:
                return {
                    'orderId': order.get('id'),
                    'symbol': order.get('symbol'),
                    'side': 'BUY' if order.get('side') == 'Bid' else 'SELL',
                    'price': order.get('price'),
                    'origQty': order.get('quantity'),
                    'executedQty': order.get('executedQuantity', '0'),
                    'status': self._convert_order_status(order.get('status')),
                    'type': order.get('orderType')
                }
            return None
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Backpack] 查询订单失败 ({symbol}, {orderId}): {e}")
            return None
    
    def order_limit_buy(self, symbol: str, quantity: float, price: str, **kwargs) -> Dict:
        """限价买单"""
        try:
            bpx_symbol = self._convert_symbol(symbol)
            time_in_force = kwargs.get('timeInForce', 'GTC')
            
            result = self.account.execute_order(
                symbol=bpx_symbol,
                side='Bid',  # Backpack 使用 Bid/Ask
                order_type='Limit',
                quantity=str(quantity),
                price=price,
                time_in_force=time_in_force
            )
            
            # 调试：打印完整的 API 响应
            print(f"[{datetime.now().isoformat()}] 🔍 [Backpack] order_limit_buy API 响应类型: {type(result)}")
            print(f"[{datetime.now().isoformat()}] 🔍 [Backpack] order_limit_buy API 响应内容: {result}")
            
            # 检查是否是错误响应
            if self._check_api_error(result, "限价买单"):
                raise Exception(f"Backpack API 错误: {result.get('code')} - {result.get('message')}")
            
            if result:
                # 尝试多个可能的字段名获取订单ID
                order_id = result.get('id') or result.get('orderId') or result.get('order_id') or result.get('clientId')
                print(f"[{datetime.now().isoformat()}] 🔍 [Backpack] 提取的订单ID: {order_id}")
                
                if not order_id:
                    print(f"[{datetime.now().isoformat()}] ⚠️ [Backpack] 无法从响应中提取订单ID，响应字段: {list(result.keys()) if isinstance(result, dict) else 'N/A'}")
                
                return {
                    'orderId': order_id,
                    'id': order_id,  # 同时提供 id 字段以兼容
                    'symbol': bpx_symbol,
                    'side': 'BUY',
                    'price': price,
                    'origQty': str(quantity),
                    'status': 'NEW'
                }
            else:
                raise Exception(f"下单返回结果为空: symbol={symbol}, quantity={quantity}, price={price}")
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Backpack] 限价买单失败 ({symbol}): {e}")
            raise
    
    def order_limit_sell(self, symbol: str, quantity: float, price: str, **kwargs) -> Dict:
        """限价卖单"""
        try:
            bpx_symbol = self._convert_symbol(symbol)
            time_in_force = kwargs.get('timeInForce', 'GTC')
            
            result = self.account.execute_order(
                symbol=bpx_symbol,
                side='Ask',  # Backpack 使用 Bid/Ask
                order_type='Limit',
                quantity=str(quantity),
                price=price,
                time_in_force=time_in_force
            )
            
            # 调试：打印完整的 API 响应
            print(f"[{datetime.now().isoformat()}] 🔍 [Backpack] order_limit_sell API 响应类型: {type(result)}")
            print(f"[{datetime.now().isoformat()}] 🔍 [Backpack] order_limit_sell API 响应内容: {result}")
            
            # 检查是否是错误响应
            if self._check_api_error(result, "限价卖单"):
                raise Exception(f"Backpack API 错误: {result.get('code')} - {result.get('message')}")
            
            if result:
                # 尝试多个可能的字段名获取订单ID
                order_id = result.get('id') or result.get('orderId') or result.get('order_id') or result.get('clientId')
                print(f"[{datetime.now().isoformat()}] 🔍 [Backpack] 提取的订单ID: {order_id}")
                
                if not order_id:
                    print(f"[{datetime.now().isoformat()}] ⚠️ [Backpack] 无法从响应中提取订单ID，响应字段: {list(result.keys()) if isinstance(result, dict) else 'N/A'}")
                
                return {
                    'orderId': order_id,
                    'id': order_id,  # 同时提供 id 字段以兼容
                    'symbol': bpx_symbol,
                    'side': 'SELL',
                    'price': price,
                    'origQty': str(quantity),
                    'status': 'NEW'
                }
            else:
                raise Exception(f"下单返回结果为空: symbol={symbol}, quantity={quantity}, price={price}")
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Backpack] 限价卖单失败 ({symbol}): {e}")
            raise
    
    def cancel_order(self, symbol: str, order_id: str) -> Dict:
        """取消订单"""
        try:
            bpx_symbol = self._convert_symbol(symbol)
            result = self.account.cancel_order(bpx_symbol, order_id)
            
            # 检查是否是错误响应
            if self._check_api_error(result, "取消订单"):
                raise Exception(f"Backpack API 错误: {result.get('code')} - {result.get('message')}")
            
            return result or {'success': True}
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Backpack] 取消订单失败 ({symbol}, {order_id}): {e}")
            raise
    
    def cancel_replace_order(self, symbol: str, side: str, order_type: str, 
                            quantity: float, price: str, cancel_order_id: str, **kwargs) -> Dict:
        """取消并替换订单（改价）
        
        Backpack 不支持原子性的 cancel_replace，需要分两步：
        1. 取消旧订单
        2. 下新订单
        """
        try:
            # 1. 取消旧订单
            self.cancel_order(symbol, cancel_order_id)
            
            # 2. 下新订单
            if side == 'BUY':
                new_order = self.order_limit_buy(symbol, quantity, price, **kwargs)
            else:
                new_order = self.order_limit_sell(symbol, quantity, price, **kwargs)
            
            # 返回格式兼容 Binance
            return {
                'cancelResult': 'SUCCESS',
                'newOrderResponse': new_order
            }
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Backpack] 改价失败 ({symbol}): {e}")
            raise
    
    def start_websocket(self, symbol: str, on_ticker: Callable, on_user: Optional[Callable] = None) -> Dict:
        """启动 WebSocket 连接
        
        注意：Backpack 的 WebSocket 实现可能与 Binance 不同
        这里返回一个标记，表示不支持 WebSocket，使用 REST 轮询
        """
        print(f"[{datetime.now().isoformat()}] ℹ️ [Backpack] WebSocket 暂不支持，将使用 REST 轮询")
        
        return {
            'manager': None,
            'ticker_enabled': False,
            'user_enabled': False
        }
    
    def stop_websocket(self, ws_manager) -> None:
        """停止 WebSocket 连接"""
        # Backpack 暂不支持 WebSocket
        pass
    
    def parse_ticker_message(self, msg: Dict) -> Optional[float]:
        """解析行情消息"""
        try:
            if 'lastPrice' in msg:
                return float(msg['lastPrice'])
            if 'c' in msg:  # 兼容 Binance 格式
                return float(msg['c'])
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [Backpack] 解析行情消息失败: {e}")
        return None
    
    def parse_user_message(self, msg: Dict) -> Optional[Dict]:
        """解析用户数据消息"""
        # Backpack 使用 REST 轮询，不需要解析 WebSocket 消息
        return None
    
    def get_price_precision(self, symbol_info: Dict) -> tuple:
        """提取价格精度"""
        if not symbol_info:
            print(f"[{datetime.now().isoformat()}] ⚠️ [Backpack] symbol_info 无效，使用默认价格精度")
            return 0.01, 2
        
        try:
            # Backpack 使用 filters 字段
            filters = symbol_info.get('filters', {})
            price_filter = filters.get('price', {})
            
            tick_size = float(price_filter.get('tickSize', 0.01))
            if tick_size > 0:
                price_decimals = int(abs(math.log10(tick_size)))
                return tick_size, price_decimals
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ⚠️ [Backpack] 解析价格精度失败: {e}")
        
        return 0.01, 2
    
    def get_quantity_precision(self, symbol_info: Dict) -> tuple:
        """提取数量精度"""
        if not symbol_info:
            print(f"[{datetime.now().isoformat()}] ⚠️ [Backpack] symbol_info 无效，使用默认数量精度")
            return 0.000001, 6
        
        try:
            # Backpack 使用 filters 字段
            filters = symbol_info.get('filters', {})
            quantity_filter = filters.get('quantity', {})
            
            step_size = float(quantity_filter.get('stepSize', 0.000001))
            if step_size > 0:
                qty_decimals = int(abs(math.log10(step_size)))
                return step_size, qty_decimals
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ⚠️ [Backpack] 解析数量精度失败: {e}")
        
        return 0.000001, 6
    
    def _convert_order_status(self, bpx_status: str) -> str:
        """转换订单状态为统一格式"""
        status_map = {
            'Open': 'NEW',
            'Filled': 'FILLED',
            'PartiallyFilled': 'PARTIALLY_FILLED',
            'Cancelled': 'CANCELED',
            'Expired': 'EXPIRED'
        }
        return status_map.get(bpx_status, bpx_status)
    
    def get_account(self):
        """获取原始账户客户端（用于扩展功能）"""
        return self.account
    
    def get_public(self):
        """获取原始公共客户端（用于扩展功能）"""
        return self.public
