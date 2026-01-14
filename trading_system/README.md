# 动态网格套利交易系统 - 重构版 v2.0

## 📋 项目概述

这是对原有 `trading.py` 的架构级重构，从1270行的脚本式代码升级为工程化、可维护的交易系统。

**核心改进**：
- ✅ 状态清晰：使用状态机管理订单生命周期
- ✅ 边界清楚：严格分层，职责单一
- ✅ 可扩展：支持多策略、多交易所
- ✅ 可测试：业务逻辑与基础设施解耦
- ✅ 工程级质量：完整类型注解、文档字符串

## 🏗️ 架构分层

```
trading_system/
├── domain/              # 领域模型层
│   ├── order_state.py          # 订单状态枚举
│   ├── order_info.py           # 订单信息（不可变）
│   ├── order_metrics.py        # 订单指标
│   ├── order_state_machine.py  # 订单状态机
│   ├── order_manager.py        # 订单管理器
│   ├── market_state.py         # 市场状态
│   ├── runtime_state.py        # 运行时状态
│   ├── trading_config.py       # 交易配置（不可变）
│   └── trading_context.py      # 交易上下文（聚合根）
│
├── strategy/            # 策略层
│   ├── price_calculation_strategy.py  # 价格计算策略接口
│   └── grid_price_strategy.py         # 网格价格策略实现
│
├── commands/            # 命令层
│   ├── trading_command.py             # 命令接口
│   ├── place_buy_order_command.py     # 下买单命令
│   ├── place_sell_order_command.py    # 下卖单命令
│   ├── reprice_buy_order_command.py   # 改价买单命令
│   ├── reprice_sell_order_command.py  # 改价卖单命令
│   └── command_executor.py            # 命令执行器
│
├── services/            # 服务层
│   ├── notification_service.py        # 通知服务
│   ├── order_placement_service.py     # 订单下单服务
│   ├── order_repricing_service.py     # 订单改价服务
│   └── order_synchronizer.py          # 订单同步服务
│
├── infrastructure/      # 基础设施层
│   └── trading_event_bus.py           # 事件总线
│
├── orchestrator/        # 编排层
│   └── trading_loop_orchestrator.py   # 主循环编排器
│
├── factory.py           # 工厂类
└── api.py               # API接口（兼容原有接口）
```

## 🎯 设计模式应用

1. **状态模式**：`OrderStateMachine` 管理订单生命周期
2. **命令模式**：封装业务操作，支持回滚
3. **策略模式**：可插拔的价格计算策略
4. **观察者模式**：`TradingEventBus` 事件驱动
5. **工厂模式**：`TradingContextFactory` 创建对象
6. **聚合根模式**：`TradingContext` 统一入口

## 📦 核心组件

### 领域模型层

**TradingContext（聚合根）**
- 统一管理配置、市场状态、运行时状态、订单管理器
- 提供业务方法：`can_place_order()`, `needs_more_orders()`

**OrderStateMachine（状态机）**
- 管理订单状态转换：PENDING → PLACED → FILLED/CANCELLED
- 保证状态转换合法性

**OrderManager（订单管理器）**
- 集中管理所有订单状态机
- 提供查询、过滤、清理功能

### 命令层

**TradingCommand（命令接口）**
- 封装业务操作：`execute()`, `rollback()`, `validate()`
- 支持命令验证和回滚

**具体命令**
- `PlaceBuyOrderCommand`：下买单
- `PlaceSellOrderCommand`：下卖单
- `RepriceBuyOrderCommand`：改价买单
- `RepriceSellOrderCommand`：改价卖单

### 服务层

**OrderPlacementService**：批量下单服务
**OrderRepricingService**：改价服务
**OrderSynchronizer**：订单同步服务
**NotificationService**：异步通知服务

### 编排层

**TradingLoopOrchestrator**
- 协调所有组件完成交易逻辑
- 处理价格更新、订单成交等事件
- 管理主循环流程

## 🚀 使用示例

### 基本使用

