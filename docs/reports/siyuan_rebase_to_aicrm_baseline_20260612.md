# siyuan-crm rebase to AI-CRM baseline - 2026-06-12

## 1. Executive Summary

Conclusion: BASELINE_REBASE_READY_FOR_REHEARSAL

- product code now follows AI-CRM main baseline
- siyuan operational overlays retained only where required for migration and cutover rehearsal
- production not changed
- next step is same-server restored-data rehearsal

This conclusion is valid only with the validation set below passing. This PR changes the repository only. It does not write production DB data, restart services, edit production systemd/nginx files, change production env, or change the main-push deployment workflow.

## 2. Baselines

- AI-CRM main SHA: `6feb8c9daa7170ef4b260cb1610f15ef6510e1e6`
- siyuan previous main SHA: `a43da560dffdf11ffcd350368123e5bcf42ddf15`
- siyuan new branch SHA: see PR head SHA recorded in pull request metadata and PR body
- compare date: `2026-06-12`

## 3. Synced From AI-CRM

- `aicrm_next/`
- `migrations/`
- `scripts/`
- `tools/`
- `tests/`
- `.github/workflows/ci.yml` for PR smoke alignment only
- `docs/architecture/`
- `docs/development/`
- `docs/external_orders_api.md`
- `requirements.txt`
- `app.py`

`docs/route_ownership/` is absent from the AI-CRM baseline and was removed from siyuan instead of retained as an overlay.

`.github/workflows/deploy.yml` and `deploy/` are intentionally not synced in PR-11. They remain on the existing siyuan main behavior so this baseline rebase cannot change main-push production deployment, systemd units, nginx, or env wiring. Deploy/systemd/nginx/env changes are deferred to PR-12 same-server rehearsal and PR-13 blue-green cutover.

## 4. Retained siyuan Overlays

- `scripts/siyuan_migration/`
- `docs/reports/siyuan_*`
- `docs/runbooks/siyuan_*`
- `docs/reports/templates/siyuan_aicrm_next_production_cutover_report_template.md`
- `docs/external_orders_api.md` domain and example placeholders for siyuan deployment
- no-op migration overlays for AI-CRM production-data-specific revisions:
  - `0032_miniprogram_only_resend_20260611`
  - `0033_complete_miniprogram_only_resend_20260611`
  - `0034_reset_miniprogram_only_material_jobs_20260611`
- existing `.github/workflows/deploy.yml` and `deploy/` production deployment overlay from siyuan main, unchanged by PR-11

`app.py` stays on AI-CRM Next-only runtime commands. The removed siyuan `init-next-schema-safe` and `sync-customer-read-model` app CLI entries were not restored. Rehearsal helpers now live under `scripts/siyuan_migration/`.

## 5. Migration Safety Review

| migration | AI-CRM behavior | siyuan treatment | reason |
|---|---|---|---|
| `0001_baseline` through `0031_automation_runtime_v2` | schema and generic idempotent changes for Next runtime, commerce, channel, customer read model, user ops, external push, automation runtime | kept | required to match AI-CRM product schema baseline |
| `0021_broadcast_queue_platform_hardening` | generic idempotent `broadcast_jobs` metadata backfill | kept | no AI-CRM hardcoded campaign/member/product IDs |
| `0022_next_automation_agents` | schema plus generic default agent metadata | kept | generic seed data, not AI-CRM production data |
| `0023_group_ops_webhook_rules` | schema plus builtin `has_used_core_feature` rule metadata | kept | generic capability metadata |
| `0024_cloud_plan_recipient_approval` | merge/schema materialization | kept | required graph merge/schema baseline |
| `0032_miniprogram_only_resend_20260611` | creates AI-CRM miniprogram-only resend campaigns from production campaign rows | siyuan-safe no-op | AI-CRM production campaign/member/external contact data must not be imported or mutated |
| `0033_complete_miniprogram_only_resend_20260611` | completes AI-CRM resend campaign segment/step/member rows | siyuan-safe no-op | AI-CRM production campaign/member data migration |
| `0034_reset_miniprogram_only_material_jobs_20260611` | resets AI-CRM failed broadcast jobs for a specific production resend group | siyuan-safe no-op | AI-CRM production broadcast job mutation |
| `0035_wechat_shop_refunds` | schema-only WeChat Shop refunds | kept | schema-only |
| `0036_channel_multi_staff_assignment` and `0036_wechat_shop_sync_runs` | schema-only parallel heads | kept | schema-only |
| `0037_*` and `0038_merge_duplicate_channel_wechat_shop_heads` | merge revisions | kept | maintains a single Alembic head |

