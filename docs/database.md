# TerminalAccessManager 数据库设计文档

> 文档版本：v3.12.0  更新日期：2026-08-20

## 1. 概述

### 1.1 技术栈

| 组件 | 版本 / 说明 |
|---|---|
| 数据库 | PostgreSQL 15 |
| ORM | SQLAlchemy 2.0（异步模式） |
| 驱动 | asyncpg |
| 缓存 | Redis 7 |

### 1.2 连接池配置

| 参数 | 值 | 说明 |
|---|---|---|
| pool_size | 10 | 常驻连接数 |
| max_overflow | 20 | 超出 pool_size 后允许的最大溢出连接 |
| pool_timeout | 30 | 获取连接超时时间（秒），SQLAlchemy 默认值 |
| pool_recycle | 3600 | 连接回收时间（秒） |
| pool_pre_ping | true | 使用前检测连接可用性 |

### 1.3 PostgreSQL 配置参数

docker-compose.yml 中 PostgreSQL 的 `command` 参数列表如下：

| 参数 | 值 | 说明 |
|---|---|---|
| shared_buffers | 256MB | 共享缓冲区大小 |
| work_mem | 4MB | 排序/哈希操作内存 |
| effective_cache_size | 768MB | 查询规划器可用缓存估计 |
| wal_level | replica | WAL 日志级别 |
| max_connections | 100 | 最大连接数 |
| random_page_cost | 1.1 | 随机页面访问成本（SSD 优化） |
| log_min_duration_statement | 1000 | 慢查询阈值（ms） |
| log_connections | on | 记录连接日志 |
| log_disconnections | on | 记录断开连接日志 |
| log_line_prefix | `%t [%p] %u@%d ` | 日志行前缀格式 |
| log_timezone | `${TZ:-Asia/Shanghai}` | 数据库日志时间戳时区 |
| timezone | `${TZ:-Asia/Shanghai}` | 数据库查询时间时区 |

> **时区参数说明：** `log_timezone` 和 `timezone` 的实际值从 `.env` 文件中的 `TZ` 变量读取，默认为 `Asia/Shanghai`。修改 `.env` 中的 `TZ` 值后，重启容器即可同时更新数据库日志时区和查询时区，确保日志时间戳与业务时间一致。

---

## 2. ER 关系图

```
┌──────────────┐       ┌───────────────────┐       ┌──────────────────┐
│    users     │       │     terminals      │       │    whitelist     │
├──────────────┤       ├───────────────────┤       ├──────────────────┤
│ id        PK │       │ id             PK │       │ id            PK │
│ username     │       │ ip_address        │       │ mac_address      │
│ email        │       │ mac_address       │       │ ip_pattern       │
│ hashed_pass  │       │ status            │       │ pattern_type     │
│ is_active    │       │ comments          │       │ comments         │
│ is_superuser │       │ timestamp         │       │ added_by         │
│ created_at   │       │ source            │       │ mac_address_norm │
│ updated_at   │       │ source_tag        │       │ created_at       │
└──────┬───────┘       │ compliance_status │       └──────────────────┘
       │               │ wl_match_type     │
       │ 1:N           │ mac_address_norm  │       ┌──────────────────┐
       ├──────────────┐ └───────────────────┘       │    blacklist     │
       │              │                            ├──────────────────┤
┌──────┴──────────┐   │                            │ id            PK │
│   audit_logs    │   │                            │ ip_address       │
├─────────────────┤   │                            │ mac_address      │
│ id           PK │   │                            │ reason           │
│ user_id     FK ─┘   │                            │ blocked_at       │
│ username          │   │                            │ expires_at       │
│ action            │   │                            │ blocked_by       │
│ resource_type     │   │                            │ source_tag       │
│ resource_id       │   │                            │ firewall_tag     │
│ details           │   │                            │ is_auto_blocked  │
│ ip_address        │   │                            │ auto_unblocked   │
│ timestamp         │   │                            │ mac_address_norm │
└───────────────────┘   │                            └──────────────────┘
                        │
┌───────────────────┐   │       ┌──────────────────────┐
│  system_config    │   │       │  data_source_bindings │
├───────────────────┤   │       ├──────────────────────┤
│ id             PK │   │       │ id                PK │
│ key               │   │       │ arp_source_tag       │
│ value             │   │       │ firewall_tag         │
│ description       │   │       │ created_at           │
│ category          │   │       └──────────────────────┘
│ value_type        │   │                ▲
│ is_readonly       │   │                │ 关联
│ updated_by        │   │                │
│ created_at        │   │       ┌────────┴─────────────┐
│ updated_at        │   │       │    data_sources      │
└───────────────────┘   │       ├──────────────────────┤
                        │       │ id                PK │
                        │       │ name                 │
                        │       │ type                 │
                        │       │ tag                  │
                        │       │ config (JSON)        │
                        │       │ enabled              │
                        │       │ last_sync_at         │
                        │       │ last_sync_status     │
                        │       │ last_sync_error      │
                        │       │ created_at           │
                        │       │ updated_at           │
                        │       └──────────────────────┘
                        │
                        └─────── source_tag / firewall_tag 逻辑关联

┌──────────────────────┐
│ compliance_baselines │
├──────────────────────┤
│ id                PK │
│ name                 │
│ type                 │
│ tag                  │
│ config (JSON)        │
│ enabled              │
│ last_sync_at         │
│ last_sync_status     │
│ last_sync_error      │
│ created_at           │
│ updated_at           │
└──────────────────────┘

┌──────────────────┐       ┌──────────────────┐
│     roles        │       │   permissions    │
├──────────────────┤       ├──────────────────┤
│ id           PK  │       │ id           PK  │
│ name             │       │ code             │
│ description      │       │ name             │
│ is_default       │       │ module           │
│ created_at       │       │ description      │
│ updated_at       │       └────────┬─────────┘
└───────┬──────────┘                │
        │                           │
        ├───────────┐   ┌───────────┤
        │           │   │           │
        ▼           ▼   ▼           │
┌──────────────────────┐ ┌──────────────────────┐
│    user_roles        │ │  role_permissions    │
├──────────────────────┤ ├──────────────────────┤
│ user_id  FK→users.id │ │ role_id  FK→roles.id │
│ role_id  FK→roles.id │ │ permission_id        │
│                      │ │   FK→permissions.id  │
│ PK: (user_id,        │ │ PK: (role_id,        │
│      role_id)        │ │      permission_id)  │
└──────────────────────┘ └──────────────────────┘

┌──────────────────┐
│  backup_config   │
├──────────────────┤
│ id           PK  │
│ enabled          │
│ schedule         │
│ retention_days   │
│ storage_type     │
│ storage_config   │
│ backup_database  │
│ backup_config    │
│ backup_logs      │
│ encrypt_backup   │
│ created_at       │
│ updated_at       │
└──────────────────┘
```

