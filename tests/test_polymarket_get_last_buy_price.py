"""
测试 Polymarket _get_last_filled_buy_price 方法
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import Mock, MagicMock, patch
from exchanges.polymarket_adapter import NativePolymarketSpot


def test_get_last_filled_buy_price():
    """测试从历史订单获取最近买入价"""
    
    # 模拟订单数据（来自用户提供的真实数据）
    mock_order = {
        'id': '0x2e3ceefaa43fef8cee279b35fc24bafe040aeb438ebb0962c78c46923e6afb5a',
        'owner': '84c15c7d-fb22-db2a-c3c3-55e09af7b4ca',
        'maker_address': '0x5354b9aF3980149e03Dd32c7e0b716382f7B92d8',
        'matched_amount': '2.66',
        'price': '0.35',
        'fee_rate_bps': '1000',
        'asset_id': '111687137513747780904882674372859005833329319415172086974117982617968875263437',
        'outcome': 'Down',
        'outcome_index': 0,
        'side': 'BUY',
        'status': 'MATCHED',  # 已成交
        'created_at': 1705449600,  # 模拟时间戳
        'timestamp': 1705449600
    }
    
    # 创建 mock 客户端
    mock_client = MagicMock()
    mock_client.get_orders.return_value = [mock_order]
    
    # 直接创建最小化的适配器对象，避免完整初始化
    adapter = Mock(spec=NativePolymarketSpot)
    adapter.client = mock_client
    adapter._last_buy_price = 0.0
    adapter.symbol = '111687137513747780904882674372859005833329319415172086974117982617968875263437'
    
    # 直接调用真实方法
    buy_price = NativePolymarketSpot._get_last_filled_buy_price(adapter, adapter.symbol)
    
    print("OK: 测试成功!")
    print(f"获取到的买入价: {buy_price}")
    print(f"预期买入价: 0.35")
    
    assert buy_price == 0.35, f"买入价不匹配: 期望 0.35, 实际 {buy_price}"
    print("OK: 断言通过: 买入价正确")


def test_get_last_filled_buy_price_no_orders():
    """测试没有历史订单时的 fallback"""
    
    # 创建 mock 客户端（返回空订单列表）
    mock_client = MagicMock()
    mock_client.get_orders.return_value = []
    
    adapter = Mock(spec=NativePolymarketSpot)
    adapter.client = mock_client
    adapter._last_buy_price = 0.42  # 设置 fallback 价格
    adapter.symbol = 'test_asset_id'
    
    # 测试获取买入价
    buy_price = NativePolymarketSpot._get_last_filled_buy_price(adapter, 'test_asset_id')
    
    print("\nOK: 测试成功 (无历史订单)!")
    print(f"获取到的买入价: {buy_price}")
    print(f"预期买入价 (fallback): 0.42")
    
    assert buy_price == 0.42, f"买入价不匹配: 期望 0.42, 实际 {buy_price}"
    print("OK: 断言通过: fallback 机制正常")


def test_get_last_filled_buy_price_multiple_orders():
    """测试多个历史订单时取最近一笔"""
    
    # 模拟多个订单（不同时间）
    mock_orders = [
        {
            'id': 'order_1',
            'price': '0.30',
            'side': 'BUY',
            'status': 'MATCHED',
            'created_at': 1705449600,  # 较早
            'timestamp': 1705449600
        },
        {
            'id': 'order_2',
            'price': '0.35',
            'side': 'BUY',
            'status': 'MATCHED',
            'created_at': 1705453200,  # 最近
            'timestamp': 1705453200
        },
        {
            'id': 'order_3',
            'price': '0.32',
            'side': 'BUY',
            'status': 'MATCHED',
            'created_at': 1705450800,  # 中间
            'timestamp': 1705450800
        }
    ]
    
    mock_client = MagicMock()
    mock_client.get_orders.return_value = mock_orders
    
    adapter = Mock(spec=NativePolymarketSpot)
    adapter.client = mock_client
    adapter._last_buy_price = 0.0
    adapter.symbol = 'test_asset_id'
    
    # 测试获取买入价
    buy_price = NativePolymarketSpot._get_last_filled_buy_price(adapter, 'test_asset_id')
    
    print("\nOK: 测试成功 (多个订单)!")
    print(f"获取到的买入价: {buy_price}")
    print(f"预期买入价 (最近一笔): 0.35")
    
    assert buy_price == 0.35, f"买入价不匹配: 期望 0.35, 实际 {buy_price}"
    print("OK: 断言通过: 正确取最近一笔订单")


def test_get_last_filled_buy_price_filter_sell_orders():
    """测试过滤卖单，只取买单"""
    
    # 模拟混合订单（买单+卖单）
    mock_orders = [
        {
            'id': 'order_sell',
            'price': '0.50',
            'side': 'SELL',  # 卖单，应被过滤
            'status': 'MATCHED',
            'created_at': 1705453200,
            'timestamp': 1705453200
        },
        {
            'id': 'order_buy',
            'price': '0.35',
            'side': 'BUY',  # 买单
            'status': 'MATCHED',
            'created_at': 1705449600,
            'timestamp': 1705449600
        }
    ]
    
    mock_client = MagicMock()
    mock_client.get_orders.return_value = mock_orders
    
    adapter = Mock(spec=NativePolymarketSpot)
    adapter.client = mock_client
    adapter._last_buy_price = 0.0
    adapter.symbol = 'test_asset_id'
    
    # 测试获取买入价
    buy_price = NativePolymarketSpot._get_last_filled_buy_price(adapter, 'test_asset_id')
    
    print("\nOK: 测试成功 (过滤卖单)!")
    print(f"获取到的买入价: {buy_price}")
    print(f"预期买入价 (只取买单): 0.35")
    
    assert buy_price == 0.35, f"买入价不匹配: 期望 0.35, 实际 {buy_price}"
    print("OK: 断言通过: 正确过滤卖单")


if __name__ == '__main__':
    print("=" * 60)
    print("Test: _get_last_filled_buy_price method")
    print("=" * 60)
    
    try:
        test_get_last_filled_buy_price()
        test_get_last_filled_buy_price_no_orders()
        test_get_last_filled_buy_price_multiple_orders()
        test_get_last_filled_buy_price_filter_sell_orders()
        
        print("\n" + "=" * 60)
        print("OK: All tests passed!")
        print("=" * 60)
    except AssertionError as e:
        print(f"\nFAIL: Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: Test exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
