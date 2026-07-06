# P1 Group Ops Workspace Draft Persistence RFC - 2026-06-24

RFC verdict:

- `RFC_READY_FOR_REVIEW`
- `IMPLEMENTATION_NOT_STARTED`
- `EXECUTION_NOT_IN_SCOPE`
- `PASS_90_PLUS_NOT_CLAIMED`

This RFC is the design review boundary between the read-only
`/admin/p1/group-ops-workspace` trial and any future draft persistence work. It
does not implement database tables, migrations, APIs, frontend save actions,
Push Center execution, or external-effect execution.

## 1. Executive Summary

The read-only Group Ops workspace is trial-ready, as recorded in
`docs/reports/p1_group_ops_workspace_read_only_closeout_20260624.md`.

This RFC proposes the next design layer: allowing a user to save a draft from
the P1 workspace. A draft is only a persisted planning artifact. It is not a
send, not an approval, not a Push Center execution request, not an
external-effect job, and not `PASS_90_PLUS` evidence.

Draft persistence may store only sanitized orchestration structure and internal
reference ids. It must not store raw receivers, raw `external_userid`, phone
numbers, raw chat/member ids, tokens, secrets, `Authorization` headers, raw
message bodies, raw callback bodies, or target lists that could be used for
direct sending.

## 2. Non-goals

This RFC explicitly does not authorize:

- sending messages
- triggering external effects
- creating Push Center jobs
- bypassing Push Center
- bypassing approval, receiver allowlist, or gray-window gates
- treating draft as sent or completed
- treating request-review as approved
- claiming global `PASS_90_PLUS`
- treating copied summary / exported preview as an execution credential
- changing deploy/systemd/nginx/env
- running a production migration
- restoring legacy runtime or adding compatibility shims

## 3. Data Model Proposal

This is a proposal only. This PR creates no migration.

### `group_ops_workspace_drafts`

Purpose: one saved draft header per workspace plan draft.

Suggested fields:

| Field | Type | Notes |
| --- | --- | --- |
| `draft_id` | string / uuid | Primary id, generated server-side. |
| `tenant_id` | string / nullable | Use current tenant/admin scope if available. |
| `admin_scope` | string / nullable | Scope for admin-console isolation if current model uses admin scope. |
| `created_by` | string | Actor id from authenticated admin context. |
| `updated_by` | string | Last actor id from authenticated admin context. |
| `source_plan_id` | string / nullable | Internal plan id or redacted reference. |
| `draft_status` | enum | `draft`, `ready_for_review`, `archived`, `rejected`. |
| `version` | integer | Optimistic concurrency and history counter. |
| `idempotency_key` | string | Request-level idempotency key. |
| `snapshot_hash` | string | Hash of sanitized structure for dedupe/conflict checks. |
| `sanitized_payload_json` | json | Sanitized orchestration structure and internal references only. |
| `guardrail_summary_json` | json | Derived guardrails at save time. |
| `approval_requirements_json` | json | Required approval / allowlist / gray-window summary. |
| `created_at` | timestamp | Server time. |
| `updated_at` | timestamp | Server time. |
| `archived_at` | timestamp / nullable | Server time when archived. |

### `group_ops_workspace_draft_items`

Purpose: normalized per-item references for search, diff, and future review UI.

Suggested fields:

| Field | Type | Notes |
| --- | --- | --- |
| `item_id` | string / uuid | Primary id. |
| `draft_id` | string / uuid | FK to `group_ops_workspace_drafts`. |
| `version` | integer | Draft version at which item was saved. |
| `entity_type` | enum | `plan`, `group`, `node`, `execution`, `push_center`, `evidence`. |
| `entity_ref_id` | string | Internal redacted/reference id only. |
| `sort_order` | integer | UI ordering within sanitized draft. |
| `lane_id` | string | Optional lane reference from grouped canvas. |
| `status` | string | Evidence/status value at save time. |
| `derived_status` | string | Derived read-only status at save time. |
| `sanitized_item_json` | json | Sanitized item summary only. |
| `created_at` | timestamp | Server time. |
| `updated_at` | timestamp | Server time. |

