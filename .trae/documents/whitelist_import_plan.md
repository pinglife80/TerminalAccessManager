# 白名单数据导入功能实施计划

## 一、需求分析

**目标**：在白名单管理页面新增"导入"功能，支持用户上传 CSV 文件批量导入白名单数据。

**核心场景**：

1. 用户导出当前白名单 CSV → 外部编辑 → 导入更新
2. 从备份文件（CSV 格式）恢复白名单数据
3. 批量新增白名单条目（避免逐条手动添加）

**与现有功能关系**：

* 导出功能已存在：`GET /whitelist/export` 输出 CSV（7 列：ID/MAC/IP/Pattern Type/Comments/Added By/Created At）

* 备份恢复已存在：`POST /backup/whitelist/restore/{filename}` 基于服务端 ZIP 文件

* **本功能定位**：用户级 CSV 导入，上传文件到服务端解析并入库，与导出形成闭环

***

## 二、实施方案

### 2.1 后端新增内容

#### 新增 API 端点 `POST /whitelist/import`

**文件**：`backend/app/api/v1/endpoints/whitelist.py`

* 接收 `UploadFile`（支持 `.csv` 格式）

* 参数：`mode`（`skip`/`overwrite`，默认 `skip`）、`validate_only`（布尔，仅校验不入库）

* 返回：导入结果统计（success\_count, skipped\_count, failed\_count, errors 列表）

#### 新增 Schema

**文件**：`backend/app/schemas/terminal.py`

* `WhitelistImportResult`：导入结果响应（含逐行错误详情）

* `WhitelistImportError`：单条错误详情（行号 + 原因）

#### 新增 Service 方法

**文件**：`backend/app/services/terminal_service.py`

* `import_whitelist_csv(file_content, mode, username)`：核心导入逻辑

  1. 解析 CSV（跳过表头行）
  2. 校验每行数据（MAC 格式、IP 格式、必填项）
  3. 根据 `mode` 决定冲突处理策略
  4. 批量写入数据库
  5. 触发缓存失效 + 合规重算
  6. 写入审计日志 `whitelist_import`

**CSV 格式**（与导出对齐）：

```
ID,MAC Address,IP Pattern,Pattern Type,Comments,Added By,Created At
1,AA:BB:CC:DD:EE:FF,,mac_only,Office Printer,admin,2025-01-01T00:00:00
2,,192.168.1.0/24,cidr,Office Subnet,admin,2025-01-01T00:00:00
3,AA:BB:CC:DD:EE:FF,10.0.0.1,both,Server MAC+IP,admin,2025-01-01T00:00:00
```

**字段处理规则**：

* ID 列：忽略（导入时不指定 ID，由数据库自增）

* MAC Address：可选，自动归一化

* IP Pattern：可选，支持 single\_ip / cidr / ip\_range

* Pattern Type：可选，自动推断

* Comments：可选

* Added By：忽略（使用当前操作用户）

* Created At：忽略（使用当前时间）

**冲突处理策略**：

* `skip` 模式（默认）：跳过已存在的条目（MAC+IP 组合重复）

* `overwrite` 模式：覆盖已存在条目的 Comments 字段

#### CSV 校验规则

1. 文件扩展名必须为 `.csv`
2. 文件大小限制 5MB
3. MAC 地址格式校验（如存在）
4. IP/CIDR/范围格式校验（如存在）
5. MAC 和 IP 至少填写一个
6. Comments 字段非空校验（可选，空则设默认值）

***

### 2.2 前端新增内容

#### Whitelist 页面新增导入 UI

**文件**：`frontend/src/pages/Whitelist.tsx`

* 在页面顶部 Header 区域新增"导入"按钮（Upload 图标）

* 点击打开导入 Modal，包含：

  1. **文件选择区**：拖拽/点击上传 CSV 文件
  2. **格式说明**：展示支持的 CSV 格式模板
  3. **预览表格**：展示解析后的前 20 行数据
  4. **冲突处理选择**：跳过重复 / 覆盖重复
  5. **校验按钮**：仅校验不导入
  6. **导入按钮**：执行导入
  7. **结果展示**：成功/跳过/失败统计 + 详细错误列表

#### 国际化文案

**文件**：`frontend/src/i18n/locales/{zh,en,ja}.ts`

新增 `whitelistImport` 命名空间下的翻译项。

#### API 常量

**文件**：`frontend/src/lib/constants.ts`

新增 `WHITELIST_IMPORT: '/whitelist/import'`

***

### 2.3 文件变更清单

| 文件                                          | 操作 | 说明                                                       |
| ------------------------------------------- | -- | -------------------------------------------------------- |
| `backend/app/api/v1/endpoints/whitelist.py` | 编辑 | 新增 `POST /whitelist/import` 端点                           |
| `backend/app/schemas/terminal.py`           | 编辑 | 新增 `WhitelistImportResult`、`WhitelistImportError` Schema |
| `backend/app/services/terminal_service.py`  | 编辑 | 新增 `import_whitelist_csv()` 方法                           |
| `frontend/src/pages/Whitelist.tsx`          | 编辑 | 新增导入按钮 + 导入 Modal UI                                     |
| `frontend/src/lib/constants.ts`             | 编辑 | 新增 `WHITELIST_IMPORT` 常量                                 |
| `frontend/src/i18n/locales/zh.ts`           | 编辑 | 新增中文翻译                                                   |
| `frontend/src/i18n/locales/en.ts`           | 编辑 | 新增英文翻译                                                   |
| `frontend/src/i18n/locales/ja.ts`           | 编辑 | 新增日文翻译                                                   |

**共计 8 个文件，0 个新文件**（所有修改均在现有文件中进行）。

***

## 三、实施步骤

### Step 1：后端 Schema 定义

* 在 `terminal.py` 中添加 `WhitelistImportError` 和 `WhitelistImportResult` 响应 Schema

### Step 2：后端 Service 方法

* 在 `terminal_service.py` 中实现 `import_whitelist_csv()` 核心导入逻辑

* 包含 CSV 解析、逐行校验、冲突处理、批量写入、审计日志

* 复用现有 `_normalize_mac`、`_escape_like` 工具函数

### Step 3：后端 API 端点

* 在 `whitelist.py` 中新增 `POST /whitelist/import` 端点

* 实现文件上传处理、参数校验、调用 Service

* 权限要求：`whitelist:write`

### Step 4：前端常量与翻译

* 添加 API 端点常量

* 添加三语言国际化文案

### Step 5：前端导入 UI

* 实现导入 Modal 组件（内嵌在 Whitelist.tsx 中）

* 文件上传 + 预览 + 校验 + 导入 + 结果展示完整流程

### Step 6：验证

* 语法检查

* 功能流程测试

***

## 四、风险与注意事项

1. **数据安全**：导入操作默认使用 `skip` 模式，防止意外覆盖数据
2. **大文件处理**：限制单次导入不超过 10000 条记录，防止内存溢出
3. **审计追踪**：所有导入操作必须记录审计日志
4. **缓存一致性**：导入完成后必须调用 `invalidate_whitelist_cache()` 和合规重算
5. **权限控制**：导入需要 `whitelist:write` 权限
6. **CSV 注入防御**：校验文件类型，防止伪装扩展名著火
7. **唯一约束冲突**：数据库已有 `uq_whitelist_pattern` 唯一索引，需正确处理 IntegrityError

