"""检查 Bitcoin Up or Down 市场的详细信息"""
import requests
import sys

sys.stdout.reconfigure(encoding='utf-8')

slug = "btc-updown-15m-1767093300"

print(f"Fetching market details for: {slug}\n")

# 通过 slug 获取市场
response = requests.get(f"https://gamma-api.polymarket.com/events?slug={slug}", timeout=10)

if response.status_code == 200:
    data = response.json()
    if len(data) > 0:
        event = data[0]
        
        print("Event Details:")
        print(f"  Title: {event.get('title')}")
        print(f"  Slug: {event.get('slug')}")
        print(f"  Active: {event.get('active')}")
        print(f"  Closed: {event.get('closed')}")
        print(f"  Archived: {event.get('archived')}")
        print(f"  Featured: {event.get('featured')}")
        print(f"  Category: {event.get('category')}")
        print(f"  Created: {event.get('creationDate')}")
        print(f"  End Date: {event.get('endDate')}")
        
        markets = event.get('markets', [])
        print(f"\n  Markets: {len(markets)}")
        
        for market in markets:
            print(f"\n  Market:")
            print(f"    Question: {market.get('question')}")
            print(f"    Condition ID: {market.get('conditionId')}")
            
            tokens = market.get('tokens', [])
            print(f"    Tokens: {len(tokens)}")
            for token in tokens:
                print(f"      - {token.get('outcome')}: {token.get('token_id')}")

# 检查为什么这个市场不在列表中
print("\n" + "="*80)
print("Checking why this market is not in the main list...\n")

# 获取所有事件并检查过滤条件
all_response = requests.get('https://gamma-api.polymarket.com/events', 
                           params={'limit': 1000}, 
                           timeout=30)

if all_response.status_code == 200:
    all_events = all_response.json()
    print(f"Total events in list: {len(all_events)}")
    
    # 查找这个 slug
    found = False
    for event in all_events:
        if event.get('slug') == slug:
            found = True
            print(f"\nFound in list!")
            print(f"  Position: {all_events.index(event) + 1}")
            break
    
    if not found:
        print(f"\nNOT found in the list of {len(all_events)} events")
        print("Possible reasons:")
        print("  - Market is too new or too old")
        print("  - Market is filtered by some criteria")
        print("  - Market is in a different category")

# 测试不同的过滤参数
print("\n" + "="*80)
print("Testing different filter parameters...\n")

test_params = [
    {"limit": 1000, "closed": "true"},
    {"limit": 1000, "active": "true"},
    {"limit": 1000, "archived": "false"},
]

for params in test_params:
    response = requests.get('https://gamma-api.polymarket.com/events', 
                          params=params, 
                          timeout=10)
    if response.status_code == 200:
        events = response.json()
        found = any(e.get('slug') == slug for e in events)
        print(f"Params: {params}")
        print(f"  Total: {len(events)}, Found: {found}")
