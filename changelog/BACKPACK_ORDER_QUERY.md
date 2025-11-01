# Backpack 订单查询机制

## 🔍 问题背景

Backpack API 的 `get_open_order()` 方法**只返回未完成的订单**，如果订单已经成交或已取消，会返回 `RESOURCE_NOT_FOUND` 错误。

这导致程序无法区分：
- 订单已成交（需要挂卖单）
- 订单真的不存在（数据错误）

## 📊 Backpack API 订单查询方法

### 1. `get_open_order(symbol, order_id)`
**用途：** 查询单个未完成订单

**返回：**
- ✅ 订单存在且未完成 → 返回订单详情
- ❌ 订单已成交/已取消 → 返回错误 `RESOURCE_NOT_FOUND`

**示例：**
```python
order = account.get_open_order(symbol="HYPE_USDC", order_id="16598636798")

# 如果订单已成交
# {'code': 'RESOURCE_NOT_FOUND', 'message': 'Not Found'}
```

### 2. `get_open_orders(symbol)`
**用途：** 查询所有未完成订单

**返回：** 订单列表（只包含未完成的订单）

**示例：**
```python
orders = account.get_open_orders("HYPE_USDC")
# [{'id': '123', 'status': 'New', ...}, {'id': '456', 'status': 'Open', ...}]
```

### 3. `get_order_history(symbol, limit=100, order_id=None)` ⭐
**用途：** 查询历史订单（包括已成交、已取消的订单）

**参数：**
- `symbol`: 交易对
- `limit`: 返回数量（默认 100）
- `order_id`: 可选，指定订单 ID 直接查询

**返回：** 历史订单列表

**示例：**
```python
# 查询最近的历史订单
history = account.get_order_history(symbol="HYPE_USDC", limit=100)
# [
#   {'id': '123', 'status': 'Filled', ...},
#   {'id': '456', 'status': 'Cancelled', ...},
#   ...
# ]

# 直接查询指定订单（推荐）⭐
history = account.get_order_history(symbol="HYPE_USDC", order_id="16598636798")
# [{'id': '16598636798', 'status': 'Filled', ...}]
```

### 4. `get_fill_history(symbol, limit=1000, fill_type="User")`
**用途：** 查询成交记录

**返回：** 成交记录列表

## 🔧 解决方案

### 改进后的 `get_order()` 方法

```python
def get_order(self, symbol: str, orderId: str) -> Dict:
    """查询订单状态
    
    先查询未完成订单，如果不存在则直接查询历史订单
    """
    # 步骤 1：查询未完成订单
    order = self.account.get_open_order(symbol=symbol, order_id=orderId)
    
    if order and 'code' not in order:
        # 找到了，返回订单状态
        return convert_order(order)
    
    # 步骤 2：订单不在未完成列表中，直接查询历史订单
    if error_code in ['RESOURCE_NOT_FOUND', 'ORDER_NOT_FOUND']:
        # ⭐ 使用 order_id 参数直接查询，无需遍历
        history = self.account.get_order_history(symbol=symbol, order_id=orderId)
        
        if isinstance(history, list) and len(history) > 0:
            # 找到了！返回第一个（应该只有一个）
            return convert_order(history[0])
        
        # 历史订单中也没找到
        return {'status': 'NOT_FOUND', 'orderId': orderId}
    
    # 其他错误
    return None
```

## 📝 查询流程

```
查询订单 16598636798
    ↓
[1] 调用 get_open_order(symbol, order_id)
    ↓
    ├─ 找到 → 返回订单状态（New/Open）
    │
    └─ RESOURCE_NOT_FOUND
        ↓
    [2] 调用 get_order_history(symbol, order_id=16598636798) ⭐
        ↓
        ├─ 找到 → 返回订单状态（Filled/Cancelled）
        │
        └─ 未找到 → 返回 {'status': 'NOT_FOUND'}
```

**优化点：** 使用 `order_id` 参数直接查询，无需遍历 100 个订单，查询速度更快！

## 🎯 实际效果

### 修复前 ❌
```
🔍 [Backpack] [Order#16598636798] 查询订单状态...
❌ [Backpack] [Order#16598636798] 查询订单失败: RESOURCE_NOT_FOUND - Not Found
⚠️ [POLL] 无法查询订单 16598636798 状态，保留在 pending_buys 中
⏭️ [SKIP] 存在1笔待跟踪买单，跳过本次买单挂单  ← 永久阻塞
```

### 修复后 ✅
```
🔍 [Backpack] [Order#16598636798] 查询订单状态...
🔍 [Backpack] [Order#16598636798] 未完成订单中未找到，查询历史订单...
✅ [Backpack] [Order#16598636798] 在历史订单中找到，状态: Filled -> FILLED
📥 [Backpack] 下限价卖单: HYPE_USDC SELL 4.0 @ 43.816
✅ [Backpack] [Order#16598636799] 卖单下单成功
✅ [REST-FALLBACK] 买单 16598636798 成交，自动挂卖单 16598636799 @ 43.816
```

## 📊 订单状态对照表

| Backpack 状态 | 在哪里能查到 | 统一状态 | 说明 |
|--------------|------------|---------|------|
| `New` | get_open_order | `NEW` | 新订单，未完成 |
| `Open` | get_open_order | `NEW` | 挂单中，未完成 |
| `PartiallyFilled` | get_open_order | `PARTIALLY_FILLED` | 部分成交 |
| `Filled` | get_order_history | `FILLED` | 已成交 ⭐ |
| `Cancelled` | get_order_history | `CANCELED` | 已取消 |
| `Expired` | get_order_history | `EXPIRED` | 已过期 |

## 💡 关键要点

1. **`get_open_order()` 不返回已成交订单**
   - 这是 Backpack API 的设计，不是 bug

2. **必须查询历史订单**
   - 使用 `get_order_history()` 获取已成交/已取消的订单

3. **限制历史查询范围**
   - `limit=100` 足够覆盖最近的订单
   - 避免查询过多数据影响性能

4. **区分"不存在"和"网络错误"**
   - 订单不存在 → 返回 `{'status': 'NOT_FOUND'}`
   - 网络错误 → 返回 `None`

## 🔗 相关文档

- `FIX_ORDER_NOT_FOUND.md` - 完整修复说明
- `BACKPACK_ORDER_STATUS.md` - 订单状态说明
- `examples/bpx-py/account_examples.py` - Backpack SDK 示例

## 更新日期
2025-11-01
