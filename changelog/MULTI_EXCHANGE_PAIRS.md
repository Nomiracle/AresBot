# 多交易所共用交易对功能

## 更新日期
2025-10-30

## 功能说明

现在交易对可以在多个交易所之间共用。每个交易对可以标记支持哪些交易所（Binance、Backpack 等），系统会根据当前选择的交易所自动过滤显示相应的交易对。

## 主要特性

### 1. 交易对支持多交易所标记
- 每个交易对可以选择支持一个或多个交易所
- 默认情况下，交易对同时支持 Binance 和 Backpack
- 可以在编辑时修改支持的交易所

### 2. 智能过滤
- 切换交易所时，交易对下拉列表自动过滤
- 只显示当前交易所支持的交易对
- 避免选择不兼容的交易对

### 3. 可视化显示
- 交易对管理页面显示每个交易对支持的交易所
- 编辑时可以通过复选框选择支持的交易所

## 数据库更新

### 新增字段

在 `trading_pairs` 表中添加了 `exchanges` 字段：

```sql
ALTER TABLE trading_pairs ADD COLUMN exchanges TEXT DEFAULT 'binance,backpack'
```

**字段说明：**
- 类型: TEXT
- 格式: 逗号分隔的交易所列表，如 'binance,backpack'
- 默认值: 'binance,backpack'（支持所有交易所）

### 数据迁移

系统会自动为已存在的表添加 `exchanges` 列，无需手动迁移。现有的交易对会自动设置为支持所有交易所。

## 前端更新

### 1. 交易对列表显示

**之前：**
```
BTC/USDT (BTCUSDT)
创建时间: 2025-10-30
```

**现在：**
```
BTC/USDT (BTCUSDT)
支持交易所: Binance, Backpack
创建时间: 2025-10-30
```

### 2. 编辑交易对界面

添加了交易所复选框：
```
[交易对输入框] [显示名称输入框]
☑ Binance  ☑ Backpack
[💾 保存] [❌ 取消]
```

### 3. 交易对过滤

**`updateSymbolDropdown()` 函数更新：**
```javascript
function updateSymbolDropdown(pairs) {
  const currentExchange = document.getElementById("exchange").value;
  
  // 过滤出支持当前交易所的交易对
  const filteredPairs = pairs.filter(pair => {
    const exchanges = pair.exchanges || 'binance,backpack';
    return exchanges.split(',').includes(currentExchange);
  });
  
  // 只显示过滤后的交易对
  select.innerHTML = filteredPairs
    .map((p) => `<option value="${p.symbol}">${p.display_name}</option>`)
    .join("");
}
```

### 4. 交易所切换

**`updateExchangeUI()` 函数更新：**
```javascript
function updateExchangeUI() {
  // 更新 placeholder
  // ...
  
  // 重新加载交易对列表（会根据当前交易所过滤）
  loadTradingPairs();
}
```

## 后端更新

### 1. database.py

**`get_user_trading_pairs()` 更新：**
```python
def get_user_trading_pairs(username):
    c.execute("""SELECT id, symbol, display_name, exchanges, created_at
                 FROM trading_pairs WHERE user_id=? ORDER BY id ASC""", (user_id,))
    
    return [
        {
            'id': p[0],
            'symbol': p[1],
            'display_name': p[2],
            'exchanges': p[3] or 'binance,backpack',
            'created_at': p[4]
        }
        for p in pairs
    ]
```

**`update_trading_pair()` 更新：**
```python
def update_trading_pair(username, pair_id, symbol, display_name, exchanges=None):
    if exchanges is not None:
        c.execute("""UPDATE trading_pairs SET symbol=?, display_name=?, exchanges=?
                     WHERE id=? AND user_id=?""",
                  (symbol.upper(), display_name, exchanges, pair_id, user_id))
    else:
        c.execute("""UPDATE trading_pairs SET symbol=?, display_name=?
                     WHERE id=? AND user_id=?""",
                  (symbol.upper(), display_name, pair_id, user_id))
```

### 2. routes.py

**`/api/trading_pairs/update` 更新：**
```python
@app.route('/api/trading_pairs/update', methods=['POST'])
def api_update_trading_pair():
    data = request.json
    pair_id = data.get('id')
    symbol = data.get('symbol', '').strip().upper()
    display_name = data.get('display_name', '').strip()
    exchanges = data.get('exchanges')  # 新增
    
    if update_trading_pair(username, pair_id, symbol, display_name, exchanges):
        return jsonify({'success': True, 'message': '交易对更新成功'})
```

## 使用示例

### 场景 1: 创建通用交易对

