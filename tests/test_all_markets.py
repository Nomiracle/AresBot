"""获取所有 Polymarket 市场(包括分页)"""
from py_clob_client.client import ClobClient
import sys

sys.stdout.reconfigure(encoding='utf-8')

client = ClobClient("https://clob.polymarket.com")

print("Fetching ALL markets with pagination...")

all_markets = []
next_cursor = 'MA=='  # 初始 cursor
page = 1

while next_cursor:
    print(f"\nFetching page {page}...")
    response = client.get_markets(next_cursor=next_cursor)
    
    if isinstance(response, dict):
        markets = response.get('data', [])
        all_markets.extend(markets)
        next_cursor = response.get('next_cursor')
        
        print(f"  Got {len(markets)} markets")
        print(f"  Total so far: {len(all_markets)}")
        print(f"  Next cursor: {next_cursor}")
        
        page += 1
        
        # 安全限制:最多获取 10 页
        if page > 10:
            print("\n  Reached page limit (10 pages)")
            break
    else:
        break

print(f"\n{'='*80}")
print(f"Total markets fetched: {len(all_markets)}")

# 搜索 BTC 市场
btc_markets = []
for market in all_markets:
    question = market.get('question', '').lower()
    description = market.get('description', '').lower()
    
    if 'btc' in question or 'btc' in description or 'bitcoin' in question or 'bitcoin' in description:
        btc_markets.append(market)

print(f"\nBTC/Bitcoin markets found: {len(btc_markets)}")

# 统计状态
open_markets = [m for m in btc_markets if not m.get('closed', False)]
closed_markets = [m for m in btc_markets if m.get('closed', False)]

print(f"Open BTC markets: {len(open_markets)}")
print(f"Closed BTC markets: {len(closed_markets)}")

# 显示所有开放的 BTC 市场
if open_markets:
    print(f"\n{'='*80}")
    print("OPEN BTC Markets:")
    for i, market in enumerate(open_markets, 1):
        print(f"\n{i}. {market.get('question')}")
        tokens = market.get('tokens', [])
        for token in tokens:
            print(f"   - {token.get('outcome')}: {token.get('token_id')}")
