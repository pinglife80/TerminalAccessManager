# 备份选项不生效问题修复计划

## 问题分析

经过代码审查，发现备份选项在实际备份任务中不生效的根因有以下几点：

### Bug 1（关键）：手动备份未加载已保存的配置

**位置**: [backup.py#L93-L120](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/api/v1/endpoints/backup.py#L93-L120)

`/backup/run` 端点通过依赖注入创建 `BackupService(db=db)`，但 **从未调用 `load_config()`**。这导致服务使用的是 `BackupConfig()` 的默认值（所有选项均为默认值），而非用户在界面上保存的实际配置。

对比 `scheduled_backup()` 在 [main.py#L461-L462](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/main.py#L461-L462) 中正确调用了 `load_config()`。

### Bug 2（关键）：白名单备份未受配置选项控制

**位置**: [backup_service.py#L210-L213](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/backup_service.py#L210-L213)

在 `run_backup()` 方法中：
- 数据库备份 ✅ 检查了 `self.config.backup_database`
- 配置备份 ✅ 检查了 `self.config.backup_config`
- 日志备份 ✅ 检查了 `self.config.backup_logs`
- **白名单备份 ❌ 没有检查 `self.config.backup_whitelist`**，始终执行

### Bug 3（关键）：白名单备份端点也未加载配置

**位置**: [backup.py#L123-L150](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/api/v1/endpoints/backup.py#L123-L150)

`/backup/whitelist` 端点同样未调用 `load_config()`，使用默认配置而非用户保存的配置。

### 已排除项

- **encrypt_backup 加密功能**：虽然 `encrypt_backup` 选项确实未被使用，但这是一个**新功能缺失**，不属于"选项不生效"的 bug 范畴。加密功能需要完整的密钥管理、备份恢复解密、向后兼容等设计，应作为独立需求处理。

---

## 修复方案

### 修改 1：在 `run_backup()` 中为白名单备份添加配置检查

**文件**: `backend/app/services/backup_service.py`

在 `run_backup()` 方法第 210-213 行，为白名单备份添加 `if self.config.backup_whitelist:` 条件检查，与其他备份选项保持一致：

```python
# 修改前：
if backup_type == "full" or backup_type == "whitelist":
    whitelist_path = await self.backup_whitelist(temp_dir)
    if whitelist_path:
        backup_files.append(whitelist_path)

# 修改后：
if backup_type == "full" or backup_type == "whitelist":
    if self.config.backup_whitelist:
        whitelist_path = await self.backup_whitelist(temp_dir)
        if whitelist_path:
            backup_files.append(whitelist_path)
```

### 修改 2：在手动备份 API 端点中加载配置

**文件**: `backend/app/api/v1/endpoints/backup.py`

在 `/backup/run` 和 `/backup/whitelist` 端点中，执行备份前先调用 `await backup_service.load_config()`，确保使用用户保存的配置：

```python
# /backup/run 端点：
config = await backup_service.load_config()
if not config.enabled:
    raise HTTPException(status_code=400, detail="Backup is disabled")
job = await backup_service.run_backup(backup_type=backup_type)

# /backup/whitelist 端点：
config = await backup_service.load_config()
if not config.enabled:
    raise HTTPException(status_code=400, detail="Backup is disabled")
job = await backup_service.run_backup(backup_type="whitelist")
```

---

## 涉及文件

| 文件 | 修改类型 | 修改内容 |
|------|----------|----------|
| `backend/app/services/backup_service.py` | 逻辑修复 | `run_backup()` 中白名单备份添加 `backup_whitelist` 检查 |
| `backend/app/api/v1/endpoints/backup.py` | 逻辑修复 | 两个端点添加 `load_config()` 调用 |

## 风险评估

- **低风险**：所有修改均为逻辑修复，让已有的选项真正生效
- **向后兼容**：修改后，如果用户之前没有显式关闭某项备份，行为与之前一致（默认值均为 True）
- **定时备份不受影响**：`scheduled_backup()` 已经正确调用 `load_config()`，本次修改不涉及

## 验证计划

1. 修改完成后重新构建项目
2. 在前端关闭"白名单备份"选项，保存配置
3. 触发手动备份 → 验证备份内容中无白名单数据
4. 开启"白名单备份"，关闭"数据库备份"
5. 触发手动备份 → 验证备份内容中有白名单但无数据库
6. 确认定时备份同样受选项控制
