# Questionnaire OAuth Route Inventory

Scope: Legacy Exit group 10 moved Questionnaire H5 OAuth/auth exact start/callback transport to the Next OAuth adapter, then locked the exact start/callback legacy rollback closed. This closeout does not delete OAuth/auth wildcard rollback, does not enable real OAuth by default, and does not handle real WeCom tag mutation, external push execution, payment, storage, OpenClaw, automation runtime, admin read/write, or H5 submit business rollback.

| route | method | current owner | expected owner | oauth step | identity/session effect | external side effect risk | adapter mode | replacement decision | delete decision | test coverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/api/h5/wechat/oauth/start` | `GET`, `OPTIONS` | Next exact route, legacy rollback removed | `next_adapter` | state generation, redirect construction, redirect allowlist | no session yet | medium / guarded | `fake` local/test, `real_blocked` production default | Next OAuth adapter only; no real OAuth by default | `deletion_locked` | `tests/test_questionnaire_oauth_start_adapter.py`, `tests/test_questionnaire_oauth_state_security.py`, `tests/test_questionnaire_oauth_no_real_external_calls.py` |
| `/api/h5/wechat/oauth/callback` | `GET`, `OPTIONS` | Next exact route, legacy rollback removed | `next_adapter` | code/state verification, fake/sandbox identity, replay protection, audit | signed identity session cookie | medium / guarded | `fake` local/test, `real_blocked` production default | Next OAuth adapter only; no real OAuth by default | `deletion_locked` | `tests/test_questionnaire_oauth_callback_adapter.py`, `tests/test_questionnaire_oauth_session_cookie.py`, `historical removed reference (test_questionnaire_oauth_registry_lifecycle.py)` |
| `/api/h5/wechat/oauth/{path:path}` | all | production compatibility wildcard | inventory only | unknown OAuth subpath | unknown | guarded | `real_blocked` | retained as wildcard rollback / unknown-surface inventory | `active` | `tests/test_questionnaire_oauth_inventory.py` |
| `/auth/wecom/{path:path}` | all | production compatibility wildcard | inventory only | admin/WeCom auth wildcard | legacy admin auth session | guarded | `real_blocked` | retained out of scope; not part of questionnaire H5 OAuth adapter replacement | `active` | `tests/test_questionnaire_oauth_inventory.py` |

## A. OAuth Start

- Builds a signed state with `slug`, redirect target, nonce, issued-at, expiry, and adapter mode.
- Enforces redirect allowlist. Relative `/...` targets are allowed; absolute redirects require `AICRM_QUESTIONNAIRE_OAUTH_REDIRECT_ALLOWLIST`.
- Default API mode returns JSON with `source_status=next_oauth_adapter`, `route_owner=ai_crm_next`, `fallback_used=false`, and `real_external_call_executed=false`.
- Browser mode is enabled with `response_mode=redirect` or `browser_redirect=1`. Successful fake/sandbox start returns `302` to the prepared callback URL; successful real-enabled start returns `302` to the WeChat authorize URL.
- In browser mode, `real_blocked` or adapter errors return a readable HTML page instead of exposing JSON/state to the user.
- Local/test defaults to `fake`; production defaults to `real_blocked`.

## B. OAuth Callback

- Verifies signed state, nonce, expiry, and replay status.
- Fake/sandbox modes create deterministic test identity without network calls.
- `real_blocked` records a controlled blocked result and does not exchange code with WeChat.
- Default API mode returns JSON, creates a signed `questionnaire_h5_identity` cookie on success, and records AuditLedger evidence.
- Browser mode is enabled with `response_mode=redirect`, `browser_redirect=1`, or the signed state field `browser_redirect=true`. Successful callback writes `questionnaire_h5_identity` on the `RedirectResponse` and returns to the signed redirect target such as `/s/{slug}`.
- Browser-mode callback errors return a readable HTML page with a return-to-questionnaire link. Error paths write diagnostics without logging sensitive tokens.

## C. Production Configuration

Real WeChat OAuth is still disabled by default. To enable the real browser authorization URL in production, configure all of:

- `AICRM_QUESTIONNAIRE_OAUTH_ADAPTER_MODE=real_enabled`
- `AICRM_QUESTIONNAIRE_OAUTH_ENABLE_REAL=1`
- `WECHAT_MP_APP_ID`
- `WECHAT_MP_APP_SECRET`
- `SECRET_KEY` or `AICRM_QUESTIONNAIRE_OAUTH_STATE_SECRET`

The existing public base URL settings (`AICRM_PUBLIC_BASE_URL`, `PUBLIC_BASE_URL`, `EXTERNAL_BASE_URL`, `APP_EXTERNAL_BASE_URL`, or `NEXT_PUBLIC_BASE_URL`) should point to the production HTTPS origin used by the WeChat callback. Without the explicit real-enabled gate, production remains `real_blocked`; browser users see the controlled HTML error page rather than raw adapter JSON.

## D. Wildcard / Out Of Scope

- `/api/h5/wechat/oauth/{path:path}` remains retained legacy rollback for unknown OAuth subpaths; exact start/callback are deletion_locked and do not use this rollback.
- `/auth/wecom/*` remains out of scope and is not deletion locked by this group.
- Real OAuth enablement requires explicit `AICRM_QUESTIONNAIRE_OAUTH_ADAPTER_MODE` plus `AICRM_QUESTIONNAIRE_OAUTH_ENABLE_REAL`; this PR does not enable it.
