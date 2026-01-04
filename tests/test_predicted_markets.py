"""测试预测的市场 slug 是否存在"""
import requests
import sys
import datetime

sys.stdout.reconfigure(encoding='utf-8')

print("Testing predicted market slugs...\n")

# 生成当前和未来的时间戳
now = datetime.datetime.now()
current_minute = now.minute
next_15min_mark = ((current_minute // 15) + 1) * 15

if next_15min_mark >= 60:
    next_time = now.replace(hour=now.hour + 1, minute=0, second=0, microsecond=0)
else:
    next_time = now.replace(minute=next_15min_mark, second=0, microsecond=0)

# 测试过去、当前和未来的市场
test_times = []

# 过去的 5 个市场
for i in range(5, 0, -1):
    past_time = next_time - datetime.timedelta(minutes=15*i)
    test_times.append(('Past', past_time))

# 当前市场
test_times.append(('Current', next_time))

# 未来的 3 个市场
for i in range(1, 4):
    future_time = next_time + datetime.timedelta(minutes=15*i)
    test_times.append(('Future', future_time))

print(f"Current time: {now}")
print(f"Testing {len(test_times)} market timestamps...\n")
print("="*80)

found_markets = []
not_found_markets = []

for label, test_time in test_times:
    timestamp = int(test_time.timestamp())
    slug = f"btc-updown-15m-{timestamp}"
    
    try:
        response = requests.get(f'https://gamma-api.polymarket.com/events?slug={slug}', timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                event = data[0]
                found_markets.append((label, test_time, slug, event))
                print(f"✓ [{label}] {test_time.strftime('%Y-%m-%d %H:%M')}")
                print(f"  Slug: {slug}")
                print(f"  Title: {event.get('title')}")
                print(f"  Closed: {event.get('closed')}, Active: {event.get('active')}")
            else:
                not_found_markets.append((label, test_time, slug))
                print(f"✗ [{label}] {test_time.strftime('%Y-%m-%d %H:%M')} - Not found")
        else:
            not_found_markets.append((label, test_time, slug))
            print(f"✗ [{label}] {test_time.strftime('%Y-%m-%d %H:%M')} - API error")
    except Exception as e:
        not_found_markets.append((label, test_time, slug))
        print(f"✗ [{label}] {test_time.strftime('%Y-%m-%d %H:%M')} - Error: {e}")
    
    print()

# 总结
print("="*80)
print(f"\nSummary:")
print(f"  Found: {len(found_markets)} markets")
print(f"  Not found: {len(not_found_markets)} markets")

if found_markets:
    print(f"\n市场创建规律:")
    print(f"  - 每 15 分钟创建一个新市场")
    print(f"  - 时间戳对应市场结束时间")
    print(f"  - Slug 格式: btc-updown-15m-{timestamp}")
    
    # 检查市场的生命周期
    if len(found_markets) > 1:
        print(f"\n市场状态:")
        for label, test_time, slug, event in found_markets:
            status = "已关闭" if event.get('closed') else "进行中"
            print(f"  {test_time.strftime('%H:%M')}: {status}")
