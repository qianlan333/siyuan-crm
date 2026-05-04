# 标题

瘦身后台一级能力并接入企业微信 SSO + 本地 RBAC

## 背景

当前后台入口过多，历史模块和 AI 工具控制台仍作为一级能力展示，影响产品边界和后续维护。本次 PR 做第一阶段瘦身收口：先下线非核心页面、保留底层 API 和数据表观察 7 天，同时把后台登录口径统一为企业微信 SSO + CRM 本地 RBAC，break-glass 仅作为兜底入口。

## 本次改动

### 后台瘦身

- 左侧一级导航只保留：自动化运营、问卷、配置、API 文档。
- `/admin` 不再渲染工作台，统一 `302` 到 `/admin/automation-conversion`。
- 旧页面如客户、运营、Customer Pulse、Followup Orchestrator、同步任务、系统、操作记录等进入 sunset 占位页。
- sunset 访问写入 `admin_operation_logs`，用于 7 天观察后判断是否硬删。

### API 文档替代 MCP 控制台

- 新增 `/admin/api-docs` 后台内置 API 文档页。
- `/admin/mcp`、`/admin/mcp/preflight`、`/admin/mcp/sample-call` 兼容跳转到 `/admin/api-docs`。
- 配置中心移除 `mcp_tools` 页签和“AI 工具设置”入口。
- `/mcp` 协议 endpoint 不硬删，仍保留 Bearer Token 访问兼容。

### 企业微信 SSO + 本地 RBAC

- `/login` 主入口为企业微信登录。
- 新增 `/auth/wecom/start` 和 `/auth/wecom/callback`。
- 企业微信负责身份识别，CRM 本地 `admin_users` / `admin_user_roles` 负责授权。
- 新增“配置 > 登录与权限”页面，管理企微成员授权、角色、启停和登录审计。
- break-glass 默认关闭，仅在企业微信 SSO 故障或首次修复授权时临时启用。

### 旧页面 sunset 与 7 天观察

- `/admin/user-ops*`
- `/admin/customer-pulse*`
- `/admin/followup-orchestrator*`
- `/admin/jobs*`
- `/admin/system*`
- `/admin/audit*`
- `/admin/class-user-management*`
- `/admin/class-user-backoffice*`

`/admin/customers*` 已恢复为全量客户查询入口，不再作为 sunset 页面处理。

## 影响范围

- 页面入口：后台一级导航、登录页、配置中心、API 文档页、旧页面 sunset 页。
- 路由：`/admin`、`/login`、`/logout`、`/auth/wecom/start`、`/auth/wecom/callback`、`/admin/api-docs`、`/admin/mcp`、`/admin/config/login-access`。
- 配置项：新增或使用 `ADMIN_AUTH_MODE`、`ADMIN_LOGIN_REDIRECT_URI`、`ADMIN_WECHAT_TRUSTED_DOMAIN`、`ADMIN_BREAK_GLASS_*`。
- 数据表：新增 `admin_users`、`admin_user_roles`、`admin_login_audit`、`admin_sso_states`。
- 测试：覆盖瘦身导航、旧页面 sunset、MCP 兼容跳转、SSO 登录、RBAC、break-glass、`/mcp` endpoint。
- 文档：新增瘦身说明、删除候选、SSO 登录、RBAC、UAT、发布 checklist。

## 不在本次范围

- 不硬删 `/mcp`。
- 不硬删 customer/timeline/messages 底层读接口。
- 不硬删 `customer_pulse_*`。
- 不硬删 `followup_orchestrator_*`。
- 不硬删 `mcp_tool_settings`。
- 上述模块和表仍在 7 天观察范围内。

## 风险与回滚

可能风险：

- 企业微信 SSO 配置错误会导致后台主登录失败。
- 未预先配置企微授权成员会导致 SSO 成功后无后台权限。
- 老用户访问旧页面会看到 sunset 占位页，不再进入原功能。

回滚方式：

- 应用层可回滚本 PR，恢复旧后台入口和旧登录行为。
- SSO 故障时可临时开启 break-glass，进入“配置 > 登录与权限”修复企微成员授权。
- 本次不 drop 旧表和底层 API，数据层回滚风险较低。
