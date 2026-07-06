# Production Page Restore Investigation

Date: 2026-06-27
Timezone: Asia/Shanghai
Production host: 150.158.82.186
Public domain: https://www.youcangogogo.com

## Summary

2026-06-27 11:10-11:17 CST, AI-CRM production pages and the WeCom sidebar became
unresponsive because WeCom callback retry traffic saturated the only web
application runtime on `127.0.0.1:5001`.

The user-visible symptom was page/sidebar loading failure. The underlying
failure mode was not nginx, PostgreSQL, host CPU, or host memory exhaustion. The
single FastAPI/Uvicorn process was sharing normal page traffic and callback POST
traffic. When callback traffic reached roughly 900-1200 requests/minute, nginx
started seeing upstream resets, refused connections, client-side 499s, and page
timeouts.

Current recheck at 2026-06-27 15:49-15:56 CST shows the user-facing pages and
sidebar APIs have recovered. No additional restart was performed during this
recheck because the current service was healthy and a restart would introduce a
short new outage.

Follow-up public HTTP recheck at 2026-06-27 16:38 CST still shows the
user-facing page layer is available, but the permanent callback repair is not
deployed: `/admin/webhook-inbox` and the webhook inbox admin APIs return 404,
and an invalid callback POST still returns plain `success`.

Follow-up public HTTP recheck at 2026-06-27 17:53-17:56 CST confirms the same state,
and now checks both production callback URLs. `/health`, `/sidebar/bind-mobile`,
and `/admin/automation-conversion` are reachable, but `/admin/webhook-inbox`
and the webhook inbox JSON APIs still return 404. Invalid POST probes to both
`/wecom/external-contact/callback` and `/api/wecom/events` return HTTP 200 with
body `success`, so production is still in emergency quick ACK mode rather than
app-level verify/decrypt/enqueue mode.

Follow-up public HTTP recheck at 2026-06-27 18:12 CST confirms there is no
state change: user-facing pages remain available, `/admin/webhook-inbox` and
its JSON APIs still return 404, and both callback URLs still return nginx-level
plain `success` for invalid callback POSTs. A deploy-smoke run that used the
same public URL for both web and ingress was intentionally rejected because it
cannot prove `5001`/`5002` runtime isolation.

The recovery is still temporary. Production is protected by nginx-level quick
ACK rules that return `200 success` for WeCom callback POSTs before they reach
the app. This keeps pages alive, but callback events are not durably ingested or
processed while that rule is active.

## Current Recovery Status

Public probes:

| Check | Result |
| --- | --- |
| `GET /health` | HTTP 200, about 0.20s |
| `GET /sidebar/bind-mobile` | HTTP 200, about 0.10s |
| `GET /admin/automation-conversion` | HTTP 302, about 0.09s; expected unauthenticated redirect |
| `GET aicrm_next/frontend_compat/static/sidebar_workbench/sidebar_workbench.js` | HTTP 200 |
| `GET aicrm_next/frontend_compat/static/sidebar_workbench/sidebar_workbench.css` | HTTP 200 |

Follow-up public probes at 2026-06-27 16:38 CST:

| Check | Result |
| --- | --- |
| `GET /health` | HTTP 200 |
| `GET /sidebar/bind-mobile` | HTTP 200 |
| `GET /admin/automation-conversion` | HTTP 200 login page; route reachable |
| `GET /admin/webhook-inbox` | HTTP 404 |
| `GET /api/admin/webhook-inbox/metrics?provider=wecom&event_family=external_contact` | HTTP 404 |
| `GET /api/admin/webhook-inbox/items?provider=wecom&event_family=external_contact&limit=1` | HTTP 404 |
| `GET /api/admin/wecom/callback/reconciliation?limit=1` | HTTP 404 |
| invalid `POST /wecom/external-contact/callback?...` | HTTP 200 with body `success` |

Follow-up public probes at 2026-06-27 17:53-17:56 CST:

| Check | Result |
| --- | --- |
| `GET /health` | HTTP 200 |
| `GET /sidebar/bind-mobile` | HTTP 200 |
| `GET /admin/automation-conversion` | HTTP 200 login page; route reachable |
| `GET /admin/webhook-inbox` | HTTP 404 |
| `GET /api/admin/webhook-inbox/metrics?provider=wecom&event_family=external_contact` | HTTP 404 |
| `GET /api/admin/webhook-inbox/items?provider=wecom&event_family=external_contact&limit=1` | HTTP 404 |
| `GET /api/admin/webhook-inbox/0` | HTTP 404 |
| `GET /api/admin/wecom/callback/reconciliation?limit=1` | HTTP 404 |
| invalid `POST /wecom/external-contact/callback?...` | HTTP 200 with body `success` |
| invalid `POST /api/wecom/events?...` | HTTP 200 with body `success` |

