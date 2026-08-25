# 备份管理闭环完善方案

## 概述

根据系统业务功能全面评估，备份管理需要完整覆盖以下范围：

| 备份类型 | 说明 | 优先级 |
|----------|------|--------|
| 数据库备份 | PostgreSQL 全库备份（终端、白名单、黑名单、审计日志等） | P0 |
| 系统配置备份 | system_config 表（安全、调度、品牌、邮件等） | P0 |
| 通知渠道备份 | notification_channels 表（邮件、飞书、钉钉等渠道配置） | P0 |
| 认证配置备份 | auth_providers 表（LDAP、本地认证等） | P0 |
| 数据源配置备份 | datasource 表（Sangfor、Switch 等数据源） | P0 |
| 品牌资源备份 | login_bg、favicon 等上传文件 | P1 |
| 白名单独立备份 | 白名单数据单独备份和恢复 | P1 |
| 日志备份 | 系统日志文件（可选） | P2 |

---

## 现状深度分析

### 当前系统配置结构

**数据库表配置：**

| 表名 | 内容 | 是否需要备份 |
|------|------|--------------|
| `system_config` | 安全策略、调度配置、品牌配置、邮件配置、通用配置 | ✅ 是 |
| `notification_channels` | 通知渠道（邮件、飞书、钉钉、企业微信、Webhook） | ✅ 是 |
| `notification_rules` | 通知规则（事件订阅） | ✅ 是 |
| `notification_templates` | 通知模板 | ✅ 是 |
| `auth_providers` | 认证提供者（本地、LDAP） | ✅ 是 |
| `datasource` | 数据源配置（Sangfor、Switch、IpGuard） | ✅ 是 |
| `roles` | 用户角色 | ✅ 是 |
| `permissions` | 权限定义 | ✅ 是 |
| `users` | 用户信息（密码已加密） | ✅ 是 |

**文件资源：**

| 路径 | 内容 | 是否需要备份 |
|------|------|--------------|
| `/app/uploads/branding/` | 品牌资源（login_bg、favicon） | ✅ 是 |
| `/app/uploads/` | 其他上传文件 | ✅ 是 |
| `/var/log/tam/` | 系统日志 | ⚠️ 可选 |

### 当前备份功能缺陷

1. **配置备份不完整**：仅备份 docker-compose.yml 和 manage.sh，缺失数据库中的系统配置
2. **无品牌资源备份**：login_bg、favicon 等品牌自定义资源未备份
3. **无白名单独立备份**：无法单独备份/恢复白名单数据
4. **恢复功能有限**：仅支持全库恢复，无选择性恢复
5. **前端功能不完整**：缺少备份类型选择、备份内容展示、恢复确认等

---

## 解决方案

### 一、备份架构设计

#### 1.1 备份文件结构

```
tam_backup_20260708_120000.zip
├── manifest.json          # 备份清单和校验信息
├── database/
│   └── database.sql       # PostgreSQL 数据库完整备份
├── config/
│   ├── docker-compose.yml # Docker Compose 配置
│   ├── manage.sh          # 管理脚本
│   └── system_config.json # 系统配置 JSON（system_config 表导出）
├── branding/              # 品牌资源文件
│   ├── login_bg.jpg
│   └── favicon.ico
├── whitelist/             # 白名单独立备份
│   └── whitelist.json
└── logs/                  # 日志文件（可选）
    └── app.log
```

#### 1.2 manifest.json 格式

```json
{
    "version": "3.6.9",
    "created_at": "2026-07-08T12:00:00Z",
    "backup_type": "full",
    "contents": {
        "database": true,
        "config": true,
        "branding": true,
        "whitelist": true,
        "logs": false
    },
    "checksum": "sha256:...",
    "size_bytes": 1048576
}
```

### 二、后端服务层增强

#### 2.1 系统配置备份

**文件**：`backend/app/services/backup_service.py`

