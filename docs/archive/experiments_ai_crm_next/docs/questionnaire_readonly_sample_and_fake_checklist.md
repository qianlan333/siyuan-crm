# Questionnaire Readonly Sample And Fake Checklist

Readonly gray preparation does not require real submit, real OAuth, real WeCom tags, or real webhook push. Sample data only proves route shape and read-path coverage.

## Admin Read Samples

| area | minimum sample | impact if missing |
| --- | --- | --- |
| Admin list | at least one questionnaire with masked id/slug/title | Detail, export, debug, public routes should skip with reason if no sample exists. |
| Admin detail | questionnaire id selected from list | Shape check remains sample-dependent. |
| Preflight | no sample required | Expected to show fake/stubbed external checks. |
| Export | questionnaire id selected from list | Can pass with empty `items`; this is still readonly shape coverage only. |
| Latest submit debug | questionnaire id selected from list | Can return `submission=null`; result endpoint then skips unless a submission sample exists. |

## Public Read Samples

| area | minimum sample | impact if missing |
| --- | --- | --- |
| Public slug | slug selected from admin list or fixture response | `/s/{slug}` and public API skip if absent. |
| Result endpoint | slug plus submission id from latest debug or fake submit | Result endpoint skips if no submission id is available. |

## Local Old Flask Masked Sample

The historical questionnaire sample seed helper is retired; see
`docs/archive/experiments_ai_crm_next/retired_tools.md`.

Safety rules:

- Host must be `127.0.0.1`, `localhost`, or `::1`.
- Database name must be exactly `aicrm_old_flask_test` and include `test`.
- Default mode is dry-run; writes require explicit `--apply`.
- Output redacts credentials.
- The seed tool does not import `wecom_ability_service` or `openclaw_service`.
- Seeded values are masked: `questionnaire_slug_masked_001`, `questionnaire_title_masked_001`, `question_title_masked_001`, `option_label_masked_001`, `openid_masked_001`, `unionid_masked_001`, `external_user_masked_001`, and `result_token_masked_001`.

2026-05-20 local evidence:

- The retired questionnaire sample seed helper wrote masked sample data to local `aicrm_old_flask_test`.
- Old readonly API checks returned sample data for admin list, admin detail, export, latest-submit-debug, and public page.
- Old `/api/h5/questionnaires/{slug}` returned the legacy WeChat-browser gate (`403 please_open_in_wechat`); the gray smoke report records this as legacy drift when Next satisfies the public read API contract.
- Old Flask exposes result rendering as `/s/{slug}/result/{result_token}`. It does not expose Next's JSON result API path `/api/h5/questionnaires/{slug}/result/{submission_id}`; the gray smoke report records this as legacy drift when Next satisfies the result API contract.
- Latest dual report: `/tmp/questionnaire_readonly_gray_smoke_dual_after_sample.md` and `/tmp/questionnaire_readonly_gray_smoke_dual_after_sample.json`.

## Fake Submit Boundary

- Fake submit is not part of default readonly smoke.
- Fake submit requires explicit `--include-fake-submit`.
- Fake submit is allowed only against Next TestClient.
- Fake submit must never be sent to old Flask.
- Fake submit data must use masked identifiers, for example `external_user_masked_gray_001` and `openid_masked_gray_001`.

## OAuth Boundary

- Current OAuth start/callback behavior is fake/stubbed.
- Real OAuth signing/state/replay validation is not proven.
- OAuth callback is excluded from default readonly smoke and from old-base-url mode.
- Do not mark fake OAuth as production-ready.

## External Push / WeCom Boundary

- Real WeCom tag mutation is disabled.
- Real external webhook push/retry is disabled.
- External push retry routes are not gray-ready.

## Masking Rules

Use masked values only:

- `questionnaire_masked_001`
- `submission_masked_001`
- `openid_masked_001`
- `unionid_masked_001`
- `external_user_masked_001`
- `mobile_masked_001`

Do not use real phone-number formats, real openid/unionid, real external user ids, real names, or production database connections.
