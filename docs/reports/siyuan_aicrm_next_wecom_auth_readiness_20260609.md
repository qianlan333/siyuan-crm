# siyuan AI-CRM Next WeCom Auth Readiness Report - 2026-06-09

## 1. 执行环境

- 执行入口：真实服务器普通 SSH shell。
- 执行目录：`/home/ubuntu/releases/siyuan-crm-aicrm-next-rehearsal-20260609`。
- 代码 commit：`ea0192b6`。
- PR #56：已包含，merge commit 为 `ea0192b6`。
- 基础检查：
  - `git status --short`：clean。
  - `bash -n scripts/siyuan_migration/*.sh scripts/siyuan_migration/lib_db_url.sh`：通过。
  - `scripts/siyuan_migration/test_lib_db_url.sh`：通过。
  - `python3 -m compileall app.py aicrm_next scripts`：通过。
- 本次未切生产。
- 本次未修改 systemd/nginx。
- 本次未对生产库执行 `DROP` / `CLEAN` / `pg_restore`。

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
| `AICRM_NEXT_WECOM_ADMIN_AUTH_MODE` | missing |
| `AICRM_NEXT_WECOM_ADMIN_AUTH_TIMEOUT_SECONDS` | missing |
| `AICRM_NEXT_ADMIN_SESSION_COOKIE_SECURE` | missing |

Additional checks:

- `AICRM_NEXT_WECOM_ADMIN_AUTH_MODE=live`：no。
- `ADMIN_LOGIN_REDIRECT_URI` path：confirmed as `/auth/wecom/callback` without recording the full URL。

## 3. Auth Smoke Result

Auth smoke was not executed because the production env does not yet set `AICRM_NEXT_WECOM_ADMIN_AUTH_MODE=live`.

Per the cutover readiness rule, if the mode is not `live`, the auth smoke must stop and record No-Go rather than temporarily forcing a production configuration.

| Check | Result | Notes |
| --- | --- | --- |
| `/auth/wecom/callback` missing code | not_run | Blocked by missing live mode config |
| `/auth/wecom/callback?code=dummy&state=dummy` | not_run | Blocked by missing live mode config |
| `/auth/wecom/start?mode=qr&next=/admin` | not_run | Blocked by missing live mode config |
| `/auth/wecom/start?mode=oauth&next=/admin` | not_run | Blocked by missing live mode config |
| Open redirect defense | not_run | Blocked by missing live mode config |
| `external_call_blocked` regression | not_verified | Requires live mode env and rerun |

## 4. Real WeCom Login Verification

- `real_wecom_login_test`：not_run。
- Reason：`AICRM_NEXT_WECOM_ADMIN_AUTH_MODE` is missing in the loaded production env, so live WeCom admin auth is not enabled.
- No real code, state, session cookie, userid, mobile, token, or secret was recorded.

## 5. Regression Result

Full endpoint regression was not executed after the auth-mode No-Go. The readiness session stopped before launching a temporary staging service, in order to avoid testing a configuration that would still be blocked in the next cutover window.

| Check | Result |
| --- | --- |
| `/health` | not_run |
| `/api/admin/user-ops/overview` | not_run |
| customer/sidebar smoke | not_run |
| channel diagnosis | not_run |
| core admin pages | not_run |

## 6. Conclusion

Current conclusion: **No-Go for the second production cutover window**.

Remaining blocker:

- Production env has not enabled AI-CRM Next WeCom admin auth live mode.
- Required action: authorized operator must update the production env so that `AICRM_NEXT_WECOM_ADMIN_AUTH_MODE=live` is present before rerunning readiness.

Recommended next readiness after env update:

```bash
curl -i "http://127.0.0.1:5001/auth/wecom/callback"
curl -i "http://127.0.0.1:5001/auth/wecom/callback?code=dummy&state=dummy"
curl -i "http://127.0.0.1:5001/auth/wecom/start?mode=qr&next=/admin"
curl -i "http://127.0.0.1:5001/auth/wecom/start?mode=oauth&next=/admin"
```

Expected results after live mode is configured:

- missing code returns 400.
- dummy code/state returns `400 invalid_or_expired_state`.
- QR/OAuth start returns 302 to WeCom authorize URL.
- No secret, code, state, token, session cookie, userid, external_userid, scene_value, unionid, openid, or mobile appears in logs or reports.

## 7. Security Statement

- No `.env`, dump, uploads, instance, pem/key file was committed.
- No full `DATABASE_URL` was printed or recorded.
- No database password, `WECOM_SECRET`, token, code, state, session cookie, AESKey, private key, raw userid, raw external_userid, raw scene_value, mobile, unionid, or openid was printed or recorded.
- No systemd/nginx change was made.
- No production cutover was performed.
- No production database destructive action was performed.
