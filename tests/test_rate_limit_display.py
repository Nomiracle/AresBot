"""
测试币安API限制显示功能
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from exchanges.binance_adapter import _ORDER_WINDOW_10S, _ORDER_WINDOW_24H
from collections import deque
import time


def test_rate_limit_display():
    """测试限制状态获取"""
    print("=" * 60)
    print("测试: 币安API限制状态显示")
    print("=" * 60)
    
    # 模拟API key
    test_api_key = "test_key_123"
    
    # 清空之前的记录
    _ORDER_WINDOW_10S[test_api_key] = deque()
    _ORDER_WINDOW_24H[test_api_key] = deque()
    
    # 创建模拟的BinanceAdapter
    class MockBinanceAdapter:
        def __init__(self, api_key):
            self.api_key = api_key
        
        def get_rate_limit_status(self):
            """获取限制状态"""
            now = time.time()
            ten_seconds_ago = now - 10
            one_day_ago = now - 24 * 60 * 60

            window_10s = _ORDER_WINDOW_10S.setdefault(self.api_key, deque())
            window_24h = _ORDER_WINDOW_24H.setdefault(self.api_key, deque())

            # 清理过期记录
            while window_10s and window_10s[0] <= ten_seconds_ago:
                window_10s.popleft()

            while window_24h and window_24h[0] <= one_day_ago:
                window_24h.popleft()

            count_10s = len(window_10s)
            count_24h = len(window_24h)

            return {
                'count_10s': count_10s,
                'limit_10s': 100,
                'count_24h': count_24h,
                'limit_24h': 200000,
                'exceeded_10s': count_10s > 100,
                'exceeded_24h': count_24h > 200000
            }
    
    adapter = MockBinanceAdapter(test_api_key)
    
    # 场景1: 无订单
    print("\n场景1: 无订单操作")
    status = adapter.get_rate_limit_status()
    print(f"  10秒: {status['count_10s']}/{status['limit_10s']} ({status['count_10s']/status['limit_10s']*100:.1f}%)")
    print(f"  24小时: {status['count_24h']}/{status['limit_24h']} ({status['count_24h']/status['limit_24h']*100:.2f}%)")
    print(f"  超限: 10秒={status['exceeded_10s']}, 24小时={status['exceeded_24h']}")
    
    # 场景2: 添加一些订单
    print("\n场景2: 模拟30次订单操作")
    now = time.time()
    window_10s = _ORDER_WINDOW_10S[test_api_key]
    window_24h = _ORDER_WINDOW_24H[test_api_key]
    
    for i in range(30):
        window_10s.append(now - i * 0.2)  # 每0.2秒一次
        window_24h.append(now - i * 0.2)
    
    status = adapter.get_rate_limit_status()
    print(f"  10秒: {status['count_10s']}/{status['limit_10s']} ({status['count_10s']/status['limit_10s']*100:.1f}%)")
    print(f"  24小时: {status['count_24h']}/{status['limit_24h']} ({status['count_24h']/status['limit_24h']*100:.2f}%)")
    print(f"  超限: 10秒={status['exceeded_10s']}, 24小时={status['exceeded_24h']}")
    
    # 场景3: 接近10秒限制
    print("\n场景3: 接近10秒限制(95次)")
    window_10s.clear()
    window_24h.clear()
    
    for i in range(95):
        window_10s.append(now - i * 0.1)
        window_24h.append(now - i * 0.1)
    
    status = adapter.get_rate_limit_status()
    percent_10s = status['count_10s']/status['limit_10s']*100
    color_10s = '红色' if status['exceeded_10s'] else ('黄色' if percent_10s > 80 else '绿色')
    
    print(f"  10秒: {status['count_10s']}/{status['limit_10s']} ({percent_10s:.1f}%) - 颜色: {color_10s}")
    print(f"  24小时: {status['count_24h']}/{status['limit_24h']} ({status['count_24h']/status['limit_24h']*100:.2f}%)")
    print(f"  超限: 10秒={status['exceeded_10s']}, 24小时={status['exceeded_24h']}")
    
    # 场景4: 超出10秒限制
    print("\n场景4: 超出10秒限制(105次)")
    window_10s.clear()
    window_24h.clear()
    
    for i in range(105):
        window_10s.append(now - i * 0.09)
        window_24h.append(now - i * 0.09)
    
    status = adapter.get_rate_limit_status()
    percent_10s = status['count_10s']/status['limit_10s']*100
    color_10s = '红色' if status['exceeded_10s'] else ('黄色' if percent_10s > 80 else '绿色')
    
    print(f"  10秒: {status['count_10s']}/{status['limit_10s']} ({percent_10s:.1f}%) - 颜色: {color_10s}")
    print(f"  24小时: {status['count_24h']}/{status['limit_24h']} ({status['count_24h']/status['limit_24h']*100:.2f}%)")
    print(f"  超限: 10秒={status['exceeded_10s']}, 24小时={status['exceeded_24h']}")
    
    print("\n" + "=" * 60)
    print("[OK] 测试完成")
    print("=" * 60)
    print("\n前端显示规则:")
    print("  - 绿色: 使用率 <= 80%")
    print("  - 黄色: 使用率 > 80% 且未超限")
    print("  - 红色: 已超限")
    print("  - 超限时显示 '[!]超限' 标记")


if __name__ == '__main__':
    test_rate_limit_display()