---

## 3. 表详细设计

### 3.1 users — 用户表

存储系统用户账号信息，支持超级管理员与普通用户角色。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|---|---|---|---|---|
| id | INTEGER | PK, INDEX | 自增 | 主键 |
| username | VARCHAR(50) | UNIQUE, NOT NULL, INDEX | — | 用户名 |
| email | VARCHAR(120) | UNIQUE, INDEX | NULL | 邮箱（可选） |
| hashed_password | VARCHAR(255) | NOT NULL | — | bcrypt 哈希密码 |
| is_active | BOOLEAN | | TRUE | 是否启用 |
| is_superuser | BOOLEAN | | FALSE | 是否超级管理员 |
| created_at | TIMESTAMP WITH TZ | | utcnow | 创建时间 |
| updated_at | TIMESTAMP WITH TZ | | utcnow, onupdate=utcnow | 更新时间 |

**索引：**

| 索引名 | 类型 | 字段 |
|---|---|---|
| ix_users_username | UNIQUE | username |
| ix_users_email | UNIQUE | email |

**外键关系：**

| 关系 | 说明 |
|---|---|
| users.id ← audit_logs.user_id | 一对多：一个用户拥有多条审计日志 |

---

### 3.2 terminals — 终端表

存储从各数据源采集的 MAC-IP 终端绑定记录，是系统核心业务表。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|---|---|---|---|---|
| id | INTEGER | PK, INDEX | 自增 | 主键 |
| ip_address | VARCHAR(45) | NOT NULL, INDEX | — | IPv4/IPv6 地址（DHCP换IP时更新） |
| mac_address | VARCHAR(17) | NOT NULL, INDEX | — | MAC 地址（格式 XX-XX-XX-XX-XX-XX） |
| status | VARCHAR(20) | INDEX | 'unblocked' | 终端防火墙状态（blocked/unblocked） |
| comments | TEXT | | NULL | 备注 |
| timestamp | TIMESTAMP WITH TZ | INDEX | utcnow | 记录创建时间（首次发现时间） |
| updated_at | TIMESTAMP WITH TZ | INDEX | NULL | 记录更新时间（ARP 采集更新时写入，不覆盖 timestamp） |
| source | VARCHAR(50) | | 'arp' | 数据来源 |
| source_tag | VARCHAR(50) | INDEX | NULL | 数据源标签，关联 data_sources.tag |
| compliance_status | VARCHAR(20) | INDEX | 'unknown' | 合规状态 |
| wl_match_type | VARCHAR(10) | | NULL | 白名单匹配类型 |
| mac_address_normalized | VARCHAR(12) | NOT NULL, UNIQUE, INDEX | — | MAC 地址标准化（去除分隔符的大写 12 位字符串，如 AABBCCDDEEFF），v3.12起为唯一键 |
| firewall_tag | VARCHAR(50) | | NULL | 封堵操作时写入的防火墙标签，解封时清除 |
| non_compliant_confirm_count | INTEGER | | 0 | 连续不合规确认计数（降级用） |
| compliant_confirm_count | INTEGER | | 0 | 连续合规确认计数（升级用，v3.12+） |
| ip_changed_at | TIMESTAMP WITH TZ | | NULL | 最近IP变更时间戳（用于宽限期判断，v3.12+） |

> **v3.12 重要变更**：终端记录以 MAC 地址为唯一标识，一个 MAC 对应一条记录，IP 地址作为可变属性在 DHCP 换 IP 时更新，不再产生重复记录。双网卡终端每个 MAC 独立一条记录。

**索引：**

| 索引名 | 类型 | 字段 |
|---|---|---|
| idx_mac_timestamp | COMPOSITE | (mac_address, timestamp) |
| idx_ip_status | COMPOSITE | (ip_address, status) |
| uq_terminal_mac | UNIQUE | mac_address_normalized | MAC 标准化列唯一索引，一个MAC一条记录 |

**约束：**

| 约束名 | 类型 | 字段 | 说明 |
|---|---|---|---|
| uq_terminal_mac | UNIQUE | mac_address_normalized | 以归一化MAC为唯一标识，v3.12替换原uq_terminal_ip_mac |

**数据字典 — status：**

| 值 | 说明 |
|---|---|
| blocked | 已封堵（被防火墙阻断） |
| unblocked | 未封堵（默认初始状态） |

**数据字典 — source：**

| 值 | 说明 |
|---|---|
| arp | ARP 表采集 |
| compliance_baseline | 合规基准导入 |
| whitelist | 白名单导入 |
| manual | 手动录入 |

**数据字典 — compliance_status：**

| 值 | 说明 |
|---|---|
| compliant | 合规（匹配合规基准，IP+MAC 同时匹配） |
| bypass | 旁路（匹配白名单，MAC/IP/Both） |
| non_compliant | 不合规（未匹配白名单和合规基准） |
| unknown | 未知（未进行合规检查） |

**数据字典 — wl_match_type：**

| 值 | 说明 |
|---|---|
| mac | 仅 MAC 匹配白名单 |
| ip | 仅 IP 匹配白名单 |
| both | MAC 和 IP 均匹配白名单 |
| NULL | 未匹配白名单 |

---

### 3.3 whitelist — 白名单表

存储准入终端规则，支持按 MAC、IP、CIDR、IP 范围匹配。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|---|---|---|---|---|
| id | INTEGER | PK, INDEX | 自增 | 主键 |
| mac_address | VARCHAR(17) | INDEX | NULL | MAC 地址（与 ip_pattern 至少填一项） |
| ip_pattern | VARCHAR(100) | INDEX | NULL | IP 匹配模式（单 IP / CIDR / IP 范围） |
| pattern_type | VARCHAR(20) | | 'single_ip' | 模式类型 |
| comments | TEXT | | NULL | 备注 |
| added_by | VARCHAR(50) | NOT NULL | — | 添加人用户名 |
| mac_address_normalized | VARCHAR(12) | INDEX | NULL | MAC 地址标准化（去除分隔符的大写 12 位字符串） |
| created_at | TIMESTAMP WITH TZ | INDEX | utcnow | 创建时间 |

