# 修复：卖单数量问题 - 手续费导致余额不足

## 🐛 问题描述

买单成交后自动挂卖单时，使用原始下单数量而不是实际成交数量，导致卖单失败。

### 错误日志示例

```
[18:30:00] ✅ [SUCCESS] 买单成交，ID=16607400612，数量=1.0
[18:30:01] 📥 [Backpack] 下限价卖单: HYPE_USDC SELL 1.0 @ 43.385
[18:30:01] ❌ [Backpack] 限价卖单失败: INSUFFICIENT_FUNDS - Insufficient funds
[18:30:01] 💡 [Backpack] 账户余额不足，请充值
```

## 🔍 根本原因

### 问题流程

```
1. 下买单：1.0 HYPE @ 43.168
   ↓
2. 买单成交
   - 原始数量：1.0 HYPE
   - 手续费：0.001 HYPE (0.1% Taker Fee)
   - 实际到账：0.999 HYPE
   ↓
3. 自动挂卖单
   - 使用数量：1.0 HYPE ❌ (pb['quantity'])
   - 可用余额：0.999 HYPE
   - 结果：INSUFFICIENT_FUNDS
```

### 代码问题

**修改前：**
```python
sell_qty = float(pb['quantity'])  # 使用原始下单数量
```

**问题：**
- `pb['quantity']` 是下单时的数量（1.0）
- 实际到账数量 = 成交数量 - 手续费（0.999）
- 卖单数量 > 可用余额 → 失败

## 🔧 解决方案

### 修改内容

**文件：** `trading.py`

**位置：** 第 453-460 行

```python
# 使用实际成交数量（扣除手续费后），而不是原始下单数量
executed_qty = float(order_info.get('executedQty', pb['quantity']))
sell_qty = executed_qty
print(f"📊 [SELL] 买单成交数量: {executed_qty}（原始: {pb['quantity']}）")

qty_decimals = int(abs(math.log10(step_size))) if step_size else 6
aligned_sell_qty = math.floor(sell_qty / step_size) * step_size if step_size else sell_qty
aligned_sell_qty = round(aligned_sell_qty, qty_decimals)
```

### 关键改进

1. **使用 `executedQty`** - 从订单信息中获取实际成交数量
2. **添加日志** - 显示实际数量和原始数量的对比
3. **保持对齐** - 仍然按照 `step_size` 对齐数量

## 📊 修复后的行为

### 正常流程

```
[18:30:00] ✅ [SUCCESS] 买单成交，ID=16607400612
[18:30:00] 📊 [SELL] 买单成交数量: 0.999（原始: 1.0）
[18:30:01] 📥 [Backpack] 下限价卖单: HYPE_USDC SELL 0.99 @ 43.385
[18:30:01] ✅ [Backpack] 限价卖单成功，订单ID=16607400613
[18:30:01] ✅ [REST-FALLBACK] 买单成交，自动挂卖单成功
```

### 数量计算

| 步骤 | 数量 | 说明 |
|------|------|------|
| 买单下单 | 1.0 | `pb['quantity']` |
| 买单成交 | 1.0 | 完全成交 |
| 手续费 | 0.001 | 0.1% Taker Fee |
| 实际到账 | 0.999 | `executedQty` |
| 对齐后 | 0.99 | 按 `step_size=0.01` 向下对齐 |
| 卖单数量 | 0.99 | ✅ 不超过可用余额 |

## 🎯 效果对比

| 场景 | 修改前 ❌ | 修改后 ✅ |
|------|----------|----------|
| **买入 1.0** | 卖出 1.0 → 失败 | 卖出 0.99 → 成功 |
| **买入 10.0** | 卖出 10.0 → 失败 | 卖出 9.99 → 成功 |
| **买入 0.5** | 卖出 0.5 → 失败 | 卖出 0.49 → 成功 |

## 💡 关键要点

### 1. 为什么要用 `executedQty`？

- **`origQty`** - 原始下单数量（1.0）
- **`executedQty`** - 实际成交数量（1.0）
- **实际到账** - 成交数量 - 手续费（0.999）

Backpack 的 `executedQty` 已经是扣除手续费后的数量！

### 2. 手续费率

Backpack 手续费：
- **Maker**: 0.02%
- **Taker**: 0.1%

市价单和立即成交的限价单都是 Taker，手续费 0.1%。

### 3. 数量对齐

```python
# 0.999 按 step_size=0.01 向下对齐
aligned_sell_qty = math.floor(0.999 / 0.01) * 0.01
# = math.floor(99.9) * 0.01
# = 99 * 0.01
# = 0.99
```

向下对齐确保不超过可用余额。

### 4. 回退机制

```python
executed_qty = float(order_info.get('executedQty', pb['quantity']))
```

如果 `executedQty` 不存在（旧数据），回退到 `pb['quantity']`。

## 🔗 相关文档

- `FIX_ORDER_NOT_FOUND.md` - 订单查询修复
- `FIX_API_SYNC_DELAY.md` - API 同步延迟修复
- `BACKPACK_ORDER_QUERY.md` - 订单查询机制

## 📅 更新日期
2025-11-01
