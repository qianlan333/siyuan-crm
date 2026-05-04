# Phase 1 发布前检查清单

本清单用于“瘦身重构 + 企业微信 SSO 收口”上线前确认。

## 1. 企业微信 SSO 配置检查

- [ ] `WECOM_CORP_ID` 已配置为当前企业微信企业 ID。
- [ ] `WECOM_SECRET` 已配置为后台自建应用 Secret。
- [ ] `WECOM_AGENT_ID` 已配置为后台自建应用 Agent ID。
- [ ] `ADMIN_AUTH_MODE` 已配置为 `wecom_sso`。
- [ ] `WECOM_API_BASE` 在生产环境指向企业微信正式 API，测试环境才使用 mock。

## 2. redirect_uri / 可信域名检查

- [ ] `ADMIN_LOGIN_REDIRECT_URI` 指向生产域名下的 `/auth/wecom/callback`。
- [ ] `ADMIN_WECHAT_TRUSTED_DOMAIN` 与企业微信后台配置的可信域名一致。
- [ ] 企业微信自建应用后台已允许当前后台域名用于 OAuth / 扫码登录回调。
- [ ] 生产后台域名使用 HTTPS，证书有效。

## 3. break-glass 配置检查

- [ ] `ADMIN_BREAK_GLASS_LOGIN_ENABLED` 上线默认值为 `false` 或未配置。
- [ ] `ADMIN_BREAK_GLASS_USERNAME` 仅在应急预案中保存，不作为日常登录账号。
- [ ] `ADMIN_BREAK_GLASS_PASSWORD_HASH` 只保存 werkzeug 哈希，不保存明文。
- [ ] 如需应急演练，短时开启后访问 `/login?manual=1`，确认表单出现、登录可用、修复完成后立即关闭。

## 4. 内部 Bearer Token 检查

- [ ] `MCP_BEARER_TOKEN` 已配置且与调用方一致。
- [ ] 不带 Token 请求 `/mcp` 返回 `401`。
- [ ] 带 `MCP_BEARER_TOKEN` 请求 `/mcp` 的 `initialize` 返回 `200` 和 MCP `serverInfo`。
- [ ] `AUTOMATION_INTERNAL_API_TOKEN` 已配置且未泄露。

## 5. SECRET_KEY / session 检查

- [ ] `SECRET_KEY` 在生产环境为稳定强随机值，不使用测试默认值。
- [ ] 完成企业微信登录后刷新后台页面，登录态保持正常。
- [ ] 部署层 Cookie / HTTPS 设置正确，Cookie 仅通过 HTTPS 传输，生产域名隔离。

## 6. DB migration 检查

- [ ] 执行 DB 初始化 / migration 后，`admin_users` 存在。
- [ ] 执行 DB 初始化 / migration 后，`admin_user_roles` 存在。
- [ ] 执行 DB 初始化 / migration 后，`admin_login_audit` 存在。
- [ ] 执行 DB 初始化 / migration 后，`admin_sso_states` 存在。
- [ ] 在 `/admin/config/login-access` 新增企微成员，可保存 `wecom_userid`、角色、启停状态。
- [ ] 完成一次 SSO 登录后，`admin_login_audit` 写入成功记录。
- [ ] customer / user_ops / customer_pulse / followup_orchestrator / mcp 相关旧表未被 drop，仍保留观察。

## 7. smoke test 检查

- [ ] 访问 `/admin` 返回 `302` 到 `/admin/automation-conversion`。
- [ ] 访问 `/auth/wecom/start?mode=qr` 返回 `302` 到企业微信扫码地址。
- [ ] 登录后访问 `/admin/automation-conversion` 返回 `200`。
- [ ] 登录后访问 `/admin/customers` 返回 `200`，支持关键词、负责人、手机号、标签查询和分页。
- [ ] 登录后访问 `/admin/questionnaires` 返回 `200`。
- [ ] 登录后访问 `/admin/config` 返回 `200`。
- [ ] 登录后访问 `/admin/api-docs` 返回 `200`。
- [ ] 带 `MCP_BEARER_TOKEN` 调 `/mcp initialize` 返回 `200`。

## 8. 旧页面 sunset 日志观察检查

- [ ] 访问 `/admin/user-ops` 返回 `410` 和“模块已下线”。
- [ ] 访问 `/admin/customer-pulse` 返回 `410` 和“模块已下线”。
- [ ] 访问 `/admin/followup-orchestrator` 返回 `410` 和“模块已下线”。
- [ ] 访问 `/admin/jobs` 返回 `410` 和“模块已下线”。
- [ ] 访问 `/admin/system` 返回 `410` 和“模块已下线”。
- [ ] 访问 `/admin/audit` 返回 `410` 和“模块已下线”。
- [ ] 查询 `admin_operation_logs`，确认旧页面访问写入 `sunset_route_access`。
- [ ] 连续 7 天观察旧页面访问、外部调用、定时任务依赖；无访问、无调用、无依赖且主链路回归通过后，进入第二阶段硬删。
