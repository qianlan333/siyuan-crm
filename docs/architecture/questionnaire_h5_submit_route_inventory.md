# Questionnaire H5 Submit Route Inventory

Scope: Legacy Exit group 9 locks public H5 submit and client diagnostics writes to the Next CommandBus. This group removes the submit/diagnostics legacy rollback and does not handle OAuth/auth, payment, storage, OpenClaw, or automation runtime execution. When scoring derives questionnaire `final_tags`, the submit path must synchronously execute the real WeCom `/cgi-bin/externalcontact/mark_tag` call; local `contact_tags` rows are only a mirror after WeCom succeeds.

| route | method | current owner | expected owner | write type | identity source | external side effect risk | command name | side effect plan | replacement decision | delete decision | test coverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/api/h5/questionnaires/{slug}/submit` | `POST` | Next exact route; exact legacy rollback removed | `next_command` | form submission, answer validation, result calculation, identity binding payload, submission projection, synchronous WeCom tag apply | anonymous, `identity`, `respondent_identity`, top-level `external_userid` / `follow_user_userid` / `openid` / `unionid` / `mobile` | high / guarded | `questionnaire.h5.submit` | `questionnaire.h5.submit.side_effects`, `adapter_mode=real_mark_tag`; `tag_apply.status=succeeded` only after WeCom mark_tag succeeds; local `contact_tags` mirrors only after success | Next CommandBus only; legacy rollback removed | `deletion_locked` | `tests/test_questionnaire_h5_submit_commands.py`, `tests/test_questionnaire_h5_final_tags_real_wecom.py`, `tests/test_questionnaire_h5_external_push.py`, `tests/test_questionnaire_h5_submit_no_fixture_production.py` |
| `/api/h5/questionnaires/{slug}/client-diagnostics` | `POST` | Next exact route; exact legacy rollback removed | `next_command` | client error / environment diagnostic write | anonymous, `identity`, `respondent_identity` | low / guarded | `questionnaire.h5.client_diagnostics` | none; AuditLedger only | Next CommandBus/AuditLedger only; unresolved slug is recorded without external calls | `deletion_locked` | `tests/test_questionnaire_h5_client_diagnostics.py`, `historical removed reference (test_questionnaire_h5_submit_registry_lifecycle.py)` |

## A. H5 Submit

- Submit validates the questionnaire slug exists and is enabled.
- `answers` must be a JSON object and required answers are validated with the existing questionnaire domain rules.
- Identity may be anonymous or supplied with `external_userid`, `follow_user_userid`, `openid`, `unionid`, `mobile`, and `respondent_key`.
- Result calculation uses the existing score/tag rules and writes a local submission projection through the Next questionnaire repository in fixture mode.
- Production writes that cannot use a real Next submission model return controlled `production_unavailable`; fixture data is not used as production success.
- Response includes `ok`, `command_id`, `submission_id`, `questionnaire_id`, `slug`, `result`, `external_push`, `tag_apply`, `source_status=next_command`, `route_owner=ai_crm_next`, `fallback_used=false`, and `real_external_call_executed` based on whether configured questionnaire external push or WeCom tag apply made a real external call.
- `tag_apply.status=succeeded` requires `ProductionWeComAdapter.mark_external_contact_tags()` to return successfully from the real `/cgi-bin/externalcontact/mark_tag` request.
- `tag_apply.status=failed` is explicit for `missing_external_userid`, `owner_userid_missing`, `missing_wecom_config`, `tag_ids_missing`, `wecom_error_*`, and retryable `network_error`. Failed tag apply must not write the local `contact_tags` mirror.

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
| real WeCom tag mutation | In scope only for questionnaire `final_tags`; success means WeCom mark_tag succeeded, and local `contact_tags` is only a post-success mirror. |
| payment / storage / OpenClaw / automation runtime | Out of scope; no real runtime execution added. |
| admin read/write | Already deletion_locked; this group does not change the lock. |
