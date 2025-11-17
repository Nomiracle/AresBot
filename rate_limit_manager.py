"""
币安API限制管理器
负责计算和调整机器人间隔时间,确保不超过币安的限制:
- 10秒内最多100次订单操作
- 24小时内最多200000次订单操作
"""
from typing import Dict, List, Tuple
from datetime import datetime


class RateLimitManager:
    """API限制管理器"""
    
    # 币安限制常量
    LIMIT_10S = 100  # 10秒内最多100次
    LIMIT_24H = 200000  # 24小时内最多200000次
    
    # 安全系数(保留20%余量)
    SAFETY_MARGIN = 0.8
    
    @staticmethod
    def calculate_order_rate(interval: float) -> Tuple[float, float]:
        """
        计算给定间隔下的订单频率
        
        Args:
            interval: 查询间隔(秒)
            
        Returns:
            (10秒内订单数, 24小时内订单数)
        """
        # 每个循环可能产生的订单操作数:
        # - 查询未完成订单: 1次
        # - 改价买单(如果有): 2次 (取消+新建)
        # - 改价卖单(如果有): 2次 (取消+新建)
        # - 新建买单(如果没有订单): 1次
        # 最坏情况: 每个循环5次操作
        operations_per_cycle = 3
        
        # 10秒内的循环次数
        cycles_10s = 10.0 / interval
        orders_10s = cycles_10s * operations_per_cycle
        
        # 24小时内的循环次数
        cycles_24h = (24 * 60 * 60) / interval
        orders_24h = cycles_24h * operations_per_cycle
        
        return orders_10s, orders_24h
    
    @staticmethod
    def check_rate_limit(bots_config: List[Dict]) -> Tuple[bool, str, float, float]:
        """
        检查一组机器人配置是否会超过限制
        
        Args:
            bots_config: 机器人配置列表,每个配置包含 interval 字段
            
        Returns:
            (是否超限, 错误信息, 10秒预计订单数, 24小时预计订单数)
        """
        total_10s = 0.0
        total_24h = 0.0
        
        for config in bots_config:
            interval = config.get('interval', 1)
            orders_10s, orders_24h = RateLimitManager.calculate_order_rate(interval)
            total_10s += orders_10s
            total_24h += orders_24h
        
        # 应用安全系数
        safe_limit_10s = RateLimitManager.LIMIT_10S * RateLimitManager.SAFETY_MARGIN
        safe_limit_24h = RateLimitManager.LIMIT_24H * RateLimitManager.SAFETY_MARGIN
        
        if total_10s > safe_limit_10s:
            return False, f"10秒限制: 预计{total_10s:.1f}次 > 安全限制{safe_limit_10s:.1f}次", total_10s, total_24h
        
        if total_24h > safe_limit_24h:
            return False, f"24小时限制: 预计{total_24h:.0f}次 > 安全限制{safe_limit_24h:.0f}次", total_10s, total_24h
        
        return True, "", total_10s, total_24h
    
    @staticmethod
    def adjust_intervals(bots_config: List[Dict]) -> List[Dict]:
        """
        自动调整机器人间隔时间,确保不超过限制
        
        算法:
        1. 计算当前总频率
        2. 如果超限,计算需要的缩放因子
        3. 按每个机器人的间隔占比,等比例增加间隔
        
        Args:
            bots_config: 机器人配置列表
            
        Returns:
            调整后的配置列表
        """
        # 检查是否超限
        is_ok, error_msg, total_10s, total_24h = RateLimitManager.check_rate_limit(bots_config)
        
        if is_ok:
            return bots_config  # 不需要调整
        
        # 计算需要的缩放因子(取两个限制中更严格的)
        safe_limit_10s = RateLimitManager.LIMIT_10S * RateLimitManager.SAFETY_MARGIN
        safe_limit_24h = RateLimitManager.LIMIT_24H * RateLimitManager.SAFETY_MARGIN
        
        scale_10s = total_10s / safe_limit_10s if total_10s > safe_limit_10s else 1.0
        scale_24h = total_24h / safe_limit_24h if total_24h > safe_limit_24h else 1.0
        scale_factor = max(scale_10s, scale_24h)
        
        # 调整所有机器人的间隔
        adjusted_configs = []
        for config in bots_config:
            adjusted_config = config.copy()
            old_interval = config.get('interval', 1)
            new_interval = old_interval * scale_factor
            
            # 向上取整到整数秒
            new_interval = int(new_interval) + (1 if new_interval % 1 > 0 else 0)
            
            adjusted_config['interval'] = new_interval
            adjusted_config['_original_interval'] = old_interval  # 保存原始值
            adjusted_config['_adjusted'] = True
            
            adjusted_configs.append(adjusted_config)
        
        return adjusted_configs
    
    @staticmethod
    def get_bots_by_api_key(user_bots: Dict, api_key: str) -> List[Dict]:
        """
        获取使用指定API key的所有机器人配置
        
        Args:
            user_bots: 全局机器人字典
            api_key: API密钥
            
        Returns:
            机器人配置列表
        """
        configs = []
        
        for username, user_data in user_bots.items():
            if not isinstance(user_data, dict):
                continue
                
            bots = user_data.get('bots', {})
            for symbol, bot_data in bots.items():
                if not bot_data.get('running'):
                    continue
                    
                exchange = bot_data.get('exchange')
                if exchange and hasattr(exchange, 'api_key') and exchange.api_key == api_key:
                    config = bot_data.get('config', {})
                    configs.append({
                        'username': username,
                        'symbol': symbol,
                        'interval': config.get('interval', 1),
                        'config': config
                    })
        
        return configs
    
    @staticmethod
    def format_adjustment_message(old_configs: List[Dict], new_configs: List[Dict]) -> str:
        """
        格式化调整信息
        
        Args:
            old_configs: 原始配置
            new_configs: 调整后配置
            
        Returns:
            格式化的消息
        """
        if not new_configs or not any(c.get('_adjusted') for c in new_configs):
            return ""
        
        lines = ["[!] 检测到API限制风险,已自动调整间隔时间:"]
        
        for old, new in zip(old_configs, new_configs):
            if new.get('_adjusted'):
                old_interval = old.get('interval', 1)
                new_interval = new.get('interval', 1)
                symbol = old.get('symbol', '未知')
                username = old.get('username', '未知')
                
                lines.append(f"  - [{username}] {symbol}: {old_interval}秒 -> {new_interval}秒")
        
        return "\n".join(lines)


