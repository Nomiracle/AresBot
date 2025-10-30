# Backpack (BPX) 交易所集成文档

## 概述

已成功集成 Backpack 交易所（也称为 BPX），支持通过统一的适配器接口进行交易。

**集成时间**: 2025-10-30  
**SDK**: bpx-py v2.0.11

## 新增文件

### 1. `exchanges/backpack_adapter.py`
Backpack 交易所适配器实现，包含：
- 完整的 BaseExchange 接口实现
- 交易对格式转换（BTCUSDT ↔ BTC_USDT）
- 订单管理（下单、查询、取消）
- 精度处理
- 错误处理

### 2. `examples/bpx-py/`
官方示例代码（参考用）：
- `account_examples.py` - 账户相关 API 示例
- `public_example.py` - 公共 API 示例

## 功能特性

### ✅ 已支持

1. **连接测试**
   - `ping()` - 测试连接

2. **市场数据**
   - `get_symbol_info()` - 获取交易对信息
   - `get_symbol_ticker()` - 获取当前价格
   - 自动缓存市场信息

3. **订单管理**
   - `order_limit_buy()` - 限价买单
   - `order_limit_sell()` - 限价卖单
   - `get_open_orders()` - 获取未完成订单
   - `get_order()` - 查询订单状态
   - `cancel_order()` - 取消订单
   - `cancel_replace_order()` - 改价（分两步实现）

4. **精度处理**
   - `get_price_precision()` - 价格精度
   - `get_quantity_precision()` - 数量精度

5. **交易对格式转换**
   - 自动转换 Binance 格式到 Backpack 格式
   - BTCUSDT → BTC_USDT
   - ETHUSDC → ETH_USDC
   - SOLUSDC → SOL_USDC

### ⚠️ 限制

1. **WebSocket 支持**
   - Backpack 暂不支持 WebSocket 实时数据流
   - 系统会自动使用 REST 轮询作为回退方案
   - 不影响核心交易功能

2. **测试网**
   - Backpack 目前没有公开的测试网
   - testnet 参数保留但不生效

## 使用方法

### 1. 安装依赖

```bash
pip install bpx-py==2.0.11
```

或使用 requirements.txt：
```bash
pip install -r requirements.txt
```

### 2. 创建适配器

```python
from exchanges.factory import ExchangeFactory

# 使用 'backpack' 或 'bpx'
exchange = ExchangeFactory.create(
    'backpack',  # 或 'bpx'
    api_key='your_public_key',
    api_secret='your_secret_key',
    testnet=False  # Backpack 暂无测试网
)
```

### 3. 基本操作

```python
# 测试连接
if exchange.ping():
    print("连接成功")

# 获取价格
ticker = exchange.get_symbol_ticker('SOLUSDC')
print(f"SOL 价格: {ticker['price']}")

# 下限价买单
order = exchange.order_limit_buy(
    symbol='SOLUSDC',
    quantity=0.1,
    price='100.00',
    timeInForce='GTC'
)
print(f"订单ID: {order['orderId']}")

# 查询订单
order_status = exchange.get_order('SOLUSDC', order['orderId'])
print(f"订单状态: {order_status['status']}")

# 取消订单
exchange.cancel_order('SOLUSDC', order['orderId'])
```

### 4. 在配置中使用

在 Web 界面或配置中指定交易所：

```python
config = {
    'exchange': 'backpack',  # 指定使用 Backpack
    'symbol': 'SOLUSDC',     # 会自动转换为 SOL_USDC
    'api_key': 'your_key',
    'api_secret': 'your_secret',
    'quantity': 0.1,
    'offset_percent': 1.0,
    # ...
}
```

## 交易对格式

### Binance 格式 → Backpack 格式

| Binance | Backpack | 说明 |
|---------|----------|------|
| BTCUSDT | BTC_USDT | 比特币/USDT |
| ETHUSDC | ETH_USDC | 以太坊/USDC |
| SOLUSDC | SOL_USDC | Solana/USDC |
| BTCUSDC_PERP | BTC_USDC_PERP | 永续合约 |

