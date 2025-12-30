# Polymarket 交易所快速入门

## 简介

Polymarket 是一个去中心化的预测市场平台，用户可以对各种事件的结果进行交易。AresBot 现已支持 Polymarket 交易所的自动交易功能。

## 特点

- ✅ 基于 Polygon 主网运行
- ✅ 支持限价单买卖
- ✅ 使用 REST API 轮询模式监听价格和订单
- ✅ 支持标准 EOA 钱包和代理钱包
- ✅ 价格范围 0-1 (概率值)

## 前置准备

### 1. 安装依赖

```bash
pip install py-clob-client>=0.22.0
```

### 2. 准备钱包

使用标准 EOA 钱包（如 MetaMask）：
- 钱包地址：`0x` 开头的 40 位十六进制字符串
- 私钥：`0x` 开头的 64 位十六进制字符串
- 示例地址：`0x1234567890abcdef1234567890abcdef12345678`
- 示例私钥：`0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef`

### 3. 获取 Token ID

每个 Polymarket 市场都有唯一的 token_id。获取方式：

1. 访问 [Polymarket API 文档](https://docs.polymarket.com/developers/gamma-markets-api/get-markets)
2. 使用 API 查询市场列表
3. 找到你想交易的市场的 `token_id`

示例 API 调用：
```python
from py_clob_client.client import ClobClient

client = ClobClient("https://clob.polymarket.com")
markets = client.get_simplified_markets()
print(markets["data"][:5])  # 查看前5个市场
```

### 4. 设置 Token 授权（仅 EOA 钱包）

如果使用 MetaMask 或硬件钱包，首次交易前需要设置 token 授权：

```python
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

client = ClobClient(
    "https://clob.polymarket.com",
    key="your-private-key",
    chain_id=137
)

# 设置 USDC 授权
client.set_token_allowance(POLYGON.collateral_token_address, amount=1000)

# 设置条件代币授权
client.set_conditional_token_allowance()
```

## AresBot 配置

### 配置参数说明

在 AresBot 控制台的"交易配置"页面：

| 参数 | 说明 | 示例 |
|------|------|------|
| **交易所** | 选择 `polymarket` 或 `native_polymarket_spot` | `polymarket` |
| **API Key** | 钱包地址（0x开头） | `0x1234...5678` |
| **API Secret** | 钱包私钥（0x开头） | `0xabcd...ef` |
| **交易对** | 市场的 token_id | `21742633143...` |
| **偏移百分比** | 买入价格偏移（负数表示低于市价） | `-0.5` |
| **卖单加价百分比** | 卖出价格加价 | `2.0` |
| **下单数量** | 购买的份额数量 | `10.0` |
| **轮询间隔** | 价格检查间隔（秒） | `5` |

### 价格说明

Polymarket 的价格表示事件发生的概率：
- 价格范围：`0.00` - `1.00`
- `0.65` 表示 65% 的概率
- `0.50` 表示 50/50 的概率
- 最小价格单位：`0.001` (0.1%)

### 手续费

- **Maker**: -0.02% (返佣)
- **Taker**: 0.1%

## 使用示例

### 配置示例

```
交易所: polymarket
API Key: 0x1234567890abcdef1234567890abcdef12345678
API Secret: 0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef
交易对: 21742633143462248961306261002318505831055566520414311359030899466832640
偏移百分比: -0.5
卖单加价百分比: 2.0
下单数量: 10.0
```

## 交易流程

1. **启动机器人**
   - 点击"启动机器人"按钮
   - 系统会连接 Polymarket API
   - 开始监听市场价格

2. **自动下单**
   - 当价格满足条件时自动下买单
   - 买单成交后自动挂卖单
   - 卖单成交后继续循环

3. **监控状态**
   - 控制台实时显示当前价格
   - 显示目标买入价和卖出价
   - 显示订单状态和成交信息

## 注意事项

### 1. 网络要求
- Polymarket 运行在 Polygon 主网
- 确保网络连接稳定
- 建议使用可靠的 RPC 节点

### 2. 资金准备
- 账户需要有足够的 USDC（Polygon 链）
- 账户需要有少量 MATIC 支付 gas 费
- 建议先小额测试

### 3. 价格精度
- 价格保留 3 位小数
- 数量保留 2 位小数
- 系统会自动对齐到最小单位

### 4. 订单监听
- 使用 HTTP 轮询模式（每 2-3 秒）
- 不支持 WebSocket 实时推送
- 订单状态可能有轻微延迟

### 5. 市场流动性
- 预测市场流动性可能较低
- 大额订单可能难以成交
- 建议设置合理的价格偏移

## 常见问题

### Q: 如何获取私钥？
A: 
- MetaMask: 账户详情 → 导出私钥
- 其他钱包: 查看钱包文档
- ⚠️ 私钥泄露会导致资金损失，请妥善保管

### Q: 为什么订单没有成交？
A: 可能原因：
- 价格设置不合理（偏离市价太多）
- 市场流动性不足
- 账户余额不足（需要USDC和MATIC）
- Token 授权未设置（首次使用需设置）

### Q: 如何查看订单历史？
A: 
- AresBot 控制台 → 订单历史
- Polymarket 官网 → 我的订单
- 使用 API 查询交易记录

### Q: 支持测试网吗？
A: Polymarket 主要运行在 Polygon 主网，建议先用小额资金测试。

### Q: 手续费如何计算？
A: 
- 挂单（Maker）: -0.02% (返佣)
- 吃单（Taker）: 0.1%
- 系统会自动计算并在卖价中考虑手续费

## 安全建议

1. **私钥安全**
   - 不要在公共场合暴露私钥
   - 使用环境变量存储敏感信息
   - 定期更换 API 密钥

2. **资金管理**
   - 不要在账户中存放大额资金
   - 使用专门的交易账户
   - 定期提取利润

3. **风险控制**
   - 先使用模拟模式测试
   - 设置合理的止损点
   - 不要过度杠杆

4. **监控告警**
   - 定期检查机器人运行状态
   - 关注异常交易
   - 设置资金告警

## 相关链接

- [Polymarket 官网](https://polymarket.com/)
- [Polymarket API 文档](https://docs.polymarket.com/)
- [py-clob-client GitHub](https://github.com/Polymarket/py-clob-client)
- [Polygon 区块浏览器](https://polygonscan.com/)

## 技术支持

如遇问题，请：
1. 查看 AresBot 日志文件
2. 检查 Polymarket API 状态
3. 提交 [GitHub Issue](https://github.com/Nomiracle/AresBot/issues)

---

**最后更新**: 2024-12-30
