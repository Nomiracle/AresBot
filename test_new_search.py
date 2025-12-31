"""测试新的搜索逻辑"""
import requests
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("Testing new search logic with Gamma API + CLOB API...\n")

# 模拟搜索逻辑
all_markets = []

# 1. 从 Gamma API 获取
try:
    gamma_response = requests.get('https://gamma-api.polymarket.com/events', timeout=30)
    if gamma_response.status_code == 200:
        gamma_events = gamma_response.json()
        
        print(f"Gamma API: Got {len(gamma_events)} events")
        
        for event in gamma_events:
            event_markets = event.get('markets', [])
            
            if event_markets:
                for market in event_markets:
                    all_markets.append({
                        'question': market.get('question', event.get('title', 'N/A')),
                        'condition_id': market.get('conditionId', ''),
                        'description': event.get('description', ''),
                        'active': event.get('active', False),
                        'closed': event.get('closed', False),
                        'tokens': market.get('tokens', [])
                    })
            else:
                all_markets.append({
                    'question': event.get('title', 'N/A'),
                    'condition_id': event.get('id', ''),
                    'description': event.get('description', ''),
                    'active': event.get('active', False),
                    'closed': event.get('closed', False),
                    'tokens': []
                })
except Exception as e:
    print(f"Gamma API error: {e}")

print(f"Total markets after Gamma API: {len(all_markets)}\n")

# 搜索 "Bitcoin Up or Down"
keyword = "bitcoin up or down"
keyword_lower = keyword.lower()

results = []
for market in all_markets:
    question = market.get('question', '').lower()
    description = market.get('description', '').lower()
    
    if keyword_lower in question or keyword_lower in description:
        results.append(market)

print(f"Search results for '{keyword}': {len(results)} markets\n")

if results:
    print("Found markets:")
    for i, market in enumerate(results[:10], 1):
        print(f"\n{i}. {market.get('question')}")
        print(f"   Closed: {market.get('closed')}")
        print(f"   Active: {market.get('active')}")
        print(f"   Condition ID: {market.get('condition_id')}")
        
        tokens = market.get('tokens', [])
        if tokens:
            print(f"   Tokens:")
            for token in tokens:
                print(f"     - {token.get('outcome', 'N/A')}: {token.get('token_id', 'N/A')}")
else:
    print("No markets found")

# 测试其他关键词
print("\n" + "="*80)
print("Testing other keywords:\n")

test_keywords = ['bitcoin', 'btc', 'up or down', 'updown']

for kw in test_keywords:
    count = sum(1 for m in all_markets if kw in m.get('question', '').lower())
    print(f"'{kw}': {count} markets")
