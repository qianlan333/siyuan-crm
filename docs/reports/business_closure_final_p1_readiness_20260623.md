# Business Closure Final P1 Readiness - 2026-06-23

Executive verdict: `P1_READY_WITH_EXCEPTIONS`

This report is the final business-closure readiness decision before starting
P1 TypeScript Frontend Foundation. It summarizes the available redacted
operator evidence and the remaining exceptions. It does not claim global
`PASS_90_PLUS`.

## Scope

Evidence inputs:

- `docs/reports/evidence/external_orders_consumer_run_due_evidence_20260623.md`
- `docs/reports/evidence/group_ops_gray_send_evidence_20260623.md`
- `docs/reports/evidence/group_ops_gray_send_approval_allowlist_window_supplement_20260623.md`
- `docs/reports/evidence/ops_plan_to_broadcast_next_native_cloud_plan_e2e_20260623.md`
- `docs/reports/evidence/wecom_auth_callback_evidence_20260623.md`
- `docs/reports/evidence/wecom_auth_callback_operator_evidence_20260623.md`
- `docs/reports/business_closure_90_plus_evidence_closeout.md`
- `docs/runbooks/operator_business_closure_evidence_collection.md`

Non-goals:

- no runtime code changes
- no route changes
- no production deploy/systemd/nginx/env changes
- no production migration
- no production DB write
- no new real external effect trigger
- no P1 frontend implementation in this PR
- no token, secret, `Authorization` header, raw `external_userid`, receiver
  plaintext, phone number, openid/unionid, raw target list, raw callback body,
  or customer-private request/response body in this report

## Executive Verdict

`P1_READY_WITH_EXCEPTIONS`

P1 may start, but the business closure cannot be represented as global
`PASS_90_PLUS` yet.

This is intentionally stricter than a marketing-style "all green" closeout:

- External Orders has production evidence and is `EVIDENCE_COLLECTED /
  order_linked`.
- Ops Plan -> Broadcast has a Next-native evidence chain to `broadcast_job` and
  Push Center pending, and is `EVIDENCE_COLLECTED`.
- Group Ops / Push Center has a real sent external effect and Push Center
  reconciliation, but independent governance records are still missing, so it
  remains `EVIDENCE_COLLECTED`.
- WeCom Auth / Callback is still `BLOCKED_CONFIG_NOT_APPROVED` because the
  git-external WeCom config / approval window did not become effective enough
  to collect valid callback signature, auth record, internal event,
  idempotency, and permission-scope evidence.

## Scenario Matrix

| Scenario | Current Status | Evidence Summary | P1 Readiness Impact |
| --- | --- | --- | --- |
| External Orders | `EVIDENCE_COLLECTED / order_linked` | Valid-token path, order linkage, internal event consumers, customer read-model projection, admin visibility, and Push Center external effect evidence are collected. | Not a blocker for P1 frontend foundation. Keep displaying real order reconciliation and idempotency status. |
| Ops Plan -> Broadcast | `EVIDENCE_COLLECTED / Push Center pending` | Next-native `cloud_plan` approval generated `ops_plan.approved`, `broadcast_task_planner_consumer` succeeded, `broadcast_job:3644` was created, and Push Center shows the job as pending. | Not a blocker for P1 frontend foundation. UI must present downstream pending instead of implying send completion. |
| Group Ops / Push Center | `EVIDENCE_COLLECTED / sent / governance residual risk` | `external_effect_job:97` reached Push Center `sent`; the successful attempt executed the WeCom group message adapter with real external call evidence. Independent operator approval, receiver allowlist, and gray-window records are still not attached. | Not a blocker for frontend foundation, but pages must show governance/evidence incomplete state. |
| WeCom Auth / Callback | `BLOCKED_CONFIG_NOT_APPROVED / external-config exception` | Next routes are reachable and fail closed. Approved-window recollection still found WeCom env/config approval incomplete, so real auth/callback signature, callback-linked event, idempotency, and permission-scope evidence are missing. | Allowed as a P1 exception only if frontend shows `external-config-blocked` and does not pretend WeCom auth is complete. |

## Why This Is Not PASS_90_PLUS

Global `PASS_90_PLUS` is not allowed under the closeout rules in
`docs/reports/business_closure_90_plus_evidence_closeout.md` and
`docs/runbooks/operator_business_closure_evidence_collection.md`.

Blocking or incomplete evidence remains:

- Group Ops lacks independent operator approval evidence.
- Group Ops lacks independent receiver allowlist evidence.
- Group Ops lacks independent gray-window approval evidence.
- WeCom lacks real operator auth evidence.
- WeCom lacks valid callback signature evidence.
- WeCom lacks callback-linked auth/callback record or internal event evidence.
- WeCom lacks idempotency and duplicate callback handling evidence.
- WeCom lacks permission-scope evidence.
- Ops Plan -> Broadcast has only reached Push Center pending; the downstream
  external effect worker was not executed in this evidence window.

Therefore the final classification is `P1_READY_WITH_EXCEPTIONS`, not
`PASS_90_PLUS`.

## Why P1 Can Start With Exceptions

P1 TypeScript Frontend Foundation can start because the remaining gaps are not
frontend-foundation code prerequisites.

The following foundations are complete or sufficiently evidenced for P1:

