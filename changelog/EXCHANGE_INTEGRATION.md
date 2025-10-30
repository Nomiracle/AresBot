# 交易所集成架构说明

## 概述

为了方便将来扩展支持多个交易所，所有币安特定的逻辑已被抽取到 `exchanges/` 模块中。

## 目录结构

```
exchanges/
├── __init__.py              # 包初始化
├── base.py                  # 基类接口定义
├── binance_adapter.py       # 币安适配器实现
└── factory.py               # 交易所工厂类
```

## 核心组件

### 1. BaseExchange (base.py)
所有交易所适配器的抽象基类，定义了统一的接口：

**核心方法：**
- `ping()` - 测试连接
- `get_symbol_info()` - 获取交易对信息
- `get_symbol_ticker()` - 获取当前价格
- `get_open_orders()` - 获取未完成订单
- `order_limit_buy/sell()` - 限价买卖单
- `cancel_replace_order()` - 改价（取消并替换）
- `start_websocket()` - 启动 WebSocket
- `parse_ticker_message()` - 解析行情消息
- `parse_user_message()` - 解析用户数据消息

### 2. BinanceAdapter (binance_adapter.py)
币安交易所的具体实现，封装了：
- 所有币安 API 调用
- WebSocket 连接管理
- 消息格式解析
- 精度计算逻辑

### 3. ExchangeFactory (factory.py)
工厂类，用于创建交易所实例：

```python
from exchanges.factory import ExchangeFactory

# 创建币安适配器
exchange = ExchangeFactory.create(
    exchange_name='binance',
    api_key='your_key',
    api_secret='your_secret',
    testnet=True
)
```

## 如何添加新交易所

### 步骤 1: 创建适配器类

在 `exchanges/` 目录下创建新文件，例如 `okx_adapter.py`:

```python
from .base import BaseExchange

class OKXAdapter(BaseExchange):
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        # 初始化 OKX 客户端
        pass
    
    def ping(self) -> bool:
        # 实现 OKX 的连接测试
        pass
    
    # 实现其他所有抽象方法...
```

### 步骤 2: 注册到工厂

在 `factory.py` 中添加：

```python
from .okx_adapter import OKXAdapter

class ExchangeFactory:
    SUPPORTED_EXCHANGES = {
        'binance': BinanceAdapter,
        'okx': OKXAdapter,  # 新增
    }
```

### 步骤 3: 更新配置

在用户配置中添加 `exchange` 字段：

```python
config = {
    'exchange': 'okx',  # 或 'binance'
    'api_key': '...',
    'api_secret': '...',
    # ...
}
```

### 步骤 4: 使用工厂创建实例

在 `routes.py` 中：

```python
exchange_name = config.get('exchange', 'binance')
exchange = ExchangeFactory.create(
    exchange_name=exchange_name,
    api_key=config['api_key'],
    api_secret=config['api_secret'],
    testnet=bool(config.get('testnet', 1))
)
```

## 当前使用方式

### 在 routes.py 中

```python
from exchanges.factory import ExchangeFactory

# 启动机器人时
exchange = ExchangeFactory.create(
    'binance',
    config['api_key'],
    config['api_secret'],
    testnet=bool(config.get('testnet', 1))
)

# 测试连接
exchange.ping()

# 存储到 bot_data
user_bots[username]['bots'][symbol] = {
    'running': True,
    'exchange': exchange,  # 使用适配器而非原始 client
    'config': config,
    # ...
}
```

### 在 trading.py 中

```python
# 获取交易所适配器
exchange = bot_data['exchange']

# 统一的接口调用
info = exchange.get_symbol_info(symbol)
ticker = exchange.get_symbol_ticker(symbol)
orders = exchange.get_open_orders(symbol)

# WebSocket
ws_result = exchange.start_websocket(
    symbol=symbol,
    on_ticker=_on_ticker_callback,
    on_user=_on_user_callback
)
```

## 优势

1. **解耦**: 交易逻辑与交易所 API 分离
2. **可扩展**: 添加新交易所只需实现接口
3. **可测试**: 可以轻松 mock 交易所适配器
4. **统一**: 所有交易所使用相同的接口
5. **维护性**: 交易所特定代码集中管理

## 注意事项

1. 不同交易所的精度规则可能不同，需在适配器中处理
2. WebSocket 消息格式各异，需在 `parse_*_message()` 中标准化
3. 订单状态枚举可能不同，建议统一映射到标准状态
4. API 限流规则不同，可在适配器中实现限流逻辑

## 未来扩展

- [ ] 支持 OKX
- [ ] 支持 Bybit
- [ ] 支持 Gate.io
- [ ] 统一错误处理（自定义异常类）
- [ ] 统一限流管理
- [ ] 适配器配置文件（每个交易所的特殊参数）
