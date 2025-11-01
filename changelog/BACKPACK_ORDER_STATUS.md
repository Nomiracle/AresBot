# Backpack 订单状态说明

## 🔍 问题发现

在实际测试中发现，Backpack API 返回的订单状态与预期不同：

### 原始假设 ❌
```python
# 错误的假设：只有 'Open' 状态表示未完成订单
if order_status != 'Open':
    continue  # 跳过
```

### 实际情况 ✅
Backpack 新下的订单状态是 `'New'`，不是 `'Open'`！

**日志证据：**
```
[2025-11-01T04:40:37] 🔍 [Backpack] 订单 0 字段: ['clientId', 'createdAt', ..., 'status', ...]
[2025-11-01T04:40:37] ⏭️ [Backpack] 订单 0 状态为 New，跳过（非 Open 状态）
```

## 📊 Backpack 订单状态完整列表

| 状态 | 含义 | 是否未完成 | 说明 |
|------|------|-----------|------|
| `'New'` | 新订单 | ✅ 是 | 刚下单，还未进入订单簿 |
| `'Open'` | 挂单中 | ✅ 是 | 已进入订单簿，等待成交 |
| `'PartiallyFilled'` | 部分成交 | ✅ 是 | 部分成交，剩余部分继续挂单 |
| `'Filled'` | 已成交 | ❌ 否 | 完全成交 |
| `'Cancelled'` | 已取消 | ❌ 否 | 用户主动取消 |
| `'Expired'` | 已过期 | ❌ 否 | 订单过期（如 IOC、FOK） |

## 🔧 正确的过滤逻辑

```python
# ✅ 正确：接受所有未完成状态
order_status = order.get('status')
if order_status not in ['New', 'Open', 'PartiallyFilled']:
    print(f"订单状态为 {order_status}，跳过（非未完成状态）")
    continue
```

**注意：** 如果不需要处理部分成交订单，可以只接受 `['New', 'Open']`

## 🆚 与 Binance 的对比

| Backpack | Binance | 说明 |
|----------|---------|------|
| `'New'` | `'NEW'` | 新订单 |
| `'Open'` | `'NEW'` | Binance 不区分 New/Open |
| `'PartiallyFilled'` | `'PARTIALLY_FILLED'` | 部分成交 |
| `'Filled'` | `'FILLED'` | 已成交 |
| `'Cancelled'` | `'CANCELED'` | 已取消 |
| `'Expired'` | `'EXPIRED'` | 已过期 |

**关键差异：**
- Backpack 区分 `'New'` 和 `'Open'` 两种未完成状态
- Binance 统一使用 `'NEW'` 表示未完成订单

## 📝 状态转换映射

```python
def _convert_order_status(self, bpx_status: str) -> str:
    """转换订单状态为统一格式"""
    status_map = {
        'New': 'NEW',           # Backpack 新订单状态
        'Open': 'NEW',          # Backpack 挂单中状态
        'Filled': 'FILLED',
        'PartiallyFilled': 'PARTIALLY_FILLED',
        'Cancelled': 'CANCELED',
        'Expired': 'EXPIRED'
    }
    return status_map.get(bpx_status, bpx_status)
```

## 🎯 实际应用场景

### 场景 1：获取未完成订单
```python
# 需要包含 'New' 状态
if order_status not in ['New', 'Open']:
    continue
```

### 场景 2：检查订单是否成交
```python
if order_status == 'Filled':
    # 订单已成交，挂卖单
    place_sell_order()
```

### 场景 3：改价逻辑
```python
# 只改价真正在订单簿中的订单
if order_status in ['New', 'Open']:
    # 可以改价
    cancel_replace_order()
```

## ⚠️ 常见错误

### 错误 1：只检查 'Open'
```python
# ❌ 错误：会漏掉 'New' 状态的订单
if order_status != 'Open':
    continue
```

### 错误 2：不过滤已成交订单
```python
# ❌ 错误：会尝试改价已成交的订单
for order in get_open_orders():
    cancel_replace_order(order)  # 可能失败：Order not found
```

### 错误 3：大小写不匹配
```python
# ❌ 错误：Backpack 使用首字母大写
if order_status == 'new':  # 应该是 'New'
    continue
```

## 🔍 调试技巧

### 1. 打印订单完整信息
```python
print(f"订单字段: {list(order.keys())}")
print(f"订单状态: {order.get('status')}")
print(f"完整订单: {order}")
```

### 2. 记录状态变化
```python
print(f"订单 {order_id} 状态: {old_status} -> {new_status}")
```

### 3. 统计状态分布
```python
status_count = {}
for order in orders:
    status = order.get('status')
    status_count[status] = status_count.get(status, 0) + 1
print(f"状态分布: {status_count}")
```

## 📚 参考资料

- Backpack API 文档: https://docs.backpack.exchange/
- 订单状态字段: `status` (string)
- 订单字段列表: `['clientId', 'createdAt', 'executedQuantity', 'id', 'orderType', 'price', 'quantity', 'side', 'status', 'symbol', 'timeInForce', ...]`

## 更新日期
2025-11-01

## 相关修复
- `FIX_ORDER_NOT_FOUND.md` - 订单成交后未挂卖单问题
- `backpack_adapter.py` - Backpack 适配器实现
