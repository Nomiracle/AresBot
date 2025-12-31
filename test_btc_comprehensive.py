"""全面测试 BTC 相关市场搜索"""
from py_clob_client.client import ClobClient
import sys

sys.stdout.reconfigure(encoding='utf-8')

client = ClobClient("https://clob.polymarket.com")
response = client.get_markets()

if isinstance(response, dict):
    markets = response.get('data', response.get('markets', []))
elif isinstance(response, list):
    markets = response
else:
    markets = []

print(f"Total markets: {len(markets)}")

# 扩展搜索关键词 - 更全面的 BTC/Bitcoin 相关词
btc_keywords = [
    'btc', 'bitcoin', 'satoshi', 'sats',
    'crypto', 'cryptocurrency', 'digital currency',
    'blockchain', 'halving', 'mining'
]

print("\n" + "="*80)
print("Comprehensive BTC/Bitcoin market search...")

btc_markets = []
seen_condition_ids = set()

for market in markets:
    question = market.get('question', '').lower()
    description = market.get('description', '').lower()
    condition_id = market.get('condition_id', '')
    
    # 避免重复
    if condition_id in seen_condition_ids:
        continue
    
    # 检查是否包含任何 BTC 相关关键词
    for keyword in btc_keywords:
        if keyword in question or keyword in description:
            btc_markets.append(market)
            seen_condition_ids.add(condition_id)
            break

print(f"\nTotal BTC-related markets found: {len(btc_markets)}")

# 统计状态
open_markets = [m for m in btc_markets if not m.get('closed', False)]
closed_markets = [m for m in btc_markets if m.get('closed', False)]

print(f"Open markets: {len(open_markets)}")
print(f"Closed markets: {len(closed_markets)}")

# 显示所有市场
print("\n" + "="*80)
print("ALL BTC-related markets:")
for i, market in enumerate(btc_markets, 1):
    status = "CLOSED" if market.get('closed') else "OPEN"
    print(f"\n{i}. [{status}] {market.get('question')}")
    print(f"   Condition ID: {market.get('condition_id')}")
    
    # 显示匹配的关键词
    question = market.get('question', '').lower()
    description = market.get('description', '').lower()
    matched_keywords = [kw for kw in btc_keywords if kw in question or kw in description]
    print(f"   Matched keywords: {', '.join(matched_keywords)}")

# 尝试只搜索 'btc' 或 'bitcoin'
print("\n" + "="*80)
print("Markets with ONLY 'btc' or 'bitcoin' in question or description:")
strict_btc_markets = []
for market in markets:
    question = market.get('question', '').lower()
    description = market.get('description', '').lower()
    
    if 'btc' in question or 'btc' in description or 'bitcoin' in question or 'bitcoin' in description:
        strict_btc_markets.append(market)

print(f"Found {len(strict_btc_markets)} markets")
