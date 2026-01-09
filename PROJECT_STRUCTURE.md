# AresBot 项目结构配置

## 项目目录结构

```
AresBot/
├── app.py                    # Flask 应用主文件
├── config.py                 # 配置文件
├── routes.py                 # 路由定义
├── trading.py                # 交易逻辑
├── database.py               # 数据库操作
├── crash_logger.py           # 崩溃日志
├── crypto_utils.py           # 加密工具
├── rate_limit_manager.py     # 速率限制管理
├── simple_logger.py          # 简单日志
├── migrate_db.py             # 数据库迁移
├── start.sh                  # 启动脚本
├── requirements.txt          # Python 依赖
├── readme.md                # 项目说明
├── LICENSE                   # 许可证
├── .gitignore               # Git 忽略文件
├── package-lock.json         # 包锁定文件
├── aresbot.db               # SQLite 数据库
├── encryption.key           # 加密密钥
│
├── exchanges/               # 交易所适配器
│   ├── __init__.py
│   ├── base.py              # 基础适配器类
│   ├── factory.py           # 交易所工厂
│   ├── polymarket_adapter.py
│   ├── polymarket_updown15m_adapter.py
│   ├── ccxt_backpack_spot_adapter.py
│   ├── ccxt_binance_futures_adapter.py
│   ├── backpack/
│   │   └── backpack_ws_account.py
│   └── binance/
│       └── alpha_token_list.py
│
├── notification/            # 通知模块
│   ├── __init__.py
│   ├── base.py              # 基础通知类
│   └── dingtalk.py          # 钉钉通知
│
├── templates/              # HTML 模板
│   ├── index.html
│   ├── login.html
│   ├── register.html
│   ├── change_password.html
│   └── ...
│
├── tests/                   # 测试文件
│   ├── README.md            # 测试说明
│   ├── test_stop_loss.py    # 止损功能测试
│   ├── verify_stop_loss.py  # 代码结构验证
│   ├── test_*.py            # 其他测试文件
│   └── ...
│
├── docs/                    # 文档目录
│   ├── STOP_LOSS_IMPLEMENTATION.md  # 止损实现文档
│   └── ...                  # 其他文档
│
├── examples/                # 示例代码
│   └── bpx-py/
│       ├── account_examples.py
│       └── public_example.py
│
├── tools/                   # 工具脚本
│   ├── get_polymarket_tokens.py
│   └── list_polymarket_markets.py
│
├── migrate/                 # 迁移脚本
│   └── migrate_credentials.py
│
├── changelog/               # 变更日志
│   └── *.md                # 各种变更日志
│
├── logs/                    # 日志目录
│   └── ...                  # 日志文件
│
└── __pycache__/             # Python 缓存
    └── ...
```

## 文件放置规则

### 测试文件
- **位置**: `tests/` 目录
- **命名**: `test_*.py` 或 `verify_*.py`
- **说明**: 所有测试相关的文件都应放在 tests/ 目录下

### 文档文件
- **位置**: `docs/` 目录
- **格式**: Markdown (.md) 文件
- **说明**: 项目文档、实现说明、API 文档等

### 工具脚本
- **位置**: `tools/` 目录
- **命名**: 功能相关的描述性名称
- **说明**: 辅助工具、脚本等

### 示例代码
- **位置**: `examples/` 目录
- **说明**: 使用示例、演示代码等

### 核心代码
- **位置**: 对应功能模块目录
- **说明**: 主要业务逻辑代码

## 重要提醒

1. **测试文件必须放在 `tests/` 目录**
2. **文档文件必须放在 `docs/` 目录**
3. **工具脚本必须放在 `tools/` 目录**
4. **示例代码必须放在 `examples/` 目录**
5. **不要在根目录创建临时文件**

## 开发规范

- 新功能开发时，同步创建对应的测试文件
- 重要功能需要编写文档说明
- 保持目录结构的整洁和一致性
- 遵循 Python 包管理规范
