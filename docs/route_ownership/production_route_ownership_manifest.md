# Production Route Ownership Manifest

Status: final frozen. This document does not restore production compatibility
fallbacks, enable timers, or open real external calls.

The source of truth is
`docs/route_ownership/production_route_ownership_manifest.yaml`.

## Ownership Rules

- AI-CRM Next remains the default FastAPI modular monolith runtime.
- Production compatibility catch-all routes have been removed from runtime and
  must not be reintroduced without a new explicit gated adapter PR.
- Next exact routers own current exact route implementations.
- `frontend_compat` owns legacy admin page parity and must not add direct
  production SQL.
- Historical legacy facade notes are archived planning context, not active
  route ownership.
- Timer routes remain `scheduled_safe_mode`; this manifest does not approve
  enabling timers.
- External side-effect routes remain `real_blocked`, `guarded`, or fake adapter
  contracts. This manifest does not approve real WeCom, Payment, OAuth,
  OpenClaw, or MCP external calls.
- Fixture/local_contract/demo data is not allowed in production success paths.

## Required Fields

Each route family record includes:

- `route_pattern`
- `methods`
- `capability_owner`
- `current_runtime_owner`
- `production_behavior`
- `legacy_fallback_allowed`
- `fixture_allowed_in_production`
- `external_side_effect_risk`
- `delete_ready`
- `checker`
- `notes`

## Checker

Run:

```bash
.venv/bin/python tools/check_production_route_ownership_manifest.py \
  --output-md /tmp/production_route_ownership_manifest.md \
  --output-json /tmp/production_route_ownership_manifest.json
```

The checker imports the FastAPI app with final Legacy Exit guards enabled. It verifies:

- required route families match current app routes;
- production compatibility route count remains zero;
- legacy fallback route count remains zero;
- real external side-effect routes are not marked as real production behavior;
- `/admin/customers` and `/admin/questionnaires` are production readonly facade
  paths and do not allow fixture data in production;
- `/mcp` is owned by `aicrm_next.integration_gateway` and not by
  `openclaw_service`.
