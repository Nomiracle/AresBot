"""
测试API限制管理器
"""
from rate_limit_manager import RateLimitManager, check_and_adjust_rate_limit


def test_calculate_order_rate():
    """测试订单频率计算"""
    print("=" * 60)
    print("测试1: 订单频率计算")
    print("=" * 60)
    
    # 测试不同间隔的订单频率
    intervals = [1, 2, 5, 10]
    for interval in intervals:
        orders_10s, orders_24h = RateLimitManager.calculate_order_rate(interval)
        print(f"间隔 {interval}秒: 10秒内{orders_10s:.1f}次, 24小时内{orders_24h:.0f}次")
    print()


def test_check_rate_limit():
    """测试限制检查"""
    print("=" * 60)
    print("测试2: 限制检查")
    print("=" * 60)
    
    # 场景1: 正常情况(不超限)
    configs_normal = [
        {'interval': 5},
        {'interval': 5},
        {'interval': 5}
    ]
    is_ok, msg, total_10s, total_24h = RateLimitManager.check_rate_limit(configs_normal)
    print(f"场景1 - 3个机器人,间隔5秒:")
    print(f"  结果: {'通过' if is_ok else '超限'}")
    print(f"  10秒: {total_10s:.1f}次, 24小时: {total_24h:.0f}次")
    if msg:
        print(f"  消息: {msg}")
    print()
    
    # 场景2: 10秒限制超限
    configs_10s_exceed = [
        {'interval': 1},
        {'interval': 1},
        {'interval': 1},
        {'interval': 1},
        {'interval': 1}
    ]
    is_ok, msg, total_10s, total_24h = RateLimitManager.check_rate_limit(configs_10s_exceed)
    print(f"场景2 - 5个机器人,间隔1秒:")
    print(f"  结果: {'通过' if is_ok else '超限'}")
    print(f"  10秒: {total_10s:.1f}次, 24小时: {total_24h:.0f}次")
    if msg:
        print(f"  消息: {msg}")
    print()
    
    # 场景3: 24小时限制超限
    configs_24h_exceed = [
        {'interval': 1} for _ in range(20)
    ]
    is_ok, msg, total_10s, total_24h = RateLimitManager.check_rate_limit(configs_24h_exceed)
    print(f"场景3 - 20个机器人,间隔1秒:")
    print(f"  结果: {'通过' if is_ok else '超限'}")
    print(f"  10秒: {total_10s:.1f}次, 24小时: {total_24h:.0f}次")
    if msg:
        print(f"  消息: {msg}")
    print()


def test_adjust_intervals():
    """测试间隔调整"""
    print("=" * 60)
    print("测试3: 间隔自动调整")
    print("=" * 60)
    
    # 场景: 5个机器人,间隔1秒,会超过10秒限制
    configs = [
        {'symbol': f'BTC{i}USDT', 'interval': 1, 'username': f'user{i}'} 
        for i in range(1, 6)
    ]
    
    print("调整前:")
    for cfg in configs:
        print(f"  {cfg['symbol']}: {cfg['interval']}秒")
    
    is_ok, msg, total_10s, total_24h = RateLimitManager.check_rate_limit(configs)
    print(f"  10秒: {total_10s:.1f}次, 24小时: {total_24h:.0f}次")
    print(f"  状态: {'通过' if is_ok else '超限'}")
    print()
    
    # 调整间隔
    adjusted = RateLimitManager.adjust_intervals(configs)
    
    print("调整后:")
    for cfg in adjusted:
        print(f"  {cfg['symbol']}: {cfg['interval']}秒 (原始: {cfg.get('_original_interval', 'N/A')}秒)")
    
    is_ok, msg, total_10s, total_24h = RateLimitManager.check_rate_limit(adjusted)
    print(f"  10秒: {total_10s:.1f}次, 24小时: {total_24h:.0f}次")
    print(f"  状态: {'通过' if is_ok else '超限'}")
    print()


def test_check_and_adjust():
    """测试便捷函数"""
    print("=" * 60)
    print("测试4: check_and_adjust_rate_limit 便捷函数")
    print("=" * 60)
    
    # 模拟已有机器人
    user_bots = {
        'user1': {
            'bots': {
                'BTCUSDT': {
                    'running': True,
                    'exchange': type('Exchange', (), {'api_key': 'test_key_123'}),
                    'config': {'interval': 1}
                },
                'ETHUSDT': {
                    'running': True,
                    'exchange': type('Exchange', (), {'api_key': 'test_key_123'}),
                    'config': {'interval': 1}
                }
            }
        },
        'user2': {
            'bots': {
                'BNBUSDT': {
                    'running': True,
                    'exchange': type('Exchange', (), {'api_key': 'test_key_123'}),
                    'config': {'interval': 1}
                }
            }
        }
    }
    
    # 尝试添加新机器人
    new_config = {
        'symbol': 'ADAUSDT',
        'interval': 1
    }
    
    print("已有机器人:")
    print("  user1: BTCUSDT(1秒), ETHUSDT(1秒)")
    print("  user2: BNBUSDT(1秒)")
    print(f"新机器人: ADAUSDT(1秒)")
    print()
    
    can_start, msg, adjusted_config = check_and_adjust_rate_limit(
        user_bots, new_config, 'test_key_123'
    )
    
    print(f"结果: {'允许启动' if can_start else '拒绝启动'}")
    print(f"新机器人调整后间隔: {adjusted_config['interval']}秒")
    if msg:
        print(f"\n消息:\n{msg}")
    print()


if __name__ == '__main__':
    test_calculate_order_rate()
    test_check_rate_limit()
    test_adjust_intervals()
    test_check_and_adjust()
    
    print("=" * 60)
    print("[OK] 所有测试完成")
    print("=" * 60)
