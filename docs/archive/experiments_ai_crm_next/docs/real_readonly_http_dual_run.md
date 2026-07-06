# Real Readonly HTTP Dual-Run

Run timestamp: `2026-05-20 15:25:36 CST`

## Targets

- Old Flask base URL: `http://127.0.0.1:5001`
- Next target: FastAPI TestClient
- Scope: `customer,user_ops`
- Report markdown: `/tmp/aicrm_next_readonly_dual_run_real_after_fix.md`
- Report JSON: `/tmp/aicrm_next_readonly_dual_run_real_after_fix.json`

## Old Flask Startup

- Startup command: `python3 app.py run`
- Host/port: `127.0.0.1:5001`
- Process: PID `26987` in the active Codex terminal session `10275`
- Stop command: send `Ctrl+C` to session `10275`, or run `kill 26987` after this evidence no longer needs to be rechecked
- Database: local PostgreSQL test database `aicrm_old_flask_test` on `127.0.0.1:5432`
- Database role: local test role `aicrm_old_flask_test`
- Production database: not connected
- External providers: WeCom, WeChat OAuth, WeChat Pay, Alipay, OpenClaw, webhook, and cloud storage were not configured for this run

Health check:

```bash
curl -sS -i http://127.0.0.1:5001/health
```

Result:

```text
HTTP/1.1 200 OK
{"ok":true,"service":"openclaw-wecom-ability-service"}
```

## Baseline Checks

Ordinary pytest:

```text
176 passed, 3 skipped in 7.67s
```

Parity:

| suite | result | report |
| --- | --- | --- |
| User Ops | PASS | `/tmp/user_ops_parity_after_dual_run_fix.md` |
| Customer Read Model | PASS | `/tmp/customer_read_model_parity_after_dual_run_fix.md` |
| Questionnaire | PASS | `/tmp/questionnaire_parity_after_dual_run_fix.md` |
| Commerce | PASS | `/tmp/commerce_parity_after_dual_run_fix.md` |
| Media Library | PASS | `/tmp/media_library_parity_after_dual_run_fix.md` |

## Readonly Dual-Run Command

```bash
.venv/bin/python retired readonly HTTP dual-run helper; see docs/archive/experiments_ai_crm_next/retired_tools.md \
  --old-base-url http://127.0.0.1:5001 \
  --next-testclient \
  --scope customer,user_ops \
  --output-md /tmp/aicrm_next_readonly_dual_run_real_after_fix.md \
  --output-json /tmp/aicrm_next_readonly_dual_run_real_after_fix.json
```

Safety:

- Old service allowed method: `GET`
- Old service write endpoints executed: `False`
- No POST, PUT, PATCH, DELETE, batch-send, do-not-disturb, submit, checkout, notify, activation webhook, or OpenClaw push endpoint was executed against old Flask.

## Result Summary

Overall result: `PASS`

| metric | count |
| --- | ---: |
| compared | 10 |
| passed | 9 |
| warnings | 1 |
| failed | 0 |
| skipped | 7 |

## Endpoint Summary

| scope | endpoint | old_status | next_status | result | notes |
| --- | --- | ---: | ---: | --- | --- |
| customer | `customers.default` | 200 | 200 | PASS | shape compatible |
| customer | `customers.page` | 200 | 200 | PASS | shape compatible |
| customer | `customers.owner_filter` | - | - | SKIPPED | `missing_owner_userid_sample` |
| customer | `customers.is_bound_true` | 200 | 200 | PASS | shape compatible |
| customer | `customers.keyword` | - | - | SKIPPED | `missing_keyword_sample` |
| customer | `customer_detail.sample` | - | - | SKIPPED | `no_customer_sample` |
| customer | `customer_timeline.sample` | - | - | SKIPPED | `no_customer_sample` |
| customer | `customer_timeline.page` | - | - | SKIPPED | `no_customer_sample` |
| customer | `recent_messages.sample` | - | - | SKIPPED | `no_customer_sample` |
| customer | `recent_messages.limit` | - | - | SKIPPED | `no_customer_sample` |
| user_ops | `overview.default` | 200 | 200 | WARN | legacy drift: old response lacks `激活待录入`; Next satisfies the current product contract |
| user_ops | `list.default` | 200 | 200 | PASS | shape compatible |
| user_ops | `list.wecom_added` | 200 | 200 | PASS | shape compatible |
| user_ops | `list.not_added` | 200 | 200 | PASS | shape compatible |
| user_ops | `list.mobile_bound` | 200 | 200 | PASS | shape compatible |
| user_ops | `list.activated` | 200 | 200 | PASS | shape compatible |
| user_ops | `send_records.default` | 200 | 200 | PASS | shape compatible |

## Blockers

- None.

## Warnings

- `user_ops / overview.default`: legacy drift. Old `/api/admin/user-ops/overview` lacks the required `激活待录入` card, while AI-CRM Next includes it.

## Legacy Drift

- `legacy_missing_required_card_label`: old runtime is behind the current `docs/user_ops_v2.md` product contract for `激活待录入`; Next satisfies the required contract.

## Skipped

- Customer owner filter and keyword filter skipped because the old customer list had no sample owner/keyword.
- Customer detail, timeline, and recent messages skipped because the old customer list had no sample `external_userid`.

## Conclusion

