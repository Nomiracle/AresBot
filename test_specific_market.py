"""测试特定 Polymarket 市场"""
from py_clob_client.client import ClobClient
import sys

# 设置输出编码
sys.stdout.reconfigure(encoding='utf-8')

client = ClobClient("https://clob.polymarket.com")
response = client.get_markets()

# 解析市场数据
if isinstance(response, dict):
    markets = response.get('data', response.get('markets', []))
elif isinstance(response, list):
    markets = response
else:
    markets = []

print(f"Total markets: {len(markets)}")

# 从 URL 提取的信息
# https://polymarket.com/event/btc-updown-15m-1767093300?tid=1767093959567
# 可能的关键词: btc, updown, 15m

test_keywords = ['btc', 'updown', '15m', '1767093300', 'bitcoin']

print("\n" + "="*80)
print("Searching for the specific market...")

for keyword in test_keywords:
    print(f"\nSearching for '{keyword}':")
    found_count = 0
    
    for market in markets:
        question = market.get('question', '').lower()
        description = market.get('description', '').lower()
        condition_id = str(market.get('condition_id', '')).lower()
        
        if keyword.lower() in question or keyword.lower() in description or keyword.lower() in condition_id:
            print(f"  - {market.get('question')}")
            print(f"    Closed: {market.get('closed')}, Active: {market.get('active')}")
            print(f"    Condition ID: {market.get('condition_id')}")
            found_count += 1
            if found_count >= 5:
                break
    
    if found_count == 0:
        print(f"  No markets found")

# 尝试查找所有包含数字的市场（可能是时间戳相关）
print("\n" + "="*80)
print("Looking for markets with timestamps or numbers...")

timestamp_markets = []
for market in markets:
    question = market.get('question', '')
    if any(char.isdigit() for char in question):
        timestamp_markets.append(market)

print(f"Found {len(timestamp_markets)} markets with numbers")
print("\nFirst 10 markets with numbers:")
for i, market in enumerate(timestamp_markets[:10], 1):
    print(f"{i}. {market.get('question')}")
    print(f"   Closed: {market.get('closed')}, Active: {market.get('active')}")
