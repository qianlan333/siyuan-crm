# Schema Migration Template

Use this template for any PR that creates, drops, renames, or materially changes
database tables, identity/business keys, or PII-bearing columns.

## Required Intake

- Lifecycle manifest entry: update `docs/architecture/data_table_lifecycle_manifest.yml`.
- Capability owner: declare the owning Next module or bounded context.
- Business key: name the canonical business key and explain why it is stable.
- PII level: `none`, `low`, `medium`, or `high`.
- Read path: list every repository, query, API, admin page, or job that reads the table.
- Write path: list every repository, command, callback, job, or migration that writes the table.
- Repository ownership: update `docs/architecture/repository_ownership.yml` for all read/write paths.
- Rollback note: state the minimum safe rollback and whether data backfill is reversible.
- Fresh DB test: run migration upgrade on an empty database and record the command/output.

## Alembic Revision Header

```python
"""<short migration purpose>

Lifecycle manifest entry:
- table:
- lifecycle:
- write_owner:

Schema ownership:
- capability_owner:
- business_key:
- pii_level:
- read_path:
- write_path:

Rollback note:
- <minimum safe rollback or explicit irreversible data reason>

Fresh DB test:
- <command and key output>
"""
```

## Pre-PR Verification

Run these before opening a schema PR:

```bash
python tools/check_data_table_lifecycle.py
python tools/check_sql_static_guard.py
python tools/check_repository_ownership.py
python tools/check_schema_change_templates.py
bash scripts/ci/run_architecture_gates.sh
```

If the migration touches identity or customer-facing effect paths, also run the
targeted tests for unionid resolution, external effect, payment, notification,
and material assets ownership that match the changed code.
