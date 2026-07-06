# P1 Group Ops Workspace Read-only Closeout - 2026-06-24

Acceptance verdict:

- `READ_ONLY_WORKSPACE_READY`
- `DRAFT_PERSISTENCE_NOT_READY`
- `EXECUTION_NOT_READY`
- `PASS_90_PLUS_NOT_CLAIMED`

This report closes the read-only trial slice for
`/admin/p1/group-ops-workspace`. It is the stage baseline before any draft
persistence design review. It does not add runtime behavior, backend APIs,
write capability, external-effect execution, or production persistence.

## Executive Summary

`/admin/p1/group-ops-workspace` is now read-only trial-ready.

The workspace can load existing read-only Group Ops and Push Center data,
display it in a TypeScript-native workspace, let operators inspect details,
filter/search, navigate the grouped canvas, build a local preview bundle, and
copy a redacted bundle summary for human review.

Current capability is limited to:

- frontend-only rendering
- read-only GET data binding
- memory-only selection, filters, canvas state, density, and preview bundles
- copy-safe text / JSON export through browser clipboard
- truthful guardrail display

Current capability does not include:

- draft persistence
- backend draft model
- save action
- real drag execution
- Push Center execution bridge
- external-effect execution
- approval / allowlist / gray-window writes
- global `PASS_90_PLUS`

## Implemented Capability Matrix

| PR | Capability | Route / page touched | New frontend modules | Data source | Write capability | External call | Production persistence | Sensitive data exposure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| #1369 | P1 native workspace shell | `/admin/p1/group-ops-workspace` | `workspace_status.ts`, `workspace_layout.ts`, `workspace_preview.ts`, `workspace_fixture.ts` | local safe fixture + existing admin shell route | false | false | false | guarded |
| #1370 | Read-only real-data binding | `/admin/p1/group-ops-workspace` | `workspace_api.ts` | existing Group Ops GET APIs and Push Center GET API | false | false | false | guarded |
| #1372 | Drilldown / detail panel | `/admin/p1/group-ops-workspace` | `workspace_detail.ts` | loaded read-only workspace data | false | false | false | guarded |
| #1374 | Filter / search / local view state | `/admin/p1/group-ops-workspace` | `workspace_filters.ts`, `workspace_view_state.ts` | loaded read-only workspace data | false | false | false | guarded |
| #1375 | Read-only grouped canvas | `/admin/p1/group-ops-workspace` | `workspace_canvas.ts`, `workspace_grouping.ts`, `workspace_sorting.ts` | loaded read-only workspace data | false | false | false | guarded |
| #1376 | UX polish / keyboard navigation / safe preview | `/admin/p1/group-ops-workspace` | `workspace_density.ts`, `workspace_keyboard.ts` | loaded read-only workspace data | false | false | false | guarded |
| #1377 | Multi-select preview bundle | `/admin/p1/group-ops-workspace` | `workspace_multi_select.ts`, `workspace_preview_bundle.ts` | loaded read-only workspace data | false | false | false | guarded |
| #1379 | Copy-safe text / JSON export | `/admin/p1/group-ops-workspace` | `workspace_bundle_export.ts` | selected in-memory preview bundle | false | false | false | guarded |

## Current Architecture Boundary

Page:

- `/admin/p1/group-ops-workspace`

Route owner:

- `ai_crm_next`

Capability owner:

- `automation_engine`

Legacy boundary:

- `/admin/automation-conversion/group-ops/ui` remains the daily operations
  page.
- The P1 workspace does not replace the legacy Group Ops default page.
- The P1 workspace is an independent TypeScript-native trial workspace.

Data source:

- Existing read-only Group Ops plan/detail/groups/nodes/executions GET APIs.
- Existing Push Center jobs GET API.
- No new backend API is required by the read-only closeout.

Writes and execution:

- write capability: none
- backend draft persistence: none
- production persistence: none
- external effect: none
- Push Center execution: none
- approval / allowlist / gate bypass: none
- URL query persistence: none
- localStorage / sessionStorage persistence: none
- file download: none

Rollback boundary:

- Revert the P1 workspace frontend PRs if the trial workspace must be removed.
- No data rollback is required.
- No external-effect rollback is required.
- Legacy Group Ops page remains available.

## Guardrail Status

The workspace must keep these guardrails visible and enforced:

