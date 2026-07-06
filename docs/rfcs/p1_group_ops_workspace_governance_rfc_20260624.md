# P1 Group Ops Workspace Governance RFC - 2026-06-24

RFC verdict:

- `GOVERNANCE_RFC_READY_FOR_REVIEW`
- `GOVERNANCE_IMPLEMENTATION_NOT_STARTED`
- `PUSH_CENTER_BRIDGE_NOT_STARTED`
- `EXECUTION_NOT_IN_SCOPE`
- `PASS_90_PLUS_NOT_CLAIMED`

This RFC defines the governance design boundary after draft persistence and
request-review support for `/admin/p1/group-ops-workspace`.

It does not add migrations, APIs, write endpoints, frontend approval actions,
Push Center jobs, broadcast jobs, internal events, external-effect jobs, or any
real external call.

## 1. Executive Summary

`ready_for_review` is not approved.

Plain rule: ready_for_review is not approved.

A saved Group Ops workspace draft must pass three governance checks before any
future execution package can be considered:

1. operator approval
2. receiver allowlist approval
3. gray-window approval

All three checks are governance evidence only. Even when all three are approved,
the draft still must not directly create an `external_effect_job`, directly send
messages, or bypass Push Center.

Push Center remains the only future sending entry point. The external-effect
boundary remains owned by the existing external effects infrastructure and must
not be bypassed by governance APIs.

## 2. Non-goals

This RFC explicitly does not authorize:

- sending messages
- creating Push Center jobs
- creating `external_effect_job`
- creating `broadcast_job`
- creating `internal_event`
- calling WeCom, webhook, message-send, or any external adapter
- treating approval as execution
- treating `ready_for_review` as approved
- treating `governance_approved` as sent or completed
- claiming `PASS_90_PLUS`
- replacing the legacy Group Ops operations page
- adding compatibility shims or restoring legacy runtime
- changing deploy/systemd/nginx/env
- running a production migration

## 3. Governance State Model

### Draft status

| Status | Entry condition | Exit condition | Operator | Executable | Push Center job creation |
| --- | --- | --- | --- | --- | --- |
| `draft` | Draft created or updated. | Archive, reject, or request review. | Draft owner or authorized admin. | false | false |
| `ready_for_review` | Existing draft requested review through the draft API. | Governance request, archive, or reject. | Authorized admin/operator. | false | false |
| `archived` | Draft archived. | None by default; restore would require a separate RFC. | Authorized admin/operator. | false | false |
| `rejected` | Draft rejected by future review flow. | New draft or explicit reopen flow in a later RFC. | Authorized reviewer/operator. | false | false |

### Governance status

| Status | Entry condition | Exit condition | Operator | Executable | Push Center job creation |
| --- | --- | --- | --- | --- | --- |
| `governance_not_started` | Draft is not under governance review. | Governance request is created from `ready_for_review`. | None. | false | false |
| `approval_pending` | Governance review exists and operator approval step is pending. | Operator approval step approved or rejected. | Authorized operator approver. | false | false |
| `allowlist_pending` | Operator approval passed; receiver allowlist step pending. | Allowlist step approved or rejected. | Authorized allowlist reviewer. | false | false |
| `gray_window_pending` | Allowlist step passed; gray-window step pending. | Gray-window step approved, rejected, or expired. | Authorized gray-window reviewer. | false | false |
| `governance_approved` | All required steps are approved and current gray window is valid. | Expire, reject by policy, or draft snapshot changes. | Governance reviewer or automated expiry check. | false | Future bridge PR only |
| `governance_rejected` | Any required step is rejected. | New governance request after a new draft version. | Authorized reviewer/operator. | false | false |
| `governance_expired` | Approved review passes its expiry or gray window ends. | New governance request for a current draft version. | Automated expiry check or authorized operator. | false | false |

Important invariants:

- `ready_for_review` cannot execute.
- `governance_approved` cannot execute by itself.
- Governance APIs must not create Push Center jobs.
- Governance APIs must not create external-effect jobs.
- Only a later Push Center bridge PR may evaluate whether
  `governance_approved` can become a Push Center job.

## 4. Data Model Proposal

