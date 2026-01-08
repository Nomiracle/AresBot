from datetime import datetime, timezone, timedelta
import requests
from .polymarket_adapter import NativePolymarketSpot
import pytz
import time
import threading
import random
from typing import Dict, Callable
from .polymarket_updown15m_adapter import UpDown15m


class UpDown4h(UpDown15m):
    """Up/Down 4小时市场交易所适配器
    
    继承自 UpDown15m，重写时间戳计算逻辑为 4 小时周期
    """
    
    # 4小时周期的起始小时（UTC-5 ET时区）：0, 4, 8, 12, 16, 20
    PERIOD_HOURS = 4
    
    MARKET_PERIOD = '4h'
    MARKET_PERIOD_SECONDS = 4 * 60 * 60  # 市场周期时长（秒）

    @classmethod
    def get_exchange_info(cls) -> Dict:
        """获取交易所信息（类方法）"""
        return {
            'id': 'native_updown_4h',
            'name': 'Polymarket-涨跌4小时',
            'description': 'Polymarket Up/Down 4h (Auto)'
        }
    
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