# Trading.py 五大问题修复总结

## 修复概览

| 问题 | 严重性 | 状态 | 修复位置 |
|------|--------|------|---------|
| 1. 改价后 order_id 不匹配 | 🔴 高 | ✅ 已修复 | 第 255-273, 304-321 行 |
| 2. REST 模式卖单失败丢失 pending_buy | 🔴 高 | ✅ 已修复 | 第 416-440 行 |
| 3. WS 模式卖单失败丢失 pending_buy | 🔴 高 | ✅ 已修复 | 第 115-138 行 |
| 4. 改价后订单不在数据库 | 🟡 中 | ✅ 已修复 | 第 269-271, 317-319 行 |
| 5. 重启后 pending_buys 丢失 | 🟡 中 | ✅ 已修复 | 第 221-233 行 |

---

## 问题 1：改价后 order_id 不匹配

### 原问题
改价成功后无条件更新 `pending_buys`，但如果改价失败或响应异常，`pending_buys` 中的 `order_id` 与实际订单不匹配，导致买单成交时找不到记录，无法挂卖单。

### 修复方案
```python
# 只有成功提取到新订单ID才更新 pending_buys
if new_order_id and new_order_id != str(order['orderId']):
    # 更新 pending_buys
    # 更新数据库：标记旧订单为 REPLACED，插入新订单
    update_order_status(str(order['orderId']), 'REPLACED')
    insert_order(user_id, config['symbol'], buy_price_str, str(aligned_quantity),
                'BUY', 'PLACED', new_order_id)
else:
    print("⚠️ 未获取到新订单ID，不更新 pending_buys")
```

### 效果
- ✅ 改价失败时保持 `pending_buys` 一致性
- ✅ 买单成交时能正确匹配并挂卖单
- ✅ 数据库记录完整（同时解决问题 4）

---

## 问题 2：REST 回退模式卖单失败后丢失 pending_buy

### 原问题
```python
if status == 'FILLED':
    try:
        # 下卖单
    except:
        print("错误")
        # ⚠️ 没有 remaining.append(pb)
else:
    remaining.append(pb)

bot_data['pending_buys'] = remaining  # pb 被丢弃！
```

### 修复方案
```python
if status == 'FILLED':
    sell_success = False
    try:
        # 下卖单
        sell_success = True
    except:
        print("错误，将保留 pending_buy 以便重试")
    
    # 只有卖单成功才移除，失败则保留
    if not sell_success:
        remaining.append(pb)
        print("⚠️ 买单已成交但卖单下单失败，保留在 pending_buys 中等待重试")
else:
    remaining.append(pb)
```

### 效果
- ✅ 卖单下单失败时保留 `pending_buy`
- ✅ 下次循环自动重试挂卖单
- ✅ 避免持仓被锁定

---

## 问题 3：WebSocket 模式卖单失败后丢失 pending_buy

### 原问题
```python
try:
    # 下卖单
except:
    print("错误")

# 无论成功失败都移除
bot_data['pending_buys'] = [pb for pb in ... if pb['order_id'] != order_id]
```

### 修复方案
```python
sell_success = False
try:
    # 下卖单
    sell_success = True
except:
    print("错误，将保留 pending_buy 以便重试")

# 只有卖单成功才移除
if sell_success:
    bot_data['pending_buys'] = [pb for pb in ... if pb['order_id'] != order_id]
else:
    print("⚠️ 买单已成交但卖单下单失败，保留在 pending_buys 中等待重试")
```

### 效果
- ✅ WS 模式下卖单失败时保留 `pending_buy`
- ✅ REST 回退轮询会检测到并重试挂卖单
- ✅ 双重保障，确保不丢失成交订单

---

## 问题 4：改价后的新订单不在数据库中

### 原问题
改价成功后只更新内存中的 `pending_buys`，但没有写入数据库，导致：
- 数据库中找不到新订单 ID
- `update_order_status(new_order_id, 'FILLED')` 失败
- 无法追踪订单历史

### 修复方案
```python
if new_order_id and new_order_id != str(order['orderId']):
    # 更新 pending_buys
    ...
    
    # 更新数据库：标记旧订单为已替换，插入新订单
    update_order_status(str(order['orderId']), 'REPLACED')
    insert_order(user_id, config['symbol'], buy_price_str, str(aligned_quantity),
                'BUY', 'PLACED', new_order_id)
```

### 效果
- ✅ 改价后新订单写入数据库
- ✅ 旧订单标记为 `REPLACED` 状态
- ✅ 订单历史完整可追溯

---

## 问题 5：机器人重启后 pending_buys 丢失

