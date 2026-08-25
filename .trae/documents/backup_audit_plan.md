# 备份管理功能全面审查报告与修复计划

## 审查方法

基于对以下所有相关文件的逐行代码审查：

* `backend/app/services/backup_service.py`（1193 行）

* `backend/app/api/v1/endpoints/backup.py`（481 行）

* `backend/app/models/backup_config.py`

* `backend/app/schemas/backup.py`

* `backend/app/main.py`（scheduled\_backup 部分）

* `frontend/src/pages/Backup.tsx`（748 行）

* `frontend/src/lib/constants.ts`

* `frontend/src/i18n/locales/zh.ts`

***

## 审查发现汇总

### 🔴 严重问题（P0）

#### 1. 前端表单 `backup_whitelist` 默认值缺失

**文件**: [Backup.tsx#L103-L115](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Backup.tsx#L103-L115)

`backup_whitelist` 未包含在 `defaultValues` 中。初始渲染时值为 `undefined`，若 API 调用失败则永远为 `undefined`，导致复选框显示为未勾选，提交时后端收到 `undefined`。

#### 2. `encrypt_backup` 选项从未生效

**文件**: [backup\_service.py#L180-L248](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/backup_service.py#L180-L248)

`encrypt_backup` 在 UI、模型、Schema、dataclass 中均有定义，但 `run_backup()` 中从未引用。

**决策（Option B）**：从 UI 暂时移除该选项，待后续版本实现真正的加密功能。后端字段保留以维持数据库兼容性。

#### 3. 备份恢复不完整：白名单和配置文件无法通过主恢复流程恢复

**文件**: [backup\_service.py#L893-L916](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/backup_service.py#L893-L916)

`restore_backup()` 恢复：

* ✅ `database.sql`（如存在）

* ✅ `system_config.json`

* ✅ `branding.zip`

* ❌ 没有恢复 whitelist 数据

* ❌ 没有恢复 config 文件（docker-compose.yml, manage.sh）

备份归档内部结构：

```
database.sql
config.zip           → config/docker-compose.yml, config/manage.sh
system_config.json    → 直接存放系统配置 JSON
branding.zip          → branding/* 资源文件
whitelist.zip         → whitelist/whitelist.json
logs.zip              → *.log 文件
```

`restore_backup()` 解压主归档后，`whitelist.zip` 和 `config.zip` 是嵌套 zip 文件，需要二次解压才能读取内容。

#### 4. 恢复操作无事务保护

**文件**: [backup\_service.py#L471-L565](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/backup_service.py#L471-L565)

`_restore_system_config_db()` 采用"先删后增"但无事务保护，中途失败会导致数据不一致。

### 🟡 中等问题（P1）

#### 5. `scheduled_backup()` 硬编码使用 "full" 类型

**文件**: [main.py#L482](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/main.py#L482)

#### 6. 手动备份结果未写入审计日志

#### 7. 历史备份清理仅清理本地文件

#### 8. `_backup_database()` 在 PostgreSQL 未配置时静默成功

### 🟢 轻微问题（P2）

#### 9. `create_archive()` 使用 basename 可能导致文件名冲突

#### 10. 日志备份无恢复逻辑

#### 11. `_backup_config()` 备份内容有限

#### 12. 备份任务结果持久化不足

***

## 修复计划

### P0 修复

#### 修复 1：前端 `defaultValues` 补充 `backup_whitelist`

**文件**: `frontend/src/pages/Backup.tsx#L103-L115`

在 `defaultValues` 中添加 `backup_whitelist: true`。

#### 修复 2：移除前端 `encrypt_backup` UI 选项

**文件**: `frontend/src/pages/Backup.tsx`

移除 encrypt\_backup 复选框（约 L493-L496）及相关注册代码。后端字段保留。

#### 修复 3：`restore_backup()` 增加白名单和配置文件恢复

**文件**: `backend/app/services/backup_service.py`

在 `restore_backup()` 方法中增加对嵌套 zip 文件的处理：

```python
# 在 restore_backup() 中，现有恢复逻辑之后添加：

# 白名单恢复：whitelist.zip 是嵌套 zip，需要二次解压
whitelist_zip = os.path.join(temp_dir, "whitelist.zip")
if os.path.exists(whitelist_zip):
    await self._restore_whitelist_from_zip(whitelist_zip)

# 配置文件恢复：config.zip 包含 docker-compose.yml, manage.sh
config_zip = os.path.join(temp_dir, "config.zip")
if os.path.exists(config_zip):
    # 配置文件解压到备份目录供下载参考
    config_extract_dir = os.path.join(self.backup_dir, "_restored_config")
    os.makedirs(config_extract_dir, exist_ok=True)
    with zipfile.ZipFile(config_zip, "r") as zipf:
        zipf.extractall(config_extract_dir)
    logger.info(f"Config files extracted to {config_extract_dir} for reference")
```

新增辅助方法：

```python
async def _restore_whitelist_from_zip(self, zip_path: str) -> bool:
    """Extract nested whitelist.zip and restore"""
    with tempfile.TemporaryDirectory() as whitelist_temp:
        with zipfile.ZipFile(zip_path, "r") as zipf:
            zipf.extractall(whitelist_temp)
        whitelist_file = os.path.join(whitelist_temp, "whitelist", "whitelist.json")
        if os.path.exists(whitelist_file):
            return await self._restore_whitelist_from_json(whitelist_file)
    return False

async def _restore_whitelist_from_json(self, json_path: str) -> bool:
    """Restore whitelist from extracted JSON file"""
    if self.db is None:
        return False
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            whitelist_data = json.load(f)
        await self.db.execute(Whitelist.__table__.delete())
        for item in whitelist_data:
            obj = Whitelist(
                mac_address=item.get("mac_address"),
                mac_address_normalized=item.get("mac_address_normalized"),
                ip_pattern=item.get("ip_pattern"),
                pattern_type=item.get("pattern_type", "single_ip"),
                comments=item.get("comments"),
                added_by=item.get("added_by", "system"),
            )
            self.db.add(obj)
        await self.db.commit()
        # Trigger compliance recalculation
        from app.services.compliance_service import recalculate_all_compliance
        await recalculate_all_compliance(self.db)
        return True
    except Exception as e:
        await self.db.rollback()
        logger.error(f"Failed to restore whitelist from JSON: {e}")
        return False
```

#### 修复 4：`_restore_system_config_db()` 添加事务保护

**文件**: `backend/app/services/backup_service.py`

使用 `begin_nested()` 为每个表创建 savepoint：

```python
async def _restore_system_config_db(self, temp_dir: str) -> bool:
    config_file = os.path.join(temp_dir, "config", "system_config.json")
    if not os.path.exists(config_file):
        return False
    if self.db is None:
        return False

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config_data = json.load(f)

        restore_sections = [
            ("system_config", SystemConfig, lambda item: SystemConfig(**item)),
            ("notification_channels", NotificationChannel, lambda item: NotificationChannel(
                name=item["name"], type=item["type"], config=item["config"],
                enabled=item["enabled"], events=item["events"],
                description=item.get("description"),
            )),
            ("notification_rules", NotificationRule, lambda item: NotificationRule(
                name=item["name"], event_type=item["event_type"],
                channel_name=item["channel_name"], enabled=item["enabled"],
                priority=item.get("priority", 100), description=item.get("description"),
                suppress_enabled=item.get("suppress_enabled", False),
                suppress_window=item.get("suppress_window", 300),
                escalate_enabled=item.get("escalate_enabled", False),
                escalate_threshold=item.get("escalate_threshold", 5),
                escalate_window=item.get("escalate_window", 3600),
                escalate_severity=item.get("escalate_severity", "error"),
            )),
            ("notification_templates", NotificationTemplate, lambda item: NotificationTemplate(
                name=item["name"], event_type=item["event_type"],
                channel_type=item["channel_type"], subject=item.get("subject"),
                body=item.get("body"), is_default=item.get("is_default", False),
            )),
            ("auth_providers", AuthConfig, lambda item: AuthConfig(
                name=item["name"], provider_type=item["provider_type"],
                config=item["config"], enabled=item["enabled"],
                priority=item.get("priority", 100),
            )),
            ("datasource", DataSource, lambda item: DataSource(
                name=item["name"], type=item["type"],
                config=item["config"], enabled=item["enabled"],
            )),
        ]

        for section, model, factory in restore_sections:
            if section not in config_data:
                continue
            savepoint = await self.db.begin_nested()
            try:
                await self.db.execute(model.__table__.delete())
                for item in config_data[section]:
                    self.db.add(factory(item))
                await savepoint.commit()
            except Exception as e:
                await savepoint.rollback()
                logger.error(f"Failed to restore {section}: {e}")
                raise

        await self.db.commit()
        logger.info("System config restoration completed")
        return True
    except Exception as e:
        await self.db.rollback()
        logger.error(f"Failed to restore system config: {e}")
        return False
```

### P1 修复

#### 修复 5：数据库未配置时抛出异常

**文件**: `backend/app/services/backup_service.py#L259-L263`

```diff
 if not hasattr(settings, 'POSTGRES_SERVER') or not settings.POSTGRES_SERVER:
-    logger.warning("PostgreSQL not configured, skipping database backup")
-    with open(backup_path, "w") as f:
-        f.write("-- PostgreSQL not configured\n")
-    return backup_path
+    raise Exception("PostgreSQL not configured, cannot backup database")
```

#### 修复 6：手动备份结果追加审计日志

**文件**: `backend/app/api/v1/endpoints/backup.py#L93-L122`

在 `run_backup` 端点中，备份完成后追加审计日志，记录完整备份结果。

#### 修复 7：远程备份清理

**文件**: `backend/app/services/backup_service.py`

在 `cleanup_old_backups()` 中增加远程清理：

```python
# 在现有本地清理之后添加：
if self.config.storage_type != "local":
    remote_backups = await self.list_remote_backups()
    retention_seconds = self.config.retention_days * 24 * 60 * 60
    now = time.time()
    for rb in remote_backups:
        if rb.get("created_at"):
            created_ts = rb["created_at"].timestamp() if hasattr(rb["created_at"], "timestamp") else now
            if now - created_ts > retention_seconds:
                await self.delete_from_remote(rb["filename"])
                logger.info(f"Removed old remote backup: {rb['filename']}")
```

### P2 修复

#### 修复 8：日志备份增加恢复逻辑

**文件**: `backend/app/services/backup_service.py`

在 `restore_backup()` 中增加日志恢复：

```python
# 在白名单恢复之后添加：
logs_zip = os.path.join(temp_dir, "logs.zip")
if os.path.exists(logs_zip):
    await self._restore_logs_from_zip(logs_zip)
```

新增 `_restore_logs_from_zip()` 方法。

#### 修复 9：`_backup_config()` 增加更多配置文件

**文件**: `backend/app/services/backup_service.py#L311-L314`

```python
config_files = [
    "docker-compose.yml",
    "manage.sh",
    "nginx.conf",
    "alembic.ini",
]
```

#### 修复 10：备份结果审计日志增强

**文件**: `backend/app/api/v1/endpoints/backup.py` + `backend/app/main.py`

在审计日志中增加备份选项详情，便于后续排查：

```python
{
    "status": job.status,
    "file_path": job.file_path,
    "file_size": job.file_size,
    "backup_type": backup_type,
    "checksum": job.checksum,
    "error_message": job.error_message,
    "options": {
        "database": config.backup_database,
        "config": config.backup_config,
        "whitelist": config.backup_whitelist,
        "logs": config.backup_logs,
    }
}
```

***

## 涉及文件汇总

| 文件                                       | 操作 | 优先级          | 修改内容                                             |
| ---------------------------------------- | -- | ------------ | ------------------------------------------------ |
| `frontend/src/pages/Backup.tsx`          | 修改 | P0           | 补充 `backup_whitelist` 默认值；移除 `encrypt_backup` UI |
| `backend/app/services/backup_service.py` | 修改 | P0 + P1 + P2 | 白名单恢复；事务保护；PostgreSQL 异常处理；远程清理；日志恢复；配置文件扩展      |
| `backend/app/api/v1/endpoints/backup.py` | 修改 | P0 + P1 + P2 | load\_config 修复；审计日志增强                           |
| `backend/app/main.py`                    | 修改 | P2           | scheduled\_backup 审计日志增强                         |

## 风险评估

* **P0 修复**：低\~中风险

  * 补充默认值：零风险

  * 移除 encrypt\_backup UI：低风险（后端字段保留）

  * 白名单恢复：中风险（需正确处理嵌套 zip）

  * 事务保护：中风险（`begin_nested()` 需 SQLAlchemy 2.0+）

* **P1 修复**：中风险

  * PostgreSQL 异常处理：改变现有行为

  * 审计日志追加：需确保不重复记录

  * 远程清理：需确保 FTP/SFTP 删除逻辑正确

* **P2 修复**：低风险

  * 日志恢复：新增功能，不影响现有流程

  * 配置文件扩展：新增文件到备份列表

  * 审计日志增强：追加字段，不影响现有逻辑

