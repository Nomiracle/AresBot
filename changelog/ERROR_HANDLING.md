# 错误处理说明

## 已修复的错误

### 1. NoneType 错误 (2025-10-30)

**错误信息：**
```
'NoneType' object is not subscriptable
```

**原因：**
- `exchange.get_symbol_ticker()` 可能返回 None
- 返回的字典可能不包含 'price' 键
- `tick_size` 或 `step_size` 可能为 None

**修复方案：**

#### 价格获取
```python
# 修复前
current_price = float(bot_data.get('current_price') or exchange.get_symbol_ticker(symbol=config['symbol'])['price'])

# 修复后
current_price = bot_data.get('current_price')
if not current_price:
    try:
        ticker = exchange.get_symbol_ticker(symbol=config['symbol'])
        if ticker and 'price' in ticker:
            current_price = float(ticker['price'])
        else:
            print(f"⚠️ 无法获取当前价格，跳过本次循环")
            time.sleep(config.get('interval', 1))
            continue
    except Exception as e:
        print(f"❌ 获取价格失败: {e}")
        time.sleep(config.get('interval', 1))
        continue
```

#### 精度对齐
```python
# 修复前
aligned_price = math.floor(target_price / tick_size) * tick_size

# 修复后
if tick_size and tick_size > 0:
    aligned_price = math.floor(target_price / tick_size) * tick_size
    aligned_price = round(aligned_price, int(abs(math.log10(tick_size))))
else:
    aligned_price = round(target_price, 2)
    print(f"⚠️ tick_size 无效，使用默认精度")
```

## 错误处理策略

### 1. 防御性编程

**原则：**
- 假设所有外部调用都可能失败
- 检查所有返回值是否为 None
- 验证字典键是否存在

**示例：**
```python
# ❌ 不安全
price = api_call()['price']

# ✅ 安全
result = api_call()
if result and 'price' in result:
    price = result['price']
else:
    # 处理错误
    pass
```

### 2. 优雅降级

**策略：**
- 使用默认值
- 跳过当前循环
- 记录警告日志

**示例：**
```python
# 无法获取价格时跳过
if not current_price:
    print(f"{log_prefix} ⚠️ 无法获取价格，跳过本次循环")
    time.sleep(interval)
    continue

# 使用默认精度
if not tick_size:
    tick_size = 0.01
    print(f"{log_prefix} ⚠️ 使用默认 tick_size")
```

### 3. 异常捕获层次

**层次结构：**
```python
while bot_data.get('running'):
    try:
        # 主循环逻辑
        
        try:
            # 具体操作（如获取价格）
            ticker = exchange.get_symbol_ticker(symbol)
        except Exception as e:
            # 操作级别错误处理
            print(f"❌ 获取价格失败: {e}")
            continue
            
    except Exception as e:
        # 循环级别错误处理
        print(f"❌ [LOOP ERR] {e}")
        time.sleep(1)
```

## 常见错误及解决方案

### 1. API 调用失败

**错误：**
- 网络超时
- API 限流
- 认证失败

**解决：**
```python
try:
    result = exchange.api_call()
except Exception as e:
    print(f"❌ API 调用失败: {e}")
    time.sleep(retry_delay)
    continue
```

### 2. 数据格式错误

**错误：**
- 返回值为 None
- 缺少必需字段
- 类型不匹配

**解决：**
```python
if result and isinstance(result, dict) and 'price' in result:
    price = float(result['price'])
else:
    print(f"⚠️ 数据格式错误")
    use_default_value()
```

### 3. 精度计算错误

**错误：**
- 除以零
- log10(0)
- 负数精度

**解决：**
```python
if tick_size and tick_size > 0:
    decimals = int(abs(math.log10(tick_size)))
    aligned = round(price, decimals)
else:
    aligned = round(price, 2)  # 默认精度
```

### 4. WebSocket 连接失败

**错误：**
- 连接超时
- 认证失败
- 网络中断

**解决：**
```python
try:
    ws_result = exchange.start_websocket(...)
    if not ws_result['user_enabled']:
        print(f"ℹ️ 用户数据流未启用，使用 REST 轮询")
except Exception as e:
    print(f"❌ WebSocket 启动失败: {e}")
    # 使用 REST 轮询作为回退
```

## 错误日志格式

### 标准格式

```
[时间戳] [用户-交易所-交易对] ❌ [错误类型] 错误描述
```

### 错误类型标签

- `[API ERR]` - API 调用错误
- `[WS ERR]` - WebSocket 错误
- `[PARSE ERR]` - 数据解析错误
- `[CALC ERR]` - 计算错误
- `[DB ERR]` - 数据库错误
- `[LOOP ERR]` - 循环主流程错误

### 示例

```
[2025-10-30T19:22:23.458295] [admin-BINANCE-BTCUSDT] ❌ [API ERR] 获取价格失败: Connection timeout
[2025-10-30T19:22:24.567890] [admin-BINANCE-BTCUSDT] ⚠️ tick_size 无效，使用默认精度
[2025-10-30T19:22:25.678901] [admin-BINANCE-BTCUSDT] ❌ [WS ERR] WebSocket 启动失败: Authentication failed
```

## 监控建议

### 1. 错误统计

```python
# 统计每种错误的出现次数
error_counts = {
    'api_error': 0,
    'ws_error': 0,
    'parse_error': 0,
    'calc_error': 0
}

# 在日志中记录
if 'API ERR' in log_line:
    error_counts['api_error'] += 1
```

### 2. 告警阈值

```python
# 设置告警阈值
ALERT_THRESHOLDS = {
    'api_error': 10,      # 10次API错误
    'ws_error': 5,        # 5次WebSocket错误
    'loop_error': 3       # 3次循环错误
}

# 超过阈值时发送告警
if error_counts['api_error'] > ALERT_THRESHOLDS['api_error']:
    send_alert("API 错误次数过多")
```

### 3. 自动恢复

```python
# 连续错误计数
consecutive_errors = 0
MAX_CONSECUTIVE_ERRORS = 5

try:
    # 正常操作
    consecutive_errors = 0  # 成功后重置
except Exception as e:
    consecutive_errors += 1
    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
        print(f"❌ 连续错误 {consecutive_errors} 次，停止机器人")
        bot_data['running'] = False
```

## 测试建议

### 1. 模拟错误场景

```python
# 测试 API 返回 None
def test_none_response():
    ticker = None
    # 应该能优雅处理
    
# 测试缺少字段
def test_missing_field():
    ticker = {'symbol': 'BTCUSDT'}  # 缺少 price
    # 应该能检测并处理
    
# 测试无效精度
def test_invalid_precision():
    tick_size = 0
    step_size = None
    # 应该使用默认值
```

### 2. 压力测试

```python
# 测试连续错误
for i in range(100):
    simulate_api_error()
    # 应该能持续运行

# 测试网络中断
disconnect_network()
time.sleep(60)
reconnect_network()
# 应该能自动恢复
```

## 最佳实践

1. **永远不要假设外部调用会成功**
2. **检查所有返回值和字典键**
3. **为所有关键操作添加 try-except**
4. **使用有意义的错误日志**
5. **实现优雅降级策略**
6. **设置错误告警阈值**
7. **定期审查错误日志**
8. **编写错误场景测试**

---

**更新日期**: 2025-10-30  
**版本**: 1.0