This is a proposal only. This PR creates no migration.

### `group_ops_workspace_governance_reviews`

Purpose: one governance review envelope for a draft snapshot.

Suggested fields:

| Field | Type | Notes |
| --- | --- | --- |
| `review_id` | string / uuid | Primary id. |
| `draft_id` | string / uuid | FK to `group_ops_workspace_drafts`. |
| `draft_version` | integer | Draft version under review. |
| `review_status` | enum | Governance state. |
| `requested_by` | string | Actor id from authenticated admin context. |
| `approved_by` | string / nullable | Final approving actor if policy allows one final approver. |
| `rejected_by` | string / nullable | Actor who rejected the review. |
| `idempotency_key` | string | Request-level idempotency key. |
| `snapshot_hash` | string | Draft snapshot hash at request time. |
| `sanitized_payload_hash` | string | Hash of sanitized payload only. |
| `audit_metadata_json` | json | Redacted metadata only. |
| `expires_at` | timestamp / nullable | Review expiry. |
| `created_at` | timestamp | Server time. |
| `updated_at` | timestamp | Server time. |

### `group_ops_workspace_governance_review_steps`

Purpose: normalized state for operator approval, allowlist approval, and
gray-window approval.

Suggested fields:

| Field | Type | Notes |
| --- | --- | --- |
| `step_id` | string / uuid | Primary id. |
| `review_id` | string / uuid | FK to governance review. |
| `draft_id` | string / uuid | Redundant index helper. |
| `step_type` | enum | `operator_approval`, `receiver_allowlist`, `gray_window`. |
| `step_status` | enum | `pending`, `approved`, `rejected`, `expired`. |
| `requested_by` | string | Actor id. |
| `approved_by` | string / nullable | Actor id. |
| `rejected_by` | string / nullable | Actor id. |
| `idempotency_key` | string | Step-level idempotency key. |
| `snapshot_hash` | string | Draft snapshot hash for stale checks. |
| `audit_metadata_json` | json | Redacted metadata only. |
| `expires_at` | timestamp / nullable | Step expiry. |
| `created_at` | timestamp | Server time. |
| `updated_at` | timestamp | Server time. |

### `group_ops_workspace_allowlist_snapshots`

Purpose: immutable redacted allowlist evidence for the reviewed draft.

Suggested fields:

| Field | Type | Notes |
| --- | --- | --- |
| `snapshot_id` | string / uuid | Primary id. |
| `review_id` | string / uuid | FK to governance review. |
| `draft_id` | string / uuid | Draft under review. |
| `allowlist_summary_json` | json | Count, source label, and redacted policy summary. |
| `allowlist_hash` | string | Hash of approved allowlist source. |
| `receiver_count` | integer | Count only; no raw receiver list. |
| `source_reference` | string | Redacted internal reference. |
| `created_by` | string | Actor id. |
| `expires_at` | timestamp / nullable | Snapshot expiry. |
| `created_at` | timestamp | Server time. |

### `group_ops_workspace_gray_window_approvals`

Purpose: explicit approval for the time window in which a future bridge may
enqueue a Push Center job.

Suggested fields:

| Field | Type | Notes |
| --- | --- | --- |
| `gray_window_id` | string / uuid | Primary id. |
| `review_id` | string / uuid | FK to governance review. |
| `draft_id` | string / uuid | Draft under review. |
| `gray_window_json` | json | `start_at`, `end_at`, `timezone`, policy label. |
| `approved_by` | string | Actor id. |
| `approval_reference` | string | Redacted internal reference. |
| `expires_at` | timestamp | Same or earlier than `end_at`. |
| `created_at` | timestamp | Server time. |
| `updated_at` | timestamp | Server time. |

### Sensitive storage boundary

Governance tables may store only sanitized summaries, internal references,
counts, hashes, and audit metadata.

They must not store:

- raw receiver
- raw `external_userid`
- phone
- raw chat/member id
- openid / unionid
- token
- secret
- `Authorization` header
- raw target list
- raw message body
- raw callback body
- any payload that can be used as a direct send target list

## 5. API Proposal

This section is design only. No route is added in this PR.

