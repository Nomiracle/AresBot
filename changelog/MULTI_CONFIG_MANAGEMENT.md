# 多配置管理功能

## 更新日期
2025-10-30

## 功能概述

现在用户可以保存多份配置，每份配置可以有不同的交易所、交易对、API 密钥和交易参数。通过配置名称（别名）来区分和加载不同的配置。

## 主要特性

### 1. 多配置保存
- 每个用户可以保存无限个配置
- 每个配置有唯一的名称（别名）
- 默认配置名称为 "default"

### 2. 配置管理界面
- 新增"配置管理"标签页
- 显示所有已保存的配置列表
- 支持加载、删除配置

### 3. 灵活的配置命名
- 可以使用描述性名称，如：
  - `binance-btc` - Binance 的 BTC 配置
  - `backpack-sol` - Backpack 的 SOL 配置
  - `strategy-1` - 策略 1
  - `test-config` - 测试配置

## 数据库更新

### 新增字段

在 `user_configs` 表中添加了两个新字段：

```sql
ALTER TABLE user_configs ADD COLUMN config_name TEXT NOT NULL DEFAULT 'default'
ALTER TABLE user_configs ADD COLUMN exchange TEXT NOT NULL DEFAULT 'binance'
```

**字段说明：**
- `config_name`: 配置名称/别名，用于区分不同配置
- `exchange`: 交易所名称（binance, backpack 等）

### 唯一约束

```sql
UNIQUE(user_id, config_name)
```

确保同一用户的配置名称不重复。

### 数据迁移

系统会自动为已存在的表添加新列，现有配置会自动设置为：
- `config_name`: 'default'
- `exchange`: 'binance'

## 使用方法

### 1. 保存配置

**步骤：**
1. 在"交易配置"页面填写所有参数
2. 在"配置名称"输入框输入名称（如 `binance-btc`）
3. 点击"💾 保存当前配置"
4. 配置保存成功

**示例：**
```
配置名称: binance-btc
交易所: Binance
交易对: BTCUSDT
API Key: your_key
...其他参数
```

### 2. 加载配置

**方法 1: 从交易配置页面加载**
1. 点击"📥 加载配置"按钮
2. 在弹出的对话框中查看可用配置列表
3. 输入要加载的配置名称
4. 配置自动填充到表单

**方法 2: 从配置管理页面加载**
1. 切换到"配置管理"标签页
2. 找到要加载的配置
3. 点击"📥 加载"按钮
4. 自动切换到"交易配置"页面并填充

### 3. 删除配置

1. 进入"配置管理"标签页
2. 找到要删除的配置
3. 点击"🗑️ 删除"按钮
4. 确认删除

**注意：** `default` 配置不能删除

### 4. 查看所有配置

进入"配置管理"标签页，可以看到：
- 配置名称
- 使用的交易所
- 交易对
- 最后更新时间

## 界面更新

### 1. 交易配置页面

**新增配置名称输入框：**
```
┌─────────────────────────────────────────────┐
│ 配置名称（用于保存多份配置）                  │
│ [输入配置名称，如: binance-btc, backpack-sol] │
│ 提示：不同配置可以保存不同的交易所、交易对和参数 │
└─────────────────────────────────────────────┘
```

**按钮更新：**
- "💾 保存配置到服务器" → "💾 保存当前配置"
- "📥 加载已保存配置" → "📥 加载配置"

### 2. 配置管理页面

**配置列表显示：**
```
┌──────────────────────────────────────────────┐
│ binance-btc                                   │
│ 交易所: Binance | 交易对: BTCUSDT             │
│ 更新时间: 2025-10-30T20:00:00                │
│                            [📥 加载] [🗑️ 删除] │
├──────────────────────────────────────────────┤
│ backpack-sol                                  │
│ 交易所: Backpack | 交易对: SOLUSDC            │
│ 更新时间: 2025-10-30T20:01:00                │
│                            [📥 加载] [🗑️ 删除] │
└──────────────────────────────────────────────┘
```

## API 接口

### 1. 保存配置

**POST** `/api/config/save`

**请求：**
```json
{
  "config_name": "binance-btc",
  "config": {
    "exchange": "binance",
    "api_key": "your_key",
    "api_secret": "your_secret",
    "symbol": "BTCUSDT",
    "offset_percent": -0.1,
    "sell_offset_percent": 0.5,
    "quantity": 0.001,
    "interval": 1,
    "testnet": 1,
    "simulate_trading": 1
  }
}
```

