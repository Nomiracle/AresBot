"""测试 Polymarket API 参数"""
from py_clob_client.client import ClobClient
import sys

sys.stdout.reconfigure(encoding='utf-8')

client = ClobClient("https://clob.polymarket.com")

# 测试不同的 API 调用
print("Testing different API parameters...")

# 1. 默认调用
print("\n1. Default get_markets():")
response = client.get_markets()
if isinstance(response, dict):
    markets = response.get('data', response.get('markets', []))
    print(f"   Markets: {len(markets)}")
    print(f"   Response keys: {response.keys()}")
    if 'next_cursor' in response or 'cursor' in response or 'offset' in response:
        print(f"   Pagination info: {response.get('next_cursor', response.get('cursor', response.get('offset')))}")
elif isinstance(response, list):
    print(f"   Markets: {len(response)}")

# 2. 尝试获取更多市场
print("\n2. Trying to get more markets...")
try:
    # 尝试不同的参数
    import inspect
    sig = inspect.signature(client.get_markets)
    print(f"   get_markets signature: {sig}")
except Exception as e:
    print(f"   Could not inspect signature: {e}")

# 3. 检查是否有搜索或过滤功能
print("\n3. Checking client methods:")
methods = [m for m in dir(client) if not m.startswith('_')]
print(f"   Available methods: {', '.join(methods[:20])}")

# 4. 尝试搜索特定市场
print("\n4. Looking for market search methods:")
search_methods = [m for m in dir(client) if 'search' in m.lower() or 'filter' in m.lower() or 'query' in m.lower()]
if search_methods:
    print(f"   Found: {search_methods}")
else:
    print("   No search methods found")

# 5. 检查响应结构
print("\n5. Response structure analysis:")
response = client.get_markets()
if isinstance(response, dict):
    print(f"   Type: dict")
    print(f"   Keys: {list(response.keys())}")
    if 'data' in response:
        print(f"   data type: {type(response['data'])}")
        if isinstance(response['data'], list) and len(response['data']) > 0:
            print(f"   First market keys: {list(response['data'][0].keys())[:10]}")
