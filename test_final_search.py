"""测试最终的搜索逻辑"""
import requests
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("Testing final search logic with limit=1000...\n")

all_markets = []

try:
    gamma_response = requests.get('https://gamma-api.polymarket.com/events', 
                                 params={'limit': 1000}, 
                                 timeout=30)
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

print(f"Total markets: {len(all_markets)}\n")

# 搜索 "Bitcoin Up or Down"
test_keywords = [
    "bitcoin up or down",
    "bitcoin up",
    "btc up",
    "up or down",
]

print("="*80)
print("Search results:\n")

for keyword in test_keywords:
    keyword_lower = keyword.lower()
    results = []
    
    for market in all_markets:
        question = market.get('question', '').lower()
        description = market.get('description', '').lower()
        
        if keyword_lower in question or keyword_lower in description:
            results.append(market)
    
    print(f"Keyword: '{keyword}'")
    print(f"  Found: {len(results)} markets")
    
    if results:
        for i, market in enumerate(results[:3], 1):
            print(f"    {i}. {market.get('question')[:80]}")
            print(f"       Closed: {market.get('closed')}, Active: {market.get('active')}")
    print()

# 统计
print("="*80)
print("Statistics:\n")

bitcoin_markets = [m for m in all_markets if 'bitcoin' in m.get('question', '').lower() or 'btc' in m.get('question', '').lower()]
print(f"Total Bitcoin/BTC markets: {len(bitcoin_markets)}")

open_markets = [m for m in bitcoin_markets if not m.get('closed', False)]
print(f"Open Bitcoin/BTC markets: {len(open_markets)}")

if open_markets:
    print("\nFirst 10 open Bitcoin markets:")
    for i, m in enumerate(open_markets[:10], 1):
        print(f"{i}. {m.get('question')[:80]}")