适配器会自动进行转换，无需手动处理。

## 订单状态映射

| Backpack | 统一格式 | 说明 |
|----------|----------|------|
| Open | NEW | 新订单 |
| Filled | FILLED | 完全成交 |
| PartiallyFilled | PARTIALLY_FILLED | 部分成交 |
| Cancelled | CANCELED | 已取消 |
| Expired | EXPIRED | 已过期 |

## 订单方向映射

| 统一格式 | Backpack | 说明 |
|----------|----------|------|
| BUY | Bid | 买单 |
| SELL | Ask | 卖单 |

## API 限流

Backpack 有 API 限流限制，请注意：
- 合理设置轮询间隔（建议 ≥ 1 秒）
- 避免频繁调用 API
- 使用市场信息缓存

## 错误处理

适配器包含完整的错误处理：

```python
try:
    order = exchange.order_limit_buy('SOLUSDC', 0.1, '100.00')
except Exception as e:
    print(f"下单失败: {e}")
```

所有错误都会记录到日志：
```
[2025-10-30T19:48:00] ❌ [Backpack] 限价买单失败 (SOLUSDC): API error message
```

## 测试

运行测试脚本：

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

## 与 Binance 的差异

| 功能 | Binance | Backpack | 说明 |
|------|---------|----------|------|
| WebSocket | ✅ 支持 | ❌ 不支持 | 使用 REST 轮询 |
| 测试网 | ✅ 支持 | ❌ 不支持 | 直接使用主网 |
| 改价 | ✅ 原子操作 | ⚠️ 两步操作 | 先取消后下单 |
| 交易对格式 | BTCUSDT | BTC_USDT | 自动转换 |
| 订单方向 | BUY/SELL | Bid/Ask | 自动转换 |

## 常见问题

### Q: 为什么没有实时价格更新？
A: Backpack 暂不支持 WebSocket，系统会自动使用 REST 轮询获取价格。

### Q: 如何获取 Backpack API 密钥？
A: 访问 Backpack 官网，在账户设置中创建 API 密钥。

### Q: 支持哪些交易对？
A: 支持 Backpack 上所有现货交易对，包括 USDC 和 USDT 计价。

### Q: 改价操作是否原子性？
A: 不是。Backpack 不支持原子性改价，适配器会先取消旧订单再下新订单。

### Q: 如何查看支持的交易对？
A: 
```python
from bpx.public import Public
public = Public()
markets = public.get_markets()
for market in markets:
    print(market['symbol'])
```

## 扩展功能

适配器提供了访问原始客户端的方法：

```python
# 获取账户客户端
account = exchange.get_account()

# 使用 Backpack 特有功能
balances = account.get_balances()
positions = account.get_open_positions()
deposits = account.get_deposits(limit=100, offset=0)

# 获取公共客户端
public = exchange.get_public()
assets = public.get_assets()
status = public.get_status()
```

## 未来计划

- [ ] WebSocket 支持（等待 Backpack 官方支持）
- [ ] 测试网支持（等待 Backpack 官方支持）
- [ ] 更多订单类型（市价单、止损单等）
- [ ] 永续合约支持
- [ ] 借贷功能集成

## 参考资源

- **Backpack 官网**: https://backpack.exchange/
- **bpx-py GitHub**: https://github.com/backpack-exchange/bpx-py
- **API 文档**: https://docs.backpack.exchange/
- **示例代码**: `examples/bpx-py/`

## 技术支持

如有问题：
1. 查看日志文件中的错误信息
2. 参考 `TROUBLESHOOTING.md`
3. 查看 Backpack 官方文档
4. 提交 Issue

---

**更新日期**: 2025-10-30  
**版本**: 1.0  
**状态**: ✅ 生产就绪
