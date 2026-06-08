# Legacy Frozen: wecom_ability_service

`wecom_ability_service/` is now a legacy fallback surface.

## Runtime Status

- Default runtime entry has moved to AI-CRM Next.
- `python3 app.py run` starts `aicrm_next.main:app`.
- Legacy Flask is available only through explicit fallback commands:
  - `python3 app.py run-legacy`
  - `python3 legacy_flask_app.py run`

## Allowed Changes

- Emergency rollback fixes.
- Data migration helpers needed before legacy retirement.
- External adapter reference work while the Next replacement remains under review.

## Disallowed Changes

- New business features.
- New default route ownership.
- New production cutover behavior.

New product work must land in `aicrm_next/`. Deletion of this directory requires the legacy delete batch process.