- `preview-only=true`
- `production_write=false`
- `real_external_call=false`
- `can_claim_pass_90_plus=false`
- sent evidence does not mean governance complete
- pending does not mean completed
- evidence-incomplete does not mean success
- preview bundle cannot execute
- copied summary cannot execute
- `P1_READY_WITH_EXCEPTIONS` is not `PASS_90_PLUS`

The workspace may display a sent Push Center or external-effect evidence state,
but it must not use that state to skip approval, receiver allowlist,
gray-window, Push Center, or external-effect boundaries.

## Sensitive-data Redaction

The workspace, copy-safe export module, and tests cover that rendered or copied
output must not expose:

- raw receiver
- raw `external_userid`
- phone
- raw chat/member id
- openid / unionid
- token
- secret
- `Authorization` header
- raw message body
- raw callback body
- any raw target list that could be used for direct sending

Allowed output is limited to redacted or internal summary fields such as:

- plan id / plan name
- entity type
- status / derived status
- counts
- projection id / Push Center status
- guardrail summary
- copy-safe selected item summary

## Verification Matrix

The following commands should remain the baseline for this read-only workspace:

```bash
npm run build:frontend
npm run typecheck
npm run test:frontend
.venv/bin/python -m pytest tests/test_group_ops_frontend_contract.py -q
.venv/bin/python -m pytest tests/test_p1_group_ops_workspace_frontend_contract.py -q
.venv/bin/python scripts/diagnose_business_closure_acceptance.py --scenario all
bash scripts/ci/run_architecture_gates.sh
git diff --check
```

If a worktree does not have its own `.venv`, use the repository-approved venv
path and keep the command semantics unchanged.

## Known Limitations

The read-only workspace intentionally does not provide:

- save draft
- real drag execution
- backend draft model
- draft migration
- approval flow binding
- receiver allowlist write
- gray-window write
- Push Center execution bridge
- external-effect execution
- production persistence
- `PASS_90_PLUS`

Operational limitations:

- Real-data rendering depends on existing read-only APIs being available.
- API failure must render `real_data_unavailable`, not sent or completed.
- Missing Push Center projection must remain evidence-incomplete.
- Missing governance evidence must remain governance-missing.
- Copied summaries are for human review and communication only.
- Copied summaries are not execution credentials, approval records, or
  production evidence by themselves.

## Draft Persistence Preconditions

Before moving from read-only trial to draft persistence, a design RFC must
settle the following:

- backend draft model
- route owner / API owner
- DB migration plan
- idempotency key design
- audit log design
- permission / auth design
- approval gate design
- receiver allowlist gate design
- gray-window gate design
- Push Center bridge design
- external-effect boundary preservation
- sensitive-data redaction and storage policy
- rollback / cleanup plan
- production test plan

The draft persistence phase must not bypass Push Center, approval, allowlist,
gray-window, or external-effect gates.

## Proposed Next Phase

Recommended next PR:

- `P1 Group Ops Workspace Draft Persistence Design RFC`

Implementation should wait until the RFC is reviewed. A likely sequence after
the RFC:

1. draft model migration
2. read/write API with route owner and idempotency
3. frontend save-draft action
4. approval bridge
5. Push Center bridge
6. separate external-effect execution evidence window, if business-approved

## Risk / Rollback

Risk is low because the current workspace is read-only and frontend-scoped.

Rollback:

- revert the P1 workspace frontend PRs or this closeout report
- no data rollback
- no external-effect rollback
- no deploy/systemd/nginx/env rollback
- legacy Group Ops page is unaffected

## Acceptance Verdict

`READ_ONLY_WORKSPACE_READY`

The workspace is ready for read-only trial usage and review.

`DRAFT_PERSISTENCE_NOT_READY`

Draft persistence requires a design RFC and the backend/API/audit/gate design
listed above.

`EXECUTION_NOT_READY`

The workspace must not execute tasks, trigger Push Center runs, create external
effects, or perform real sends.

`PASS_90_PLUS_NOT_CLAIMED`

The read-only workspace does not change the business closeout verdict. It must
continue to show `P1_READY_WITH_EXCEPTIONS` and must not claim
`PASS_90_PLUS`.

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
- 新增组件原因: 不适用，本 PR 为 read-only closeout report 和轻量契约测试
- 一级 / 二级页面职责划分: 独立 P1 workspace 作为试用工作台；legacy Group
  Ops 页面继续承担日常运营入口
- 是否存在重复标题和说明: 否
- 是否存在重复造轮子风险: 否，本 PR 不新增前端组件或交互逻辑
- 自检结论: 通过；read-only、memory-only、no write、no external call、
  no PASS_90_PLUS 边界已记录
