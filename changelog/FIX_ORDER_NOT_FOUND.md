# 修复：订单成交后未挂卖单问题

## 问题描述

**症状：**
- 买单成交了，但没有自动挂卖单
- 日志显示：`❌ [REPRICE ERR] 订单 XXX 替换价格错误: Order not found`
- 程序一直显示：`⏭️ [SKIP] 存在1笔未完成买单，跳过本次买单挂单`

**根本原因：**
Backpack 的 `get_open_orders()` API 可能返回已成交或已取消的订单，导致：
1. 程序认为订单还未完成，尝试改价
2. 改价时发现订单不存在（Order not found）
3. 程序认为还有未完成买单，跳过新买单
4. **已成交的买单没有触发挂卖单逻辑**

## 修复内容

### 1. 过滤非 Open 状态的订单 ✅

**文件：** `exchanges/backpack_adapter.py`

**位置：** `get_open_orders()` 方法，第248-252行

**修改：**
```python
# ⚠️ 关键修复：只处理 Open 状态的订单，过滤已成交/已取消的订单
order_status = order.get('status')
if order_status != 'Open':
    print(f"[{datetime.now().isoformat()}] ⏭️ [Backpack] 订单 {i} 状态为 {order_status}，跳过（非 Open 状态）")
    continue
```

**效果：**
- 只返回真正未完成的订单（状态为 `Open`）
- 已成交（`Filled`）或已取消（`Cancelled`）的订单不会被返回
- 避免尝试改价不存在的订单

### 2. 改价失败时清理 pending_buys ✅

**文件：** `trading.py`

**位置：** 第321-325行

**修改：**
```python
except Exception as e:
    print(f"[{datetime.now().isoformat()}] {log_prefix} ❌ [REPRICE ERR] 订单 {order['orderId']} 外层错误: {e}")
    # 外层错误也需要从pending_buys中移除以避免永久阻塞
    bot_data['pending_buys'] = [p for p in bot_data.get('pending_buys', []) if p['order_id'] != str(order['orderId'])]
    update_order_status(str(order['orderId']), 'FAILED')
```

**效果：**
- 改价失败时，从 `pending_buys` 中移除该订单
- 避免订单永久阻塞交易循环
- 允许程序继续下新买单

## 修复后的行为

### 正常流程：
```
1. 买单下单成功 → 加入 pending_buys
2. 买单成交 → REST 轮询检测到
3. 自动挂卖单 → 从 pending_buys 移除
4. 继续下一轮交易
```

### 异常处理：
```
1. get_open_orders() 返回已成交订单
   → ✅ 现在会被过滤掉，不会进入改价流程

2. 改价时订单不存在
   → ✅ 从 pending_buys 移除，避免阻塞

3. 买单成交但卖单下单失败
   → ✅ 保留在 pending_buys，下次循环重试
```

## 验证方法

### 1. 查看日志
修复后应该看到：
```
[2025-11-01T...] ⏭️ [Backpack] 订单 0 状态为 Filled，跳过（非 Open 状态）
[2025-11-01T...] ✅ [Backpack] 找到 0 个未完成订单
[2025-11-01T...] ✅ [CHECK] 未发现交易所未完成订单。
```

而不是：
```
[2025-11-01T...] 🔁 [REPRICE] 检测到 1 笔未完成买单 (ID: XXX)
[2025-11-01T...] ❌ [REPRICE ERR] 订单 XXX 替换价格错误: Order not found
```

### 2. 测试场景
1. **正常成交：** 买单成交 → 自动挂卖单 ✅
2. **改价失败：** 订单不存在 → 从 pending_buys 移除 → 继续交易 ✅
3. **卖单失败：** 保留在 pending_buys → 下次重试 ✅

## 相关文件

- `exchanges/backpack_adapter.py` - Backpack 适配器
- `trading.py` - 交易主循环
- `analyze_logs.py` - 日志分析工具
- `quick_check.md` - 排查指南

## 注意事项

### Backpack 特性
- Backpack 不支持 WebSocket，使用 REST 轮询（默认 1 秒）
- `get_open_orders()` 可能返回非 Open 状态的订单（API 特性）
- 需要显式过滤订单状态

### 监控建议
1. 定期检查 `pending_buys` 是否有积压
2. 关注 `[REPRICE ERR]` 和 `[SELL ERR]` 日志
3. 使用 `analyze_logs.py` 工具分析交易流程

## 更新日期
2025-11-01

## 相关问题
- 挂单成交但未挂卖单
- Order not found 错误
- pending_buys 永久阻塞
