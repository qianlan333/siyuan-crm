# CRM Sensitive Routes

## 目标

这份清单只保留“当前真实存在、且后续建议纳入 internal auth 或同等级保护”的接口。

说明：

- 本轮不启用 internal auth
- 本轮不改变现有路由行为
- 清单以 `create_app().url_map` 与 [routes.py](../wecom_ability_service/routes.py) 为准

## 当前真实存在的敏感接口

### 配置 / 初始化 / 运维

- `GET /api/ops/status`
- `GET /api/settings`
- `PUT /api/settings`
- `POST /api/init-db`
- `GET /api/archive/health`
- `POST /api/archive/sync`

### Contacts / Identity / Group Chats

- `GET /api/contacts`
- `GET /api/contacts/<external_userid>`
- `POST /api/contacts/description`
- `POST /api/contacts/full-sync`
- `POST /api/contacts/sync-new`
- `POST /api/contacts/normalize-description`
- `GET /api/identity/resolve`
- `POST /internal/wecom/external-contact/full-sync`
- `POST /api/group-chats/full-sync`
- `POST /api/group-chats/sync-new`

### Messages / Archive Read

- `GET /archive/messages`
- `GET /api/messages/<external_userid>`
- `GET /api/messages/<external_userid>/recent`
- `GET /api/messages/search`

### Sidebar / Class User

- `GET /api/sidebar/contact-binding-status`
- `GET /api/sidebar/jssdk-config`
- `POST /api/sidebar/bind-mobile`
- `GET /api/sidebar/signup-tags/status`
- `POST /api/sidebar/signup-tags/mark`
- `POST /api/admin/class-user-management/bootstrap`
- `POST /api/admin/class-user-management/migrate`
- `GET /api/admin/class-user-management`
- `GET /api/admin/class-user-management/export`
- `GET /api/admin/class-user-management/history`
- `GET /api/admin/wecom/tags`
- `GET /admin/class-user-management/ui`
- `GET /admin/class-user-backoffice/ui`

### Tags / Tasks

- `GET /api/tags`
- `POST /api/tags`
- `POST /api/tags/mark`
- `POST /api/tags/unmark`
- `POST /api/tasks/private-message`
- `POST /api/tasks/moment`
- `POST /api/tasks/group-message`

### Customer Center / Customer Timeline Aggregation

- `GET /api/customers`
- `GET /api/customers/<external_userid>`
- `GET /api/customers/<external_userid>/timeline`

### Questionnaire Admin / Debug

- `GET /api/admin/questionnaires`
- `POST /api/admin/questionnaires`
- `GET /api/admin/questionnaires/preflight`
- `GET /api/admin/questionnaires/<int:questionnaire_id>`
- `PUT /api/admin/questionnaires/<int:questionnaire_id>`
- `POST /api/admin/questionnaires/<int:questionnaire_id>/disable`
- `DELETE /api/admin/questionnaires/<int:questionnaire_id>`
- `GET /api/admin/questionnaires/<int:questionnaire_id>/latest-submit-debug`
- `GET /api/admin/questionnaires/<int:questionnaire_id>/export`
- `GET /api/debug/questionnaire/session`
- `GET /admin/questionnaires/ui`

### MCP

- `GET /mcp`
- `POST /mcp`

## 当前应保持公开或继续走既有签名机制的接口

这些接口当前真实存在，但不适合简单套 internal auth。

- `GET /health`
- `GET /sidebar/bind-mobile`
- `GET /s/<slug>`
- `GET /s/<slug>/submitted`
- `GET /api/h5/questionnaires/<slug>`
- `POST /api/h5/questionnaires/<slug>/submit`
- `GET /api/h5/wechat/oauth/start`
- `GET /api/h5/wechat/oauth/callback`
- `GET,POST /api/wecom/events`
- `GET,POST /wecom/external-contact/callback`
- `GET /<path:filename>` 用于 `WW_verify_*.txt` / `MP_verify_*.txt`

## 建议保护策略

后续如果上线 internal auth，建议采用最小 bearer 方案：

- `Authorization: Bearer <CRM_INTERNAL_TOKEN>`

可选兼容：

- `X-Internal-Token: <CRM_INTERNAL_TOKEN>`

建议上线顺序：

1. 先保护 admin / settings / init-db / sync / tasks / tags 写接口
2. 再保护 contacts / identity / messages / customer 聚合读接口
3. 保持 callback、问卷公开入口、MCP 的现有安全机制独立演进

## 附录：未来新增后应纳入保护的接口类型

以下不是当前已实现路由，只是后续如果新增，建议自动纳入敏感接口评审：

- 新的 customer_center 聚合写接口
- 新的 customer_timeline 回填或修正接口
- 新的 internal batch / replay / repair 路由
- 新的 questionnaire admin 批量处理接口
