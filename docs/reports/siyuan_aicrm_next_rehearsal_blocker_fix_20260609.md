# siyuan AI-CRM Next rehearsal blocker fix note

## Scope

This note records the blocker fix path for the June 9, 2026 full server staging rehearsal. It does not contain production secrets, database URLs, raw scene values, raw external user IDs, dumps, uploads, or private keys.

## Rehearsal Blockers

- `/api/admin/user-ops/overview` returned `fixture_repository_blocked_in_production` because User Ops still defaulted to the in-memory repository even when the runtime was production PostgreSQL.
- Customer and sidebar read endpoints returned 503 when `customer_detail_snapshot_next` and sibling Next read-model tables were missing after restore and legacy init.
- Alembic commands could not be used as the immediate unblock path because the revision graph currently reports duplicate `0012` and `0016` revisions and a missing `0013` referenced by `0014_alipay_pay.py`.

## Fix Path

This was the pre-closeout rehearsal unblock path. Current startup closeout supersedes it: production schema changes now use `python3 -m alembic upgrade head`, and `app.py` legacy/bootstrap init commands are removed.

- In PostgreSQL runtime, User Ops now resolves to SQLAlchemy/PostgreSQL repository by default unless explicitly configured otherwise for non-production experimentation.
- Historical pre-closeout `python3 app.py init-next-schema-safe` and `scripts/siyuan_migration/06_safe_next_schema_init.sql` created missing AI-CRM Next customer read-model and User Ops SQL read-model tables/indexes using only safe `CREATE ... IF NOT EXISTS` statements.
- `scripts/siyuan_migration/07_validate_next_blockers.sql` checks whether the blocker tables exist before smoke testing.

## Alembic Follow-up

This PR does not rewrite historical migration revisions. A later migration-governance PR should repair the duplicate/missing revision graph and re-enable reliable `alembic upgrade head` for clean databases.
