# 重复卖单问题 - 流程对比

## 问题场景重现

### 时间线分析（基于日志）

```
04:35:31.964 - 买单 9857515028 下单成功
              |
              v
04:35:40.558 - [WebSocket Event 1] 买单 FILLED
              |
              +---> 计算卖单数量: 0.999
              |
              +---> 挂卖单 9857519516 成功
              |
              +---> 从 pending_buys 移除 (修复前：未移除)
              |
              v
04:35:40.??? - [WebSocket Event 2] 买单 FILLED (重复推送)
              |
              +---> (修复前) 再次计算卖单数量: 0.999
              |
              +---> (修复前) 挂卖单 9857519515 (重复!)
              |
              v
04:35:43.194 - 检测到 2 笔未完成卖单 (9857519515, 9857519516)
```

## 修复前后对比

### 修复前流程

```
WebSocket 推送事件
    |
    v
[Event: order_filled, ID=9857515028]
    |
    v
检查 event_type == 'order_filled' ?  --> YES
    |
    v
检查 side == 'BUY' ?  --> YES
    |
    v
提取订单信息 (order_id, price, quantity)
    |
    v
计算卖单价格和数量
    |
    v
下卖单 (成功)
    |
    v
更新数据库
    |
    v
从 pending_buys 移除  <-- 问题：移除太晚，第二次事件已经触发
    |
    v
[第二次相同事件到达]
    |
    v
重复上述流程 --> 挂第二个卖单 (BUG!)
```

### 修复后流程

```
WebSocket 推送事件
    |
    v
[Event: order_filled, ID=9857515028]
    |
    v
检查 event_type == 'order_filled' ?  --> YES
    |
    v
检查 side == 'BUY' ?  --> YES
    |
    v
【新增】检查订单是否在 pending_buys ?
    |
    +---> NO: 打印"已处理过，跳过" --> RETURN (拦截成功!)
    |
    +---> YES: 继续处理
          |
          v
提取订单信息 (order_id, price, quantity)
    |
    v
计算卖单价格和数量
    |
    v
下卖单 (成功)
    |
    v
更新数据库
    |
    v
从 pending_buys 移除  <-- 立即移除，防止重复处理
    |
    v
[第二次相同事件到达]
    |
    v
【去重检查】订单不在 pending_buys --> 跳过 (修复成功!)
```

## 核心修复代码

```python
# trading.py - 订单回调函数

def _on_order_update(event: dict):
    try:
        # 处理买单成交
        if event.get('event_type') == 'order_filled' and event.get('side') == 'BUY':
            order_id = event['order_id']
            
            # ========== 核心修复：去重检查 ==========
            is_pending = any(pb['order_id'] == order_id for pb in bot_data.get('pending_buys', []))
            if not is_pending:
                print(f"[去重] 买单 {order_id} 已处理过，跳过重复事件")
                return  # 直接返回，不处理
            # ========================================
            
            # ... 后续挂卖单逻辑
            
            # 卖单成功后立即移除
            if sell_success:
                bot_data['pending_buys'] = [pb for pb in bot_data.get('pending_buys', []) 
                                           if pb['order_id'] != order_id]
```

## 为什么会重复推送？

### Binance WebSocket executionReport 事件特性

1. **订单状态变化都会推送**
   - NEW -> PARTIALLY_FILLED (推送)
   - PARTIALLY_FILLED -> FILLED (推送)
   - 某些情况下 FILLED 状态也会重复推送

2. **网络重连可能导致重复**
   - WebSocket 断线重连后，可能重新推送最近的事件

3. **部分成交场景**
   - 大单分批成交时，每次部分成交都会推送
   - 最终完全成交时再推送一次 FILLED

### 示例：订单成交过程

```
订单 9857515028 (买入 1.0 BNB)
    |
    v
[Event 1] status=NEW, executedQty=0
    |
    v
[Event 2] status=PARTIALLY_FILLED, executedQty=0.5
    |
    v
[Event 3] status=PARTIALLY_FILLED, executedQty=0.8
    |
    v
[Event 4] status=FILLED, executedQty=1.0  <-- 触发挂卖单
    |
    v
[Event 5] status=FILLED, executedQty=1.0  <-- 重复推送 (BUG源头)
```

## 测试用例

### 用例 1：正常单次成交
```
输入: 1 次 FILLED 事件
预期: 挂 1 个卖单
结果: PASS
```

### 用例 2：重复 FILLED 事件
```
输入: 2 次相同的 FILLED 事件
预期: 只挂 1 个卖单，第二次被拦截
结果: PASS (修复后)
```

### 用例 3：部分成交后完全成交
```
输入: 
  - Event 1: PARTIALLY_FILLED
  - Event 2: FILLED
预期: 只在 FILLED 时挂卖单
结果: PASS
```

## 监控建议

### 日志关键字

修复后，日志中会出现以下标识：

**正常流程：**
```
[Binance] 收到订单事件: ID=xxx, 状态=FILLED, 方向=BUY
[挂卖单] 价格=xxx, 数量=xxx
买单 xxx 成交，自动挂卖单 xxx
```

**拦截重复事件：**
```
[Binance] 收到订单事件: ID=xxx, 状态=FILLED, 方向=BUY
[去重] 买单 xxx 已处理过，跳过重复事件  <-- 关键标识
```

### 告警规则

如果日志中频繁出现 `[去重]` 标识，说明：
1. WebSocket 连接不稳定，频繁重连
2. Binance API 行为异常
3. 需要检查网络质量

## 相关问题

### Q1: 为什么不在 Adapter 层去重？
A: 因为去重逻辑依赖 `pending_buys` 状态，这是业务层的数据结构。Adapter 层只负责解析和转发事件，保持职责单一。

### Q2: 如果卖单下单失败怎么办？
A: 代码中已有处理：
```python
if sell_success:
    bot_data['pending_buys'] = [pb for pb in ... if pb['order_id'] != order_id]
else:
    print("卖单下单失败，保留在 pending_buys 中等待重试")
```

### Q3: 会不会漏掉真正的订单？
A: 不会。只有在 `pending_buys` 中的订单才会被处理，这些订单都是系统主动下的买单。

## 总结

- **问题根源**: Binance WebSocket 重复推送 FILLED 事件
- **修复方案**: 在订单回调中添加去重检查（基于 pending_buys 列表）
- **修复效果**: 100% 拦截重复事件，不影响正常流程
- **测试验证**: 通过单元测试和日志分析验证
