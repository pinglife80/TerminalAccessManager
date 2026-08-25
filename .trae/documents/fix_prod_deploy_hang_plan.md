# 修复 prod 模式下部署卡住 + 后端日志 KeyError 问题

## 问题分析

### 报错现象
1. `./manage.sh deploy --prod` 卡在 "Verifying Deployment" 阶段
2. `./manage.sh status` 卡在 "Web Access" 阶段
3. `./manage.sh health` 卡在 "Web UI" 阶段
4. 后端日志持续报错：`KeyError: '"timestamp"'`

### 根因 1: loguru JSON 格式化冲突 (CRITICAL)

**文件**: [logging_config.py:67-92](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/core/logging_config.py#L67-L92)

`_json_format()` 返回一个 JSON 字符串，例如：
```json
{"timestamp": "2026-08-07T...", "level": "INFO", ...}
```

但 loguru 的 `format` 参数返回的字符串会被 loguru **二次格式化**（调用 `format_map(formatter_record)`）。JSON 中的 `{` 和 `}` 被 loguru 误认为是占位符。具体来说，`{"timestamp":` 中的 `{"timestamp"}` 被解析为名为 `"timestamp"`（**含双引号**）的占位符，而 record 中没有这个 key，导致 `KeyError: '"timestamp"'`。

**影响范围**：仅在 `ENVIRONMENT=production` 时触发（因为 `use_json = settings.ENVIRONMENT == "production"`）。dev 模式使用 `_log_format`，不受影响。

**修复方案**: 在 `_json_format` 返回的 JSON 字符串中，将所有 `{` 转义为 `{{`，`}` 转义为 `}}`。loguru 的 `format_map` 会将 `{{` → `{`，`}}` → `}`，最终输出正确的 JSON。

### 根因 2: manage.sh curl 命令无超时 (HIGH)

**文件**: [manage.sh](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/manage.sh) — 共 10 处 `curl` 调用

所有 Web 检查的 curl 命令均未设置 `--connect-timeout` 或 `--max-time`：
- L1002, L1005, L1011, L1014 (deploy verify)
- L1397, L1399 (status web access)
- L1515, L1518 (health web UI)
- L2134, L2136 (upgrade verify)

当 nginx 容器异常（如之前因 `cap_drop` 崩溃时），curl 连接 8443 端口可能因 TCP 连接建立后无响应而长时间挂起，导致脚本"卡住"。

**修复方案**: 为所有 10 处 curl 命令添加 `--connect-timeout 3 --max-time 5`。

### 两个问题的关联

1. nginx 因 `cap_drop: ALL` 缺少 `CHOWN` 而崩溃（已修复，添加了 `CHOWN`）
2. nginx 崩溃 → curl 检查无响应 → 脚本卡住
3. 同时，后端 loguru JSON 格式化 bug 在 production 模式下持续报错

## 修改方案

### 修改 1: 修复 loguru JSON 格式化 (CRITICAL)

**文件**: `backend/app/core/logging_config.py`
**函数**: `_json_format()` (L67-92)

在 `return` 语句前添加大括号转义：
```python
    result = json.dumps(log_data) + "\n"
    # Escape braces: loguru's format_map will interpret { } as placeholders.
    # Doubling them ({{ }}) makes format_map output literal { }.
    return result.replace("{", "{{").replace("}", "}}")
```

注意：json.dumps 输出的 JSON 字符串中，`{` 和 `}` 仅出现在 JSON 结构层（非字符串值内部），转义后 format_map 会还原为单个，输出正确 JSON。

### 修改 2: 为 manage.sh 所有 curl 检查添加超时 (HIGH)

**文件**: `manage.sh`

为以下 10 处 curl 命令添加 `--connect-timeout 3 --max-time 5`：

| 行号 | 函数 | 修改 |
|------|------|------|
| L1002 | cmd_deploy (dev HTTP) | `curl --connect-timeout 3 --max-time 5 -s ...` |
| L1005 | cmd_deploy (dev HTTPS) | `curl --connect-timeout 3 --max-time 5 -sk ...` |
| L1011 | cmd_deploy (prod HTTPS) | `curl --connect-timeout 3 --max-time 5 -sk ...` |
| L1014 | cmd_deploy (prod HTTP) | `curl --connect-timeout 3 --max-time 5 -s ...` |
| L1397 | cmd_status (HTTPS) | `curl --connect-timeout 3 --max-time 5 -sk ...` |
| L1399 | cmd_status (HTTP) | `curl --connect-timeout 3 --max-time 5 -s ...` |
| L1515 | cmd_health (HTTPS) | `curl --connect-timeout 3 --max-time 5 -sk ...` |
| L1518 | cmd_health (HTTP) | `curl --connect-timeout 3 --max-time 5 -s ...` |
| L2134 | cmd_upgrade (HTTPS) | `curl --connect-timeout 3 --max-time 5 -sk ...` |
| L2136 | cmd_upgrade (HTTP) | `curl --connect-timeout 3 --max-time 5 -s ...` |

## 验证步骤

1. Python 语法检查: `python3 -c "import ast; ast.parse(open('backend/app/core/logging_config.py').read())"`
2. Bash 语法检查: `bash -n manage.sh`
3. 重建 backend: `./manage.sh rebuild backend`
4. 检查后端日志无 KeyError: `./manage.sh logs backend --tail 20`
5. 运行 `./manage.sh status` — 不再卡住，快速返回结果
6. 运行 `./manage.sh health` — 不再卡住，快速返回结果
