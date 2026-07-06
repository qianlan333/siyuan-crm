# siyuan-crm sync to AI-CRM main - 2026-07-06

## 1. Executive Summary

Conclusion: BASELINE_SYNC_READY_FOR_REVIEW

- `siyuan-crm` product code has been refreshed from the current `AI-CRM` main baseline.
- Siyuan production and migration overlays are retained.
- No production host, DB, systemd, nginx, or env file was changed by this repository sync.
- Follow-up before production release: run restored-data staging rehearsal against a siyuan staging DB, then merge/deploy through the normal GitHub path.

## 2. Baselines

- AI-CRM main SHA: `7b80f7c0`
- siyuan-crm previous main SHA: `e0b35a2`
- compare date: `2026-07-06`

## 3. Synced From AI-CRM

- `aicrm_next/`
- `migrations/`
- `scripts/`
- `tools/`
- `tests/`
- `frontend/`
- `experiments/`
- `skills/`
- frontend package metadata: `package.json`, `package-lock.json`, `tsconfig.frontend.json`
- AI-CRM CI workflows except the siyuan deploy workflow
- AI-CRM top-level runtime/dev files such as `app.py`, `Makefile`, `pyproject.toml`, `requirements*.txt`, and `alembic.ini`
- AI-CRM docs are refreshed, with siyuan overlays restored afterwards

## 4. Retained Siyuan Overlays

- `.env.example`
- `README.md`
- `WW_verify_XDgKINYU8LF2JoSa.txt`
- `.github/workflows/deploy.yml`
- `deploy/`
- `scripts/siyuan_migration/`
- `docs/siyuan_aicrm_next_migration.md`
- `docs/external_orders_api.md`
- `docs/reports/*siyuan*`
- `docs/runbooks/siyuan_*`
- `docs/reports/templates/siyuan_aicrm_next_production_cutover_report_template.md`

## 5. Migration Safety Review

These AI-CRM production-data migrations remain siyuan-safe no-op overlays:

- `0032_miniprogram_only_resend_20260611`
- `0033_complete_miniprogram_only_resend_20260611`
- `0034_reset_miniprogram_only_material_jobs_20260611`

`0037_channel_multi_staff_assignment` is retained as a siyuan-only compatibility revision ID, but its body is now no-op. The generic channel assignment schema is provided by `0036_channel_multi_staff_assignment`, and later AI-CRM unionid cleanup migrations handle old `external_contact_id` shapes when present.

`0038_merge_duplicate_channel_wechat_shop_heads` keeps the siyuan-only `0037_channel_multi_staff_assignment` down revision so databases that already know that revision remain traversable.

No AI-CRM production campaign/member/order/product ID, `external_userid`, `scene_value`, `unionid`, `openid`, or mobile value is added by the siyuan overlay.

## 6. Safety / Non-goals

- No production deployment.
- No production DB write.
- No production systemd/nginx/env mutation.
- No real WeCom, payment, OAuth, OpenClaw, MCP, or webhook external call was enabled or executed.
- The existing siyuan deploy workflow and `deploy/` service overlay remain the production-release boundary.

## 7. Verification

Local verification completed on this sync branch:

- `git diff --check`: pass
- `python3 -m compileall app.py aicrm_next scripts tools tests`: pass
- `.venv/bin/python app.py health`: pass, `default_runtime=ai_crm_next`
- `.venv/bin/python app.py routes`: pass
- `npm run typecheck`: pass
- `npm run test:frontend:all`: pass
- `npm run build:frontend`: pass
- `bash scripts/ci/run_architecture_gates.sh --mode full`: pass
- focused sync contract pytest: `61 passed, 19 skipped, 1 warning`
- callback/deploy overlay pytest rerun: `20 passed, 24 skipped, 1 warning`
- `scripts/run_tests.sh`: `2508 passed, 133 skipped, 55 warnings`

Skipped tests are the AI-CRM canonical production deploy/systemd/callback cutover asset checks that are intentionally not applicable while this PR preserves the existing siyuan production deploy overlay.

Full production confidence still requires a restored-data staging rehearsal because this PR intentionally does not touch the live siyuan database.
