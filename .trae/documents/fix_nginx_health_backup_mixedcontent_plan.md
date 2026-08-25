# 修复 nginx 健康检查、备份清理、Mixed Content 三个问题

## 问题分析

### 问题 1: nginx 健康检查不通过

**文件**: [docker-compose.yml:191](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.yml#L191)

**根因**: nginx 健康检查使用 `wget http://localhost:8080/`，在 prod 模式下：
- nginx 的 8080 端口是 HTTP server block，返回 `301 https://$host:8443$request_uri`
- wget 跟随重定向到 HTTPS `https://localhost:8443/`
- 因 SSL 自签名证书不受信任，wget 验证失败
- 导致健康检查超时，容器状态显示 `health: starting` 而非 `healthy`

**修复**: 修改健康检查命令，使用 `--no-check-certificate` 跳过 SSL 验证，直接请求 HTTPS 健康端点：
```
test: ["CMD-SHELL", "wget --no-verbose --tries=1 --spider --no-check-certificate https://localhost:8443/health || exit 1"]
```

### 问题 2: 备份文件清理

**文件**: [backup_service.py:942-956](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/backup_service.py#L942-L956)

**根因**: `_cleanup_old_backups()` 仅在备份完成后调用，但用户提到的 4 个历史无效备份文件可能是：
- 在代码修复前创建的备份（因 pg_dump 缺失等问题产生的空/无效备份）
- 保留天数配置过大
- 文件 mtime 不准确（容器卷挂载问题）

**修复方案**: 
1. 添加启动时一次性清理逻辑，删除大小为 0 或无效的备份文件
2. 在 cleanup 函数中添加文件大小检查，清理 0 字节文件

### 问题 3: Mixed Content HTTPS→HTTP (CRITICAL)

**文件**: [nginx/etc/conf.d/tam.conf](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/nginx/etc/conf.d/tam.conf)

**根因**: 浏览器日志显示：
```
GET http://10.8.25.121:8443/api/v1/notifications/channels 
(redirected from https://10.8.25.121:8443/api/v1/notifications/channels/)
```

这是 **trailing slash redirect** 问题：
1. 前端请求 `https://10.8.25.121:8443/api/v1/notifications/channels/` (带尾斜杠)
2. FastAPI/Starlette 自动将其重定向到 `/api/v1/notifications/channels` (不带尾斜杠)
3. 但重定向 URL 使用了 `http://` 而非 `https://`
4. 原因：后端不知道原始请求是 HTTPS（`X-Forwarded-Proto` 头虽已设置，但 FastAPI 默认不用它构建重定向 URL）

**修复方案**: 在 Nginx 的 `/api/` location 块中添加 `proxy_redirect http:// https://;`

这会将后端返回的所有 HTTP 重定向 Location 头重写为 HTTPS。

## 修改方案

### 修改 1: nginx 健康检查 (docker-compose.yml)

**文件**: `docker-compose.yml` L191

**Before**:
```yaml
test: ["CMD-SHELL", "wget --no-verbose --tries=1 --spider http://localhost:8080/ || exit 1"]
```

**After**:
```yaml
test: ["CMD-SHELL", "wget --no-verbose --tries=1 --spider --no-check-certificate https://localhost:8443/health || exit 1"]
```

### 修改 2: Nginx proxy_redirect (tam.conf)

**文件**: `nginx/etc/conf.d/tam.conf` L103-123

在 `/api/` location 块中添加 `proxy_redirect http:// https://;`

**Before** (L103-106):
```nginx
    location /api/ {
        limit_req zone=api_limit burst=30 nodelay;

        proxy_pass http://backend_api;
```

**After**:
```nginx
    location /api/ {
        limit_req zone=api_limit burst=30 nodelay;

        proxy_pass http://backend_api;
        proxy_redirect http:// https://;
```

同样需要在 auth 和 metrics 的 location 块中添加：
- `/api/v1/auth/login` location (L126-135)
- `/metrics` location (L138-149)

### 修改 3: 备份清理增强 (backup_service.py)

**文件**: `backend/app/services/backup_service.py` L948-954

在 `_cleanup_sync` 中添加文件大小检查，清理 0 字节或过小的备份文件：

**Before**:
```python
for filename in os.listdir(self.backup_dir):
    file_path = os.path.join(self.backup_dir, filename)
    if os.path.isfile(file_path):
        file_age = now - os.path.getmtime(file_path)
        if file_age > retention_seconds:
            os.remove(file_path)
            logger.info(f"Removed old local backup: {filename}")
```

**After**:
```python
for filename in os.listdir(self.backup_dir):
    file_path = os.path.join(self.backup_dir, filename)
    if os.path.isfile(file_path):
        file_size = os.path.getsize(file_path)
        file_age = now - os.path.getmtime(file_path)
        # Remove zero-byte or invalid backups regardless of age
        if file_size == 0:
            os.remove(file_path)
            logger.info(f"Removed empty backup file: {filename}")
        elif file_age > retention_seconds:
            os.remove(file_path)
            logger.info(f"Removed old local backup: {filename}")
```

## 验证步骤

1. **语法检查**:
   ```bash
   python3 -c "import ast; ast.parse(open('backend/app/services/backup_service.py').read())"
   ```

2. **重启服务**:
   ```bash
   ./manage.sh rebuild nginx
   ./manage.sh rebuild backend
   ```

3. **验证 nginx 健康检查**:
   ```bash
   ./manage.sh status
   ```
   预期 nginx 状态为 `Up (healthy)`

4. **验证 Mixed Content 修复**:
   在浏览器中访问 `https://10.8.25.121:8443/notifications`
   预期不再出现 Mixed Content 错误

5. **验证备份清理**:
   检查备份目录中 0 字节文件已被清理

## 风险评估

1. **proxy_redirect**: 低风险。仅重写后端返回的 Location 头中的协议，不影响正常代理请求。
2. **健康检查**: 低风险。使用 `--no-check-certificate` 仅跳过本地自签名证书验证。
3. **备份清理**: 低风险。仅添加 0 字节文件清理，不影响正常备份文件。
