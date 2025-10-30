# 调试指南

## 错误日志增强

所有关键错误现在都会打印完整的堆栈跟踪（traceback），方便快速定位问题。

### 增强的错误点

1. **交易循环主流程错误**
2. **WebSocket 用户消息处理错误**
3. **获取价格失败**

### 日志格式

```
[时间戳] [用户-交易所-交易对] ❌ [错误类型] 错误描述
[时间戳] [用户-交易所-交易对] 📋 [TRACEBACK]
Traceback (most recent call last):
  File "...", line X, in function_name
    code_line
ErrorType: error message
```

### 示例

```
[2025-10-30T19:25:30.123456] [admin-BINANCE-BTCUSDT] ❌ [LOOP ERR] 交易循环主流程错误: 'NoneType' object is not subscriptable
[2025-10-30T19:25:30.123456] [admin-BINANCE-BTCUSDT] 📋 [TRACEBACK]
Traceback (most recent call last):
  File "c:\Users\xubo\Desktop\AresBot\trading.py", line 163, in trading_loop
    current_price = float(bot_data.get('current_price') or exchange.get_symbol_ticker(symbol=config['symbol'])['price'])
TypeError: 'NoneType' object is not subscriptable
```

## 调试技巧

### 1. 快速定位错误

**使用 grep 过滤错误日志：**
```bash
# 查看所有错误
grep "❌" app.log

# 查看特定用户的错误
grep "\[admin-" app.log | grep "❌"

# 查看 traceback
grep -A 10 "TRACEBACK" app.log
```

**Windows PowerShell：**
```powershell
# 查看所有错误
Select-String -Pattern "❌" -Path app.log

# 查看 traceback
Select-String -Pattern "TRACEBACK" -Path app.log -Context 0,10
```

### 2. 实时监控错误

**Linux/Mac：**
```bash
# 实时监控所有错误
tail -f app.log | grep --line-buffered "❌"

# 实时监控特定用户
tail -f app.log | grep --line-buffered "\[admin-"
```

**Windows PowerShell：**
```powershell
# 实时监控
Get-Content app.log -Wait -Tail 50 | Select-String -Pattern "❌"
```

### 3. 分析错误模式

**Python 脚本：**
```python
import re
from collections import defaultdict

def analyze_errors(log_file):
    """分析错误类型和频率"""
    error_types = defaultdict(int)
    error_details = defaultdict(list)
    
    with open(log_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    for i, line in enumerate(lines):
        if '❌' in line:
            # 提取错误类型
            match = re.search(r'\[([^\]]+ERR)\]', line)
            if match:
                err_type = match.group(1)
                error_types[err_type] += 1
                
                # 提取上下文
                context = {
                    'line': line.strip(),
                    'traceback': []
                }
                
                # 查找 traceback
                if i + 1 < len(lines) and 'TRACEBACK' in lines[i + 1]:
                    j = i + 2
                    while j < len(lines) and j < i + 20:
                        if lines[j].strip():
                            context['traceback'].append(lines[j].strip())
                        else:
                            break
                        j += 1
                
                error_details[err_type].append(context)
    
    return error_types, error_details

# 使用
error_types, error_details = analyze_errors('app.log')

print("错误统计：")
for err_type, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True):
    print(f"  {err_type}: {count} 次")

print("\n错误详情：")
for err_type, details in error_details.items():
    print(f"\n{err_type} ({len(details)} 次):")
    for detail in details[:3]:  # 只显示前3个
        print(f"  - {detail['line']}")
        if detail['traceback']:
            print(f"    Traceback: {detail['traceback'][0]}")
```

### 4. 常见错误及解决方案

#### 错误 1: NoneType object is not subscriptable

**原因：**
- API 返回 None
- 字典缺少必需的键

**定位：**
```bash
grep "NoneType" app.log -A 5
```

**解决：**
- 检查 API 连接
- 验证交易对是否有效
- 查看是否有网络问题

#### 错误 2: Connection timeout

**原因：**
- 网络延迟
- API 服务器响应慢

**定位：**
```bash
grep "timeout" app.log -i
```

**解决：**
- 检查网络连接
- 增加超时时间
- 使用代理