All future APIs must use route owner `ai_crm_next`, capability owner
`automation_engine`, require admin/operator authentication, and guarantee no
external call and no Push Center job creation.

### POST `/api/admin/p1/group-ops-workspace/drafts/{draft_id}/governance/request`

- Owner: `automation_engine` / `ai_crm_next`
- Auth requirement: authenticated admin/operator; unauthenticated requests fail closed
- Request schema: expected draft version, idempotency key, snapshot hash,
  sanitized guardrail acknowledgement, optional reviewer scope
- Response schema: review id, `review_status=approval_pending`, step summaries,
  `approved=false`, `push_center_job_created=false`, `external_effect_job_created=false`
- Idempotency: same actor + draft + idempotency key + snapshot hash returns the
  prior review result
- Audit: write request audit with actor, draft id, version, snapshot hash, and
  redacted metadata
- Failure modes: unauthenticated, forbidden, draft not found, draft not
  `ready_for_review`, stale version, snapshot mismatch, sensitive field
  rejected, duplicate conflict
- No external call guarantee: true
- No Push Center job creation guarantee: true

### GET `/api/admin/p1/group-ops-workspace/governance/{review_id}`

- Owner: `automation_engine` / `ai_crm_next`
- Auth requirement: authenticated admin/operator
- Request schema: review id
- Response schema: review header, step timeline, allowlist summary,
  gray-window summary, audit summary, all redacted
- Idempotency: not applicable
- Audit: read access logging only if current admin pattern requires it
- Failure modes: unauthenticated, forbidden, not found
- No external call guarantee: true
- No Push Center job creation guarantee: true

### POST `/api/admin/p1/group-ops-workspace/governance/{review_id}/steps/{step_id}/approve`

- Owner: `automation_engine` / `ai_crm_next`
- Auth requirement: authenticated reviewer with the step-specific role
- Request schema: expected review version, idempotency key, step type,
  sanitized approval note, snapshot hash
- Response schema: updated step, review status, `approved=false` unless all
  governance steps pass; execution flags remain false
- Idempotency: duplicate approve with same key returns prior step result
- Audit: approve audit with actor, step id, review id, before/after status,
  snapshot hash, redacted metadata
- Failure modes: unauthenticated, forbidden, stale version, wrong step type,
  already rejected, expired, duplicate conflict, sensitive field rejected
- No external call guarantee: true
- No Push Center job creation guarantee: true

### POST `/api/admin/p1/group-ops-workspace/governance/{review_id}/steps/{step_id}/reject`

- Owner: `automation_engine` / `ai_crm_next`
- Auth requirement: authenticated reviewer with the step-specific role
- Request schema: expected review version, idempotency key, sanitized reject
  reason, snapshot hash
- Response schema: updated step, `review_status=governance_rejected`,
  execution flags false
- Idempotency: duplicate reject with same key returns prior rejection result
- Audit: reject audit with actor, step id, review id, before/after status,
  redacted metadata
- Failure modes: unauthenticated, forbidden, stale version, already approved by
  conflicting key, expired, sensitive field rejected
- No external call guarantee: true
- No Push Center job creation guarantee: true

### POST `/api/admin/p1/group-ops-workspace/governance/{review_id}/expire`

- Owner: `automation_engine` / `ai_crm_next`
- Auth requirement: authenticated operator or future scheduled governance
  expiry worker with explicit owner
- Request schema: expected review version, idempotency key, expiry reason
- Response schema: `review_status=governance_expired`, step expiry summary,
  execution flags false
- Idempotency: duplicate expire returns existing expired state
- Audit: expire audit with actor/system actor, review id, reason, redacted metadata
- Failure modes: unauthenticated, forbidden, not expired yet, already rejected,
  stale version
- No external call guarantee: true
- No Push Center job creation guarantee: true

## 6. Permission Model

Governance must fail closed without authenticated admin/operator context.

Suggested role model:

| Capability | Allowed actor | Notes |
| --- | --- | --- |
| Request governance | Draft creator, admin, or operator with workspace permission | Draft must be `ready_for_review`. |
| Operator approve | Operator approver role | May require separation from requester. |
| Allowlist approve | Allowlist reviewer / admin role | Must verify snapshot hash and count. |
| Gray-window approve | Gray-window approver / operations lead | Must verify time window and timezone. |
| Reject step | Same role as approver or higher admin | Must provide sanitized reason. |
| Expire review | System expiry actor or operator/admin | Must write audit. |

