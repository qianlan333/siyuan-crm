# Route Inventory Archive

This directory stores route inventory files whose exact route rows are now
regenerated from `docs/architecture/route_ownership_manifest.yml` by
`tools/report_route_inventory_consolidation.py`.

Archived files remain reviewable closeout evidence. They are not the active
route ownership source, do not change router registration, and do not authorize
production traffic changes or external calls.

The archive currently includes manifest-derivable closeout evidence for sidebar,
cloud orchestrator, customer automation webhook tombstones, User Ops, and WeCom
tag live-mutation plan-only boundaries. Tests may still assert these archived
documents when the evidence is intentionally retained.
