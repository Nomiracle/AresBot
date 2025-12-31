"""验证 BTC Up/Down 15m token 获取功能"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from exchanges.btc_updown_15m import BtcUpDown15m

print("="*80)
print("验证 BTC Up/Down 15m Token 获取功能")
print("="*80)

# 只测试 token 获取,不初始化完整的交易所
test_instance = BtcUpDown15m.__new__(BtcUpDown15m)
test_instance.outcome = "Up"

print("\n测试 Up 方向:")
print("-"*80)
token_up = test_instance._get_latest_market_token()
if token_up:
    print(f"✅ 成功获取 Up token: {token_up}")
    print(f"✅ 市场 slug: {test_instance.market_slug}")
else:
    print("❌ 获取失败")

print("\n测试 Down 方向:")
print("-"*80)
test_instance.outcome = "Down"
token_down = test_instance._get_latest_market_token()
if token_down:
    print(f"✅ 成功获取 Down token: {token_down}")
    print(f"✅ 市场 slug: {test_instance.market_slug}")
else:
    print("❌ 获取失败")

print("\n" + "="*80)
print("验证完成")
print("="*80)