### `group_ops_workspace_draft_audit_logs`

Purpose: immutable audit log for draft lifecycle actions.

Suggested fields:

| Field | Type | Notes |
| --- | --- | --- |
| `audit_id` | string / uuid | Primary id. |
| `draft_id` | string / uuid | Draft id. |
| `actor_id` | string | Authenticated admin/operator actor. |
| `actor_role` | string / nullable | Role snapshot if available. |
| `action` | enum | `create`, `update`, `archive`, `request_review`, `reject`. |
| `version_before` | integer / nullable | Previous version. |
| `version_after` | integer | New version. |
| `snapshot_hash_before` | string / nullable | Previous sanitized snapshot hash. |
| `snapshot_hash_after` | string | New sanitized snapshot hash. |
| `metadata_json` | json | Redacted metadata only. |
| `created_at` | timestamp | Server time. |

### Payload storage rules

`sanitized_payload_json` and `sanitized_item_json` may contain:

- internal plan id / redacted plan reference
- entity type
- node type
- status and derived status
- count summaries
- Push Center projection id when already safe to display
- guardrail summary
- approval requirement summary
- copy-safe bundle summary ids

They must not contain:

- raw receiver
- raw `external_userid`
- phone
- raw chat/member id
- openid / unionid
- token
- secret
- `Authorization` header
- raw message body unless a reviewed redaction strategy exists; default is do
  not store
- raw callback body
- target lists that enable direct sending

## 4. API Proposal

This section is a design proposal only. No route or API is added in this PR.

All proposed APIs must use route owner `ai_crm_next`, capability owner
`automation_engine`, require admin authentication, and guarantee no external
call and no Push Center execution.

### GET `/api/admin/p1/group-ops-workspace/drafts`

- Owner: `automation_engine` / `ai_crm_next`
- Auth: admin cookie/session required; unauthenticated requests fail closed
- Request schema: pagination, status filter, source plan filter
- Response schema: draft summaries with `draft_id`, `draft_status`, `version`,
  `source_plan_id`, safe counts, updated time, actor summary
- Idempotency behavior: not applicable
- Audit behavior: no write audit; access logging only if existing pattern
  already requires it
- Failure modes: unauthenticated, forbidden, invalid filter, read model
  unavailable
- Rate / abuse guard: follow existing admin list endpoint rate/session policy
- No external call guarantee: true
- No Push Center execution guarantee: true

### GET `/api/admin/p1/group-ops-workspace/drafts/{draft_id}`

- Owner: `automation_engine` / `ai_crm_next`
- Auth: admin cookie/session required
- Request schema: `draft_id`
- Response schema: draft header, sanitized payload, item summaries, audit
  summary, guardrail summary
- Idempotency behavior: not applicable
- Audit behavior: no write audit; access logging only if existing pattern
  already requires it
- Failure modes: unauthenticated, forbidden, not found, archived visibility
  denied
- Rate / abuse guard: follow existing admin detail endpoint policy
- No external call guarantee: true
- No Push Center execution guarantee: true

### POST `/api/admin/p1/group-ops-workspace/drafts`

- Owner: `automation_engine` / `ai_crm_next`
- Auth: admin cookie/session required
- Request schema: idempotency key, source plan id, sanitized payload,
  guardrail summary, approval requirements, snapshot hash
- Response schema: created or reused draft, version, idempotency result,
  audit id
- Idempotency behavior: same actor + idempotency key returns the existing
  draft result; same snapshot hash may return duplicate summary if policy
  allows
- Audit behavior: create audit log with actor, action, draft id, version,
  snapshot hash, redacted metadata
- Failure modes: unauthenticated, forbidden, invalid payload, sensitive field
  rejected, duplicate conflict, stale source plan, validation error
- Rate / abuse guard: per-actor create limits if existing admin write patterns
  provide this; otherwise define a conservative future rate policy
- No external call guarantee: true
- No Push Center execution guarantee: true

### PATCH `/api/admin/p1/group-ops-workspace/drafts/{draft_id}`

