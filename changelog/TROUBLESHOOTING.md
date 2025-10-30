# 故障排查指南

## 常见错误及解决方案

### 1. 交易对不存在或无效

**错误信息：**
```
[2025-10-30T19:28:29.409333] [admin-BINANCE-BTCUSD1] ❌ [LOOP ERR] 交易循环主流程错误: 'NoneType' object is not subscriptable
⚠️ [Binance] 交易对 BTCUSD1 不存在或无效
⚠️ 无法获取交易规则，使用默认精度
```

**原因：**
- 交易对名称错误（如 `BTCUSD1` 应该是 `BTCUSDT`）
- 交易对在该交易所不存在
- 测试网和主网交易对不同

**解决方案：**

1. **检查交易对名称**
   ```
   常见错误：
   ❌ BTCUSD1  → ✅ BTCUSDT
   ❌ BTC-USDT → ✅ BTCUSDT
   ❌ btcusdt  → ✅ BTCUSDT (大写)
   ```

2. **验证交易对是否存在**
   - 访问 Binance 网站确认交易对
   - 测试网: https://testnet.binance.vision/
   - 主网: https://www.binance.com/

3. **检查配置**
   ```python
   # 确认 testnet 设置
   config = {
       'symbol': 'BTCUSDT',  # 正确的交易对名称
       'testnet': 1,          # 1=测试网, 0=主网
       # ...
   }
   ```

### 2. API 密钥错误

**错误信息：**
```
❌ [Binance] 获取交易对信息失败: API-key format invalid
```

**解决方案：**
1. 检查 API Key 和 Secret 是否正确
2. 确认是测试网还是主网密钥
3. 验证 API 权限设置

### 3. 网络连接问题

**错误信息：**
```
❌ 获取价格失败: Connection timeout
```

**解决方案：**
1. 检查网络连接
2. 尝试使用代理
3. 增加超时时间

### 4. 精度错误

**错误信息：**
```
⚠️ tick_size 无效，使用默认精度
⚠️ step_size 无效，使用默认精度
```

**解决方案：**
- 系统会自动使用默认精度
- 如果持续出现，检查交易对是否有效

## 快速诊断

### 步骤 1: 检查日志

```bash
# 查看最新错误
tail -50 app.log | grep "❌"

# 查看特定交易对
grep "BTCUSD1" app.log
```

### 步骤 2: 验证配置

```python
# 在 Python 控制台测试
from binance.client import Client

# 测试网
client = Client('your_key', 'your_secret', testnet=True)

# 测试连接
client.ping()

# 测试交易对
info = client.get_symbol_info(symbol='BTCUSDT')
print(info)
```

### 步骤 3: 查看完整 traceback

```bash
# 查看所有 traceback
grep -A 10 "TRACEBACK" app.log
```

## 修复历史

### 2025-10-30: NoneType 错误修复

**问题：**
- `get_symbol_info()` 返回 None 导致崩溃
- `get_price_precision()` 未检查 None

**修复：**
1. 在 `binance_adapter.py` 中添加 None 检查
2. 在 `trading.py` 中添加异常处理
3. 使用默认精度作为回退

**代码变更：**
```python
# binance_adapter.py
def get_price_precision(self, symbol_info: Dict) -> tuple:
    if not symbol_info or 'filters' not in symbol_info:
        print(f"⚠️ symbol_info 无效，使用默认价格精度")
        return 0.01, 2  # 默认值
    # ...

# trading.py
try:
    info = exchange.get_symbol_info(symbol=config['symbol'])
    if info:
        tick_size, price_decimals = exchange.get_price_precision(info)
    else:
        tick_size, price_decimals = 0.01, 2  # 默认值
except Exception as e:
    tick_size, price_decimals = 0.01, 2  # 默认值
```

## 预防措施

1. **验证输入**
   - 启动前验证交易对名称
   - 检查 API 密钥格式

2. **使用默认值**
   - 所有关键参数都有默认值
   - 优雅降级而非崩溃

3. **详细日志**
   - 记录所有错误和警告
   - 包含完整 traceback

4. **监控告警**
   - 设置错误阈值
   - 自动通知管理员

## 联系支持

如果问题仍未解决：

1. 收集以下信息：
   - 完整错误日志
   - 配置信息（隐藏密钥）
   - 系统环境

2. 查看文档：
   - `ERROR_HANDLING.md`
   - `DEBUG_GUIDE.md`

3. 提交 Issue 或联系开发者

---

**更新日期**: 2025-10-30  
**版本**: 1.0
