"""
BTC Up/Down 15分钟市场交易所适配器
自动计算并使用最新的 15 分钟时间戳市场
"""
from datetime import datetime
import requests
from .polymarket_adapter import NativePolymarketSpot


class BtcUpDown15m(NativePolymarketSpot):
    """BTC Up/Down 15分钟市场交易所适配器
    
    自动计算下一个 15 分钟时间戳,并使用对应的市场进行交易
    """
    
    def __init__(self, api_key: str, api_secret: str, outcome: str = "Up", testnet: bool = True):
        """初始化 BTC Up/Down 15分钟市场适配器
        
        Args:
            api_key: 钱包地址
            api_secret: 私钥 (Private Key, 0x开头的十六进制字符串)
            outcome: 交易方向 "Up" 或 "Down" (默认: "Up")
            testnet: 是否使用测试网
        """
        self.outcome = outcome
        
        # 获取最新市场的 token_id
        token_id = self._get_latest_market_token()
        
        if not token_id:
            raise ValueError("无法获取最新的 BTC Up/Down 15分钟市场")
        
        # 调用父类初始化
        super().__init__(api_key, api_secret, token_id, testnet)
        
        print(f"[{datetime.now().isoformat()}] ✅ [BTC Up/Down 15m] 使用市场: {self.market_slug}")
        print(f"[{datetime.now().isoformat()}] ✅ [BTC Up/Down 15m] 交易方向: {outcome}")
        print(f"[{datetime.now().isoformat()}] ✅ [BTC Up/Down 15m] Token ID: {token_id}")
    
    def _calculate_next_timestamp(self) -> int:
        """计算下一个 15 分钟时间戳
        
        Returns:
            int: Unix 时间戳
        """
        now = datetime.now()
        current_minute = now.minute
        next_15min_mark = ((current_minute // 15) + 1) * 15
        
        if next_15min_mark >= 60:
            next_time = now.replace(hour=now.hour + 1, minute=0, second=0, microsecond=0)
        else:
            next_time = now.replace(minute=next_15min_mark, second=0, microsecond=0)
        
        return int(next_time.timestamp())
    
    def _calculate_current_timestamp(self) -> int:
        """计算当前 15 分钟时间戳
        
        Returns:
            int: Unix 时间戳
        """
        now = datetime.now()
        current_minute = now.minute
        current_15min_mark = (current_minute // 15) * 15
        
        current_time = now.replace(minute=current_15min_mark, second=0, microsecond=0)
        
        return int(current_time.timestamp())
    
    def _get_latest_market_token(self) -> str:
        """获取最新市场的 token_id
        
        尝试顺序:
        1. 下一个 15 分钟市场
        2. 当前 15 分钟市场
        3. 前一个 15 分钟市场
        
        Returns:
            str: Token ID,如果获取失败返回 None
        """
        # 尝试多个时间戳
        timestamps_to_try = [
            self._calculate_next_timestamp(),      # 下一个市场
            self._calculate_current_timestamp(),   # 当前市场
        ]
        
        for timestamp in timestamps_to_try:
            try:
                slug = f"btc-updown-15m-{timestamp}"
                
                print(f"[{datetime.now().isoformat()}] 🔍 [BTC Up/Down 15m] 查询市场: {slug}")
                
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
                                    print(f"[{datetime.now().isoformat()}] ⚠️ [BTC Up/Down 15m] 解析 clobTokenIds 失败: {e}")
                            
                            # 查找对应方向的 token
                            for token in tokens:
                                if token.get('outcome', '').lower() == self.outcome.lower():
                                    token_id = token.get('token_id')
                                    self.market_slug = slug
                                    print(f"[{datetime.now().isoformat()}] ✅ [BTC Up/Down 15m] 找到 {self.outcome} token: {token_id}")
                                    return token_id
                            
                            # 如果没有找到指定方向,使用第一个 token
                            if tokens:
                                token_id = tokens[0].get('token_id')
                                actual_outcome = tokens[0].get('outcome', 'Unknown')
                                self.market_slug = slug
                                print(f"[{datetime.now().isoformat()}] ⚠️ [BTC Up/Down 15m] 未找到 {self.outcome},使用 {actual_outcome}: {token_id}")
                                return token_id
                
                print(f"[{datetime.now().isoformat()}] ⏭️ [BTC Up/Down 15m] 市场 {slug} 不存在,尝试下一个...")
                
            except Exception as e:
                print(f"[{datetime.now().isoformat()}] ❌ [BTC Up/Down 15m] 查询失败: {e}")
                continue
        
        print(f"[{datetime.now().isoformat()}] ❌ [BTC Up/Down 15m] 所有时间戳都无可用市场")
        return None
    
    def refresh_market(self) -> bool:
        """刷新到最新的市场
        
        当当前市场即将结束或已结束时,可以调用此方法切换到新市场
        
        Returns:
            bool: 是否成功刷新
        """
        try:
            print(f"[{datetime.now().isoformat()}] 🔄 [BTC Up/Down 15m] 刷新市场...")
            
            # 获取新的 token_id
            new_token_id = self._get_latest_market_token()
            
            if new_token_id and new_token_id != self.symbol:
                self.symbol = new_token_id
                print(f"[{datetime.now().isoformat()}] ✅ [BTC Up/Down 15m] 市场已更新: {self.market_slug}")
                print(f"[{datetime.now().isoformat()}] ✅ [BTC Up/Down 15m] 新 Token ID: {new_token_id}")
                return True
            elif new_token_id == self.symbol:
                print(f"[{datetime.now().isoformat()}] ℹ️ [BTC Up/Down 15m] 已是最新市场")
                return True
            else:
                print(f"[{datetime.now().isoformat()}] ❌ [BTC Up/Down 15m] 刷新失败")
                return False
                
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ [BTC Up/Down 15m] 刷新市场失败: {e}")
            return False
    
    def get_market_info(self) -> dict:
        """获取当前市场信息
        
        Returns:
            dict: 市场信息
        """
        return {
            'slug': self.market_slug,
            'token_id': self.symbol,
            'outcome': self.outcome,
            'timestamp': self._calculate_next_timestamp(),
            'end_time': datetime.fromtimestamp(self._calculate_next_timestamp()).isoformat()
        }
