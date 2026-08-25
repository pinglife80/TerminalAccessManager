# 修复品牌资源上传后加载报 403 错误

> 文档版本：v1.0  更新日期：2026-08-10

---

## 一、问题现象

用户通过系统设置上传自定义品牌资源（登录页背景图、favicon 图标）后，前端加载这些资源时浏览器返回 **403 Forbidden**，导致背景图和图标无法显示。

- 开发环境（localhost）正常
- 生产环境（通过 IP 地址访问）必现

---

## 二、根因分析

### 请求链路

1. 用户通过 `https://<IP>:8443/login` 访问登录页
2. [Login.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Login.tsx#L86-L88) 从 `/api/v1/settings/branding` 获取 `login_bg_url = "/uploads/login_bg_xxxx.jpg"`
3. 浏览器渲染 `backgroundImage: url(/uploads/login_bg_xxxx.jpg)`，发起 `GET https://<IP>:8443/uploads/login_bg_xxxx.jpg`
4. 浏览器自动携带 `Referer: https://<IP>:8443/login`

### Nginx 配置拦截

[tam.conf.template](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/nginx/etc/conf.d/tam.conf.template#L157-L178) 中 `/uploads/` location 配置了 Referer 检查：

```nginx
location /uploads/ {
    proxy_pass http://backend_api;
    ...
    valid_referers none blocked server_names ~\.localhost ~localhost;
    if ($invalid_referer) {
        return 403;
    }
}
```

### 403 触发逻辑

`valid_referers` 规则逐一匹配失败：

| 规则 | 说明 | 匹配结果 |
|------|------|----------|
| `none` | 无 Referer | ❌ 浏览器发送了 Referer |
| `blocked` | Referer 被代理修改 | ❌ Referer 完整 |
| `server_names` | 匹配 `server_name` 的值 | ❌ `server_name _`，无法匹配实际 IP |
| `~\.localhost` | 正则匹配 localhost | ❌ 生产环境 Referer 是 IP |
| `~localhost` | 正则匹配 localhost | ❌ 同上 |

→ `$invalid_referer = 1` → `return 403`

### 为什么开发环境正常

开发环境通过 `localhost:8080` / `localhost:8443` 访问，Referer 包含 `localhost`，匹配 `~localhost` 规则，不会触发 403。

---

## 三、修复方案

### 修改文件

[tam.conf.template](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/nginx/etc/conf.d/tam.conf.template#L157-L178)

### 修改内容

删除 `valid_referers` 检查块（L172-L177），同时更新 location 注释：

```nginx
# Serve uploaded branding assets (login bg, favicon)
# Filenames are UUID-based, preventing URL guessing
location /uploads/ {
    proxy_pass http://backend_api;
    proxy_http_version 1.1;
    proxy_set_header Host $host:$server_port;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # Cache uploaded assets
    expires 7d;
    add_header Cache-Control "public";
    add_header X-Content-Type-Options "nosniff" always;
}
```

### 安全性评估

移除 Referer 检查不影响安全性，原因：

1. **文件名不可猜测**：[settings.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/api/v1/endpoints/settings.py#L266) 使用 `uuid.uuid4().hex` 生成文件名（如 `login_bg_8a7b6c5d4e3f...jpg`），128 位随机性
2. **资源本身是公开内容**：登录页背景和 favicon 在登录页公开展示，无需访问控制
3. **Referer 检查不可靠**：Referer 可被客户端伪造，作为安全机制价值有限
4. **配置与实际部署矛盾**：`server_name _` 通配符无法匹配任何实际域名/IP，`valid_referers` 中的 `server_names` 规则永远无法生效

---

## 四、验证步骤

```bash
# 1. 重建 nginx 容器使配置生效
./manage.sh update

# 2. 验证品牌资源加载
# 浏览器访问 https://<IP>:8443/login
# 检查 DevTools Network 面板：
#   - /uploads/login_bg_xxx.jpg → 200 OK（非 403）
#   - 背景图正确显示
#   - favicon 正确显示

# 3. 验证直接访问资源 URL 也正常
# 浏览器直接打开 https://<IP>:8443/uploads/login_bg_xxx.jpg → 200 OK

# 4. 验证缓存头正确
curl -I https://localhost:8443/uploads/login_bg_xxx.jpg
# 预期：HTTP/2 200, Cache-Control: public, Expires: 7d后
```
