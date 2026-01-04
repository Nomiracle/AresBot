"""测试 Polymarket API 是否支持关键词搜索"""
import requests
import sys

sys.stdout.reconfigure(encoding='utf-8')

# Polymarket API 基础 URL
base_url = "https://clob.polymarket.com"

# 测试不同的 API 端点
print("Testing Polymarket API endpoints for search functionality...\n")

# 1. 测试是否有搜索端点
test_endpoints = [
    "/search",
    "/markets/search",
    "/api/search",
    "/api/markets/search",
]

for endpoint in test_endpoints:
    url = f"{base_url}{endpoint}?q=bitcoin"
    try:
        response = requests.get(url, timeout=5)
        print(f"Testing: {endpoint}")
        print(f"  Status: {response.status_code}")
        if response.status_code == 200:
            print(f"  Response: {response.text[:200]}")
    except Exception as e:
        print(f"Testing: {endpoint}")
        print(f"  Error: {e}")
    print()

# 2. 测试 GET_MARKETS 是否支持查询参数
print("="*80)
print("Testing GET_MARKETS with query parameters...\n")

test_params = [
    {"q": "bitcoin"},
    {"search": "bitcoin"},
    {"query": "bitcoin"},
    {"keyword": "bitcoin"},
    {"filter": "bitcoin"},
]

for params in test_params:
    url = f"{base_url}/markets"
    try:
        response = requests.get(url, params=params, timeout=5)
        print(f"Testing: /markets with params {params}")
        print(f"  Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict):
                print(f"  Keys: {list(data.keys())}")
                if 'data' in data:
                    print(f"  Markets count: {len(data['data'])}")
    except Exception as e:
        print(f"Testing: /markets with params {params}")
        print(f"  Error: {e}")
    print()

# 3. 检查 Polymarket Gamma API (可能有更多功能)
print("="*80)
print("Testing Gamma API (Polymarket's data API)...\n")

gamma_url = "https://gamma-api.polymarket.com"
gamma_endpoints = [
    "/markets",
    "/events",
]

for endpoint in gamma_endpoints:
    url = f"{gamma_url}{endpoint}?limit=10"
    try:
        response = requests.get(url, timeout=5)
        print(f"Testing: {gamma_url}{endpoint}")
        print(f"  Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"  Response type: {type(data)}")
            if isinstance(data, list) and len(data) > 0:
                print(f"  First item keys: {list(data[0].keys())[:10]}")
            elif isinstance(data, dict):
                print(f"  Keys: {list(data.keys())}")
    except Exception as e:
        print(f"Testing: {gamma_url}{endpoint}")
        print(f"  Error: {e}")
    print()
