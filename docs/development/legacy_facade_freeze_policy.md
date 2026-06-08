# Legacy Facade Growth Freeze Policy

Status: archived guardrail plus final closeout lock. `production_compat` and
`aicrm_next/integration_gateway/legacy_flask_facade.py` have been removed from
AI-CRM Next runtime. This policy remains as a historical freeze and regression
guard; it does not enable real external calls or change deploy/systemd/nginx
configuration.

## Positioning

`legacy_flask_facade` and `production_compat` are removed runtime boundaries.
Timer/run-due safety guard semantics are now owned by the Next-native
`aicrm_next.platform_foundation.internal_run_due_guard` module. Historical notes
may reference the former facade, but active runtime code must not import it or
restore legacy Flask forwarding.

New product work defaults to AI-CRM Next native modules under the modular
monolith. A legacy facade route must not be restored as a compatibility shortcut.

## Allowed Exceptions

Adding a legacy facade or `production_compat` route is not allowed. Historical
rollback or hotfix work must use a new, explicitly reviewed Next-native owner.
Any proposed exception requires all of these:

- It is a production hotfix, a rollback compatibility path, or a route whose
  real external side effect does not yet have a Next adapter.
- Production data is still stably served only by the legacy service.
- `docs/route_ownership/production_route_ownership_manifest.yaml` is updated in
  the same change.
- The route entry names the replacement owner, delete condition, and checker in
  notes or an adjacent route-ownership document.
- The route keeps `fixture_allowed_in_production: false` and does not mark real
  external calls as allowed.

## Forbidden

- Do not add direct `wecom_ability_service` or `openclaw_service` imports inside
  `aicrm_next`.
- Do not use `importlib` or string concatenation to bypass import checks for
  `wecom_ability_service`.
- Do not restore `production_compat` wildcard coverage.
- Do not add direct SQL in `aicrm_next/frontend_compat`.
- Do not treat fixture, local_contract, or demo data as production success data.

## Replacement Order

1. Replace read-only routes first.
2. Replace internal write routes second.
3. Replace external side-effect routes third.
4. Replace timer and automation execution routes last.

## Checker

Run:

```bash
python3 tools/check_legacy_facade_growth_freeze.py \
  --output-md /tmp/legacy_facade_growth_freeze.md \
  --output-json /tmp/legacy_facade_growth_freeze.json
```

The checker is static and deterministic. It enforces that the legacy import
boundary remains removed, blocks direct SQL in `frontend_compat`, verifies this
policy and route ownership documents exist, and rejects manifest entries that
allow production fixtures or real external side effects.

## Replacement Backlog

Phase 2 backlog is the planning source for page-shell migration and remaining
startup compatibility assessment. Before any route family replacement starts, the
backlog entry must name `replacement_owner`, `delete_condition`, and
`rollback_path`.

The backlog does not authorize runtime switching, fallback deletion, or real
external calls. For routes with `daily_business_critical: true`, replacement
work must use gray release, parity checks, and fallback retention so current
daily business usage is not interrupted.
