# Phase 1 瘦身重构

## 目标

第一阶段只做“后台壳层收口”，不直接硬删底层 API 和数据表。

当前后台一级能力收敛为 4 个：

- 自动化运营
- 问卷
- 配置
- API 文档

其中“登录与权限”不单独放在左侧一级导航，而是挂到“配置”子页。

## 本次变更

### 后台壳层

- `/admin` 不再渲染工作台，直接 `302` 到 `/admin/automation-conversion`
- 左侧一级导航只保留：
  - `/admin/automation-conversion`
  - `/admin/questionnaires`
  - `/admin/config`
  - `/admin/api-docs`
- `/admin/mcp` 不再展示 AI 工具控制台，统一 `302` 到 `/admin/api-docs`

### 配置中心

- 移除 `mcp_tools` 配置页签
- 新增“登录与权限”子页：`/admin/config/login-access`
- 配置中心首页只保留：
  - 系统设置
  - 登录与权限
  - 配置检查清单

企微标签管理作为客户管理后台一级入口保留，不再归入配置中心页签。

### 登录与权限入口

- “登录与权限”只保留为配置子页入口：`/admin/config/login-access`
- 本文只记录“瘦身后后台信息架构”这一事实，不展开认证 / 授权实现细节
- 认证与授权唯一口径见：
  - `docs/wecom_sso_login.md`
  - `docs/admin_auth_rbac.md`

### 临时下线

以下页面不再作为产品能力展示，访问时会进入“模块已下线”占位页并记录观察日志：

- `/admin/user-ops*`
- `/admin/customer-pulse*`
- `/admin/followup-orchestrator*`
- `/admin/jobs*`
- `/admin/system*`
- `/admin/audit*`
- `/admin/class-user-management*`
- `/admin/class-user-backoffice*`

`/admin/customers*` 已恢复为全量客户查询入口，继续支持分页、关键词、负责人、手机号、标签查询和客户档案。

## 观察期判断标准

7 天后进入第二阶段硬删前，需要同时满足：

- 7 天无人工访问
- 7 天无外部调用
- 7 天无定时任务依赖
- 自动化运营 / 问卷 / 配置主链路回归通过

## 本次明确不删

- 企微底座能力：`contacts`、`identity`、`tags`、`tasks`、`callbacks`、`archive`、`group_chats`
- customer / timeline / recent messages 读接口
- `user_ops_*` 相关表
- `/mcp` 协议实现本身
