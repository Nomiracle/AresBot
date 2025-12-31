"""测试 BTC Up/Down 15分钟市场交易所适配器"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from exchanges.btc_updown_15m import BtcUpDown15m
from datetime import datetime

print("="*80)
print("测试 BTC Up/Down 15分钟市场交易所适配器")
print("="*80)

# 测试参数 (使用测试钱包)
test_wallet = "0x0000000000000000000000000000000000000000"
test_private_key = "0x0000000000000000000000000000000000000000000000000000000000000000"

print("\n1. 测试初始化 (Up 方向)")
print("-"*80)

try:
    # 初始化交易所 - Up 方向
    exchange_up = BtcUpDown15m(
        api_key=test_wallet,
        api_secret=test_private_key,
        outcome="Up",
        testnet=False
    )
    
    print(f"\n✅ 初始化成功!")
    
    # 获取市场信息
    market_info = exchange_up.get_market_info()
    print(f"\n市场信息:")
    print(f"  Slug: {market_info['slug']}")
    print(f"  Token ID: {market_info['token_id']}")
    print(f"  方向: {market_info['outcome']}")
    print(f"  时间戳: {market_info['timestamp']}")
    print(f"  结束时间: {market_info['end_time']}")
    
except Exception as e:
    print(f"\n❌ 初始化失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*80)
print("2. 测试初始化 (Down 方向)")
print("-"*80)

try:
    # 初始化交易所 - Down 方向
    exchange_down = BtcUpDown15m(
        api_key=test_wallet,
        api_secret=test_private_key,
        outcome="Down",
        testnet=False
    )
    
    print(f"\n✅ 初始化成功!")
    
    # 获取市场信息
    market_info = exchange_down.get_market_info()
    print(f"\n市场信息:")
    print(f"  Slug: {market_info['slug']}")
    print(f"  Token ID: {market_info['token_id']}")
    print(f"  方向: {market_info['outcome']}")
    print(f"  时间戳: {market_info['timestamp']}")
    print(f"  结束时间: {market_info['end_time']}")
    
except Exception as e:
    print(f"\n❌ 初始化失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*80)
print("3. 测试市场刷新功能")
print("-"*80)

try:
    if 'exchange_up' in locals():
        print("\n刷新到最新市场...")
        success = exchange_up.refresh_market()
        
        if success:
            print("\n✅ 刷新成功!")
            market_info = exchange_up.get_market_info()
            print(f"  新市场: {market_info['slug']}")
            print(f"  新 Token ID: {market_info['token_id']}")
        else:
            print("\n❌ 刷新失败")
            
except Exception as e:
    print(f"\n❌ 刷新失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*80)
print("测试完成")
print("="*80)
