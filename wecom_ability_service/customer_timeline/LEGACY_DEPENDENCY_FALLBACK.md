# Legacy Dependency Fallback

`wecom_ability_service/customer_timeline/` no longer owns legacy Flask Customer Read Model timeline HTTP routes after D3.

AI-CRM Next owns the readonly timeline route by default. This package is retained only because non-D3 legacy fallback code still imports timeline helpers for automation context, MCP dispatch, and rollback/reference paths.

Do not add new business features here. New customer timeline behavior must go through `aicrm_next/customer_read_model`.

