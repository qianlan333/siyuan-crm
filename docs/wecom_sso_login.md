# 企业微信 SSO 登录

## 当前模式

当前后台使用的是“企业微信自建应用登录”。

后台最终主认证口径固定为“企业微信 SSO”；本地用户名 / 密码不再作为日常主登录方案。

这次只解决单企业后台的登录问题，不做多企业 SaaS 的第三方应用 / 服务商模式。

## PC 扫码登录

PC 浏览器访问 `/login` 时，默认展示“企业微信扫码登录”入口。

流程：

1. 用户访问 `/login`
2. 点击“企业微信扫码登录”
3. 后端跳到 `/auth/wecom/start?mode=qr`
4. 服务端构造企业微信扫码地址：
   - `appid = WECOM_CORP_ID`
   - `agentid = WECOM_AGENT_ID`
   - `redirect_uri = ADMIN_LOGIN_REDIRECT_URI` 或后台可信域名推导值
   - `state = admin_sso_states.state_token`
5. 企业微信回调 `/auth/wecom/callback`
6. 后端校验 `state`
7. 用 `code` 调企业微信 `auth/getuserinfo`
8. 拿到 `UserId` 后匹配本地 `admin_users`
9. 命中授权成员后写入后台 session

## H5 OAuth 登录

企业微信客户端内打开后台页面时，`/login` 会优先发起 OAuth 登录。

流程：

1. 企业微信内访问 `/login`
2. 后端跳到 `/auth/wecom/start?mode=oauth`
3. 服务端构造 OAuth2 授权地址：
   - `appid = WECOM_CORP_ID`
   - `agentid = WECOM_AGENT_ID`
   - `scope = snsapi_base`
   - `redirect_uri = /auth/wecom/callback`
   - `state = admin_sso_states.state_token`
4. 企业微信回调 `/auth/wecom/callback`
5. 服务端校验 `state`
6. 通过 `code` 换取 `UserId`
7. 匹配本地 RBAC 并建立 session

## 本地 RBAC 绑定

企业微信身份只决定“是谁”，权限由 CRM 本地表维护：

- `admin_users`
- `admin_user_roles`
- `admin_login_audit`
- `admin_sso_states`

后台授权入口：`/admin/config/login-access`

最小绑定字段：

- `wecom_userid`
- `wecom_corpid`
- `display_name`
- `is_active`
- `role_codes`

## break-glass 启用方式

默认关闭。

启用时需要配置：

- `ADMIN_BREAK_GLASS_LOGIN_ENABLED=true`
- `ADMIN_BREAK_GLASS_USERNAME=<username>`
- `ADMIN_BREAK_GLASS_PASSWORD_HASH=<werkzeug generate_password_hash 结果>`

示例：

```python
from werkzeug.security import generate_password_hash
print(generate_password_hash("replace-with-strong-password"))
```

配置后，`/login` 页面会显示应急入口表单，但仍不作为主登录方式。

如果当前环境还没有任何已授权企微管理员，可以临时开启 break-glass 完成首次企微成员绑定；绑定完成后应回到企业微信 SSO 主链路，并关闭该入口。

## 当前不做的事情

- 不把企业微信部门结构直接当权限系统
- 不做多企业 SaaS 场景的第三方应用 / 服务商模式
- 不废弃 `/mcp` 协议 endpoint，只废弃旧后台控制台入口
