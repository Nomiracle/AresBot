"""测试 Polymarket Gamma API 的搜索功能"""
import requests
import sys

sys.stdout.reconfigure(encoding='utf-8')

gamma_url = "https://gamma-api.polymarket.com"

print("Testing Gamma API search capabilities...\n")

# 1. 测试 /markets 端点的参数
print("="*80)
print("Testing /markets endpoint with different parameters...\n")

test_params = [
    {},  # 无参数
    {"limit": 20},
    {"q": "bitcoin"},
    {"search": "bitcoin"},
    {"query": "bitcoin"},
    {"keyword": "bitcoin"},
    {"tag": "crypto"},
    {"category": "crypto"},
]

for params in test_params:
    try:
        response = requests.get(f"{gamma_url}/markets", params=params, timeout=10)
        print(f"Params: {params}")
        print(f"  Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"  Markets count: {len(data)}")
            if len(data) > 0:
                # 检查是否包含 bitcoin
                bitcoin_markets = [m for m in data if 'bitcoin' in m.get('question', '').lower()]
                print(f"  Bitcoin markets: {len(bitcoin_markets)}")
                if bitcoin_markets:
                    print(f"  Example: {bitcoin_markets[0].get('question', 'N/A')[:80]}")
        print()
    except Exception as e:
        print(f"Params: {params}")
        print(f"  Error: {e}\n")

# 2. 测试 /events 端点
print("="*80)
print("Testing /events endpoint...\n")

try:
    response = requests.get(f"{gamma_url}/events", params={"limit": 10}, timeout=10)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Events count: {len(data)}")
        if len(data) > 0:
            print(f"First event: {data[0].get('title', 'N/A')}")
            print(f"Event keys: {list(data[0].keys())}")
except Exception as e:
    print(f"Error: {e}")

# 3. 获取所有市场并统计
print("\n" + "="*80)
print("Fetching all markets from Gamma API...\n")

try:
    response = requests.get(f"{gamma_url}/markets", timeout=30)
    if response.status_code == 200:
        all_markets = response.json()
        print(f"Total markets: {len(all_markets)}")
        
        # 搜索 bitcoin 市场
        bitcoin_markets = [m for m in all_markets if 'bitcoin' in m.get('question', '').lower() or 'btc' in m.get('question', '').lower()]
        print(f"Bitcoin/BTC markets: {len(bitcoin_markets)}")
        
        # 显示前 10 个
        print("\nFirst 10 Bitcoin markets:")
        for i, market in enumerate(bitcoin_markets[:10], 1):
            print(f"{i}. {market.get('question', 'N/A')}")
            print(f"   Closed: {market.get('closed', 'N/A')}")
            print(f"   ID: {market.get('id', 'N/A')}")
except Exception as e:
    print(f"Error: {e}")
