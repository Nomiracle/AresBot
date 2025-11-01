# 日志格式说明

## 📋 日志前缀规范

所有日志都包含订单ID前缀，方便追踪和定位问题。

### 格式
```
[时间戳] [emoji] [组件] [Order#订单ID] 消息内容
```

### 示例
```
[2025-11-01T04:40:37.396982] 🔍 [Backpack] [Order#16583188603] 处理订单
[2025-11-01T04:40:37.397431] ⏭️ [Backpack] [Order#16583188603] 状态为 New，跳过（非未完成状态）
[2025-11-01T04:40:38.123456] ✅ [Backpack] [Order#16583188604] 买单下单成功
```

## 🎯 订单ID前缀

### Backpack 适配器

#### get_open_orders() - 获取未完成订单
```
🔍 [Backpack] [Order#123456] 处理订单
🔍 [Backpack] [Order#123456] 字段: ['id', 'symbol', 'status', ...]
⏭️ [Backpack] [Order#123456] 状态为 Filled，跳过（非未完成状态）
✅ [Backpack] [Order#123456] 转换完成: Bid 4.0 @ 43.598
✅ [Backpack] 找到 2 个未完成订单: [123456, 123457]
```

#### get_order() - 查询订单状态
```
🔍 [Backpack] [Order#123456] 查询订单状态...
✅ [Backpack] [Order#123456] 状态: Filled -> FILLED
⚠️ [Backpack] [Order#123456] 未找到订单
❌ [Backpack] [Order#123456] 查询失败: Connection timeout
```

#### order_limit_buy() - 限价买单
```
📤 [Backpack] 下限价买单: HYPE_USDC BUY 4.0 @ 43.598
✅ [Backpack] [Order#123456] 买单下单成功
⚠️ [Backpack] [Order#?] 无法提取订单ID，响应字段: ['status', 'message']
```

#### order_limit_sell() - 限价卖单
```
📤 [Backpack] 下限价卖单: HYPE_USDC SELL 4.0 @ 43.816
✅ [Backpack] [Order#123457] 卖单下单成功
```

#### cancel_order() - 取消订单
```
🗑️ [Backpack] [Order#123456] 取消订单...
✅ [Backpack] [Order#123456] 订单已取消
❌ [Backpack] [Order#123456] 取消失败: Order not found
```

### Trading 主循环

#### 订单改价
```
🔁 [REPRICE] 检测到 1 笔未完成买单 (ID: 123456)
⏭️ [REPRICE SKIP] 订单 123456 当前价格 43.598 与目标价格 43.598 一致，跳过替换
✅ [REPRICE] 订单 123456 已替换为新价格 43.600，新订单ID=123458
❌ [REPRICE ERR] 订单 123456 替换价格错误: Order not found
```

#### 买单成交处理
```
✅ [WS] 买单 123456 成交，自动挂卖单 123457 @ 43.816
✅ [REST-FALLBACK] 买单 123456 成交，自动挂卖单 123457 @ 43.816
❌ [WS SELL ERR] 卖单下单错误: Insufficient funds
⚠️ [WS] 买单 123456 已成交但卖单下单失败，保留在 pending_buys 中等待重试
```

## 📊 Emoji 图例

| Emoji | 含义 | 使用场景 |
|-------|------|---------|
| 🔍 | 查询/检查 | 查询订单、检查状态 |
| ✅ | 成功 | 操作成功完成 |
| ❌ | 失败 | 操作失败、错误 |
| ⚠️ | 警告 | 需要注意的情况 |
| ⏭️ | 跳过 | 跳过某个操作 |
| 📤 | 发送 | 下买单 |
| 📥 | 接收 | 下卖单 |
| 🗑️ | 删除 | 取消订单 |
| 🔄 | 循环/刷新 | 获取最新价格 |
| 🔁 | 重试/改价 | 订单改价 |
| 💰 | 价格 | 价格相关信息 |
| 📋 | 详情 | 详细信息、堆栈 |
| 💡 | 提示 | 建议、提示 |
| 🎯 | 目标 | 目标价格、规则 |

## 🔍 日志搜索技巧