```python
from trading_system.api import start_trading_bot, stop_trading_bot, get_bot_status

# 启动交易机器人
start_trading_bot(
    username="trader1",
    bot_key="BTCUSDT",
    exchange=exchange_adapter,
    config={
        'symbol': 'BTCUSDT',
        'exchange': 'binance',
        'quantity': 0.01,
        'interval': 1,
        'order_grid': 3,
        'offset_percent': -0.1,
        'sell_offset_percent': 0.5,
        'sell_decay_count': 5,
        'reprice_threshold_percent': 0.01
    }
)

# 获取状态
status = get_bot_status("trader1", "BTCUSDT")
print(f"运行状态: {status['running']}")
print(f"当前价格: {status['current_price']}")
print(f"待成交买单: {len(status['pending_buys'])}")

# 停止交易
stop_trading_bot("trader1", "BTCUSDT")
```

### 高级使用（直接使用组件）

```python
from trading_system.factory import TradingContextFactory
from trading_system.domain import TradingConfig

# 创建配置
config = TradingConfig(
    symbol="BTCUSDT",
    exchange="binance",
    quantity=0.01,
    interval=1,
    order_grid=3,
    offset_percent=-0.1,
    sell_offset_percent=0.5
)

# 创建上下文
context = TradingContext(
    username="trader1",
    user_id="uid123",
    config=config,
    exchange=exchange_adapter
)

# 创建编排器
orchestrator = TradingContextFactory.create_orchestrator(context)

# 运行
orchestrator.run()
```

## 🔄 与原系统对比

| 维度 | 原系统 | 新系统 | 改进 |
|------|--------|--------|------|
| **代码行数** | 1270行单文件 | ~800行多文件 | -37% |
| **函数参数** | 最多10个 | 最多3个 | -70% |
| **状态管理** | 字典散列 | 状态机集中 | ✅ 类型安全 |
| **并发控制** | 单锁 | 分层锁 | ✅ 细粒度 |
| **可测试性** | 困难 | 简单 | ✅ Mock友好 |
| **扩展性** | 修改原函数 | 新增类 | ✅ 开闭原则 |

## 🔮 扩展性

### 添加新策略

```python
from trading_system.strategy import PriceCalculationStrategy

class MartinStrategy(PriceCalculationStrategy):
    def calculate_buy_price(self, ...):
        # 马丁格尔策略实现
        pass
    
    def calculate_sell_price(self, ...):
        # 卖出价格计算
        pass
```

### 添加新命令

```python
from trading_system.commands import TradingCommand

class CancelAllOrdersCommand(TradingCommand):
    def execute(self):
        # 取消所有订单
        pass
```

### 添加新服务

```python
class RiskManagementService:
    def check_risk(self, context):
        # 风控检查
        pass
```

## 📝 语义一致性保证

重构严格保持了原有业务语义：

1. **订单流程**：买单成交 → 挂卖单 → 卖单成交（完全一致）
2. **改价逻辑**：网格计算、衰减逻辑、阈值判断（完全一致）
3. **状态同步**：WebSocket事件处理、订单恢复（完全一致）
4. **数据库操作**：订单记录、状态更新（完全一致）
5. **通知发送**：钉钉通知格式、异步执行（完全一致）

## ✅ 成功标准

- [x] 状态清晰：订单状态机明确管理生命周期
- [x] 边界清楚：严格分层，无跨层调用
- [x] 可扩展：策略、命令、服务可插拔
- [x] 可测试：业务逻辑与交易所解耦
- [x] 工程级质量：类型注解、文档字符串、异常处理

## 📚 技术栈

- Python 3.10+
- 类型注解（Type Hints）
- 数据类（Dataclasses）
- 线程安全（Threading Locks）
- 事件驱动（Event Bus）

## 🔧 维护指南

### 添加新功能
1. 确定功能所属层次
2. 创建对应的类/命令/服务
3. 在编排器中集成
4. 编写单元测试

### 调试技巧
- 使用 `context.get_log_prefix()` 统一日志前缀
- 检查状态机转换日志
- 查看事件总线发布/订阅日志

### 性能优化
- 订单管理器使用字典索引，O(1)查询
- 分层锁减少锁竞争
- 事件总线异步处理

---

**版本**: 2.0.0  
**更新日期**: 2025-01-15  
**维护者**: Trading Team
