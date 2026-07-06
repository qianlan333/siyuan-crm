# Gray Release Acceptance Checklist

This checklist must be completed for every route-level gray batch. It does not authorize production cutover by itself.

## Global Commands

```bash
.venv/bin/python -m pytest -q
```

Run all six parity tools:

```bash
# Historical command retired; see docs/archive/experiments_ai_crm_next/retired_tools.md
# Historical command retired; see docs/archive/experiments_ai_crm_next/retired_tools.md
# Historical command retired; see docs/archive/experiments_ai_crm_next/retired_tools.md
# Historical command retired; see docs/archive/experiments_ai_crm_next/retired_tools.md
# Historical command retired; see docs/archive/experiments_ai_crm_next/retired_tools.md
```

## Batch Commands

| batch | required smoke | required parity | dual-run |
| --- | --- | --- | --- |
| Batch 1 Media Library readonly | `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md --next-testclient` | Media parity | not required |
| Batch 2 Product Management readonly | `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md --next-testclient` | Commerce parity | not required |
| Batch 3 Customer Read Model readonly | `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md --next-testclient` | Customer parity | old-base-url dual required before full gray |
| Batch 4 User Ops readonly | `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md --next-testclient` | User Ops parity | old-base-url dual required before full gray |
| Batch 5 Questionnaire readonly | `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md --next-testclient` | Questionnaire parity | old-base-url dual recommended; accepted legacy drift allowed |
| Batch 6 Automation readonly | retired | retired | old automation_program/runtime-v2 parity and smoke tooling removed; `/admin/automation-conversion` is AI Audience |

## Frontend Screenshot Route Check

Confirm `docs/archive/experiments_ai_crm_next/docs/frontend_screenshot_baseline.md` includes the selected batch page routes and the latest route status remains `200`.

## Safety Checks

- no old write endpoint executed
- no real WeCom call
- no real OAuth call
- no real payment call
- no real OpenClaw call
- no real cloud storage upload
- no external webhook call
- rollback owner recorded
- rollback command reviewed
- signoff template completed

## Batch 1 Local Rehearsal

Before any production-like route flag change, run:

```bash
# Historical command retired; see docs/archive/experiments_ai_crm_next/retired_tools.md
```

Required result:

- `recommendation=GO`
- `production_config_modified=false`
- `old_write_endpoints_executed=false`
- `cloud_storage_upload_executed=false`
- `wecom_media_upload_executed=false`
- `real_traffic_cutover_executed=false`

## Batch 1 Staging Canary Readiness

Before a staging or production-like canary signoff, run:

```bash
# Historical command retired; see docs/archive/experiments_ai_crm_next/retired_tools.md
```

Required result:

- `readiness_status=canary_plan_ready`
- `recommendation=GO_TO_STAGING_CANARY_SIGNOFF`
- included routes are all GET
- excluded routes include Media Library POST/PUT/DELETE routes
- rollback dry-run is present
- screenshot baseline includes the three Media pages
- production config modified is false
- cloud storage and WeCom media remain disabled

## No-Go

Stop the batch if any condition is true:

- selected smoke has blockers
- parity has blockers
- Next route returns 5xx
- excluded route appears in smoke route results
- side-effect safety flag indicates real external call or old write
- rollback owner is missing
- fake adapter is represented as production validation