**响应：**
```json
{
  "success": true,
  "message": "配置 \"binance-btc\" 已加密保存到服务器"
}
```

### 2. 加载配置

**GET** `/api/config/load?config_name=binance-btc`

**响应：**
```json
{
  "success": true,
  "config": {
    "config_name": "binance-btc",
    "exchange": "binance",
    "api_key": "decrypted_key",
    "api_secret": "decrypted_secret",
    "symbol": "BTCUSDT",
    "offset_percent": -0.1,
    "sell_offset_percent": 0.5,
    "quantity": 0.001,
    "interval": 1,
    "testnet": 1,
    "simulate_trading": 1
  }
}
```

### 3. 获取配置列表

**GET** `/api/configs`

**响应：**
```json
{
  "success": true,
  "configs": [
    {
      "config_name": "binance-btc",
      "exchange": "binance",
      "symbol": "BTCUSDT",
      "updated_at": "2025-10-30T20:00:00"
    },
    {
      "config_name": "backpack-sol",
      "exchange": "backpack",
      "symbol": "SOLUSDC",
      "updated_at": "2025-10-30T20:01:00"
    }
  ]
}
```

### 4. 删除配置

**POST** `/api/config/delete`

**请求：**
```json
{
  "config_name": "test-config"
}
```

**响应：**
```json
{
  "success": true,
  "message": "配置 \"test-config\" 已删除"
}
```

## 使用场景

### 场景 1: 多交易所管理

```
配置 1: binance-btc
  - 交易所: Binance
  - 交易对: BTCUSDT
  - API Key: binance_key

配置 2: backpack-sol
  - 交易所: Backpack
  - 交易对: SOLUSDC
  - API Key: backpack_key
```

### 场景 2: 不同策略

```
配置 1: aggressive
  - 偏移: -0.5%
  - 数量: 0.01
  - 间隔: 1秒

配置 2: conservative
  - 偏移: -0.1%
  - 数量: 0.001
  - 间隔: 5秒
```

### 场景 3: 测试和生产

```
配置 1: test
  - 测试网: 是
  - 模拟交易: 是
  - 数量: 0.001

配置 2: production
  - 测试网: 否
  - 模拟交易: 否
  - 数量: 0.01
```

## 最佳实践

### 1. 命名规范

**推荐格式：**
- `{交易所}-{交易对}`: `binance-btc`, `backpack-sol`
- `{策略名称}`: `aggressive`, `conservative`, `scalping`
- `{环境}-{用途}`: `test-config`, `prod-btc`, `demo-eth`

**避免：**
- 特殊字符（除了 `-` 和 `_`）
- 过长的名称
- 容易混淆的名称

### 2. 配置管理

- 为每个交易所创建独立配置
- 为不同策略创建独立配置
- 定期清理不用的配置
- 保留 `default` 作为默认配置

### 3. 安全建议

- 不同交易所使用不同的 API 密钥
- 测试配置使用测试网密钥
- 生产配置使用生产密钥
- 定期更新 API 密钥

## 向后兼容

### 旧配置迁移

系统会自动将旧配置迁移为 `default` 配置：
- 配置名称: `default`
- 交易所: `binance`（如果未指定）

### API 兼容性

旧的 API 调用仍然有效：
```javascript
// 旧方式（仍然有效，保存到 default）
fetch("/api/config/save", {
  body: JSON.stringify(config)
})

// 新方式（推荐）
fetch("/api/config/save", {
  body: JSON.stringify({
    config_name: "my-config",
    config: config
  })
})
```

## 故障排查

### 问题 1: 配置名称冲突

**错误：** 保存时提示配置已存在

**解决：**
- 使用不同的配置名称
- 或者直接覆盖（系统会更新现有配置）

### 问题 2: 无法删除 default 配置

**原因：** default 配置受保护

**解决：**
- default 配置不能删除
- 可以修改 default 配置的内容

### 问题 3: 加载配置后交易对不显示

**原因：** 交易对不支持当前交易所

**解决：**
1. 检查交易对的 exchanges 设置
2. 确保交易对支持配置中的交易所

## 未来扩展

- [ ] 配置导入/导出功能
- [ ] 配置模板
- [ ] 配置复制功能
- [ ] 批量配置管理
- [ ] 配置版本历史

## 相关文档

- **多交易所支持**: `UI_EXCHANGE_SELECTOR.md`
- **交易对管理**: `MULTI_EXCHANGE_PAIRS.md`
- **数据库结构**: 查看 `database.py`

---

**更新日期**: 2025-10-30  
**版本**: v3.2  
**状态**: ✅ 完成
