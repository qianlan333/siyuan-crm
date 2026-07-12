# Issue 67 R01 — Route Policy、RBAC、Session 与 CSRF 实施计划

## 目标与边界

- 交付 Issue #70，父 Epic #67。
- 不新增页面、菜单、业务 API、业务表或产品流程。
- 保持现有安全调用的成功 contract；匿名、弱认证、越权和跨动作重放改为 401/403。
- 复用现有 `admin_users`、角色、sidebar signed context、内部 bearer token 和问卷 `result_token`，只补最小安全字段与约束。

## 设计

### 1. RoutePolicy 真源

在 `route_ownership_manifest.yml` 的每个运行时路由条目上追加：

- `audience`: `admin | sidebar | public_h5 | callback | internal_worker | external_integration`
- `auth_scheme`
- `capability`
- `access_scope`
- `pii_level`
- `csrf`
- `rate_limit`

运行时从已提交的显式 manifest 构建 policy index。业务路由缺 policy 时默认拒绝；静态资源与 FastAPI 内建文档使用单独的最小平台 policy。

### 2. 认证与 capability

- `super_admin`: 全 capability。
- `config_admin`: 后台读取、配置和账号管理。
- `automation_admin`: 后台读取、客户读取、自动化、群运营、触达。
- `questionnaire_admin`: 后台读取、客户读取、问卷管理与导出。
- `viewer`: 只读后台与允许的只读客户能力，所有写操作拒绝。
- service account: 只接受对应用途的 bearer token，不接受万能匿名 fallback。

RoutePolicy middleware 在 endpoint 前执行认证、capability、CSRF 和基础 rate-limit；现有 endpoint 内部业务签名、webhook token 与 owner 校验继续作为纵深防御。

### 3. Session 与 CSRF

- `admin_users.session_version` 作为 server-side revocation/version 真源。
- SSO session 绑定 `admin_user_id`、`session_version` 与角色快照；每次受保护请求校验账号 active/login_enabled、版本和当前角色。
- 停用、角色/等级变化时递增 version，使旧 session 立即失效。
- CSRF 使用 session 内随机 token + Secure/SameSite cookie；非安全方法必须从 `X-CSRF-Token` 或 form 字段提交 token，不能只凭 cookie。

### 4. 重点不安全路径

- `/mcp`: 要求用途明确的内部 bearer token。
- `/api/identity/resolve`: 要求内部 service token；后台继续使用 `/api/admin/identity/resolve`。
- sidebar read/write: 要求签名 owner context；actor/owner 从 token 派生，不能相信 body/query 自报身份；跨 owner 统一 403。
- `/api/automation/group-ops/*` 管理兼容别名：保留兼容 URL，但要求后台 session + `manage_group_ops`，不再公开。
- 问卷结果：URL 只接受已有高熵 `result_token`，不接受顺序 submission id。

### 5. Action token

把现有全局时间片 token 替换为签名声明：`admin_user_id`、session 指纹、capability、method、action、target、iat、exp、nonce。校验时必须传入当前 request/action，上下文不一致即拒绝。迁移现有页面为按动作签发；旧无绑定 token 不再通过生产校验。

## 实施步骤

1. 先写 RoutePolicy schema/manifest gate 与 100% route 对齐失败测试。
2. 增加集中 middleware、角色 capability 矩阵和五类 principal 负向测试。
3. 加 session_version migration、登录绑定、即时吊销与降权测试。
4. 切换 CSRF header/form contract，补后台页面请求 token 传递与回归测试。
5. 封闭 MCP、identity、sidebar、group-ops alias、问卷结果枚举。
6. 收敛 action token 并补跨用户/session/action/target/过期重放测试。
7. 运行 PostgreSQL 聚焦回归、架构全门禁、前端 typecheck/build/tests、全量 pytest。
8. PR 合并后验证 exact SHA 部署、migration head、匿名拒绝和已认证 smoke。

## 回滚

- 代码回滚前先保留新的拒绝策略；只有确认新版本不可用时才回滚应用。
- `0098` downgrade 删除 `session_version` 与问卷 result-token 唯一索引；旧 session 不应重新启用，回滚时强制旋转 `SECRET_KEY` 或结束所有后台 session。
- 问卷 `result_token` 和现有业务数据不删除。