Policy choices that must be settled before implementation:

- whether submitter and approver may be the same person
- whether two-person approval is required
- whether allowlist and gray-window approvers can be the same actor
- how roles map to current admin session claims
- how emergency rejection or expiry is handled

Unauthenticated, missing-cookie, or insufficient-role requests must return
401/403 and must not create reviews, steps, audit rows, Push Center jobs,
broadcast jobs, internal events, external effects, or external calls.

## 7. Allowlist Design

The receiver allowlist step validates that the selected audience/receiver scope
is approved for the gray send.

Rules:

- Store only redacted summary, hash, count, source reference, and expiry.
- Do not store raw receiver lists.
- Do not store raw external ids, raw chat/member ids, or phone numbers.
- Generate `allowlist_hash` from the approved allowlist source outside the
  request body where possible.
- Persist `receiver_count` and policy label for human review.
- If allowlist content changes, the hash must change and prior approval must
  become stale.
- Count mismatch or hash mismatch must block approval.
- Expired allowlist snapshots must move review to `governance_expired` or
  require a new governance request.
- A future Push Center bridge must re-check the allowlist hash and snapshot
  expiry before creating any job.

Failure examples:

- `allowlist_hash_mismatch`
- `allowlist_count_mismatch`
- `allowlist_snapshot_expired`
- `allowlist_source_missing`
- `allowlist_sensitive_payload_rejected`

## 8. Gray-window Design

A gray window is the approved time interval in which a future bridge may submit
an already governed draft to Push Center.

Required fields:

- `start_at`
- `end_at`
- `timezone`
- redacted approval reference
- approved actor id
- policy label

Rules:

- `start_at` must be before `end_at`.
- Timezone must be explicit.
- Future bridge must reject requests outside the approved window.
- When the window expires, governance becomes `governance_expired`.
- A changed draft snapshot requires a new review or explicit re-approval.
- A changed receiver allowlist requires a new review or explicit re-approval.
- A renewed window must create a new approval record or a new review version.
- Audit must capture actor, timestamps, snapshot hash, and redacted policy
  metadata.

Failure examples:

- `gray_window_missing`
- `gray_window_invalid_range`
- `gray_window_timezone_missing`
- `gray_window_not_started`
- `gray_window_expired`
- `gray_window_snapshot_mismatch`

## 9. Audit / Idempotency

All governance mutations must write audit rows:

- request governance
- approve step
- reject step
- expire review

Audit may store:

- actor id / role snapshot
- action
- review id
- draft id
- step id
- version
- snapshot hash
- before/after status metadata
- redacted reason or policy reference
- created time

Audit must not store raw payloads, raw receivers, phone numbers, tokens,
secrets, target lists, raw message bodies, raw callback bodies, or anything
usable for direct sending.

Idempotency rules:

- Request governance idempotency scope: actor/admin scope + draft id +
  idempotency key + snapshot hash.
- Step approval idempotency scope: actor/admin scope + review id + step id +
  idempotency key + expected status.
- Duplicate approve/reject with the same key and same payload returns prior
  result.
- Same key with different payload returns 409 conflict.
- Stale review version returns 409 conflict.
- Repeated governance request for an unchanged draft may return the existing
  active review.
- Repeated governance request after draft snapshot changes must create a new
  review or require explicit conflict handling.

## 10. Push Center Bridge Preconditions

The future Push Center bridge may be considered only when all of these are true:

- `draft_status=ready_for_review`
- `governance_status=governance_approved`
- operator approval step is approved
- receiver allowlist step is approved
- gray-window step is approved and not expired
- current time is inside the approved gray window
- draft `snapshot_hash` matches governance `snapshot_hash`
- allowlist hash matches governance allowlist snapshot
- no sensitive payload is present
- actor is authorized for bridge submission
- idempotency key is valid

