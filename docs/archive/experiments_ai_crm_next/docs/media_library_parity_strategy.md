# Media Library Parity Strategy

Status: `partial`.

This first media-library slice locks image, attachment, and mini-program material contracts while keeping storage fixture-backed.

## Modes

- Fixture mode compares `tests/fixtures/old_media_library/` with AI-CRM Next TestClient.
- HTTP mode is reserved for isolated read-only checks.
- Upload/import APIs remain fake/fixture only.

## Covered Contracts

- `GET /api/admin/image-library`
- `POST /api/admin/image-library`
- `POST /api/admin/image-library/from-url`
- `POST /api/admin/image-library/from-base64`
- `GET /api/admin/attachment-library`
- `POST /api/admin/attachment-library`
- `GET /api/admin/miniprogram-library`
- `POST /api/admin/miniprogram-library`

## Not Connected

- no cloud object storage;
- no real WeCom media upload;
- no production database;
- no replacement of the old material-library system.

Image Library, Attachment Library, and Mini-program Library remain `partial`.