- P0 architecture gates are complete and must remain in CI.
- External effects, DB/session, background job contract, route ownership, and
  architecture/import boundaries are already enforced.
- External Orders has production evidence for order linkage, internal event
  consumers, Push Center visibility, and customer projection.
- Ops Plan -> Broadcast has Next-native planner evidence through broadcast job
  creation and Push Center pending state.
- Group Ops / Push Center has a real sent external effect and an explainable
  Push Center reconciliation.
- WeCom routes fail closed when external configuration is unavailable.

The remaining items are external configuration and governance evidence issues:

- WeCom requires an approved git-external config / callback evidence window.
- Group Ops requires governance source records for approval, receiver allowlist,
  and gray-window authorization.
- Ops Plan downstream external-effect execution can be collected later if the
  business owner requires send-completion evidence beyond planner/job evidence.

These are valid P1 exceptions as long as P1 presents them truthfully.

## Residual Risks

### Group Ops Governance

Residual risk: a real Group Ops external effect was sent and reconciled, but the
separate governance records for operator approval, receiver allowlist, and
gray-window approval are not attached.

P1 tracking:

- Group Ops surfaces must show governance evidence incomplete.
- Operators must be able to distinguish "send succeeded" from "governance
  evidence complete".
- Final `PASS_90_PLUS` requires attaching or formally business-accepting these
  governance records.

### WeCom External Configuration

Residual risk: WeCom auth/callback is blocked by external configuration approval
and has no real valid-signature callback evidence yet.

P1 tracking:

- WeCom auth UI must show `external-config-blocked`.
- The UI must not display WeCom operator auth as complete.
- No frontend path may hardcode or bypass corp/app/callback secrets.
- A future approved config window must recollect auth/callback evidence.

### Ops Plan Downstream Execution

Residual risk: Ops Plan -> Broadcast proved the Next-native planner path through
`broadcast_job:3644` and Push Center pending, but did not execute downstream
external-effect work in this evidence window.

P1 tracking:

- Ops Plan / Push Center surfaces must show pending/downstream status as
  pending, not sent.
- If the business owner requires send-completion evidence, run a separate
  approved downstream worker evidence window.

## P1 Entry Guardrails

P1 may start only under these guardrails:

- Do not modify or weaken P0 architecture gates.
- Do not bypass the external effects boundary.
- Do not bypass DB/session boundary rules.
- Do not bypass Push Center for send/status explanation.
- Do not bypass approval, receiver allowlist, gray-window, token, or config
  gates.
- Do not hardcode unfinished WeCom config into the frontend.
- Do not introduce new unverified real external call capability.
- P1 should focus on TypeScript/frontend foundation, page shells, data binding,
  and truthful status presentation.
- WeCom frontend states must show `external-config-blocked` until the approved
  callback evidence exists.
- Group Ops pages must be able to show `governance_missing` or
  `evidence_incomplete` alongside real send status.
- Ops Plan pages must show Push Center pending/downstream pending when the
  downstream external effect has not run.

## P1 Non-Goals

- Do not use P1 to add WeCom secrets, corp config, callback tokens, or AES keys.
- Do not use P1 to enable new real external calls.
- Do not use P1 to bypass Push Center reconciliation.
- Do not use P1 to bypass external-effect approval, receiver allowlist, gray
  window, token, or config gates.
- Do not use P1 to claim global `PASS_90_PLUS`.

## Required Follow-Up After P1 Starts

| Follow-Up | Owner / Boundary | Required Evidence |
| --- | --- | --- |
| WeCom approved config window and callback recollection | WeCom operator + platform boundary | Real auth start, valid callback signature, persisted auth/callback record or internal event, idempotency, duplicate handling, permission scope, admin visibility. |
| Group Ops governance source record attachment | Group Ops operator + governance boundary | Independent operator approval reference, receiver allowlist source, receiver membership confirmation, gray-window source and time range. |
| Ops Plan downstream external-effect worker evidence, if required | Ops Plan / Push Center operator | Broadcast job downstream worker result, external effect job if created, Push Center sent/failed/pending reconciliation. |
| Final Business Closure 90%+ re-closeout | Business owner + platform foundation | All four chains have complete redacted evidence, no blocking reasons, and closeout summary can show `can_claim_90_plus=true`. |

## Sensitive-Data Redaction Confirmation

This report references only internal ids, redacted ids, route names, status
labels, and evidence document paths. It does not include:

- token
- secret
- `Authorization` header
- raw `external_userid`
- receiver plaintext
- phone number
- openid/unionid
- raw target list
- raw callback body
- customer-private request/response body

## Risk / Rollback

This PR is document-only.

Rollback path: revert this report. There is no runtime rollback, no data
rollback, and no deployment rollback.

## Next Action

Start P1 TypeScript Frontend Foundation with the guardrails above.

Track the remaining exceptions in parallel:

1. WeCom approved config window + callback evidence recollection.
2. Group Ops governance source record attachment.
3. Ops Plan downstream external-effect worker evidence, if later required.
4. Final `PASS_90_PLUS` only after exceptions are closed or explicitly accepted
   by the business owner.

Frontend Skill Checklist: not applicable. This PR is a document-only final
closeout report and does not implement frontend pages, components, UI, or admin
console behavior.
