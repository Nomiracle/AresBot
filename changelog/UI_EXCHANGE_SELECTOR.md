# 前端交易所选择功能

## 更新日期
2025-10-30

## 更新内容

### 1. 前端界面更新 (`templates/index.html`)

#### 新增交易所选择器
在"交易配置"区域添加了交易所下拉选择框：

```html
<div class="input-group">
  <label>交易所 🏦</label>
  <select id="exchange" onchange="updateExchangeUI()">
    <option value="binance">Binance (币安)</option>
    <option value="backpack">Backpack (BPX)</option>
  </select>
</div>
```

#### 新增 JavaScript 函数

**`updateExchangeUI()`** - 交易所切换时更新界面
- 自动更新 API Key/Secret 的 placeholder 提示
- 根据选择的交易所切换交易对列表
- Binance: BTCUSDT, ETHUSDT, BNBUSDT, ADAUSDT, SOLUSDT
- Backpack: SOLUSDC, BTCUSDC, ETHUSDC, SOLUSDT

**更新的函数：**
- `startBot()` - 添加 `exchange` 参数
- `saveConfig()` - 保存交易所选择
- `loadConfig()` - 加载交易所选择并更新 UI

#### 页面标题更新
```
旧: 币安自动交易机器人 v3.0
新: 多交易所自动交易机器人 v3.1 - 支持 Binance & Backpack
```

### 2. 后端路由更新 (`routes.py`)

#### `/api/start` 路由
- 从配置中读取 `exchange` 参数（默认 'binance'）
- 使用 `ExchangeFactory.create()` 动态创建交易所适配器
- 添加交易所验证，不支持的交易所返回错误

```python
exchange_name = config.get('exchange', 'binance').lower()
exchange = ExchangeFactory.create(
    exchange_name,
    config['api_key'],
    config['api_secret'],
    testnet=testnet
)

if not exchange:
    return jsonify({'success': False, 'message': f'不支持的交易所: {exchange_name}'}), 400
```

#### `/api/bot/start` 路由
- 同样支持 `exchange` 参数
- 动态创建交易所适配器

## 使用方法

### 1. 选择交易所

在"交易配置"页面：
1. 点击"交易所"下拉框
2. 选择 "Binance (币安)" 或 "Backpack (BPX)"
3. 界面会自动更新：
   - API Key/Secret 提示文本
   - 可用的交易对列表

### 2. 配置参数

**Binance 配置：**
- 交易所: Binance (币安)
- API Key: Binance API Key
- API Secret: Binance API Secret
- 交易对: BTCUSDT, ETHUSDT 等

**Backpack 配置：**
- 交易所: Backpack (BPX)
- API Key: Backpack Public Key
- API Secret: Backpack Secret Key
- 交易对: SOLUSDC, BTCUSDC 等

### 3. 保存和加载

**保存配置：**
- 点击"保存配置到服务器"
- 交易所选择会被保存

**加载配置：**
- 点击"加载已保存配置"
- 自动恢复交易所选择
- 自动更新界面

### 4. 启动机器人

- 配置完成后点击"启动机器人"
- 系统会使用选择的交易所创建适配器
- 日志中会显示交易所名称

## 界面截图说明

### 选择 Binance
```
交易所: [Binance (币安) ▼]
API Key: [输入 Binance API Key]
API Secret: [输入 Binance API Secret]
交易对: [BTCUSDT ▼]
```

### 选择 Backpack
```
交易所: [Backpack (BPX) ▼]
API Key: [输入 Backpack Public Key]
API Secret: [输入 Backpack Secret Key]
交易对: [SOLUSDC ▼]
```

## 技术细节

### 前端数据流

1. **用户选择交易所** → `updateExchangeUI()` 被调用
2. **更新 placeholder** → 提示用户输入正确的密钥类型
3. **更新交易对列表** → 显示该交易所支持的交易对
4. **保存配置** → `exchange` 字段被包含在配置中
5. **加载配置** → 恢复交易所选择并更新 UI

### 后端数据流

1. **接收配置** → 包含 `exchange` 字段
2. **创建适配器** → `ExchangeFactory.create(exchange_name, ...)`
3. **验证交易所** → 检查是否支持
4. **启动机器人** → 使用对应的交易所适配器

### 配置格式

```json
{
  "exchange": "backpack",
  "api_key": "your_public_key",
  "api_secret": "your_secret_key",
  "symbol": "SOLUSDC",
  "offset_percent": -0.1,
  "sell_offset_percent": 0.5,
  "quantity": 0.1,
  "interval": 2,
  "testnet": 0,
  "simulate_trading": 1
}
```

## 兼容性

### 向后兼容
- 如果配置中没有 `exchange` 字段，默认使用 'binance'
- 现有配置无需修改即可继续使用
- 旧的 Binance 配置会自动工作

### 数据库
- 配置存储在数据库的 `config` 字段（JSON 格式）
- `exchange` 字段会被自动保存和加载
- 无需数据库迁移

## 错误处理

### 不支持的交易所
```json
{
  "success": false,
  "message": "不支持的交易所: unknown_exchange"
}
```

### 交易所创建失败
- 前端显示错误提示
- 后端返回详细错误信息
- 日志记录完整堆栈

## 测试建议

### 功能测试

1. **切换交易所**
   - 选择 Binance → 验证交易对列表
   - 选择 Backpack → 验证交易对列表
   - 验证 placeholder 文本更新

2. **保存和加载**
   - 配置 Binance → 保存 → 刷新页面 → 加载 → 验证
   - 配置 Backpack → 保存 → 刷新页面 → 加载 → 验证

3. **启动机器人**
   - 使用 Binance 配置启动
   - 使用 Backpack 配置启动
   - 验证日志中的交易所名称

### 边界测试

1. **无效交易所**
   - 手动修改配置为不支持的交易所
   - 验证错误提示

2. **缺少 exchange 字段**
   - 使用旧配置（无 exchange 字段）
   - 验证默认使用 Binance

3. **交易对不匹配**
   - Binance 配置使用 Backpack 交易对
   - 验证错误处理

## 未来改进

- [ ] 添加更多交易所（OKX, Bybit）
- [ ] 交易对列表从后端动态获取
- [ ] 显示交易所状态（在线/离线）
- [ ] 支持自定义交易对输入
- [ ] 交易所特定的参数配置

## 相关文档

- **Backpack 集成**: `BACKPACK_INTEGRATION.md`
- **快速开始**: `BACKPACK_QUICKSTART.md`
- **故障排查**: `TROUBLESHOOTING.md`

---

**更新完成日期**: 2025-10-30  
**版本**: v3.1  
**状态**: ✅ 完成
