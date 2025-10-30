# 日志格式说明

## 统一日志格式

所有交易相关日志现在使用统一的前缀格式：

```
[时间戳] [用户-交易所-交易对] 日志内容
```

### 格式说明

- **时间戳**: ISO 8601 格式，如 `2025-10-30T19:20:30.123456`
- **用户**: 登录用户名
- **交易所**: 交易所名称（大写），如 `BINANCE`、`OKX`
- **交易对**: 交易对符号，如 `BTCUSDT`、`ETHUSDT`

### 示例

```
[2025-10-30T19:20:30.123456] [admin-BINANCE-BTCUSDT] ▶️ 交易循环已启动
[2025-10-30T19:20:31.234567] [admin-BINANCE-BTCUSDT] 🎯 交易规则加载完成：tick_size=0.01, step_size=0.00001
[2025-10-30T19:20:32.345678] [admin-BINANCE-BTCUSDT] 当前价: $50000.00 -> 计划挂买价: $50500.00（数量: 0.001）
[2025-10-30T19:20:33.456789] [admin-BINANCE-ETHUSDT] ▶️ 交易循环已启动
[2025-10-30T19:20:34.567890] [user2-OKX-BTCUSDT] ▶️ 交易循环已启动
```

## 特殊前缀

### 全局操作

当操作影响所有交易对时，使用 `ALL` 标识：

```
[2025-10-30T19:20:35.678901] [admin-ALL-ALL] ◼️ 机器人停止请求
```

## 日志级别标识

### 表情符号含义

- ▶️ 启动/开始
- ◼️ 停止/结束
- ✅ 成功
- ❌ 错误/失败
- ⚠️ 警告
- ℹ️ 信息
- 🎯 配置/规则
- 🔄 恢复/重试
- 🔁 改价/替换
- 📌 保留/维持
- ⏭️ 跳过
- ➡️ 执行
- ⏸️ 暂停/禁用

### 日志类型标签

- `[WS]` - WebSocket 相关
- `[REST-FALLBACK]` - REST 轮询回退
- `[RECOVER]` - 订单恢复
- `[REPRICE]` - 订单改价
- `[CHECK]` - 订单检查
- `[EXECUTE]` - 执行下单
- `[SUCCESS]` - 下单成功
- `[FAILURE]` - 下单失败
- `[SKIP]` - 跳过操作
- `[POLL ERR]` - 轮询错误
- `[LOOP ERR]` - 循环错误
- `[SELL ERR]` - 卖单错误

## 日志过滤示例

### 按用户过滤

```bash
# Linux/Mac
grep "\[admin-" app.log

# Windows PowerShell
Select-String -Pattern "\[admin-" -Path app.log
```

### 按交易所过滤

```bash
# 查看所有币安相关日志
grep "BINANCE" app.log

# 查看所有 OKX 相关日志
grep "OKX" app.log
```

### 按交易对过滤

```bash
# 查看 BTCUSDT 相关日志
grep "BTCUSDT" app.log

# 查看特定用户的特定交易对
grep "\[admin-BINANCE-BTCUSDT\]" app.log
```

### 按日志类型过滤

```bash
# 查看所有错误
grep "❌" app.log

# 查看所有 WebSocket 相关
grep "\[WS\]" app.log

# 查看所有订单成交
grep "成交" app.log
```

### 组合过滤

```bash
# 查看特定用户的错误日志
grep "\[admin-" app.log | grep "❌"

# 查看特定交易对的 WebSocket 日志
grep "BTCUSDT" app.log | grep "\[WS\]"

# 查看特定时间段的日志
grep "2025-10-30T19:2" app.log
```

## Python 日志解析示例

```python
import re
from datetime import datetime

def parse_log_line(line):
    """解析日志行"""
    pattern = r'\[([^\]]+)\] \[([^-]+)-([^-]+)-([^\]]+)\] (.+)'
    match = re.match(pattern, line)
    if match:
        return {
            'timestamp': datetime.fromisoformat(match.group(1)),
            'user': match.group(2),
            'exchange': match.group(3),
            'symbol': match.group(4),
            'message': match.group(5)
        }
    return None

# 使用示例
with open('app.log', 'r', encoding='utf-8') as f:
    for line in f:
        log = parse_log_line(line)
        if log:
            # 过滤特定用户
            if log['user'] == 'admin':
                print(log)
            
            # 过滤特定交易所
            if log['exchange'] == 'BINANCE':
                print(log)
            
            # 过滤特定交易对
            if log['symbol'] == 'BTCUSDT':
                print(log)
```

## 日志监控建议

### 实时监控

```bash
# Linux/Mac
tail -f app.log | grep "\[admin-"

# Windows PowerShell
Get-Content app.log -Wait -Tail 50 | Select-String -Pattern "\[admin-"
```

### 错误告警

```bash
# 监控错误日志并发送告警
tail -f app.log | grep "❌" | while read line; do
    echo "ERROR: $line"
    # 发送邮件/钉钉/Slack 通知
done
```

### 性能统计

```python
import re
from collections import defaultdict

def analyze_logs(log_file):
    """分析日志统计"""
    stats = defaultdict(lambda: {
        'total': 0,
        'success': 0,
        'error': 0
    })
    
    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            log = parse_log_line(line)
            if log:
                key = f"{log['user']}-{log['exchange']}-{log['symbol']}"
                stats[key]['total'] += 1
                
                if '✅' in log['message']:
                    stats[key]['success'] += 1
                elif '❌' in log['message']:
                    stats[key]['error'] += 1
    
    return stats

# 打印统计结果
stats = analyze_logs('app.log')
for key, data in stats.items():
    print(f"{key}: {data['success']}/{data['total']} 成功, {data['error']} 错误")
```

## 日志轮转建议

### 使用 Python logging

```python
import logging
from logging.handlers import RotatingFileHandler

# 配置日志轮转
handler = RotatingFileHandler(
    'app.log',
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)
handler.setFormatter(logging.Formatter(
    '[%(asctime)s] %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S'
))

logger = logging.getLogger()
logger.addHandler(handler)
```

### 使用 logrotate (Linux)

```bash
# /etc/logrotate.d/aresbot
/path/to/AresBot/app.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0644 user group
}
```

## 最佳实践

1. **保持格式一致**: 所有日志都使用统一的前缀格式
2. **使用表情符号**: 便于快速识别日志类型
3. **添加上下文**: 包含用户、交易所、交易对信息
4. **分级记录**: 区分信息、警告、错误
5. **定期清理**: 设置日志轮转，避免文件过大
6. **监控告警**: 对关键错误设置实时告警
7. **统计分析**: 定期分析日志，优化系统性能

---

**更新日期**: 2025-10-30  
**版本**: 1.0
