# Admin API

所有 `/api/admin/ai-audience/*` 接口必须 admin session 鉴权。响应不返回 SQL、secret、payload 明细或成员隐私字段。

## Package

- `GET /api/admin/ai-audience/packages`
- `POST /api/admin/ai-audience/packages`
- `GET /api/admin/ai-audience/packages/{package_id}`
- `PATCH /api/admin/ai-audience/packages/{package_id}`
- `POST /api/admin/ai-audience/packages/{package_id}/copy`
- `POST /api/admin/ai-audience/packages/{package_id}/pause`
- `POST /api/admin/ai-audience/packages/{package_id}/activate`
- `DELETE /api/admin/ai-audience/packages/{package_id}`

`POST create` 默认创建 draft/paused，不自动 active。`DELETE` 只 archive。

## Version

- `POST /api/admin/ai-audience/packages/{package_id}/versions`
- `POST /api/admin/ai-audience/packages/{package_id}/preview`
- `POST /api/admin/ai-audience/packages/{package_id}/publish`

`publish` 可传 `version_id`；不传时发布 latest version。校验失败不能继续沿用旧 current version。

## Members

`GET /api/admin/ai-audience/packages/{package_id}/members`

只返回：

- `nickname`
- `external_userid`
- `entered_at`

## Webhooks

- `GET /api/admin/ai-audience/packages/{package_id}/webhooks`
- `PATCH /api/admin/ai-audience/packages/{package_id}/webhooks`
- `POST /api/admin/ai-audience/packages/{package_id}/webhooks/rotate-inbound-secret`

接收 URL 系统生成，不可编辑。secret 只返回 configured 状态。

## Senders

- `GET /api/admin/ai-audience/packages/{package_id}/senders`
- `PUT /api/admin/ai-audience/packages/{package_id}/senders`

发送人解析按 active whitelist 的 `priority ASC, id ASC` 取第一位；无命中时 `skip_reason=no_allowed_sender`。