**新增方法**：
```python
async def _backup_system_config_db(self, temp_dir: str) -> str:
    """从 database 导出 system_config、notification_channels、auth_providers、datasource 等配置表"""

async def _restore_system_config_db(self, temp_dir: str) -> bool:
    """恢复 system_config、notification_channels、auth_providers、datasource 等配置表"""
```

**备份内容**：
- `system_config` - 安全、调度、品牌、邮件配置
- `notification_channels` - 通知渠道
- `notification_rules` - 通知规则
- `notification_templates` - 通知模板
- `auth_providers` - 认证提供者
- `datasource` - 数据源配置
- `roles` - 用户角色
- `permissions` - 权限定义

#### 2.2 品牌资源备份

**文件**：`backend/app/services/backup_service.py`

**新增方法**：
```python
async def _backup_branding(self, temp_dir: str) -> str:
    """备份品牌资源文件（login_bg、favicon 等）"""

async def _restore_branding(self, temp_dir: str) -> bool:
    """恢复品牌资源文件"""
```

#### 2.3 白名单独立备份

**文件**：`backend/app/services/backup_service.py`

**新增方法**：
```python
async def backup_whitelist(self, temp_dir: str) -> str:
    """导出白名单为 JSON 文件"""

async def restore_whitelist(self, file_path: str) -> bool:
    """从 JSON 文件恢复白名单"""
```

#### 2.4 备份类型支持

**修改 `_backup_files` 方法**：
```python
async def _backup_files(self, temp_dir: str, config: BackupConfig) -> str:
    """根据配置备份指定类型的文件"""
    # 根据 backup_type 参数决定备份内容
    if config.backup_type == "full":
        await self._backup_database(temp_dir)
        await self._backup_config_files(temp_dir)
        await self._backup_system_config_db(temp_dir)
        await self._backup_branding(temp_dir)
        if config.backup_logs:
            await self._backup_logs(temp_dir)
    elif config.backup_type == "config":
        await self._backup_config_files(temp_dir)
        await self._backup_system_config_db(temp_dir)
        await self._backup_branding(temp_dir)
    elif config.backup_type == "whitelist":
        await self.backup_whitelist(temp_dir)
    elif config.backup_type == "database":
        await self._backup_database(temp_dir)
```

### 三、后端 API 层增强

#### 3.1 新增白名单备份端点

**文件**：`backend/app/api/v1/endpoints/backup.py`

```python
@router.post("/whitelist", response_model=BackupJobResponse)
async def create_whitelist_backup(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("backup_create"))
):
    """创建白名单专用备份"""

@router.get("/whitelist/list", response_model=BackupListResponse)
async def get_whitelist_backups(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("backup_view"))
):
    """获取白名单备份列表"""

@router.post("/whitelist/restore/{filename}", response_model=BackupRestoreResponse)
async def restore_whitelist_backup(
    filename: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("backup_restore"))
):
    """从白名单备份恢复"""
```

#### 3.2 新增备份内容查询端点

**文件**：`backend/app/api/v1/endpoints/backup.py`

```python
@router.get("/{filename}/contents", response_model=dict)
async def get_backup_contents(
    filename: str,
    current_user: User = Depends(require_permission("backup_view"))
):
    """获取备份文件包含的内容清单"""
```

#### 3.3 备份类型参数支持

**修改 `create_backup` 端点**：
```python
@router.post("/", response_model=BackupJobResponse)
async def create_backup(
    config: BackupConfig,
    backup_type: str = Query("full", enum=["full", "database", "config", "whitelist", "logs"]),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("backup_create"))
):
    """创建备份，支持多种备份类型"""
```

### 四、前端页面完善

#### 4.1 备份类型选择器

**文件**：`frontend/src/pages/Backup.tsx`

```tsx
<select value={backupType} onChange={handleBackupTypeChange}>
    <option value="full">{t('backup.backupType.full')}</option>
    <option value="database">{t('backup.backupType.database')}</option>
    <option value="config">{t('backup.backupType.config')}</option>
    <option value="whitelist">{t('backup.backupType.whitelist')}</option>
    <option value="logs">{t('backup.backupType.logs')}</option>
</select>
```