**索引：**

| 索引名 | 类型 | 字段 |
|---|---|---|
| idx_whitelist_created_at | SINGLE | created_at |
| idx_whitelist_mac_normalized | SINGLE | mac_address_normalized | MAC 标准化列索引 |

**数据字典 — pattern_type：**

| 值 | 说明 | ip_pattern 示例 |
|---|---|---|
| single_ip | 单个 IP 地址 | `192.168.1.100` |
| cidr | CIDR 网段 | `192.168.1.0/24` |
| ip_range | IP 范围 | `192.168.1.1-192.168.1.50` |
| mac_only | 仅 MAC 匹配 | NULL |

---

### 3.4 blacklist — 黑名单表

存储被阻断的 IP/MAC 终端记录，支持自动阻断与手动阻断。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|---|---|---|---|---|
| id | INTEGER | PK, INDEX | 自增 | 主键 |
| ip_address | VARCHAR(45) | INDEX | NULL | 被阻断的 IP 地址 |
| mac_address | VARCHAR(17) | INDEX | NULL | 被阻断的 MAC 地址 |
| reason | TEXT | | NULL | 阻断原因 |
| blocked_at | TIMESTAMP WITH TZ | | utcnow | 阻断时间（可空） |
| expires_at | TIMESTAMP WITH TZ | | NULL | 过期时间（NULL 表示永久） |
| blocked_by | VARCHAR(50) | NOT NULL | — | 执行阻断的用户名 |
| source_tag | VARCHAR(50) | INDEX | NULL | ARP 数据源标签 |
| firewall_tag | VARCHAR(50) | INDEX | NULL | 防火墙标签 |
| is_auto_blocked | BOOLEAN | | FALSE | 是否由合规检查自动阻断 |
| auto_unblocked | BOOLEAN | | FALSE | 是否已自动解封（合规后） |
| unblocked_at | TIMESTAMP WITH TZ | INDEX | NULL | 解封时间（NULL 表示未解封） |
| unblocked_by | VARCHAR(50) | | NULL | 执行解封的用户名（手动解封时写入） |
| mac_address_normalized | VARCHAR(12) | INDEX | NULL | MAC 地址标准化（去除分隔符的大写 12 位字符串） |

**索引：**

| 索引名 | 类型 | 字段 |
|---|---|---|
| idx_blacklist_ip | COMPOSITE | (ip_address) |
| idx_blacklist_mac | COMPOSITE | (mac_address) |
| idx_blacklist_auto | COMPOSITE | (is_auto_blocked, auto_unblocked) |
| idx_blacklist_unblocked | SINGLE | unblocked_at |
| idx_blacklist_blocked_at | SINGLE | blocked_at |
| idx_blacklist_expires_at | SINGLE | expires_at |
| idx_blacklist_mac_normalized | SINGLE | mac_address_normalized | MAC 标准化列索引 |
| idx_blacklist_unique_active | UNIQUE PARTIAL | (ip_address, mac_address_normalized) WHERE unblocked_at IS NULL AND auto_unblocked = FALSE | 唯一部分索引，防止活跃黑名单记录重复 |

---

### 3.5 audit_logs — 审计日志表

记录系统所有关键操作，满足安全审计与追溯需求。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|---|---|---|---|---|
| id | INTEGER | PK, INDEX | 自增 | 主键 |
| user_id | INTEGER | FK → users.id | NULL | 操作用户 ID（系统操作时为 NULL） |
| username | VARCHAR(50) | NOT NULL, INDEX | — | 操作用户名（冗余，避免 JOIN） |
| action | VARCHAR(100) | NOT NULL, INDEX | — | 操作类型 |
| resource_type | VARCHAR(50) | | NULL | 资源类型 |
| resource_id | VARCHAR(100) | | NULL | 资源标识 |
| resource_name | VARCHAR(200) | | NULL | 资源的可读名称（如用户名、数据源名称、IP 地址） |
| details | TEXT | | NULL | 操作详情（JSON 格式，json.dumps 序列化，每个 dict 包含 message 字段） |
| ip_address | VARCHAR(45) | INDEX | NULL | 请求来源 IP |
| timestamp | TIMESTAMP WITH TZ | INDEX | utcnow | 操作时间 |

**索引：**

| 索引名 | 类型 | 字段 |
|---|---|---|
| idx_audit_user_timestamp | COMPOSITE | (username, timestamp) |
| idx_audit_action | COMPOSITE | (action) |
| idx_audit_ip_address | SINGLE | ip_address |
| idx_audit_logs_keyset | COMPOSITE | (timestamp DESC, id DESC) |

**数据字典 — resource_type：**

| 值 | 说明 |
|---|---|
| mac | 终端地址操作 |
| whitelist | 白名单操作 |
| blacklist | 黑名单操作 |
| datasource | 数据源操作 |
| user | 用户管理操作 |
| auth | 认证操作 |
| system | 系统配置操作 |

**数据字典 — action：**

| 值 | 说明 | resource_type |
|---|---|---|
| `block_terminal` | 封禁终端 | mac |
| `unblock_terminal` | 解封终端 | mac |
| `block_blacklist` | 加入黑名单 | blacklist |
| `unblock_blacklist` | 移出黑名单 | blacklist |
| `add_whitelist` | 添加白名单 | whitelist |
| `remove_whitelist` | 移除白名单 | whitelist |
| `cleanup_expired` | 清理过期黑名单 | blacklist |
| `login` | 用户登录 | auth |
| `logout` | 用户登出 | auth |
| `create_datasource` | 创建数据源 | datasource |
| `update_datasource` | 更新数据源 | datasource |
| `delete_datasource` | 删除数据源 | datasource |
| `test_datasource` | 测试数据源连接 | datasource |
| `sync_datasource` | 同步数据源 | datasource |
| `create_user` | 创建用户 | user |
| `update_user` | 更新用户 | user |
| `delete_user` | 删除用户 | user |
| `reset_password` | 重置密码 | user |
| `unlock_user` | 解锁用户 | user |
| `update_config` | 更新系统配置 | system |

