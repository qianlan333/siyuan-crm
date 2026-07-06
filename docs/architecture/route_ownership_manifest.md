# Route Ownership Manifest

`docs/architecture/route_ownership_manifest.yml` is the source of truth for AI-CRM
Next route ownership. The first baseline is generated from the current FastAPI
app and covers non-static `APIRoute` entries. Static mounts are intentionally
excluded from the required manifest and may be checked separately with
`--include-static` when needed.

## Required Fields

Each route entry must include:

- `path`
- `methods`
- `route_name`
- `capability_owner`
- `runtime_owner`
- `layer`
- `external_effects`
- `data_source`
- `requires_auth`
- `rollback`

`capability_owner` and `runtime_owner` must never be `unknown`. `runtime_owner`
is limited to `ai_crm_next`, `blocked`, or `retired`; `external_effects` is
limited to `none`, `fake_only`, `staging_disabled`, or
`real_requires_approval`.

## Update Flow

When adding or removing a route:

1. Implement the route in its owning AI-CRM Next context.
2. Add or update the matching manifest entry in
   `docs/architecture/route_ownership_manifest.yml`.
3. Set `capability_owner` to the business context that owns the route, not the
   file that happened to register it.
4. Set `external_effects=real_requires_approval` only for approved routes that
   can cause real external effects. Do not enable real WeCom, Payment, OAuth,
   OpenClaw, or MCP calls as part of manifest maintenance.
5. Run:

   ```bash
   .venv/bin/python tools/check_route_ownership_manifest.py
   .venv/bin/python -m pytest tests/test_route_ownership_manifest.py -q
   ```

## Rollback

This manifest and checker are guardrails only. If the checker blocks an urgent
rollback, remove the CI gate or revert the manifest/checker PR; no runtime route
behavior depends on this file.
