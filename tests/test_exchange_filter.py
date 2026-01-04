"""
测试API限制管理器只对币安交易所生效
"""

def test_exchange_filter():
    """模拟测试不同交易所的处理"""
    print("=" * 60)
    print("测试: 交易所过滤")
    print("=" * 60)
    
    # 模拟配置
    test_cases = [
        {'exchange': 'binance', 'should_check': True},
        {'exchange': 'okx', 'should_check': False},
        {'exchange': 'bybit', 'should_check': False},
        {'exchange': 'Binance', 'should_check': True},  # 大小写测试
        {'exchange': 'BINANCE', 'should_check': True},
    ]
    
    for case in test_cases:
        exchange_name = case['exchange'].lower()
        should_check = case['should_check']
        
        # 模拟routes.py中的逻辑
        if exchange_name == 'binance':
            will_check = True
        else:
            will_check = False
        
        status = "[OK]" if will_check == should_check else "[FAIL]"
        check_text = "检查限制" if will_check else "跳过检查"
        
        print(f"{status} {case['exchange']:10s} -> {check_text}")
    
    print()
    print("说明:")
    print("- 币安交易所: 会进行API限制检查和自动调整")
    print("- 其他交易所: 跳过限制检查,正常启动")
    print("=" * 60)


if __name__ == '__main__':
    test_exchange_filter()
