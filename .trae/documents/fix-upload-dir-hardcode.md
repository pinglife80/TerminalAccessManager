# 修复 UPLOAD_DIR 硬编码路径问题

> 文档版本：v3.3.0 | 更新日期：2026-06-17

## 问题

`/app/uploads` 硬编码在 2 个文件中，CI 环境无 `/app` 写权限导致 PermissionError。

| 文件 | 行 | 代码 |
|------|-----|------|
| `backend/app/main.py:405` | `UPLOAD_DIR = "/app/uploads"` | 模块级创建目录 |
| `backend/app/api/v1/endpoints/settings.py:21` | `UPLOAD_DIR = "/app/uploads"` | 模块级创建目录 |

## 修复方案

将 `UPLOAD_DIR` 集成到 `config.py` Settings 类，与项目现有模式一致：

- Docker 容器中通过环境变量 `UPLOAD_DIR=/app/uploads` 设置
- CI/本地环境不设置该变量，默认使用 `./uploads`（相对于工作目录）
- 2 个文件统一从 `settings.UPLOAD_DIR` 读取

### Step 1: config.py 添加 UPLOAD_DIR 配置

```python
# 在 Settings 类中添加
UPLOAD_DIR: str = "./uploads"
```

### Step 2: main.py 改用 settings.UPLOAD_DIR

```python
from app.core.config import settings

UPLOAD_DIR = settings.UPLOAD_DIR

def _ensure_upload_dir():
    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        return True
    except (PermissionError, OSError) as e:
        logger.warning(f"Cannot create upload directory {UPLOAD_DIR}: {e}")
        return False

if _ensure_upload_dir():
    app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
```

### Step 3: settings.py 改用 settings.UPLOAD_DIR

```python
from app.core.config import settings

UPLOAD_DIR = settings.UPLOAD_DIR
# 移除 os.makedirs(UPLOAD_DIR, exist_ok=True) — 由 main.py 统一管理
```

### Step 4: .env.example 添加 UPLOAD_DIR

```
UPLOAD_DIR=/app/uploads
```

### Step 5: 提交并推送
