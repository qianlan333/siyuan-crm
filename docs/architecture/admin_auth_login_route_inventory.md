# Admin Auth Login Route Inventory

## Scope

Legacy Exit group 26 replaces `/login` and `/logout` with Next-owned admin auth routes and removes their `production_compat` rollback.

`/auth/wecom/start` and `/auth/wecom/callback` remain out of scope for this group. They are already exact Next blocked responses and must not perform real WeCom token exchange by default.

## Frontend <-> API <-> Backend Contract Matrix

| Surface | Method | Frontend/template | Action | Handler | Backend/Auth Service | External side effect | Closeout status | Smoke |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/login` | GET | `admin_console/login.html` | Render Next login page with WeCom SSO links and break-glass slot | `aicrm_next.admin_auth.api.admin_login_page` | `login_context`, `safe_next_path`, signed-cookie session check | None; WeCom links point to `/auth/wecom/start` only | `legacy_fallback_allowed=false`, `deletion_locked`, `replacement_status=locked` | GET 200, non-empty, no compatibility facade |
| `/login` | POST | `admin_console/login.html` form `action="/login"` | Break-glass submit | `aicrm_next.admin_auth.api.admin_login_submit` | `authenticate_break_glass`, `sign_session` | None; password checked locally, no WeCom token exchange | `legacy_fallback_allowed=false`, `deletion_locked`, `replacement_status=locked` | Invalid credential controlled 401 page; success 302 safe next |
| `/login` | OPTIONS | API diagnostics | Preflight/diagnostics | `aicrm_next.admin_auth.api.admin_login_options` | `diagnostics_payload` | None | `legacy_fallback_allowed=false`, `deletion_locked`, `replacement_status=locked` | OPTIONS 200 Next JSON |
| `/logout` | GET | Admin/user initiated | Clear Next admin auth cookie and redirect | `aicrm_next.admin_auth.api.admin_logout` | `SESSION_COOKIE` deletion | None | `legacy_fallback_allowed=false`, `deletion_locked`, `replacement_status=locked` | 302 `/login`, cookie cleared |
| `/logout` | OPTIONS | API diagnostics | Preflight/diagnostics | `aicrm_next.admin_auth.api.admin_logout_options` | `diagnostics_payload` | None | `legacy_fallback_allowed=false`, `deletion_locked`, `replacement_status=locked` | OPTIONS 200 Next JSON |
| `/auth/wecom/start` link | GET/OPTIONS | Login page links | SSO start link only | Existing `aicrm_next.auth_wecom.api.auth_wecom_start` | Existing blocked exact response | Real WeCom authorize/token exchange blocked | Out of scope; keep current `deletion_locked` exact route | GET 503 controlled blocked |
| `/auth/wecom/callback` | GET/OPTIONS | WeCom SSO return path | SSO callback | Existing `aicrm_next.auth_wecom.api.auth_wecom_callback` | Existing blocked exact response | Real WeCom code/token exchange blocked | Out of scope; keep current `deletion_locked` exact route | Existing auth_wecom tests |

## Behavior Notes

- Already logged-in requests to `GET /login` redirect to a safe local `next` path or `/admin`.
- Unsafe `next` values such as `https://evil.example.com` are normalized to `/admin`.
- Missing or invalid break-glass credentials return a controlled login page error and do not 500.
- Break-glass success sets only the Next signed `aicrm_next_admin_session` cookie.
- No password is printed or echoed.
- `real_external_call_executed=false` and `wecom_token_exchange_executed=false` are exposed on route headers/diagnostics.

## Legacy Deletion Lock

- Removed `production_compat` decorators for `/login` and `/logout`.
- `scripts/check_no_new_legacy.py` blocks `/login` and `/logout` from returning to `production_compat`.
- Registry and manifest lock `/login` and `/logout` with `legacy_fallback_allowed=false`, `delete_status=deletion_locked`, and `replacement_status=locked`.

## Explicit Non-Goals

- Do not rebuild `/auth/wecom/start`.
- Do not rebuild `/auth/wecom/callback`.
- Do not enable real WeCom OAuth, token exchange, or access-token fetch by default.
- Do not change `/api/h5/wechat/oauth/*`.
- Do not change payment, checkout, order, product, `/p/*`, or `/pay/*` fallbacks.