#### 4.2 白名单备份模块

**文件**：`frontend/src/pages/Backup.tsx`

新增独立区域，包含：
- 白名单备份列表（独立展示）
- 创建白名单备份按钮
- 恢复/删除操作
- 备份内容预览

#### 4.3 备份详情和恢复确认

**文件**：`frontend/src/pages/Backup.tsx`

新增确认对话框，显示：
- 备份文件包含的内容清单
- 备份时间和大小
- 恢复将覆盖的数据提示
- 二次确认按钮

#### 4.4 备份设置优化

**文件**：`frontend/src/pages/Backup.tsx`

增强备份设置面板：
- 备份类型配置（全量/数据库/配置/白名单/日志）
- 品牌资源备份开关
- 通知渠道备份开关
- 认证配置备份开关

### 五、i18n 完整覆盖

#### 5.1 中文翻译

**文件**：`frontend/src/i18n/locales/zh.ts`

新增翻译项：
```ts
backup: {
    // ... 现有翻译 ...
    backupType: {
        full: '全量备份',
        database: '数据库备份',
        config: '配置备份',
        whitelist: '白名单备份',
        logs: '日志备份',
    },
    whitelistBackup: {
        title: '白名单备份',
        description: '白名单数据独立备份和恢复',
        createWhitelistBackup: '创建白名单备份',
        whitelistBackups: '白名单备份列表',
        restoreWhitelist: '恢复白名单',
    },
    backupContents: {
        title: '备份内容',
        database: '数据库',
        config: '配置文件',
        systemConfig: '系统配置',
        notificationChannels: '通知渠道',
        authProviders: '认证配置',
        datasource: '数据源配置',
        branding: '品牌资源',
        whitelist: '白名单',
        logs: '日志文件',
    },
    restoreConfirm: {
        title: '恢复确认',
        warning: '恢复将覆盖当前系统数据，请确保已备份当前状态',
        confirm: '确认恢复',
        cancel: '取消',
    },
}
```

#### 5.2 英文翻译

**文件**：`frontend/src/i18n/locales/en.ts`

同步新增英文翻译项。

---

## 实施步骤

### 阶段一：后端服务层增强

| Step | 文件 | 修改内容 | 风险 |
|------|------|----------|------|
| 1.1 | `backup_service.py` | 新增 `_backup_system_config_db` 方法 | 低 |
| 1.2 | `backup_service.py` | 新增 `_restore_system_config_db` 方法 | 中（可能覆盖配置） |
| 1.3 | `backup_service.py` | 新增 `_backup_branding` 方法 | 低 |
| 1.4 | `backup_service.py` | 新增 `_restore_branding` 方法 | 中（可能覆盖文件） |
| 1.5 | `backup_service.py` | 新增白名单备份/恢复方法 | 低 |
| 1.6 | `backup_service.py` | 修改 `_backup_files` 支持备份类型 | 低 |

### 阶段二：后端 API 层增强

| Step | 文件 | 修改内容 | 风险 |
|------|------|----------|------|
| 2.1 | `backup.py` | 新增白名单备份端点 | 低 |
| 2.2 | `backup.py` | 新增备份内容查询端点 | 低 |
| 2.3 | `backup.py` | 修改 `create_backup` 支持备份类型 | 低 |
| 2.4 | `schemas/backup.py` | 新增备份类型相关 Schema | 低 |

### 阶段三：前端页面完善

| Step | 文件 | 修改内容 | 风险 |
|------|------|----------|------|
| 3.1 | `Backup.tsx` | 新增备份类型选择器 | 低 |
| 3.2 | `Backup.tsx` | 新增白名单备份模块 | 低 |
| 3.3 | `Backup.tsx` | 新增备份详情和恢复确认对话框 | 低 |
| 3.4 | `Backup.tsx` | 增强备份设置面板 | 低 |

### 阶段四：i18n 覆盖