---

### 3.6 system_config — 系统配置表

存储系统运行时配置项，支持按类别分组与类型校验。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|---|---|---|---|---|
| id | INTEGER | PK, INDEX | 自增 | 主键 |
| key | VARCHAR(100) | UNIQUE, NOT NULL, INDEX | — | 配置键 |
| value | TEXT | NOT NULL | — | 配置值（文本存储，按 value_type 解析） |
| description | TEXT | | NULL | 配置说明 |
| category | VARCHAR(50) | NOT NULL | 'general' | 配置分类 |
| value_type | VARCHAR(20) | NOT NULL | 'string' | 值类型 |
| is_readonly | BOOLEAN | | FALSE | 是否只读（系统内置不可修改） |
| updated_by | VARCHAR(100) | | NULL | 最后修改人 |
| created_at | TIMESTAMP WITH TZ | server_default=now() | — | 创建时间 |
| updated_at | TIMESTAMP WITH TZ | server_default=now(), onupdate=now() | — | 更新时间 |

**数据字典 — category：**

| 值 | 说明 |
|---|---|
| security | 安全策略 |
| rate_limit | 限流配置 |
| auth | 认证配置（保留，暂未使用） |
| network | 网络配置 |
| scheduler | 定时任务配置 |
| general | 通用配置 |
| logging | 日志配置 |
| branding | 品牌定制 |

**数据字典 — value_type：**

| 值 | 说明 | value 示例 |
|---|---|---|
| string | 字符串 | `"192.168.1.0/24"` |
| int | 整数 | `"300"` |
| bool | 布尔值 | `"true"` |
| json | JSON 对象 | `'{"key": "value"}'` |

**启动时自动迁移：**

应用启动时，lifespan 会自动检查并迁移 `system_config` 表中的旧品牌值。将 `app_name`、`login_heading` 等品牌配置项中包含的旧品牌名 `"Terminal Access Platform"` 替换为 `"Terminal Access Manager"`，确保品牌一致性。此迁移为幂等操作，仅更新包含旧值的记录。

---

### 3.7 data_sources — 数据源表

存储外部数据源连接配置，支持 ARP、深信服等多种数据采集方式。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|---|---|---|---|---|
| id | INTEGER | PK, INDEX | 自增 | 主键 |
| name | VARCHAR(100) | UNIQUE, NOT NULL | — | 数据源名称 |
| type | VARCHAR(20) | NOT NULL | — | 数据源类型 |
| tag | VARCHAR(50) | UNIQUE, NOT NULL, INDEX | — | 数据源唯一标签 |
| config | JSON | NOT NULL | `{}` | 连接配置（JSON 格式，敏感字段 Fernet 加密存储，读取时通过 `db.expunge` + `decrypt_config` 解密） |
| enabled | BOOLEAN | | TRUE | 是否启用 |
| last_sync_at | TIMESTAMP WITH TZ | | NULL | 最近同步时间 |
| last_sync_status | VARCHAR(20) | | NULL | 最近同步状态 |
| last_sync_error | TEXT | | NULL | 最近同步错误信息 |
| created_at | TIMESTAMP WITH TZ | server_default=now() | — | 创建时间 |
| updated_at | TIMESTAMP WITH TZ | server_default=now(), onupdate=now() | — | 更新时间 |

**数据字典 — type：**

| 值 | 说明 |
|---|---|
| arp_ssh | 通过 SSH 采集 ARP 表 |
| arp_api | 通过 API 采集 ARP 表 |
| sangfor | 深信服防火墙 |

**数据字典 — last_sync_status：**

| 值 | 说明 |
|---|---|
| success | 同步成功 |
| failed | 同步失败 |

---

### 3.8 data_source_bindings — 数据源绑定表

定义 ARP 数据源与防火墙数据源之间的绑定关系，用于合规检查与自动阻断联动。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|---|---|---|---|---|
| id | INTEGER | PK, INDEX | 自增 | 主键 |
| arp_source_tag | VARCHAR(50) | NOT NULL, INDEX | — | ARP 数据源标签 |
| firewall_tag | VARCHAR(50) | NOT NULL, INDEX | — | 防火墙数据源标签 |
| created_at | TIMESTAMP WITH TZ | server_default=now() | — | 创建时间 |

**约束：**

| 约束名 | 类型 | 字段 |
|---|---|---|
| uq_arp_firewall | UNIQUE | (arp_source_tag, firewall_tag) |

---

### 3.9 compliance_baselines — 合规基准表

存储合规基准数据源配置，支持 IP Guard 等多种合规数据采集方式。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|---|---|---|---|---|
| id | INTEGER | PK, INDEX | 自增 | 主键 |
| name | VARCHAR(100) | UNIQUE, NOT NULL | — | 基准名称 |
| type | VARCHAR(20) | NOT NULL | — | 基准类型（sqlserver/mysql/postgresql） |
| tag | VARCHAR(50) | UNIQUE, NOT NULL, INDEX | — | 基准唯一标签 |
| config | JSON | NOT NULL | `{}` | 连接配置（JSON 格式，包含 host、port、db_name、username、password、query 等） |
| enabled | BOOLEAN | | TRUE | 是否启用 |
| last_sync_at | TIMESTAMP WITH TZ | | NULL | 最近同步时间 |
| last_sync_status | VARCHAR(20) | | NULL | 最近同步状态（success/failed） |
| last_sync_error | TEXT | | NULL | 最近同步错误信息 |
| created_at | TIMESTAMP WITH TZ | server_default=now() | — | 创建时间 |
| updated_at | TIMESTAMP WITH TZ | server_default=now(), onupdate=now() | — | 更新时间 |

**数据字典 — type：**

| 值 | 说明 |
|---|---|
| sqlserver | SQL Server 数据库 |
| mysql | MySQL 数据库 |
| postgresql | PostgreSQL 数据库 |

---

### 3.10 RBAC 权限控制表

系统通过4张核心表实现 RBAC 数据模型：

