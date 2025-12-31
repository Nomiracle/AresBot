"""测试搜索 Bitcoin Up or Down 市场"""
from py_clob_client.client import ClobClient
import sys

sys.stdout.reconfigure(encoding='utf-8')

client = ClobClient("https://clob.polymarket.com")

print("Searching for 'Bitcoin Up or Down' markets...\n")

# 获取多页市场数据
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
    else:
        break

print(f"\nTotal markets fetched: {len(all_markets)}")

# 测试不同的搜索关键词
test_keywords = [
    'bitcoin up or down',
    'btc up or down',
    'up or down',
    'updown',
    'up down',
    'bitcoin up',
    'btc up',
]

print("\n" + "="*80)
print("Testing different search keywords...\n")

for keyword in test_keywords:
    keyword_lower = keyword.lower()
    found = []
    
    for market in all_markets:
        question = market.get('question', '').lower()
        description = market.get('description', '').lower()
        
        if keyword_lower in question or keyword_lower in description:
            found.append(market)
    
    print(f"Keyword: '{keyword}'")
    print(f"  Found: {len(found)} markets")
    
    if found:
        print(f"  Examples:")
        for i, m in enumerate(found[:3], 1):
            print(f"    {i}. {m.get('question')}")
            print(f"       Closed: {m.get('closed')}")
    print()

# 搜索包含 "15m" 的市场(短期市场)
print("="*80)
print("Searching for short-term markets (15m, 30m, 1h)...\n")

time_keywords = ['15m', '30m', '1h', '1hr', 'hour']

for keyword in time_keywords:
    found = []
    for market in all_markets:
        question = market.get('question', '').lower()
        if keyword in question:
            found.append(market)
    
    print(f"Keyword: '{keyword}' - Found: {len(found)} markets")
    if found:
        for i, m in enumerate(found[:2], 1):
            print(f"  {i}. {m.get('question')[:80]}")
