"""测试直接访问特定市场 URL"""
import requests
import sys

sys.stdout.reconfigure(encoding='utf-8')

# 从 URL 提取信息
url = "https://polymarket.com/event/btc-updown-15m-1767093300"
slug = "btc-updown-15m-1767093300"

print(f"Testing URL: {url}")
print(f"Slug: {slug}\n")

# 1. 尝试通过 Gamma API 获取事件
print("="*80)
print("Testing Gamma API...\n")

gamma_endpoints = [
    f"https://gamma-api.polymarket.com/events/{slug}",
    f"https://gamma-api.polymarket.com/events?slug={slug}",
    f"https://gamma-api.polymarket.com/markets?slug={slug}",
]

for endpoint in gamma_endpoints:
    try:
        response = requests.get(endpoint, timeout=10)
        print(f"Endpoint: {endpoint}")
        print(f"  Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"  Response type: {type(data)}")
            if isinstance(data, dict):
                print(f"  Keys: {list(data.keys())[:10]}")
                if 'title' in data:
                    print(f"  Title: {data.get('title')}")
                if 'question' in data:
                    print(f"  Question: {data.get('question')}")
            elif isinstance(data, list) and len(data) > 0:
                print(f"  Count: {len(data)}")
                print(f"  First item: {data[0].get('title', data[0].get('question', 'N/A'))}")
        print()
    except Exception as e:
        print(f"Endpoint: {endpoint}")
        print(f"  Error: {e}\n")

# 2. 尝试搜索最新的市场
print("="*80)
print("Searching for newest markets in CLOB API...\n")

from py_clob_client.client import ClobClient

client = ClobClient("https://clob.polymarket.com")

# 获取第一页(最新的市场)
response = client.get_markets(next_cursor='MA==')

if isinstance(response, dict):
    markets = response.get('data', [])
    print(f"Total markets in first page: {len(markets)}")
    
    # 查找包含 "updown" 或时间相关的市场
    print("\nSearching for 'updown' or time-based markets:")
    
    for market in markets[:100]:  # 只检查前100个
        question = market.get('question', '').lower()
        
        if 'updown' in question or 'up down' in question or 'up or down' in question:
            print(f"\nFound: {market.get('question')}")
            print(f"  Closed: {market.get('closed')}")
            print(f"  Condition ID: {market.get('condition_id')}")
            
        # 检查是否有今天的时间戳
        if '1767093' in str(market.get('condition_id', '')):
            print(f"\nFound timestamp match: {market.get('question')}")
            print(f"  Condition ID: {market.get('condition_id')}")

# 3. 检查是否有反向排序的选项
print("\n" + "="*80)
print("Checking if there are any BTC markets in the first 50 results...\n")

btc_count = 0
for market in markets[:50]:
    question = market.get('question', '')
    if 'btc' in question.lower() or 'bitcoin' in question.lower():
        btc_count += 1
        if btc_count <= 5:
            print(f"{btc_count}. {question}")
            print(f"   Closed: {market.get('closed')}")

print(f"\nTotal BTC markets in first 50: {btc_count}")