Follow-up public probes at 2026-06-27 18:12 CST:

| Check | Result |
| --- | --- |
| `GET /health` | HTTP 200 |
| `GET /sidebar/bind-mobile` | HTTP 200 |
| `GET /admin/automation-conversion` | HTTP 200 login page; route reachable |
| `GET /admin/webhook-inbox` | HTTP 404 |
| `GET /api/admin/webhook-inbox/metrics?provider=wecom&event_family=external_contact` | HTTP 404 |
| `GET /api/admin/webhook-inbox/items?provider=wecom&event_family=external_contact&limit=1` | HTTP 404 |
| `GET /api/admin/webhook-inbox/0` | HTTP 404 |
| `GET /api/admin/wecom/callback/reconciliation?limit=1` | HTTP 404 |
| invalid `POST /wecom/external-contact/callback?...` | HTTP 200 with body `success` |
| invalid `POST /api/wecom/events?...` | HTTP 200 with body `success` |
| deploy smoke with identical public `--web-base-url` and `--ingress-base-url` | rejected; cannot prove `5001`/`5002` isolation |

The follow-up SSH password attempt did not authenticate, so this recheck did
not refresh host-local port, nginx file, or database schema evidence. The public
HTTP evidence is still enough to prove that the production callback route is not
yet in app-level verify/decrypt/enqueue mode.

Sidebar API probes with a real production `external_userid` from
`user_ops_lead_pool_current`:

| API | Result |
| --- | --- |
| `GET /api/sidebar/v2/workbench?external_userid=...` | HTTP 200, about 0.58s |
| `GET /api/sidebar/v2/questionnaires?external_userid=...` | HTTP 200, about 0.55s |
| `GET /api/sidebar/v2/products?external_userid=...` | HTTP 200, about 0.13s |
| `GET /api/sidebar/v2/orders?external_userid=...` | HTTP 200, about 0.35s |
| `GET /api/sidebar/v2/other-staff-messages?external_userid=...` | HTTP 200, about 0.11s |
| `GET /api/sidebar/contact-binding-status?external_userid=...` | HTTP 200, about 0.24s |
| `GET /api/sidebar/v2/materials?type=image&limit=50` | HTTP 200, about 0.79s |
| `GET /api/sidebar/v2/materials?type=mini&limit=50` | HTTP 200, about 0.15s |
| `GET /api/sidebar/v2/materials?type=pdf&limit=50` | HTTP 200, about 0.17s |

Host-local checks:

| Check | Result |
| --- | --- |
| `http://127.0.0.1:5001/health` | HTTP 200, about 0.003s |
| `openclaw-wecom-postgres.service` | active since 2026-06-27 11:17:17 CST |
| nginx | active |
| PostgreSQL | active |
| `127.0.0.1:5001` | listening |
| `127.0.0.1:5002` | absent |
| `webhook_inbox` table | missing in production database |
| `/admin/webhook-inbox` | HTTP 404 |

Near-current error logs:

- No nginx errors found for `2026/06/27 15:5x`.
- No application journal errors, exceptions, tracebacks, timeouts, or 5xx lines
  found since `2026-06-27 15:45:00`.

## Incident Evidence

During the failure window, nginx error logs showed callback upstream failures
and page timeouts:

| Error class | Count in sampled 11:10-11:17 window |
| --- | ---: |
| `recv() failed (104: Connection reset by peer)` | 119 |
| `connect() failed (111: Connection refused)` | 65 |
| `upstream timed out` | 2 |
| Total sampled nginx upstream errors | 186 |

The two sampled page timeouts were:

- `GET /admin/automation-conversion` at 2026-06-27 11:14:04 CST.
- `GET /admin/automation-conversion` at 2026-06-27 11:15:10 CST.

Callback POST traffic in the outage window:

| Minute CST | Callback POST count | Status evidence |
| --- | ---: | --- |
| 11:10 | 890 | 802 x 499, 88 x 502 |
| 11:11 | 672 | 82 x 200, 582 x 499, 8 x 502 |
| 11:12 | 1027 | 1027 x 499 |
| 11:13 | 1025 | 1025 x 499 |
| 11:14 | 1233 | 1233 x 499 |
| 11:15 | 1089 | 1089 x 499 |
| 11:16 | 1142 | 1142 x 499 |
| 11:17 | 955 | 514 x 200, 352 x 499, 88 x 502, 1 x 301 |

By contrast, in the 15:00 hour recheck window there were 26 callback POSTs and
all returned HTTP 200, because the nginx quick ACK rule was active.

## Current Temporary Mitigation

Production nginx has exact-location quick ACK rules:

