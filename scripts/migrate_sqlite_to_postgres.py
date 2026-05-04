from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

try:
    import psycopg
except ImportError as exc:  # pragma: no cover
    raise SystemExit("psycopg is required. Install requirements first.") from exc


TABLES = {
    "archived_messages": {
        "columns": [
            "id",
            "seq",
            "msgid",
            "chat_type",
            "external_userid",
            "owner_userid",
            "sender",
            "receiver",
            "msgtype",
            "content",
            "send_time",
            "raw_payload",
            "created_at",
        ],
        "conflict": "msgid",
        "update_columns": [
            "seq",
            "chat_type",
            "external_userid",
            "owner_userid",
            "sender",
            "receiver",
            "msgtype",
            "content",
            "send_time",
            "raw_payload",
            "created_at",
        ],
    },
    "contacts": {
        "columns": ["id", "external_userid", "customer_name", "owner_userid", "remark", "description", "updated_at"],
        "conflict": "external_userid",
        "update_columns": ["customer_name", "owner_userid", "remark", "description", "updated_at"],
    },
    "group_chats": {
        "columns": [
            "id",
            "chat_id",
            "group_name",
            "owner_userid",
            "notice",
            "member_count",
            "status",
            "create_time",
            "dismissed_at",
            "raw_payload",
            "updated_at",
        ],
        "conflict": "chat_id",
        "update_columns": [
            "group_name",
            "owner_userid",
            "notice",
            "member_count",
            "status",
            "create_time",
            "dismissed_at",
            "raw_payload",
            "updated_at",
        ],
    },
    "app_settings": {
        "columns": ["key", "value", "updated_at"],
        "conflict": "key",
        "update_columns": ["value", "updated_at"],
    },
    "sync_runs": {
        "columns": [
            "id",
            "status",
            "start_time",
            "end_time",
            "owner_userid",
            "cursor",
            "fetched_count",
            "inserted_count",
            "raw_response",
            "error_message",
            "created_at",
            "finished_at",
        ],
        "conflict": "id",
        "update_columns": [
            "status",
            "start_time",
            "end_time",
            "owner_userid",
            "cursor",
            "fetched_count",
            "inserted_count",
            "raw_response",
            "error_message",
            "created_at",
            "finished_at",
        ],
    },
    "outbound_tasks": {
        "columns": ["id", "task_type", "request_payload", "response_payload", "wecom_task_id", "status", "created_at"],
        "conflict": "id",
        "update_columns": ["task_type", "request_payload", "response_payload", "wecom_task_id", "status", "created_at"],
    },
    "contact_tags": {
        "columns": ["id", "external_userid", "userid", "tag_id", "tag_name", "created_at"],
        "conflict": "external_userid, userid, tag_id",
        "update_columns": ["tag_name", "created_at"],
    },
    "archive_sync_state": {
        "columns": ["state_key", "last_seq", "updated_at"],
        "conflict": "state_key",
        "update_columns": ["last_seq", "updated_at"],
    },
}

SEQUENCE_TABLES = {
    "archived_messages": "id",
    "contacts": "id",
    "group_chats": "id",
    "sync_runs": "id",
    "outbound_tasks": "id",
    "contact_tags": "id",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate SQLite data into PostgreSQL")
    parser.add_argument("--sqlite-path", required=True)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--schema-path", default="wecom_ability_service/schema_postgres.sql")
    parser.add_argument("--truncate-target", action="store_true")
    return parser.parse_args()


def sqlite_count(conn: sqlite3.Connection, table_name: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])


def postgres_count(conn, table_name: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        return int(cur.fetchone()[0])


def run_schema(conn, schema_path: Path) -> None:
    sql = schema_path.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        for statement in [item.strip() for item in sql.split(";") if item.strip()]:
            cur.execute(statement)
    conn.commit()


def migrate_table(sqlite_conn: sqlite3.Connection, pg_conn, table_name: str, config: dict, truncate_target: bool) -> dict:
    columns = config["columns"]
    column_sql = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    update_sql = ", ".join([f"{column} = EXCLUDED.{column}" for column in config["update_columns"]])
    conflict = config["conflict"]

    source_rows = sqlite_conn.execute(f"SELECT {column_sql} FROM {table_name}").fetchall()
    before_count = len(source_rows)

    with pg_conn.cursor() as cur:
        if truncate_target:
            cur.execute(f"TRUNCATE TABLE {table_name} RESTART IDENTITY CASCADE")
        if source_rows:
            sql = (
                f"INSERT INTO {table_name} ({column_sql}) VALUES ({placeholders}) "
                f"ON CONFLICT ({conflict}) DO UPDATE SET {update_sql}"
            )
            cur.executemany(sql, source_rows)
    pg_conn.commit()

    after_count = postgres_count(pg_conn, table_name)
    return {"before_count": before_count, "after_count": after_count}


def reset_sequences(pg_conn) -> None:
    with pg_conn.cursor() as cur:
        for table_name, id_column in SEQUENCE_TABLES.items():
            cur.execute(
                """
                SELECT pg_get_serial_sequence(%s, %s)
                """,
                (table_name, id_column),
            )
            sequence_name = cur.fetchone()[0]
            if not sequence_name:
                continue
            cur.execute(
                f"SELECT setval(%s, COALESCE((SELECT MAX({id_column}) FROM {table_name}), 1), true)",
                (sequence_name,),
            )
    pg_conn.commit()


def main() -> None:
    args = parse_args()
    sqlite_path = Path(args.sqlite_path)
    schema_path = Path(args.schema_path)
    sqlite_conn = sqlite3.connect(sqlite_path)
    pg_conn = psycopg.connect(args.database_url)

    try:
        run_schema(pg_conn, schema_path)
        summary: dict[str, dict] = {}
        for table_name, config in TABLES.items():
            summary[table_name] = migrate_table(sqlite_conn, pg_conn, table_name, config, args.truncate_target)
        reset_sequences(pg_conn)
        print(
            json.dumps(
                {
                    "ok": True,
                    "sqlite_path": str(sqlite_path),
                    "database_url": args.database_url,
                    "truncate_target": args.truncate_target,
                    "tables": summary,
                    "notes": [
                        "TEXT/JSON payload fields keep their original string form.",
                        "Primary key ids are preserved for migrated rows and PostgreSQL sequences are reset to max(id).",
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    main()
