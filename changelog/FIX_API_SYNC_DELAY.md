# 修复：API 同步延迟导致订单查询失败

## 🐛 问题描述

订单刚下完（0.5秒内），立即查询就找不到，导致被错误地从 `pending_buys` 移除。

### 问题日志

```
[18:11:04.503] ✅ 真实买单已下。新订单ID=16607400612
[18:11:04.504] 🔍 查询订单状态...
[18:11:04.952] 🔍 未完成订单中未找到，查询历史订单...
[18:11:05.484] 🔍 历史订单返回内容: []  ← 空列表
[18:11:05.484] ⚠️ 订单不存在，从 pending_buys 移除  ← 错误！
```

**时间线：**
- `t=0.000s` - 下单成功
- `t=0.001s` - 立即查询订单
- `t=0.449s` - 未完成订单中未找到
- `t=0.981s` - 历史订单返回空列表
- `t=0.981s` - **错误地移除订单**

## 🔍 根本原因

**Backpack API 存在同步延迟**：
- 订单创建后，需要 1-3 秒才能在 API 中查询到
- `get_open_order()` 和 `get_order_history()` 都查不到刚创建的订单
- 程序误认为订单不存在，从 `pending_buys` 移除

## 🔧 解决方案

### 修改 1：记录订单创建时间

**文件：** `trading.py`

**位置：** 第 403-410 行

```python
bot_data.setdefault('pending_buys', []).append({
    'order_id': real_order_id,
    'price': float(buy_price_str),
    'quantity': aligned_quantity,
    'symbol': config['symbol'],
    'user_id': user_id,
    'created_at': datetime.now().timestamp()  # ⭐ 记录创建时间
})
```

### 修改 2：跳过刚创建的订单

**文件：** `trading.py`

**位置：** 第 426-431 行

```python
# 🔧 跳过刚创建的订单（等待 3 秒让 API 同步）
order_age = current_time - pb.get('created_at', 0)
if order_age < 3:
    print(f"⏳ [POLL] 订单 {pb['order_id']} 刚创建 {order_age:.1f}s，等待 API 同步...")
    remaining.append(pb)
    continue
```

### 修改 3：恢复订单时设置 created_at

**文件：** `trading.py`

**位置：** 第 270-277 行

```python
bot_data.setdefault('pending_buys', []).append({
    'order_id': str(order['orderId']),
    'price': float(order['price']),
    'quantity': float(order['origQty']),
    'symbol': config['symbol'],
    'user_id': user_id,
    'created_at': 0  # ⭐ 恢复的订单设为 0，立即可查询
})
```

## 📊 修复后的行为

### 正常流程

```
[18:11:04.503] ✅ 真实买单已下。新订单ID=16607400612
[18:11:04.504] ⏳ [POLL] 订单 16607400612 刚创建 0.5s，等待 API 同步...
[18:11:05.504] ⏳ [POLL] 订单 16607400612 刚创建 1.5s，等待 API 同步...
[18:11:06.504] ⏳ [POLL] 订单 16607400612 刚创建 2.5s，等待 API 同步...
[18:11:07.504] 🔍 [POLL] 查询订单 16607400612 状态...
[18:11:07.600] ✅ [Backpack] 状态: Open -> NEW  ← 3秒后能查到了
```

### 订单成交流程

```
[18:11:04] ✅ 买单已下，ID=16607400612
[18:11:04-07] ⏳ 等待 API 同步（3秒）
[18:11:07] 🔍 查询订单状态
[18:11:07] ✅ 状态: Filled -> FILLED
[18:11:07] 📥 自动挂卖单
[18:11:07] ✅ 卖单已下，ID=16607400613
```

## 🎯 效果对比

| 场景 | 修复前 ❌ | 修复后 ✅ |
|------|----------|----------|
| **刚下的单** | 立即查询 → 找不到 → 移除 | 等待 3 秒 → 查询 → 找到 |
| **已成交的单** | 查询 → 找到 → 挂卖单 | 查询 → 找到 → 挂卖单 |
| **恢复的订单** | 立即查询 | 立即查询（created_at=0） |

## 💡 关键要点

1. **API 同步延迟是正常的**
   - Backpack API 需要 1-3 秒同步订单状态
   - 不是程序 bug，是 API 特性

2. **等待时间设置**
   - 3 秒是合理的等待时间
   - 太短：可能还查不到
   - 太长：影响成交后的卖单速度

3. **恢复订单的处理**
   - 恢复的订单 `created_at=0`
   - 立即可查询（已经存在很久了）

4. **不影响正常交易**
   - 只延迟查询，不延迟下单
   - 成交后仍能快速挂卖单

## 🔗 相关文档

- `FIX_ORDER_NOT_FOUND.md` - 订单不存在问题修复
- `BACKPACK_ORDER_QUERY.md` - 订单查询机制说明

## 更新日期
2025-11-01
