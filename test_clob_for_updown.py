"""在 CLOB API 中搜索 Bitcoin Up or Down"""
from py_clob_client.client import ClobClient
import sys

sys.stdout.reconfigure(encoding='utf-8')

client = ClobClient("https://clob.polymarket.com")

# 目标 condition_id
target_condition_id = "0xd410ccaf50fe606f04e69c6c6da1b1e2c825f988e6932417992cd954e0077c62"

print(f"Searching for condition_id: {target_condition_id}\n")

# 搜索前几页
all_markets = []
next_cursor = 'MA=='
max_pages = 10

for page in range(max_pages):
    print(f"Fetching page {page + 1}...")
    response = client.get_markets(next_cursor=next_cursor)
    
    if isinstance(response, dict):
        markets = response.get('data', [])
        all_markets.extend(markets)
        next_cursor = response.get('next_cursor')
        
        if not next_cursor:
            break

print(f"\nTotal markets: {len(all_markets)}")

# 搜索 condition_id
found = False
for market in all_markets:
    if market.get('condition_id') == target_condition_id:
        found = True
        print(f"\nFound market!")
        print(f"  Question: {market.get('question')}")
        print(f"  Closed: {market.get('closed')}")
        print(f"  Active: {market.get('active')}")
        print(f"  Tokens: {len(market.get('tokens', []))}")
        break

if not found:
    print(f"\nNOT found in {len(all_markets)} markets")
    
    # 搜索包含 "up" 和 "down" 的市场
    print("\nSearching for markets with 'up' and 'down'...")
    
    updown_markets = []
    for market in all_markets:
        question = market.get('question', '').lower()
        if 'up' in question and 'down' in question:
            updown_markets.append(market)
    
    print(f"Found {len(updown_markets)} markets with 'up' and 'down'")
    
    for i, m in enumerate(updown_markets[:10], 1):
        print(f"{i}. {m.get('question')}")
