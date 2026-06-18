# 修复 CI frontend-build 失败 — 根因：.gitignore 忽略了前端 lib 文件

## 根因分析

根目录 [.gitignore](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/.gitignore#L16) 第 16 行的 `lib/` 模式（无前导 `/`）会匹配项目中**任何层级**名为 `lib` 的目录，包括 `frontend/src/lib/`。

**验证结果**（`git check-ignore -v`）：
```
.gitignore:16:lib/      frontend/src/lib/api.ts
.gitignore:16:lib/      frontend/src/lib/utils.ts
.gitignore:16:lib/      frontend/src/lib/__tests__/utils.test.ts
```

**git 跟踪状态**（`git ls-files frontend/src/lib/`）：
| 文件 | git 跟踪 | 原因 |
|---|---|---|
| `constants.ts` | ✅ 已跟踪 | 在 `lib/` 规则添加前就已提交 |
| `logger.ts` | ✅ 已跟踪 | 同上 |
| `api.ts` | ❌ 未跟踪 | 被 `.gitignore:16:lib/` 忽略 |
| `utils.ts` | ❌ 未跟踪 | 被 `.gitignore:16:lib/` 忽略 |
| `__tests__/utils.test.ts` | ❌ 未跟踪 | 被 `.gitignore:16:lib/` 忽略 |

**CI 失败链**：
1. `actions/checkout@v4` 检出代码 → `api.ts`、`utils.ts` 不在仓库中 → 缺失
2. Docker `COPY . .` → 容器中无这两个文件
3. `tsc` 编译 → `Cannot find module '@/lib/api'` 和 `'@/lib/utils'`
4. 构建失败

## 修复方案

### 修改 1：修复 `.gitignore` 中的 `lib/` 模式

**文件**：`.gitignore`

**变更**：`lib/` → `/lib/`，`lib64/` → `/lib64/`

添加前导 `/` 使模式仅匹配仓库根目录的 `lib/`（Python 虚拟环境目录），不再误匹配 `frontend/src/lib/`。

```diff
-lib/
-lib64/
+/lib/
+/lib64/
```

**原因**：`lib/` 和 `lib64/` 是 Python 虚拟环境的目录，只存在于项目根目录。添加前导 `/` 是 git 的标准做法，限制匹配范围到根目录。

### 修改 2：将未跟踪的文件加入 git

```bash
git add frontend/src/lib/api.ts frontend/src/lib/utils.ts frontend/src/lib/__tests__/utils.test.ts
```

修复 `.gitignore` 后，这3个文件不再被忽略，可以正常 `git add`。

### 修改 3：提交并推送

```bash
git commit -m "fix: correct .gitignore lib/ pattern to unignore frontend/src/lib/ files"
git push origin develop
```

## 对系统功能和稳定性的影响

**无影响。** 这是纯粹的 git 跟踪问题：
- 不修改任何源代码
- 不修改任何配置逻辑
- 仅修复 `.gitignore` 模式的匹配范围（从全局匹配改为根目录匹配）
- 将本应被跟踪但被误忽略的文件加入版本控制

## 验证步骤

1. `git check-ignore frontend/src/lib/api.ts` → 应无输出（不再被忽略）
2. `git ls-files frontend/src/lib/` → 应显示全部5个文件
3. CI 重新运行，frontend-build job 应通过
