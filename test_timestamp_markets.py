"""分析 Polymarket 时间戳市场的规律"""
import requests
import sys
import datetime

sys.stdout.reconfigure(encoding='utf-8')

print("Analyzing Polymarket timestamp-based markets...\n")

# 1. 获取多个 Bitcoin Up/Down 市场
gamma_url = "https://gamma-api.polymarket.com"

# 搜索所有 Bitcoin 相关的事件
response = requests.get(f"{gamma_url}/events", params={'limit': 1000}, timeout=30)

if response.status_code == 200:
    events = response.json()
    
    # 筛选出 "Bitcoin Up or Down" 类型的市场
    btc_updown_markets = []
    
    for event in events:
        title = event.get('title', '')
        slug = event.get('slug', '')
        
        if 'bitcoin' in title.lower() and ('up or down' in title.lower() or 'updown' in slug):
            btc_updown_markets.append(event)
    
    print(f"Found {len(btc_updown_markets)} Bitcoin Up/Down markets\n")
    print("="*80)
    
    if btc_updown_markets:
        print("Market Details:\n")
        
        timestamps = []
        
        for i, market in enumerate(btc_updown_markets[:20], 1):
            title = market.get('title')
            slug = market.get('slug')
            end_date = market.get('endDate')
            created = market.get('creationDate')
            closed = market.get('closed')
            
            # 从 slug 提取时间戳
            parts = slug.split('-')
            if len(parts) >= 4:
                timestamp_str = parts[-1]
                try:
                    timestamp = int(timestamp_str)
                    dt = datetime.datetime.fromtimestamp(timestamp)
                    timestamps.append(timestamp)
                    
                    print(f"{i}. {title}")
                    print(f"   Slug: {slug}")
                    print(f"   Timestamp: {timestamp} -> {dt}")
                    print(f"   End Date: {end_date}")
                    print(f"   Closed: {closed}")
                    print()
                except:
                    pass
        
        # 分析时间戳规律
        if len(timestamps) > 1:
            print("="*80)
            print("Timestamp Analysis:\n")
            
            timestamps.sort()
            
            print(f"Total timestamps: {len(timestamps)}")
            print(f"First: {timestamps[0]} -> {datetime.datetime.fromtimestamp(timestamps[0])}")
            print(f"Last: {timestamps[-1]} -> {datetime.datetime.fromtimestamp(timestamps[-1])}")
            
            # 计算时间间隔
            intervals = []
            for i in range(1, len(timestamps)):
                interval = timestamps[i] - timestamps[i-1]
                intervals.append(interval)
            
            if intervals:
                print(f"\nTime intervals (seconds):")
                for i, interval in enumerate(intervals[:10], 1):
                    minutes = interval / 60
                    print(f"  {i}. {interval} seconds = {minutes:.1f} minutes")
                
                # 统计间隔
                unique_intervals = set(intervals)
                print(f"\nUnique intervals:")
                for interval in sorted(unique_intervals):
                    count = intervals.count(interval)
                    minutes = interval / 60
                    print(f"  {interval} seconds ({minutes:.0f} min): {count} times")

# 2. 检查当前时间和下一个市场时间
print("\n" + "="*80)
print("Predicting next market timestamps:\n")

now = datetime.datetime.now()
print(f"Current time: {now}")
print(f"Current timestamp: {int(now.timestamp())}")

# 计算下一个 15 分钟间隔
current_minute = now.minute
next_15min_mark = ((current_minute // 15) + 1) * 15

if next_15min_mark >= 60:
    next_time = now.replace(hour=now.hour + 1, minute=0, second=0, microsecond=0)
else:
    next_time = now.replace(minute=next_15min_mark, second=0, microsecond=0)

print(f"\nNext 15-minute mark: {next_time}")
print(f"Next timestamp: {int(next_time.timestamp())}")

# 生成接下来几个时间戳
print("\nNext 5 market timestamps:")
for i in range(5):
    future_time = next_time + datetime.timedelta(minutes=15*i)
    future_timestamp = int(future_time.timestamp())
    slug = f"btc-updown-15m-{future_timestamp}"
    print(f"{i+1}. {future_time} -> {future_timestamp}")
    print(f"   Slug: {slug}")
