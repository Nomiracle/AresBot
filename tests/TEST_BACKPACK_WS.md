# BackpackWsAccount 测试脚本说明

## 概述

为 `BackpackWsAccount` 类创建了两个测试脚本，用于测试 Backpack 交易所的 WebSocket 连接功能。

## 文件说明

### 1. `test_backpack_ws_account.py` - 完整测试脚本

功能全面的测试脚本，支持命令行参数配置。

**特性：**
- ✅ 支持自定义交易对
- ✅ 支持自定义测试时长
- ✅ 详细的消息解析和显示
- ✅ 完整的错误处理
- ✅ 时间戳记录

**使用方法：**

```bash
# 基本用法（默认 SOL_USDC，30秒）
python test_backpack_ws_account.py

# 指定交易对
python test_backpack_ws_account.py --symbol BTC_USDC

# 指定测试时长（60秒）
python test_backpack_ws_account.py --symbol SOL_USDC --duration 60

# 测试 HYPE_USDC
python test_backpack_ws_account.py --symbol HYPE_USDC --duration 120
```

**命令行参数：**
- `--symbol, -s`: 交易对符号（默认: SOL_USDC）
- `--duration, -d`: 测试持续时间，单位秒（默认: 30）

### 2. `test_backpack_ws_simple.py` - 简单测试脚本

快速测试脚本，无需命令行参数，直接运行。

**特性：**
- ✅ 快速启动
- ✅ 固定测试 SOL_USDC
- ✅ 固定测试 10 秒
- ✅ 简洁输出

**使用方法：**

```bash
python test_backpack_ws_simple.py
```

## BackpackWsAccount 类修复

在创建测试脚本时，修复了 `BackpackWsAccount` 类的以下问题：

### 修复内容

1. **移除不存在的基类**
   - 移除了 `from bpx.base.base_ws_account import BaseWsAccount`
   - 移除了 `super().__init__()` 调用

2. **添加 symbol 属性保存**
   ```python
   self.symbol = symbol
   ```

3. **修复 subscribe_markPrice 方法**
   - 将 `websocket` 改为 `self.ws`
   - 添加了方法文档字符串
   - 修复订阅消息格式（`markPrice.{symbol}`）
   - 添加了 `on_message` 的空值检查

4. **添加初始化标志**
   ```python
   self._initialized = True
   ```

## 测试输出示例

### 成功连接示例

```
============================================================
BackpackWsAccount WebSocket 测试
============================================================
交易对: SOL_USDC
测试时长: 30 秒
WebSocket URL: wss://ws.backpack.exchange/
============================================================

[2025-11-05 20:52:00] 🔄 正在连接 WebSocket...
[2025-11-05 20:52:00] ✅ WebSocket 连接已建立
[2025-11-05 20:52:00] 📡 订阅标记价格...
subscribe_message: {'method': 'SUBSCRIBE', 'params': ['markPrice.SOL_USDC']}
[2025-11-05 20:52:00] ⏳ 监听消息 30 秒...

[2025-11-05 20:52:01.123] 📨 收到消息:
  事件类型: 标记价格更新
  交易对: SOL_USDC
  标记价格: 18.70
  预估资金费率: 1.70
  指数价格: 19.70
  下次资金费时间: 1694687965941
```

## 消息类型

WebSocket 可能返回的消息类型：

### 1. 标记价格 (markPrice)

```json
{
  "e": "markPrice",
  "E": 1694687965941000,
  "s": "SOL_USDC",
  "p": "18.70",
  "f": "1.70",
  "i": "19.70",
  "n": 1694687965941,
  "T": 1694687965940999
}
```

### 2. 订单簿深度 (depth)

```json
{
  "e": "depth",
  "s": "SOL_USDC",
  "bids": [["18.50", "100"], ["18.49", "200"]],
  "asks": [["18.51", "150"], ["18.52", "250"]]
}
```

## 依赖要求

```bash
pip install websockets
```

## 注意事项

1. **网络连接**：确保能够访问 `wss://ws.backpack.exchange/`
2. **防火墙**：检查防火墙是否允许 WebSocket 连接
3. **测试时长**：建议测试时长不要太长，避免占用资源
4. **交易对格式**：使用 Backpack 格式，如 `SOL_USDC`，不是 `SOLUSDC`

## 故障排查

### 连接失败

```bash
❌ WebSocket 错误: [Errno 11001] getaddrinfo failed
```

**解决方案：**
- 检查网络连接
- 检查 DNS 设置
- 尝试使用 VPN

### 订阅失败

```bash
❌ WebSocket 错误: Connection closed
```

**解决方案：**
- 检查交易对格式是否正确
- 检查 Backpack API 是否可用
- 查看 Backpack 官方文档确认 WebSocket 端点

## 相关文件

- `exchanges/backpack/backpack_ws_account.py` - WebSocket 客户端实现
- `exchanges/backpack_adapter.py` - Backpack 交易所适配器
- `test_backpack_order.py` - REST API 测试脚本

## 开发建议

1. **扩展功能**：可以添加更多订阅类型（如 trades, kline 等）
2. **错误重连**：添加自动重连机制
3. **消息队列**：使用队列处理消息，避免阻塞
4. **日志记录**：添加日志文件记录，便于调试

## 更新日志

- **2025-11-05**: 创建测试脚本和修复 BackpackWsAccount 类
