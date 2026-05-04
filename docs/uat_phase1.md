# Phase 1 人工验收清单

本清单用于“瘦身重构 + 企业微信 SSO 收口”合并前人工验收。

固定口径：

- 一级能力只保留：自动化运营、问卷、配置、API 文档
- 主认证：企业微信 SSO
- 主授权：CRM 本地 RBAC
- break-glass：仅兜底，不是主入口

## 1. 登录与认证

| 验收项 | 操作步骤 | 预期结果 |
| --- | --- | --- |
| 登录页主入口 | 未登录访问 `/login` | 页面标题为“后台登录”，主文案为“企业微信登录”，展示企业微信扫码登录入口 |
| 未登录拦截 | 未登录访问 `/admin/automation-conversion` | 返回 `302`，跳转到 `/login?next=/admin/automation-conversion` |
| 企业微信扫码登录 | 点击 `/login` 页面“企业微信扫码登录” | 跳转到企业微信扫码登录 URL，URL 带 `appid`、`agentid`、`redirect_uri`、`state` |
| 企业微信回调 | 使用测试账号完成企业微信回调 | 后台 session 写入企微成员身份，进入原 `next` 页面 |
| break-glass 默认状态 | 未配置 `ADMIN_BREAK_GLASS_LOGIN_ENABLED=true` 时访问 `/login` | 不展示本地账号密码表单，页面提示本地兜底账号默认关闭 |
| break-glass 应急登录 | 显式开启 break-glass 后访问 `/login?manual=1` 并提交正确账号密码 | 登录成功，session 的 `login_type` 为 `break_glass`，仅用于应急 |

## 2. 导航与入口

| 验收项 | 操作步骤 | 预期结果 |
| --- | --- | --- |
| `/admin` 默认入口 | 登录后访问 `/admin` | 返回 `302`，跳转到 `/admin/automation-conversion` |
| 左侧一级导航 | 分别访问 `/admin/automation-conversion`、`/admin/customers`、`/admin/questionnaires`、`/admin/config`、`/admin/api-docs` | 左侧显示“自动化运营、客户、问卷、配置、API 文档” |
| 旧一级入口隐藏 | 检查左侧导航 | 不出现“工作台、运营、AI 推进、团队编排、AI 工具、同步任务、操作记录、系统” |
| 旧 MCP 页面入口 | 访问 `/admin/mcp` | 返回 `302`，跳转到 `/admin/api-docs` |

## 3. 自动化运营

| 验收项 | 操作步骤 | 预期结果 |
| --- | --- | --- |
| 自动化运营入口 | 登录后访问 `/admin/automation-conversion` | 页面正常渲染，标题为自动化运营相关文案 |
| 自动化运营导航状态 | 在自动化运营页面查看左侧导航 | “自动化运营”为当前激活入口，其余入口包含客户、问卷、配置、API 文档 |
| 自动化角色访问 | 使用 `automation_admin` 登录访问 `/admin/automation-conversion` | 返回 `200` |
| 非授权角色访问 | 使用 `questionnaire_admin` 或 `config_admin` 登录访问 `/admin/automation-conversion` | 返回 `403` |

## 4. 客户

| 验收项 | 操作步骤 | 预期结果 |
| --- | --- | --- |
| 客户入口 | 登录后访问 `/admin/customers` | 页面正常渲染，可按关键词、负责人、手机号、标签查询 |
| 客户详情 | 从客户列表点击“查看档案” | 能进入客户档案页，查看基础资料、实时标签、问卷记录和聊天记录 |
| 客户分页 | 在客户列表点击下一页 | 只加载当前页结果，不因客户总量大而长时间阻塞 |

## 5. 问卷

