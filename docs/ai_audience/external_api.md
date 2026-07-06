# External Spec API

External Spec API 给 Codex、脚本和外部 Agent 使用 Bearer token 创建和管理 AI Audience package spec。它不改变 `/api/admin/ai-audience/*` 的后台 cookie 鉴权模型。

## 配置

必填：

- `AICRM_AI_AUDIENCE_SPEC_API_TOKEN`

可选：

- `AICRM_AI_AUDIENCE_SPEC_ALLOW_PUBLISH=false`

Bearer token 认证通过后可创建或更新正式 package key；`package_key_prefix`
只是脚本/测试场景里的可选命名辅助，不再作为权限限制。默认不允许 publish。

## 鉴权

所有请求必须带：

```http
Authorization: Bearer <token>
```

无 token 返回 `401 external_token_required`；错误 token 返回 `401 external_token_invalid`；服务端 token 未配置返回 `503 external_token_not_configured`。

## Dry-run

```bash
curl -sS -X POST https://www.youcangogogo.com/api/external/ai-audience/spec/dry-run \
  -H "Authorization: Bearer $AICRM_AI_AUDIENCE_SPEC_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"spec_markdown":"..."}'
```

Dry-run 只 parse/validate，不创建 package，不 publish，不触发 external effect。

## Apply

```bash
curl -sS -X POST https://www.youcangogogo.com/api/external/ai-audience/spec/apply \
  -H "Authorization: Bearer $AICRM_AI_AUDIENCE_SPEC_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"spec_markdown":"...","publish":false,"operator":"codex"}'
```

Apply 会创建或更新 package，创建新 version，并执行 preview。默认不 publish、不 activate、不触发真实发送。

## Publish

```bash
curl -sS -X POST https://www.youcangogogo.com/api/external/ai-audience/spec/publish \
  -H "Authorization: Bearer $AICRM_AI_AUDIENCE_SPEC_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"package_key":"q101_submitted_added_wecom","version_id":123,"operator":"codex"}'
```

Publish 需要 `AICRM_AI_AUDIENCE_SPEC_ALLOW_PUBLISH=true`。External publish 只发布 version，不 activate package。

## Archive

```bash
curl -sS -X POST https://www.youcangogogo.com/api/external/ai-audience/packages/q101_submitted_added_wecom/archive \
  -H "Authorization: Bearer $AICRM_AI_AUDIENCE_SPEC_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"operator":"codex"}'
```

Archive 只软归档，不物理删除。

## Script

```bash
AICRM_AI_AUDIENCE_SPEC_API_TOKEN='...' \
python scripts/ai_audience_apply_package_spec.py docs/ai_audience/examples/questionnaire_submitted_added_wecom.md \
  --external-api-base https://www.youcangogogo.com \
  --external-token-from-env \
  --apply \
  --confirm-production
```

脚本不会输出 token。

## 安全边界

- 不允许裸访问。
- 不接受浏览器 cookie。
- 不绕过 SQL linter。
- 不返回 secret/token/DSN/cookie。
- 不调用 User Ops batch-send execute。
- 不触发真实私聊发送。
- 所有调用写入 `admin_operation_logs` 审计。
