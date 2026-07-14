from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT = Path(__file__).resolve().parents[2]
BASELINE_ID = "0001_post_legacy_v1"
BASELINE_PATH = ROOT / "migrations" / "baselines" / "0001_post_legacy.sql"
BOOTSTRAP_LOCK_KEY = 4_249_004_111


class DatabaseBootstrapRefused(RuntimeError):
    """Raised when a database is not safe for the empty-database bootstrap."""


@dataclass(frozen=True)
class DatabaseBootstrapResult:
    target: str
    baseline_id: str
    baseline_sha256: str
    baseline_applied: bool
    revision_before: str | None
    revision_after: str


def install_or_upgrade_database(
    database_url: str,
    *,
    baseline_path: Path = BASELINE_PATH,
) -> DatabaseBootstrapResult:
    psycopg_url = _psycopg_url(database_url)
    target = _safe_target(psycopg_url)
    baseline_sql = baseline_path.read_text(encoding="utf-8")
    baseline_sha256 = hashlib.sha256(baseline_sql.encode("utf-8")).hexdigest()

    with psycopg.connect(psycopg_url, autocommit=True) as lock_connection:
        lock_connection.execute("SELECT pg_advisory_lock(%s)", (BOOTSTRAP_LOCK_KEY,))
        try:
            has_alembic_state = _has_alembic_version_table(lock_connection)
            revision_before = _current_revision(lock_connection) if has_alembic_state else None
            baseline_applied = False

            if has_alembic_state:
                if not revision_before:
                    raise DatabaseBootstrapRefused(
                        "alembic_version exists without a revision; refusing an ambiguous recovery"
                    )
            else:
                relations = _user_relations(lock_connection)
                if relations:
                    sample = ", ".join(relations[:8])
                    raise DatabaseBootstrapRefused(
                        "database has user relations but no Alembic state; "
                        f"refusing bootstrap ({sample})"
                    )
                with lock_connection.transaction():
                    lock_connection.execute(baseline_sql)
                baseline_applied = True

            expected_head = _upgrade_to_head(database_url)
            revision_after = _current_revision(lock_connection)
            if revision_after != expected_head:
                raise RuntimeError(
                    f"Alembic head mismatch: expected {expected_head}, got {revision_after or 'none'}"
                )
        finally:
            lock_connection.execute("SELECT pg_advisory_unlock(%s)", (BOOTSTRAP_LOCK_KEY,))

    return DatabaseBootstrapResult(
        target=target,
        baseline_id=BASELINE_ID,
        baseline_sha256=baseline_sha256,
        baseline_applied=baseline_applied,
        revision_before=revision_before,
        revision_after=revision_after,
    )


def _upgrade_to_head(database_url: str) -> str:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    expected_head = ScriptDirectory.from_config(config).get_current_head()
    if not expected_head:
        raise RuntimeError("Alembic has no single current head")

    previous_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        command.upgrade(config, "head")
    finally:
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url
    return expected_head


def _has_alembic_version_table(connection: psycopg.Connection[object]) -> bool:
    row = connection.execute(
        "SELECT to_regclass('public.alembic_version') IS NOT NULL"
    ).fetchone()
    return bool(row and row[0])


def _current_revision(connection: psycopg.Connection[object]) -> str | None:
    if not _has_alembic_version_table(connection):
        return None
    row = connection.execute("SELECT version_num FROM alembic_version LIMIT 1").fetchone()
    return str(row[0]) if row and row[0] else None


def _user_relations(connection: psycopg.Connection[object]) -> list[str]:
    rows = connection.execute(
        """
        SELECT namespace.nspname || '.' || relation.relname
        FROM pg_class relation
        JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname NOT IN ('information_schema', 'pg_catalog')
          AND namespace.nspname NOT LIKE 'pg_toast%'
          AND relation.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
        ORDER BY namespace.nspname, relation.relname
        """
    ).fetchall()
    return [str(row[0]) for row in rows]


def _psycopg_url(database_url: str) -> str:
    value = str(database_url or "").strip()
    if not value:
        raise ValueError("DATABASE_URL is required")
    if value.startswith("postgresql+psycopg://"):
        value = "postgresql://" + value.removeprefix("postgresql+psycopg://")
    if not value.startswith(("postgresql://", "postgres://")):
        raise ValueError("DATABASE_URL must use PostgreSQL")
    return value


def _safe_target(database_url: str) -> str:
    parsed = urlsplit(database_url)
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    database = parsed.path.lstrip("/")
    return urlunsplit(("postgresql", f"{host}{port}", f"/{database}", "", ""))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install an empty AI-CRM PostgreSQL database or upgrade an Alembic-managed one."
    )
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--baseline", type=Path, default=BASELINE_PATH)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = install_or_upgrade_database(args.database_url, baseline_path=args.baseline)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": type(exc).__name__,
                    "message": redact_sensitive_text(str(exc), args.database_url),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps({"ok": True, **asdict(result)}, ensure_ascii=False, sort_keys=True))
    return 0


def redact_sensitive_text(message: str, database_url: str) -> str:
    raw_url = str(database_url or "")
    redacted = message.replace(raw_url, "[database-url-redacted]") if raw_url else message
    try:
        parsed = urlsplit(raw_url)
    except ValueError:
        return redacted
    if parsed.password:
        redacted = redacted.replace(parsed.password, "***")
    return redacted


if __name__ == "__main__":
    sys.exit(main())
