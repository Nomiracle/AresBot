"""测试 Polymarket 价格获取"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from py_clob_client.client import ClobClient

print("="*80)
print("测试 Polymarket 价格获取")
print("="*80)

# 测试 token ID
token_id = "34385852015642320554443385145417930410379060533178979952680844476301145994973"

try:
    client = ClobClient("https://clob.polymarket.com")
    
    print(f"\n测试 Token ID: {token_id}")
    print("-"*80)
    
    # 测试 get_midpoint
    print("\n1. 测试 get_midpoint():")
    midpoint = client.get_midpoint(token_id)
    print(f"   返回类型: {type(midpoint)}")
    print(f"   返回值: {midpoint}")
    
    # 测试 get_price
    print("\n2. 测试 get_price(BUY):")
    buy_price = client.get_price(token_id, side="BUY")
    print(f"   返回类型: {type(buy_price)}")
    print(f"   返回值: {buy_price}")
    
    print("\n3. 测试 get_price(SELL):")
    sell_price = client.get_price(token_id, side="SELL")
    print(f"   返回类型: {type(sell_price)}")
    print(f"   返回值: {sell_price}")
    
except Exception as e:
    print(f"\n❌ 错误: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*80)
print("测试完成")
print("="*80)
