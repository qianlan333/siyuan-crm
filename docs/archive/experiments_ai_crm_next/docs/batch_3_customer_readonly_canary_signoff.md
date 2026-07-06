# Batch 3 Customer Read Model Readonly Canary Signoff Draft

This signoff draft is based on `docs/archive/experiments_ai_crm_next/docs/gray_release_signoff_template.md`. It records staging-simulated evidence only and does not approve production rollout.

| field | value |
| --- | --- |
| batch name | `customer_readonly` |
| operator | Codex |
| timestamp | 2026-05-20 19:40:00 CST |
| git commit | `d48082a` |
| old service version | local old Flask GET-only test target when available |
| next service version | AI-CRM Next TestClient |
| database target | fixture/in-memory TestClient data plus masked local old Flask test sample |
| external adapters mode | fake / disabled |
| canary mode | `staging_simulated_canary` |
| staging proxy | not available / not used |
| smoke result | `/tmp/customer_gray_smoke_batch_3.json` |
| parity result | `/tmp/customer_parity_batch_3.json` |
| readonly dual-run result | `/tmp/readonly_dual_run_batch_3_customer.json` |
| readiness result | `/tmp/batch_3_customer_canary_readiness.json` |
| screenshot baseline link | `historical removed reference (route_status.json)` |
| sample external_userid | `external_user_masked_001` |
| rollback owner | old Flask |
| rollback instruction | `AICRM_NEXT_ROUTE_CUSTOMER_READONLY=false` |
| rollback status | dry-run only; no real route changed |
| go/no-go decision | GO for staging-simulated canary evidence |
| signoff status | `staging_simulated_only` |

## Risk Acceptance

Accepted for staging-simulated evidence:

- No production proxy or deployment config is modified.
- No production traffic is switched.
- No production PostgreSQL is connected.
- No old-system write endpoint is executed.
- No customer write route is executed.
- No real WeCom contact sync is executed.
- No archive sync is executed.
- No tag refresh is executed.
- No real OpenClaw push or webhook is executed.
- Masked local sample data remains test-only evidence.

Not accepted:

- Production rollout.
- Production Nginx/app route changes.
- Production PostgreSQL use.
- Real WeCom/archive/tag/OpenClaw adapter enablement.
- Customer write-route cutover.
- Production data migration/backfill.

## Required Human Signoff Before Real Staging Proxy Canary

| role | signoff |
| --- | --- |
| release owner | pending |
| customer owner | pending |
| rollback owner | pending |
| staging operator | pending |

## Next Action

Execute the same Batch 3 GET-only canary against a real staging proxy or staging base URL, then update this signoff with real staging route-owner and rollback evidence.