```nginx
location = /wecom/external-contact/callback {
    default_type text/plain;
    if ($request_method = POST) {
        return 200 "success";
    }
    proxy_pass http://127.0.0.1:5001;
}

location = /api/wecom/events {
    default_type text/plain;
    if ($request_method = POST) {
        return 200 "success";
    }
    proxy_pass http://127.0.0.1:5001;
}
```

This is why pages are currently loading again: callback POSTs no longer consume
the single 5001 app runtime.

This is also why the current state is not a complete repair:

- Valid callback POSTs are acknowledged before decrypt/verify/ingest.
- No durable `webhook_inbox` row is created in production.
- No callback worker can process or retry the event.
- No `/admin/webhook-inbox` operations page exists in production.
- No isolated `127.0.0.1:5002` callback ingress runtime is deployed.

## Root Cause

The immediate root cause was callback retry storm saturation of a shared web
runtime.

The architectural root causes are:

1. Callback ingress and normal page/admin/sidebar traffic share the same
   `127.0.0.1:5001` process.
2. Callback POST handling is not isolated behind a tiny ingress process.
3. Production does not have durable `webhook_inbox` storage for raw inbound
   callbacks.
4. Production does not have a separate callback worker with retry/dead-letter
   semantics.
5. The only effective live protection is nginx quick ACK, which restores page
   availability at the cost of callback processing correctness.

## Why Sidebar And Pages Loaded Again

After the quick ACK mitigation, WeCom callback POSTs stopped reaching the app,
so normal web requests could use the 5001 runtime again. Current probes confirm:

- Sidebar HTML and static assets load.
- Sidebar business APIs return normal 200 responses with a real customer ID.
- Admin route responds with an expected auth redirect instead of timeout.
- Local app health responds immediately.
- Recent nginx and app logs are clean.

## Risk Assessment

Current user-facing availability risk is lower than during the 11:10-11:17
incident because the quick ACK rule is shielding the app.

Current data/business correctness risk remains high:

- WeCom callback events are being acknowledged but not durably recorded.
- Any automation depending on those callbacks may miss events.
- Removing the quick ACK before deploying the permanent ingress/inbox/worker
  design can recreate the page outage.
- Keeping the quick ACK indefinitely hides callback failures from operators.

## Recommended System Fix

Implement and cut over the permanent callback ingestion architecture:

1. Deploy `webhook_inbox` migration to production.
2. Deploy isolated callback ingress on `127.0.0.1:5002`.
3. Change nginx callback routes to proxy POSTs to 5002, not return quick ACK.
4. Make callback HTTP path only verify/decrypt/enqueue/ACK.
5. Return 400 for verify/decrypt failure.
6. Return 500/503 for enqueue/database failure; do not fake ACK.
7. Treat duplicate enqueue as HTTP 200 success.
8. Run separate callback inbox worker for processing/retry/dead-letter.
9. Keep real external calls behind `external_effect_job`, with gated realtime
   wakeup only after jobs are planned.
10. Deploy `/admin/webhook-inbox` for metrics, item detail, retry, skip,
    reconciliation, and replay-chain inspection.

## Production Acceptance Checklist

Do not remove the quick ACK or mark the permanent repair complete until these
checks pass in production:

| Area | Required proof |
| --- | --- |
| Runtime isolation | `5001` serves web/admin/sidebar; `5002` serves callback ingress; workers run separately |
| No quick ACK | nginx callback POST routes no longer contain `return 200 "success"` |
| Durable ingestion | Same-sample valid callback creates a `webhook_inbox` row |
| Correct ACK semantics | invalid signature/decrypt returns 400; enqueue failure returns 500/503; duplicate returns 200 |
| Worker processing | inbox row transitions through processing to succeeded or retry/dead-letter |
| Page isolation | `/health`, `/sidebar/bind-mobile`, and `/admin/automation-conversion` stay healthy under callback pressure |
| Backpressure | pressure test around 1200/min does not saturate 5001 |
| Operations | `/admin/webhook-inbox` shows metrics and can retry/skip/reconcile |
| Dual callback route cutover | both `/wecom/external-contact/callback` and `/api/wecom/events` reject invalid callback POSTs with app-level 4xx, not plain `success` |
| Rollback | rollback drill restores previous known-safe routing without page outage |

## Immediate Operator Guidance

For now:

- Leave the nginx quick ACK in place until the isolated ingress/inbox/worker
  stack is deployed and verified.
- Do not treat current callback HTTP 200s as proof of real business processing.
- If pages load slowly again, check nginx error log for upstream timeout/refused
  errors and `ss -ltnp` backlog on `127.0.0.1:5001`.
- If 5001 becomes unhealthy again while quick ACK is still active, then restart
  `openclaw-wecom-postgres.service` as a short-term page recovery action and
  preserve logs for analysis.