| Step | 文件 | 修改内容 | 风险 |
|------|------|----------|------|
| 4.1 | `zh.ts` | 新增中文翻译项 | 低 |
| 4.2 | `en.ts` | 新增英文翻译项 | 低 |

---

## Docker Compose 环境适配

### 备份存储路径

**当前配置**（[docker-compose.yml](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.yml)）：
```yaml
volumes:
  - tam-logs:/var/log/tam
  - tam-uploads:/app/uploads
```

**备份路径**：`/app/backups/`（已在 backup_service.py 中定义）

### Docker 环境下的备份执行

由于系统运行在 Docker Compose 环境中，备份执行方式：
1. **手动备份**：通过前端 UI 触发，后端在容器内执行备份
2. **定时备份**：通过 `manage.sh` 定时任务执行，或通过前端配置的 cron 调度

### manage.sh 集成

**文件**：`manage.sh`

可考虑新增命令：
```bash
./manage.sh backup [full|database|config|whitelist]
./manage.sh restore <backup_file> [--type <type>]
```

---

## 风险评估

### 高风险项

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 配置恢复覆盖关键设置 | 可能导致系统不可用 | 恢复前自动备份当前配置；提供恢复预览；支持选择性恢复 |
| 品牌资源文件冲突 | 覆盖自定义品牌 | 使用文件名哈希；恢复前提示文件覆盖 |
| 白名单恢复数据重复 | 数据一致性问题 | 恢复前清除现有白名单；提供合并选项 |

### 中风险项

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 备份文件过大 | 存储和传输问题 | 支持选择性备份；gzip 压缩；日志备份可选 |
| 恢复过程中系统中断 | 数据损坏 | 使用事务；恢复前锁定备份文件；增量恢复 |
| 通知渠道配置敏感信息 | 安全风险 | 配置数据已加密存储；备份文件可加密 |

### 低风险项

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| i18n 翻译遗漏 | 用户体验问题 | 完整覆盖中英文翻译；翻译校验 |
| 前端功能兼容性 | 浏览器兼容性 | 使用标准 React 组件；测试主流浏览器 |

---

## 验证方案

### 配置备份验证

**步骤**：
1. 修改系统配置（安全策略、邮件配置、品牌资源）
2. 创建全量备份
3. 修改通知渠道配置
4. 创建配置备份
5. 恢复配置备份，验证系统配置和通知渠道恢复正确
6. 验证品牌资源文件恢复正确

### 白名单备份验证

**步骤**：
1. 创建多个白名单条目
2. 创建白名单独立备份
3. 修改/删除白名单数据
4. 恢复白名单备份
5. 验证白名单数据完整性
6. 验证终端管理中备注信息同步正确

### 前端功能验证

**步骤**：
1. 测试所有备份类型选择（全量/数据库/配置/白名单/日志）
2. 测试白名单备份列表和操作
3. 测试备份内容详情展示
4. 测试恢复确认对话框
5. 测试备份设置面板
6. 测试中英文切换

### Docker 环境验证

**步骤**：
1. 使用 `./manage.sh update` 重建服务
2. 使用 `./manage.sh test` 运行测试
3. 使用 `./manage.sh health` 验证服务健康
4. 创建备份并验证文件生成
5. 恢复备份并验证系统功能

---

## 文件修改清单

| 文件 | 修改内容 |
|------|----------|
| `backend/app/services/backup_service.py` | 增强配置备份/恢复、品牌资源备份/恢复、白名单备份/恢复、支持备份类型 |
| `backend/app/api/v1/endpoints/backup.py` | 新增白名单备份端点、备份内容查询端点、支持备份类型参数 |
| `backend/app/schemas/backup.py` | 新增备份类型相关 Schema |
| `frontend/src/pages/Backup.tsx` | 备份类型选择器、白名单备份模块、备份详情、恢复确认对话框 |
| `frontend/src/i18n/locales/zh.ts` | 新增备份类型、白名单备份、备份内容、恢复确认等翻译 |
| `frontend/src/i18n/locales/en.ts` | 同步新增英文翻译 |