#### roles 表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | SERIAL | PRIMARY KEY | 角色ID |
| name | VARCHAR(50) | UNIQUE, NOT NULL | 角色标识名 |
| description | VARCHAR(200) | | 角色描述 |
| is_default | BOOLEAN | DEFAULT FALSE | 是否为默认角色 |
| created_at | TIMESTAMP | DEFAULT NOW() | 创建时间 |
| updated_at | TIMESTAMP | DEFAULT NOW() | 更新时间 |

#### permissions 表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | SERIAL | PRIMARY KEY | 权限ID |
| code | VARCHAR(100) | UNIQUE, NOT NULL | 权限码（如 terminal:read） |
| name | VARCHAR(100) | NOT NULL | 权限名称 |
| module | VARCHAR(50) | NOT NULL | 所属模块 |
| description | VARCHAR(200) | | 权限描述 |

#### user_roles 表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| user_id | INTEGER | FK→users.id, ON DELETE CASCADE | 用户ID |
| role_id | INTEGER | FK→roles.id, ON DELETE CASCADE | 角色ID |

联合主键: (user_id, role_id)

#### role_permissions 表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| role_id | INTEGER | FK→roles.id, ON DELETE CASCADE | 角色ID |
| permission_id | INTEGER | FK→permissions.id, ON DELETE CASCADE | 权限ID |

联合主键: (role_id, permission_id)

### RBAC 种子数据自动填充（v3.2.0-r2）

`manage.sh init` 和 `python cli.py setup` 现在自动调用 `_ensure_rbac_seed(db)` 填充 RBAC 种子数据：

| 数据 | 数量 | 说明 |
|------|------|------|
| 角色 | 5 | superadmin, admin, operator, auditor, viewer |
| 权限码 | 29 | 覆盖 10 个功能模块 |
| 角色-权限映射 | 51 | admin(23), operator(10), auditor(8), viewer(10) |

幂等保护：`roles` 表已有 >= 5 条记录时跳过种子操作。

> **注意**：通过 `alembic upgrade head` 升级的已有数据库，由 006_rbac_tables.py 迁移脚本负责种子数据填充。

---

### 3.11 notification_channels — 通知渠道表

存储通知渠道配置，支持邮件、钉钉、企业微信、通用 Webhook 等多种通知方式。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | INTEGER | PK, INDEX | 自增 | 主键 |
| name | VARCHAR(100) | UNIQUE, NOT NULL | — | 渠道名称 |
| channel_type | VARCHAR(20) | NOT NULL | — | 渠道类型 |
| config | JSON | NOT NULL | `{}` | 渠道配置（JSON 格式，敏感字段加密存储） |
| events | TEXT[] | | `[]` | 订阅的事件类型列表 |
| description | TEXT | | NULL | 渠道描述 |
| enabled | BOOLEAN | | TRUE | 是否启用 |
| created_by | VARCHAR(50) | | NULL | 创建人用户名 |
| created_at | TIMESTAMP WITH TZ | server_default=now() | — | 创建时间 |
| updated_at | TIMESTAMP WITH TZ | server_default=now(), onupdate=now() | — | 更新时间 |

**数据字典 — channel_type：**

| 值 | 说明 |
|------|------|
| email | SMTP 邮件通知 |
| dingtalk | 钉钉 Webhook |
| wecom | 企业微信 Webhook |
| webhook | 通用 Webhook |

**索引：**

| 索引名 | 类型 | 字段 |
|------|------|------|
| ix_notification_channels_name | UNIQUE | name |
| ix_notification_channels_type | SINGLE | channel_type |

---

### 3.12 notification_logs — 通知日志表

记录每条通知的发送状态和结果，用于问题排查和审计。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | INTEGER | PK, INDEX | 自增 | 主键 |
| channel_id | INTEGER | FK → notification_channels.id | NOT NULL | 关联的通知渠道 |
| event_type | VARCHAR(50) | NOT NULL | — | 事件类型 |
| status | VARCHAR(20) | NOT NULL | 'pending' | 发送状态 |
| error_message | TEXT | | NULL | 错误信息 |
| retries | INTEGER | | 0 | 重试次数 |
| archived | BOOLEAN | NOT NULL | FALSE | 是否已归档 |
| created_at | TIMESTAMP WITH TZ | server_default=now() | — | 创建时间 |
| updated_at | TIMESTAMP WITH TZ | server_default=now(), onupdate=now() | — | 更新时间 |

**数据字典 — status：**

| 值 | 说明 |
|------|------|
| pending | 待发送 |
| sent | 发送成功 |
| failed | 发送失败 |
| retrying | 重试中 |

**索引：**

| 索引名 | 类型 | 字段 |
|------|------|------|
| ix_notification_logs_channel | COMPOSITE | (channel_id, created_at DESC) |
| ix_notification_logs_status | SINGLE | status |
| ix_notification_logs_event | SINGLE | event_type |
| ix_notification_logs_archived | SINGLE | archived |

---

### 3.13 notification_templates — 消息模板表

存储基于 Jinja2 的通知消息模板，按 (event_type, channel_type) 组合唯一索引。当存在匹配模板时，使用模板渲染消息内容；否则使用各渠道的默认格式化逻辑。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | INTEGER | PK, INDEX | 自增 | 主键 |
| name | VARCHAR(100) | UNIQUE, NOT NULL | — | 模板名称 |
| event_type | VARCHAR(100) | NOT NULL, INDEX | — | 事件类型（支持 `*` 通配符匹配所有事件） |
| channel_type | VARCHAR(50) | NOT NULL, INDEX | — | 渠道类型（email、webhook、feishu、dingtalk、wecom） |
| subject_template | TEXT | NULLABLE | NULL | 标题模板（仅邮件等有标题的渠道使用） |
| body_template | TEXT | NOT NULL | — | 正文模板（Jinja2 语法） |
| is_default | BOOLEAN | | FALSE | 是否为该事件-渠道组合的默认模板 |
| priority | INTEGER | NOT NULL | 100 | 优先级，数值越小优先级越高 |
| created_by | VARCHAR(100) | NULLABLE | NULL | 创建人 |
| created_at | TIMESTAMP | default=now() | — | 创建时间 |
| updated_at | TIMESTAMP | default=now(), onupdate=now() | — | 更新时间 |

**唯一约束**：

| 约束名 | 字段 | 说明 |
|--------|------|------|
| uq_template_event_channel | (event_type, channel_type) | 同一事件-渠道组合仅一个模板 |