- Owner: `automation_engine` / `ai_crm_next`
- Auth: admin cookie/session required
- Request schema: expected version, idempotency key, sanitized payload patch or
  full sanitized payload, snapshot hash
- Response schema: updated draft, new version, idempotency result, audit id
- Idempotency behavior: same draft + actor + idempotency key returns prior
  update response
- Audit behavior: update audit log with before/after version, before/after
  snapshot hash, redacted changed-field metadata
- Failure modes: unauthenticated, forbidden, not found, archived draft,
  version conflict, sensitive field rejected, duplicate conflict
- Rate / abuse guard: per-draft and per-actor update limits if available
- No external call guarantee: true
- No Push Center execution guarantee: true

### POST `/api/admin/p1/group-ops-workspace/drafts/{draft_id}/archive`

- Owner: `automation_engine` / `ai_crm_next`
- Auth: admin cookie/session required
- Request schema: expected version, idempotency key, archive reason
- Response schema: archived draft, version, audit id
- Idempotency behavior: duplicate archive request returns already archived
  result
- Audit behavior: archive audit log with actor, reason, version, snapshot hash
- Failure modes: unauthenticated, forbidden, not found, already archived,
  version conflict
- Rate / abuse guard: follow admin mutation policy
- No external call guarantee: true
- No Push Center execution guarantee: true

### POST `/api/admin/p1/group-ops-workspace/drafts/{draft_id}/request-review`

- Owner: `automation_engine` / `ai_crm_next`
- Auth: admin cookie/session required
- Request schema: expected version, idempotency key, reviewer scope, review
  note, guardrail acknowledgement
- Response schema: draft in `ready_for_review`, version, audit id, review
  request id if future review subsystem exists
- Idempotency behavior: duplicate request-review returns existing
  `ready_for_review` result for the same idempotency key
- Audit behavior: request-review audit log with actor, reviewer scope, version,
  snapshot hash, guardrail acknowledgement summary
- Failure modes: unauthenticated, forbidden, not found, archived draft, version
  conflict, governance requirements missing, invalid reviewer scope
- Rate / abuse guard: per-draft request-review throttle if available
- No external call guarantee: true
- No Push Center execution guarantee: true

## 5. Permission / Auth Model

Draft persistence must fail closed without authenticated admin context.

Proposed permissions:

- create draft: authenticated admin/operator with Group Ops workspace access
- edit draft: creator, assigned operator, or admin role with Group Ops write
  permission
- archive draft: creator or admin role; optionally owner/admin only after
  `ready_for_review`
- request review: creator or editor with explicit acknowledgement of guardrails
- view draft: users with Group Ops workspace read access and tenant/admin scope
  access

Actor recording:

- every mutation records `actor_id`
- record `actor_role` or permission snapshot if the current auth model exposes
  it
- unauthenticated, missing-cookie, expired-session, or forbidden requests must
  return controlled failure and must not create audit rows or drafts

Operator approval:

- draft creation is not operator approval
- request-review is not operator approval
- future execution still requires a separate approval / allowlist /
  gray-window path

## 6. Idempotency Design

Save draft idempotency key:

- generated client-side for the request and validated server-side, or generated
  server-side for retry tokens if that pattern already exists
- scope: actor + route + source plan + idempotency key
- duplicate key with identical snapshot returns the existing success response
- duplicate key with different snapshot returns conflict

Snapshot hash:

- computed over canonical sanitized payload and approval requirements
- used to detect duplicate save attempts and stale updates
- excludes volatile UI-only state such as filters, hover/focus, and copy
  preview state

Request-review idempotency:

- scope: draft id + actor + idempotency key
- repeated request-review returns existing ready-for-review response
- if the draft changed after the request-review snapshot, return stale version
  conflict

Failure retry:

- validation failures are retryable only after payload correction
- conflict failures require refresh and reapply
- server failures may be retried with the same idempotency key

## 7. Audit Log Design

The following actions must write audit logs:

- create
- update
- archive
- request-review
- reject, if added later

Each audit row records:

- actor id
- actor role / permission snapshot when available
- action
- draft id
- version before / after
- snapshot hash before / after
- source plan id
- high-level counts by entity type
- guardrail summary
- approval requirements summary
- request id / idempotency key hash or redacted idempotency reference

