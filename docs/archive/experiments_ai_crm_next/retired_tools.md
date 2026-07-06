# Retired Experiment Tool Wrappers

The frozen `experiments/ai_crm_next` workspace previously contained thin
wrappers that imported same-named scripts from the repository root `tools/`
directory. Those root scripts no longer exist, so the wrappers failed at import
time and no longer represented runnable evidence.

This archive record documents their retirement. The historical markdown reports
under `docs/archive/experiments_ai_crm_next/docs/` still describe what those
commands produced at the time; they are not current runbooks.

Retired wrappers:

- `compare_commerce_parity.py`
- `compare_customer_read_model_parity.py`
- `compare_media_library_parity.py`
- `compare_questionnaire_parity.py`
- `compare_user_ops_parity.py`
- `customer_read_model_gray_smoke.py`
- `media_library_gray_smoke.py`
- `product_management_gray_smoke.py`
- `questionnaire_readonly_gray_smoke.py`
- `run_gray_rehearsal_batch.py`
- `user_ops_readonly_gray_smoke.py`

Retired readiness and review helpers:

- `check_batch_1_media_canary_readiness.py`
- `check_batch_1_media_production_signoff_readiness.py`
- `check_batch_2_product_canary_readiness.py`
- `check_batch_3_customer_canary_readiness.py`
- `check_batch_4_user_ops_canary_readiness.py`
- `check_batch_5_questionnaire_canary_readiness.py`
- `check_production_canary_approval_package.py`
- `generate_gray_release_report.py`

Retired local evidence helpers:

- `capture_frontend_screenshots.py`
- `readonly_http_dual_run.py`
- `seed_old_flask_customer_sample.py`
- `seed_old_flask_questionnaire_sample.py`

Retired tests:

- `test_customer_read_model_gray_smoke.py`
- `test_media_library_gray_smoke.py`
- `test_product_management_gray_smoke.py`
- `test_questionnaire_readonly_gray_smoke.py`
- `test_gray_rehearsal_batch.py`
- `test_user_ops_readonly_gray_smoke.py`
- `test_batch_1_media_canary_readiness.py`
- `test_batch_1_media_production_signoff_readiness.py`
- `test_batch_2_product_canary_readiness.py`
- `test_batch_3_customer_canary_readiness.py`
- `test_batch_4_user_ops_canary_readiness.py`
- `test_batch_5_questionnaire_canary_readiness.py`
- `test_gray_release_runbook.py`
- `test_production_canary_approval_package.py`
- `test_frontend_route_smoke.py`
- `test_readonly_http_dual_run.py`
- `test_seed_old_flask_customer_sample.py`
- `test_seed_old_flask_questionnaire_sample.py`

Active experiment coverage remains in the parity specs, fixture masking tests,
contract tests, route/header tests, PostgreSQL readiness tests, and architecture
gates. Historical canary, gray-release, signoff, screenshot, seed, and dual-run
evidence remains archived under `docs/archive/experiments_ai_crm_next/docs/`;
the retired helpers above should not be used as current runbooks or production
approval checks.
