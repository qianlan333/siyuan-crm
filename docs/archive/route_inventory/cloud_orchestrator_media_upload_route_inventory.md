# Cloud Orchestrator Media Upload Route Inventory

Scope: Legacy Exit group 17 locks `POST /api/admin/cloud-orchestrator/media/upload` and `OPTIONS /api/admin/cloud-orchestrator/media/upload` to the Next adapter. The route keeps the legacy `media_id` upload contract for Cloud Orchestrator step editing and operational SOP scripts. `POST` performs the intended real WeCom temporary image media upload through the approved WeCom client gateway. It does not execute campaign send, run-due, Sidebar material send, payment, or automation runtime.

Route precedence:

- `aicrm_next.main.create_app()` registers `cloud_orchestrator_router` before `production compatibility router`.
- `aicrm_next.cloud_orchestrator.api` owns the exact media upload route.
- `aicrm_next.production_compat.api` no longer registers `/api/admin/cloud-orchestrator/media/upload`; production_compat rollback is removed for this exact route.
- `historical removed reference (test_cloud_orchestrator_media_upload_route_precedence.py)` and `historical removed reference (test_production_route_resolution.py)` prove POST/OPTIONS resolve to `aicrm_next.cloud_orchestrator.api`, not `aicrm_next.production_compat.api`.

Adapter and side-effect boundary:

- The Next route accepts multipart field `image` and validates missing image, empty image, and non-image content types.
- The response keeps legacy fields `ok`, `media_id`, `file_name`, `content_type`, and `size`.
- The response also includes `command_id`, `source_status=next_cloud_orchestrator_media_upload`, `route_owner=ai_crm_next`, `fallback_used=false`, `adapter_mode`, `real_external_call_executed=true`, `wecom_media_upload_executed=true`, and `side_effect_plan`.
- Default production adapter mode is `production`. Local/fake mode may still return a deterministic fake WeCom media id for tests and offline development.
- The adapter path uses the approved WeCom client gateway boundary. It does not import `WeComClient.from_app` directly, call `requests` / `httpx`, or touch `access_token` in the Cloud Orchestrator module.

## Frontend ↔ API ↔ Backend Contract Matrix

| 页面入口 | 前端模板/JS | 动作 | API | Method | Payload | Handler | Adapter/Command | SideEffectPlan | Smoke |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/admin/cloud-orchestrator/campaigns` | `aicrm_next/frontend_compat/templates/admin_console/cloud_campaigns_workspace.html` | Deprecated legacy campaign step image upload bridge; current inline editor primarily uses image library picker | `/api/admin/cloud-orchestrator/media/upload` | POST | multipart `image` | `api_cloud_orchestrator_media_upload` | `UploadCloudOrchestratorMediaCommand` | `wecom.media.upload`, `adapter_mode=production`, real WeCom image upload only | `tests/test_cloud_orchestrator_media_upload_frontend_contract.py` |
| `/admin/cloud-orchestrator/plans` | `aicrm_next/frontend_compat/templates/admin_console/cloud_plan_review.html`, `aicrm_next/frontend_compat/static/admin_console/cloud_plan_review.js` | Plan list/review page; message editor uses material picker/image library, not direct cloud upload | API-only/deprecated for this page | n/a | n/a | n/a | n/a | Page smoke verifies page remains 200 and route is not needed by plan list | `tests/test_cloud_orchestrator_media_upload_inventory.py` |
| `/admin/cloud-orchestrator/plans/{plan_id}` | `cloud_plan_review.html`, `cloud_plan_review.js`, `material_picker.js`, `send_content_composer.js` | Recipient message image/material editing via media library IDs | API-only/deprecated for this page | n/a | n/a | n/a | n/a | Material send/execute remains out of scope | `tests/test_cloud_orchestrator_media_upload_frontend_contract.py` |
| `cloud_campaigns_workspace.html` | legacy Flask template | Historical plan/step image upload button or external automation fast path | `/api/admin/cloud-orchestrator/media/upload` | POST | multipart `image` | `api_cloud_orchestrator_media_upload` | Next media adapter | returns real WeCom temporary image `media_id` | `tests/test_cloud_orchestrator_media_upload_adapter.py` |
| `cloud_plan_review.html` | Next frontend_compat template | No direct caller; material picker uses image/attachment/miniprogram libraries | API-only/deprecated | n/a | n/a | n/a | n/a | `tests/test_cloud_orchestrator_media_upload_frontend_contract.py` |
| API-only / operational fast path | scripts, SOP, old browser callers | Upload local selected image and write returned `media_id` into a step | `/api/admin/cloud-orchestrator/media/upload` | POST | multipart `image` | `api_cloud_orchestrator_media_upload` | `UploadCloudOrchestratorMediaCommand` | `real_external_call_executed=true`, `wecom_media_upload_executed=true` | curl smoke |
| Diagnostics/preflight | API-only | Confirm route owner and no legacy forward | `/api/admin/cloud-orchestrator/media/upload` | OPTIONS | none | `api_cloud_orchestrator_media_upload_options` | diagnostics payload | no side effect | `tests/test_cloud_orchestrator_media_upload_adapter.py` |

## Deletion Closeout Status Matrix

| 页面入口 | 前端模板/JS | 动作 | API | Handler | Adapter/Command | SideEffectPlan | closeout 状态 | Smoke |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/admin/cloud-orchestrator/campaigns` | `aicrm_next/frontend_compat/templates/admin_console/cloud_campaigns_workspace.html` | 页面仍可打开；cloud upload 是 deprecated / API-only / legacy bridge caller | `/api/admin/cloud-orchestrator/media/upload` | `api_cloud_orchestrator_media_upload` | `UploadCloudOrchestratorMediaCommand` | `wecom.media.upload`, `adapter_mode=production`, real WeCom image upload only | Next adapter only; production_compat rollback removed | page smoke + valid upload smoke |
| `/admin/cloud-orchestrator/plans` | `cloud_plan_review.html`, `cloud_plan_review.js`, `material_picker.js` | 当前计划页走 Media Library picker，不直接使用 cloud upload | API-only/deprecated for this page | n/a | n/a | n/a | No page button calls deleted legacy route | page smoke |
| `/admin/cloud-orchestrator/plans/{plan_id}` | `cloud_plan_review.html`, `cloud_plan_review.js`, `material_picker.js`, `send_content_composer.js` | 当前计划明细/recipient message material editing 走 Media Library IDs | API-only/deprecated for this page | n/a | n/a | n/a | No page button calls deleted legacy route | page/detail contract tests |
| `/api/admin/cloud-orchestrator/media/upload` | API-only / old browser callers / SOP scripts | Upload image and get legacy-compatible `media_id` | `/api/admin/cloud-orchestrator/media/upload` | `api_cloud_orchestrator_media_upload` | `UploadCloudOrchestratorMediaCommand` | `real_external_call_executed=true`, `wecom_media_upload_executed=true` | `deletion_locked`, `legacy_fallback_allowed=false`, production_compat rollback removed | valid, missing image, invalid content type, OPTIONS smoke |

## Out Of Scope

- Cloud Orchestrator campaign execute and run-due.
- Sidebar material real send.
- Media Library rollback.
- Payment, storage, OpenClaw, and automation runtime.
