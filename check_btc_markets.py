"""检查所有 BTC 相关市场"""
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

# 搜索所有 BTC 市场（包括已关闭的）
btc_markets = []
for market in markets:
    question = market.get('question', '').lower()
    description = market.get('description', '').lower()
    
    if 'btc' in question or 'btc' in description or 'bitcoin' in question or 'bitcoin' in description:
        btc_markets.append(market)

print(f"\nTotal BTC/Bitcoin markets: {len(btc_markets)}")

# 统计状态
open_markets = [m for m in btc_markets if not m.get('closed', False)]
closed_markets = [m for m in btc_markets if m.get('closed', False)]

print(f"Open BTC markets: {len(open_markets)}")
print(f"Closed BTC markets: {len(closed_markets)}")

if open_markets:
    print("\n" + "="*80)
    print("OPEN BTC Markets:")
    for i, market in enumerate(open_markets, 1):
        print(f"\n{i}. {market.get('question')}")
        print(f"   Active: {market.get('active')}, Closed: {market.get('closed')}")
        tokens = market.get('tokens', [])
        for token in tokens:
            print(f"   - {token.get('outcome')}: {token.get('token_id')}")

if closed_markets:
    print("\n" + "="*80)
    print(f"CLOSED BTC Markets (showing first 10 of {len(closed_markets)}):")
    for i, market in enumerate(closed_markets[:10], 1):
        print(f"\n{i}. {market.get('question')}")
        print(f"   Active: {market.get('active')}, Closed: {market.get('closed')}")