**索引**：

| 索引名 | 类型 | 字段 |
|------|------|------|
| ix_notification_templates_event | SINGLE | event_type |
| ix_notification_templates_channel | SINGLE | channel_type |
| ix_notification_templates_name | UNIQUE | name |

---

### 3.14 notification_rules — 通知规则表

存储通知抑制、聚合和升级规则，用于减少通知骚扰并确保重要告警不被遗漏。规则按 event_type 匹配，channel_name 为 NULL 时表示适用于所有渠道。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | INTEGER | PK, INDEX | 自增 | 主键 |
| name | VARCHAR(100) | UNIQUE, NOT NULL | — | 规则名称 |
| event_type | VARCHAR(100) | NOT NULL, INDEX | — | 事件类型（支持 `*` 通配符匹配所有事件） |
| channel_name | VARCHAR(100) | NULLABLE, INDEX | NULL | 渠道名称（NULL 表示所有渠道） |
| enabled | BOOLEAN | | TRUE | 是否启用 |
| description | TEXT | NULLABLE | NULL | 规则描述 |
| suppress_enabled | BOOLEAN | | FALSE | 是否启用消息抑制 |
| suppress_window | INTEGER | | 300 | 抑制窗口（秒），窗口内同类事件仅发送一次 |
| escalate_enabled | BOOLEAN | | FALSE | 是否启用消息升级 |
| escalate_threshold | INTEGER | | 5 | 升级阈值（窗口内事件数） |
| escalate_window | INTEGER | | 3600 | 升级统计窗口（秒） |
| escalate_severity | VARCHAR(20) | | `error` | 升级后的严重等级（info/warning/error/critical） |
| priority | INTEGER | NOT NULL | 100 | 优先级，数值越小优先级越高 |
| created_by | VARCHAR(100) | NULLABLE | NULL | 创建人 |
| created_at | TIMESTAMP | default=now() | — | 创建时间 |
| updated_at | TIMESTAMP | default=now(), onupdate=now() | — | 更新时间 |

> **注意**：由于 PostgreSQL 中 NULL 在 UNIQUE 约束中被视为互不相同，(event_type, channel_name) 的唯一性通过迁移脚本中的部分索引实现，确保每个 event_type 仅有一条 NULL channel_name 的 catch-all 规则。

**索引**：

| 索引名 | 类型 | 字段 |
|------|------|------|
| ix_notification_rules_name | UNIQUE | name |
| ix_notification_rules_event | SINGLE | event_type |
| ix_notification_rules_channel | SINGLE | channel_name |

---

### 3.15 auth_providers — 认证提供者表

存储认证提供者配置，支持本地认证、LDAP认证、OAuth认证等多种认证方式。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | INTEGER | PK, INDEX | 自增 | 主键 |
| name | VARCHAR(100) | UNIQUE, NOT NULL | — | 提供者名称 |
| provider_type | VARCHAR(20) | NOT NULL | — | 提供者类型 |
| config | JSON | NOT NULL | `{}` | 认证配置（JSON 格式，敏感字段加密存储） |
| enabled | BOOLEAN | | TRUE | 是否启用 |
| created_at | TIMESTAMP WITH TZ | server_default=now() | — | 创建时间 |
| updated_at | TIMESTAMP WITH TZ | server_default=now(), onupdate=now() | — | 更新时间 |

**数据字典 — provider_type：**

| 值 | 说明 |
|------|------|
| local | 本地认证（用户名密码） |
| ldap | LDAP/Active Directory 认证 |
| oauth | OAuth 认证（预留扩展） |

**索引：**

| 索引名 | 类型 | 字段 |
|------|------|------|
| ix_auth_providers_name | UNIQUE | name |
| ix_auth_providers_type | SINGLE | provider_type |

---

### 3.16 backup_config — 备份配置表

存储系统备份策略配置，支持定时备份、多种存储类型（本地/SFTP/FTP）、备份内容选择和加密选项。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|---|---|---|---|---|
| id | INTEGER | PK | 自增 | 主键 |
| enabled | BOOLEAN | NOT NULL | FALSE | 是否启用备份 |
| schedule | VARCHAR(100) | NOT NULL | '0 2 * * *' | CRON 定时表达式 |
| retention_days | INTEGER | NOT NULL | 7 | 备份保留天数 |
| storage_type | VARCHAR(50) | NOT NULL | 'local' | 存储类型（local/sftp/ftp） |
| storage_config | JSON | | {} | 存储配置（SFTP/FTP 参数） |
| backup_database | BOOLEAN | NOT NULL | TRUE | 是否备份数据库 |
| backup_config | BOOLEAN | NOT NULL | TRUE | 是否备份配置文件 |
| backup_logs | BOOLEAN | NOT NULL | FALSE | 是否备份日志文件 |
| encrypt_backup | BOOLEAN | NOT NULL | TRUE | 是否加密备份文件 |
| created_at | TIMESTAMP WITH TZ | | utcnow | 创建时间 |
| updated_at | TIMESTAMP WITH TZ | | utcnow, onupdate=utcnow | 更新时间 |

**storage_config JSON 结构说明：**

| 存储类型 | JSON 字段 | 说明 |
|---|---|---|
| local | 无特殊字段 | 使用本地 backups 目录 |
| sftp | host, port, username, password, path | SFTP 连接参数 |
| ftp | host, port, username, password, path, use_ssl | FTP 连接参数，use_ssl 为 true 时使用 FTPS |

**约束说明：**
- 表中只允许存在一条记录（通过应用层逻辑保证）
- schedule 字段必须符合 CRON 5 字段格式：`分钟 小时 日 月 周`

---

## 4. 数据字典汇总

### 4.1 TerminalStatus（终端状态）

| 枚举值 | 适用表 | 说明 |
|---|---|---|
| blocked | terminals.status | 终端已被防火墙封堵 |
| unblocked | terminals.status | 终端未被封堵（默认值） |

> **说明**：`status` 字段现在只表示防火墙封堵状态，合规状态由 `compliance_status` 字段独立追踪。
>
> **v3.2.0-r4 数据迁移说明：** 终端状态从 6 值枚举精简为 2 值枚举，迁移规则如下：
> - `frozen` → `blocked`
> - `unfrozen` → `unblocked`
> - 其他遗留值（`active`、`inactive`、`pending`）→ `unblocked`