### 原问题
`pending_buys` 存储在内存中，机器人重启后丢失，导致：
- 已有未完成买单但 `pending_buys` 为空
- 买单成交时 WS 回调找不到记录
- 无法获取买价，不挂卖单

### 修复方案
```python
# 在主循环开始时添加恢复逻辑
pending_buys_recovered = False

while bot_data.get('running'):
    open_orders = client.get_open_orders(symbol=config['symbol'])
    
    if open_orders:
        open_buy_orders = [o for o in open_orders if o['side'] == 'BUY']
        
        # 机器人启动时恢复 pending_buys
        if not pending_buys_recovered and not bot_data.get('pending_buys', []) and open_buy_orders:
            print(f"🔄 [RECOVER] 检测到 {len(open_buy_orders)} 笔未完成买单，正在恢复到 pending_buys...")
            for order in open_buy_orders:
                bot_data.setdefault('pending_buys', []).append({
                    'order_id': str(order['orderId']),
                    'price': float(order['price']),
                    'quantity': float(order['origQty']),
                    'symbol': config['symbol'],
                    'user_id': user_id
                })
            print(f"✅ [RECOVER] 已恢复 {len(open_buy_orders)} 笔买单到 pending_buys")
            pending_buys_recovered = True
```

### 效果
- ✅ 机器人重启后自动恢复 `pending_buys`
- ✅ 已有买单成交时能正常挂卖单
- ✅ 无缝恢复运行状态

---

## 测试场景

### 场景 1：改价失败
**预期行为**：
```
🔁 [REPRICE] 检测到 1 笔未完成买单 (ID: 123)，尝试直接替换为新价格 1089.00。
❌ [REPRICE ERR] 订单 123 替换价格异常: ...
⏭️ [SKIP] 存在未完成订单或待跟踪买单，跳过本次买单挂单。
```
- `pending_buys` 中 `order_id` 仍为 `123`
- 买单成交时能正确匹配并挂卖单

### 场景 2：卖单下单失败（WS 模式）
**预期行为**：
```
✅ [WS] 买单 123 成交，自动挂卖单 ...
❌ [WS SELL ERR] 卖单下单异常: ...，将保留 pending_buy 以便重试
⚠️ [WS] 买单 123 已成交但卖单下单失败，保留在 pending_buys 中等待重试
```
- `pending_buy` 保留在列表中
- REST 回退轮询检测到并重试挂卖单

### 场景 3：卖单下单失败（REST 模式）
**预期行为**：
```
❌ [SELL ERR] 卖单下单异常: ...，将保留 pending_buy 以便重试
⚠️ [REST-FALLBACK] 买单 123 已成交但卖单下单失败，保留在 pending_buys 中等待重试
```
- 下次循环继续检测该 `pending_buy`
- 直到卖单成功才移除

### 场景 4：改价成功
**预期行为**：
```
🔁 [REPRICE] 检测到 1 笔未完成买单 (ID: 123)，尝试直接替换为新价格 1089.00。
✅ [REPRICE] 订单 123 已替换为新价格 1089.00，新订单ID=456
```
- 数据库中订单 `123` 状态更新为 `REPLACED`
- 数据库中插入新订单 `456`，状态为 `PLACED`
- `pending_buys` 中 `order_id` 更新为 `456`

### 场景 5：机器人重启
**预期行为**：
```
▶️ 交易循环已启动 (user=admin, symbol=BNBUSDT)
🔄 [RECOVER] 检测到 1 笔未完成买单，正在恢复到 pending_buys...
✅ [RECOVER] 已恢复 1 笔买单到 pending_buys
```
- 重启后自动恢复已有订单
- 买单成交时能正常挂卖单

---

## 关键改进点总结

1. **原子性保障**：只有操作成功才更新状态
2. **失败重试机制**：卖单失败时保留 `pending_buy` 等待重试
3. **数据一致性**：内存状态与数据库状态同步
4. **状态恢复**：机器人重启后自动恢复运行状态
5. **详细日志**：每个关键步骤都有清晰的日志输出

---

## 升级建议

### 立即测试
1. 启动机器人，观察日志输出
2. 手动触发各种异常场景（网络断开、余额不足等）
3. 验证 `pending_buys` 是否正确保留和恢复

### 后续优化
1. **持久化 pending_buys**：写入数据库或文件，避免依赖内存
2. **重试次数限制**：卖单失败后限制重试次数，避免无限循环
3. **告警机制**：卖单连续失败时发送通知
4. **订单状态同步**：定期从交易所同步订单状态，确保一致性

---

## 修复完成时间
2025-10-30 15:50 UTC+08:00

## 修复人员
Cascade AI Assistant
