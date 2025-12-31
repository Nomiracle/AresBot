"""测试 Gamma API 分页和参数"""
import requests
import sys

sys.stdout.reconfigure(encoding='utf-8')

gamma_url = "https://gamma-api.polymarket.com"

print("Testing Gamma API pagination and parameters...\n")

# 测试不同的参数
test_params = [
    {},
    {"limit": 100},
    {"limit": 1000},
    {"offset": 0, "limit": 100},
    {"active": "true"},
    {"closed": "false"},
]

for params in test_params:
    try:
        response = requests.get(f"{gamma_url}/events", params=params, timeout=10)
        print(f"Params: {params}")
        print(f"  Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"  Count: {len(data)}")
            
            # 检查是否有 Bitcoin Up or Down
            btc_updown = [e for e in data if 'bitcoin' in e.get('title', '').lower() and 'up' in e.get('title', '').lower()]
            if btc_updown:
                print(f"  Found Bitcoin Up/Down markets: {len(btc_updown)}")
                for e in btc_updown[:3]:
                    print(f"    - {e.get('title')}")
        print()
    except Exception as e:
        print(f"Params: {params}")
        print(f"  Error: {e}\n")

# 测试通过 slug 直接搜索
print("="*80)
print("Testing direct slug search...\n")

slug = "btc-updown-15m-1767093300"
try:
    response = requests.get(f"{gamma_url}/events?slug={slug}", timeout=10)
    print(f"Slug search: {slug}")
    print(f"  Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"  Count: {len(data)}")
        if len(data) > 0:
            event = data[0]
            print(f"  Title: {event.get('title')}")
            print(f"  Closed: {event.get('closed')}")
            print(f"  Active: {event.get('active')}")
            
            markets = event.get('markets', [])
            print(f"  Markets: {len(markets)}")
            for market in markets:
                print(f"    - {market.get('question', 'N/A')}")
                tokens = market.get('tokens', [])
                for token in tokens:
                    print(f"      Token: {token.get('outcome')} - {token.get('token_id')}")
except Exception as e:
    print(f"  Error: {e}")

# 测试搜索参数
print("\n" + "="*80)
print("Testing search parameters...\n")

search_params = [
    {"q": "bitcoin"},
    {"search": "bitcoin"},
    {"title": "bitcoin"},
]

for params in search_params:
    try:
        response = requests.get(f"{gamma_url}/events", params=params, timeout=10)
        print(f"Params: {params}")
        print(f"  Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"  Count: {len(data)}")
        print()
    except Exception as e:
        print(f"Params: {params}")
        print(f"  Error: {e}\n")
