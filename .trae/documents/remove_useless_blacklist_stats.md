# 移除黑名单管理中无用的统计功能

## 问题分析
用户反馈：黑名单中的 "Database Active Blocks" 和 "Firewall Actual Blocks" 统计是鸡肋，没有实际操作价值，要求移除。

## 问题定位

### 统计展示位置
文件：`/home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Blacklist.tsx`
- 第135-154行：统计展示区域
- 第55行：`useBlacklistStats` hook调用
- 第3-4行：相关import

### 统计内容
- **Database Active Blocks**：数据库中活跃的黑名单数量
- **Firewall Actual Blocks**：防火墙中实际被封锁的IP数量

## 改进方案

### 方案：移除整个统计展示区域

#### 前端修改
1. **移除第135-154行**：整个统计展示的div区域
2. **移除第55行**：`useBlacklistStats` hook调用
3. **移除第4行import**：`useBlacklistStats`和相关constants（如果没用了）

#### 后端说明
- 暂不修改后端API，保留`/api/v1/blacklist/stats`接口，避免影响其他可能的使用

## 修改文件清单

### 前端
- `frontend/src/pages/Blacklist.tsx` - 移除统计展示区域和相关hook

## 实施步骤
1. 移除统计展示区域（第135-154行）
2. 移除`useBlacklistStats` hook调用（第55行）
3. 清理未使用的import（如果需要）
4. 测试功能正常，其他功能不受影响
