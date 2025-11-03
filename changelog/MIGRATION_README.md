# API凭证迁移指南

## 概述
本次更新将API密钥管理从配置表(`user_configs`)中分离出来,统一管理在`api_credentials`表中。

## 迁移步骤

### 1. 备份数据库
```bash
# 在运行迁移前,请先备份数据库
cp ares_bot.db ares_bot.db.backup
```

### 2. 运行迁移脚本
```bash
python migrate_credentials.py
```

### 3. 验证迁移结果
迁移脚本会输出统计信息:
- API凭证总数
- 已关联凭证的配置数量
- 未关联凭证的配置数量

### 4. 重启应用
```bash
python app.py
```

## 迁移内容

### 数据库变更
1. **user_configs表**
   - ❌ 删除列: `api_key`, `api_secret`
   - ✅ 新增列: `credential_id` (外键引用api_credentials表)

2. **api_credentials表** (已存在)
   - 存储所有用户的API密钥
   - 每个密钥有唯一的别名

### 迁移逻辑
1. 从`user_configs`表中提取所有唯一的`api_key`和`api_secret`组合
2. 为每个唯一组合在`api_credentials`表中创建记录
3. 自动生成别名格式: `{交易所}-{密钥前8位}`
4. 更新`user_configs`表,设置`credential_id`引用
5. 重建`user_configs`表,移除`api_key`和`api_secret`列

## 注意事项

⚠️ **重要提示:**
- 迁移后,旧的直接存储API密钥的方式将不再支持
- 所有配置必须通过`credential_id`引用密钥
- 如果有配置没有关联密钥,用户需要在"API密钥管理"页面重新选择

## 回滚方案

如果迁移出现问题,可以恢复备份:
```bash
# 停止应用
# 恢复备份
cp ares_bot.db.backup ares_bot.db
# 重启应用
python app.py
```

## 前端变更

### API密钥管理页面
- 显示所有用户的API密钥(不区分配置)
- 每个密钥有唯一别名
- 可以添加、编辑、删除密钥

### 交易配置页面
- 移除手动输入API密钥的选项
- 只能通过下拉框选择已保存的密钥
- 必须先在"API密钥管理"页面添加密钥才能使用

## 技术细节

### 密钥去重
迁移脚本会自动去重相同的API密钥:
- 使用`(user_id, exchange, api_key)`作为唯一键
- 相同的密钥只创建一次凭证记录
- 多个配置可以共享同一个凭证

### 别名冲突处理
如果生成的别名已存在,会自动添加序号:
- 第一个: `BINANCE-ABC12345`
- 第二个: `BINANCE-ABC12345-2`
- 第三个: `BINANCE-ABC12345-3`

## 验证清单

迁移完成后,请验证:
- [ ] 所有配置都能正常加载
- [ ] API密钥管理页面显示正常
- [ ] 可以正常保存新配置
- [ ] 可以正常启动机器人
- [ ] 旧配置的密钥已正确迁移
