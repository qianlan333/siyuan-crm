# Post-Legacy Cloud Orchestrator HTTP Handler Prune Inventory

Scope: Historical Handler Prune group 2 removes the Cloud Orchestrator legacy Flask HTTP handler family after Next runtime ownership is already frozen. This inventory covers HTTP handler modules only; `wecom_ability_service/domains/cloud_orchestrator/*` and `wecom_ability_service/domains/campaigns/*` remain available for domain compatibility tests.

## Reference Classification

| Reference class | Finding | Decision |
| --- | --- | --- |
| Next runtime import | No `aicrm_next` runtime file imports `wecom_ability_service.http.cloud_orchestrator_*` or `cloud_orchestrator_endpoint`. | No runtime fix required. |
| Legacy HTTP registry | `wecom_ability_service/http/__init__.py` imported `register_cloud_orchestrator_routes`, listed seven Cloud modules in `HTTP_ROUTE_MODULES`, described them in `HTTP_ROUTE_PLACEMENT`, and registered the aggregator. | Removed import, module records, placement records, and registrar. |
| Tests / monkeypatch | `tests/integration/test_pg_compat_smoke.py` monkeypatched `wecom_ability_service.http.cloud_orchestrator_campaigns`; `tests/test_http_registration_contract.py` expected legacy split route modules; `tests/test_campaign_hard_delete.py` used legacy Flask Cloud endpoints. | Migrated to Next API / Next command boundary and domain service tests. |
| Docs / inventory | Main prune inventory marked the Cloud handlers `keep_temporarily_historical`. | Updated each module to `deleted` with replacement and validation. |
| Old fallback app | Historical Flask app registered Cloud Orchestrator routes only through the legacy HTTP registry. | Registry no longer registers Cloud Orchestrator routes; production route resolution remains Next-owned. |

## Module Decisions

| legacy module / package | 原用途 | 替代 Next 模块 | 当前引用迁移 | 删除决策 | 测试 |
| --- | --- | --- | --- | --- | --- |
| `wecom_ability_service/http/cloud_orchestrator_endpoint.py` | legacy route aggregator for Cloud pages, plans, campaigns, segments, media | `aicrm_next.cloud_orchestrator.api` | Removed from `wecom_ability_service/http/__init__.py`; no runtime import remains. | `deleted` | `tests/test_http_registration_contract.py`, `tests/test_post_legacy_cloud_orchestrator_legacy_handlers_removed.py` |
| `wecom_ability_service/http/cloud_orchestrator_campaigns.py` | campaign list/detail/write/run-due HTTP handlers | `aicrm_next.cloud_orchestrator.api`, `campaigns_read`, `campaigns_write`, `run_due` | PG smoke monkeypatch migrated to Next `TestClient` batch-start command. | `deleted` | `tests/integration/test_pg_compat_smoke.py`, `tests/test_cloud_orchestrator_campaign_write_commands.py` |
| `wecom_ability_service/http/cloud_orchestrator_campaign_details.py` | campaign members and steps handlers | `aicrm_next.cloud_orchestrator.api`, `campaigns_read`, `campaigns_write` | Only imported by the retired aggregator. | `deleted` | `tests/test_cloud_orchestrator_campaigns_read_routes.py`, `tests/test_cloud_orchestrator_campaign_write_commands.py` |
| `wecom_ability_service/http/cloud_orchestrator_media.py` | media upload handler | `aicrm_next.cloud_orchestrator.api`, `aicrm_next.cloud_orchestrator.media_upload` | Next media upload adapter already owns POST/OPTIONS. | `deleted` | `tests/test_cloud_orchestrator_media_upload_adapter.py`, route precedence tests |
| `wecom_ability_service/http/cloud_orchestrator_pages.py` | admin Cloud pages | `aicrm_next.cloud_orchestrator.api` and current frontend templates | Page smoke and route resolution use Next routes. | `deleted` | `tests/test_post_legacy_admin_pages_smoke.py`, smoke |
| `wecom_ability_service/http/cloud_orchestrator_plans.py` | plan, audit, observability handlers | `aicrm_next.cloud_orchestrator.api` | Audit/observability are Next-owned by cloud_orchestrator after PR-11; plans remain Next-owned. | `deleted` | `tests/test_post_legacy_deferred_api_routes.py`, `tests/test_post_legacy_baseline_still_green.py` |
| `wecom_ability_service/http/cloud_orchestrator_segments.py` | segment list/detail/preview handlers | retained domain tests and Next ownership where applicable | Only imported by the retired aggregator. | `deleted` | `tests/test_http_registration_contract.py` |

## Retained Modules

None in the Cloud Orchestrator HTTP handler family. Domain/service modules are intentionally retained because they are not HTTP handlers and are still used by compatibility, approval token, campaign, and planning tests.

## Validation Contract

- `wecom_ability_service/http/__init__.py` must not mention `register_cloud_orchestrator_routes` or any `cloud_orchestrator_*` HTTP module.
- Deleted files must not exist.
- `aicrm_next` runtime must not import `wecom_ability_service.http.cloud_orchestrator*`.
- Representative routes must stay Next-owned:
  - `/admin/cloud-orchestrator/campaigns`
  - `/api/admin/cloud-orchestrator/campaigns`
  - `/api/admin/cloud-orchestrator/campaigns/run-due/preview`
  - `/api/admin/cloud-orchestrator/media/upload`
  - `/api/admin/cloud-orchestrator/observability`
- `production_compat_route_count`, `production_compat_catch_all_count`, `legacy_fallback_routes_count`, `unknown_owner_routes_count`, and `deleted_but_still_registered_count` must remain `0`.
