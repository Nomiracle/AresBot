# 交易所适配器迁移指南

## 概述

本指南说明如何将现有代码迁移到新的交易所适配器架构。

## 主要变更

### 1. routes.py 中的变更

#### 旧代码：
```python
from binance.client import Client

# 创建客户端
client = Client(config['api_key'], config['api_secret'], testnet=testnet)
client.ping()

# 存储
user_bots[username]['bots'][symbol] = {
    'client': client,
    # ...
}
```

#### 新代码：
```python
from exchanges.factory import ExchangeFactory

# 创建交易所适配器
exchange = ExchangeFactory.create(
    'binance',  # 交易所名称
    config['api_key'],
    config['api_secret'],
    testnet=testnet
)
exchange.ping()

# 存储
user_bots[username]['bots'][symbol] = {
    'exchange': exchange,  # 使用 exchange 而非 client
    # ...
}
```

### 2. trading.py 中的变更

#### 旧代码：
```python
client = bot_data['client']

# API 调用
ticker = client.get_symbol_ticker(symbol=config['symbol'])
info = client.get_symbol_info(symbol=config['symbol'])
orders = client.get_open_orders(symbol=config['symbol'])
order = client.order_limit_buy(...)
```

#### 新代码：
```python
exchange = bot_data['exchange']

# 统一接口调用
ticker = exchange.get_symbol_ticker(symbol=config['symbol'])
info = exchange.get_symbol_info(symbol=config['symbol'])
orders = exchange.get_open_orders(symbol=config['symbol'])
order = exchange.order_limit_buy(...)
```

### 3. WebSocket 处理变更

#### 旧代码：
```python
from binance import ThreadedWebsocketManager

# 手动创建和管理 WebSocket
twm = ThreadedWebsocketManager(api_key=api_key, api_secret=api_secret)
twm.start()
twm.start_symbol_ticker_socket(callback=_on_ticker, symbol=symbol)
twm.start_user_socket(callback=_on_user)

# 手动解析消息
def _on_ticker(msg):
    last_price = msg.get('c') or msg.get('p')
    # ...

def _on_user(msg):
    if msg.get('e') == 'executionReport':
        side = msg.get('S')
        # ...
```

#### 新代码：
```python
# 使用适配器启动 WebSocket
def _on_ticker(msg):
    # 使用适配器解析
    price = exchange.parse_ticker_message(msg)
    if price:
        bot_data['current_price'] = price

def _on_user(msg):
    # 使用适配器解析为标准格式
    event = exchange.parse_user_message(msg)
    if event and event['event_type'] == 'order_filled':
        order_id = event['order_id']
        side = event['side']
        # 统一的处理逻辑
        # ...

# 启动 WebSocket
ws_result = exchange.start_websocket(
    symbol=config['symbol'],
    on_ticker=_on_ticker,
    on_user=_on_user
)

bot_data['twm'] = ws_result['manager']
bot_data['ws_user_enabled'] = ws_result['user_enabled']
```

### 4. 精度处理变更

#### 旧代码：
```python
info = client.get_symbol_info(symbol=config['symbol'])
price_filter = next(f for f in info['filters'] if f['filterType'] == 'PRICE_FILTER')
lot_filter = next(f for f in info['filters'] if f['filterType'] == 'LOT_SIZE')

tick_size = float(price_filter['tickSize'])
step_size = float(lot_filter['stepSize'])
price_decimals = int(abs(math.log10(tick_size)))
qty_decimals = int(abs(math.log10(step_size)))
```

#### 新代码：
```python
info = exchange.get_symbol_info(symbol=config['symbol'])

# 使用适配器提取精度
tick_size, price_decimals = exchange.get_price_precision(info)
step_size, qty_decimals = exchange.get_quantity_precision(info)
```

## 迁移步骤

### 步骤 1: 更新 routes.py

1. 导入工厂类：
```python
from exchanges.factory import ExchangeFactory
```

2. 在 `/api/start` 和 `/api/bot/start` 中替换客户端创建：
```python
# 旧：client = Client(...)
# 新：
exchange = ExchangeFactory.create(
    'binance',
    config['api_key'],
    config['api_secret'],
    testnet=bool(config.get('testnet', 1))
)
```

3. 更新 bot_data 存储：
```python
user_bots[username]['bots'][symbol] = {
    'running': True,
    'exchange': exchange,  # 改为 exchange
    'config': config,
    # ...
}
```

### 步骤 2: 更新 trading.py

1. 导入适配器（如果需要类型提示）：
```python
from exchanges.base import BaseExchange
```

2. 替换所有 `client` 引用为 `exchange`：
```python
# 旧：client = bot_data['client']
# 新：exchange = bot_data['exchange']
```

3. 更新所有 API 调用（接口相同，无需改动调用方式）

4. 更新 WebSocket 处理：
   - 使用 `exchange.start_websocket()`
   - 使用 `exchange.parse_ticker_message()`
   - 使用 `exchange.parse_user_message()`

5. 更新精度处理：
   - 使用 `exchange.get_price_precision()`
   - 使用 `exchange.get_quantity_precision()`

### 步骤 3: 测试

1. 启动应用：`python app.py`
2. 登录并启动机器人
3. 验证：
   - API 调用正常
   - WebSocket 连接成功
   - 订单下单/查询正常
   - 价格精度对齐正确

### 步骤 4: 清理（可选）

1. 移除 trading.py 中直接导入的 binance 模块：
```python
# 可以移除：
# from binance.client import Client
# from binance.exceptions import BinanceAPIException
# from binance import ThreadedWebsocketManager
```

2. 通过适配器访问异常类：
```python
# 如果需要捕获 Binance 特定异常，可以：
try:
    exchange.order_limit_buy(...)
except Exception as e:
    # 适配器会处理并重新抛出标准异常
    pass
```

## 兼容性说明

- 新架构完全向后兼容
- 可以逐步迁移，不需要一次性改完
- 旧的 `client` 仍可通过 `exchange.get_client()` 获取（仅币安）

## 回滚方案

如果需要回滚到旧架构：

1. 恢复 routes.py 中的 `Client` 创建
2. 恢复 trading.py 中的 `client` 引用
3. 保留 `exchanges/` 目录以备将来使用

## 常见问题

**Q: 现有代码会立即失效吗？**
A: 不会。新架构是增量式的，现有代码仍可运行。

**Q: 必须立即迁移吗？**
A: 不必须，但建议尽快迁移以享受统一接口的好处。

**Q: 如何同时支持多个交易所？**
A: 在配置中添加 `exchange` 字段，使用工厂类创建对应实例。

**Q: 性能会受影响吗？**
A: 不会。适配器只是薄封装层，几乎无性能损耗。

## 下一步

迁移完成后，可以：
1. 添加其他交易所支持（OKX, Bybit等）
2. 在 UI 中添加交易所选择器
3. 实现跨交易所套利策略
