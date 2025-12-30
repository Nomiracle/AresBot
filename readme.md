# AresBot

多交易所自动交易机器人（本地控制台，Flask）。支持 Binance、Backpack 等多个交易所，默认以模拟模式运行，支持加密保存 API Key/Secret、交易对管理与订单历史记录。

## 支持的交易所

- ✅ **Binance** (币安) - 完整支持，包括 WebSocket 实时数据
- ✅ **Backpack (BPX)** - 完整支持，使用 REST 轮询
- ✅ **Polymarket** - 完整支持，预测市场交易，使用 REST 轮询
- 🔜 **OKX** - 计划中
- 🔜 **Bybit** - 计划中

## 环境要求

- Python 3.10+（建议 3.10 或 3.11）
- pip

## 安装

```bash
# 1) 建议创建虚拟环境（任选其一）
python -m venv .venv && source .venv/bin/activate           # macOS/Linux
# 或
python3 -m venv .venv && source .venv/bin/activate          # 一些系统 python3 命令
# Windows (PowerShell)
python -m venv .venv; .\.venv\Scripts\Activate.ps1

# 2) 安装依赖
pip install -r requirements.txt
```

## 启动

```bash
python app.py
```

启动后访问：

- 控制台地址: http://localhost:50001
- 默认账号: `admin`
- 默认密码: `admin123`

首次启动会自动：

- 初始化 SQLite 数据库 `aresbot.db`
- 生成并保存加密密钥文件 `encryption.key`

### 可选参数

- `--recreate-db` 重建数据库（会删除现有的 `aresbot.db` 后重建，谨慎使用）

示例：

```bash
python app.py --recreate-db
```

## 使用说明

1. 使用默认账号登录控制台。
2. 在"交易配置"中填写：
   - **交易所选择**（Binance、Backpack 或 Polymarket）
   - API Key / Secret（必填，用于连接交易所）
   - 交易对、偏移百分比、卖单加价百分比、下单数量、轮询间隔
   - 网络环境（测试网/生产）与交易模式（模拟/真实）
3. 点击"保存配置到服务器"可将配置加密存储到本地数据库。
4. 点击"启动机器人"开始运行，控制台顶部将显示运行状态、当前价与目标价。
5. "交易对管理"可添加/编辑/删除你常用的交易对，并同步到交易配置下拉框。
6. "订单历史"可查看最近记录（本地数据库）。

### Backpack 交易所使用

如果使用 Backpack 交易所：
- 交易对格式会自动转换（如 SOLUSDC → SOL_USDC）
- 暂不支持 WebSocket，系统会自动使用 REST 轮询
- 详细说明请查看 `changelog/BACKPACK_QUICKSTART.md`

### Polymarket 交易所使用

如果使用 Polymarket 预测市场：
- **API Key**: 填写你的钱包地址（0x开头，40位十六进制）
- **API Secret**: 填写你的钱包私钥（0x开头，64位十六进制）
- **交易对**: 填写市场的 token_id（可从 Polymarket API 获取）
- **价格范围**: Polymarket 价格为概率值，范围 0-1（如 0.65 表示 65%）
- **手续费**: Maker -0.02%（返佣），Taker 0.1%
- 使用 REST 轮询模式监听价格和订单状态
- 运行在 Polygon 主网（Chain ID: 137）

## 关于模拟与实盘

- “交易模式”默认为“模拟交易（simulate_trading=1）”。在模拟模式下不会真实下单，但仍会拉取行情并打印计划操作。
- 切换到“真实交易（simulate_trading=0）”前请务必确认：
  - API Key 权限与风控设置
  - 账户余额与费率
  - 所填写数量与精度满足该交易对的规则

## 关于测试网（Testnet）

- 选择“测试网络”可连接币安测试网账号进行验证。
- 如果出现连接问题，检查 python-binance 版本与测试网可用性；必要时参考 python-binance 文档配置测试网的 API 端点。

## 数据与安全

