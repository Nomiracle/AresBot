"""
Up/Down 15分钟市场交易所适配器
自动计算并使用最新的 15 分钟时间戳市场
支持多种市场（如 btc, eth 等）
"""
from datetime import datetime, timezone, timedelta
import requests
from .polymarket_adapter import NativePolymarketSpot
import pytz
import time
import threading
from typing import Dict, Callable


class UpDown15m(NativePolymarketSpot):
    """Up/Down 15分钟市场交易所适配器
    
    自动计算下一个 15 分钟时间戳,并使用对应的市场进行交易
    支持多种市场，通过 symbol 参数指定，格式为 "market-outcome"，如 "btc-Up"
    """
    
    # 默认市场关闭前的阈值时间(秒) - 用于取消订单和刷新市场
    DEFAULT_MARKET_CLOSE_THRESHOLD_SECONDS = 180
    
    def __init__(self, api_key: str, api_secret: str, symbol: str = "btc-Up", testnet: bool = True,
                 min_price_threshold: float = None, market_close_threshold: int = None):
        """初始化 Up/Down 15分钟市场适配器
        
        Args:
            api_key: 钱包地址
            api_secret: 私钥 (Private Key, 0x开头的十六进制字符串)
            symbol: 交易对，格式为 "market-outcome"，如 "btc-Up" 或 "eth-Down"
                   market: 市场前缀（如 btc, eth）
                   outcome: 交易方向 "Up" 或 "Down"
            testnet: 是否使用测试网
            min_price_threshold: 最低价格阈值（默认 0.15）
            market_close_threshold: 市场关闭前阈值时间秒数（默认 180）
        """
        # 解析 symbol，格式为 "market-outcome"，如 "btc-Up"
        self.market_prefix, self.outcome = self._parse_symbol(symbol)
        self.original_symbol = symbol  # 保存原始 symbol 用于事件回调
        
        # 市场关闭阈值
        self.market_close_threshold = market_close_threshold if market_close_threshold is not None else self.DEFAULT_MARKET_CLOSE_THRESHOLD_SECONDS
        
        self.market_end_time = None  # 市场结束时间戳
        self.condition_id = None  # 市场的条件 ID (用于 WebSocket 订阅)
        self._ws_callbacks = None  # 保存 WebSocket 回调函数
        self._refresh_timer = None  # 市场刷新定时器
        self._timer_lock = threading.Lock()  # 定时器锁
        self._is_switching_market = False  # 市场切换中标志
        
        # 获取最新市场的 token_id
        token_id = self._get_latest_market_token()
        
        if not token_id:
            raise ValueError(f"无法获取最新的 {self.market_prefix.upper()} Up/Down 15分钟市场")
        
        # 保存 min_price_threshold 用于传递给父类
        self._min_price_threshold = min_price_threshold
        
        # 调用父类初始化
        super().__init__(api_key, api_secret, token_id, testnet, min_price_threshold=min_price_threshold)
        
        print(f"[{datetime.now().isoformat()}] ✅ [UpDown15m] 使用市场: {self.market_slug}")
        print(f"[{datetime.now().isoformat()}] ✅ [UpDown15m] 市场前缀: {self.market_prefix}")
        print(f"[{datetime.now().isoformat()}] ✅ [UpDown15m] 交易方向: {self.outcome}")
        print(f"[{datetime.now().isoformat()}] ✅ [UpDown15m] Token ID: {token_id}")
        print(f"[{datetime.now().isoformat()}] ✅ [UpDown15m] 市场关闭阈值: {self.market_close_threshold}秒")
        
        # 注意: 定时器将在 start_ws() 中设置,确保客户端已完成认证
    
    def _parse_symbol(self, symbol: str) -> tuple:
        """解析 symbol 格式
        
        Args:
            symbol: 交易对，格式为 "market-outcome"，如 "btc-Up" 或 "eth-Down"
        
        Returns:
            tuple: (market_prefix, outcome)
        """
        if '-' in symbol:
            parts = symbol.split('-', 1)
            market_prefix = parts[0].lower()
            outcome = parts[1].capitalize() if len(parts) > 1 else 'Up'
        else:
            # 兼容旧格式，只传入 "Up" 或 "Down"
            market_prefix = 'btc'
            outcome = symbol.capitalize() if symbol else 'Up'
        
        # 验证 outcome
        if outcome not in ['Up', 'Down']:
            outcome = 'Up'
        
        return market_prefix, outcome
    
    def _get_log_prefix(self) -> str:
        """生成日志前缀"""
        api_key_short = self.api_key[:6] if self.api_key else "NOKEY"
        return f"[{datetime.now().isoformat()}] [UpDown15m-{api_key_short}-{self.market_slug}-{self.outcome}]"

    
    def _calculate_next_timestamp(self) -> int:
        """计算下一个 15 分钟时间戳 (使用 ET 时区)
        
        Returns:
            int: Unix 时间戳
        """
        # 使用 ET (美国东部时间) 时区
        et_tz = pytz.timezone('America/New_York')
        now = datetime.now(et_tz)
        current_minute = now.minute
        next_15min_mark = ((current_minute // 15) + 1) * 15
        
        if next_15min_mark >= 60:
            next_time = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        else:
            next_time = now.replace(minute=next_15min_mark, second=0, microsecond=0)
        
        return int(next_time.timestamp())
    
    def _calculate_current_timestamp(self) -> int:
        """计算当前 15 分钟时间戳 (使用 ET 时区)
        
        Returns:
            int: Unix 时间戳
        """
        # 使用 ET (美国东部时间) 时区
        et_tz = pytz.timezone('America/New_York')
        now = datetime.now(et_tz)
        current_minute = now.minute
        current_15min_mark = (current_minute // 15) * 15
        
        current_time = now.replace(minute=current_15min_mark, second=0, microsecond=0)
        
        return int(current_time.timestamp())
    
    def _get_market_token_by_timestamp(self, timestamp: int, update_state: bool = True) -> str:
        """根据时间戳获取市场的 token_id
        
        Args:
            timestamp: 市场开始时间戳
            update_state: 是否更新实例状态(market_slug, market_end_time)
        
        Returns:
            str: Token ID,如果获取失败返回 None
        """
        try:
            # 使用动态市场前缀
            slug = f"{self.market_prefix}-updown-15m-{timestamp}"
            
            print(f"[{datetime.now().isoformat()}] 🔍 [UpDown15m] 查询市场: {slug}")
            
            # 通过 Gamma API 查询市场
            response = requests.get(
                f'https://gamma-api.polymarket.com/events?slug={slug}',
                timeout=10
            )
            
            if response.status_code == 200:
                events = response.json()
                if events and len(events) > 0:
                    event = events[0]
                    markets = event.get('markets', [])
                    
                    if markets and len(markets) > 0:
                        market = markets[0]
                        
                        # 保存 condition_id (用于 WebSocket 订阅)
                        if update_state:
                            condition_id = market.get('conditionId') or market.get('condition_id')
                            if condition_id:
                                self.condition_id = condition_id
                                print(f"[{datetime.now().isoformat()}] 🔑 [UpDown15m] Condition ID: {condition_id}")
                        
                        # 尝试从 tokens 字段获取
                        tokens = market.get('tokens', [])
                        
                        # 如果 tokens 为空,尝试从 clobTokenIds 获取
                        if not tokens:
                            import json
                            clob_token_ids_str = market.get('clobTokenIds', '[]')
                            try:
                                clob_token_ids = json.loads(clob_token_ids_str)
                                outcomes_str = market.get('outcomes', '[]')
                                outcomes = json.loads(outcomes_str)
                                
                                # 构建 tokens 列表
                                tokens = []
                                for i, token_id in enumerate(clob_token_ids):
                                    if i < len(outcomes):
                                        tokens.append({
                                            'token_id': token_id,
                                            'outcome': outcomes[i]
                                        })
                            except (json.JSONDecodeError, Exception) as e:
                                print(f"[{datetime.now().isoformat()}] ⚠️ [UpDown15m] 解析 clobTokenIds 失败: {e}")
                        
                        # 查找对应方向的 token
                        print(f"[{datetime.now().isoformat()}] 🔍 [UpDown15m] 市场 {slug} 有 {len(tokens)} 个 token")
                        for token in tokens:
                            print(f"[{datetime.now().isoformat()}] 🔍 [UpDown15m]   - {token.get('outcome')}: {token.get('token_id')}")
                            if token.get('outcome', '').lower() == self.outcome.lower():
                                token_id = token.get('token_id')
                                
                                if update_state:
                                    self.market_slug = slug
                                    self.market_end_time = timestamp + 900  # 900秒 = 15分钟
                                
                                print(f"[{datetime.now().isoformat()}] ✅ [UpDown15m] 找到 {self.outcome} token")
                                print(f"[{datetime.now().isoformat()}] ✅ [UpDown15m] Slug: {slug} (开始: {datetime.fromtimestamp(timestamp, tz=pytz.UTC).strftime('%H:%M')} UTC)")
                                print(f"[{datetime.now().isoformat()}] ✅ [UpDown15m] Token ID: {token_id}")
                                print(f"[{datetime.now().isoformat()}] ⏰ [UpDown15m] 市场结束时间: {datetime.fromtimestamp(timestamp + 900, tz=pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC")
                                return token_id
                        
                        # 如果没有找到指定方向,使用第一个 token
                        if tokens:
                            token_id = tokens[0].get('token_id')
                            actual_outcome = tokens[0].get('outcome', 'Unknown')
                            
                            if update_state:
                                self.market_slug = slug
                                self.market_end_time = timestamp + 900  # 900秒 = 15分钟
                            
                            print(f"[{datetime.now().isoformat()}] ⚠️ [UpDown15m] 未找到 {self.outcome},使用 {actual_outcome}: {token_id}")
                            print(f"[{datetime.now().isoformat()}] ⏰ [UpDown15m] 市场结束时间: {datetime.fromtimestamp(timestamp + 900, tz=pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC")
                            return token_id
            
            print(f"[{datetime.now().isoformat()}] ⏭️ [UpDown15m] 市场 {slug} 不存在")
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [UpDown15m] 查询失败: {e}")
        
        return None
    
    def _get_latest_market_token(self) -> str:
        """获取最新市场的 token_id
        
        尝试顺序:
        1. 当前 15 分钟市场
        
        Returns:
            str: Token ID,如果获取失败返回 None
        """
        current_timestamp = self._calculate_current_timestamp()
        token_id = self._get_market_token_by_timestamp(current_timestamp, update_state=True)
        
        if not token_id:
            print(f"[{datetime.now().isoformat()}] ❌ [UpDown15m] 无法获取最新市场")
        
        return token_id
    
    def _get_next_market_token(self) -> str:
        """获取下一个 15 分钟市场的 token_id
        
        Returns:
            str: Token ID,如果获取失败返回 None
        """
        next_timestamp = self._calculate_next_timestamp()
        token_id = self._get_market_token_by_timestamp(next_timestamp, update_state=True)
        
        if not token_id:
            print(f"[{datetime.now().isoformat()}] ❌ [UpDown15m] 无法获取下一个市场")
        
        return token_id
    
    def _check_and_schedule_refresh(self) -> None:
        """检查市场状态并设置定时器
        
        如果距离市场关闭小于阈值时间,立即切换到新市场
        否则设置定时器在结束前阈值时间触发刷新
        """
        if not self.market_end_time:
            print(f"{self._get_log_prefix()} ⚠️ 未设置市场结束时间,跳过定时器设置")
            return
        
        seconds_left = self.get_seconds_until_market_close()
        
        print(f"{self._get_log_prefix()} ⏰ 距离市场关闭还有 {seconds_left} 秒")
        
        # 如果市场已关闭或即将关闭(小于阈值),立即切换到新市场
        if seconds_left <= self.market_close_threshold:
            print(f"{self._get_log_prefix()} 🔄 市场即将关闭,立即切换到新市场...")
            self._refresh_market_and_cancel_orders()
        else:
            # 设置定时器,在结束前阈值时间触发
            delay = seconds_left - self.market_close_threshold
            print(f"{self._get_log_prefix()} ⏲️ 设置定时器: {delay} 秒后触发市场刷新")
            
            with self._timer_lock:
                # 取消旧定时器
                if self._refresh_timer:
                    self._refresh_timer.cancel()
                
                # 创建新定时器
                self._refresh_timer = threading.Timer(delay, self._refresh_market_and_cancel_orders)
                self._refresh_timer.daemon = True
                self._refresh_timer.start()
    
    def _cancel_all_buy_orders(self, tag: str = "", asset_id: str = None) -> int:
        """批量取消所有未完成的买单
        
        Args:
            tag: 日志标签，用于区分调用来源
            asset_id: 指定的 asset_id，为 None 时使用当前 self.symbol
        
        Returns:
            int: 成功取消的订单数量
        """
        try:
            log_tag = f"({tag})" if tag else ""
            target_asset_id = asset_id if asset_id is not None else self.symbol
            print(f"{self._get_log_prefix()} 🚫 取消所有买单{log_tag} (asset_id={target_asset_id})...")
            
            open_orders = self.get_open_orders(asset_id=target_asset_id)
            buy_orders = [o for o in open_orders if o.get('side') == 'BUY']
            
            if not buy_orders:
                print(f"{self._get_log_prefix()} ℹ️ 没有待取消的买单{log_tag}")
                return 0
            
            # 提取所有买单 ID
            buy_order_ids = [o.get('orderId') for o in buy_orders if o.get('orderId')]
            
            if not buy_order_ids:
                return 0
            
            # 使用批量取消接口
            result = self.cancel_orders(buy_order_ids)
            canceled = result.get('canceled', [])
            not_canceled = result.get('not_canceled', {})
            print(f"{self._get_log_prefix()} ✅ 批量取消买单完成{log_tag}: 成功 {len(canceled)} 个, 失败 {len(not_canceled)} 个")
            return len(canceled)
            
        except Exception as e:
            print(f"{self._get_log_prefix()} ⚠️ 查询或取消订单失败{tag}: {e}")
            return 0
    
    def _refresh_market_and_cancel_orders(self) -> None:
        """刷新市场并取消旧市场的买单"""
        try:
            print(f"{self._get_log_prefix()} 🔄 开始刷新市场流程...")
            
            # 保存旧市场的 asset_id，用于定时器取消订单
            old_asset_id = self.symbol
            print(f"{self._get_log_prefix()} 📝 保存旧市场 asset_id: {old_asset_id}")
            
            # 设置市场切换中标志，禁止下单和改价
            self._is_switching_market = True
            print(f"{self._get_log_prefix()} 🚫 市场切换中，禁止下单和改价")
            
            # 等待1秒，确保正在进行的操作完成
            time.sleep(1)
            
            # 1. 批量取消所有未完成的买单（第一次，使用旧 asset_id）
            self._cancel_all_buy_orders("第1次", asset_id=old_asset_id)
            
            # 设置定时器，7秒后再次执行批量取消（使用旧 asset_id）
            cancel_timer = threading.Timer(7, self._cancel_all_buy_orders, kwargs={"tag": "第2次-定时器", "asset_id": old_asset_id})
            cancel_timer.daemon = True
            cancel_timer.start()
            print(f"{self._get_log_prefix()} ⏲️ 已设置7秒后再次取消买单的定时器 (asset_id={old_asset_id})")
            
            # 2. 刷新到新市场
            print(f"{self._get_log_prefix()} 🔄 切换到新市场...")
            success = self.refresh_market()
            
            if success:
                # 等待1秒，确保新市场 WebSocket 连接稳定
                time.sleep(2)
                
                # 3. 为新市场设置定时器
                print(f"{self._get_log_prefix()} ⏲️ 为新市场设置定时器...")
                self._check_and_schedule_refresh()
            else:
                print(f"{self._get_log_prefix()} ❌ 市场刷新失败")
                
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 刷新市场流程失败: {e}")
            import traceback
            traceback.print_exc()
    
    def refresh_market(self) -> bool:
        """刷新到下一个市场
        
        当当前市场即将结束或已结束时,可以调用此方法切换到新市场
        同时会自动关闭旧市场的 WebSocket 并开启新市场的 WebSocket
        
        Returns:
            bool: 是否成功刷新
        """
        try:
            print(f"[{datetime.now().isoformat()}] 🔄 [UpDown15m] 刷新市场...")
            print(f"[{datetime.now().isoformat()}] 🔍 [UpDown15m] 当前状态: slug={self.market_slug}, token_id={self.symbol}")
            
            old_token_id = self.symbol
            old_slug = self.market_slug
            
            # 获取下一个市场的 token_id (这会同时更新 self.market_slug 和 self.market_end_time)
            new_token_id = self._get_next_market_token()
            new_slug = self.market_slug
            
            if new_token_id and new_token_id != old_token_id:
                # 清空成交订单去重缓存（新市场的订单 ID 不会与旧市场冲突）
                self.clear_filled_order_ids()
                
                # 关闭旧市场的 WebSocket
                print(f"[{datetime.now().isoformat()}] 🔌 [UpDown15m] 关闭旧市场 WebSocket...")
                self.stop_ws()
                
                # 等待 WebSocket 完全关闭
                time.sleep(1)
                
                # 更新 token_id
                self.symbol = new_token_id
                
                # 如果之前有 WebSocket 回调,重新启动新市场的 WebSocket
                if self._ws_callbacks:
                    print(f"[{datetime.now().isoformat()}] 🚀 [UpDown15m] 启动新市场 WebSocket...")
                    self.start_ws(
                        on_price_update=self._ws_callbacks['price'],
                        on_order_update=self._ws_callbacks['order']
                    )
                
                print(f"[{datetime.now().isoformat()}] ✅ [UpDown15m] 市场已更新")
                print(f"[{datetime.now().isoformat()}] ✅ [UpDown15m] 旧市场: token_id={old_token_id}")
                print(f"[{datetime.now().isoformat()}] ✅ [UpDown15m] 新市场: slug={self.market_slug}, token_id={new_token_id}")
                

                
                # 发送 refresh_market 事件给 trading.py，清除旧市场的缓存订单
                if self._ws_callbacks and self._ws_callbacks.get('order'):
                    refresh_event = {
                        'event_type': 'refresh_market',
                        'symbol': self.original_symbol,  # 使用原始 symbol
                        'old_slug': old_slug,
                        'new_slug': new_slug
                    }
                    self._ws_callbacks['order'](refresh_event)
                    print(f"[{datetime.now().isoformat()}] 📤 [UpDown15m] 已发送 refresh_market 事件")
                time.sleep(1)
                # 重置市场切换标志，允许下单和改价
                self._is_switching_market = False
                print(f"[{datetime.now().isoformat()}] ✅ [UpDown15m] 市场切换完成，允许下单和改价")
                
                return True
            elif new_token_id == old_token_id:
                print(f"[{datetime.now().isoformat()}] ℹ️ [UpDown15m] 已是最新市场: slug={self.market_slug}, token_id={self.symbol}")
                # 重置市场切换标志
                self._is_switching_market = False
                return True
            else:
                print(f"[{datetime.now().isoformat()}] ❌ [UpDown15m] 刷新失败")
                # 刷新失败也要重置标志，否则会永久禁止下单
                self._is_switching_market = False
                return False
                
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [UpDown15m] 刷新市场失败: {e}")
            import traceback
            traceback.print_exc()
            # 异常时也要重置标志
            self._is_switching_market = False
            return False
    
    def order_limit_buy(self, quantity: float, price: str, **kwargs) -> Dict:
        """限价买单 - 重写父类方法，检查市场切换状态"""
        if self._is_switching_market:
            error_msg = "市场切换中，禁止下单"
            print(f"{self._get_log_prefix()} 🚫 {error_msg}")
            raise RuntimeError(error_msg)
        return super().order_limit_buy(quantity, price, **kwargs)
    
    def order_limit_sell(self, quantity: float, price: str, **kwargs) -> Dict:
        """限价卖单 - 重写父类方法，检查市场切换状态"""
        if self._is_switching_market:
            error_msg = "市场切换中，禁止下单"
            print(f"{self._get_log_prefix()} 🚫 {error_msg}")
            raise RuntimeError(error_msg)
        return super().order_limit_sell(quantity, price, **kwargs)
    
    def modify_order(self, cancel_order_id: str, new_price: str, new_quantity: float = None, side: str = None) -> Dict:
        """改价 - 重写父类方法，检查市场切换状态"""
        if self._is_switching_market:
            error_msg = "市场切换中，禁止改价"
            print(f"{self._get_log_prefix()} 🚫 {error_msg}")
            raise RuntimeError(error_msg)
        return super().modify_order(cancel_order_id, new_price, new_quantity, side)
    
    def _process_order_event(self, data: dict, symbol: str = None) -> dict:
        """处理订单事件 - 重写父类方法,使用 original_symbol 作为 symbol
        
        Args:
            data: 订单事件数据
            symbol: 用于事件的 symbol 字段,如果为 None 则使用 self.original_symbol
        
        Returns:
            dict: 处理后的事件字典,如果不需要回调则返回 None
        """
        # 使用 original_symbol 作为 symbol,因为 config['symbol'] 存储的是 "btc-Up" 格式
        return super()._process_order_event(data, symbol=self.original_symbol)

    def _process_trade_event(self, data: dict, symbol: str = None) -> dict:
        """处理交易事件 - 重写父类方法,使用 original_symbol 作为 symbol
        
        Args:
            data: 交易事件数据
            symbol: 用于事件的 symbol 字段,如果为 None 则使用 self.original_symbol
        
        Returns:
            dict: 处理后的事件字典,如果不需要回调则返回 None
        """
        # 使用 original_symbol 作为 symbol,因为 config['symbol'] 存储的是 "btc-Up" 格式
        return super()._process_trade_event(data, symbol=self.original_symbol)
    
    def get_market_info(self) -> dict:
        """获取当前市场信息
        
        Returns:
            dict: 市场信息
        """
        # 添加调试日志
        # print(f"{self._get_log_prefix()} 📊 市场信息: slug={self.market_slug}, token_id={self.symbol}, end_time={self.market_end_time}")
        
        return {
            'slug': self.market_slug,
            'token_id': self.symbol,
            'market_prefix': self.market_prefix,
            'outcome': self.outcome,
            'original_symbol': self.original_symbol,
            'timestamp': self.market_end_time or self._calculate_next_timestamp(),
            'end_time': datetime.fromtimestamp(self.market_end_time).isoformat() if self.market_end_time else None
        }
    
    def get_seconds_until_market_close(self) -> int:
        """获取距离市场关闭的秒数
        
        Returns:
            int: 距离市场关闭的秒数,如果市场已关闭返回0
        """
        if not self.market_end_time:
            return 0
        
        # 使用 UTC 时间戳进行比较
        now = datetime.now(timezone.utc).timestamp()
        seconds_left = int(self.market_end_time - now)
        return max(0, seconds_left)
    
    def is_market_closing_soon(self, threshold_seconds: int = None) -> bool:
        """检查市场是否即将关闭
        
        Args:
            threshold_seconds: 阈值秒数,默认使用 MARKET_CLOSE_THRESHOLD_SECONDS
        
        Returns:
            bool: 如果距离关闭时间小于等于阈值返回True
        """
        if threshold_seconds is None:
            threshold_seconds = self.market_close_threshold
        seconds_left = self.get_seconds_until_market_close()
        return 0 < seconds_left <= threshold_seconds
    
    def check_and_cancel_orders_before_close(self, threshold_seconds: int = None) -> bool:
        """检查市场关闭时间,如果即将关闭则取消所有订单
        
        Args:
            threshold_seconds: 距离关闭的阈值秒数,默认使用 MARKET_CLOSE_THRESHOLD_SECONDS
        
        Returns:
            bool: 是否执行了取消操作
        """
        try:
            if not self.market_end_time:
                print(f"{self._get_log_prefix()} ⚠️ 未设置市场结束时间,跳过检查")
                return False
            
            seconds_left = self.get_seconds_until_market_close()
            
            # 市场已关闭
            if seconds_left == 0:
                print(f"{self._get_log_prefix()} ⏰ 市场已关闭")
                return False
            
            # 使用默认阈值
            if threshold_seconds is None:
                threshold_seconds = self.market_close_threshold
            
            # 市场即将关闭
            if seconds_left <= threshold_seconds:
                print(f"{self._get_log_prefix()} ⚠️ 市场将在 {seconds_left} 秒后关闭,开始取消所有订单...")
                
                # 获取所有未完成订单
                open_orders = self.get_open_orders()
                
                if not open_orders:
                    print(f"{self._get_log_prefix()} ℹ️ 没有未完成订单需要取消")
                    return False
                
                # 提取所有订单 ID，使用批量取消
                order_ids = [o.get('orderId') for o in open_orders if o.get('orderId')]
                
                if order_ids:
                    result = self.cancel_orders(order_ids)
                    canceled = result.get('canceled', [])
                    not_canceled = result.get('not_canceled', {})
                    print(f"{self._get_log_prefix()} ✅ 批量取消完成: 成功 {len(canceled)} 个, 失败 {len(not_canceled)} 个")
                
                return True
            
            return False
            
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 检查并取消订单失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def auto_update_market_if_needed(self) -> bool:
        """自动检查并更新市场(如果当前市场已过期)
        
        Returns:
            bool: 是否执行了市场更新
        """
        try:
            if not self.market_end_time:
                print(f"{self._get_log_prefix()} ⚠️ 未设置市场结束时间,尝试刷新市场")
                return self.refresh_market()
            
            seconds_left = self.get_seconds_until_market_close()
            
            # 市场已关闭,需要更新
            if seconds_left == 0:
                print(f"{self._get_log_prefix()} 🔄 市场已关闭,自动更新到新市场...")
                return self.refresh_market()
            
            return False
            
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 自动更新市场失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def check_market_and_manage_orders(self, cancel_threshold_seconds: int = None) -> dict:
        """综合检查市场状态并管理订单(推荐在交易循环中调用)
        
        功能:
        1. 检查市场是否即将关闭,如果是则取消所有订单
        2. 检查市场是否已关闭,如果是则自动更新到新市场
        
        Args:
            cancel_threshold_seconds: 距离关闭多少秒时取消订单,默认使用 MARKET_CLOSE_THRESHOLD_SECONDS
        
        Returns:
            dict: 包含执行结果的字典
                - orders_cancelled: 是否取消了订单
                - market_updated: 是否更新了市场
                - seconds_left: 距离市场关闭的秒数
        """
        result = {
            'orders_cancelled': False,
            'market_updated': False,
            'seconds_left': 0
        }
        
        try:
            # 1. 检查并取消即将关闭市场的订单
            result['orders_cancelled'] = self.check_and_cancel_orders_before_close(cancel_threshold_seconds)
            
            # 2. 检查并自动更新市场
            result['market_updated'] = self.auto_update_market_if_needed()
            
            # 3. 获取当前市场剩余时间
            result['seconds_left'] = self.get_seconds_until_market_close()
            
            return result
            
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 市场检查和订单管理失败: {e}")
            import traceback
            traceback.print_exc()
            return result
    
    def start_ws(self, on_price_update: Callable[[float], None], 
                 on_order_update: Callable[[Dict], None]) -> bool:
        """启动 WebSocket 并保存回调函数
        
        重写父类方法以保存回调函数,用于市场切换时重新订阅
        """
        # 保存回调函数
        self._ws_callbacks = {
            'price': on_price_update,
            'order': on_order_update
        }
        
        # 调用父类方法启动 WebSocket
        result = super().start_ws(on_price_update, on_order_update)
        
        # WebSocket 启动成功后,设置市场刷新定时器
        if result:
            print(f"{self._get_log_prefix()} ⏲️ WebSocket 已启动,开始设置市场刷新定时器...")
            self._check_and_schedule_refresh()
        
        return result
    
    def _check_market_close_before_order(self) -> None:
        """下单前检查市场是否即将关闭
        
        Raises:
            RuntimeError: 如果市场已关闭或即将关闭(阈值时间内)
        """
        if not self.market_end_time:
            return
        
        seconds_left = self.get_seconds_until_market_close()
        
        # 市场已关闭
        if seconds_left == 0:
            error_msg = f"市场已关闭,无法下单"
            print(f"{self._get_log_prefix()} ❌ {error_msg}")
            raise RuntimeError(error_msg)
        
        # 市场即将关闭(阈值时间内)
        if seconds_left <= self.market_close_threshold:
            error_msg = f"市场将在 {seconds_left} 秒后关闭,拒绝下单"
            print(f"{self._get_log_prefix()} ❌ {error_msg}")
            raise RuntimeError(error_msg)
    
    def order_limit_buy(self, quantity: float, price: str, **kwargs) -> Dict:
        """限价买单(带市场关闭检查)
        
        重写父类方法,添加市场关闭前的检查
        
        Raises:
            RuntimeError: 如果市场即将关闭
        """
        # 检查市场是否即将关闭(会抛出异常)
        self._check_market_close_before_order()
        
        # 调用父类方法
        return super().order_limit_buy(quantity, price, **kwargs)
    
    def order_limit_sell(self, quantity: float, price: str, **kwargs) -> Dict:
        """限价卖单(带市场关闭检查)
        
        重写父类方法,添加市场关闭前的检查
        
        Raises:
            RuntimeError: 如果市场即将关闭
        """
        # 检查市场是否即将关闭(会抛出异常)
        self._check_market_close_before_order()
        
        # 调用父类方法
        return super().order_limit_sell(quantity, price, **kwargs)
    
    def stop_ws(self) -> None:
        """停止 WebSocket 并清理定时器
        
        重写父类方法以清理定时器
        """
        # 取消定时器
        with self._timer_lock:
            if self._refresh_timer:
                self._refresh_timer.cancel()
                self._refresh_timer = None
                print(f"{self._get_log_prefix()} ⏲️ 已取消市场刷新定时器")
        
        # 调用父类方法
        super().stop_ws()
    
    def __del__(self):
        """析构函数,清理资源"""
        try:
            with self._timer_lock:
                if self._refresh_timer:
                    self._refresh_timer.cancel()
        except:
            pass


# 为了向后兼容，保留 BtcUpDown15m 别名
BtcUpDown15m = UpDown15m


class UpDown4h(UpDown15m):
    """Up/Down 4小时市场交易所适配器
    
    继承自 UpDown15m，重写时间戳计算逻辑为 4 小时周期
    """
    
    # 4小时周期的起始小时（UTC-5 ET时区）：0, 4, 8, 12, 16, 20
    PERIOD_HOURS = 4
    
    def __init__(self, api_key: str, api_secret: str, symbol: str = "btc-Up", testnet: bool = True,
                 min_price_threshold: float = None, market_close_threshold: int = None):
        """初始化 Up/Down 4小时市场适配器
        
        Args:
            api_key: 钱包地址
            api_secret: 私钥
            symbol: 交易对，格式为 "market-outcome"，如 "btc-Up"
            testnet: 是否使用测试网
            min_price_threshold: 最低价格阈值
            market_close_threshold: 市场关闭前阈值时间秒数（默认 180）
        """
        super().__init__(api_key, api_secret, symbol, testnet, min_price_threshold, market_close_threshold)
    
    def _get_log_prefix(self) -> str:
        """获取日志前缀"""
        api_key_short = self.api_key[:6] if self.api_key else 'N/A'
        return f"[{datetime.now().isoformat()}] [UpDown4h-{api_key_short}-{self.market_slug}-{self.outcome}]"
    
    def _calculate_next_timestamp(self) -> int:
        """计算下一个 4 小时时间戳 (使用 ET 时区)
        
        4小时周期：0:00, 4:00, 8:00, 12:00, 16:00, 20:00
        
        Returns:
            int: Unix 时间戳
        """
        et_tz = pytz.timezone('America/New_York')
        now = datetime.now(et_tz)
        current_hour = now.hour
        
        # 计算下一个 4 小时周期的起始小时
        next_period_hour = ((current_hour // self.PERIOD_HOURS) + 1) * self.PERIOD_HOURS
        
        if next_period_hour >= 24:
            # 跨天，需要加一天
            next_time = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        else:
            next_time = now.replace(hour=next_period_hour, minute=0, second=0, microsecond=0)
        
        return int(next_time.timestamp())
    
    def _calculate_current_timestamp(self) -> int:
        """计算当前 4 小时时间戳 (使用 ET 时区)
        
        Returns:
            int: Unix 时间戳
        """
        et_tz = pytz.timezone('America/New_York')
        now = datetime.now(et_tz)
        current_hour = now.hour
        
        # 计算当前 4 小时周期的起始小时
        current_period_hour = (current_hour // self.PERIOD_HOURS) * self.PERIOD_HOURS
        
        current_time = now.replace(hour=current_period_hour, minute=0, second=0, microsecond=0)
        
        return int(current_time.timestamp())
    
    def _get_market_token_by_timestamp(self, timestamp: int, update_state: bool = True) -> str:
        """根据时间戳获取市场的 token_id
        
        重写父类方法，使用 4h slug 格式
        
        Args:
            timestamp: 市场开始时间戳
            update_state: 是否更新实例状态
        
        Returns:
            str: Token ID,如果获取失败返回 None
        """
        try:
            # 使用 4h slug 格式
            slug = f"{self.market_prefix}-updown-4h-{timestamp}"
            
            print(f"[{datetime.now().isoformat()}] 🔍 [UpDown4h] 查询市场: {slug}")
            
            # 通过 Gamma API 查询市场
            response = requests.get(
                f'https://gamma-api.polymarket.com/events?slug={slug}',
                timeout=10
            )
            
            if response.status_code == 200:
                events = response.json()
                if events and len(events) > 0:
                    event = events[0]
                    markets = event.get('markets', [])
                    
                    if markets and len(markets) > 0:
                        market = markets[0]
                        
                        # 保存 condition_id
                        if update_state:
                            condition_id = market.get('conditionId') or market.get('condition_id')
                            if condition_id:
                                self.condition_id = condition_id
                                print(f"[{datetime.now().isoformat()}] 🔑 [UpDown4h] Condition ID: {condition_id}")
                        
                        # 尝试从 tokens 字段获取
                        tokens = market.get('tokens', [])
                        
                        # 如果 tokens 为空,尝试从 clobTokenIds 获取
                        if not tokens:
                            clob_token_ids = market.get('clobTokenIds', [])
                            if clob_token_ids and len(clob_token_ids) >= 2:
                                outcome_index = 0 if self.outcome == 'Up' else 1
                                token_id = clob_token_ids[outcome_index]
                                
                                if update_state:
                                    self.market_slug = slug
                                    end_time_str = market.get('endDate') or market.get('end_date_iso')
                                    if end_time_str:
                                        self.market_end_time = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
                                    self.symbol = token_id
                                
                                print(f"[{datetime.now().isoformat()}] ✅ [UpDown4h] 获取到市场 token_id: {token_id[:20]}...")
                                return token_id
                        else:
                            # 从 tokens 中找到对应的 outcome
                            for token in tokens:
                                token_outcome = token.get('outcome', '')
                                if token_outcome == self.outcome:
                                    token_id = token.get('token_id')
                                    
                                    if update_state:
                                        self.market_slug = slug
                                        end_time_str = market.get('endDate') or market.get('end_date_iso')
                                        if end_time_str:
                                            self.market_end_time = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
                                        self.symbol = token_id
                                    
                                    print(f"[{datetime.now().isoformat()}] ✅ [UpDown4h] 获取到市场 token_id: {token_id[:20]}...")
                                    return token_id
            
            print(f"[{datetime.now().isoformat()}] ❌ [UpDown4h] 未找到市场: {slug}")
            return None
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [UpDown4h] 获取市场失败: {e}")
            return None