Audit rows must not record:

- sensitive payload
- raw receiver
- raw external user id
- phone
- raw chat/member id
- token / secret / Authorization header
- raw message or callback body
- direct-send target lists

Audit log should be append-only. Corrections should be represented as new rows,
not mutation of prior audit entries, unless a legal/compliance deletion policy
requires a separate redaction workflow.

## 8. Guardrail / Approval Design

Draft status semantics:

- `draft`: saved planning artifact, not executable
- `ready_for_review`: submitted for review, still not executable
- `archived`: hidden from active draft flows, not executable
- `rejected`: review result, not executable

Guardrails:

- `draft_status=draft` cannot execute
- `ready_for_review` cannot execute
- future execution must go through approval, receiver allowlist, gray-window,
  Push Center, and external-effect boundaries
- governance missing blocks execution
- sent evidence does not mean governance complete
- Push Center pending does not mean completed
- evidence-incomplete does not mean success
- copy-safe export is not an execution credential

The UI may show a "request review" action after draft save, but it must not show
"send", "execute", or "mark complete" as a result of draft persistence.

## 9. Push Center Bridge Design

Future bridge path:

1. draft
2. request review
3. approved package
4. Push Center job
5. external-effect job, if and only if the existing external-effect boundary
   permits it

Bridge rules:

- Push Center remains the only send/status explanation entry point.
- Draft APIs must not create Push Center jobs.
- Draft APIs must not create `external_effect_job`.
- The bridge requires a separate design and implementation PR.
- The bridge requires production tests that prove no draft save or update can
  trigger execution.
- External-effect execution remains controlled by existing integration /
  external-effect boundaries.

## 10. Frontend Integration Plan

Future frontend changes should be staged after backend draft model and API are
approved.

Potential UI actions:

- Save draft
- Save as new version
- Archive draft
- Request review
- View draft list
- View version history
- Resolve stale version conflict
- Retry failed save with same idempotency key

State handling:

- Dirty state tracks payload changes only.
- Filter/search/view state remains frontend memory-only unless explicitly
  included in the sanitized payload design.
- Preview bundle export remains frontend-only and is not saved as production
  data.
- Optimistic UI is allowed only if it clearly displays "saving" and rolls back
  on conflict/failure; it must not show execution success.
- Save failure, permission failure, and stale version conflict must preserve the
  local unsaved draft for user recovery.

Frontend must continue to show:

- `preview-only`
- no production write until the save response succeeds
- no real external call
- not `PASS_90_PLUS`
- sent evidence does not bypass governance

## 11. Migration Plan

This RFC does not create a migration.

Future migration plan:

- create `group_ops_workspace_drafts`
- create `group_ops_workspace_draft_items`
- create `group_ops_workspace_draft_audit_logs`
- add indexes for tenant/admin scope + draft status + updated time
- add index for source plan id
- add unique constraint for scoped idempotency key
- add version constraint for optimistic concurrency
- add FK from draft items and audit logs to drafts, subject to local DB
  conventions
- no backfill required

Rollback strategy:

- migration rollback drops draft tables before any production usage, if safe
- after production usage, rollback should archive/disable write paths first and
  retain audit logs unless data governance approves deletion
- failed migration verification must confirm no partial write path is exposed

Production migration verification:

- tables exist
- indexes exist
- unique constraints exist
- write API remains disabled until backend implementation PR is deployed
- no Push Center or external-effect rows are created by migration

## 12. Rollback / Cleanup Plan

Draft cleanup operations:

- archive drafts through controlled admin action
- cleanup orphan draft items via audited maintenance script if FK protection is
  not sufficient
- retain audit logs according to product/compliance retention policy
- do not hard-delete audit rows through normal UI

Failed implementation rollback:

- disable draft write routes
- keep read-only workspace available
- preserve existing legacy Group Ops page
- revert frontend save controls if they confuse operators
- verify no external-effect jobs or Push Center jobs were created by draft save

## 13. Production Test Plan

