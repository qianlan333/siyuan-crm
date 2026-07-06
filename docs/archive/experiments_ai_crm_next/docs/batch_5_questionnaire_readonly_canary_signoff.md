# Batch 5 Questionnaire Readonly Canary Signoff Draft

This signoff draft is based on `docs/archive/experiments_ai_crm_next/docs/gray_release_signoff_template.md`. It records staging-simulated evidence only and does not approve production rollout.

| field | value |
| --- | --- |
| batch name | `questionnaire_readonly` |
| operator | Codex |
| timestamp | 2026-05-20 20:32:00 CST |
| git commit | `d48082a` |
| old service version | local old Flask GET-only target when available |
| next service version | AI-CRM Next TestClient |
| database target | fixture/in-memory TestClient data plus old local test DB GET-only comparison |
| external adapters mode | fake / disabled |
| canary mode | `staging_simulated_canary` |
| staging proxy | not available / not used |
| smoke result | `/tmp/questionnaire_readonly_gray_smoke_batch_5.json` |
| parity result | `/tmp/questionnaire_parity_batch_5.json` |
| readonly dual-run result | Questionnaire readonly gray smoke dual report |
| readiness result | `/tmp/batch_5_questionnaire_canary_readiness.json` |
| legacy drift accepted | old non-WeChat `403 please_open_in_wechat`; old result route differs from Next JSON result API |
| screenshot baseline link | `historical removed reference (route_status.json)` |
| rollback owner | old Flask |
| rollback instruction | `AICRM_NEXT_ROUTE_QUESTIONNAIRE_READONLY=false` |
| rollback status | dry-run only; no real route changed |
| go/no-go decision | GO for staging-simulated canary evidence |
| signoff status | `staging_simulated_only` |

## Risk Acceptance

Accepted for staging-simulated evidence:

- No production proxy or deployment config is modified.
- No production traffic is switched.
- No old-system write endpoint is executed.
- No admin create/update/delete/enable/disable route is executed.
- H5 submit is not executed.
- Real OAuth is not executed.
- WeCom tag mutation is not executed.
- External webhook push/retry is not executed.
- Old non-WeChat public API gate is accepted only as legacy drift.
- Old result route difference is accepted only when Next satisfies the JSON result contract.

Not accepted:

- Production rollout.
- Production Nginx/app route changes.
- Admin write route cutover.
- Submit route cutover.
- Real OAuth enablement.
- Real WeCom tag mutation.
- Real external webhook push/retry.

## Required Human Signoff Before Real Staging Proxy Canary

| role | signoff |
| --- | --- |
| release owner | pending |
| product owner | pending |
| rollback owner | pending |
| staging operator | pending |

## Next Action

Execute the same Batch 5 GET-only canary against a real staging proxy or staging base URL, then update this signoff with real staging route-owner and rollback evidence.
