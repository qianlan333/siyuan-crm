# Service Layer Layout

This document defines the service-layer contract for `wecom_ability_service`.

## Rules

Only two domain layout modes are allowed:

1. `simple`
- `service.py`
- `repo.py`

2. `complex`
- `service.py`
- `queries.py`
- `writers.py`
- optional `repo.py` as an aggregation entry

Companion files are allowed only when they stay inside one of those two modes and do not create a third layering style.
Examples:
- `definitions.py` for domain-owned rules
- `preflight_service.py` for a small domain-local application assembly helper

## Direction Of Dependencies

- HTTP controller -> domain `service.py`
- Domain `service.py` -> same-domain `repo.py` or `queries.py` / `writers.py`
- Domain code -> `infra/*` for shared constants, settings, runtime clients, and low-level helpers
- `wecom_ability_service/services.py` -> compatibility facade only

Forbidden directions:
- controller -> raw SQL
- controller -> direct `requests` / `WeComClient.from_*`
- domain -> Flask response objects
- new business implementation -> `services.py`

## Current Domain Modes

| Domain | Mode | Primary responsibility | Notes |
| --- | --- | --- | --- |
| `archive` | `simple` | archived messages, sync runs, message batches | `service.py + repo.py` |
| `callbacks` | `simple` | external-contact callback business orchestration | `service.py + repo.py` |
| `class_user` | `simple` | signup status state machine and history | `service.py + repo.py` |
| `contacts` | `simple` | contact snapshot, description sync, WeCom contact reads | `service.py + repo.py` |
| `group_chats` | `simple` | group-chat snapshot and persistence | `service.py + repo.py` |
| `identity` | `simple` | people, bindings, identity map, resolve flow | `service.py + repo.py` |
| `questionnaire` | `simple` | questionnaire definition, submit, export, SCRM apply | `preflight_service.py` is a narrow companion helper |
| `routing_config` | `simple` | owner role map, signup routing, mapping rules | `definitions.py` keeps domain-owned rules |
| `tags` | `simple` | tag snapshot, signup tag rules, tag refresh | `service.py + repo.py` |
| `tasks` | `simple` | outbound task dispatch and persistence | `service.py + repo.py` |
| `user_ops` | `simple` | lead pool, imports, activation, deferred jobs, class-term mapping | `service.py + repo.py` |

## Shared Infra

`wecom_ability_service/infra/` is the only shared layer for cross-domain support:

- `constants.py`: cross-domain constants and enumerations
- `settings.py`: app-setting storage helpers
- `helpers.py`: low-level shared helpers
- `wechat_oauth.py`: WeChat OAuth HTTP client helpers
- `wecom_runtime.py`: runtime wrappers around WeCom clients

## `services.py`

`wecom_ability_service/services.py` stays as a thin compatibility facade.
It may only contain:

- re-exports for old import paths
- a small number of wrappers for backward-compatible call signatures
- monkeypatch / dependency injection glue needed by existing tests

It must not contain:

- new domain implementation
- raw SQL
- direct third-party HTTP calls
- domain-owned business rules
