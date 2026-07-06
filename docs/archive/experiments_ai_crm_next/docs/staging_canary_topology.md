# Staging Canary Topology

This topology is for Batch 1 Media Library readonly staging or production-like rehearsal only. It does not switch production traffic, modify production Nginx, connect production databases, or enable real external providers.

## Environment Layers

| layer | role | required stance |
| --- | --- | --- |
| `old_flask_staging` | Legacy route owner and rollback target | Staging or local old Flask only; GET checks only. |
| `ai_crm_next_staging` | Candidate readonly owner for Batch 1 routes | AI-CRM Next staging HTTP server or TestClient for local checks. |
| `staging_proxy / route router` | Optional route selection layer | Staging-only header, cookie, or flag routing. Never production config in this repo. |
| `test PostgreSQL` | Optional staging data store | Local/test database only. No production PostgreSQL. |
| fake external adapters | Storage and WeCom media boundary | Cloud storage and WeCom media stay fake or disabled. |
| artifact storage | Evidence archive | Store reports, parity JSON, smoke JSON, signoff drafts, and screenshots. |

## Explicitly Forbidden

- production DB
- production WeCom
- production cloud storage
- production payment provider
- production OpenClaw webhook
- production Nginx or deployment config changes
- real route cutover
- old Flask write endpoints

## Recommended Topology

Use same host and different ports for the first staging rehearsal.

| component | local or staging target | notes |
| --- | --- | --- |
| old Flask | `127.0.0.1:5001` or staging equivalent | Rollback owner and optional GET-only comparison target. |
| AI-CRM Next | `127.0.0.1:8000` or TestClient for local | Candidate readonly route owner. |
| proxy/router | staging-only | Header/cookie/flag router only; not production Nginx. |

## Data Strategy

- Use masked fixture or staging data only.
- Do not use production customer, media, or contact data.
- Do not perform destructive writes.
- Keep Batch 1 readonly-only: page GETs and list GETs.
- Leave media create/update/delete and upload flows outside the canary.

## Observability

Record these signals for every staging canary attempt:

- route status for each included route
- media gray smoke result
- media parity result
- frontend screenshot baseline reference
- side-effect safety flags
- rollback flag and owner confirmation
- generated markdown/json reports
- human signoff and Go/No-Go decision

## Exit Stance

Passing this topology review means the canary plan is ready for operator signoff. It does not mean production traffic has been cut or that real cloud/WeCom media adapters are ready.
