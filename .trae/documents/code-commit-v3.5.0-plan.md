# 代码提交计划 (v3.5.0)

## 一、当前状态

### 1.1 分支状态

| 分支 | 最近提交 | 状态 |
|------|---------|------|
| develop | 53f6b23 fix(manage.sh): fix service status detection issues | 当前工作分支 |
| main | 6c8bbce Merge pull request #2 from pinglife80/hotfix/v3.3.1 | 生产分支 |

### 1.2 待提交变更统计

| 类型 | 数量 |
|------|------|
| 修改文件 | 35 |
| 新增文件 | 27 |
| 删除文件 | 20 |
| 新增目录 | 2 (auth_providers/, notification_channels/) |

### 1.3 变更内容分类

#### 新增功能
- **事件通知服务**：事件总线架构、多通知渠道（邮件/钉钉/企业微信/Webhook）、通知日志、测试连接
- **认证提供者系统**：插件化认证架构、本地认证、LDAP认证、认证提供者管理
- **SFTP备份服务**：数据库备份、配置文件备份、SFTP远程上传、备份轮转、校验和验证
- **系统设置前端页面**：通用设置、认证提供者、备份配置、通知管理、用户管理、角色管理

#### 安全修复
- 路径遍历漏洞修复（backup.py）
- LDAP DN注入防护（ldap_provider.py）
- 2FA验证码暴力破解防护（email_service.py）
- 敏感信息备份泄露修复（backup_service.py）
- FTP支持移除，强制SFTP
- SFTP主机密钥验证

#### 性能优化
- N+1查询优化（roles.py）
- 异步性能优化（backup_service.py）
- 通知模块权限控制
- Nginx限流调整

#### 文档更新
- API文档新增通知、认证提供者、备份章节
- 用户手册新增系统设置章节
- 架构文档和数据库文档更新
- 版本号统一升级至 v3.5.0

---

## 二、提交计划

### 2.1 提交策略

按照项目发布流程约定：
1. develop 分支开发完成 → release prepare commit
2. PR merge to main
3. 创建 annotated tag
4. sync back to develop branch

### 2.2 提交步骤

#### Step 1: 检查 gitignore

确保 `.trae/documents/` 目录中的临时文件已被正确忽略（已完成清理，仅保留 code_review_summary.md 和 project-update-v3.5.0-plan.md）

#### Step 2: 构建验证

```bash
# 后端构建验证
./manage.sh update

# 前端构建验证
cd frontend && npm run build
```

#### Step 3: 测试验证

```bash
# 运行单元测试
cd backend && python -m pytest tests/ -v
```

#### Step 4: 添加所有变更

```bash
git add -A
```

#### Step 5: 创建 Release Prepare Commit

```bash
git commit -m "release: prepare v3.5.0 release

## 新增功能

- 事件通知服务：事件总线架构、多通知渠道（邮件/钉钉/企业微信/Webhook）、通知日志
- 认证提供者系统：插件化认证架构、本地认证、LDAP认证
- SFTP备份服务：数据库备份、配置文件备份、SFTP远程上传、备份轮转
- 系统设置前端页面：通用设置、认证提供者、备份配置、通知管理

## 安全修复

- 路径遍历漏洞修复
- LDAP DN注入防护
- 2FA验证码暴力破解防护
- 敏感信息备份泄露修复
- FTP支持移除，强制SFTP

## 性能优化

- N+1查询优化
- 异步性能优化
- 通知模块权限控制
- Nginx限流调整

## 文档更新

- API文档新增通知、认证提供者、备份章节
- 用户手册新增系统设置章节
- 架构文档和数据库文档更新"
```

#### Step 6: Push to origin/develop

```bash
git push origin develop
```

#### Step 7: 创建 Pull Request

在 GitHub/GitLab 上创建从 develop 到 main 的 PR

#### Step 8: Merge PR to main

PR 审核通过后合并到 main 分支

#### Step 9: 创建 Annotated Tag

```bash
git tag -a "v3.5.0" -m "release v3.5.0: notification service, auth providers, backup service, security fixes"
git push origin v3.5.0
```

#### Step 10: Sync back to develop

```bash
git checkout develop
git merge main
git push origin develop
```

---

## 三、风险评估

| 风险 | 等级 | 应对措施 |
|------|------|---------|
| 构建失败 | 中 | 在提交前执行构建验证 |
| 测试失败 | 中 | 在提交前执行测试验证 |
| 代码冲突 | 低 | 提交前执行 git pull --rebase |
| 标签冲突 | 低 | 确保版本号唯一 |

---

## 四、验证标准

1. ✅ 所有变更已添加到暂存区
2. ✅ 后端构建成功
3. ✅ 前端构建成功
4. ✅ 单元测试通过
5. ✅ Commit message 符合 Conventional Commits 规范
6. ✅ PR 合并成功
7. ✅ Annotated tag 创建成功并推送
8. ✅ develop 分支同步更新