### 按订单ID搜索
```powershell
# PowerShell
Select-String -Path logs.txt -Pattern "\[Order#123456\]"

# Bash/Linux
grep "\[Order#123456\]" logs.txt
```

### 搜索特定操作
```powershell
# 搜索所有买单
Select-String -Path logs.txt -Pattern "买单"

# 搜索所有错误
Select-String -Path logs.txt -Pattern "❌"

# 搜索订单改价
Select-String -Path logs.txt -Pattern "REPRICE"
```

### 追踪订单生命周期
```powershell
# 追踪订单从下单到成交的完整流程
Select-String -Path logs.txt -Pattern "\[Order#123456\]" | Select-Object -First 20
```

## 📝 日志分析示例

### 示例 1：正常交易流程
```
[04:40:35] 📤 [Backpack] 下限价买单: HYPE_USDC BUY 4.0 @ 43.598
[04:40:35] ✅ [Backpack] [Order#16583188603] 买单下单成功
[04:40:37] 🔍 [Backpack] [Order#16583188603] 处理订单
[04:40:37] ✅ [Backpack] [Order#16583188603] 转换完成: Bid 4.0 @ 43.598
[04:41:20] 🔍 [Backpack] [Order#16583188603] 查询订单状态...
[04:41:20] ✅ [Backpack] [Order#16583188603] 状态: Filled -> FILLED
[04:41:20] 📥 [Backpack] 下限价卖单: HYPE_USDC SELL 4.0 @ 43.816
[04:41:20] ✅ [Backpack] [Order#16583188604] 卖单下单成功
[04:41:20] ✅ [REST-FALLBACK] 买单 16583188603 成交，自动挂卖单 16583188604 @ 43.816
```

### 示例 2：订单改价
```
[04:40:35] 📤 [Backpack] 下限价买单: HYPE_USDC BUY 4.0 @ 43.598
[04:40:35] ✅ [Backpack] [Order#16583188603] 买单下单成功
[04:40:37] 🔍 [Backpack] [Order#16583188603] 处理订单
[04:40:37] 🔁 [REPRICE] 检测到 1 笔未完成买单 (ID: 16583188603)
[04:40:37] 🗑️ [Backpack] [Order#16583188603] 取消订单...
[04:40:37] ✅ [Backpack] [Order#16583188603] 订单已取消
[04:40:38] 📤 [Backpack] 下限价买单: HYPE_USDC BUY 4.0 @ 43.600
[04:40:38] ✅ [Backpack] [Order#16583188605] 买单下单成功
[04:40:38] ✅ [REPRICE] 订单 16583188603 已替换为新价格 43.600，新订单ID=16583188605
```

### 示例 3：错误处理
```
[04:40:35] 📤 [Backpack] 下限价买单: HYPE_USDC BUY 4.0 @ 43.598
[04:40:35] ✅ [Backpack] [Order#16583188603] 买单下单成功
[04:40:37] 🔁 [REPRICE] 检测到 1 笔未完成买单 (ID: 16583188603)
[04:40:37] 🗑️ [Backpack] [Order#16583188603] 取消订单...
[04:40:37] ❌ [Backpack] [Order#16583188603] 取消失败: Order not found
[04:40:37] ❌ [REPRICE ERR] 订单 16583188603 替换价格错误: Order not found
```

## 💡 最佳实践

### 1. 使用订单ID追踪
始终通过订单ID追踪订单的完整生命周期：
- 下单 → 挂单 → 改价 → 成交 → 挂卖单

### 2. 关注关键日志
重点关注这些日志：
- `❌` 错误日志
- `⚠️` 警告日志
- `[REPRICE ERR]` 改价失败
- `[SELL ERR]` 卖单失败

### 3. 定期分析
使用 `analyze_logs.py` 工具定期分析日志：
```powershell
python analyze_logs.py logs.txt
```

### 4. 保存历史日志
建议每天保存日志文件：
```powershell
# 按日期命名
python app.py > logs_2025-11-01.txt 2>&1
```

## 🔗 相关文档

- `analyze_logs.py` - 日志分析工具
- `FIX_ORDER_NOT_FOUND.md` - 订单问题修复
- `BACKPACK_ORDER_STATUS.md` - Backpack 订单状态说明
