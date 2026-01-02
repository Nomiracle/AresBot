"""
测试 NativePolymarketSpot.get_open_orders 是否正确过滤交易对

问题：怀疑 get_open_orders 返回了所有交易对的订单，而不是只返回当前 symbol 的订单
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exchanges.polymarket_adapter import NativePolymarketSpot


def test_get_open_orders_filter(api_key: str, api_secret: str, test_symbol: str = None):
    """测试 get_open_orders 是否按 symbol 过滤
    
    Args:
        api_key: Polymarket Proxy Wallet 地址
        api_secret: 私钥
        test_symbol: 测试用的 token_id (可选)
    """
    
    if not api_key or not api_secret:
        print("❌ 请提供 api_key 和 api_secret")
        return
    
    # 使用一个特定的 token_id 作为 symbol
    TEST_SYMBOL = test_symbol or "test_token_id_12345"  # 一个不存在的 token_id
    
    print(f"\n{'='*60}")
    print(f"测试 get_open_orders 过滤功能")
    print(f"{'='*60}")
    print(f"测试 symbol: {TEST_SYMBOL}")
    
    try:
        # 创建适配器实例
        adapter = NativePolymarketSpot(
            api_key=api_key,
            api_secret=api_secret,
            symbol=TEST_SYMBOL,
            testnet=False
        )
        
        print(f"\n📍 适配器 symbol: {adapter.symbol}")
        
        # 获取未完成订单
        print(f"\n🔍 调用 get_open_orders()...")
        open_orders = adapter.get_open_orders()
        
        print(f"\n📊 返回订单数量: {len(open_orders)}")
        
        if not open_orders:
            print("✅ 没有返回订单（可能账户没有订单，或过滤正确）")
            return
        
        # 分析返回的订单
        print(f"\n📋 订单详情:")
        symbols_found = set()
        for i, order in enumerate(open_orders):
            order_symbol = order.get('symbol', 'N/A')
            symbols_found.add(order_symbol)
            print(f"  [{i+1}] order_id={order.get('orderId')[:16]}..., "
                  f"symbol={order_symbol[:32]}..., "
                  f"side={order.get('side')}, "
                  f"price={order.get('price')}")
        
        print(f"\n📊 发现的不同 symbol 数量: {len(symbols_found)}")
        
        # 检查是否有非当前 symbol 的订单
        other_symbols = [s for s in symbols_found if s != TEST_SYMBOL]
        
        if other_symbols:
            print(f"\n⚠️ 发现问题！返回了其他 symbol 的订单:")
            for s in other_symbols:
                count = sum(1 for o in open_orders if o.get('symbol') == s)
                print(f"  - {s[:48]}... ({count} 笔)")
            print(f"\n❌ 结论: get_open_orders 没有按 symbol 过滤！")
        else:
            print(f"\n✅ 所有订单都属于当前 symbol")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


def test_get_open_orders_raw(api_key: str, api_secret: str):
    """直接查看原始返回数据
    
    Args:
        api_key: Polymarket Proxy Wallet 地址
        api_secret: 私钥
    """
    
    if not api_key or not api_secret:
        print("❌ 请提供 api_key 和 api_secret")
        return
    
    print(f"\n{'='*60}")
    print(f"查看原始订单数据")
    print(f"{'='*60}")
    
    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import OpenOrderParams
        
        # 直接使用 ClobClient
        private_key = api_secret
        if private_key.startswith('0x'):
            private_key = private_key[2:]
        
        client = ClobClient(
            host="https://clob.polymarket.com",
            key=private_key,
            chain_id=137,
            signature_type=2,
            funder=api_key
        )
        
        # 设置 API 凭证
        api_creds = client.create_or_derive_api_creds()
        client.set_api_creds(api_creds)
        
        # 获取所有订单
        print(f"\n🔍 调用 client.get_orders(OpenOrderParams())...")
        orders = client.get_orders(OpenOrderParams())
        
        print(f"\n📊 原始返回订单数量: {len(orders)}")
        
        if orders:
            print(f"\n📋 原始订单数据 (前5个):")
            for i, order in enumerate(orders[:5]):
                print(f"\n  [{i+1}] 订单详情:")
                print(f"      id: {order.get('id', 'N/A')}")
                print(f"      asset_id: {order.get('asset_id', 'N/A')}")
                print(f"      status: {order.get('status', 'N/A')}")
                print(f"      side: {order.get('side', 'N/A')}")
                print(f"      price: {order.get('price', 'N/A')}")
                print(f"      original_size: {order.get('original_size', 'N/A')}")
                print(f"      size_matched: {order.get('size_matched', 'N/A')}")
            
            # 统计不同的 asset_id
            asset_ids = set(order.get('asset_id', 'N/A') for order in orders)
            print(f"\n📊 不同 asset_id 数量: {len(asset_ids)}")
            for aid in asset_ids:
                count = sum(1 for o in orders if o.get('asset_id') == aid)
                print(f"  - {aid[:48]}... ({count} 笔)")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='测试 Polymarket get_open_orders')
    parser.add_argument('--api-key', required=True, help='Polymarket Proxy Wallet 地址')
    parser.add_argument('--api-secret', required=True, help='私钥')
    parser.add_argument('--symbol', default=None, help='测试用的 token_id (可选)')
    parser.add_argument('--raw', action='store_true', help='查看原始数据')
    args = parser.parse_args()
    
    if args.raw:
        test_get_open_orders_raw(args.api_key, args.api_secret)
    else:
        test_get_open_orders_filter(args.api_key, args.api_secret, args.symbol)
        print("\n" + "="*60)
        print("提示: 使用 --raw 参数查看原始订单数据")
