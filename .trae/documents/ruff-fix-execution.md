# 执行 ruff check --fix 修复 CI 错误

> 文档版本：v3.3.0 | 更新日期：2026-06-17

## 当前状态

ruff 已安装到 `~/.local/bin/ruff`，运行 `ruff check app/ tests/` 检测到 244 个错误，其中 204 个可自动修复。

主要错误类型：
- I001: Import 排序问题（isort）
- F401: 未使用的 import
- F841: 未使用的局部变量
- UP017: `timezone.utc` → `datetime.UTC`
- 其他 UP 规则残留

## 实施步骤

### Step 1: 执行 ruff --fix

```bash
cd /home/dada/Codespace/TraeCN/TerminalAccessManager/backend
~/.local/bin/ruff check app/ tests/ --fix
```

### Step 2: 检查修复结果

```bash
~/.local/bin/ruff check app/ tests/
```

确认剩余错误数量，评估是否需要手动处理。

### Step 3: 如有 unsafe-fixes 需要处理

```bash
~/.local/bin/ruff check app/ tests/ --unsafe-fixes
```

评估 27 个 unsafe fixes 是否安全，酌情执行。

### Step 4: 提交并推送

```bash
git add -A
git commit -m "style(backend): apply ruff --fix for all auto-fixable lint errors"
git push origin develop
```
