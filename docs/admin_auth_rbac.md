# 后台登录与 RBAC

## 认证与授权边界

- 认证：企业微信 SSO
- 授权：CRM 本地 RBAC
- 本地用户名 / 密码不是后台主登录方案
- break-glass 仅是默认关闭的应急兜底入口

也就是：

- 企业微信负责“你是谁”
- CRM 本地负责“你能干什么”

后台会在企微回调成功后拿到 `UserId`，再用 `UserId + CorpId` 匹配本地 `admin_users`，最后通过 `admin_user_roles` 决定可访问模块与写权限。

`admin_users` 的主模型是企微成员授权，不保存日常后台登录密码；本地用户名 / 密码只存在于 break-glass 配置项中。

## 登录入口

- 登录页：`/login`
- 登出：`/logout`
- 企微登录启动：`/auth/wecom/start`
- 企微登录回调：`/auth/wecom/callback`

## 角色说明

- `super_admin`
  - 可访问全部后台模块
  - 可管理授权成员与角色
- `automation_admin`
  - 可访问自动化运营、API 文档
- `questionnaire_admin`
  - 可访问问卷、API 文档
- `config_admin`
  - 可访问配置、API 文档
- `viewer`
  - 可读访问四个主模块
  - 不允许写操作

## 会话机制

- AI-CRM Next 后台页面使用签名 admin session cookie 保存登录态
- session payload 至少包含：
  - `admin_user_id`
  - `wecom_userid`
  - `role list`
  - `login_type`
- 页面内写操作继续使用 `admin_action_token` 做防误操作保护

## 授权管理

入口：`/admin/config/login-access`

支持：

- 查看已授权企微成员
- 创建授权成员
- 编辑角色
- 启停成员
- 查看最近登录时间
- 查看最近登录审计

## break-glass 兜底入口

- 默认关闭
- 仅在企业微信 SSO 故障时启用
- 通过配置项控制：
  - `ADMIN_BREAK_GLASS_LOGIN_ENABLED`
  - `ADMIN_BREAK_GLASS_USERNAME`
  - `ADMIN_BREAK_GLASS_PASSWORD_HASH`

推荐流程：

1. 临时开启 break-glass
2. 使用 break-glass 登录后台
3. 到 `/admin/config/login-access` 绑定或修复企微管理员权限
4. 验证企微 SSO 正常
5. 关闭 break-glass

## 与内部 Token 的边界

- 后台登录仅用于人访问后台页面
- 内部自动化动作仍继续使用 `AUTOMATION_INTERNAL_API_TOKEN` / Bearer Token
- 两套认证不混用，避免后台 session 影响自动化链路
