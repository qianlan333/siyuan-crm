# Issue #121 — Remove the Admin Read Model Reverse Import

## Objective

Delete the unused API-docs read-model compatibility chain that creates the `admin_read_model -> admin_config` reverse import, while preserving the real `/admin/api-docs` route and view model.

## Verified call graph

- `admin_read_model.projections.api_docs_payload` is referenced only by `GetAdminApiDocsPageQuery`.
- `GetAdminApiDocsPageQuery` is referenced only by `frontend_compat.admin_real_data.api_docs_payload`.
- The frontend compatibility wrapper has no callers.
- The active route calls `admin_config.api_docs_view_model.build_api_docs_view_model` directly.

## Implementation sequence

1. Add a failing import-graph assertion for the reverse edge.
2. Remove the dead projection, query class, import, and zero-call compatibility wrapper.
3. Tighten the graph budget from 194 to 193 edges and from 26 to 22 cyclic contexts.
4. Run API-docs page/view-model compatibility tests and all architecture gates.

## Safety and rollback

- No active route, template, API response, database state, or external effect changes.
- Revert this PR to restore the unused compatibility chain; no data rollback is needed.