| 验收项 | 操作步骤 | 预期结果 |
| --- | --- | --- |
| 问卷入口 | 登录后访问 `/admin/questionnaires` | 页面正常渲染 |
| 问卷导航状态 | 在问卷页面查看左侧导航 | “问卷”为当前激活入口，其余入口包含自动化运营、客户、配置、API 文档 |
| 问卷角色访问 | 使用 `questionnaire_admin` 登录访问 `/admin/questionnaires` | 返回 `200` |
| 非授权角色访问 | 使用 `automation_admin` 或 `config_admin` 登录访问 `/admin/questionnaires` | 返回 `403` |

## 6. 配置

| 验收项 | 操作步骤 | 预期结果 |
| --- | --- | --- |
| 配置入口 | 登录后访问 `/admin/config` | 页面正常渲染 |
| 配置 tabs | 查看 `/admin/config` 的配置导航 | 只包含“概览、渠道 / 分配规则、报名标签规则、班期标签规则、系统设置、登录与权限” |
| 移除 MCP 工具配置 | 检查 `/admin/config` 页面源码或文本 | 不出现 `mcp_tools`、`/admin/config/mcp-tools`、“AI 工具设置” |
| MCP 工具配置兼容入口 | 访问 `/admin/config/mcp-tools` | 返回 `302`，跳转到 `/admin/api-docs` |
| 登录与权限页 | 访问 `/admin/config/login-access` | 页面管理企微成员授权、角色分配、启停状态和登录审计 |
| 配置角色访问 | 使用 `config_admin` 登录访问 `/admin/config` | 返回 `200` |
| viewer 写操作 | 使用 `viewer` 提交配置写操作 | 返回 `403` |

## 7. API 文档

| 验收项 | 操作步骤 | 预期结果 |
| --- | --- | --- |
| API 文档入口 | 登录后访问 `/admin/api-docs` | 页面正常渲染，标题为“API 文档” |
| 文档内容 | 查看 `/admin/api-docs` | 包含认证方式、自动化运营核心接口、问卷核心接口、配置接口、Webhook / Callback、错误码、请求示例 |
| 非控制台验证 | 检查 `/admin/api-docs` | 不出现旧 MCP 控制台的 preflight、sample-call、tool registry 交互入口 |
| 所有角色访问 | 使用各后台角色访问 `/admin/api-docs` | 均返回 `200` |

## 8. 旧页面下线观察

| 验收项 | 操作步骤 | 预期结果 |
| --- | --- | --- |
| 运营页下线 | 访问 `/admin/user-ops` | 返回 `410`，页面展示“模块已下线” |
| Customer Pulse 下线 | 访问 `/admin/customer-pulse` | 返回 `410`，页面展示“模块已下线” |
| Followup Orchestrator 下线 | 访问 `/admin/followup-orchestrator` | 返回 `410`，页面展示“模块已下线” |
| 同步任务下线 | 访问 `/admin/jobs` | 返回 `410`，页面展示“模块已下线” |
| 系统页下线 | 访问 `/admin/system` | 返回 `410`，页面展示“模块已下线” |
| 操作记录下线 | 访问 `/admin/audit` | 返回 `410`，页面展示“模块已下线” |
| 观察日志 | 访问任一旧页面后查询 `admin_operation_logs` | 有 `target_type='sunset_route'`、`action_type='sunset_route_access'` 的访问记录 |

## 9. 回滚点

| 验收项 | 操作步骤 | 预期结果 |
| --- | --- | --- |
| SSO 配置异常兜底 | 临时开启 break-glass 并访问 `/login?manual=1` | 可显示应急入口，用于进入配置中心修复企微成员授权 |
| 关闭兜底 | 修复企微 SSO 后关闭 `ADMIN_BREAK_GLASS_LOGIN_ENABLED` | `/login` 不再展示本地账号密码表单 |
| 路由回滚 | 如需回滚本次 PR | 后台入口、旧页面展示和认证链路恢复到回滚版本行为 |
| 数据回滚 | 如需回滚 DB 迁移 | 不直接 drop 新表，先确认 `admin_users`、`admin_user_roles`、`admin_login_audit`、`admin_sso_states` 是否已有生产数据 |
