# 版本号统一管理修复计划

## 调研结论

### 问题1：是否已经完整实现"所有版本号统一动态从VERSION文件获取"？

**结论：核心功能已经完整实现，仅manage.sh存在多余检查逻辑。**

| 组件 | 版本号来源 | 是否动态读取VERSION | 当前状态 |
|------|-----------|-------------------|---------|
| 后端（所有API返回、健康检查、metrics） | `settings.VERSION` → 读根目录`VERSION`文件，docker-compose通过环境变量`VERSION`注入 | ✅ 是 | 正确实现，无需修改 |
| 前端本地开发（npm run dev） | vite.config.ts → `getVersion()` 直接读根目录`VERSION`文件，注入`VITE_APP_VERSION` | ✅ 是 | 正确实现，无需修改 |
| 前端生产构建（Docker） | Dockerfile通过build arg `VERSION` → 设置ENV `VITE_APP_VERSION=${VERSION}` → 前端代码读取`import.meta.env.VITE_APP_VERSION` | ✅ 是 | 正确实现，无需修改 |
| package.json version字段 | Dockerfile第14行构建时sed自动替换，前端代码**不读取**这个字段 | ⚠️ 仅为文件元数据一致，不影响功能 | Docker构建时自动同步，不需要手动维护 |
| package-lock.json version字段 | npm自动生成，**所有代码都不读取** | ❌ 完全不需要手动维护 | 当前manage.sh错误地要求同步它 |

**实际运行时，没有任何代码读取package.json或package-lock.json中的version字段**：
- 前端运行时版本号来自`import.meta.env.VITE_APP_VERSION`（构建时注入或dev server动态读取）
- 后端运行时版本号来自根目录VERSION文件

---

### 问题2：package.json 和 package-lock.json 中的version字段是否有存在的必要？

| 文件 | 是否必要 | 说明 |
|------|---------|------|
| `frontend/package.json` 中 `version` | ⚠️ 无害但不必要 | 这是npm包的标准元数据字段，保留不会有问题。Docker构建时自动同步它，不影响功能。本地开发和生产运行都不读取它。 |
| `frontend/package-lock.json` 中 `version` | ❌ 完全不需要手动维护 | package-lock.json是npm自动生成的锁文件，顶层version字段npm install/ci会自动更新匹配package.json，**任何手动修改都会被npm下次操作覆盖**，手动同步毫无意义。Docker构建时也不读取它。 |

当前不一致：
- VERSION = 3.12.1 ✅
- package.json version = 3.12.1 ✅（之前手动更新了）
- package-lock.json version = 3.11.0 ❌（未同步，但不影响任何功能）

---

### 问题3：manage.sh version 相关命令逻辑是否符合现状？

**结论：不符合现状，需要修复。**

当前manage.sh版本检查逻辑错误点：
1. **错误地将`package-lock.json`列为需要手动同步的静态文件**：实际上它由npm自动维护，不应该手动sed修改
2. 动态文件列表正确列出了`docker-compose.yml`/`vite.config.ts`/`manage.sh`/`Dockerfile`，这些确实都是动态读取VERSION不需要同步
3. `version bump`命令错误地去sed修改package-lock.json：修改后下次npm install又会被覆盖，属于多余操作
4. package.json：Docker构建时自动同步，不需要手动bump修改？但是为了git工作区干净，保留同步也可以，不影响核心逻辑

---

## 需要修改的文件

| 文件 | 修改内容 |
|------|---------|
| `manage.sh` | 修复 `cmd_version_check` 和 `cmd_version_bump`，移除对 `package-lock.json` 的检查和同步 |
| `frontend/package-lock.json` | 一次性修正顶层version到3.12.1（让当前工作区一致，后续不需要手动维护） |

---

## 修改步骤

### 1. 修复manage.sh版本检查逻辑

- **`cmd_version_check`函数**：从`static_files`数组中移除`frontend/package-lock.json`，不再检查它
- **`cmd_version_bump`函数**：移除对`frontend/package-lock.json`的sed同步操作
- 更新注释说明：package-lock.json由npm自动维护，不需要手动同步；package.json在Docker构建时自动同步，本地开发不依赖它

### 2. 修复当前package-lock.json不一致

运行命令一次性更新package-lock.json顶层version匹配当前VERSION：
```bash
sed -i "1,5s/\"version\": \"[0-9]*\.[0-9]*\.[0-9]*\"/\"version\": \"$(cat VERSION | tr -d '[:space:]')\"/" frontend/package-lock.json
```
或者直接运行`./manage.sh version bump 3.12.1`（但在修复manage.sh之前运行会多修改一次，修复后运行只会改VERSION和package.json，但package.json已经是对的）

### 3. 验证修复

运行：
```bash
./manage.sh version check
```
预期输出：所有检查通过，不再报package-lock.json不一致。

---

## 最终正确的版本更新流程

修复后，版本更新只需要：

```bash
# 一条命令完成版本更新（只写VERSION文件，package.json可选同步方便git查看）
./manage.sh version bump X.Y.Z

# 验证一致性
./manage.sh version check

# 重建服务（Docker构建时自动处理前端版本注入）
./manage.sh update
```

✅ **唯一需要手动更新的文件是根目录`VERSION`**，其他全部自动处理：
- 后端：启动时直接读VERSION，自动更新
- 前端本地dev：vite直接读VERSION，重启dev server自动更新
- 前端生产构建：Docker构建时从VERSION注入VITE_APP_VERSION，自动更新
- package-lock.json：npm自动维护，永远不需要手动修改

---

## 风险评估

| 风险 | 影响 | 处理 |
|------|------|------|
| 修改manage.sh逻辑错误 | 低 | 修改后运行version check验证 |
| Docker构建npm ci因版本不一致报错 | 极低 | 经确认npm ci只检查依赖版本一致性，不检查顶层version字段，不影响构建；即使有问题，Docker构建时npm ci失败会在CI阶段发现 |

---

> 文档版本：v1.0，创建日期：2026-08-20
