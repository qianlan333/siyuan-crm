# Batch 4 User Ops Readonly Canary Signoff Draft

This signoff draft is based on `docs/archive/experiments_ai_crm_next/docs/gray_release_signoff_template.md`. It records staging-simulated evidence only and does not approve production rollout.

| field | value |
| --- | --- |
| batch name | `user_ops_readonly` |
| operator | Codex |
| timestamp | 2026-05-20 20:08:00 CST |
| git commit | `d48082a` |
| old service version | local old Flask GET-only target when available |
| next service version | AI-CRM Next TestClient |
| database target | fixture/in-memory TestClient data plus old local test DB GET-only comparison |
| external adapters mode | fake / disabled |
| canary mode | `staging_simulated_canary` |
| staging proxy | not available / not used |
| smoke result | `/tmp/user_ops_readonly_gray_smoke_batch_4.json` |
| parity result | `/tmp/user_ops_parity_batch_4.json` |
| readonly dual-run result | `/tmp/readonly_dual_run_batch_4_user_ops.json` |
| readiness result | `/tmp/batch_4_user_ops_canary_readiness.json` |
| legacy drift accepted | old overview missing `激活待录入`; Next satisfies current 8-card contract |
| screenshot baseline link | `historical removed reference (route_status.json)` |
| rollback owner | old Flask |
| rollback instruction | `AICRM_NEXT_ROUTE_USER_OPS_READONLY=false` |
| rollback status | dry-run only; no real route changed |
| go/no-go decision | GO for staging-simulated canary evidence |
| signoff status | `staging_simulated_only` |

## Risk Acceptance

Accepted for staging-simulated evidence:

- No production proxy or deployment config is modified.
- No production traffic is switched.
- No old-system write endpoint is executed.
- No User Ops write route is executed.
- DND is not executed.
- Batch-send preview is not executed.
- Batch-send execute is not executed.
- Deferred jobs are not executed.
- Internal User Ops jobs are not executed.
- No real WeCom dispatch is executed.
- No real WeCom media upload is executed.
- Old overview missing `激活待录入` is accepted only because Next satisfies the current 8-card contract.

Not accepted:

- Production rollout.
- Production Nginx/app route changes.
- DND, batch-send, deferred job, or internal write-route cutover.
- Real WeCom dispatch or media-upload adapter enablement.
- Any Next overview regression that removes `激活待录入`.

## Required Human Signoff Before Real Staging Proxy Canary

| role | signoff |
| --- | --- |
| release owner | pending |
| product owner | pending |
| rollback owner | pending |
| staging operator | pending |

## Next Action

Execute the same Batch 4 GET-only canary against a real staging proxy or staging base URL, then update this signoff with real staging route-owner and rollback evidence.
