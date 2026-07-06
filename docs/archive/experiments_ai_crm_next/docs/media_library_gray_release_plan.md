# Media Library Gray Release Preparation Plan

This document prepares Media Library for a future route-level gray release. It does not cut production traffic, replace old Flask routes, connect real storage, or enable real WeCom media upload.

## Scope

Routes in scope:

- `GET /admin/image-library`
- `/api/admin/image-library*`
- `GET /admin/attachment-library`
- `/api/admin/attachment-library*`
- `GET /admin/miniprogram-library`
- `/api/admin/miniprogram-library*`

## Current Status

| area | status | notes |
| --- | --- | --- |
| frontend | partial adapter | Image and mini-program pages use copied legacy templates; attachment uses a legacy admin shell partial adapter. |
| backend | parity_ready partial | Image, attachment, and mini-program API contracts are implemented with tests and parity fixtures. |
| storage | fake / in-memory / fixture | No real cloud storage is connected. |
| external adapter | cloud storage fake, WeCom media fake | No real WeCom media upload is executed. |
| production replacement | not ready | No production traffic, production database, or external adapter cutover has happened. |

## Gray-Eligible Items

- Read-only page smoke for the three admin routes.
- API shape compatibility for read/list endpoints.
- Fixture-backed CRUD behavior in AI-CRM Next only.
- Route-level screenshot baseline for the three admin pages.
- Gray smoke tooling against AI-CRM Next TestClient or Next HTTP read routes.

## Not Gray-Eligible In This Phase

- Real cloud storage upload.
- Real WeCom media upload.
- Production media data migration.
- Production write-route replacement.
- Any old Flask write call during gray smoke or parity checks.

## Preconditions

| condition | required evidence |
| --- | --- |
| ordinary pytest pass | `.venv/bin/python -m pytest -q` |
| media parity pass | `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md --old-fixture-dir ... --next-testclient` |
| frontend smoke pass | `retired frontend route smoke test; see docs/archive/experiments_ai_crm_next/retired_tools.md` and screenshot baseline |
| screenshot baseline pass | 14-route baseline includes image, attachment, and miniprogram pages |
| no old backend imports | architecture boundary scan/tests |
| no production external calls | fake adapters remain active; no storage or WeCom media credentials used |
| rollback checklist ready | route-level rollback remains old Flask by default |

## Rollback Strategy

- Route-level rollback target is old Flask.
- Disable any future Next media route flag before switching traffic back.
- Keep old media routes active until production verification is complete.
- Do not perform destructive data operations during gray preparation.
- Because this phase uses fixture/in-memory data, no production data rollback should be required.

## Go / No-Go

Go only when all are true:

- Ordinary pytest passes.
- Media parity passes.
- Media gray smoke passes in default read-only mode.
- Optional fake-write smoke passes only against Next TestClient.
- Frontend PNG screenshot baseline includes the three media pages.
- No old backend imports exist in AI-CRM Next.
- No real cloud storage or WeCom media upload is configured.
- Rollback route remains old Flask.

No-Go if any are true:

- Any media page route returns 5xx.
- Any required API shape key is missing.
- A gray smoke run attempts POST/PUT/DELETE against old Flask.
- Real cloud storage or WeCom media upload is triggered.
- Any module is mislabeled `production_ready`.
- Production route cutover is attempted without rollback owner approval.

## Next Action

Run Media Library gray smoke in read-only mode, then optionally run fake-write smoke against AI-CRM Next TestClient only. Use the resulting reports as preparation evidence for later gray-release review.
