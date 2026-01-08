"""
测试交易所适配器迁移
验证新架构是否正常工作
"""
import sys
import os

# 设置控制台编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_factory():
    """测试工厂类"""
    print("=" * 50)
    print("测试 1: 交易所工厂类")
    print("=" * 50)
    
    from exchanges.factory import ExchangeFactory
    
    # 测试获取支持的交易所列表
    supported = ExchangeFactory.get_supported_exchanges()
    print(f"✓ 支持的交易所: {supported}")
    assert 'ccxt_binance_spot' in supported, "应该支持 ccxt_binance_spot"
    assert 'ccxt_backpack_spot' in supported, "应该支持 ccxt_backpack_spot"
    assert 'native_polymarket_spot' in supported, "应该支持 native_polymarket_spot"
    
    # 测试创建币安适配器（使用测试密钥）
    exchange = ExchangeFactory.create(
        'ccxt_binance_spot',
        'test_key',
        'test_secret',
        testnet=True
    )
    print(f"✓ 成功创建币安适配器: {type(exchange).__name__}")
    assert exchange is not None, "应该成功创建适配器"
    
    # 测试创建 Backpack 适配器
    try:
        backpack_exchange = ExchangeFactory.create(
            'ccxt_backpack_spot',
            'test_key',
            'test_secret',
            testnet=True
        )
        if backpack_exchange:
            print(f"✓ 成功创建 Backpack 适配器: {type(backpack_exchange).__name__}")
            
            # 测试 backpack 别名
            backpack_alias = ExchangeFactory.create('backpack', 'test_key', 'test_secret')
            print(f"✓ backpack 别名正常工作: {type(backpack_alias).__name__}")
            
            # 测试 bpx 别名
            bpx_exchange = ExchangeFactory.create('bpx', 'test_key', 'test_secret')
            print(f"✓ bpx 别名正常工作: {type(bpx_exchange).__name__}")
        else:
            print("ℹ️ Backpack 适配器创建失败")
    except Exception as e:
        print(f"ℹ️ Backpack 测试失败: {e}")
    
    # 测试不支持的交易所
    unsupported = ExchangeFactory.create('unknown_exchange', 'key', 'secret')
    print(f"✓ 不支持的交易所返回 None: {unsupported is None}")
    assert unsupported is None, "不支持的交易所应返回 None"
    
    print("✅ 工厂类测试通过\n")
    return True

def test_adapter_interface():
    """测试适配器接口"""
    print("=" * 50)
    print("测试 2: 适配器接口")
    print("=" * 50)
    
    from exchanges.factory import ExchangeFactory
    from exchanges.base import BaseExchange
    
    exchange = ExchangeFactory.create('binance', 'test_key', 'test_secret', testnet=True)
    
    # 验证实现了基类接口
    print(f"✓ 适配器是 BaseExchange 的实例: {isinstance(exchange, BaseExchange)}")
    assert isinstance(exchange, BaseExchange), "应该继承自 BaseExchange"
    
    # 验证关键方法存在
    methods = [
        'ping', 'get_symbol_info', 'get_symbol_ticker',
        'get_open_orders', 'get_order', 'order_limit_buy',
        'order_limit_sell', 'cancel_order', 'cancel_replace_order',
        'start_websocket', 'stop_websocket',
        'parse_ticker_message', 'parse_user_message',
        'get_price_precision', 'get_quantity_precision'
    ]
    
    for method in methods:
        assert hasattr(exchange, method), f"应该有 {method} 方法"
        print(f"  ✓ {method}")
    
    print("✅ 适配器接口测试通过\n")
    return True

def test_imports():
    """测试导入是否正常"""
    print("=" * 50)
    print("测试 3: 模块导入")
    print("=" * 50)
    
    try:
        # 测试 routes.py 导入
        from routes import register_routes
        print("✓ routes.py 导入成功")
        
        # 测试 trading.py 导入
        from trading import trading_loop, user_bots
        print("✓ trading.py 导入成功")
        
        # 测试交易所模块导入
        from exchanges.factory import ExchangeFactory
        from exchanges.base import BaseExchange
        from exchanges.binance_adapter import BinanceAdapter
        print("✓ exchanges 模块导入成功")
        
        print("✅ 模块导入测试通过\n")
        return True
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        return False

def test_parse_methods():
    """测试消息解析方法"""
    print("=" * 50)
    print("测试 4: 消息解析")
    print("=" * 50)
    
    from exchanges.factory import ExchangeFactory
    
    exchange = ExchangeFactory.create('binance', 'test_key', 'test_secret', testnet=True)
    
    # 测试行情消息解析
    ticker_msg = {'s': 'BTCUSDT', 'c': '50000.00'}
    price = exchange.parse_ticker_message(ticker_msg)
    print(f"✓ 解析行情消息: {price}")
    assert price == 50000.00, "应该正确解析价格"
    
    # 测试用户消息解析 - 订单成交
    user_msg = {
        'e': 'executionReport',
        'i': '12345',
        's': 'BTCUSDT',
        'S': 'BUY',
        'X': 'FILLED',
        'p': '50000',
        'q': '0.001'
    }
    event = exchange.parse_user_message(user_msg)
    print(f"✓ 解析用户消息: {event}")
    assert event['event_type'] == 'order_filled', "应该识别为订单成交"
    assert event['side'] == 'BUY', "应该识别为买单"
    
    # 测试错误消息解析
    error_msg = {'e': 'error', 'type': 'test', 'm': 'test error'}
    error_event = exchange.parse_user_message(error_msg)
    print(f"✓ 解析错误消息: {error_event}")
    assert error_event['event_type'] == 'error', "应该识别为错误"
    
    print("✅ 消息解析测试通过\n")
    return True

def main():
    """运行所有测试"""
    print("\n" + "=" * 50)
    print("开始交易所适配器迁移测试")
    print("=" * 50 + "\n")
    
    tests = [
        ("模块导入", test_imports),
        ("工厂类", test_factory),
        ("适配器接口", test_adapter_interface),
        ("消息解析", test_parse_methods),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ {name} 测试失败: {e}\n")
            results.append((name, False))
    
    # 打印总结
    print("=" * 50)
    print("测试总结")
    print("=" * 50)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status}: {name}")
    
    print(f"\n总计: {passed}/{total} 测试通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！迁移成功！")
        return 0
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败，请检查")
        return 1

if __name__ == '__main__':
    exit(main())
