# 移除测试文件中多余的 sys.path 操作

> 文档版本：v3.3.0 | 更新日期：2026-06-17

## 问题

3 个测试文件中有手动的 `sys.path.insert` 操作，但 CI 工作目录已经是 `backend/`，这些操作是多余的。

| 文件 | 当前代码 | 问题 |
|------|---------|------|
| `tests/conftest.py:9` | `sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))` | 多余，且在环境变量设置之前 |
| `tests/test_auth.py:13` | `sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))` | 多余 |
| `tests/test_app.py:11` | `sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))` | 多余且路径错误（多了一层 backend） |

## 修复方案

### conftest.py
- 移除 `sys.path.insert` 行
- 保留 `import os, sys`（`os` 用于环境变量设置，`sys` 可能被其他地方引用，但检查后如不需要也移除）
- 环境变量设置必须在 `from app.xxx import` 之前，当前顺序正确，移除 sys.path 不影响

### test_auth.py
- 移除 `sys.path.insert` 行
- 移除不再需要的 `import os, sys`

### test_app.py
- 移除 `sys.path.insert` 行
- 移除不再需要的 `import os, sys`

## 实施步骤

1. 编辑 3 个文件，移除 sys.path.insert 和不再需要的 import
2. 提交并推送