Even when all preconditions pass, only a later Push Center bridge PR may create
a Push Center job. Only a later Push Center bridge PR may create the job.
Governance request and approval APIs must never create a Push Center job,
broadcast job, internal event, external-effect job, or external call.

## 11. Frontend Integration Plan

Future frontend work should extend `/admin/p1/group-ops-workspace` with a
governance panel after backend governance APIs exist.

Planned UI elements:

- Governance panel
- request governance button
- step status timeline
- operator approval required copy
- allowlist summary card
- gray-window summary card
- rejected state
- expired state
- stale snapshot warning
- conflict state
- audit summary
- no execute button
- no send button
- no Push Center job display until bridge exists

Frontend guardrails:

- `ready_for_review` is not approved.
- `governance_approved` is still not execution.
- `sent` evidence does not bypass governance.
- Missing allowlist blocks bridge.
- Expired gray window blocks bridge.
- No frontend action may call send/run/execute endpoints.
- No frontend action may create external effects.
- No frontend action may create Push Center jobs before the bridge PR.

## 12. Production Test Plan

Future implementation PRs must include production-safe tests for:

- unauthenticated governance request fail-closed
- unauthorized approval fail-closed
- request governance writes review/audit only
- approve step writes step/audit only
- reject step writes step/audit only
- expire review writes review/audit only
- no Push Center job created
- no `external_effect_job` created
- no `broadcast_job` created
- no `internal_event` created
- no external call executed
- sensitive field rejection
- allowlist hash mismatch rejected
- allowlist count mismatch rejected
- gray-window expired rejected
- gray-window invalid range rejected
- stale review version conflict
- duplicate idempotency key behavior
- governance approved still not execution
- legacy Group Ops page unaffected
- P1 workspace still displays governance status truthfully

## 13. Acceptance Criteria

This RFC must be accepted before any governance implementation begins.

Implementation PRs must remain split:

1. governance migration only
2. backend governance request/review API
3. frontend governance panel
4. approval/allowlist/gray-window step APIs
5. frontend approval step integration
6. Push Center bridge later

Each implementation PR must keep these boundaries:

- no real external call
- no direct external-effect execution
- no Push Center bridge until its dedicated PR
- no send/execute/run button before bridge
- no sensitive receiver payload storage
- no `PASS_90_PLUS` claim from governance alone

## 14. Verdict

Recommended verdict:

- `GOVERNANCE_RFC_READY_FOR_REVIEW`
- `GOVERNANCE_IMPLEMENTATION_NOT_STARTED`
- `PUSH_CENTER_BRIDGE_NOT_STARTED`
- `EXECUTION_NOT_IN_SCOPE`
- `PASS_90_PLUS_NOT_CLAIMED`

This RFC is ready for review. Implementation has not started. Execution is not
in scope. Push Center bridge remains a separate later PR.

## 15. Verification Baseline

Because this PR is documentation-only, validation should prove that no runtime,
API, migration, or frontend behavior was introduced.

Required commands:

```bash
npm run build:frontend
npm run typecheck
npm run test:frontend
.venv/bin/python -m pytest tests/test_group_ops_frontend_contract.py -q
.venv/bin/python -m pytest tests/test_p1_group_ops_workspace_frontend_contract.py -q
.venv/bin/python -m pytest tests/test_group_ops_workspace_draft_migration.py -q
.venv/bin/python -m pytest tests/test_p1_group_ops_workspace_draft_api.py -q
.venv/bin/python scripts/diagnose_business_closure_acceptance.py --scenario all
bash scripts/ci/run_architecture_gates.sh
git diff --check
```

## 16. Frontend Skill Checklist

- 已读取 `frontend-development-skill.md`: 是
- 参考的已有页面: `/admin/p1/group-ops-workspace`
- 参考的已有组件: shared status / guardrail / interaction modules only as
  future integration context
- 复用的 hooks / services / types: no implementation in this RFC
- 是否新增组件: 否
- 新增组件原因: 不适用
- 一级 / 二级页面职责划分: P1 workspace remains the future governance panel
  host; legacy Group Ops remains the operational page
- 是否存在重复标题和说明: 否
- 是否存在重复造轮子风险: 否，本 PR 只做治理设计
- 自检结论: RFC-only, no runtime behavior added
