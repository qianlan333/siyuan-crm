# Frontend Screenshot Baseline

Run timestamp: `2026-05-20 15:51 CST`

## Purpose

Route-level frontend smoke and screenshot baseline verifies that AI-CRM Next still serves the copied legacy frontend adapters before any route-level gray release. This baseline is intentionally not a redesign review and not a full browser interaction test.

## Command

```bash
.venv/bin/python retired frontend screenshot helper; see docs/archive/experiments_ai_crm_next/retired_tools.md \
  --output-dir artifacts/frontend_screenshots \
  --mode testclient \
  --output-md /tmp/aicrm_next_frontend_route_screenshot_baseline.md \
  --output-json /tmp/aicrm_next_frontend_route_screenshot_baseline.json
```

Generated reports:

- Markdown report: `/tmp/aicrm_next_frontend_route_screenshot_baseline.md`
- JSON report: `/tmp/aicrm_next_frontend_route_screenshot_baseline.json`
- Route manifest artifact: `historical removed reference (manifest.json)`
- Route status artifact: `historical removed reference (route_status.json)`
- HTML snapshots: `artifacts/frontend_screenshots/html/*.html`
- PNG screenshots: `artifacts/frontend_screenshots/png/*.png`

`artifacts/frontend_screenshots/` is generated output and is gitignored. Re-run the command to regenerate local evidence.

Local screenshot dependency:

- `playwright` package: `1.60.0`
- Chromium browser: Playwright Chromium `v1223`, Chrome for Testing `148.0.7778.96`
- Install command: `.venv/bin/python -m pip install playwright && .venv/bin/python -m playwright install chromium`

## Result Summary

| metric | value |
| --- | ---: |
| routes | 14 |
| passed | 14 |
| failed | 0 |
| screenshots_generated | 14 |
| screenshots_skipped | 0 |

Overall result: `PASS`

Screenshot status: PNG screenshots and HTML snapshots were generated for every route. Ordinary pytest still does not depend on Playwright; the screenshot command is a separate gray-release evidence step and keeps HTML snapshot fallback behavior if a future environment lacks a browser.

## Route Status

| route | status | screenshot/html status | notes |
| --- | --- | --- | --- |
| `/admin` | PASS | HTML snapshot and PNG generated | Copied legacy admin shell. |
| `/admin/customers` | PASS | HTML snapshot and PNG generated | Customer list fixture adapter. |
| `/admin/user-ops/ui` | PASS | HTML snapshot and PNG generated | Legacy User Ops UI with 8-card contract. |
| `/admin/questionnaires` | PASS | HTML snapshot and PNG generated | Questionnaire admin baseline. |
| `/admin/questionnaires/ui` | PASS | HTML snapshot and PNG generated | Alias route. |
| `/admin/wechat-pay/products` | PASS | HTML snapshot and PNG generated | Product management partial adapter. |
| `/admin/wechat-pay/transactions` | PASS | HTML snapshot and PNG generated | WeChat Pay transaction template. |
| `/admin/alipay/transactions` | PASS | HTML snapshot and PNG generated | Alipay partial adapter. |
| `/admin/image-library` | PASS | HTML snapshot and PNG generated | Image material template. |
| `/admin/attachment-library` | PASS | HTML snapshot and PNG generated | Attachment partial adapter. |
| `/admin/miniprogram-library` | PASS | HTML snapshot and PNG generated | Mini-program material template. |
| `/s/hxc-activation-v1` | PASS | HTML snapshot and PNG generated | Public questionnaire H5 fixture. |
| `/p/course-masked-001` | PASS | HTML snapshot and PNG generated | Public product fixture. |

## Known Gaps

- Several frontend adapters remain partial shells: product management, Alipay transactions, and attachment library.
- Customer detail/timeline/message real dual-run coverage still needs a representative old test database customer sample.
- This baseline does not prove production auth, real external adapters, or production database readiness.
- Media Library gray-release preparation uses the existing image, attachment, and mini-program screenshots as route-level evidence only; it does not prove real cloud storage or WeCom media upload.

## How To Use For Gray Release

Before route-level gray release, require:

- ordinary pytest pass,
- six fixture parity CLIs pass,
- real PostgreSQL integration evidence remains available,
- readonly HTTP dual-run has no blocker,
- this route smoke report has no failed route,
- PNG screenshots are generated or the HTML-snapshot fallback is explicitly accepted for the environment,
- no fake adapter is marked production-ready.

Product Management gray-release preparation uses the existing `/admin/wechat-pay/products` and `/p/course-masked-001` screenshots as route-level evidence only. It does not prove production checkout, real WeChat Pay, real Alipay, or production product publishing readiness.

Customer Read Model readonly gray-release preparation uses the existing `/admin/customers` screenshot as route-level evidence only. It does not prove production data coverage, real WeCom contact sync, message archive sync, tag refresh, or OpenClaw webhook readiness.

User Ops readonly gray-release preparation uses the existing `/admin/user-ops/ui` screenshot as route-level evidence only. It does not authorize DND, batch-send preview/execute, deferred jobs, real WeCom dispatch, media upload, or production traffic cutover.

Questionnaire readonly gray-release preparation uses the existing `/admin/questionnaires`, `/admin/questionnaires/ui`, and `/s/hxc-activation-v1` screenshots as route-level evidence only. It does not authorize production submit, real WeChat OAuth, WeCom tag mutation, external webhook push, or production traffic cutover.

`/admin/automation-conversion` is no longer part of this historical experiment screenshot baseline. The current main application validates that route as the AI Audience package list through the `ai_audience_ops` admin page/API tests.