No AI-CRM production data was imported. No AI-CRM campaign/member/order/product ID, `external_userid`, `scene_value`, `unionid`, `openid`, or mobile value was added by the siyuan overlay.

## 6. Runtime Parity Result

- `main.py`: AI-CRM `aicrm_next/main.py` baseline synced
- `frontend_compat`: AI-CRM baseline synced; legacy route registry template removed with baseline
- `post_legacy_deferred`: removed with AI-CRM baseline
- `wecom_ability_service`: removed from repository
- `background_jobs`: AI-CRM `aicrm_next/background_jobs/` baseline synced
- `external_push`: AI-CRM `aicrm_next/external_push/` and worker tests synced
- `route ownership`: legacy `docs/route_ownership/` removed because AI-CRM baseline no longer carries it
- `runtime_v2` realtest target guard: production-like external_userid is not committed; allowed realtest target IDs must come from `AICRM_RUNTIME_V2_REALTEST_ALLOWED_EXTERNAL_USERIDS`

Runtime-only grep found no `wecom_ability_service`, `legacy_flask_facade`, `forward_to_legacy_flask`, or `production_compat_router` imports in `aicrm_next`, `app.py`, or `scripts`.

## 7. Known Deferred / Next Step

- no production deploy in PR-11
- no `.github/workflows/deploy.yml` change in PR-11
- no `deploy/` systemd unit change in PR-11
- data rehearsal required in PR-12
- blue-green cutover required in PR-13
- observation required in PR-14
- old asset cleanup only after PR-15

## 8. Validation

- `.venv/bin/python -m compileall app.py aicrm_next scripts tools tests`
- `.venv/bin/python app.py health`
- `.venv/bin/python app.py routes > /tmp/pr11_routes.txt` (`631` routes)
- `.venv/bin/python -m pytest tests/test_alembic_revision_chain.py -q` (`7 passed`)
- `.venv/bin/python -m pytest tests/test_deploy_workflow_contract.py tests/test_external_push_worker_next_native.py tests/test_sidebar_write_commands.py tests/test_channel_multi_staff_backend.py tests/test_next_channel_qrcode_generate.py tests/test_external_orders_api.py tests/test_startup_entrypoint_next_only.py tests/test_background_jobs_next_native.py -q` (`72 passed`, `7 skipped`, one StarletteDeprecationWarning)
- targeted fixture cleanup rerun: `66 passed`, `2 skipped`, one StarletteDeprecationWarning
- YAML check:
  - `docs/development/phase_execution_state.yaml`: `yaml_ok`
  - `docs/architecture/legacy_exit_route_registry.yaml`: missing in AI-CRM baseline
  - `docs/route_ownership/production_route_ownership_manifest.yaml`: missing in AI-CRM baseline
- legacy/runtime grep: no runtime legacy Flask fallback imports
- diff check: `git diff --check` passed

AI-CRM current baseline no longer includes `scripts/check_no_new_legacy.py` or `tools/generate_legacy_replacement_backlog.py`; these were not reintroduced.

Because those legacy checkers were removed by the AI-CRM baseline, PR-12 restored-data rehearsal and PR-13 production smoke must cover the remaining deployment/runtime safety checks before any production cutover. The deploy-workflow rollout assertions in `tests/test_deploy_workflow_contract.py` are skipped while PR-11 intentionally keeps the existing siyuan deploy overlay unchanged.

## 9. Security Statement

- no env committed
- no dump committed
- no uploads/instance/pem/key committed
- no secrets printed
- no raw external_userid/scene_value/mobile/unionid/openid added by this PR overlay
- no production DB writes
- no systemd/nginx/env changes on any production host
- no `.github/workflows/deploy.yml` production deploy workflow change
- no `deploy/` systemd unit change

Full repository scans contain AI-CRM baseline test fixtures, placeholder env key names, and local test URLs. The runtime realtest external_userid guard is env-driven instead of committing a raw production-like external_userid.