### 4.2 ComplianceStatus（合规状态）

| 枚举值 | 适用表 | 说明 |
|---|---|---|
| compliant | terminals.compliance_status | 合规（匹配合规基准，IP+MAC 同时匹配） |
| bypass | terminals.compliance_status | 旁路（匹配白名单，MAC/IP/Both） |
| non_compliant | terminals.compliance_status | 不合规（未匹配白名单和合规基准） |
| unknown | terminals.compliance_status | 未知（未进行合规检查） |

### 4.3 WlMatchType（白名单匹配类型）

| 枚举值 | 适用表 | 说明 |
|---|---|---|
| mac | terminals.wl_match_type | 仅 MAC 匹配 |
| ip | terminals.wl_match_type | 仅 IP 匹配 |
| both | terminals.wl_match_type | MAC 和 IP 均匹配 |
| NULL | terminals.wl_match_type | 未匹配白名单 |

### 4.4 PatternType（白名单模式类型）

| 枚举值 | 适用表 | 说明 |
|---|---|---|
| single_ip | whitelist.pattern_type | 单个 IP 地址 |
| cidr | whitelist.pattern_type | CIDR 网段 |
| ip_range | whitelist.pattern_type | IP 范围 |
| mac_only | whitelist.pattern_type | 仅 MAC 匹配 |

### 4.5 DataSourceType（数据源类型）

| 枚举值 | 适用表 | 说明 |
|---|---|---|
| arp_ssh | data_sources.type | SSH 方式采集 ARP 表 |
| arp_api | data_sources.type | API 方式采集 ARP 表 |
| sangfor | data_sources.type | 深信服防火墙 |

### 4.6 SystemConfigCategory（配置分类）

| 枚举值 | 适用表 | 说明 |
|---|---|---|
| security | system_config.category | 安全策略 |
| rate_limit | system_config.category | 限流配置 |
| auth | system_config.category | 认证配置 |
| network | system_config.category | 网络配置 |
| scheduler | system_config.category | 定时任务配置 |
| general | system_config.category | 通用配置 |
| logging | system_config.category | 日志配置 |
| branding | system_config.category | 品牌定制 |

### 4.7 SystemConfigValueType（配置值类型）

| 枚举值 | 适用表 | 说明 |
|---|---|---|
| string | system_config.value_type | 字符串 |
| int | system_config.value_type | 整数 |
| bool | system_config.value_type | 布尔值 |
| json | system_config.value_type | JSON 对象 |

### 4.8 ScopeType（合规范围条件类型，v3.11+）

| 枚举值 | 适用表 | 说明 |
|---|---|---|
| ip_cidr | compliance_scope.scope_type | IP网段（CIDR）匹配终端IP，命中后忽略MAC仅用IP匹配IPGuard |
| ip_range | compliance_scope.scope_type | IP范围匹配终端IP，命中后忽略MAC仅用IP匹配IPGuard |
| mac_prefix_arp | compliance_scope.scope_type | MAC前缀匹配ARP采集的终端MAC，命中后忽略MAC仅用IP匹配IPGuard（v3.12拆分自原mac_prefix） |
| mac_prefix_ipguard | compliance_scope.scope_type | MAC前缀匹配IPGuard基线中的MAC，命中后按IP+MAC精确匹配（v3.12新增） |

---

## 5. Redis 数据结构

### 5.1 令牌黑名单

| 项目 | 说明 |
|---|---|
| Key | `token_blacklist:{jti}` |
| Value | `1` |
| Type | STRING |
| TTL | Token 剩余有效期 |
| 用途 | JWT 注销后将其 jti 加入黑名单，请求时校验 |

### 5.2 登录尝试计数

| 项目 | 说明 |
|---|---|
| Key | `login_attempts:{username}` |
| Value | 尝试次数（整数） |
| Type | STRING |
| TTL | lockout_duration（账户锁定时长） |
| 用途 | 记录用户连续登录失败次数，超限后触发锁定 |

### 5.3 账户锁定

| 项目 | 说明 |
|---|---|
| Key | `login_lock:{username}` |
| Value | `1` |
| Type | STRING |
| TTL | lockout_duration |
| 用途 | 标记账户已被锁定，锁定期间拒绝登录 |

### 5.4 接口限流

| 项目 | 说明 |
|---|---|
| Key | `rate_limit:{client_id}:{path}` |
| Value | 请求时间戳集合 |
| Type | SORTED SET（score=时间戳） |
| TTL | 60s |
| 用途 | 滑动窗口限流，统计 60 秒内请求次数 |

### 5.5 系统配置缓存

| 项目 | 说明 |
|---|---|
| Key | `sys_config:{key}` |
| Value | 配置值（序列化字符串） |
| Type | STRING |
| TTL | 300s |
| 用途 | 缓存 system_config 表数据，减少数据库查询 |

### 5.6 合规基准数据缓存

| 项目 | 说明 |
|---|---|
| Key | `compliance_baseline:{source_tag}` |
| Value | 合规基准终端数据（序列化） |
| Type | STRING |
| TTL | 600s |
| 用途 | 缓存合规基准采集结果，避免频繁请求外部接口 |

### 5.7 白名单缓存

| 项目 | 说明 |
|---|---|
| Key | `whitelist:all` |
| Value | 白名单规则列表（序列化） |
| Type | STRING |
| TTL | 300s |
| 用途 | 缓存白名单数据，加速合规匹配计算 |

### 5.8 定时任务暂停控制

| 项目 | 说明 |
|---|---|
| Key | `scheduler:ctrl:{task_name}` |
| Type | STRING |
| Value | `"paused"` |
| TTL | 无（手动管理） |
| 用途 | 标记定时任务暂停状态 |

说明：
- `manage.sh scheduler pause <task>` 写入该键
- `manage.sh scheduler resume <task>` 删除该键
- `_is_task_paused()` 函数在定时任务循环中检查该键，值为 `"paused"` 时跳过当轮执行
- 可用任务名：`arp_collection`、`ipguard_sync`、`firewall_query`、`compliance_check`、`auto_unblock`、`scheduled_backup`

### 5.9 Redis fail-open 降级策略

所有 Redis 交互函数统一添加 try/except 异常处理，Redis 不可用时按策略降级：

