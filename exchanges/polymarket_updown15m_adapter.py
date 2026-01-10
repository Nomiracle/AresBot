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
import random
from typing import Dict, Callable


class UpDown15m(NativePolymarketSpot):
    """Up/Down 15分钟市场交易所适配器
    
    自动计算下一个 15 分钟时间戳,并使用对应的市场进行交易
    支持多种市场，通过 symbol 参数指定，格式为 "market-outcome"，如 "btc-Up"
    """
    
    # 默认市场关闭前的阈值时间(秒) - 用于取消订单和刷新市场
    DEFAULT_MARKET_CLOSE_THRESHOLD_SECONDS = 180

    MARKET_PERIOD = '15m'
    MARKET_PERIOD_SECONDS = 15 * 60  # 市场周期时长（秒）
    
    def __init__(self, api_key: str, api_secret: str, symbol: str = "btc-Up", testnet: bool = True,
                 min_price_threshold: float = None, market_close_threshold: int = None,
                 username: str = None):
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
            username: 用户名（用于通知等功能）
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
        
        # 止损相关属性
        self._stop_loss_timers = {}  # 止损定时器字典 {market_slug: timer}
        self._stop_loss_lock = threading.Lock()  # 止损定时器锁
        self._stop_loss_cache = {}  # 止损状态缓存 {order_id: {'buy_price': float, 'market_slug': str}}
        
        # 保存用户名用于通知
        self.username = username
        
        # 获取最新市场的 token_id
        token_id = self._get_latest_market_token()
        
        if not token_id:
            raise ValueError(f"无法获取最新的 {self.market_prefix.upper()} Up/Down 15分钟市场")
        
        # 保存 min_price_threshold 用于传递给父类
        self._min_price_threshold = min_price_threshold
        
        # 调用父类初始化
        super().__init__(api_key, api_secret, token_id, testnet, min_price_threshold=min_price_threshold)
        
        print(f"[{datetime.now().isoformat()}] ✅ {self._get_log_prefix()}  使用市场: {self.market_slug}")
        print(f"[{datetime.now().isoformat()}] ✅ {self._get_log_prefix()}  市场前缀: {self.market_prefix}")
        print(f"[{datetime.now().isoformat()}] ✅ {self._get_log_prefix()}  交易方向: {self.outcome}")
        print(f"[{datetime.now().isoformat()}] ✅ {self._get_log_prefix()}  Token ID: {token_id}")
        print(f"[{datetime.now().isoformat()}] ✅ {self._get_log_prefix()}  市场关闭阈值: {self.market_close_threshold}秒")
        
        # 注意: 定时器将在 start_ws() 中设置,确保客户端已完成认证
    
    def _cache_sell_order_for_stop_loss(self, order_id: str, buy_price: float) -> None:
        """缓存卖单信息用于止损
        
        Args:
            order_id: 卖单ID
            buy_price: 买入价格
        """
        self._stop_loss_cache[order_id] = {
            'buy_price': buy_price,
            'market_slug': self.market_slug,
            'timestamp': datetime.now().isoformat()
        }
        print(f"{self._get_log_prefix()} 💾 已缓存卖单 {order_id} 止损信息，买入价格: {buy_price}")
    
    def _update_stop_loss_cache_on_replace(self, old_order_id: str, new_order_id: str, buy_price: float) -> None:
        """改价时更新止损缓存
        
        Args:
            old_order_id: 原卖单ID
            new_order_id: 新卖单ID
            buy_price: 买入价格
        """
        # 如果原订单在缓存中，更新到新订单
        if old_order_id in self._stop_loss_cache:
            cache_data = self._stop_loss_cache.pop(old_order_id)
            cache_data['buy_price'] = buy_price  # 更新买入价格
            self._stop_loss_cache[new_order_id] = cache_data
            print(f"{self._get_log_prefix()} 🔄 已更新止损缓存：{old_order_id} -> {new_order_id}，买入价格: {buy_price}")
        else:
            # 如果原订单不在缓存中，直接缓存新订单
            self._cache_sell_order_for_stop_loss(new_order_id, buy_price)
    
    def _clear_stop_loss_cache(self, order_id: str) -> None:
        """清除止损缓存（订单正常成交或取消时）
        
        Args:
            order_id: 订单ID
        """
        if order_id in self._stop_loss_cache:
            del self._stop_loss_cache[order_id]
            print(f"{self._get_log_prefix()} 🗑️ 已清除订单 {order_id} 的止损缓存")
    
    def _insert_stop_loss_order_to_database(self, original_order_id: str, market_order_id: str, 
                                           executed_price: float, quantity: float) -> bool:
        """插入止损订单记录到数据库（使用现有字段）
        
        Args:
            original_order_id: 原始卖单ID
            market_order_id: 市价卖单ID
            executed_price: 执行价格
            quantity: 数量
            
        Returns:
            bool: 是否成功插入
        """
        try:
            if not self.username:
                print(f"{self._get_log_prefix()} ⚠️ 用户名为空，无法更新数据库")
                return False
            
            # 获取缓存的买入价格
            cache_data = self._stop_loss_cache.get(original_order_id)
            if not cache_data:
                print(f"{self._get_log_prefix()} ⚠️ 未找到订单 {original_order_id} 的止损缓存")
                return False
            
            buy_price = cache_data['buy_price']
            
            # 使用现有的insert_order函数插入止损订单记录
            from database import insert_order
            
            success = insert_order(
                username=self.username,
                symbol=self.original_symbol,
                price=str(executed_price),  # 市价执行价格
                quantity=str(quantity),
                side='SELL',
                status='FILLED',
                order_id=market_order_id,
                buy_price=str(buy_price),  # 原始买入价格
                exchange='polymarket'
            )
            
            if success:
                print(f"{self._get_log_prefix()} ✅ 已插入止损订单记录：买入{buy_price} -> 卖出{executed_price} （{original_order_id} -> {market_order_id}）")
                # 注意：缓存已在_execute_market_sell中清除，这里不需要重复清除
            
            return success
            
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 插入止损订单记录失败: {e}")
            return False
    
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
        api_key_short = getattr(self, 'api_key', None)
        api_key_short = api_key_short[:6] if api_key_short else "NOKEY"
        market_slug = getattr(self, 'market_slug', 'N/A')
        outcome = getattr(self, 'outcome', 'N/A')
        return f"[{datetime.now().isoformat()}] [{api_key_short}-{market_slug}-{outcome}]"

    @classmethod
    def get_exchange_info(cls) -> Dict:
        """获取交易所信息（类方法）"""
        return {
            'id': 'native_updown_15m',
            'name': 'Polymarket-涨跌15分钟',
            'description': 'Polymarket Up/Down 15m (Auto)'
        }
    
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
            slug = f"{self.market_prefix}-updown-{self.MARKET_PERIOD}-{timestamp}"
            
            print(f"[{datetime.now().isoformat()}] 🔍 {self._get_log_prefix()}  查询市场: {slug}")
            
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
                                print(f"[{datetime.now().isoformat()}] 🔑 {self._get_log_prefix()}  Condition ID: {condition_id}")
                        
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
                            print(f"[{datetime.now().isoformat()}] ⚠️ {self._get_log_prefix()}  解析 clobTokenIds 失败: {e}")
                        
                        # 查找对应方向的 token
                        print(f"[{datetime.now().isoformat()}] 🔍 {self._get_log_prefix()}  市场 {slug} 有 {len(tokens)} 个 token")
                        for token in tokens:
                            print(f"[{datetime.now().isoformat()}] 🔍 {self._get_log_prefix()}    - {token.get('outcome')}: {token.get('token_id')}")
                            if token.get('outcome', '').lower() == self.outcome.lower():
                                token_id = token.get('token_id')
                                
                                if update_state:
                                    self.market_slug = slug
                                    # 市场结束时间 = 市场开始时间 + 周期时长
                                    self.market_end_time = timestamp + self.MARKET_PERIOD_SECONDS
                                
                                print(f"[{datetime.now().isoformat()}] ✅ {self._get_log_prefix()}  找到 {self.outcome} token")
                                print(f"[{datetime.now().isoformat()}] ✅ {self._get_log_prefix()}  Slug: {slug} (开始: {datetime.fromtimestamp(timestamp, tz=pytz.UTC).strftime('%H:%M')} UTC)")
                                print(f"[{datetime.now().isoformat()}] ✅ {self._get_log_prefix()}  Token ID: {token_id}")
                                print(f"[{datetime.now().isoformat()}] ⏰ {self._get_log_prefix()}  市场结束时间: {datetime.fromtimestamp(self.market_end_time, tz=pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC")
                                return token_id
                        
                        # 如果没有找到指定方向,使用第一个 token
                        if tokens:
                            token_id = tokens[0].get('token_id')
                            actual_outcome = tokens[0].get('outcome', 'Unknown')
                            
                            if update_state:
                                self.market_slug = slug
                                # 市场结束时间 = 市场开始时间 + MARKET_PERIOD_SECONDS
                                self.market_end_time = timestamp + self.MARKET_PERIOD_SECONDS
                            
                            print(f"[{datetime.now().isoformat()}] ⚠️ {self._get_log_prefix()}  未找到 {self.outcome},使用 {actual_outcome}: {token_id}")
                            print(f"[{datetime.now().isoformat()}] ⏰ {self._get_log_prefix()}  市场开始时间: {datetime.fromtimestamp(timestamp, tz=pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC, 当前时间: {datetime.now(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC")
                            print(f"[{datetime.now().isoformat()}] ⏰ {self._get_log_prefix()}  市场结束时间: {datetime.fromtimestamp(self.market_end_time, tz=pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC")
                            return token_id
            
            print(f"[{datetime.now().isoformat()}] ⏭️ {self._get_log_prefix()}  市场 {slug} 不存在")
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ {self._get_log_prefix()}  查询失败: {e}")
        
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
            print(f"[{datetime.now().isoformat()}] ❌ {self._get_log_prefix()}  无法获取最新市场")
        
        return token_id
    
    def _get_next_market_token(self, initial_delay: int = 5) -> str:
        """获取下一个 15 分钟市场的 token_id
        
        如果市场不存在,会在当前市场结束时间之前持续尝试
        重试间隔递增: 5秒, 10秒, 15秒, 20秒...
        
        Args:
            initial_delay: 初始重试间隔秒数 (默认5秒)
        
        Returns:
            str: Token ID,如果获取失败返回 None
        """
        next_timestamp = self._calculate_next_timestamp()
        attempt = 0
        current_delay = initial_delay
        
        while True:
            attempt += 1
            token_id = self._get_market_token_by_timestamp(next_timestamp, update_state=True)
            
            if token_id:
                if attempt > 1:
                    print(f"[{datetime.now().isoformat()}] ✅ {self._get_log_prefix()}  第{attempt}次尝试成功获取市场")
                return token_id
            
            # 检查是否还有时间继续重试
            if self.market_end_time:
                seconds_left = self.get_seconds_until_market_close()
                if seconds_left <= current_delay:
                    print(f"[{datetime.now().isoformat()}] ⏰ {self._get_log_prefix()}  距离市场结束仅剩{seconds_left}秒,停止重试")
                    break
            
            # 等待后重试
            print(f"[{datetime.now().isoformat()}] ⏳ {self._get_log_prefix()}  市场尚未创建,{current_delay}秒后重试 (第{attempt}次尝试)")
            time.sleep(current_delay)
            
            # 递增重试间隔
            current_delay += initial_delay
        
        print(f"[{datetime.now().isoformat()}] ❌ {self._get_log_prefix()}  尝试{attempt}次后仍无法获取下一个市场")
        return None
    
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
            # 添加随机偏移(0-10秒),避免多个市场同时更新
            base_delay = seconds_left - self.market_close_threshold
            random_offset = random.randint(0, 10)
            delay = max(0, base_delay - random_offset)
            print(f"{self._get_log_prefix()} ⏲️ 设置定时器: {delay} 秒后触发市场刷新 (基础延迟={base_delay}秒, 随机偏移=-{random_offset}秒)")
            
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
            old_market_slug = getattr(self, 'market_slug', None)
            print(f"{self._get_log_prefix()} 📝 保存旧市场 asset_id: {old_asset_id}")
            print(f"{self._get_log_prefix()} 📝 保存旧市场 slug: {old_market_slug}")
            
            # 检测并记录卖单，设置止损逻辑
            self._setup_stop_loss_for_market(old_asset_id, old_market_slug)
            
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
            print(f"[{datetime.now().isoformat()}] 🔄 {self._get_log_prefix()}  刷新市场...")
            print(f"[{datetime.now().isoformat()}] 🔍 {self._get_log_prefix()}  当前状态: slug={self.market_slug}, token_id={self.symbol}")
            
            old_token_id = self.symbol
            old_slug = self.market_slug
            
            # 获取下一个市场的 token_id (这会同时更新 self.market_slug 和 self.market_end_time)
            new_token_id = self._get_next_market_token()
            new_slug = self.market_slug
            
            if new_token_id and new_token_id != old_token_id:
                # 清空成交订单去重缓存（新市场的订单 ID 不会与旧市场冲突）
                self.clear_filled_order_ids()
                
                # 关闭旧市场的 WebSocket（保留止损定时器）
                print(f"[{datetime.now().isoformat()}] 🔌 {self._get_log_prefix()}  关闭旧市场 WebSocket（保留止损定时器）...")
                self.stop_ws_for_refresh()
                
                # 等待 WebSocket 完全关闭
                time.sleep(1)
                
                # 更新 token_id
                self.symbol = new_token_id
                
                # 如果之前有 WebSocket 回调,重新启动新市场的 WebSocket
                if self._ws_callbacks:
                    print(f"[{datetime.now().isoformat()}] 🚀 {self._get_log_prefix()}  启动新市场 WebSocket...")
                    self.start_ws(
                        on_price_update=self._ws_callbacks['price'],
                        on_order_update=self._ws_callbacks['order']
                    )
                
                print(f"[{datetime.now().isoformat()}] ✅ {self._get_log_prefix()}  市场已更新")
                print(f"[{datetime.now().isoformat()}] ✅ {self._get_log_prefix()}  旧市场: token_id={old_token_id}")
                print(f"[{datetime.now().isoformat()}] ✅ {self._get_log_prefix()}  新市场: slug={self.market_slug}, token_id={new_token_id}")
                

                
                # 发送 refresh_market 事件给 trading.py，清除旧市场的缓存订单
                if self._ws_callbacks and self._ws_callbacks.get('order'):
                    refresh_event = {
                        'event_type': 'refresh_market',
                        'symbol': self.original_symbol,  # 使用原始 symbol
                        'old_slug': old_slug,
                        'new_slug': new_slug
                    }
                    self._ws_callbacks['order'](refresh_event)
                    print(f"[{datetime.now().isoformat()}] 📤 {self._get_log_prefix()}  已发送 refresh_market 事件")
                time.sleep(1)
                # 重置市场切换标志，允许下单和改价
                self._is_switching_market = False
                print(f"[{datetime.now().isoformat()}] ✅ {self._get_log_prefix()}  市场切换完成，允许下单和改价")
                
                return True
            elif new_token_id == old_token_id:
                print(f"[{datetime.now().isoformat()}] ℹ️ {self._get_log_prefix()}  已是最新市场: slug={self.market_slug}, token_id={self.symbol}")
                # 重置市场切换标志
                self._is_switching_market = False
                return True
            else:
                # new_token_id 为 None，说明交易所可能在维护，继续尝试下一个市场
                print(f"[{datetime.now().isoformat()}] ⚠️ {self._get_log_prefix()}  当前市场刷新失败，可能交易所维护中，继续尝试下一个市场...")
                # 不重置 _is_switching_market 标志，继续尝试
                # 递归调用，尝试下一个市场（market_end_time 已在 _get_next_market_token 中更新）
                retry_delay = random.randint(10, 20)  # 随机等待10-20秒
                print(f"[{datetime.now().isoformat()}] ⏳ {self._get_log_prefix()}  等待 {retry_delay} 秒后重试...")
                time.sleep(retry_delay)
                return self.refresh_market()
                
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ {self._get_log_prefix()}  刷新市场失败: {e}")
            import traceback
            traceback.print_exc()
            # 异常时也要重置标志
            self._is_switching_market = False
            return False
    
    
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
    
    def get_notification_info(self) -> str:
        """获取通知消息的附加信息
        
        重写父类方法,返回当前市场的 slug
        
        Returns:
            str: 市场 slug,如 "will-btc-close-higher-on-jan-5-2026-at-1-00-pm-et-than-at-12-45-pm-et"
        """
        return self.market_slug
    
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
        now = datetime.now(timezone.utc)
        
        # 确保 market_end_time 是 datetime 对象
        if isinstance(self.market_end_time, datetime):
            end_time = self.market_end_time
            # 如果没有时区信息，假设为 UTC
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=timezone.utc)
            seconds_left = int((end_time - now).total_seconds())
        else:
            # 如果是时间戳（float/int）
            seconds_left = int(self.market_end_time - now.timestamp())
        
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
        
        # 优先检查市场切换状态
        if self._is_switching_market:
            error_msg = "市场切换中，禁止下单"
            print(f"{self._get_log_prefix()} 🚫 {error_msg}")
            raise RuntimeError(error_msg)
        
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
        
        # 检查通过，可以下单
        return
    
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
        
        重写父类方法,添加市场关闭前的检查和止损缓存
        
        Args:
            quantity: 数量
            price: 价格
            **kwargs: 其他参数，包括 entry_price（用于止损计算）
            
        Raises:
            RuntimeError: 如果市场即将关闭
        """
        # 检查市场是否即将关闭(会抛出异常)
        self._check_market_close_before_order()
        
        # 从kwargs获取买入价格
        entry_price = kwargs.get('entry_price')
        
        # 调用父类方法下单
        result = super().order_limit_sell(quantity, price, **kwargs)
        
        # 如果下单成功且提供了买入价格，缓存止损信息
        if result and entry_price:
            order_id = result.get('orderId') or result.get('id')
            if order_id:
                self._cache_sell_order_for_stop_loss(order_id, entry_price)
        
        return result
    
    def cancel_replace_order(self, side: str, order_type: str, 
                            quantity: float, price: str, cancel_order_id: str, **kwargs) -> Dict:
        """取消并替换订单（改价）- 重写父类方法，添加止损缓存更新
        
        Args:
            side: 订单方向 ('BUY' 或 'SELL')
            order_type: 订单类型 ('LIMIT' 等)
            quantity: 数量
            price: 新价格
            cancel_order_id: 要取消的订单ID
            **kwargs: 其他参数，包括 entry_price（用于止损缓存更新）
            
        Returns:
            Dict: 包含新订单信息的字典
        """
        # 如果不是卖单，直接调用父类方法
        if side.upper() != 'SELL':
            return super().cancel_replace_order(side, order_type, quantity, price, cancel_order_id, **kwargs)
        
        # 只有卖单才执行以下重写逻辑
        try:
            # 从kwargs获取买入价格
            entry_price = kwargs.get('entry_price')
            
            print(f"{self._get_log_prefix()} 🔄 开始改价: orderID={cancel_order_id}, side={side}, new_price={price}, quantity={quantity}")
            
            # 检查是否为虚拟订单（来自持仓的虚拟卖单）
            is_virtual = cancel_order_id.startswith('pos_token_')
            
            if is_virtual:
                # 虚拟订单不需要取消，直接创建新订单
                print(f"{self._get_log_prefix()} 💰 虚拟订单无需取消，直接创建新订单")
            else:
                # Polymarket不支持原子性的cancel_replace,需要分两步
                # 1. 取消旧订单
                print(f"{self._get_log_prefix()} 🚫 改价步骤1: 取消旧订单 {cancel_order_id}")
                self.cancel_order(cancel_order_id)
                
                # 清除对应的止损缓存
                print(f"{self._get_log_prefix()} 🗑️ 已清除订单 {cancel_order_id} 的止损缓存")
                self._clear_stop_loss_cache(cancel_order_id)
                
                # 短暂延迟确保取消完成
                time.sleep(0.1)
            
            # 2. 创建新订单
            print(f"{self._get_log_prefix()} 📝 改价步骤2: 创建新订单 price={price}, quantity={quantity}")
            new_order = self.order_limit_sell(quantity, price, entry_price=entry_price, **kwargs)
            
            new_order_id = new_order.get('orderId') or new_order.get('id')
            print(f"{self._get_log_prefix()} ✅ 改价完成: 旧订单={cancel_order_id}, 新订单={new_order_id}")
            
            # 如果提供了买入价格，更新止损缓存
            if entry_price and new_order_id:
                self._update_stop_loss_cache_on_replace(cancel_order_id, new_order_id, entry_price)
            
            # 返回 Binance 兼容的格式,包含 newOrderResponse
            return {
                'newOrderResponse': new_order
            }
                
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 改价失败: orderID={cancel_order_id}, error={e}")
            raise
        
    def stop_ws(self) -> None:
        """停止 WebSocket
        
        重写父类方法，取消定时器和止损定时器
        """
        # 取消定时器
        with self._timer_lock:
            if self._refresh_timer:
                self._refresh_timer.cancel()
                self._refresh_timer = None
                print(f"{self._get_log_prefix()} ⏲️ 已取消市场刷新定时器")
        
        # 取消所有止损定时器
        with self._stop_loss_lock:
            for market_slug, timer in self._stop_loss_timers.items():
                if timer:
                    timer.cancel()
                    print(f"{self._get_log_prefix()} 🛡️ 已取消 {market_slug} 的止损定时器")
            self._stop_loss_timers.clear()
        
        # 调用父类方法
        super().stop_ws()
    
    def stop_ws_for_refresh(self) -> None:
        """停止 WebSocket 仅用于市场刷新（保留止损定时器）
        
        专门用于市场切换时停止 WebSocket，不影响止损定时器
        """
        # 只取消市场刷新定时器，保留止损定时器
        with self._timer_lock:
            if self._refresh_timer:
                self._refresh_timer.cancel()
                self._refresh_timer = None
                print(f"{self._get_log_prefix()} ⏲️ 已取消市场刷新定时器（保留止损定时器）")
        
        # 调用父类方法停止 WebSocket
        super().stop_ws()
    
    def _setup_stop_loss_for_market(self, asset_id: str, market_slug: str) -> None:
        """为指定市场设置止损逻辑
        
        Args:
            asset_id: 市场的 asset_id (token_id)
            market_slug: 市场的 slug
        """
        try:
            if not market_slug:
                print(f"{self._get_log_prefix()} ⚠️ 市场slug为空，跳过止损设置")
                return
            
            # 检测该市场的卖单
            sell_orders = self._detect_sell_orders(asset_id)
            
            if not sell_orders:
                print(f"{self._get_log_prefix()} ℹ️ 市场 {market_slug} 没有卖单，无需设置止损")
                return
            
            # 提取订单号用于日志
            order_ids = [order.get('orderId') for order in sell_orders if order.get('orderId')]
            order_ids_str = ', '.join(order_ids) if order_ids else '无订单号'
            
            print(f"{self._get_log_prefix()} 🛡️ [止损设置] 市场 {market_slug} 检测到 {len(sell_orders)} 个卖单，订单号: {order_ids_str}")
            
            # 记录卖单信息
            self._record_sell_orders(market_slug, sell_orders)
            
            # 计算止损检查时间：(市场结束时间 - 当前时间) / 2
            current_time = datetime.now(timezone.utc)
            market_end_time = self.market_end_time
            
            if not market_end_time:
                print(f"{self._get_log_prefix()} ⚠️ 无法获取市场结束时间，跳过止损设置")
                return
            
            # 确保 market_end_time 是 datetime 对象
            if isinstance(market_end_time, (int, float)):
                market_end_time = datetime.fromtimestamp(market_end_time, tz=timezone.utc)
            elif market_end_time.tzinfo is None:
                market_end_time = market_end_time.replace(tzinfo=timezone.utc)
            
            # 计算剩余时间和止损检查时间
            total_seconds_left = (market_end_time - current_time).total_seconds()
            
            if total_seconds_left <= 0:
                print(f"{self._get_log_prefix()} ⚠️ 市场已结束，无需设置止损")
                return
            
            # 止损检查时间为剩余时间的一半
            stop_loss_delay = max(30, total_seconds_left / 2)  # 最少30秒
            
            print(f"{self._get_log_prefix()} ⏰ 市场剩余时间: {total_seconds_left:.0f}秒，止损检查时间: {stop_loss_delay:.0f}秒后")
            
            # 设置止损定时器
            with self._stop_loss_lock:
                # 取消该市场的旧定时器（如果存在）
                if market_slug in self._stop_loss_timers:
                    old_timer = self._stop_loss_timers[market_slug]
                    if old_timer:
                        old_timer.cancel()
                
                # 创建新的止损定时器
                timer = threading.Timer(
                    stop_loss_delay,
                    self._check_and_execute_stop_loss,
                    args=[asset_id, market_slug, sell_orders]
                )
                timer.daemon = True
                timer.start()
                
                self._stop_loss_timers[market_slug] = timer
                
            print(f"{self._get_log_prefix()} ✅ 已为市场 {market_slug} 设置止损定时器，{stop_loss_delay:.0f}秒后执行")
            
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 设置止损失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _detect_sell_orders(self, asset_id: str) -> list:
        """检测指定市场的卖单
        
        Args:
            asset_id: 市场的 asset_id
            
        Returns:
            list: 卖单列表
        """
        try:
            print(f"{self._get_log_prefix()} 🔍 检测市场 {asset_id} 的卖单...")
            
            # 获取开放订单
            open_orders = self.get_open_orders(asset_id=asset_id)
            
            # 筛选卖单
            sell_orders = [order for order in open_orders if order.get('side') == 'SELL']
            
            print(f"{self._get_log_prefix()} 🔍 发现 {len(sell_orders)} 个卖单")
            
            for order in sell_orders:
                order_id = order.get('orderId')
                price = order.get('price')
                quantity = order.get('origQty')
                print(f"{self._get_log_prefix()}   - 卖单 {order_id}: 价格={price}, 数量={quantity}")
            
            return sell_orders
            
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 检测卖单失败: {e}")
            return []
    
    def _record_sell_orders(self, market_slug: str, sell_orders: list) -> None:
        """记录卖单信息到日志
        
        Args:
            market_slug: 市场的 slug
            sell_orders: 卖单列表
        """
        try:
            print(f"{self._get_log_prefix()} 📝 记录市场 {market_slug} 的卖单信息:")
            
            for order in sell_orders:
                order_id = order.get('orderId')
                price = order.get('price')
                quantity = order.get('origQty')
                
                log_msg = f"[止损记录] 市场: {market_slug}, 卖单: {order_id}, 价格: {price}, 数量: {quantity}, 时间: {datetime.now().isoformat()}"
                print(f"{self._get_log_prefix()} 📝 {log_msg}")
                
                # 这里可以扩展到数据库记录
                # 例如：insert_stop_loss_record(market_slug, order_id, price, quantity)
                
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 记录卖单信息失败: {e}")
    
    def _check_and_execute_stop_loss(self, asset_id: str, market_slug: str, original_sell_orders: list) -> None:
        """检查并执行止损
        
        Args:
            asset_id: 市场的 asset_id
            market_slug: 市场的 slug
            original_sell_orders: 原始卖单列表
        """
        try:
            # 提取原始订单号用于日志
            original_order_ids = [order.get('orderId') for order in original_sell_orders if order.get('orderId')]
            original_order_ids_str = ', '.join(original_order_ids) if original_order_ids else '无订单号'
            
            print(f"{self._get_log_prefix()} 🛡️ [止损执行] 市场 {market_slug} 开始止损检查，原始订单号: {original_order_ids_str}")
            
            # 清理该市场的止损定时器
            with self._stop_loss_lock:
                if market_slug in self._stop_loss_timers:
                    del self._stop_loss_timers[market_slug]
            
            # 检查原始卖单是否还存在
            current_sell_orders = self._detect_sell_orders(asset_id)
            
            # 找出仍然存在的卖单
            remaining_orders = []
            original_order_ids_set = {str(order.get('orderId')) for order in original_sell_orders}
            current_order_ids_set = {str(order.get('orderId')) for order in current_sell_orders}
            
            remaining_order_ids = original_order_ids_set.intersection(current_order_ids_set)
            
            if not remaining_order_ids:
                print(f"{self._get_log_prefix()} ✅ [止损执行] 市场 {market_slug} 所有原始卖单已成交，无需止损，订单号: {original_order_ids_str}")
                return
            
            # 构建仍然存在的卖单详细信息
            for order in current_sell_orders:
                if str(order.get('orderId')) in remaining_order_ids:
                    remaining_orders.append(order)
            
            # 提取剩余订单号用于日志
            remaining_order_ids_str = ', '.join(remaining_order_ids) if remaining_order_ids else '无订单号'
            
            print(f"{self._get_log_prefix()} ⚠️ [止损执行] 市场 {market_slug} 发现 {len(remaining_orders)} 个卖单仍存在，订单号: {remaining_order_ids_str}，开始市价抛售")
            
            # 执行市价抛售
            self._execute_market_sell(remaining_orders, market_slug)
            
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 止损检查执行失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _execute_market_sell(self, sell_orders: list, market_slug: str) -> None:
        """执行市价抛售
        
        Args:
            sell_orders: 需要抛售的卖单列表
            market_slug: 市场的 slug
        """
        try:
            # 提取所有订单号用于日志
            order_ids = [order.get('orderId') for order in sell_orders if order.get('orderId')]
            order_ids_str = ', '.join(order_ids) if order_ids else '无订单号'
            
            print(f"{self._get_log_prefix()} 🚀 [市价抛售] 市场 {market_slug} 开始执行市价抛售，订单号: {order_ids_str}")
            
            for order in sell_orders:
                order_id = order.get('orderId')
                price = order.get('price')
                quantity = order.get('origQty')
                
                try:
                    print(f"{self._get_log_prefix()} 🔄 [市价抛售] 订单 {order_id} 取消原卖单准备市价抛售...")
                    
                    # 先取消原卖单
                    cancel_result = self.cancel_orders([order_id])
                    canceled = cancel_result.get('canceled', [])
                    
                    if order_id in canceled:
                        print(f"{self._get_log_prefix()} ✅ [市价抛售] 订单 {order_id} 原卖单已取消")
                        
                        # 清除对应的止损缓存
                        print(f"{self._get_log_prefix()} 🗑️ 已清除订单 {order_id} 的止损缓存")
                        self._clear_stop_loss_cache(order_id)
                        
                        # 执行市价卖单
                        print(f"{self._get_log_prefix()} 🚀 [市价抛售] 订单 {order_id} 执行市价抛售，数量: {quantity}")
                        
                        market_sell_result = self.order_market_sell(quantity=quantity)
                        
                        if market_sell_result:
                            market_order_id = market_sell_result.get('orderId') or market_sell_result.get('id')
                            print(f"{self._get_log_prefix()} ✅ [市价抛售] 订单 {order_id} 市价抛售成功，新订单号: {market_order_id}")
                            
                            # 获取执行价格（如果市价单返回了价格）
                            executed_price = market_sell_result.get('price') or price
                            if isinstance(executed_price, str):
                                executed_price = float(executed_price)
                            
                            # 插入止损订单记录到数据库
                            self._insert_stop_loss_order_to_database(
                                original_order_id=order_id,
                                market_order_id=market_order_id,
                                executed_price=executed_price,
                                quantity=float(quantity)
                            )
                            
                            # 发送通知
                            self._send_stop_loss_notification(market_slug, order_id, price, quantity, market_order_id)
                            
                            # 记录日志
                            self._log_stop_loss_execution(market_slug, order_id, price, quantity, market_order_id)
                        else:
                            print(f"{self._get_log_prefix()} ❌ [市价抛售] 订单 {order_id} 市价抛售失败")
                    else:
                        print(f"{self._get_log_prefix()} ❌ [市价抛售] 订单 {order_id} 取消原卖单失败")
                        
                except Exception as order_error:
                    print(f"{self._get_log_prefix()} ❌ [市价抛售] 订单 {order_id} 处理失败: {order_error}")
            
            # 执行完成后，清除所有非当前slug的缓存
            self._clear_other_markets_cache(market_slug)
            
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 市价抛售执行失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _clear_other_markets_cache(self, current_market_slug: str) -> None:
        """清除所有非当前市场的止损缓存
        
        Args:
            current_market_slug: 当前市场的slug
        """
        try:
            if not self._stop_loss_cache:
                return
            
            # 找出需要清除的缓存项（非当前市场的）
            orders_to_remove = []
            for order_id, cache_data in self._stop_loss_cache.items():
                cached_market_slug = cache_data.get('market_slug')
                if cached_market_slug != current_market_slug:
                    orders_to_remove.append(order_id)
            
            # 清除这些缓存项
            for order_id in orders_to_remove:
                del self._stop_loss_cache[order_id]
                print(f"{self._get_log_prefix()} 🗑️ 已清除其他市场订单 {order_id} 的止损缓存")
            
            if orders_to_remove:
                print(f"{self._get_log_prefix()} ✅ 已清除 {len(orders_to_remove)} 个其他市场的止损缓存")
            
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 清除其他市场缓存失败: {e}")
    
    def _send_stop_loss_notification(self, market_slug: str, original_order_id: str, 
                                   original_price: str, quantity: str, market_order_id: str) -> None:
        """发送止损执行通知
        
        Args:
            market_slug: 市场的 slug
            original_order_id: 原始卖单ID
            original_price: 原始价格
            quantity: 数量
            market_order_id: 市价订单ID
        """
        try:
            from notification import DingTalkNotification
            
            # 获取用户名（从父类或其他地方获取）
            username = getattr(self, 'username', None)
            if not username:
                print(f"{self._get_log_prefix()} ⚠️ 无法获取用户名，跳过通知发送")
                return
            
            notifier = DingTalkNotification(username=username)
            
            # 构建通知消息
            time_str = datetime.now().strftime("%H:%M:%S")
            msg = f"[{time_str}] 🛡️ 止损执行 - {market_slug}"
            msg += f"\n原卖单: {original_order_id} (价格: {original_price})"
            msg += f"\n市价抛售: {market_order_id} (数量: {quantity})"
            msg += f"\n原因: 市场即将结束，卖单仍未成交"
            
            success = notifier.send(msg)
            
            if success:
                print(f"{self._get_log_prefix()} ✅ 止损通知发送成功")
            else:
                print(f"{self._get_log_prefix()} ❌ 止损通知发送失败")
                
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 发送止损通知失败: {e}")
    
    def _log_stop_loss_execution(self, market_slug: str, original_order_id: str, 
                                original_price: str, quantity: str, market_order_id: str) -> None:
        """记录止损执行日志
        
        Args:
            market_slug: 市场的 slug
            original_order_id: 原始卖单ID
            original_price: 原始价格
            quantity: 数量
            market_order_id: 市价订单ID
        """
        try:
            log_msg = f"[止损执行] 市场: {market_slug}"
            log_msg += f", 原卖单: {original_order_id} (价格: {original_price}, 数量: {quantity})"
            log_msg += f", 市价订单: {market_order_id}"
            log_msg += f", 时间: {datetime.now().isoformat()}"
            
            print(f"{self._get_log_prefix()} 📝 {log_msg}")
            
            # 这里可以扩展到数据库记录
            # 例如：insert_stop_loss_execution_log(market_slug, original_order_id, original_price, quantity, market_order_id)
            
        except Exception as e:
            print(f"{self._get_log_prefix()} ❌ 记录止损日志失败: {e}")
    
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


    