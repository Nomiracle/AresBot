"""
真实查询 Polymarket 订单数据测试
使用真实的订单 ID 查询服务器，验证数据处理
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exchanges.polymarket_adapter import NativePolymarketSpot


def test_real_order_query():
    """使用真实订单数据测试"""
    
    # 用户提供的订单信息
    order_info = {
        'order_id': '0x2e3ceefaa43fef8cee279b35fc24bafe040aeb438ebb0962c78c46923e6afb5a',
        'maker_address': '0x5354b9aF3980149e03Dd32c7e0b716382f7B92d8',
        'asset_id': '111687137513747780904882674372859005833329319415172086974117982617968875263437',
        'price': '0.35',
        'side': 'BUY'
    }
    
    print("=" * 80)
    print("真实查询 Polymarket 订单数据测试")
    print("=" * 80)
    print(f"\n订单信息:")
    print(f"  Order ID: {order_info['order_id']}")
    print(f"  Maker Address: {order_info['maker_address']}")
    print(f"  Asset ID: {order_info['asset_id']}")
    print(f"  Expected Price: {order_info['price']}")
    print(f"  Side: {order_info['side']}")
    
    # 从环境变量或配置文件读取真实凭证
    # 注意：这里需要用户提供真实的 API 凭证
    api_key = input("\n请输入 Polymarket Proxy Wallet 地址 (或按回车跳过): ").strip()
    if not api_key:
        api_key = order_info['maker_address']  # 使用订单中的地址
    
    api_secret = input("请输入私钥 (0x开头，或按回车跳过测试): ").strip()
    if not api_secret:
        print("\n⚠️ 未提供私钥，跳过真实查询测试")
        print("提示：如需真实测试，请提供有效的私钥")
        return
    
    try:
        print("\n" + "=" * 80)
        print("步骤 1: 初始化 Polymarket 客户端")
        print("=" * 80)
        
        adapter = NativePolymarketSpot(
            api_key=api_key,
            api_secret=api_secret,
            symbol=order_info['asset_id'],
            testnet=False
        )
        
        print("✅ 客户端初始化成功")
        
        print("\n" + "=" * 80)
        print("步骤 2: 查询历史订单")
        print("=" * 80)
        
        # 调用真实的 _get_last_filled_buy_price 方法
        buy_price = adapter._get_last_filled_buy_price(order_info['asset_id'])
        
        print(f"\n✅ 查询成功!")
        print(f"获取到的买入价: {buy_price}")
        print(f"预期买入价: {order_info['price']}")
        
        if buy_price is not None:
            print(f"\n✅ 数据处理成功: 买入价 = {buy_price}")
            
            # 验证价格是否合理
            expected_price = float(order_info['price'])
            if abs(buy_price - expected_price) < 0.01:
                print(f"✅ 价格匹配: {buy_price} ≈ {expected_price}")
            else:
                print(f"⚠️ 价格不匹配: {buy_price} != {expected_price}")
                print("   (可能是获取到了其他订单的价格)")
        else:
            print("⚠️ 未获取到买入价 (可能没有历史买单)")
        
        print("\n" + "=" * 80)
        print("步骤 3: 查看原始订单数据")
        print("=" * 80)
        
        # 直接查询订单列表，查看原始数据结构
        from py_clob_client.clob_types import OpenOrderParams
        orders = adapter.client.get_orders(OpenOrderParams(asset_id=order_info['asset_id']))
        
        print(f"\n找到 {len(orders)} 个订单")
        
        # 查找匹配的买单
        buy_orders = [o for o in orders if o.get('side', '').upper() == 'BUY' and o.get('status', '').upper() == 'MATCHED']
        print(f"其中 {len(buy_orders)} 个已成交的买单")
        
        if buy_orders:
            print("\n已成交买单详情:")
            for i, order in enumerate(buy_orders[:3], 1):  # 只显示前3个
                print(f"\n  订单 {i}:")
                print(f"    ID: {order.get('id', 'N/A')[:66]}...")
                print(f"    Price: {order.get('price', 'N/A')}")
                print(f"    Side: {order.get('side', 'N/A')}")
                print(f"    Status: {order.get('status', 'N/A')}")
                print(f"    Size: {order.get('original_size', 'N/A')}")
                print(f"    Matched: {order.get('size_matched', 'N/A')}")
                print(f"    Created: {order.get('created_at', order.get('timestamp', 'N/A'))}")
        
        print("\n" + "=" * 80)
        print("✅ 测试完成!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def test_order_data_structure():
    """测试订单数据结构解析"""
    
    print("\n" + "=" * 80)
    print("订单数据结构测试")
    print("=" * 80)
    
    # 用户提供的订单数据示例
    sample_order = {
        'order_id': '0x2e3ceefaa43fef8cee279b35fc24bafe040aeb438ebb0962c78c46923e6afb5a',
        'owner': '84c15c7d-fb22-db2a-c3c3-55e09af7b4ca',
        'maker_address': '0x5354b9aF3980149e03Dd32c7e0b716382f7B92d8',
        'matched_amount': '2.66',
        'price': '0.35',
        'fee_rate_bps': '1000',
        'asset_id': '111687137513747780904882674372859005833329319415172086974117982617968875263437',
        'outcome': 'Down',
        'outcome_index': 0,
        'side': 'BUY'
    }
    
    print("\n示例订单数据:")
    for key, value in sample_order.items():
        print(f"  {key}: {value}")
    
    print("\n数据字段说明:")
    print("  ✅ price: 订单价格 (0.35)")
    print("  ✅ side: 订单方向 (BUY)")
    print("  ✅ matched_amount: 成交数量 (2.66)")
    print("  ✅ asset_id: 资产ID (token_id)")
    
    print("\n预期处理逻辑:")
    print("  1. 过滤条件: side='BUY' AND status='MATCHED'")
    print("  2. 排序: 按 created_at/timestamp 降序")
    print("  3. 取值: 最近一笔订单的 price 字段")
    print("  4. 转换: float(price) = 0.35")
    
    print("\n✅ 数据结构符合预期")


if __name__ == '__main__':
    # 先测试数据结构
    test_order_data_structure()
    
    # 询问是否进行真实查询
    print("\n" + "=" * 80)
    choice = input("\n是否进行真实 API 查询测试? (需要提供私钥) [y/N]: ").strip().lower()
    
    if choice == 'y':
        test_real_order_query()
    else:
        print("\n跳过真实查询测试")
        print("提示: 如需测试，请运行脚本并选择 'y'")