The real old Flask + AI-CRM Next readonly HTTP dual-run executed safely and did not call old write endpoints. There are no blockers after classifying the old-only missing `激活待录入` overview card as legacy drift. This supports moving to route-level frontend smoke / screenshot baseline, while keeping the skipped customer sample endpoints as known coverage gaps for a richer old test dataset.

## Next Action

Proceed to route-level frontend smoke / screenshot baseline. Keep old Flask online for audit recheck until the next verification pass is complete.

## Follow-Up: Customer Readonly Gray Preparation

Customer Read Model readonly gray-release preparation now has dedicated planning and tooling in:

- `docs/archive/experiments_ai_crm_next/docs/customer_read_model_gray_release_plan.md`
- `docs/archive/experiments_ai_crm_next/docs/customer_read_model_route_cutover_manifest.md`
- `docs/archive/experiments_ai_crm_next/docs/customer_read_model_sample_data_checklist.md`
- `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md`

The known sample-data gap remains: the previous local old Flask test database did not provide a representative `external_userid`, so customer detail, timeline, and recent-message dual-run endpoints must remain skipped/pending until safe masked sample data exists. This is not production-ready evidence and does not enable production route cutover.

## Follow-Up: Masked Customer Sample Run

Run timestamp: `2026-05-20 16:48 CST`

Local old Flask test database `aicrm_old_flask_test` was seeded with masked sample data through `retired customer sample seed helper; see docs/archive/experiments_ai_crm_next/retired_tools.md`. The tool uses a localhost/test-database safety guard, redacts passwords, defaults to dry-run, and requires `--apply` before writing.

Old admin page access check:

- `GET /admin/customers`: `302`
- `Location`: `/login?next=/admin/customers`
- Classification: `legacy_admin_auth_redirect`; this is old admin auth/page behavior and not a Customer Read Model API blocker.

Old API sample verification:

| endpoint | result |
| --- | --- |
| `GET /api/customers` | `200`, `total=1`, sample `external_userid=external_user_masked_001` |
| `GET /api/customers/external_user_masked_001` | `200`, detail includes binding, identity, and sidebar context |
| `GET /api/customers/external_user_masked_001/timeline` | `200`, `total=2` |
| `GET /api/messages/external_user_masked_001/recent?limit=5` | `200`, one masked message |

Customer gray smoke dual report:

- Command: `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md --old-base-url http://127.0.0.1:5001 --next-testclient`
- Report markdown: `/tmp/customer_read_model_gray_smoke_dual_after_sample.md`
- Report JSON: `/tmp/customer_read_model_gray_smoke_dual_after_sample.json`
- Result: `PASS`
- Compared: `8`
- Passed: `7`
- Warnings: `1`
- Failed: `0`
- Skipped: `0`
- Warning: old `/admin/customers` is `legacy_admin_auth_redirect`.
- Old write endpoints executed: `False`
- Real WeCom/archive sync/tag refresh/OpenClaw calls executed: `False`

Readonly HTTP dual-run report:

- Command: `retired readonly HTTP dual-run helper; see docs/archive/experiments_ai_crm_next/retired_tools.md --old-base-url http://127.0.0.1:5001 --next-testclient --scope customer,user_ops`
- Report markdown: `/tmp/aicrm_next_readonly_dual_run_after_customer_sample.md`
- Report JSON: `/tmp/aicrm_next_readonly_dual_run_after_customer_sample.json`
- Result: `PASS`
- Compared: `17`
- Passed: `16`
- Warnings: `1`
- Failed: `0`
- Skipped: `0`
- Warning: User Ops legacy drift where old `/api/admin/user-ops/overview` lacks `激活待录入`; Next satisfies the current product contract.
- Old write endpoints executed: `False`

Conclusion: the customer detail, timeline, and recent-message routes now have local masked old-test-data dual-run evidence. This is still not production route cutover evidence and does not connect production PostgreSQL or real WeCom/archive/tag/OpenClaw services.

## Follow-Up: User Ops Readonly Gray Preparation

User Ops readonly gray-release preparation now has dedicated planning and tooling in:

- `docs/archive/experiments_ai_crm_next/docs/user_ops_readonly_gray_release_plan.md`
- `docs/archive/experiments_ai_crm_next/docs/user_ops_readonly_route_cutover_manifest.md`
- `docs/archive/experiments_ai_crm_next/docs/user_ops_readonly_sample_and_drift_checklist.md`
- `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md`

The accepted legacy drift remains: old `/api/admin/user-ops/overview` may miss `激活待录入`, while Next must satisfy the current 8-card product contract. DND, batch-send preview/execute, deferred jobs, internal User Ops routes, real WeCom dispatch, and media upload remain outside readonly dual-run and gray preparation.

Latest User Ops readonly gray smoke evidence:

- Next-only report: `/tmp/user_ops_readonly_gray_smoke.md`, result `PASS`, compared `8`, skipped `0`.
- Dual report: `/tmp/user_ops_readonly_gray_smoke_dual.md`, result `PASS`, compared `8`, passed `6`, warnings `2`, failed `0`, skipped `0`.
- Dual warnings: old `/admin/user-ops/ui` returned `legacy_admin_auth_redirect`; old `/api/admin/user-ops/overview` missed `激活待录入` while Next satisfied the current contract.
- Side-effect safety: `old_write_endpoints_executed=false`, `wecom_dispatch_executed=false`, `media_upload_executed=false`, `deferred_jobs_executed=false`.
