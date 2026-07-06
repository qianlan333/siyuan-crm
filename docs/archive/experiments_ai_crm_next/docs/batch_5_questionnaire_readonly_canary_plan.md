# Batch 5 Questionnaire Readonly Canary Plan

This plan prepares a staging or production-like canary for Batch 5 Questionnaire admin/public readonly. It does not switch production routes, execute real submit, run real OAuth, mutate WeCom tags, send external webhooks, or modify production proxy/deploy configuration.

## Summary

| field | value |
| --- | --- |
| batch name | `questionnaire_readonly` |
| production rollout | not approved |
| admin writes | excluded |
| H5 submit | excluded by default |
| OAuth / WeCom tag / webhook | fake / disabled |
| accepted legacy drift | old non-WeChat public API may return `403 please_open_in_wechat`; old result page route differs from Next JSON result API |

## Execution Mode Options

| mode | allowed use | notes |
| --- | --- | --- |
| `staging_simulated` | AI-CRM Next TestClient plus old Flask GET-only smoke evidence | No route owner changes. |
| `staging_proxy` | Staging proxy/router only | Requires rollback owner and staging operator signoff. |
| `header_allowlist` | One operator/session in staging | Route only requests with canary header. |
| `cookie_allowlist` | One operator/session in staging | Route only requests with canary cookie. |

## Included Readonly Routes

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
- `GET /s/{slug}/result/{result_token}` only as legacy result page evidence when needed; Next canary contract remains the JSON result API.

## Excluded Operations

- admin create/update/delete/enable/disable
- H5 submit
- OAuth start/callback
- external push / retry
- webhook
- WeCom tag
- old system writes
- production route cutover

## Entry Criteria

| criterion | required evidence |
| --- | --- |
| ordinary pytest pass | `.venv/bin/python -m pytest -q` |
| six parity pass | all `tools/compare_*_parity.py` reports |
| Questionnaire parity pass | `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md` |
| Questionnaire readonly gray smoke pass | `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md --old-base-url ... --next-testclient` |
| Questionnaire readonly dual mode pass | dual smoke has only accepted legacy drift |
| real PostgreSQL integration evidence available | `docs/archive/experiments_ai_crm_next/docs/real_postgres_integration_run.md` |
| PNG screenshot baseline pass | `historical removed reference (route_status.json)` includes Questionnaire admin/public routes |
| no old production entrypoint dirty | `git status --short --untracked-files=all` review |
| no production config modified | deploy/production config status scan and side-effect report |
| accepted legacy drift documented | old non-WeChat `403 please_open_in_wechat`; old result route differs from Next JSON route |

## Exit Criteria

- admin readonly routes return 200
- public page route returns 200
- public API route returns 200 on Next; old non-WeChat 403 is accepted only as legacy WeChat gate drift
- public result JSON route returns 200 on Next; old missing JSON route is accepted only as legacy route drift
- forbidden placeholders remain absent through frontend screenshot baseline
- side-effect safety flags are all false
- rollback dry-run is verified
- signoff draft is complete
- no write, submit, OAuth, tag, or webhook route appears in default canary route results

## No-Go Conditions

- any admin write route executed
- any submit executed against old service
- any real OAuth executed
- any WeCom tag write executed
- any external webhook executed
- production config modified
- old service write endpoint called
- smoke blocker
- parity blocker
- missing rollback owner
- fake submit appears in default canary smoke

## Readiness Command

```bash
# Historical command retired; see docs/archive/experiments_ai_crm_next/retired_tools.md
```

## Conclusion

Batch 5 readiness can only reach `canary_plan_ready` or `staging_simulated_canary_pass`. It is not `production_ready` and does not approve admin writes, submit, real OAuth, WeCom tag mutation, external webhook calls, or production route cutover.
