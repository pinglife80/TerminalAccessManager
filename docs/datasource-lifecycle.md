# 数据源全生命周期技术文档

> 文档版本：v3.2.0-r8 | 更新日期：2026-06-16

本文档详细描述 TerminalAccessManager 系统中数据源从配置、采集、解析、合规判定到自动处置的完整生命周期，涵盖架构设计、数据格式、输入输出规范和定时调度机制。

---

## 目录

- [1. 系统架构概览](#1-系统架构概览)
- [2. 数据源配置](#2-数据源配置)
- [3. 数据源绑定](#3-数据源绑定)
- [4. 合规基线配置](#4-合规基线配置)
- [5. ARP 数据采集](#5-arp-数据采集)
- [6. IP-Guard 基线同步](#6-ip-guard-基线同步)
- [7. 合规判定逻辑](#7-合规判定逻辑)
- [8. 自动封堵流程](#8-自动封堵流程)
- [9. 自动解封流程](#9-自动解封流程)
- [10. 定时调度机制](#10-定时调度机制)
- [11. 配置加密机制](#11-配置加密机制)
- [12. 数据模型](#12-数据模型)
- [13. API 接口](#13-api-接口)
- [14. 错误处理与容错](#14-错误处理与容错)
- [15. 核心业务流程总览](#15-核心业务流程总览)
- [16. 数据源安全性评估](#16-数据源安全性评估)

---

## 1. 系统架构概览

### 1.1 核心业务链

系统围绕"终端准入控制"这一核心目标，构建了从数据采集到自动处置的完整闭环：

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         数据源全生命周期                                  │
│                                                                         │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐          │
│  │ ARP 数据  │    │ IP-Guard │    │  合规    │    │  自动    │          │
│  │  采集    │───>│ 基线同步  │───>│  判定    │───>│  处置    │          │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘          │
│       │                                               │               │
│       v                                               v               │
│  ┌──────────┐                                   ┌──────────┐          │
│  │ Terminal │                                   │ Sangfor  │          │
│  │   表     │                                   │  防火墙  │          │
│  └──────────┘                                   └──────────┘          │
│       │                                               │               │
│       └───────────── 自动解封 ◄────────────────────────┘               │
│                      (合规恢复)                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 三类数据源角色

| 数据源类型 | 角色 | 说明 |
|-----------|------|------|
| `arp_ssh` / `arp_api` | **数据采集端** | 从交换机获取 ARP 表（IP+MAC 映射），发现网络中的终端设备 |
| `sangfor` | **策略执行端** | 深信服防火墙，执行封堵/解封操作，不产生数据 |
| `ipguard`（合规基线） | **合规基准端** | IP-Guard 终端管理系统，提供合法终端的 IP+MAC 基线数据 |

### 1.3 组件关系图

```
                    ┌─────────────────────┐
                    │     前端 (React)     │
                    │  DataSources.tsx     │
                    │  BindingsTab.tsx     │
                    │  ComplianceTab.tsx   │
                    └──────────┬──────────┘
                               │ HTTP API
                    ┌──────────▼──────────┐
                    │   后端 API 层        │
                    │  data_sources.py     │
                    │  compliance_baselines│
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
   ┌──────────▼──────┐ ┌──────▼───────┐ ┌──────▼───────┐
   │ DataSourceService│ │ArpCollector  │ │Compliance    │
   │ (CRUD+加密)      │ │Service       │ │Service       │
   └────────┬────────┘ │(采集+解析)    │ │(判定+封堵)    │
            │          └──────┬───────┘ └──────┬───────┘
            │                 │                │
   ┌────────▼────────┐       │       ┌────────▼────────┐
   │   PostgreSQL    │       │       │  SangforService │
   │   (数据存储)     │       │       │  (防火墙交互)    │
   └─────────────────┘       │       └────────┬────────┘
                             │                │
                    ┌────────▼────────┐ ┌─────▼──────┐
                    │  交换机/API     │ │ Sangfor AF │
                    │ (ARP 数据源)    │ │  防火墙     │
                    └─────────────────┘ └────────────┘
                             │
                    ┌────────▼────────┐
                    │   IP-Guard DB   │
                    │ (合规基线数据)   │
                    └─────────────────┘
```

---

## 2. 数据源配置

### 2.1 数据源类型与配置字段

每种数据源类型有独立的配置字段定义，前端根据类型动态渲染表单。

#### arp_ssh — SSH 采集交换机 ARP 表

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `host` | text | 是 | — | 交换机 IP 地址 |
| `port` | number | 是 | `22` | SSH 端口 |
| `username` | text | 是 | — | SSH 用户名 |
| `password` | password | 是 | — | SSH 密码（加密存储） |
| `command` | text | 是 | `show arp` | 执行的 ARP 查看命令 |

**创建请求示例**：

```json
{
  "name": "核心交换机-1F",
  "type": "arp_ssh",
  "tag": "switch-1f",
  "config": {
    "host": "192.168.1.1",
    "port": 22,
    "username": "admin",
    "password": "MySecret123",
    "command": "show arp"
  },
  "enabled": true
}
```

#### arp_api — HTTP API 采集 ARP 数据

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `url` | text | 是 | — | API 地址 |
| `method` | select | 是 | `GET` | HTTP 方法：GET / POST |
| `headers` | text(JSON) | 否 | — | 自定义请求头（JSON 格式） |
| `auth_type` | select | 是 | `none` | 认证方式：none / bearer / basic / header |
| `header_name` | text | 否 | `X-Auth-Token` | 自定义 Header 名（auth_type=header 时生效） |
| `token` | password | 否 | — | Token 或密码（加密存储） |

**创建请求示例**：

```json
{
  "name": "ARP API 服务",
  "type": "arp_api",
  "tag": "arp-api-01",
  "config": {
    "url": "https://api.example.com/arp",
    "method": "GET",
    "auth_type": "bearer",
    "token": "eyJhbGciOiJIUzI1NiIs..."
  },
  "enabled": true
}
```

#### sangfor — 深信服防火墙

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `base_url` | text | 是 | — | 防火墙 API 地址 |
| `username` | text | 是 | — | 管理员用户名 |
| `password` | password | 是 | — | 管理员密码（加密存储） |
| `verify_ssl` | select | 是 | `false` | 是否验证 SSL 证书 |
| `ca_bundle` | text | 否 | — | CA 证书包路径 |

**创建请求示例**：

```json
{
  "name": "深信服防火墙-主",
  "type": "sangfor",
  "tag": "sangfor-main",
  "config": {
    "base_url": "https://10.0.0.1",
    "username": "admin",
    "password": "SangforPass!",
    "verify_ssl": false,
    "ca_bundle": ""
  },
  "enabled": true
}
```

### 2.2 创建流程

```
前端表单提交
    │
    ▼
POST /api/v1/data-sources/
    │
    ▼
权限校验 (datasource:write)
    │
    ▼
DataSourceService.create_data_source()
    ├── 类型校验 (arp_ssh / arp_api / sangfor)
    ├── 唯一性校验 (name + tag)
    ├── 配置加密 (encrypt_config)
    │   └── 递归遍历 config，对含 password/secret/api_key/token/passphrase 的字段加密
    │       └── 加密后值带 "ENC:" 前缀
    └── 写入 data_sources 表
    │
    ▼
审计日志 (create_datasource)
    │
    ▼
返回 DataSourceResponse
```

### 2.3 数据源响应格式

```json
{
  "id": 1,
  "name": "核心交换机-1F",
  "type": "arp_ssh",
  "tag": "switch-1f",
  "config": {
    "host": "192.168.1.1",
    "port": 22,
    "username": "admin",
    "password": "MySecret123",
    "command": "show arp"
  },
  "enabled": true,
  "last_sync_at": "2026-06-11T10:00:00Z",
  "last_sync_status": "success",
  "last_sync_error": null,
  "created_at": "2026-06-11T08:00:00Z",
  "updated_at": "2026-06-11T10:00:00Z"
}
```

> **注意**：API 返回的 config 中敏感字段已自动解密，明文展示。

---

## 3. 数据源绑定

### 3.1 绑定关系

绑定建立 ARP 数据源与防火墙的关联，用于自动封堵时查找对应的防火墙：

```
┌─────────────────┐     绑定     ┌─────────────────┐
│  ARP 数据源      │ ──────────> │  防火墙          │
│  (arp_ssh/api)  │             │  (sangfor)       │
│  tag: switch-1f │             │  tag: sangfor-1  │
└─────────────────┘             └─────────────────┘
```

一个 ARP 源可绑定多个防火墙（多防火墙冗余场景），一个防火墙也可被多个 ARP 源绑定。

### 3.2 创建绑定

**请求**：

```json
POST /api/v1/data-sources/bindings/
{
  "arp_source_tag": "switch-1f",
  "firewall_tag": "sangfor-1"
}
```

**校验规则**：
- `arp_source_tag` 必须对应 `type=arp_ssh` 或 `arp_api` 的数据源
- `firewall_tag` 必须对应 `type=sangfor` 的数据源
- 同一 `(arp_source_tag, firewall_tag)` 组合不可重复

### 3.3 绑定响应格式

```json
{
  "id": 1,
  "arp_source_tag": "switch-1f",
  "firewall_tag": "sangfor-1",
  "created_at": "2026-06-11T08:00:00Z"
}
```

---

## 4. 合规基线配置

### 4.1 IP-Guard 合规基线

IP-Guard 是终端准入管理系统，其数据库中的 `terminal_info` 表存储了合法终端的 IP+MAC 映射，作为合规判定的基准数据。

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `host` | text | 是 | — | IP-Guard 数据库地址 |
| `port` | number | 是 | `3306` | 数据库端口 |
| `username` | text | 是 | — | 数据库用户名 |
| `password` | password | 是 | — | 数据库密码（加密存储） |
| `database` | text | 是 | `ipguard` | 数据库名 |

**创建请求示例**：

```json
{
  "name": "IP-Guard 生产环境",
  "type": "ipguard",
  "tag": "ipguard-prod",
  "config": {
    "host": "192.168.1.100",
    "port": 3306,
    "username": "readonly",
    "password": "DbPassword!",
    "database": "ipguard"
  },
  "enabled": true
}
```

### 4.2 合规基线响应格式

```json
{
  "id": 1,
  "name": "IP-Guard 生产环境",
  "type": "ipguard",
  "tag": "ipguard-prod",
  "config": { ... },
  "enabled": true,
  "last_sync_at": "2026-06-11T10:00:00Z",
  "last_sync_status": "success",
  "last_sync_error": null,
  "created_at": "2026-06-11T08:00:00Z",
  "updated_at": "2026-06-11T10:00:00Z"
}
```

---

## 5. ARP 数据采集

### 5.1 触发方式

| 触发方式 | API | 说明 |
|---------|-----|------|
| **手动触发** | `POST /api/v1/data-sources/{source_id}/sync` | 用户在 Web UI 点击"同步"按钮 |
| **定时调度** | `scheduled_arp_collection()` | 默认每 5 分钟自动执行 |

### 5.2 SSH 采集流程 (arp_ssh)

```
ArpCollectorService.collect_from_ssh(source)
    │
    ├── 1. 从 source.config 读取连接参数
    │      host, port, username, password, command
    │
    ├── 2. SSH 连接（netmiko ConnectHandler，在 asyncio.to_thread 中执行避免阻塞）
    │      根据命令前缀自动检测设备类型（display→huawei, show→cisco_ios）
    │      自动处理分页（--More--）和提示符检测
    │      conn = ConnectHandler(device_type=..., host=..., ...)
    │      output = conn.send_command(command, read_timeout=60)
    │
    ├── 3. 解析输出 (_parse_arp_output)
    │      支持三种格式（详见 5.3）
    │
    ├── 4. 处理条目 (process_arp_entries)
    │      详见第 5.4 节
    │
    └── 5. 更新同步状态
           entries > 0 → last_sync_status = "success"
           entries = 0 → last_sync_status = "success"（无数据但采集成功）
           failed     → last_sync_status = "failed" + last_sync_error
```

### 5.3 ARP 输出解析格式

`_parse_arp_output()` 支持三种交换机输出格式，按优先级依次尝试匹配：

#### Cisco 格式

```
Internet  192.168.1.1   2   aa11.bb22.cc33  ARPA  Vlan10
```

正则：`Internet\s+(\d+\.\d+\.\d+\.\d+)\s+\S+\s+([0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})`

MAC 转换：`aa11.bb22.cc33` → `aa11bb22cc33` → `AA-11-BB-22-CC-33`

#### 华为/H3C 格式

```
192.168.1.1  aa11-bb22-cc33  I  Vlanif10
```

正则：`(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4})`

MAC 转换：`aa11-bb22-cc33` → `aa11bb22cc33` → `AA-11-BB-22-CC-33`

#### 通用格式

```
192.168.1.1  AA:11:BB:22:CC:33
192.168.1.2  AA-11-BB-22-CC-33
```

正则：`(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2})`

MAC 转换：冒号/连字符统一转为 `XX-XX-XX-XX-XX-XX`

#### 解析输出

所有格式统一输出为：

```json
[
  {"ip_address": "192.168.1.1", "mac_address": "AA-11-BB-22-CC-33"},
  {"ip_address": "192.168.1.2", "mac_address": "AA-11-BB-22-CC-44"}
]
```

### 5.4 API 采集流程 (arp_api)

```
ArpCollectorService.collect_from_api(source)
    │
    ├── 1. 从 source.config 读取请求参数
    │      url, method, headers, auth_type, token
    │
    ├── 2. 构建认证头
    │      auth_type=bearer → headers["Authorization"] = "Bearer {token}"
    │      auth_type=header → headers[config.header_name 或 "X-Auth-Token"] = token
    │
    ├── 3. 发起 HTTP 请求 (httpx.AsyncClient, timeout=30s)
    │
    ├── 4. 解析 JSON 响应 (_parse_api_response)
    │      支持多种格式（详见 5.5）
    │
    ├── 5. 处理条目 (process_arp_entries)
    │
    └── 6. 更新同步状态
```

### 5.5 API 响应解析格式

`_parse_api_response()` 支持以下 JSON 响应结构：

#### 直接列表

```json
[
  {"ip_address": "192.168.1.1", "mac_address": "AA-11-BB-22-CC-33"},
  {"ip": "192.168.1.2", "mac": "AA:11:BB:22:CC:44"}
]
```

#### 包装格式

```json
{"data": [...]}       // data 键
{"entries": [...]}    // entries 键
{"results": [...]}    // results 键
{"arp": [...]}        // arp 键
{"devices": [...]}    // devices 键
{"records": [...]}    // records 键
```

#### 字段名兼容

| 优先级 | IP 字段名 | MAC 字段名 |
|--------|----------|-----------|
| 1 | `ip_address` | `mac_address` |
| 2 | `ipv4_address` | — |
| 3 | `ip` | `mac` |
| 4 | `ipAddress` | `macAddress` |

### 5.6 条目处理流程 (process_arp_entries)

这是 ARP 采集的核心处理逻辑，每条 ARP 条目经历以下步骤：

```
process_arp_entries(entries, source_tag)
    │
    ├── 步骤 1: MAC 地址规范化
    │   输入: "aa:11:bb:22:cc:33" / "aa11.bb22.cc33" / "aa-11-bb-22-cc-33"
    │   输出: "AA-11-BB-22-CC-33"
    │   规则: 去除所有分隔符 → 转大写 → 每2字符插入 "-"
    │   校验: 规范化后长度必须为17，原始12位hex必须为字母数字
    │
    ├── 步骤 2: 数据库 Upsert
    │   ├── 按 (ip_address, mac_address) 查找现有记录
    │   ├── 已存在: 更新 timestamp + source_tag + source="arp"
    │   └── 不存在: 创建新记录
    │       status="unblocked", source="arp", compliance_status="unknown"
    │
    ├── 步骤 3: 批量合规检查
    │   ├── 查找 source_tag 下 compliance_status="unknown" 的记录
    │   ├── 调用 ComplianceService.batch_check_compliance()
    │   ├── 更新 compliance_status: bypass / compliant / non_compliant
    │   └── 更新 wl_match_type (仅 bypass)
    │
    └── 步骤 4: 触发自动封堵 (fire-and-forget)
        └── 如果 non_compliant > 0 → asyncio.create_task(_auto_block_task)
            使用独立数据库会话，避免与父请求会话冲突
```

### 5.7 同步结果格式

```json
{
  "success": true,
  "message": "Processed 150 ARP entries from 'switch-1f'",
  "entries_processed": 150,
  "entries_added": 12,
  "entries_updated": 138,
  "errors": []
}
```

---

## 6. IP-Guard 基线同步

### 6.1 触发方式

| 触发方式 | API | 说明 |
|---------|-----|------|
| **手动触发** | `POST /api/v1/compliance-baselines/{baseline_id}/sync` | 用户在 Web UI 点击"同步"按钮 |
| **定时调度** | `scheduled_ipguard_sync()` | 默认每 10 分钟自动执行 |
| **被动触发** | `_load_all_ipguard_cache()` | 合规检查时，若 Redis 缓存无数据则自动触发同步 |

### 6.2 同步流程

```
ComplianceService.sync_ipguard_data(source_tag)
    │
    ├── 1. 查找 ComplianceBaseline (by tag)
    │      校验: baseline 必须存在且 enabled=True
    │
    ├── 2. 连接 IP-Guard 数据库 (asyncpg)
    │      host, port, username, password, database
    │      timeout=30s
    │
    ├── 3. 执行 SQL 查询
    │      SELECT ip_address, mac_address
    │      FROM terminal_info
    │      WHERE ip_address IS NOT NULL AND mac_address IS NOT NULL
    │
    ├── 4. 缓存到 Redis
    │      key: "ipguard:{tag}"
    │      TTL: 600 秒 (10 分钟)
    │      value: JSON 数组 [{"ip_address": "...", "mac_address": "..."}, ...]
    │
    └── 5. 更新同步状态
           success → last_sync_status = "success"
           failed  → last_sync_status = "failed" + last_sync_error
```

### 6.3 同步结果格式

```json
{
  "success": true,
  "entries": 1250,
  "message": "Synced 1250 entries from IPGuard"
}
```

---

## 7. 合规判定逻辑

### 7.1 判定优先级

合规判定按以下优先级依次匹配，首次命中即返回：

```
1. 白名单匹配 → compliance_status = "bypass"
   bypass 终端自动同步白名单 comments 到 Terminal.comments（格式：`Whitelist: {comments}`）
2. IP-Guard 基线匹配 → compliance_status = "compliant"
3. 都不匹配 → compliance_status = "non_compliant"
```

### 7.2 白名单匹配规则

白名单支持三种匹配模式，匹配结果记录在 `wl_match_type` 字段：

| wl_match_type | 含义 | 规则 |
|---------------|------|------|
| `"mac"` | 仅 MAC 匹配 | 白名单条目只指定 MAC，终端 MAC 精确匹配 |
| `"ip"` | 仅 IP 匹配 | 白名单条目只指定 IP，终端 IP 匹配（支持 CIDR/范围） |
| `"both"` | IP+MAC 同时匹配 | 白名单条目同时指定 IP 和 MAC，两者都匹配 |

#### IP 匹配模式 (pattern_type)

| pattern_type | 格式 | 示例 | 说明 |
|--------------|------|------|------|
| `single_ip` | 单个 IP | `192.168.1.100` | 精确匹配 |
| `cidr` | CIDR 网段 | `192.168.1.0/24` | IP 属于该网段即匹配 |
| `ip_range` | IP 范围 | `192.168.1.1-100` | 同 /24 子网内最后一位在 1-100 范围即匹配 |

#### 白名单匹配逻辑

```
对于每条白名单条目:
  ├── pattern_type == "mac_only": 仅比较 MAC（精确匹配）
  ├── 同时指定 ip_pattern + mac_address: IP 和 MAC 都必须匹配 → "both"
  ├── 仅指定 ip_pattern: IP 匹配即可 → "ip"
  └── 仅指定 mac_address: MAC 匹配即可 → "mac"
```

#### 白名单变更联动流程

白名单的添加或删除会触发合规状态重算，并联动封堵/解封操作：

```
白名单添加/删除
    │
    ▼
失效白名单缓存
    │  删除 Redis key "whitelist:all"，确保下次读取最新数据
    │
    ▼
recalculate_all_compliance()
    │  重新加载白名单 + IP-Guard 基线
    │  对所有终端重新执行合规判定
    │  更新 compliance_status（bypass / compliant / non_compliant）
    │
    ▼
合规状态更新
    │  ├── 新增 bypass：原 non_compliant → bypass（免检）
    │  ├── 新增 compliant：原 non_compliant → compliant（合规）
    │  ├── 移除 bypass：原 bypass → compliant 或 non_compliant（重新判定）
    │  └── 移除 compliant（仅白名单）：原 compliant → non_compliant（不合规）
    │
    ▼
联动封堵/解封
    │  ├── 新 non_compliant 终端 → 触发自动封堵（auto_block_non_compliant）
    │  │   调用 Sangfor API 封堵 IP → Terminal.status = "blocked"
    │   └── 恢复合规终端 → 触发自动解封（auto_unblock_compliant）
    │       调用 Sangfor API 解封 IP → Terminal.status = "unblocked"
```

### 7.3 IP-Guard 基线匹配规则

IP-Guard 匹配要求 **IP + MAC 同时匹配**：

```
对于 IP-Guard 缓存中的每条记录:
  终端 IP == 记录 IP  AND  终端 MAC(规范化) == 记录 MAC(规范化)
```

MAC 规范化：去除 `:` 和 `-`，转大写后比较。

### 7.4 批量合规检查

`batch_check_compliance()` 是性能优化版本，一次性加载所有数据到内存：

```
batch_check_compliance(entries)
    │
    ├── 1. 加载白名单数据到内存
    │      优先从 Redis 缓存读取 (key: "whitelist:all", TTL: 300s)
    │      缓存未命中则从数据库加载并写入缓存
    │
    ├── 2. 加载所有 IP-Guard 数据到内存
    │      优先从 Redis 缓存读取 (key: "ipguard:{tag}", TTL: 600s)
    │      缓存未命中则触发 sync_ipguard_data() 同步后读取
    │
    ├── 3. 逐条判定
    │      白名单匹配 → bypass
    │      IP-Guard 匹配 → compliant
    │      都不匹配 → non_compliant
    │
    └── 4. 返回 ComplianceCheckResult
           total_checked, compliant, bypass, non_compliant
           details (≤1000条时包含明细)
```

### 7.5 合规检查结果格式

```json
{
  "total_checked": 150,
  "compliant": 80,
  "bypass": 50,
  "non_compliant": 20,
  "unknown": 0,
  "message": null,
  "details": {
    "compliant": [
      {"ip_address": "192.168.1.10", "mac_address": "AA-11-BB-22-CC-33", "source_tag": "switch-1f", "compliance_status": "compliant"}
    ],
    "bypass": [
      {"ip_address": "192.168.1.1", "mac_address": "AA-11-BB-22-CC-01", "source_tag": "switch-1f", "compliance_status": "bypass", "wl_match_type": "ip"}
    ],
    "non_compliant": [
      {"ip_address": "192.168.1.200", "mac_address": "AA-11-BB-22-CC-FF", "source_tag": "switch-1f", "compliance_status": "non_compliant"}
    ]
  }
}
```

> **注意**：当检查条目超过 1000 条时，`details` 为 `null`，仅返回计数。

---

## 8. 自动封堵流程

### 8.1 触发条件

- ARP 采集后发现 `non_compliant` 终端（自动触发，fire-and-forget）
- 手动触发：`POST /api/v1/data-sources/compliance/auto-block`

### 8.2 封堵流程

```
ComplianceService.auto_block_non_compliant(arp_source_tag, block_time="30d")
    │
    ├── 1. 查找不合规终端
    │      条件: source_tag=arp_source_tag
    │            AND compliance_status="non_compliant"
    │            AND status!="blocked"
    │      排除: 已在黑名单中且未解封的 IP
    │
    ├── 2. 查找关联防火墙
    │      通过 DataSourceBinding 查找 firewall_tags
    │      无绑定 → 返回错误，跳过所有终端
    │
    ├── 3. 逐个终端封堵
    │      对每个终端，在每个关联防火墙上执行封堵:
    │      ├── 调用 SangforService.block_ip([ip], block_time)
    │      ├── 封堵成功:
    │      │   ├── Terminal.status = "blocked"
    │      │   ├── Terminal.firewall_tag = fw_tag（记录执行封堵的防火墙标签）
    │      │   ├── Terminal.comments = "Auto-blocked by TAM on firewall [{fw_tag}]"
    │      │   └── 为每个防火墙创建 Blacklist 记录
    │      │       is_auto_blocked=True, auto_unblocked=False
    │      │       expires_at = now + block_time
    │      └── 封堵失败: 标记为 skipped，不创建 Blacklist 记录
    │
    └── 4. 返回 AutoBlockResult
```

### 8.3 封堵时长格式

`block_time` 参数支持以下格式：

| 格式 | 示例 | 说明 |
|------|------|------|
| `Nd` | `30d` | N 天（默认） |
| `Nh` | `24h` | N 小时 |
| `Nm` | `60m` | N 分钟 |

默认值：`30d`（30 天）

### 8.4 Sangfor 防火墙 API 交互

使用 Sangfor AF 8.0+ 的 whiteblacklist API（永久黑名单），而非临时 blockip API。

```
SangforService
    │
    ├── 认证
    │   POST {base_url}/api/v1/namespaces/public/login
    │   Body: {"name": username, "password": password}
    │   Response: {"data": {"loginResult": {"token": "..."}}}
    │   → 将 token 设置到 session cookies
    │
    ├── 封堵（永久黑名单）
    │   1. 幂等检查：先查询是否已存在 TAM 管理的条目
    │      GET {base_url}/api/v1/namespaces/public/whiteblacklist?type=BLACK&url={ip}
    │      若已存在且描述以 "TAM" 开头 → 跳过
    │
    │   2. 添加黑名单条目
    │      POST {base_url}/api/v1/namespaces/public/whiteblacklist
    │      Body: {"url": ip, "type": "BLACK", "description": desc, "enable": true}
    │      描述格式: TAM-{source_tag}-{reason}（过滤冒号等特殊字符）
    │      示例: TAM-lab-Auto-blocked
    │      Response: {"code": 0, ...}
    │      → code==0 表示成功，409 表示已存在（跳过）
    │
    ├── 解封（删除黑名单条目）
    │   1. 安全检查：先查询条目，验证描述以 "TAM" 开头
    │      GET {base_url}/api/v1/namespaces/public/whiteblacklist?type=BLACK&url={ip}
    │      非 TAM 管理的条目 → 跳过（防止误删 AF 自身安全策略条目）
    │
    │   2. 删除黑名单条目
    │      DELETE {base_url}/api/v1/namespaces/public/whiteblacklist/{ip}
    │      Response: {"code": 0, ...}
    │      → code==0 表示成功
    │
    ├── 查询黑名单条目
    │   GET {base_url}/api/v1/namespaces/public/whiteblacklist?type=BLACK&url={ip}
    │   Response: {"code": 0, "data": {"items": [...]}}
    │   → 匹配 item.url == ip 的条目
    │
    └── 401 自动重试
        所有 API 请求遇到 401 时自动重新认证后重试
        (_request_with_retry 机制)
```

### 8.5 自动封堵结果格式

```json
{
  "total_non_compliant": 20,
  "blocked": 18,
  "skipped": 2,
  "errors": [
    "Failed to block 192.168.1.201 on firewall 'sangfor-1'"
  ],
  "details": [
    {
      "ip_address": "192.168.1.200",
      "mac_address": "AA-11-BB-22-CC-FF",
      "action": "blocked",
      "firewall_tags": ["sangfor-1"]
    }
  ]
}
```

> **注意**：当封堵明细超过 100 条时，`details` 为 `null`。

### 8.6 预览模式 (dry_run)

设置 `dry_run=true` 可预览封堵操作而不实际执行：

```json
POST /api/v1/data-sources/compliance/auto-block
{
  "arp_source_tag": "switch-1f",
  "block_time": "30d",
  "dry_run": true
}
```

预览结果中 `action` 为 `"would_block"` 而非 `"blocked"`。

---

## 9. 自动解封流程

### 9.1 触发方式

| 触发方式 | 说明 |
|---------|------|
| **定时调度** | `scheduled_auto_unblock()`，默认每 10 分钟 |
| **手动触发** | `POST /api/v1/data-sources/compliance/auto-unblock` |

### 9.2 解封流程

```
ComplianceService.auto_unblock_compliant()
    │
    ├── 1. 查找自动封堵记录
    │      条件: is_auto_blocked=True AND auto_unblocked=False
    │
    ├── 2. 加载合规数据到内存
    │      白名单 + IP-Guard 基线
    │
    ├── 3. 逐条检查合规状态
    │      ├── 现在合规 (白名单或IP-Guard匹配):
    │      │   ├── 调用防火墙 API 解封
    │      │   ├── Blacklist.auto_unblocked = True
    │      │   ├── Terminal.status = "unblocked"
    │      │   ├── Terminal.firewall_tag = None
    │      │   ├── Terminal.comments = "Auto-unblocked by TAM from firewall [{fw_tag}]"
    │      │   └── Terminal.compliance_status = "bypass" 或 "compliant"
    │      └── 仍然不合规: 跳过
    │
    └── 4. 返回 AutoUnblockResult
```

### 9.3 自动解封结果格式

```json
{
  "total_auto_blocked": 18,
  "unblocked": 5,
  "skipped": 13,
  "errors": [],
  "details": [
    {
      "ip_address": "192.168.1.200",
      "mac_address": "AA-11-BB-22-CC-FF",
      "action": "unblocked",
      "reason": "now_compliant"
    }
  ]
}
```

---

## 10. 定时调度机制

### 10.1 调度任务列表

应用启动时（`lifespan` 函数），创建 5 个后台 asyncio Task：

| 任务名 | 函数 | 默认间隔 | 配置键 | 说明 |
|--------|------|---------|--------|------|
| ARP 采集 | `scheduled_arp_collection()` | 300s (5min) | `scheduler_arp_collection_interval` | 遍历所有 enabled 的 ARP 数据源，逐个采集 |
| IPGuard 同步 | `scheduled_ipguard_sync()` | 600s (10min) | `scheduler_ipguard_sync_interval` | 遍历所有 enabled 的合规基线，逐个同步 |
| 合规检查 | `scheduled_compliance_check()` | 300s (5min) | `scheduler_compliance_check_interval` | 查找 compliance_status="unknown" 的终端，执行合规判定 |
| 自动解封 | `scheduled_auto_unblock()` | 600s (10min) | `scheduler_auto_unblock_interval` | 检查自动封堵记录，合规的自动解封 |
| 黑名单清理 | `cleanup_expired_blacklist()` | 3600s (1h) | `scheduler_firewall_query_interval` | 清理过期的黑名单记录 |

### 10.2 调度控制机制

#### 间隔配置

- 从 `system_config` 表读取间隔值
- 有效范围：30 - 86400 秒
- 可通过 Web UI 系统配置页面修改

#### 暂停控制

通过 Redis key 控制任务暂停：

```
key: scheduler:ctrl:{task_name}
value: "paused" → 任务暂停
不存在 → 任务正常运行
```

#### 分布式锁

通过 Redis `SET NX EX` 实现分布式锁，防止多实例重复执行：

```
key: scheduler:lock:{task_name}
value: 实例标识
TTL: 间隔时间 * 2
获取锁失败 → 跳过本次执行
```

### 10.3 调度执行流程

```
每个调度任务:
    │
    ├── 1. 检查暂停状态
    │      Redis GET scheduler:ctrl:{task_name}
    │      值为 "paused" → 跳过
    │
    ├── 2. 获取分布式锁
    │      Redis SET NX EX scheduler:lock:{task_name}
    │      获取失败 → 跳过（其他实例正在执行）
    │
    ├── 3. 读取间隔配置
    │      从 system_config 表读取
    │      范围限制: 30-86400 秒
    │
    ├── 4. 执行任务
    │
    ├── 5. 释放锁
    │
    └── 6. 等待间隔时间后重复
```

---

## 11. 配置加密机制

### 11.1 加密算法

- **算法**：Fernet (AES-128-CBC + HMAC-SHA256)
- **密钥来源**：优先使用 `ENCRYPTION_KEY` 环境变量，回退到 `SECRET_KEY`（通过 SHA256 派生 32 字节 Fernet 密钥）
- **密钥派生**：`hashlib.sha256(key_source.encode()).digest()` → `base64.urlsafe_b64encode()`

### 11.2 加密范围

自动加密 config 中 key 包含以下关键词的字段：

| 关键词 | 示例字段 |
|--------|---------|
| `password` | password, db_password |
| `secret` | secret_key, client_secret |
| `api_key` | api_key, x_api_key |
| `token` | token, access_token |
| `passphrase` | passphrase, ssh_passphrase |

### 11.3 加密流程

```
encrypt_config(config)
    │
    ├── 递归遍历 config 字典
    ├── 对字符串值: key 包含敏感关键词 → encrypt_value(value)
    │   输出: "ENC:gAAAAA..." (带 ENC: 前缀)
    ├── 对嵌套字典: 递归处理
    └── 其他值: 原样保留
```

### 11.4 解密流程

```
decrypt_config(config)
    │
    ├── 递归遍历 config 字典
    ├── 对字符串值: 以 "ENC:" 开头 → decrypt_value(value)
    │   去除 "ENC:" 前缀后解密
    ├── 对嵌套字典: 递归处理
    └── 其他值: 原样保留
```

**expunge 隔离**：调用 `decrypt_config` 前先 `db.expunge(source)` 分离 SQLAlchemy 对象，防止解密后的明文在 session commit 时回写数据库。`update_data_source` 在 commit 后再 expunge + 解密用于响应返回。

### 11.5 自动加解密时机

| 操作 | 加密 | 解密 |
|------|------|------|
| 创建数据源 | `create_data_source` → `encrypt_config(data.config)` | — |
| 更新数据源 | `update_data_source` → `encrypt_config(data.config)` → commit → expunge → `decrypt_config`（响应用） | — |
| 删除数据源 | — | — |
| 读取数据源 | — | `get_data_source_by_id` → expunge → `decrypt_config(source.config)` |
| 列出数据源 | — | `list_data_sources` → 逐条 expunge → `decrypt_config` |
| 连接测试 | — | `test_connection` → 读取时自动解密 |
| ARP 采集 | — | `collect_from_ssh/api` → 读取 config 时自动解密 |
| 定时采集 | — | `run_scheduled_collection` → `decrypt_config(source.config)` |
| 定时合规检查 | — | `sync_compliance_baseline_data` → `decrypt_config(config)` |
| 防火墙封堵/解封 | — | `_block_on_firewall` / `_unblock_on_firewall` → `decrypt_config(config)` |

---

## 12. 数据模型

### 12.1 data_sources 表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | Integer | PK, INDEX | 主键 |
| `name` | String(100) | UNIQUE, NOT NULL | 数据源名称 |
| `type` | String(20) | NOT NULL | 类型：arp_ssh / arp_api / sangfor |
| `tag` | String(50) | UNIQUE, NOT NULL, INDEX | 唯一标识符 |
| `config` | JSON | NOT NULL, DEFAULT {} | 连接配置（敏感字段加密存储） |
| `enabled` | Boolean | DEFAULT true | 是否启用 |
| `last_sync_at` | DateTime(TZ) | NULL | 最后同步时间 |
| `last_sync_status` | String(20) | NULL | 最后同步状态：success / failed |
| `last_sync_error` | Text | NULL | 最后同步错误信息 |
| `created_at` | DateTime(TZ) | DEFAULT now() | 创建时间 |
| `updated_at` | DateTime(TZ) | DEFAULT now(), ON UPDATE | 更新时间 |

### 12.2 data_source_bindings 表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | Integer | PK, INDEX | 主键 |
| `arp_source_tag` | String(50) | NOT NULL, INDEX | ARP 数据源 tag |
| `firewall_tag` | String(50) | NOT NULL | 防火墙 tag |
| `created_at` | DateTime(TZ) | DEFAULT now() | 创建时间 |

**唯一约束**：`(arp_source_tag, firewall_tag)`

### 12.3 compliance_baselines 表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | Integer | PK, INDEX | 主键 |
| `name` | String(100) | UNIQUE, NOT NULL | 基线名称 |
| `type` | String(20) | NOT NULL | 类型：ipguard |
| `tag` | String(50) | UNIQUE, NOT NULL, INDEX | 唯一标识符 |
| `config` | JSON | NOT NULL, DEFAULT {} | 连接配置（加密存储） |
| `enabled` | Boolean | DEFAULT true | 是否启用 |
| `last_sync_at` | DateTime(TZ) | NULL | 最后同步时间 |
| `last_sync_status` | String(20) | NULL | 最后同步状态 |
| `last_sync_error` | Text | NULL | 最后同步错误 |
| `created_at` | DateTime(TZ) | DEFAULT now() | 创建时间 |
| `updated_at` | DateTime(TZ) | DEFAULT now(), ON UPDATE | 更新时间 |

### 12.4 terminals 表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | Integer | PK, INDEX | 主键 |
| `ip_address` | String(45) | NOT NULL, INDEX | IP 地址 |
| `mac_address` | String(17) | NOT NULL, INDEX | MAC 地址（XX-XX-XX-XX-XX-XX） |
| `mac_address_normalized` | String(12) | INDEX | MAC 地址规范化（XXXXXXXXXXXX） |
| `status` | String(20) | DEFAULT "unblocked", INDEX | 状态：blocked/unblocked |
| `comments` | Text | NULL | 备注 |
| `timestamp` | DateTime(TZ) | DEFAULT now(), INDEX | 最后发现时间 |
| `source` | String(50) | DEFAULT "arp" | 来源：arp/ipguard/whitelist/manual |
| `source_tag` | String(50) | INDEX | 数据源 tag |
| `compliance_status` | String(20) | DEFAULT "unknown", INDEX | 合规状态：compliant/bypass/non_compliant/unknown |
| `wl_match_type` | String(10) | NULL | 白名单匹配类型：mac/ip/both |

**唯一约束**：`(ip_address, mac_address)`

**复合索引**：
- `(mac_address, timestamp)` — 按MAC查询时间线
- `(ip_address, status)` — 按IP查询状态

### 12.5 Redis 缓存键

| Key | TTL | 说明 |
|-----|-----|------|
| `whitelist:all` | 300s (5min) | 全量白名单数据缓存 |
| `ipguard:{tag}` | 600s (10min) | IP-Guard 基线数据缓存 |
| `scheduler:ctrl:{task}` | — | 调度任务暂停控制 |
| `scheduler:lock:{task}` | interval*2 | 调度任务分布式锁 |

---

## 13. API 接口

### 13.1 数据源管理

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/data-sources/` | `datasource:read` | 列出数据源（支持 type/enabled 过滤） |
| POST | `/data-sources/` | `datasource:write` | 创建数据源 |
| GET | `/data-sources/{source_id}` | `datasource:read` | 获取数据源详情 |
| PUT | `/data-sources/{source_id}` | `datasource:write` | 更新数据源 |
| DELETE | `/data-sources/{source_id}` | `datasource:delete` | 删除数据源（同时删除关联绑定） |
| POST | `/data-sources/{source_id}/test` | `datasource:test` | 测试连接 |
| POST | `/data-sources/{source_id}/sync` | `datasource:sync` | 手动触发同步 |

### 13.2 数据源绑定

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/data-sources/bindings/` | `datasource:read` | 列出绑定关系 |
| POST | `/data-sources/bindings/` | `datasource:write` | 创建绑定 |
| DELETE | `/data-sources/bindings/{binding_id}` | `datasource:delete` | 删除绑定 |

### 13.3 合规操作

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| POST | `/data-sources/compliance/check` | `datasource:compliance` | 合规检查 |
| POST | `/data-sources/compliance/auto-block` | `datasource:compliance` | 自动封堵 |
| POST | `/data-sources/compliance/auto-unblock` | `datasource:compliance` | 自动解封 |

### 13.4 合规基线

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/compliance-baselines/` | `baseline:read` | 列出合规基线 |
| POST | `/compliance-baselines/` | `baseline:write` | 创建合规基线 |
| GET | `/compliance-baselines/{baseline_id}` | `baseline:read` | 获取基线详情 |
| PUT | `/compliance-baselines/{baseline_id}` | `baseline:write` | 更新基线 |
| DELETE | `/compliance-baselines/{baseline_id}` | `baseline:delete` | 删除基线 |
| POST | `/compliance-baselines/{baseline_id}/test` | `baseline:test` | 测试连接 |
| POST | `/compliance-baselines/{baseline_id}/sync` | `baseline:sync` | 手动触发同步 |

---

## 14. 错误处理与容错

### 14.1 同步错误处理

| 场景 | 处理方式 |
|------|---------|
| SSH 连接失败 | 捕获异常，更新 `last_sync_status="failed"` + `last_sync_error`，返回 SyncResult(success=False) |
| HTTP 请求失败 | 同上 |
| IP-Guard 数据库连接失败 | 同上 |
| ARP 输出解析无结果 | 更新 `last_sync_status="success"`（采集成功但无数据），返回 SyncResult(success=True, entries_processed=0) |
| 单条条目处理失败 | 记录到 errors 列表，不影响其他条目 |

### 14.2 封堵错误处理

| 场景 | 处理方式 |
|------|---------|
| 无防火墙绑定 | 返回 AutoBlockResult，所有终端标记为 skipped |
| 单个防火墙封堵失败 | 该终端标记为 skipped，不创建 Blacklist 记录 |
| 部分防火墙封堵失败 | 整个终端标记为 skipped（要求所有防火墙都成功） |
| 自动封堵任务异常 | 独立会话 rollback()，不影响主流程 |

### 14.3 缓存容错

| 场景 | 处理方式 |
|------|---------|
| Redis 不可用 | 跳过缓存，直接从数据库加载 |
| 缓存反序列化失败 | 跳过缓存，从数据库重新加载 |
| IP-Guard 缓存未命中 | 自动触发 sync_ipguard_data() 同步后读取 |

### 14.4 当前限制

| 限制 | 说明 |
|------|------|
| 无自动重试 | 同步/封堵失败后不会自动重试，需等待下次定时调度或手动触发 |
| 无排队机制 | 分布式锁获取失败时直接跳过，不排队等待 |
| 合规检查明细限制 | 超过 1000 条时不返回 details |
| 封堵明细限制 | 超过 100 条时不返回 details |

---

## 15. 核心业务流程总览

### 15.1 完整生命周期

```
阶段 1: 系统配置
━━━━━━━━━━━━━━━━
  ① 创建 ARP 数据源 (arp_ssh / arp_api)
  ② 创建防火墙数据源 (sangfor)
  ③ 创建 ARP ↔ 防火墙绑定
  ④ 创建 IP-Guard 合规基线
  ⑤ 配置白名单规则

阶段 2: 数据采集
━━━━━━━━━━━━━━━━
  ⑥ ARP 数据源采集终端 IP+MAC
     ├── SSH 连接交换机执行命令
     └── HTTP API 获取 ARP 数据
  ⑦ IP-Guard 基线同步合法终端数据
     └── 连接 IP-Guard DB 查询 terminal_info

阶段 3: 合规判定
━━━━━━━━━━━━━━━━
  ⑧ 对采集到的终端执行合规检查
     ├── 白名单匹配 → bypass (免检)
     ├── IP-Guard 匹配 → compliant (合规)
     └── 都不匹配 → non_compliant (不合规)

阶段 4: 自动处置
━━━━━━━━━━━━━━━━
  ⑨ 自动封堵不合规终端
     ├── 通过绑定关系查找防火墙
     ├── 调用 Sangfor API 封堵 IP
     ├── 创建 Blacklist 记录
     └── 更新 Terminal.status = "blocked"

阶段 5: 持续监控
━━━━━━━━━━━━━━━━
  ⑩ 定时重新采集和同步
  ⑪ 定时合规复查
  ⑫ 自动解封已恢复合规的终端
     ├── 调用 Sangfor API 解封 IP
     ├── 标记 Blacklist.auto_unblocked = True
     └── 更新 Terminal.status = "unblocked"
```

### 15.2 数据流转图

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   交换机     │     │  IP-Guard   │     │   白名单     │
│  (ARP 表)   │     │   (DB)      │     │  (规则)      │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       │ SSH/API           │ asyncpg           │ DB
       v                   v                   v
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  ARP 采集    │     │ 基线同步     │     │ 白名单加载   │
│  Service    │     │  Service    │     │  (缓存)      │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       │ Upsert            │ Redis Cache       │ Redis Cache
       v                   v                   v
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Terminal 表  │     │   Redis     │     │   Redis     │
│ (IP+MAC+    │     │ ipguard:tag │     │whitelist:all│
│  status)    │     │ (TTL 600s)  │     │ (TTL 300s)  │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       └───────────────────┼───────────────────┘
                           │
                    ┌──────▼──────┐
                    │  合规判定    │
                    │  Service    │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              v            v            v
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │  bypass  │ │compliant │ │non_comp. │
        │ (免检)   │ │ (合规)   │ │(不合规)  │
        └──────────┘ └──────────┘ └────┬─────┘
                                       │
                                ┌──────▼──────┐
                                │  自动封堵    │
                                │  Service    │
                                └──────┬──────┘
                                       │
                            ┌──────────▼──────────┐
                            │   Sangfor AF 防火墙   │
                            │   block_ip / unblock  │
                            └──────────┬──────────┘
                                       │
                                ┌──────▼──────┐
                                │ Blacklist 表 │
                                │ (封堵记录)   │
                                └──────┬──────┘
                                       │
                                ┌──────▼──────┐
                                │  自动解封    │
                                │ (合规恢复)   │
                                └─────────────┘
```

### 15.3 关键文件索引

| 层次 | 文件路径 | 职责 |
|------|----------|------|
| 前端页面 | `frontend/src/pages/DataSources.tsx` | 数据源管理主页面（三Tab） |
| 前端组件 | `frontend/src/components/datasources/DataSourcesTab.tsx` | 数据源 CRUD + 测试 + 同步（Sangfor 类型隐藏同步按钮） |
| 前端组件 | `frontend/src/components/datasources/BindingsTab.tsx` | ARP-防火墙绑定管理 |
| 前端组件 | `frontend/src/components/datasources/ComplianceBaselinesTab.tsx` | 合规基线 CRUD + 测试 + 同步 |
| 前端共享 | `frontend/src/components/datasources/shared.ts` | 配置字段定义、类型徽章、工具函数 |
| 后端模型 | `backend/app/models/data_source.py` | DataSource + DataSourceBinding |
| 后端模型 | `backend/app/models/compliance_baseline.py` | ComplianceBaseline |
| 后端模型 | `backend/app/models/terminal.py` | Terminal（含 compliance_status） |
| 后端 Schema | `backend/app/schemas/data_source.py` | Pydantic schemas（含 SyncResult, ComplianceCheckResult 等） |
| 后端端点 | `backend/app/api/v1/endpoints/data_sources.py` | 数据源 + 绑定 + 合规操作 API |
| 后端端点 | `backend/app/api/v1/endpoints/compliance_baselines.py` | 合规基线 API |
| 后端服务 | `backend/app/services/data_source_service.py` | 数据源 CRUD + 连接测试 + 配置加解密 |
| 后端服务 | `backend/app/services/arp_collector_service.py` | ARP 采集 + 解析 + 条目处理 + 自动封堵触发 |
| 后端服务 | `backend/app/services/compliance_service.py` | 合规检查 + 自动封堵/解封 + 缓存管理 |
| 后端服务 | `backend/app/services/sangfor_service.py` | Sangfor AF API 交互（封堵/解封/认证） |
| 后端加密 | `backend/app/core/crypto.py` | Fernet 字段级加密/解密 |
| 后端调度 | `backend/app/main.py` | 5 个后台定时任务 + 分布式锁 + 暂停控制 |

---

## 16. 数据源安全性评估

本章对各数据源的操作类型、对外部系统的影响、现有安全防护措施及缺失防护进行全面评估。

### 16.1 安全性总览

| 数据源 | 调用方向 | 操作类型 | 对外部系统影响 | 危险等级 | 关键防护 | 关键缺失 |
|--------|---------|---------|---------------|---------|---------|---------|
| SSH 交换机 | 出站 | 只读 | 无 | 低 | 密码脱敏、超时、权限 | 命令白名单校验 |
| API 数据源 | 出站 | 配置决定（默认只读） | 取决于目标 API | 低-中 | 超时、权限 | method 白名单、POST body 校验 |
| IPGuard | 出站 | 只读 | 无 | 低 | 凭据加密、SQL 硬编码、权限 | 连接池、查询超时 |
| 防火墙（Sangfor） | 出站 | **写操作** | **修改防火墙 ACL 规则** | **高** | dry_run、权限、审计 | 封堵上限/速率限制、二次确认、回滚机制、关键 IP 保护白名单 |
| 数据源配置 CRUD | 内部 | 读写 | 间接影响外部交互 | 中 | RBAC、审计 | 删除前依赖检查、变更审批 |
| 合规基准 CRUD | 内部 | 读写 | 间接影响合规判定 | 低-中 | RBAC、唯一性校验、审计 | 删除前影响评估、级联合规重算 |

### 16.2 SSH 交换机安全性

#### 16.2.1 调用流程

```
netmiko.ConnectHandler(host, port, username, password, device_type)
    → conn.send_command(command, read_timeout=60)
    → conn.disconnect()
    → 解析输出 → upsert Terminal → 合规检查
```

#### 16.2.2 操作类型

**只读**。`send_command` 是 netmiko 的只读命令方法，仅发送命令并读取输出，不会进入配置模式。执行的命令（`display arp` / `show arp`）均为查询命令。

#### 16.2.3 风险点

| 风险 | 说明 | 严重程度 |
|------|------|---------|
| 命令注入 | `config.command` 由管理员配置，理论上可执行任意命令（含写操作如 `system-view`、`acl` 等） | 中 |
| 凭据泄露 | 运行时需解密为明文，日志中已做脱敏处理 | 低 |
| 连接占用 | 长时间采集可能占用交换机 SSH 会话资源 | 低 |

#### 16.2.4 现有防护

- 密码日志脱敏：`password[:2] + "***" + password[-2:]`
- 连接超时：`timeout=30`, `conn_timeout=30`
- 读取超时：`read_timeout=60`
- 权限控制：API 端点需 `datasource:sync` 权限
- 多设备类型回退：尝试失败自动切换下一个 device_type

#### 16.2.5 缺失防护

| 缺失项 | 建议措施 | 优先级 |
|--------|---------|--------|
| 命令白名单 | 限制 `config.command` 只允许 `display arp`、`show arp` 等只读命令，拒绝包含 `system-view`、`configure`、`acl`、`interface` 等配置模式关键字 | 高 |
| SSH 会话数限制 | 限制同一交换机的并发 SSH 连接数 | 低 |

### 16.3 API 数据源安全性

#### 16.3.1 调用流程

```
httpx.AsyncClient
    → 构建 headers（bearer / header 认证）
    → client.get(url) 或 client.post(url)
    → 解析 JSON 响应 → upsert Terminal → 合规检查
```

#### 16.3.2 操作类型

**配置决定，默认只读**。`method` 默认为 `GET`，但支持 `POST`。POST 请求不携带 body 参数。

#### 16.3.3 风险点

| 风险 | 说明 | 严重程度 |
|------|------|---------|
| 非预期写操作 | 某些 API 仅凭 POST 调用即触发操作（如重启设备、下发配置） | 中 |
| URL 注入 | `config.url` 由管理员配置，可指向内网任意服务 | 中 |
| Header 注入 | `config.header_name` 和 `config.token` 可构造任意 HTTP Header | 低 |

#### 16.3.4 现有防护

- 请求超时：30 秒
- HTTP 状态码检查：`response.raise_for_status()`
- 权限控制：API 端点需 `datasource:sync` 权限
- 认证信息加密存储

#### 16.3.5 缺失防护

| 缺失项 | 建议措施 | 优先级 |
|--------|---------|--------|
| method 白名单 | 限制 `config.method` 只允许 `GET`，如需 `POST` 需额外确认 | 高 |
| URL 域名校验 | 限制 `config.url` 只允许配置预设域名或 IP 段，防止 SSRF | 中 |
| POST body 审计 | 如支持 POST，记录请求 body 到审计日志 | 低 |

### 16.4 IPGuard 合规基准安全性

#### 16.4.1 调用流程

```
asyncpg.connect(host, port, username, password, database)
    → SELECT ip_address, mac_address FROM terminal_info WHERE ...
    → conn.close()
    → 缓存 Redis (TTL 600s)
    → 更新 ComplianceBaseline 同步状态
```

#### 16.4.2 操作类型

**只读**。仅执行硬编码的 `SELECT` 查询，不涉及任何 `INSERT`/`UPDATE`/`DELETE`。

#### 16.4.3 风险点

| 风险 | 说明 | 严重程度 |
|------|------|---------|
| 数据库连接泄露 | 每次同步创建新连接而非使用连接池 | 低 |
| 查询无超时 | asyncpg 查询未设置 `statement_timeout`，可能长时间挂起 | 低 |
| 凭据泄露 | 运行时需解密为明文 | 低 |

#### 16.4.4 现有防护

- SQL 语句硬编码：不存在 SQL 注入风险
- 凭据加密存储：Fernet 字段级加密
- 连接超时：30 秒
- 异常处理完善：失败时更新同步状态并记录错误
- 权限控制：API 端点需 `baseline:sync` 权限
- 测试连接仅执行 `SELECT 1`：不暴露表结构

#### 16.4.5 缺失防护

| 缺失项 | 建议措施 | 优先级 |
|--------|---------|--------|
| 连接池 | 使用 `asyncpg.create_pool` 替代每次新建连接 | 中 |
| 查询超时 | 设置 `statement_timeout` 防止长时间挂起 | 中 |
| 只读用户校验 | 测试连接时验证数据库用户是否为只读角色 | 低 |

### 16.5 防火墙（Sangfor）安全性

> **这是系统中唯一对外部系统执行写操作的数据源，危险性最高。**
>
> **同步说明**：Sangfor 为推送型防火墙，仅执行封堵/解封命令，不涉及数据采集。因此"同步"操作对 Sangfor 无意义——前端已隐藏 Sangfor 类型的同步按钮，后端 `POST /data-sources/{id}/sync` 对 sangfor 类型返回"Sync is not applicable"提示。Sangfor 的可用性通过"测试连接"按钮验证。

#### 16.5.1 封堵调用流程

```
查找防火墙数据源 → decrypt_config(config)
    → SangforService(base_url, username, password)
    → svc._authenticate()  [POST /api/v1/namespaces/public/login]
    → svc.block_ip(ip_list, source_tag, reason)
       ├── 幂等检查: GET /api/v1/namespaces/public/whiteblacklist?type=BLACK&url={ip}
       │   已存在 TAM 管理条目 → 跳过
       └── 添加黑名单: POST /api/v1/namespaces/public/whiteblacklist
           payload: {"url": ip, "type": "BLACK", "description": "TAM-{tag}-{reason}", "enable": true}
    → svc.close()
    → 更新 Terminal.status = "blocked"
    → 创建 Blacklist 记录
```

#### 16.5.2 解封调用流程

```
查找防火墙数据源 → decrypt_config(config)
    → SangforService(base_url, username, password)
    → svc._authenticate()
    → svc.unblock_ip(ip_list)
       ├── 安全检查: GET /api/v1/namespaces/public/whiteblacklist?type=BLACK&url={ip}
       │   非 TAM 管理条目 → 跳过（防止误删 AF 安全策略条目）
       └── 删除黑名单: DELETE /api/v1/namespaces/public/whiteblacklist/{ip}
    → svc.close()
    → 更新 Terminal.status = "unblocked"
    → 标记 Blacklist.auto_unblocked = True
```

#### 16.5.3 操作类型

**写操作**。直接修改防火墙的访问控制策略：
- **封堵**：在防火墙上创建 IP 封堵规则
- **解封**：从防火墙删除 IP 封堵规则

#### 16.5.4 风险点

| 风险 | 说明 | 严重程度 |
|------|------|---------|
| 误封合法用户 | 错误封堵导致合法用户无法访问网络 | **高** |
| 误封关键基础设施 | 封堵网关、DNS、DHCP 等关键 IP 导致大面积断网 | **高** |
| 批量封堵失控 | `block_ip` 接受 IP 列表，一次可封堵大量 IP | **高** |
| 自动封堵无回滚 | `asyncio.create_task` 触发后难以撤回 | **高** |
| 错误解封 | 不合规设备恢复网络访问 | 中 |
| 封堵规则残留 | 删除数据源或绑定后，已下发的防火墙规则不会自动清理 | 中 |

#### 16.5.5 现有防护

| 防护措施 | 说明 |
|---------|------|
| dry_run 模式 | `auto_block_non_compliant(dry_run=True)` 仅记录不执行 |
| 权限控制 | 需 `datasource:compliance` 权限 |
| 防火墙启用检查 | 封堵前检查 `fw_source.enabled` |
| 封堵结果验证 | 检查 `response.get("code") == 0` |
| 审计日志 | 所有封堵/解封操作记录到 audit_log |
| 绑定关系 | ARP 源必须绑定到防火墙才会触发自动封堵 |

#### 16.5.6 缺失防护

| 缺失项 | 建议措施 | 优先级 |
|--------|---------|--------|
| 关键 IP 保护白名单 | 维护不可封堵的 IP 列表（网关、DNS、DHCP、核心服务器），封堵前检查 | **高** |
| 单次封堵数量上限 | 限制 `block_ip` 单次最多封堵 N 个 IP（建议 50） | **高** |
| 封堵速率限制 | 限制单位时间内的封堵操作频率（如 10 次/分钟） | **高** |
| 封堵前二次确认 | 自动封堵前记录 dry_run 日志，首次封堵需人工确认 | 中 |
| 自动回滚机制 | 封堵后 N 分钟内如检测到异常（如大量封堵），自动解封 | 中 |
| 数据源删除清理 | 删除防火墙数据源前检查并清理已下发的封堵规则 | 中 |
| 封堵有效期策略 | 支持配置封堵时长（当前硬编码 `30d`），过期自动解封 | 低 |

### 16.6 数据源配置 CRUD 安全性

#### 16.6.1 操作类型

| 操作 | 端点 | 对外部系统影响 | 权限 |
|------|------|---------------|------|
| 创建数据源 | `POST /data-sources/` | 无直接影响 | `datasource:write` |
| 更新数据源 | `PUT /data-sources/{id}` | 修改 SSH 命令/API URL 可改变外部交互行为 | `datasource:write` |
| 删除数据源 | `DELETE /data-sources/{id}` | 已下发的防火墙规则不会自动清理 | `datasource:write` |
| 创建绑定 | `POST /data-sources/bindings/` | 直接影响自动封堵的目标防火墙 | `datasource:write` |
| 删除绑定 | `DELETE /data-sources/bindings/{id}` | 解除 ARP-防火墙关联，影响自动封堵流程 | `datasource:write` |

#### 16.6.2 风险点

| 风险 | 说明 | 严重程度 |
|------|------|---------|
| 删除数据源遗留封堵规则 | 删除防火墙数据源后，已封堵的 IP 规则残留在防火墙上 | **高** |
| 删除绑定中断封堵流程 | 删除绑定后，不合规终端无法自动封堵 | 中 |
| 修改 SSH 命令 | 将只读命令改为写操作命令 | 中 |
| 修改 API URL | 将 URL 指向其他服务 | 中 |

#### 16.6.3 现有防护

- RBAC 权限控制（`require_permission`）
- 所有写操作有审计日志
- 配置字段加密存储

#### 16.6.4 缺失防护

| 缺失项 | 建议措施 | 优先级 |
|--------|---------|--------|
| 删除前依赖检查 | 删除数据源前检查是否有活跃绑定、是否有未解封的封堵规则 | **高** |
| 删除前清理提示 | 删除防火墙数据源时提示用户手动清理已下发的封堵规则 | **高** |
| 关键配置变更审批 | 修改 SSH 命令、API URL 等关键字段时需二次确认 | 中 |
| 绑定删除影响提示 | 删除绑定时显示受影响的终端数量 | 中 |

### 16.7 合规基准 CRUD 安全性

#### 16.7.1 操作类型

| 操作 | 端点 | 对外部系统影响 | 权限 |
|------|------|---------------|------|
| 创建基准 | `POST /compliance-baselines/` | 无直接影响 | `baseline:write` |
| 更新基准 | `PUT /compliance-baselines/{id}` | 修改数据库连接参数可能导致同步失败或获取错误数据 | `baseline:write` |
| 删除基准 | `DELETE /compliance-baselines/{id}` | 依赖该基准的合规判断失效，可能导致大量终端变为 non_compliant | `baseline:write` |
| 手动同步 | `POST /compliance-baselines/{id}/sync` | 对 IPGuard 数据库只读 | `baseline:sync` |

#### 16.7.2 风险点

| 风险 | 说明 | 严重程度 |
|------|------|---------|
| 删除基准触发级联封堵 | 依赖该基准的终端变为 non_compliant，如启用自动封堵则触发防火墙操作 | **高** |
| 禁用基准效果等同删除 | 禁用基准后合规判断失效，效果与删除相同 | 中 |
| 修改数据库连接参数 | 连接到错误的 IPGuard 实例，获取不准确的基线数据 | 中 |

#### 16.7.3 现有防护

- RBAC 权限控制
- name/tag 唯一性校验
- 审计日志
- 连接测试端点

#### 16.7.4 缺失防护

| 缺失项 | 建议措施 | 优先级 |
|--------|---------|--------|
| 删除前影响评估 | 显示依赖该基准的终端数量，警告可能的级联封堵 | **高** |
| 删除/禁用后合规重算 | 自动触发 `recalculate_all_compliance()`，确保终端状态与最新基准配置一致 | **高** |
| 关键配置变更确认 | 修改数据库连接参数时需二次确认 | 中 |

### 16.8 安全防护优先级矩阵

按风险等级和实施难度排列：

| 优先级 | 防护项 | 影响数据源 | 风险场景 |
|--------|--------|-----------|---------|
| **P0** | 关键 IP 保护白名单 | 防火墙 | 防止误封网关/DNS/核心服务器 |
| **P0** | 删除数据源前依赖检查 | 数据源 CRUD | 防止遗留防火墙规则 |
| **P0** | 删除基准前影响评估 | 合规基准 CRUD | 防止级联封堵 |
| **P1** | 单次封堵数量上限 | 防火墙 | 防止批量封堵失控 |
| **P1** | 封堵速率限制 | 防火墙 | 防止封堵风暴 |
| **P1** | SSH 命令白名单 | SSH 交换机 | 防止执行写操作命令 |
| **P1** | 删除/禁用基准后合规重算 | 合规基准 CRUD | 确保终端状态一致 |
| **P2** | API method 白名单 | API 数据源 | 限制只读请求 |
| **P2** | 封堵前二次确认 | 防火墙 | 首次封堵人工确认 |
| **P2** | 删除防火墙数据源清理提示 | 数据源 CRUD | 提醒用户手动清理 |
| **P2** | 关键配置变更审批 | 数据源/基准 CRUD | 防止误修改 |
| **P3** | 自动回滚机制 | 防火墙 | 异常检测后自动解封 |
| **P3** | IPGuard 连接池 | IPGuard | 优化连接管理 |
| **P3** | 查询超时设置 | IPGuard | 防止长时间挂起 |
| **P3** | 封堵有效期策略 | 防火墙 | 支持配置封堵时长 |
