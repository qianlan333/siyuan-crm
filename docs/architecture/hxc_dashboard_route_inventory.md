# HXC Dashboard Route Inventory

## Scope

HXC dashboard closeout replaces the production `production_compat` fallback for `/admin/hxc-dashboard`, `/admin/hxc-send-config`, and `/api/admin/hxc-dashboard*` with Next-owned routes.

The old Flask module remains only as historical reference. Runtime traffic for this route family must not call `forward_to_legacy_flask`, `refresh_hxc_dashboard_snapshot`, `sync_admin_wecom_directory_members`, or `broadcast_to_filtered_users`.

## Frontend <-> API <-> Backend Contract Matrix

| Surface | Method | Next owner | Frontend caller | Backend command/read model | Side effect policy | Legacy fallback |
| --- | --- | --- | --- | --- | --- | --- |
| `/admin/hxc-dashboard` | GET | `aicrm_next.hxc_dashboard.api` | Admin navigation and `/admin/user-ops` redirect | `dashboard_payload()` safe-mode read model | No external calls | `legacy_fallback_allowed=false`, `deletion_locked` |
| `/admin/hxc-send-config` | GET | `aicrm_next.hxc_dashboard.api` | Dashboard "发送人管理" link | `send_config_payload()` safe-mode read model | No external calls | `legacy_fallback_allowed=false`, `deletion_locked` |
| `/api/admin/hxc-dashboard` | GET | `aicrm_next.hxc_dashboard.api` | API readers and smoke checks | `dashboard_payload()` | `real_external_call_executed=false` | `legacy_fallback_allowed=false`, `deletion_locked` |
| `/api/admin/hxc-dashboard/refresh` | POST/OPTIONS | `aicrm_next.hxc_dashboard.api` | Manual refresh button | `PlanHxcDashboardRefreshCommand` | Creates blocked `SideEffectPlan` and blocked `ExternalCallAttempt`; `hxc_refresh_executed=false` | `legacy_fallback_allowed=false`, `deletion_locked` |
| `/api/admin/hxc-dashboard/refresh-directory` | POST/OPTIONS | `aicrm_next.hxc_dashboard.api` | Send-config page sync button | `PlanHxcDirectorySyncCommand` | Creates blocked `SideEffectPlan` and blocked `ExternalCallAttempt`; `directory_sync_executed=false`, `wecom_api_called=false` | `legacy_fallback_allowed=false`, `deletion_locked` |
| `/api/admin/hxc-dashboard/send-config` | GET | `aicrm_next.hxc_dashboard.api` | Send-config page load | `send_config_payload()` | Local safe-mode data only | `legacy_fallback_allowed=false`, `deletion_locked` |
| `/api/admin/hxc-dashboard/send-config` | POST/OPTIONS | `aicrm_next.hxc_dashboard.api` | Send-config save form | `UpsertHxcSendConfigCommand` | Local safe-mode config mutation only | `legacy_fallback_allowed=false`, `deletion_locked` |
| `/api/admin/hxc-dashboard/send-config/{sender_userid}` | DELETE/OPTIONS | `aicrm_next.hxc_dashboard.api` | Send-config delete button | `DeleteHxcSendConfigCommand` | Local safe-mode config mutation only | `legacy_fallback_allowed=false`, `deletion_locked` |
| `/api/admin/hxc-dashboard/broadcast` | POST/OPTIONS | `aicrm_next.hxc_dashboard.api` | Legacy callers only; dashboard UI uses `/broadcast-tasks` | `PlanHxcBroadcastCommand` | Creates blocked `SideEffectPlan` and blocked `ExternalCallAttempt`; `hxc_broadcast_executed=false`, `wecom_send_executed=false` | `legacy_fallback_allowed=false`, `deletion_locked` |
| `/api/admin/hxc-dashboard/broadcast-tasks` | POST | `aicrm_next.hxc_dashboard.api` | Dashboard composer | Existing Next-native broadcast task creation | Creates internal task/preview only; no legacy Flask fallback | Existing Next route remains unchanged |
| `/api/admin/hxc-dashboard/{unknown_path}` | GET/POST/OPTIONS | `aicrm_next.hxc_dashboard.api` | Unknown clients | Controlled 404 payload | No external calls | `legacy_fallback_allowed=false`, `deletion_locked` |

## Legacy Deletion Lock

- Removed exact `production_compat` fallback routes for `/admin/hxc-dashboard`, `/admin/hxc-send-config`, `/api/admin/hxc-dashboard`, and `/api/admin/hxc-dashboard/{path:path}`.
- Removed wildcard `production_compat` fallback routes for `/api/admin/hxc-dashboard` and `/api/admin/hxc-dashboard/{path:path}`.
- Route registry and production route ownership manifest set `legacy_fallback_allowed=false`, `delete_status=deletion_locked`, and `replacement_status=locked`.
- `scripts/check_no_new_legacy.py` blocks reintroducing HXC `production_compat` routes or direct calls to the legacy refresh, directory sync, or broadcast functions.

## Explicit Non-Goals

- No real HXC dashboard refresh.
- No real WeCom directory sync.
- No real HXC broadcast.
- No direct HTTP client, WeCom client, OpenClaw client, or access-token path in the Next HXC closeout routes.
- Login/logout, payment/product pages, and other production_compat surfaces are out of this closeout scope.
