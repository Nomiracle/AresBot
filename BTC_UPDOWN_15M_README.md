# BTC Up/Down 15分钟市场交易所适配器

## 📋 概述

`BtcUpDown15m` 是一个专门为 Polymarket 的 BTC Up/Down 15分钟市场设计的交易所适配器。它会自动计算并使用最新的 15 分钟时间戳市场,无需手动输入 token_id。

## 🎯 特性

- ✅ **自动时间戳计算** - 自动计算下一个 15 分钟市场
- ✅ **智能回退** - 如果下一个市场不存在,自动尝试当前市场
- ✅ **方向选择** - 支持 "Up" 或 "Down" 方向
- ✅ **市场刷新** - 支持手动刷新到最新市场
- ✅ **继承完整功能** - 继承 `NativePolymarketSpot` 的所有交易功能

## 📦 安装

确保已安装依赖:
```bash
pip install py-clob-client requests
```

## 🚀 使用方法

### 基本用法

```python
from exchanges.btc_updown_15m import BtcUpDown15m

# 初始化交易所 - Up 方向
exchange = BtcUpDown15m(
    api_key="0x你的钱包地址",
    api_secret="0x你的私钥",
    outcome="Up",  # 或 "Down"
    testnet=False
)

# 获取当前市场信息
market_info = exchange.get_market_info()
print(f"市场: {market_info['slug']}")
print(f"Token ID: {market_info['token_id']}")
print(f"结束时间: {market_info['end_time']}")
```

### 交易示例

```python
# 下单买入
order = exchange.create_order(
    side='BUY',
    amount=10.0,  # USDC
    price=0.52    # 价格
)

# 获取当前价格
ticker = exchange.get_symbol_ticker()
print(f"当前价格: {ticker['price']}")

# 获取账户余额
balance = exchange.get_balance()
print(f"余额: {balance}")
```

### 市场刷新

当当前市场即将结束时,可以刷新到新市场:

```python
# 刷新到最新市场
success = exchange.refresh_market()

if success:
    market_info = exchange.get_market_info()
    print(f"已切换到新市场: {market_info['slug']}")
```

## 🔧 参数说明

### 初始化参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `api_key` | str | ✅ | 钱包地址 (0x开头) |
| `api_secret` | str | ✅ | 私钥 (0x开头) |
| `outcome` | str | ✅ | 交易方向: "Up" 或 "Down" |
| `testnet` | bool | ❌ | 是否使用测试网 (默认: True) |

### 方法

#### `get_market_info() -> dict`
获取当前市场信息

返回:
```python
{
    'slug': 'btc-updown-15m-1767107700',
    'token_id': '0x...',
    'outcome': 'Up',
    'timestamp': 1767107700,
    'end_time': '2025-12-30T23:15:00'
}
```

#### `refresh_market() -> bool`
刷新到最新市场

返回: `True` 成功, `False` 失败

## 📝 工作原理

### 时间戳计算

市场 slug 格式: `btc-updown-15m-{timestamp}`

时间戳对应市场的**结束时间**,每 15 分钟一个市场:
- 00:00, 00:15, 00:30, 00:45
- 01:00, 01:15, 01:30, 01:45
- ...

### 市场查询顺序

1. **下一个 15 分钟市场** - 优先尝试即将开始的市场
2. **当前 15 分钟市场** - 如果下一个不存在,使用当前市场

### Token 选择

- 自动查找指定方向 ("Up" 或 "Down") 的 token
- 如果找不到指定方向,使用第一个可用 token

## ⚠️ 注意事项

1. **市场可用性** - 并非所有时间戳的市场都存在,Polymarket 可能不会创建某些时间段的市场
2. **市场生命周期** - 市场在结束时间后会关闭,需要及时刷新到新市场
3. **网络要求** - 需要访问 Gamma API (`https://gamma-api.polymarket.com`)
4. **私钥安全** - 请妥善保管私钥,不要泄露

## 🔗 集成到 AresBot

在 `routes.py` 或其他地方使用:

```python
from exchanges.btc_updown_15m import BtcUpDown15m

# 创建交易所实例
exchange = BtcUpDown15m(
    api_key=user_api_key,
    api_secret=user_api_secret,
    outcome="Up"
)

# 使用交易所进行交易
# ... 你的交易逻辑 ...
```

## 📊 示例输出

```
[2025-12-30T23:00:00] 🔍 [BTC Up/Down 15m] 查询市场: btc-updown-15m-1767107700
[2025-12-30T23:00:01] ✅ [BTC Up/Down 15m] 找到 Up token: 0x1234...
[2025-12-30T23:00:01] ✅ [Polymarket] 客户端初始化成功
[2025-12-30T23:00:01] ✅ [Polymarket] 适配器初始化成功
[2025-12-30T23:00:01] ✅ [BTC Up/Down 15m] 使用市场: btc-updown-15m-1767107700
[2025-12-30T23:00:01] ✅ [BTC Up/Down 15m] 交易方向: Up
[2025-12-30T23:00:01] ✅ [BTC Up/Down 15m] Token ID: 0x1234...
```

## 🐛 故障排除

### 问题: 无法获取最新市场

**原因**: 当前和下一个时间戳的市场都不存在

**解决方案**:
1. 检查 Polymarket 网站是否有该时间段的市场
2. 尝试在市场开放时间使用
3. 检查网络连接

### 问题: 找不到指定方向的 token

**原因**: 市场可能只有一个 token 或方向名称不匹配

**解决方案**:
- 适配器会自动使用第一个可用 token
- 检查日志中的实际方向名称

## 📚 相关文档

- [Polymarket API 文档](https://docs.polymarket.com/)
- [py-clob-client](https://github.com/Polymarket/py-clob-client)
- [NativePolymarketSpot 适配器](./exchanges/polymarket_adapter.py)
