# Questionnaire H5 Submit Route Inventory

Scope: Legacy Exit group 9 locks public H5 submit and client diagnostics writes to the Next CommandBus. R09 keeps those route owners while making the questionnaire continuation durable: submission, answers, identity-resolution queue, and `questionnaire.submitted` outbox commit atomically. The request path never calls WeCom or a webhook and never directly creates an External Effect job. Internal Event consumers are the only automatic planners; local `contact_tags` rows are projected only after the WeCom External Effect succeeds.

| route | method | current owner | expected owner | write type | identity source | external side effect risk | command name | side effect plan | replacement decision | delete decision | test coverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/api/h5/questionnaires/{slug}/submit` | `POST` | Next exact route; exact legacy rollback removed | `next_command` | form submission, answer validation, result calculation, identity binding payload, submission/answers/identity-resolution queue plus transactional outbox | anonymous, `identity`, `respondent_identity`, top-level `external_userid` / `follow_user_userid` / `openid` / `unionid` / `mobile` | high / guarded | `questionnaire.h5.submit` | `questionnaire.h5.submit.side_effects`, `adapter_mode=durable_internal_event`; `questionnaire_tag_consumer` and `questionnaire_webhook_consumer` are the sole automatic External Effect planners; provider success is projected after worker execution | Next CommandBus only; legacy rollback removed | `deletion_locked` | `tests/test_questionnaire_h5_submit_commands.py`, `tests/test_questionnaire_h5_final_tags_real_wecom.py`, `tests/test_questionnaire_h5_external_push.py`, `tests/test_r09_questionnaire_transaction_postgres.py` |
| `/api/h5/questionnaires/{slug}/client-diagnostics` | `POST` | Next exact route; exact legacy rollback removed | `next_command` | client error / environment diagnostic write | anonymous, `identity`, `respondent_identity` | low / guarded | `questionnaire.h5.client_diagnostics` | none; AuditLedger only | Next CommandBus/AuditLedger only; unresolved slug is recorded without external calls | `deletion_locked` | `tests/test_questionnaire_h5_client_diagnostics.py`, `historical removed reference (test_questionnaire_h5_submit_registry_lifecycle.py)` |

## A. H5 Submit

- Submit validates the questionnaire slug exists and is enabled.
- `answers` must be a JSON object and required answers are validated with the existing questionnaire domain rules.
- Identity may be anonymous or supplied with `external_userid`, `follow_user_userid`, `openid`, `unionid`, `mobile`, and `respondent_key`.
- Result calculation uses the existing score/tag rules and writes the submission, answer snapshots, identity-resolution queue, and one `questionnaire.submitted` outbox in a caller-owned transaction.
- Production writes that cannot use a real Next submission model return controlled `production_unavailable`; fixture data is not used as production success.
- Response includes `ok`, `command_id`, `submission_id`, `questionnaire_id`, `slug`, `result`, `external_push`, `tag_apply`, `completion_target`, backward-compatible `redirect_url`, additive `completion_action`, optional `lead_qr`, `internal_event_id`/`internal_event_outbox_id`, `durable_continuation_queued`, `source_status=next_command`, `route_owner=ai_crm_next`, `fallback_used=false`, and `real_external_call_executed=false`.
- Completion precedence preserves historical questionnaire redirects: an existing H5, dynamic URL Link, or legacy native mini-program target wins over an anomalous simultaneous channel binding. A later operations save normalizes the configuration to one mode.
- `lead_qr` is projected only after a successful submission or when the existing identity mechanism recognizes a prior submission. Direct access to `/s/{slug}/submitted` without a recognized submission never exposes the QR URL.
- Channel deletion, disablement, invalid carrier, or missing QR asset degrades to `completion_action.type=default`; it does not fail or roll back the questionnaire submission.
- `tag_apply.status=queued` means only that the durable continuation exists. It does not claim that an External Effect job exists or that WeCom was called; the H5 response therefore reports `external_effect_job_status=not_planned`.
- `questionnaire_tag_consumer` reloads authoritative submission, identity, and tags and plans at most one WeCom External Effect. Missing canonical identity is retryable. `questionnaire_webhook_consumer` is the sole automatic webhook planner.
- WeCom 429 remains `failed_retryable`; an ambiguous timeout becomes `unknown_after_dispatch` and requires explicit duplicate-risk reconciliation. A successful provider attempt updates `contact_tags` using the same idempotency lineage. No failed or unconfirmed attempt may write the local projection.

## B. Diagnostics

- Diagnostics accepts client payloads even when the slug is unresolved and records `unresolved_slug=true`.
- Diagnostics records AuditLedger evidence and an in-memory diagnostics projection in local/test.
- Response includes `ok`, `command_id`, `diagnostic_id`, `source_status=next_command`, `route_owner=ai_crm_next`, `fallback_used=false`, `real_external_call_executed=false`.

## C. Out Of Scope

| surface | decision |
| --- | --- |
| `/api/h5/wechat/oauth/start` | Out of scope for group 9; handled by group 10 OAuth/auth Next adapter validation and not deletion_locked here. |
| `/api/h5/wechat/oauth/callback` | Out of scope for group 9; handled by group 10 OAuth/auth Next adapter validation and not deletion_locked here. |
| `/auth/wecom/*` | Out of scope; not deletion_locked by group 9 or group 10. |
| real WeCom tag mutation | In scope only behind the existing External Effect worker for questionnaire `final_tags`; H5 only queues the durable Internal Event. Success means the worker received a successful WeCom mark_tag result and completed the post-success `contact_tags` projection. |
| payment / storage / OpenClaw / automation runtime | Out of scope; no real runtime execution added. |
| admin read/write | Already deletion_locked; this group does not change the lock. |
