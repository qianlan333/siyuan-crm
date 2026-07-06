# Real PostgreSQL Integration Run

Run timestamp: `2026-05-20 14:34:50 CST`

## Database URL Safety

- PostgreSQL source: existing local PostgreSQL on `127.0.0.1:5432`.
- Test role/database prepared: `aicrm_next_test` / `aicrm_next_test`.
- Redacted database URL: `postgresql+psycopg://aicrm_next_test:***@127.0.0.1:5432/aicrm_next_test`.
- Safety guard result: PASS.
- Safety conclusion: local test database only; no production PostgreSQL connection was used.

The URL host is `127.0.0.1`, and the database name is `aicrm_next_test`, which satisfies the PostgreSQL integration safety guard. Logs and docs must continue to use redacted URLs only.

## Ordinary Pytest

Command:

```bash
.venv/bin/python -m pytest -q
```

Result:

```text
166 passed, 3 skipped in 7.18s
```

## PostgreSQL Integration Tests

Runner command:

```bash
AICRM_NEXT_TEST_DATABASE_URL=postgresql+psycopg://aicrm_next_test:***@127.0.0.1:5432/aicrm_next_test \
  docs/archive/experiments_ai_crm_next/workspace/scripts/run_postgres_integration_tests.sh
```

Runner result:

```text
3 passed, 166 deselected, 9 warnings in 0.53s
```

Marker command:

```bash
AICRM_NEXT_TEST_DATABASE_URL=postgresql+psycopg://aicrm_next_test:***@127.0.0.1:5432/aicrm_next_test \
  .venv/bin/python -m pytest -q -m postgres_integration
```

Marker result:

```text
3 passed, 166 deselected, 9 warnings in 0.51s
```

PostgreSQL integration status: PASS. The tests were not skipped.

## Alembic Result

- `upgrade head`: executed against the real local PostgreSQL test database and passed.
- `downgrade base`: executed against the real local PostgreSQL test database and passed.
- Tables verified during upgrade:
  - `user_ops_pool_current_next`
  - `user_ops_do_not_disturb_next`
  - `user_ops_send_records_next`
  - `customer_list_index_next`
  - `customer_detail_snapshot_next`
  - `customer_timeline_event_next`
  - `customer_recent_message_next`
- Evidence status: available.

Implementation note: the migration revision identifiers were shortened to fit Alembic's default `alembic_version.version_num` length on PostgreSQL. Table schemas and business behavior were not changed.

## SQL Repository Integration Result

- User Ops SQL repo integration: executed on real local PostgreSQL test DB and passed.
- Customer Read Model SQL repo integration: executed on real local PostgreSQL test DB and passed.
- Fixture/in-memory runtime remains the default for ordinary tests unless the explicit integration marker and safe URL are used.

## Parity Results

| parity suite | command mode | result | report |
| --- | --- | --- | --- |
| User Ops | old fixture + Next TestClient | PASS | `/tmp/user_ops_parity_pg_real_actual.md` |
| Customer Read Model | old fixture + Next TestClient | PASS | `/tmp/customer_read_model_parity_pg_real_actual.md` |
| Questionnaire | old fixture + Next TestClient | PASS | `/tmp/questionnaire_parity_pg_real_actual.md` |
| Commerce | old fixture + Next TestClient | PASS | `/tmp/commerce_parity_pg_real_actual.md` |
| Media Library | old fixture + Next TestClient | PASS | `/tmp/media_library_parity_pg_real_actual.md` |

## Known Skips / Warnings

- Ordinary pytest still reports the three opt-in PostgreSQL integration tests as skipped when no `AICRM_NEXT_TEST_DATABASE_URL` is provided. This is intentional safety behavior.
- PostgreSQL integration runs emitted Alembic deprecation warnings about `path_separator` configuration. The warnings did not fail the run and do not indicate production readiness.

## External Services

- No production PostgreSQL was connected.
- No WeCom, WeChat OAuth, WeChat Pay, Alipay, OpenClaw, webhook, cloud storage, or WeCom media service was called.

## Conclusion

Real local PostgreSQL integration evidence is now available for AI-CRM Next Phase 1. Alembic upgrade/downgrade, User Ops SQL repository integration, and Customer Read Model SQL repository integration all passed on the safe local test database.

This does not make any module production-ready. Production PostgreSQL, real external adapters, data migration, deployment smoke, and route-level rollback remain required before cutover.

## Next Action

Enter read-only HTTP dual-run with Customer Read Model and User Ops first. Keep external adapters fake/stubbed and do not execute write endpoints against the old production service.