**BTC/USDT** - 同时支持 Binance 和 Backpack
- Symbol: BTCUSDT
- 支持交易所: ☑ Binance  ☑ Backpack
- 在 Binance 模式下显示
- 在 Backpack 模式下显示

### 场景 2: 创建 Binance 专用交易对

**BNB/USDT** - 仅支持 Binance
- Symbol: BNBUSDT
- 支持交易所: ☑ Binance  ☐ Backpack
- 在 Binance 模式下显示
- 在 Backpack 模式下**不显示**

### 场景 3: 创建 Backpack 专用交易对

**SOL/USDC** - 仅支持 Backpack
- Symbol: SOLUSDC
- 支持交易所: ☐ Binance  ☑ Backpack
- 在 Binance 模式下**不显示**
- 在 Backpack 模式下显示

## 工作流程

### 1. 添加交易对
```
1. 进入"交易对管理"页面
2. 输入交易对和显示名称
3. 点击"添加"
4. 默认支持所有交易所
```

### 2. 编辑交易对
```
1. 点击交易对的"✏️ 编辑"按钮
2. 修改交易对、显示名称
3. 选择/取消选择支持的交易所
4. 点击"💾 保存"
```

### 3. 使用交易对
```
1. 在"交易配置"页面选择交易所
2. 交易对下拉列表自动过滤
3. 只显示当前交易所支持的交易对
4. 选择交易对并配置参数
```

## API 响应格式

### GET /api/trading_pairs

```json
{
  "success": true,
  "pairs": [
    {
      "id": 1,
      "symbol": "BTCUSDT",
      "display_name": "BTC/USDT",
      "exchanges": "binance,backpack",
      "created_at": "2025-10-30T20:00:00"
    },
    {
      "id": 2,
      "symbol": "BNBUSDT",
      "display_name": "BNB/USDT",
      "exchanges": "binance",
      "created_at": "2025-10-30T20:01:00"
    },
    {
      "id": 3,
      "symbol": "SOLUSDC",
      "display_name": "SOL/USDC",
      "exchanges": "backpack",
      "created_at": "2025-10-30T20:02:00"
    }
  ]
}
```

### POST /api/trading_pairs/update

**请求：**
```json
{
  "id": 1,
  "symbol": "BTCUSDT",
  "display_name": "BTC/USDT",
  "exchanges": "binance,backpack"
}
```

**响应：**
```json
{
  "success": true,
  "message": "交易对更新成功"
}
```

## 兼容性

### 向后兼容
- 现有交易对自动设置为支持所有交易所
- 如果 `exchanges` 字段为空，默认为 'binance,backpack'
- 旧的 API 调用仍然有效（不传 exchanges 参数）

### 数据库兼容
- 自动添加 `exchanges` 列
- 不影响现有数据
- 无需手动迁移

## 最佳实践

### 1. 交易对命名
- **通用交易对**: 使用常见格式（如 BTCUSDT）
- **交易所特定**: 根据交易所格式命名
  - Binance: BTCUSDT
  - Backpack: SOLUSDC (自动转换为 SOL_USDC)

### 2. 交易所选择
- **主流币种**: 支持所有交易所
- **交易所特有币种**: 只选择相应交易所
- **测试时**: 先选择一个交易所测试

### 3. 维护建议
- 定期检查交易对是否在各交易所仍然可用
- 及时更新不再支持的交易对
- 为新交易所添加相应的交易对

## 故障排查

### 问题 1: 切换交易所后看不到交易对

**原因**: 该交易对不支持当前交易所

**解决**:
1. 进入"交易对管理"
2. 编辑交易对
3. 勾选当前交易所
4. 保存

### 问题 2: 交易对在所有交易所都不显示

**原因**: exchanges 字段为空或格式错误

**解决**:
1. 编辑交易对
2. 至少选择一个交易所
3. 保存

### 问题 3: 保存时提示"请至少选择一个交易所"

**原因**: 取消了所有交易所的选择

**解决**:
- 至少选择一个交易所

## 未来扩展

- [ ] 支持更多交易所（OKX, Bybit等）
- [ ] 批量编辑交易对的交易所支持
- [ ] 交易对模板（快速添加常用交易对）
- [ ] 交易对导入/导出功能
- [ ] 交易对使用统计

## 相关文档

- **UI 交易所选择**: `UI_EXCHANGE_SELECTOR.md`
- **Backpack 集成**: `BACKPACK_INTEGRATION.md`
- **数据库结构**: 查看 `database.py`

---

**更新日期**: 2025-10-30  
**版本**: v3.1  
**状态**: ✅ 完成