Required tests before implementation can be considered production-ready:

- unauthenticated write request fail-closed
- forbidden user write request fail-closed
- create draft produces no external call
- update draft produces no external call
- archive draft produces no external call
- request review produces no external call
- create draft produces no Push Center job
- update draft produces no Push Center job
- archive draft produces no Push Center job
- request review produces no Push Center job
- create/update/archive/request-review produce no `external_effect_job`
- duplicate idempotency key with same snapshot returns existing response
- duplicate idempotency key with different snapshot returns conflict
- stale version update returns conflict
- sensitive field rejection covers raw receiver, raw external user id, phone,
  raw chat/member id, token, secret, Authorization-like header, raw message
  body, and raw callback body
- audit log written for create, update, archive, and request-review
- audit log contains only redacted metadata
- legacy Group Ops page remains unaffected
- read-only workspace still renders no-write and no-external-call guardrails

## 14. Acceptance Criteria

This RFC must be reviewed before implementation starts.

Implementation PRs must be split:

1. draft model migration only
2. backend read/write API for draft persistence
3. frontend save draft integration
4. approval/review request integration
5. Push Center bridge, independent and later

Each implementation PR must include focused tests and must keep external-effect
and Push Center boundaries intact.

## 15. Risk Assessment

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Data leakage | Sensitive receiver or customer data could be persisted. | Store sanitized structure only; reject sensitive fields; audit redacted metadata only. |
| Governance bypass | Draft could be misused as approval. | Draft and ready-for-review are non-executable; future execution requires approval / allowlist / gray-window. |
| Draft mistaken for send | Operators may think saved draft is sent/completed. | UI copy and status model must keep draft separate from sent/completed. |
| Duplicate submit | Repeated save/review creates duplicate drafts or requests. | Idempotency key + snapshot hash + version checks. |
| Audit gap | Mutations cannot be traced. | Mandatory append-only audit rows for every mutation. |
| Rollback complexity | Tables exist after partial rollout. | Migration-only PR, route disabled until API PR, archive/disable write paths before rollback. |
| Legacy page impact | New workspace could affect existing Group Ops operations. | Keep P1 workspace isolated; legacy route and tests remain unchanged. |
| External-effect boundary regression | Draft save accidentally creates send jobs. | Production tests assert no Push Center job and no external-effect job from draft APIs. |

## 16. Verdict

`RFC_READY_FOR_REVIEW`

The design is ready for product/engineering review.

`IMPLEMENTATION_NOT_STARTED`

No migration, API, write path, frontend save action, or production persistence
is implemented in this PR.

`EXECUTION_NOT_IN_SCOPE`

Draft persistence is not execution. Sending, Push Center job creation, and
external-effect execution remain out of scope.

`PASS_90_PLUS_NOT_CLAIMED`

This RFC does not change the business closeout verdict. `P1_READY_WITH_EXCEPTIONS`
remains distinct from `PASS_90_PLUS`.

## Frontend Skill Checklist

- 已读取 `frontend-development-skill.md`: 是
- 参考的已有页面: `/admin/p1/group-ops-workspace`,
  `/admin/automation-conversion/group-ops/ui`
- 参考的已有组件: P1 workspace shared status cards, guardrail notice,
  interaction shell, preview bundle, copy-safe export
- 复用的 hooks / services / types: `WorkspaceFixture`, `WorkspaceViewState`,
  `WorkspacePreviewBundle`, existing read-only Group Ops / Push Center data
  binding
- 是否新增组件: 否
- 新增组件原因: 不适用，本 PR 只新增 RFC 文档和轻量文档契约测试
- 一级 / 二级页面职责划分: 独立 P1 workspace 继续作为试用工作台；legacy
  Group Ops 页面继续承担日常运营入口；draft persistence 后续应在独立实现
  PR 中设计保存入口
- 是否存在重复标题和说明: 否
- 是否存在重复造轮子风险: 否，本 PR 不新增前端组件或交互逻辑
- 自检结论: 通过；RFC 明确 draft persistence 不等于 execution、不绕过
  Push Center / approval / allowlist / gray-window / external-effect boundary