#### 错误 3: Authentication failed

**原因：**
- API 密钥错误
- API 密钥权限不足

**定位：**
```bash
grep "Authentication" app.log
```

**解决：**
- 验证 API 密钥
- 检查 API 权限设置
- 确认 testnet/mainnet 配置

#### 错误 4: Invalid precision

**原因：**
- tick_size 或 step_size 为 0 或 None
- 精度计算错误

**定位：**
```bash
grep "precision\|tick_size\|step_size" app.log -i
```

**解决：**
- 检查交易对信息
- 使用默认精度
- 验证交易所规则

### 5. 调试模式

**启用详细日志：**
```python
# 在 trading.py 开头添加
import logging
logging.basicConfig(level=logging.DEBUG)
```

**添加调试断点：**
```python
# 在关键位置添加
import pdb; pdb.set_trace()
```

**使用 VS Code 调试：**
1. 设置断点（点击行号左侧）
2. 按 F5 启动调试
3. 使用调试控制台查看变量

### 6. 性能分析

**统计循环时间：**
```python
import time

loop_times = []
start_time = time.time()

while bot_data.get('running'):
    loop_start = time.time()
    
    # 循环逻辑
    
    loop_time = time.time() - loop_start
    loop_times.append(loop_time)
    
    if len(loop_times) % 100 == 0:
        avg_time = sum(loop_times[-100:]) / 100
        print(f"平均循环时间: {avg_time:.3f}s")
```

**内存使用监控：**
```python
import psutil
import os

process = psutil.Process(os.getpid())
memory_mb = process.memory_info().rss / 1024 / 1024
print(f"内存使用: {memory_mb:.2f} MB")
```

### 7. 单元测试

**测试交易循环：**
```python
import unittest
from unittest.mock import Mock, patch

class TestTradingLoop(unittest.TestCase):
    def test_price_fetch_failure(self):
        """测试价格获取失败的处理"""
        mock_exchange = Mock()
        mock_exchange.get_symbol_ticker.return_value = None
        
        # 应该能优雅处理
        # ...
    
    def test_invalid_precision(self):
        """测试无效精度的处理"""
        tick_size = 0
        step_size = None
        
        # 应该使用默认值
        # ...

if __name__ == '__main__':
    unittest.main()
```

### 8. 日志轮转

**防止日志文件过大：**
```python
from logging.handlers import RotatingFileHandler

handler = RotatingFileHandler(
    'app.log',
    maxBytes=50*1024*1024,  # 50MB
    backupCount=10
)
```

### 9. 远程调试

**使用 SSH 端口转发：**
```bash
# 本地访问远程服务器的 Flask 应用
ssh -L 5000:localhost:5000 user@remote-server
```

**使用远程调试器：**
```python
import debugpy
debugpy.listen(("0.0.0.0", 5678))
print("等待调试器连接...")
debugpy.wait_for_client()
```

### 10. 告警集成

**发送错误通知：**
```python
def send_alert(message):
    """发送告警通知"""
    # 邮件
    # send_email(message)
    
    # 钉钉
    # send_dingtalk(message)
    
    # Slack
    # send_slack(message)
    
    # 企业微信
    # send_wecom(message)

# 在错误处理中调用
except Exception as e:
    print(f"❌ 错误: {e}")
    traceback.print_exc()
    
    if is_critical_error(e):
        send_alert(f"严重错误: {e}")
```

## 最佳实践

1. **保留足够的日志** - 至少保留7天
2. **定期审查错误** - 每天检查错误日志
3. **设置告警阈值** - 错误超过阈值时通知
4. **记录上下文** - 包含用户、交易所、交易对
5. **使用 traceback** - 快速定位问题根源
6. **编写测试** - 覆盖错误场景
7. **监控性能** - 关注循环时间和内存
8. **文档化问题** - 记录常见问题和解决方案

## 工具推荐

- **日志分析**: ELK Stack, Grafana Loki
- **监控**: Prometheus, Grafana
- **告警**: AlertManager, PagerDuty
- **调试**: VS Code, PyCharm
- **性能**: cProfile, py-spy
- **测试**: pytest, unittest

---

**更新日期**: 2025-10-30  
**版本**: 1.0
