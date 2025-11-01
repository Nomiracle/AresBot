# Backpack 订单查询测试工具

## 📋 功能

测试 Backpack API 的 `get_order_history()` 方法，帮助调试订单查询功能。

## 🚀 使用方法

### 方法 1：从数据库读取凭证（推荐）

```powershell
# 基本用法
python test_backpack_order.py --username admin --symbol HYPE_USDC --order-id 16598636798

# 简写形式
python test_backpack_order.py -u admin -m HYPE_USDC -o 16598636798

# 只测试最近的订单（不指定 order-id）
python test_backpack_order.py -u admin -m HYPE_USDC
```

### 方法 2：直接提供 API 密钥

```powershell
python test_backpack_order.py --api-key YOUR_API_KEY --api-secret YOUR_API_SECRET --symbol HYPE_USDC --order-id 16598636798

# 简写形式
python test_backpack_order.py -k YOUR_API_KEY -s YOUR_API_SECRET -m HYPE_USDC -o 16598636798
```

## 📝 参数说明

### 必需参数（二选一）

| 参数 | 简写 | 说明 |
|------|------|------|
| `--username` | `-u` | 从数据库读取凭证的用户名 |
| `--api-key` | `-k` | Backpack API Key（公钥） |

### 可选参数

| 参数 | 简写 | 默认值 | 说明 |
|------|------|--------|------|
| `--api-secret` | `-s` | - | Backpack API Secret（使用 `--api-key` 时必需） |
| `--symbol` | `-m` | `HYPE_USDC` | 交易对符号 |
| `--order-id` | `-o` | `16598636798` | 要查询的订单 ID |

## 📊 测试内容

脚本会执行 3 种测试：

### 测试 1：基本查询
```python
get_order_history(symbol="HYPE_USDC", limit=3)
```
- 查询最近 3 个订单
- 显示订单 ID、状态、价格等信息

### 测试 2：带 order_id 参数
```python
get_order_history(symbol="HYPE_USDC", limit=3, order_id="16598636798")
```
- 测试是否支持 `order_id` 参数
- 如果不支持会显示 `TypeError`

### 测试 3：查询更多订单并手动查找
```python
get_order_history(symbol="HYPE_USDC", limit=100)
```
- 查询最近 100 个订单
- 手动遍历查找指定的订单 ID
- 显示完整的订单 JSON 数据

## 📋 输出示例

```
============================================================
测试参数:
  API Key 长度: 44
  API Secret 长度: 88
  Symbol: HYPE_USDC
  Order ID: 16598636798
============================================================

✅ Backpack 客户端初始化成功

📋 方式 1: get_order_history(symbol, limit=3)
✅ 返回类型: <class 'list'>
✅ 返回数量: 3

订单 0:
  ID: 16598636798
  状态: Filled
  方向: Bid
  价格: 43.598
  数量: 4.0
  所有字段: ['id', 'symbol', 'side', 'status', 'price', 'quantity', ...]

============================================================
📋 方式 2: get_order_history(symbol, limit=3, order_id=...)
⚠️ order_id 参数不支持: unexpected keyword argument 'order_id'
💡 提示: get_order_history 可能不支持 order_id 参数

============================================================
📋 方式 3: get_order_history(symbol, limit=100) 然后手动查找
✅ 返回类型: <class 'list'>
✅ 返回数量: 100

✅ 找到订单 16598636798:
  状态: Filled
  方向: Bid
  价格: 43.598
  数量: 4.0
  已成交数量: 4.0

完整订单数据:
{
  "id": "16598636798",
  "symbol": "HYPE_USDC",
  "side": "Bid",
  "status": "Filled",
  "orderType": "Limit",
  "price": "43.598",
  "quantity": "4.0",
  "executedQuantity": "4.0",
  "timeInForce": "GTC",
  ...
}

============================================================
测试完成！
```

## 🔍 常见问题

### Q1: 提示 "未找到用户凭证"
**A:** 检查数据库中是否存在该用户：
```powershell
python -c "from database import get_db_connection; conn = get_db_connection(); cursor = conn.cursor(); cursor.execute('SELECT username FROM users'); print(cursor.fetchall())"
```

### Q2: 提示 "order_id 参数不支持"
**A:** 这是正常的！Backpack 的 `get_order_history()` 不支持 `order_id` 参数，需要查询一批订单然后手动过滤。

### Q3: 查询历史订单中找不到订单
**A:** 可能原因：
- 订单太旧，不在最近 100 个订单中
- 订单 ID 错误
- 交易对符号错误

尝试增加 `limit` 参数或检查订单 ID。

### Q4: API 认证失败
**A:** 检查：
- API Key 和 Secret 是否正确
- API Key 是否有查询权限
- 是否有多余的空格或换行符

## 💡 调试技巧

### 查看所有可用参数
```powershell
python test_backpack_order.py --help
```

### 只查看最近的订单
```powershell
python test_backpack_order.py -u admin -m HYPE_USDC
```

### 查询不同交易对
```powershell
python test_backpack_order.py -u admin -m SOL_USDC -o YOUR_ORDER_ID
```

## 🔗 相关文件

- `exchanges/backpack_adapter.py` - Backpack 适配器实现
- `BACKPACK_ORDER_QUERY.md` - 订单查询机制说明
- `FIX_ORDER_NOT_FOUND.md` - 订单问题修复文档

## 📅 更新日期
2025-11-01
