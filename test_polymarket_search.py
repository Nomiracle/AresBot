"""测试 Polymarket 搜索功能"""
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

# 统计市场状态
active_count = sum(1 for m in markets if m.get('active', False) and not m.get('closed', False))
closed_count = sum(1 for m in markets if m.get('closed', False))
print(f"Active markets: {active_count}")
print(f"Closed markets: {closed_count}")

# 搜索 Bitcoin
print("\n" + "="*80)
print("Searching for 'bitcoin'...")
keyword = "bitcoin"
bitcoin_markets = []

for market in markets:
    if market.get('closed', False):
        continue
    
    question = market.get('question', '').lower()
    description = market.get('description', '').lower()
    
    if keyword in question or keyword in description:
        bitcoin_markets.append(market)

print(f"Found {len(bitcoin_markets)} markets containing 'bitcoin'")

if bitcoin_markets:
    print("\nTop 5 markets:")
    for i, market in enumerate(bitcoin_markets[:5], 1):
        print(f"{i}. {market.get('question')}")
        print(f"   Active: {market.get('active')}, Closed: {market.get('closed')}")
else:
    print("\nNo bitcoin markets found. Trying other keywords...")
    
    # 尝试其他关键词
    test_keywords = ['trump', 'election', 'president', 'crypto', 'btc']
    
    for test_keyword in test_keywords:
        count = 0
        for market in markets:
            if market.get('closed', False):
                continue
            question = market.get('question', '').lower()
            if test_keyword in question:
                count += 1
        print(f"  '{test_keyword}': {count} markets")
    
    # 显示前20个活跃市场
    print("\n" + "="*80)
    print("First 20 active markets:")
    shown = 0
    for market in markets:
        if not market.get('closed', False) and shown < 20:
            print(f"{shown+1}. {market.get('question')}")
            shown += 1
