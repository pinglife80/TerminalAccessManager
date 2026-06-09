# TerminalAccessManager 数据库设计文档

> 文档版本：v3.0.0 | 更新日期：2026-06-09

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
│ created_at   │       │ source            │       │ created_at       │
│ updated_at   │       │ source_tag        │       └──────────────────┘
└──────┬───────┘       │ compliance_status │
       │               │ wl_match_type     │       ┌──────────────────┐
       │ 1:N           └───────────────────┘       │    blacklist     │
       ├──────────────┐                            ├──────────────────┤
       │              │                            │ id            PK │
┌──────┴──────────┐   │                            │ ip_address       │
│   audit_logs    │   │                            │ mac_address      │
├─────────────────┤   │                            │ reason           │
│ id           PK │   │                            │ blocked_at       │
│ user_id     FK ─┘   │                            │ expires_at       │
│ username          │   │                            │ blocked_by       │
│ action            │   │                            │ source_tag       │
│ resource_type     │   │                            │ firewall_tag     │
│ resource_id       │   │                            │ is_auto_blocked  │
│ details           │   │                            │ auto_unblocked   │
│ ip_address        │   │                            └──────────────────┘
│ timestamp         │   │
└───────────────────┘   │
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
│ ip_address           │
│ mac_address          │
│ hostname             │
│ source_tag           │
│ created_at           │
│ updated_at           │
└──────────────────────┘
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
| ip_address | VARCHAR(45) | NOT NULL, INDEX | — | IPv4/IPv6 地址 |
| mac_address | VARCHAR(17) | NOT NULL, INDEX | — | MAC 地址（格式 XX-XX-XX-XX-XX-XX） |
| status | VARCHAR(20) | INDEX | 'unfrozen' | 终端状态 |
| comments | TEXT | | NULL | 备注 |
| timestamp | TIMESTAMP WITH TZ | INDEX | utcnow | 记录时间 |
| source | VARCHAR(50) | | 'arp' | 数据来源 |
| source_tag | VARCHAR(50) | INDEX | NULL | 数据源标签，关联 data_sources.tag |
| compliance_status | VARCHAR(20) | INDEX | 'unknown' | 合规状态 |
| wl_match_type | VARCHAR(10) | | NULL | 白名单匹配类型 |

**索引：**

| 索引名 | 类型 | 字段 |
|---|---|---|
| idx_terminal_timestamp | COMPOSITE | (mac_address, timestamp) |
| idx_ip_status | COMPOSITE | (ip_address, status) |

**约束：**

| 约束名 | 类型 | 字段 | 说明 |
|---|---|---|---|
| uq_terminal_ip_mac | UNIQUE | (ip_address, mac_address) | 防止并发 ARP 采集产生重复 (ip, mac) 记录 |

**数据字典 — status：**

| 值 | 说明 |
|---|---|
| active | 在线活跃 |
| inactive | 离线失活 |
| frozen | 已冻结（被防火墙阻断） |
| pending | 待处理 |
| unfrozen | 已解冻（默认初始状态） |

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
| created_at | TIMESTAMP WITH TZ | INDEX | utcnow | 创建时间 |

**索引：**

| 索引名 | 类型 | 字段 |
|---|---|---|
| idx_whitelist_created_at | SINGLE | created_at |

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
| blocked_at | TIMESTAMP WITH TZ | | utcnow | 阻断时间 |
| expires_at | TIMESTAMP WITH TZ | | NULL | 过期时间（NULL 表示永久） |
| blocked_by | VARCHAR(50) | NOT NULL | — | 执行阻断的用户名 |
| source_tag | VARCHAR(50) | INDEX | NULL | ARP 数据源标签 |
| firewall_tag | VARCHAR(50) | INDEX | NULL | 防火墙标签 |
| is_auto_blocked | BOOLEAN | | FALSE | 是否由合规检查自动阻断 |
| auto_unblocked | BOOLEAN | | FALSE | 是否已自动解封（合规后） |

**索引：**

| 索引名 | 类型 | 字段 |
|---|---|---|
| idx_blacklist_ip | COMPOSITE | (ip_address) |
| idx_blacklist_mac | COMPOSITE | (mac_address) |
| idx_blacklist_auto | COMPOSITE | (is_auto_blocked, auto_unblocked) |
| idx_blacklist_blocked_at | SINGLE | blocked_at |
| idx_blacklist_expires_at | SINGLE | expires_at |

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
| details | TEXT | | NULL | 操作详情（JSON 格式，json.dumps 序列化，每个 dict 包含 message 字段） |
| ip_address | VARCHAR(45) | INDEX | NULL | 请求来源 IP |
| timestamp | TIMESTAMP WITH TZ | INDEX | utcnow | 操作时间 |

**索引：**

| 索引名 | 类型 | 字段 |
|---|---|---|
| idx_audit_user_timestamp | COMPOSITE | (username, timestamp) |
| idx_audit_action | COMPOSITE | (action) |
| idx_audit_ip_address | SINGLE | ip_address |

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
| config | JSON | NOT NULL | `{}` | 连接配置（JSON 格式） |
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

存储合规基准数据，独立于数据源，用于合规检查时比对终端是否注册。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|---|---|---|---|---|
| id | INTEGER | PK, INDEX | 自增 | 主键 |
| ip_address | VARCHAR(45) | NOT NULL, INDEX | — | IPv4/IPv6 地址 |
| mac_address | VARCHAR(17) | NOT NULL, INDEX | — | MAC 地址（格式 XX-XX-XX-XX-XX-XX） |
| hostname | VARCHAR(100) | | NULL | 主机名 |
| source_tag | VARCHAR(50) | INDEX | NULL | 数据源标签 |
| created_at | TIMESTAMP WITH TZ | server_default=now() | — | 创建时间 |
| updated_at | TIMESTAMP WITH TZ | server_default=now(), onupdate=now() | — | 更新时间 |

**索引：**

| 索引名 | 类型 | 字段 |
|---|---|---|
| idx_compliance_baseline_ip_mac | COMPOSITE | (ip_address, mac_address) |

---

## 4. 数据字典汇总

### 4.1 TerminalStatus（终端状态）

| 枚举值 | 适用表 | 说明 |
|---|---|---|
| active | terminals.status | 在线活跃 |
| inactive | terminals.status | 离线失活 |
| frozen | terminals.status | 已冻结（被防火墙阻断） |
| pending | terminals.status | 待处理 |
| unfrozen | terminals.status | 已解冻（默认初始状态） |

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
- 可用任务名：`arp_collection`、`ipguard_sync`、`firewall_query`、`compliance_check`、`auto_unblock`

---

## 6. 数据库迁移脚本

| 脚本 | 说明 |
|---|---|
| 001_initial_schema.py | 初始数据库结构（terminals 重命名前） |
| 002_terminal_baseline.py | Terminal 重命名 + ComplianceBaseline 分离 |
| 003_search_indexes.py | 搜索优化索引：whitelist.created_at、blacklist.blocked_at、blacklist.expires_at、audit_logs.ip_address |
| 004_terminal_unique_constraint.py | terminals 表联合唯一约束 uq_terminal_ip_mac + 迁移前去重 |

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
