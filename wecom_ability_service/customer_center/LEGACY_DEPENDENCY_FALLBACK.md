# Legacy Dependency Fallback

`wecom_ability_service/customer_center/` no longer owns legacy Flask Customer Read Model HTTP routes after D3.

AI-CRM Next owns the readonly customer list and detail routes by default. This package is retained only because non-D3 legacy fallback code still imports read-model helpers for admin profile, automation context, MCP dispatch, and rollback/reference paths.

Do not add new business features here. New customer readonly behavior must go through `aicrm_next/customer_read_model`.

