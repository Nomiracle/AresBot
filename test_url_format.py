"""测试从 URL 推断市场标题格式"""
from py_clob_client.client import ClobClient
import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

# 从 URL 分析: https://polymarket.com/event/btc-updown-15m-1767093300
# slug: btc-updown-15m-1767093300
# 可能的标题格式:
# - BTC UpDown 15m
# - BTC Up/Down 15m
# - BTC: Up or Down? (15m)
# 时间戳: 1767093300

print("Analyzing URL pattern: btc-updown-15m-1767093300")
print("Timestamp: 1767093300")

# 转换时间戳
import datetime
try:
    dt = datetime.datetime.fromtimestamp(1767093300)
    print(f"Date: {dt}")
except:
    print("Invalid timestamp")

print("\n" + "="*80)
print("Fetching markets and searching for patterns...\n")

client = ClobClient("https://clob.polymarket.com")

all_markets = []
next_cursor = 'MA=='
max_pages = 10

for page in range(max_pages):
    response = client.get_markets(next_cursor=next_cursor)
    if isinstance(response, dict):
        markets = response.get('data', [])
        all_markets.extend(markets)
        next_cursor = response.get('next_cursor')
        if not next_cursor:
            break

print(f"Total markets: {len(all_markets)}")

# 搜索可能的标题格式
patterns = [
    r'btc.*up.*down',
    r'bitcoin.*up.*down',
    r'btc.*\?',
    r'bitcoin.*\?',
    r'btc.*higher',
    r'btc.*lower',
    r'price.*btc',
    r'btc.*price',
]

print("\n" + "="*80)
print("Searching with regex patterns...\n")

for pattern in patterns:
    found = []
    regex = re.compile(pattern, re.IGNORECASE)
    
    for market in all_markets:
        question = market.get('question', '')
        if regex.search(question):
            found.append(market)
    
    print(f"Pattern: '{pattern}'")
    print(f"  Found: {len(found)} markets")
    
    if found:
        for i, m in enumerate(found[:3], 1):
            print(f"    {i}. {m.get('question')[:80]}")
            print(f"       Closed: {m.get('closed')}")
    print()

# 搜索包含问号的 BTC 市场
print("="*80)
print("All BTC markets with question marks:\n")

btc_question_markets = []
for market in all_markets:
    question = market.get('question', '')
    if ('btc' in question.lower() or 'bitcoin' in question.lower()) and '?' in question:
        btc_question_markets.append(market)

print(f"Found {len(btc_question_markets)} BTC markets with '?'")
for i, m in enumerate(btc_question_markets[:10], 1):
    print(f"{i}. {m.get('question')}")
    print(f"   Closed: {m.get('closed')}, Active: {m.get('active')}")