| 函数 | Redis Key | 降级行为 |
|------|-----------|---------|
| `is_token_blacklisted` | `token_blacklist:{jti}` | 返回 `False`（放行） |
| `get_token_version` | `token_version:{user_id}` | 返回 `0` |
| `increment_token_version` | `token_version:{user_id}` | 返回 `0` |
| `check_login_attempts` | `login_lock:{username}` | 返回 `False` |
| `check_captcha_required` | `login_attempts:{username}` | 返回 `False` |
| `record_failed_login` | `login_attempts:{username}` | 静默忽略 |
| `reset_login_attempts` | `login_attempts:{username}` / `login_lock:{username}` | 静默忽略 |
| `verify_captcha` | `captcha:{captcha_id}` | 返回 `False` |
| `generate_captcha` | `captcha:{captcha_id}` | 抛出异常（必须依赖 Redis） |
| `add_token_to_blacklist` | `token_blacklist:{jti}` | 静默忽略 |

---

## 6. 数据库迁移脚本

| 脚本 | 说明 |
|---|---|
| 001_initial_schema.py | 初始数据库结构（terminals 重命名前） |
| 002_terminal_baseline.py | Terminal 重命名 + ComplianceBaseline 分离 |
| 003_search_indexes.py | 搜索优化索引：whitelist.created_at、blacklist.blocked_at、blacklist.expires_at、audit_logs.ip_address |
| 004_terminal_unique_constraint.py | terminals 表联合唯一约束 uq_terminal_ip_mac + 迁移前去重 |
| 005_mac_normalized_column.py | terminals/whitelist/blacklist 三张表添加 mac_address_normalized 列，回填历史数据，创建索引 |
| 006_rbac_tables.py | RBAC 权限控制表（roles、permissions、user_roles、role_permissions）及种子数据 |
| 007_firewall_tag.py | terminals 表新增 firewall_tag 列（VARCHAR(50), nullable, default NULL） |
| 008_audit_resource_name.py | audit_logs 表新增 resource_name 列 |
| 009_audit_keyset_index.py | audit_logs 表新增 keyset 分页复合索引 |
| ... (中间版本迁移省略) |
| 031_compliance_scope.py | 新增 compliance_scope 合规范围条件表（v3.11.0） |
| 032_mac_prefix_scope_type_split.py | 将 scope_type='mac_prefix' 迁移为 'mac_prefix_arp'，支持区分MAC前缀匹配数据源（v3.12.0） |
| 033_terminal_mac_unique.py | 数据去重后删除旧联合约束，添加 mac_address_normalized 唯一约束 uq_terminal_mac（v3.12.0） |
| 034_compliance_oscillation_fixes.py | terminals 表新增 compliant_confirm_count、ip_changed_at 字段（v3.12.0） |

### 003_search_indexes.py 详情

为搜索和分页查询添加数据库索引，提升查询性能：

| 索引名 | 表 | 字段 | 用途 |
|---|---|---|---|
| idx_whitelist_created_at | whitelist | created_at | 白名单日期范围查询优化 |
| idx_blacklist_blocked_at | blacklist | blocked_at | 黑名单按阻断时间查询优化 |
| idx_blacklist_expires_at | blacklist | expires_at | 过期黑名单清理查询优化 |
| idx_audit_ip_address | audit_logs | ip_address | 审计日志按 IP 查询优化 |

### 004_terminal_unique_constraint.py 详情

- 添加 `uq_terminal_ip_mac` 联合唯一约束
- 迁移前自动去重：删除重复 (ip_address, mac_address) 记录，仅保留最新一条（MAX id）
- 不可逆迁移（downgrade 仅移除约束，不恢复已删除的重复记录）

### 005_mac_normalized_column.py 详情

为 MAC 地址格式无关搜索添加标准化列和索引，替代 `func.replace()` 全表扫描：

| 操作 | 表 | 说明 |
|---|---|---|
| ADD COLUMN | terminals | `mac_address_normalized VARCHAR(12)` |
| ADD COLUMN | whitelist | `mac_address_normalized VARCHAR(12)` |
| ADD COLUMN | blacklist | `mac_address_normalized VARCHAR(12)` |
| 数据回填 | 三张表 | `UPDATE ... SET mac_address_normalized = UPPER(REPLACE(REPLACE(REPLACE(mac_address, '-', ''), ':', ''), '.', ''))` |
| CREATE INDEX | terminals | `idx_terminal_mac_normalized` |
| CREATE INDEX | whitelist | `idx_whitelist_mac_normalized` |
| CREATE INDEX | blacklist | `idx_blacklist_mac_normalized` |

### Alembic 配置说明

**env.py 驱动兼容性：**

- 修复 asyncpg 驱动兼容性：不再将 `postgresql+asyncpg://` 替换为 `postgresql://`
- 迁移现在使用 asyncpg 驱动，无需安装 psycopg2

### 应用启动时自动迁移

除 Alembic 迁移脚本外，以下数据迁移在应用启动时由 lifespan 自动执行（无需手动运行脚本）：

**审计日志 action 值迁移：**

将 `audit_logs` 表中旧的 action 值自动更新为新命名规范：

| 旧值 | 新值 |
|---|---|
| `block_ip` | `block_terminal` |
| `unblock_ip` | `unblock_terminal` |
| `block` | `block_blacklist` |
| `unblock` | `unblock_blacklist` |

**system_config 品牌值迁移：**

将 `system_config` 表中品牌配置项（`app_name`、`login_heading` 等）的旧值 `"Terminal Access Platform"` 替换为 `"Terminal Access Manager"`。

> **注意：** 这些迁移为幂等操作，仅更新包含旧值的记录，已更新的记录不受影响。

### 备份轮转策略（v3.2.0-r2）

通过 `BACKUP_RETAIN_COUNT` 环境变量控制备份文件保留数量：

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `BACKUP_RETAIN_COUNT` | `0`（保留全部） | 保留最近 N 个备份文件，超出时自动清理最旧的 |

轮转范围：
- PostgreSQL 备份（`backups/db_*.sql`）
- Redis 备份（`backups/redis_*.rdb`）
- 配置快照（`backups/config_*.env`）

设置示例：
```bash
# 在 .env 中设置保留最近 10 个备份
BACKUP_RETAIN_COUNT=10
```
