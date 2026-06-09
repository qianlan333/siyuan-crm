# siyuan AI-CRM Next WeCom Auth Readiness After Env Enablement Rerun - 2026-06-09

## 1. 执行环境

- 执行入口：真实服务器普通 SSH shell。
- 执行目录：`/home/ubuntu/releases/siyuan-crm-aicrm-next-rehearsal-20260609`。
- 代码 commit：`0816f059`。
- PR #56：已包含。
- PR #57：已包含。
- `git fetch origin`：成功。
- `git pull --ff-only origin main`：成功。
- 临时 readiness 服务：`127.0.0.1:5101`，避免占用当前生产 systemd 服务监听的 `127.0.0.1:5001`。
- 本次未切生产。
- 本次未修改 systemd/nginx。
- 本次未对生产库执行 `DROP` / `CLEAN` / `pg_restore`。

基础检查：

| Check | Result |
| --- | --- |
| `git status --short` | clean |
| `bash -n scripts/siyuan_migration/*.sh scripts/siyuan_migration/lib_db_url.sh` | pass |
| `scripts/siyuan_migration/test_lib_db_url.sh` | pass |
| `python3 -m compileall app.py aicrm_next scripts` | pass |

## 2. Env Present / Missing

只检查存在性，未打印任何真实值。

| Key | Result |
| --- | --- |
| `SECRET_KEY` | present |
| `DATABASE_URL` | present |
| `WECOM_CORP_ID` | present |
| `WECOM_AGENT_ID` | present |
| `WECOM_SECRET` | present |
| `ADMIN_LOGIN_REDIRECT_URI` | present |
| `AICRM_NEXT_WECOM_ADMIN_AUTH_MODE` | present |
| `AICRM_NEXT_WECOM_ADMIN_AUTH_TIMEOUT_SECONDS` | present |
| `AICRM_NEXT_ADMIN_SESSION_COOKIE_SECURE` | present |

Additional checks:

- `AICRM_NEXT_WECOM_ADMIN_AUTH_MODE=live`：confirmed。
- `ADMIN_LOGIN_REDIRECT_URI` path：`/auth/wecom/callback`。
- 本机 HTTP readiness smoke 使用 `AICRM_NEXT_ADMIN_SESSION_COOKIE_SECURE=false` 覆盖，只用于临时 `127.0.0.1:5101` smoke；正式 HTTPS 生产访问仍应使用 secure cookie 策略。

## 3. Auth Smoke

全部 auth smoke 请求均指向临时 readiness 服务 `127.0.0.1:5101`。报告不记录完整 Location，不记录真实 state/code/cookie/token。

| Check | Result | Details |
| --- | --- | --- |
| `/auth/wecom/callback` missing code | pass | HTTP 400, `missing_wecom_code`, no cookie, no `external_call_blocked` |
| `/auth/wecom/callback?code=dummy&state=dummy` | pass | HTTP 400, `invalid_or_expired_state`, no cookie, no `external_call_blocked` |
| `/auth/wecom/start?mode=qr&next=/admin` | pass | HTTP 302, Location kind `wecom_qr_authorize`, no cookie, no `external_call_blocked` |
| `/auth/wecom/start?mode=oauth&next=/admin` | pass | HTTP 302, Location kind `wecom_oauth_authorize`, no cookie, no `external_call_blocked` |
| Open redirect defense | pass | HTTP 302 to WeCom QR authorize URL; unsafe external next path was not surfaced in the response body or report |

Result:

- `external_call_blocked` no longer appears in auth smoke responses.
- No WeCom secret, token, code, state, or session cookie was printed or recorded.

## 4. Real WeCom Login Verification

- `real_wecom_login_test`：not_run。
- Reason：本次由 SSH 执行本机 readiness smoke，未进行人工扫码/企业微信授权。
- Cutover implication：正式第二次生产切换窗口前或窗口内仍需人工验证真实企业微信后台登录可以进入 `/admin`，并确认刷新 `/admin` 不反复要求登录。
- No real code, state, session cookie, userid, mobile, token, or secret was recorded.

## 5. Regression Result

Initialization against target staging/new production DB:

| Check | Result |
| --- | --- |
| target DB connection | pass |
| `python3 app.py health` | pass |
| `python3 app.py init-db` | pass |
| `python3 app.py init-next-schema-safe` | pass |
| sample scene value | present, masked |
| sample external userid | present, masked |

Readiness and smoke:

| Check | Result |
| --- | --- |
| `10_cutover_readiness_check.sh` | pass, 0 failures |
| `/health` | pass, 200 |
| `/admin` | pass, 200 |
| `/admin/channels` | pass, 200 |
| `/admin/customers` | pass, 200 |
| `/admin/config` | pass, 200 |
| `/admin/api-docs` | pass, 200 |
| `/api/admin/user-ops/overview` | pass, 200 |
| Channel runtime diagnosis | pass, 200 |
| Customer detail | pass, 200 |
| Customer timeline | pass, 200 |
| Sidebar customer context | pass, 200 |
| Sidebar profile | pass, 200 |

Readiness warnings:

- `WECHAT_MP_APPID` missing. `WECHAT_MP_APP_ID` is present.
- `CRM_API_TOKEN` missing.
- `MCP_BEARER_TOKEN` missing.
- `SIDEBAR_THIRD_PARTY_API_TOKEN` missing.
- In the generic readiness script invocation, sample values were not passed, so it skipped channel/customer sample checks there. The dedicated smoke scripts did run with masked real sample values and passed.

## 6. Conclusion

Current conclusion: **Auth readiness passed for PR #56 blocker verification**.

The previous No-Go condition has been cleared at the smoke-test level:

- `AICRM_NEXT_WECOM_ADMIN_AUTH_MODE=live` is present.
- `ADMIN_LOGIN_REDIRECT_URI` path is `/auth/wecom/callback`.
- missing code returns 400, not 503.
- dummy code/state returns 400 invalid state, not 503.
- QR/OAuth start return 302 WeCom authorize responses.
- No `external_call_blocked` appeared in auth smoke.
- Core admin/user-ops/channel/customer/sidebar regression passed with no 5xx.

Recommendation:

- The project can enter second production cutover window planning/review.
- Formal Go still requires an authorized human to complete at least one real WeCom admin login verification before or during the cutover window, because real QR/OAuth authorization was not run in this SSH-only readiness session.

## 7. Security Statement

- No `.env`, dump, uploads, instance, pem/key file was committed.
- No full `DATABASE_URL` was printed or recorded.
- No database password, `WECOM_SECRET`, token, code, state, session cookie, AESKey, private key, raw userid, raw external_userid, raw scene_value, mobile, unionid, or openid was printed or recorded.
- No systemd/nginx change was made.
- No production cutover was performed.
- No production database destructive action was performed.
- Temporary readiness service was stopped after testing.