def check_and_adjust_rate_limit(user_bots: Dict, new_config: Dict, api_key: str) -> Tuple[bool, str, Dict]:
    """
    检查并调整API限制(便捷函数)
    
    Args:
        user_bots: 全局机器人字典
        new_config: 新机器人配置
        api_key: API密钥
        
    Returns:
        (是否允许启动, 提示信息, 调整后的配置)
    """
    manager = RateLimitManager()
    
    # 获取该API key下所有运行中的机器人
    existing_bots = manager.get_bots_by_api_key(user_bots, api_key)
    
    # 添加新机器人配置
    all_configs = existing_bots + [{
        'username': 'new',
        'symbol': new_config.get('symbol', '未知'),
        'interval': new_config.get('interval', 1),
        'config': new_config
    }]
    
    # 检查是否超限
    is_ok, error_msg, total_10s, total_24h = manager.check_rate_limit(all_configs)
    
    if is_ok:
        return True, f"[OK] API限制检查通过 (10秒:{total_10s:.1f}次, 24小时:{total_24h:.0f}次)", new_config
    
    # 超限,尝试调整
    print(f"[{datetime.now().isoformat()}] WARNING: {error_msg}")
    
    adjusted_configs = manager.adjust_intervals(all_configs)
    
    # 应用调整到现有机器人
    for adj_config in adjusted_configs[:-1]:  # 排除最后一个(新机器人)
        username = adj_config['username']
        symbol = adj_config['symbol']
        
        if username in user_bots and isinstance(user_bots[username], dict):
            bots = user_bots[username].get('bots', {})
            if symbol in bots:
                bot_config = bots[symbol].get('config', {})
                bot_config['interval'] = adj_config['interval']
                print(f"[{datetime.now().isoformat()}] ADJUSTED: [{username}] {symbol} 间隔: {adj_config.get('_original_interval')}秒 -> {adj_config['interval']}秒")
    
    # 返回调整后的新机器人配置
    adjusted_new_config = adjusted_configs[-1]['config'].copy()
    adjusted_new_config['interval'] = adjusted_configs[-1]['interval']
    
    # 生成提示信息
    msg = manager.format_adjustment_message(all_configs, adjusted_configs)
    
    # 再次检查调整后是否满足限制
    final_check, final_error, final_10s, final_24h = manager.check_rate_limit(adjusted_configs)
    
    if final_check:
        msg += f"\n[OK] 调整后: 10秒{final_10s:.1f}次, 24小时{final_24h:.0f}次"
        return True, msg, adjusted_new_config
    else:
        msg += f"\n[ERROR] 调整后仍超限: {final_error}"
        return False, msg, new_config
