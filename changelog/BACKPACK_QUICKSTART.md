# Backpack 交易所快速开始

## 安装

### 1. 安装 bpx-py SDK

```bash
pip install bpx-py==2.0.11
```

或者更新所有依赖：
```bash
pip install -r requirements.txt
```

### 2. 验证安装

```bash
python -c "import bpx; print('✅ bpx-py 安装成功')"
```

## 获取 API 密钥

1. 访问 [Backpack Exchange](https://backpack.exchange/)
2. 登录账户
3. 进入 **Settings** → **API Keys**
4. 创建新的 API 密钥
5. 保存 **Public Key** 和 **Secret Key**

⚠️ **注意**: 
- 妥善保管密钥，不要泄露
- 建议设置 IP 白名单
- 根据需要设置权限（交易、查询等）

## 使用示例

### 方式 1: 通过 Web 界面

1. 启动应用：
```bash
python app.py
```

2. 访问 http://localhost:5000

3. 在配置页面：
   - **交易所**: 选择 `backpack`
   - **交易对**: 输入 `SOLUSDC`（会自动转换为 `SOL_USDC`）
   - **API Key**: 输入你的 Public Key
   - **API Secret**: 输入你的 Secret Key
   - 其他参数按需设置

4. 点击"启动机器人"

### 方式 2: 通过代码

```python
from exchanges.factory import ExchangeFactory

# 创建 Backpack 适配器
exchange = ExchangeFactory.create(
    'backpack',  # 或使用别名 'bpx'
    api_key='your_public_key_here',
    api_secret='your_secret_key_here',
    testnet=False  # Backpack 暂无测试网
)

# 测试连接
if exchange.ping():
    print("✅ 连接成功")
else:
    print("❌ 连接失败")

# 获取 SOL 价格
ticker = exchange.get_symbol_ticker('SOLUSDC')
print(f"SOL 价格: ${ticker['price']}")

# 下限价买单
order = exchange.order_limit_buy(
    symbol='SOLUSDC',
    quantity=0.1,
    price='100.00',
    timeInForce='GTC'
)
print(f"订单ID: {order['orderId']}")

# 查询订单状态
status = exchange.get_order('SOLUSDC', order['orderId'])
print(f"订单状态: {status['status']}")

# 取消订单
exchange.cancel_order('SOLUSDC', order['orderId'])
print("✅ 订单已取消")
```

## 支持的交易对

Backpack 支持多种交易对，常见的有：

| 交易对 | Binance 格式 | Backpack 格式 |
|--------|--------------|---------------|
| SOL/USDC | SOLUSDC | SOL_USDC |
| BTC/USDC | BTCUSDC | BTC_USDC |
| ETH/USDC | ETHUSDC | ETH_USDC |
| SOL/USDT | SOLUSDT | SOL_USDT |

**查看所有交易对：**
```python
from bpx.public import Public

public = Public()
markets = public.get_markets()

for market in markets:
    print(f"{market['symbol']}: {market['filters']}")
```

## 配置示例

### 基本配置

```python
config = {
    'exchange': 'backpack',
    'symbol': 'SOLUSDC',      # 自动转换为 SOL_USDC
    'api_key': 'your_key',
    'api_secret': 'your_secret',
    'quantity': 0.1,          # 每次交易数量
    'offset_percent': 1.0,    # 挂单偏移百分比
    'interval': 2,            # 轮询间隔（秒）
    'simulate_trading': 0     # 0=实盘, 1=模拟
}
```

### 高级配置

```python
config = {
    'exchange': 'backpack',
    'symbol': 'SOLUSDC',
    'api_key': 'your_key',
    'api_secret': 'your_secret',
    'quantity': 0.5,
    'offset_percent': 0.5,    # 更小的偏移
    'profit_percent': 1.5,    # 止盈百分比
    'interval': 3,            # 更长的轮询间隔
    'simulate_trading': 0,
    'timeInForce': 'GTC'      # Good Till Cancel
}
```

## 注意事项

### 1. WebSocket 限制

Backpack 目前不支持 WebSocket，系统会自动使用 REST 轮询：

```
[2025-10-30T19:48:00] ℹ️ [Backpack] WebSocket 暂不支持，将使用 REST 轮询
```

**建议：**
- 设置合理的轮询间隔（≥ 2 秒）
- 避免过于频繁的 API 调用

### 2. 改价操作

Backpack 不支持原子性改价，系统会：
1. 先取消旧订单
2. 再下新订单

这可能导致短暂的订单空窗期。

### 3. API 限流

Backpack 有 API 限流限制：
- 建议设置 `interval >= 2` 秒
- 避免同时运行多个机器人
- 监控日志中的限流错误

### 4. 精度要求

确保价格和数量符合交易对的精度要求：

```python
# 获取精度信息
info = exchange.get_symbol_info('SOLUSDC')
tick_size, price_decimals = exchange.get_price_precision(info)
step_size, qty_decimals = exchange.get_quantity_precision(info)

print(f"价格精度: {tick_size} ({price_decimals} 位小数)")
print(f"数量精度: {step_size} ({qty_decimals} 位小数)")
```

## 故障排查

### 问题 1: 连接失败

```
❌ [Backpack] Ping 失败: Connection error
```

**解决：**
- 检查网络连接
- 验证 API 密钥是否正确
- 确认 API 权限设置

### 问题 2: 交易对不存在

```
⚠️ [Backpack] 交易对 SOL_USDC 不存在
```

**解决：**
- 确认交易对在 Backpack 上存在
- 检查拼写是否正确
- 使用 `get_markets()` 查看可用交易对

### 问题 3: 订单被拒绝

```
❌ [Backpack] 限价买单失败: Insufficient balance
```

**解决：**
- 检查账户余额
- 验证订单数量和价格
- 确认精度符合要求

### 问题 4: API 限流

```
❌ [Backpack] API 调用失败: Rate limit exceeded
```

**解决：**
- 增加轮询间隔
- 减少并发请求
- 等待限流解除

## 测试

### 运行集成测试

```bash
python test_migration.py
```

预期输出：
```
✓ 支持的交易所: ['binance', 'backpack', 'bpx']
✓ 成功创建 Backpack 适配器: BackpackAdapter
✓ BPX 别名正常工作: BackpackAdapter
✅ 工厂类测试通过
```

### 手动测试

```python
# test_backpack.py
from exchanges.factory import ExchangeFactory

exchange = ExchangeFactory.create(
    'backpack',
    'your_key',
    'your_secret'
)

# 测试连接
assert exchange.ping(), "连接失败"
print("✅ 连接测试通过")

# 测试获取价格
ticker = exchange.get_symbol_ticker('SOLUSDC')
assert ticker and 'price' in ticker, "获取价格失败"
print(f"✅ 价格测试通过: ${ticker['price']}")

# 测试获取交易对信息
info = exchange.get_symbol_info('SOLUSDC')
assert info, "获取交易对信息失败"
print("✅ 交易对信息测试通过")

print("\n🎉 所有测试通过！")
```

## 监控

### 查看日志

```bash
# 实时监控
tail -f app.log | grep "Backpack"

# 查看错误
grep "❌.*Backpack" app.log

# 查看特定交易对
grep "SOL_USDC" app.log
```

### 日志格式

```
[时间戳] [用户-BACKPACK-交易对] 日志内容
```

示例：
```
[2025-10-30T19:48:00] [admin-BACKPACK-SOL_USDC] ✅ [SUCCESS] 真实买单已下。**新订单ID=12345**
[2025-10-30T19:48:01] [admin-BACKPACK-SOL_USDC] 当前价: $100.00 -> 计划挂买价: $101.00
```

## 下一步

1. **安装 bpx-py**: `pip install bpx-py`
2. **获取 API 密钥**: 访问 Backpack 官网
3. **运行测试**: `python test_migration.py`
4. **启动机器人**: 通过 Web 界面或代码
5. **监控日志**: 确保一切正常运行

## 参考资源

- **集成文档**: `BACKPACK_INTEGRATION.md`
- **故障排查**: `TROUBLESHOOTING.md`
- **API 文档**: https://docs.backpack.exchange/
- **示例代码**: `examples/bpx-py/`

---

**祝交易顺利！** 🚀
