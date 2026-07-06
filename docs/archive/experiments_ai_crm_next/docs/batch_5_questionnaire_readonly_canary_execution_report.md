# Batch 5 Questionnaire Readonly Canary Execution Report

This report records a staging-simulated canary execution for Batch 5 Questionnaire readonly. It is not a production rollout and did not modify production proxy, Nginx, deploy, or route configuration.

## Summary

| field | value |
| --- | --- |
| batch name | `questionnaire_readonly` |
| execution mode | `staging_simulated_canary` |
| operator | Codex |
| timestamp | 2026-05-20 20:32:00 CST |
| git commit | `d48082a` |
| old service target | `http://127.0.0.1:5001` GET-only when available |
| next target | AI-CRM Next TestClient |
| staging proxy target | not available / not used |
| database target | AI-CRM Next fixture/in-memory TestClient data plus old local test DB GET-only comparison |
| external adapters mode | fake / disabled |
| submit executed | no |
| real OAuth executed | no |
| WeCom tag executed | no |
| external webhook executed | no |
| production traffic cut | no |
| production config modified | no |

## Route Flags

Staging-only flag stance used for this simulated canary:

```bash
AICRM_NEXT_ROUTE_QUESTIONNAIRE_READONLY=true
AICRM_NEXT_ROUTE_QUESTIONNAIRE_WRITES=false
AICRM_NEXT_QUESTIONNAIRE_SUBMIT=false
AICRM_NEXT_QUESTIONNAIRE_OAUTH=false
AICRM_NEXT_EXTERNAL_WECOM_TAG=false
AICRM_NEXT_EXTERNAL_WEBHOOK=false
```

These flags were not written to production config and were not committed as a real `.env`.

## Included Routes

- `GET /admin/questionnaires`
- `GET /admin/questionnaires/ui`
- `GET /api/admin/questionnaires`
- `GET /api/admin/questionnaires/{questionnaire_id}`
- `GET /api/admin/questionnaires/preflight`
- `GET /api/admin/questionnaires/{questionnaire_id}/latest-submit-debug`
- `GET /api/admin/questionnaires/{questionnaire_id}/export`
- `GET /s/{slug}`
- `GET /api/h5/questionnaires/{slug}`
- `GET /api/h5/questionnaires/{slug}/result/{submission_id}`

## Excluded Routes

- `POST /api/admin/questionnaires`
- `PUT /api/admin/questionnaires/{questionnaire_id}`
- `POST /api/admin/questionnaires/{questionnaire_id}/disable`
- `POST /api/admin/questionnaires/{questionnaire_id}/enable`
- `DELETE /api/admin/questionnaires/{questionnaire_id}`
- `POST /api/h5/questionnaires/{slug}/submit`
- `GET /api/h5/wechat/oauth/start`
- `GET /api/h5/wechat/oauth/callback`
- external push / retry routes
- webhook routes
- WeCom tag writes
- old system writes

## Pre-Check Evidence

| check | report | result |
| --- | --- | --- |
| Questionnaire readonly gray smoke | `/tmp/questionnaire_readonly_gray_smoke_batch_5.json` | PASS with accepted legacy drift |
| Questionnaire parity | `/tmp/questionnaire_parity_batch_5.json` | PASS |
| readiness checker | `/tmp/batch_5_questionnaire_canary_readiness.json` | `canary_plan_ready` / `GO_TO_STAGING_CANARY_SIGNOFF` |
| screenshot baseline | `historical removed reference (route_status.json)` | Questionnaire admin/public routes present and passing |
| real PostgreSQL integration | `docs/archive/experiments_ai_crm_next/docs/real_postgres_integration_run.md` | evidence available |

## Canary Smoke Result

Command:

```bash
AICRM_NEXT_ROUTE_QUESTIONNAIRE_READONLY=true \
AICRM_NEXT_ROUTE_QUESTIONNAIRE_WRITES=false \
AICRM_NEXT_QUESTIONNAIRE_SUBMIT=false \
AICRM_NEXT_QUESTIONNAIRE_OAUTH=false \
AICRM_NEXT_EXTERNAL_WECOM_TAG=false \
AICRM_NEXT_EXTERNAL_WEBHOOK=false \
# Historical command retired; see docs/archive/experiments_ai_crm_next/retired_tools.md
```

Result: PASS with accepted legacy drift.

## Readonly Dual-Run Result

The Questionnaire readonly gray smoke dual mode is the Batch 5 dual evidence. It sends old Flask only GET requests and never sends submit, admin writes, OAuth callback, tag mutation, retry, or webhook routes.

## Legacy Drift

- old `/api/h5/questionnaires/{slug}` may return `403 please_open_in_wechat` outside WeChat; Next public read API satisfies the readonly contract.
- old result rendering uses `/s/{slug}/result/{result_token}` while Next exposes `/api/h5/questionnaires/{slug}/result/{submission_id}`; the old missing JSON route is accepted only when Next satisfies the result contract.

## Side-Effect Safety

| safety flag | result |
| --- | --- |
| `old_write_endpoints_executed` | false |
| `old_submit_executed` | false |
| `real_oauth_executed` | false |
| `wecom_tag_executed` | false |
| `external_webhook_executed` | false |
| `next_fake_submit_executed` | false |
| `production_config_modified` | false |
| `real_traffic_cutover_executed` | false |
| `default_endpoints_get_only` | true |

## Rollback Dry-Run

Rollback is simulated only because no real staging proxy route is changed.

- rollback instruction: `AICRM_NEXT_ROUTE_QUESTIONNAIRE_READONLY=false`
- owner after rollback: old Flask
- rollback verification: dry-run only
- production config modified: false
- real route changed: false

## Blockers

None.

## Warnings

- accepted legacy drift: old non-WeChat public API gate.
- accepted legacy drift: old result route differs from Next JSON result API.

## Skipped

- `fake_submit_not_requested`: expected for Batch 5 readonly.
- real staging proxy rollback: skipped because execution mode is `staging_simulated_canary`.

## Recommendation

GO for staging-simulated canary evidence.

This does not approve production rollout. A real staging proxy canary still requires operator signoff, staging route-owner confirmation, and rollback observation before any production canary.

## Signoff Status

`staging_simulated_only`

## Next Action

Run Batch 5 Questionnaire readonly canary against an actual staging proxy or staging base URL with the same GET-only route scope and rollback owner.
