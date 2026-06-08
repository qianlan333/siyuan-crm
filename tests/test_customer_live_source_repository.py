from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from aicrm_next.customer_read_model.repo import _DEFAULT_LIVE_SOURCE_LIST_LIMIT, build_customer_live_source_repository


def _execute_all(session, statements: list[str]) -> None:
    for statement in statements:
        session.execute(text(statement))
    session.commit()


def test_live_source_repository_reads_existing_customer_source_tables(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://customer:customer@127.0.0.1:1/aicrm_customer")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")

    engine = create_engine("sqlite:///:memory:", future=True)
    session = sessionmaker(bind=engine, future=True)()
    _execute_all(
        session,
        [
            """
            CREATE TABLE contacts (
                id INTEGER PRIMARY KEY,
                external_userid TEXT,
                customer_name TEXT,
                owner_userid TEXT,
                remark TEXT,
                description TEXT,
                updated_at TEXT
            )
            """,
            """
            CREATE TABLE people (
                id INTEGER PRIMARY KEY,
                mobile TEXT,
                third_party_user_id TEXT,
                updated_at TEXT
            )
            """,
            """
            CREATE TABLE external_contact_bindings (
                external_userid TEXT PRIMARY KEY,
                person_id INTEGER,
                first_owner_userid TEXT,
                last_owner_userid TEXT,
                updated_at TEXT
            )
            """,
            """
            CREATE TABLE wecom_external_contact_identity_map (
                id INTEGER PRIMARY KEY,
                external_userid TEXT,
                unionid TEXT,
                openid TEXT,
                follow_user_userid TEXT,
                name TEXT,
                status TEXT,
                updated_at TEXT
            )
            """,
            """
            CREATE TABLE wecom_external_contact_follow_users (
                id INTEGER PRIMARY KEY,
                external_userid TEXT,
                user_id TEXT,
                relation_status TEXT,
                is_primary INTEGER,
                remark TEXT,
                description TEXT,
                updated_at TEXT
            )
            """,
            """
            CREATE TABLE contact_tags (
                id INTEGER PRIMARY KEY,
                external_userid TEXT,
                userid TEXT,
                tag_id TEXT,
                tag_name TEXT,
                created_at TEXT
            )
            """,
            """
            CREATE TABLE class_user_status_current (
                external_userid TEXT PRIMARY KEY,
                signup_status TEXT,
                signup_label_name TEXT,
                customer_name_snapshot TEXT,
                owner_userid_snapshot TEXT,
                mobile_snapshot TEXT,
                status_flags_json TEXT,
                updated_at TEXT
            )
            """,
            """
            CREATE TABLE archived_messages (
                id INTEGER PRIMARY KEY,
                msgid TEXT,
                chat_type TEXT,
                external_userid TEXT,
                owner_userid TEXT,
                sender TEXT,
                receiver TEXT,
                msgtype TEXT,
                content TEXT,
                send_time TEXT,
                raw_payload TEXT,
                created_at TEXT
            )
            """,
            """
            CREATE TABLE owner_role_map (
                userid TEXT PRIMARY KEY,
                display_name TEXT
            )
            """,
            """
            INSERT INTO contacts VALUES
            (1, 'wx_ext_001', '源表客户', 'owner-a', '重点备注', '客户描述', '2026-06-02T08:00:00+00:00')
            """,
            "INSERT INTO people VALUES (1, '13800138000', 'third-party-1', '2026-06-02T08:00:00+00:00')",
            """
            INSERT INTO external_contact_bindings VALUES
            ('wx_ext_001', 1, 'owner-a', 'owner-a', '2026-06-02T08:01:00+00:00')
            """,
            """
            INSERT INTO wecom_external_contact_identity_map VALUES
            (1, 'wx_ext_001', 'union-1', 'openid-1', 'owner-a', '身份客户名', 'active', '2026-06-02T08:02:00+00:00')
            """,
            """
            INSERT INTO wecom_external_contact_follow_users VALUES
            (1, 'wx_ext_001', 'owner-a', 'active', 1, '跟进备注', '跟进描述', '2026-06-02T08:03:00+00:00')
            """,
            "INSERT INTO contact_tags VALUES (1, 'wx_ext_001', 'owner-a', 'tag-1', '重点跟进', '2026-06-02T08:04:00+00:00')",
            """
            INSERT INTO class_user_status_current VALUES
            ('wx_ext_001', 'activated', '已激活', '状态快照名', 'owner-a', '13800138000',
             '{"activation_bucket":"activated"}', '2026-06-02T08:05:00+00:00')
            """,
            """
            INSERT INTO archived_messages VALUES
            (1, 'msg-1', 'single', 'wx_ext_001', 'owner-a', 'customer', 'owner-a', 'text',
             '你好', '2026-06-02T08:06:00+00:00', '{}', '2026-06-02T08:06:00+00:00')
            """,
            "INSERT INTO owner_role_map VALUES ('owner-a', '顾问甲')",
        ],
    )

    repo = build_customer_live_source_repository(session=session)

    rows = repo.list_customers({"keyword": "重点"}, limit=50, offset=0)
    detail = repo.get_customer("wx_ext_001")
    messages = repo.list_recent_messages("wx_ext_001", limit=10)
    timeline = repo.list_timeline("wx_ext_001", limit=10)

    assert rows[0]["external_userid"] == "wx_ext_001"
    assert rows[0]["customer_name"] == "状态快照名"
    assert rows[0]["owner_display_name"] == "顾问甲"
    assert rows[0]["mobile"] == "13800138000"
    assert rows[0]["binding"]["binding_status"] == "bound"
    assert rows[0]["tags"] == ["重点跟进"]
    assert rows[0]["class_user_status"]["activation_bucket"] == "activated"
    assert detail["identity"]["unionid"] == "union-1"
    assert messages[0]["msgid"] == "msg-1"
    assert timeline[0]["event_type"] == "message"


def test_live_source_repository_uses_safe_default_limit_when_limit_is_none(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://customer:customer@127.0.0.1:1/aicrm_customer")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")

    executed_params: list[dict] = []

    class FakeResult:
        def mappings(self):
            return []

        def scalar_one(self):
            return 0

    class FakeSession:
        def execute(self, statement, params=None):
            executed_params.append(dict(params or {}))
            return FakeResult()

    repo = build_customer_live_source_repository(session=FakeSession())

    assert repo.list_customers(limit=None, offset=0) == []
    assert executed_params[-1]["limit"] == _DEFAULT_LIVE_SOURCE_LIST_LIMIT
    assert executed_params[-1]["limit"] != 100000