- 敏感信息（API Key/Secret）使用 Fernet 加密后保存在本地数据库中。
- 加密密钥文件为 `encryption.key`，已在 `.gitignore` 中忽略，请勿提交到版本库。
- 会话密钥 `app.secret_key` 当前在每次启动时随机生成，因此重启后登录会话会失效（属预期行为）。

## 常见问题（FAQ）

- 无法登录或重启后掉线？
  - 重启会重置会话，重新登录即可。
- 下单失败或精度错误？
  - 请确认数量/价格满足交易对的最小步进与精度规则。必要时调小数量或调整保留小数位。
- 连接测试网失败？
  - 确认选择了测试网、API Key 有效，且网络可访问。参照 python-binance 文档排查。
- 想重置默认数据？
  - 启动时加上 `--recreate-db` 参数（会删除并重建数据库）。

## 目录结构（摘要）

- `app.py`: Flask 入口，注册路由、启动服务
- `routes.py`: 登录、配置、订单、交易对管理 API 与页面路由
- `trading.py`: 交易循环逻辑（行情、下单、轮询）
- `database.py`: SQLite 初始化与数据访问
- `migrate_db.py`: 安全迁移（创建交易对表并补默认数据）
- `crypto_utils.py`: 加密/解密与密钥管理
- `templates/`: 前端模板（控制台、登录、修改密码）
- `requirements.txt`: 依赖列表
- `.gitignore`: 已忽略 `*.db`、`encryption.key`、`__pycache__` 等

## 风险提示

自动交易存在风险。强烈建议先使用“测试网络 + 模拟交易”进行充分验证；若切换到真实交易，请自行承担由此带来的资金风险。

## 许可证

本项目采用 **GNU Affero General Public License v3.0 (AGPL-3.0)** 许可证。

### 📋 许可证要点

- ✅ **可以自由使用** - 个人学习和研究
- ✅ **必须开源** - 任何修改或衍生作品必须开源
- ✅ **必须声明原作者** - 保留版权声明和作者信息
- ❌ **禁止商业使用** - 不得用于商业目的或盈利服务
- ❌ **无担保** - 软件按"原样"提供，作者不承担任何责任

### 🔒 附加条款

1. **非商业使用限制**
   - 禁止将本软件用于商业交易运营
   - 禁止作为付费服务提供
   - 禁止销售本软件或基于本软件的服务
   - 如需商业授权，请联系原作者

2. **署名要求**
   - 必须保留原作者信息（Nomiracle）
   - 必须保留指向原始仓库的链接
   - 必须在用户界面中显示归属信息
   - 必须保持许可证文件完整

3. **开源要求**
   - 任何修改必须公开源代码
   - 必须使用相同的 AGPL-3.0 许可证
   - 网络服务必须提供源代码下载

4. **免责声明**
   - 加密货币交易风险极高
   - 作者不对任何财务损失负责
   - 本软件仅供教育和研究目的

详细许可证内容请查看 [LICENSE](LICENSE) 文件。

## 作者

**原作者:** [Nomiracle](https://github.com/Nomiracle)

**项目地址:** https://github.com/Nomiracle/AresBot

如有问题或建议，欢迎提交 [Issue](https://github.com/Nomiracle/AresBot/issues)。

## 贡献

欢迎贡献代码！请遵循以下规则：

1. Fork 本仓库
2. 创建你的特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交你的更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启一个 Pull Request

**注意：** 所有贡献必须遵守 AGPL-3.0 许可证。

## 致谢

感谢以下开源项目：

- [Flask](https://flask.palletsprojects.com/) - Web 框架
- [python-binance](https://github.com/sammchardy/python-binance) - Binance API 客户端
- [bpx-py](https://github.com/sndmndss/bpx-py) - Backpack API 客户端
- [py-clob-client](https://github.com/Polymarket/py-clob-client) - Polymarket API 客户端
- [cryptography](https://cryptography.io/) - 加密库

---

**⚠️ 重要提示：** 本软件仅供学习和研究使用。加密货币交易存在极高风险，请谨慎使用。作者不对任何使用本软件造成的损失负责。

**📜 版权所有 © 2025 Nomiracle. 保留所有权利。**
