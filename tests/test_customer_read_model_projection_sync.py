from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from aicrm_next.customer_read_model.backfill import (
    CustomerReadModelBackfillService,
    LiveSourceCustomerReadModelSource,
)
from aicrm_next.customer_read_model.models import metadata as customer_read_model_metadata
from aicrm_next.customer_read_model.repo import SqlAlchemyCustomerReadModelRepository


MASKED_EXTERNAL_USERID = "external_user_masked_001"
MASKED_MOBILE = "mobile_masked_001"


def _engine():
    engine = create_engine("sqlite:///:memory:", future=True)
    customer_read_model_metadata.create_all(engine)
    _create_source_tables(engine)
    return engine


def _create_source_tables(engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE contacts (
                    id integer primary key,
                    external_userid varchar(128),
                    customer_name varchar(255),
                    remark varchar(255),
                    description text,
                    owner_userid varchar(128),
                    updated_at text,
                    created_at text
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE external_contact_bindings (
                    id integer primary key,
                    external_userid varchar(128),
                    person_id integer,
                    first_bound_by_userid varchar(128),
                    first_owner_userid varchar(128),
                    last_owner_userid varchar(128),
                    updated_at text,
                    created_at text
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE people (
                    id integer primary key,
                    mobile varchar(32),
                    third_party_user_id varchar(128),
                    updated_at text
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE archived_messages (
                    id integer primary key,
                    msgid varchar(128),
                    chat_type varchar(40),
                    external_userid varchar(128),
                    owner_userid varchar(128),
                    sender varchar(128),
                    receiver varchar(128),
                    msgtype varchar(40),
                    content text,
                    send_time text,
                    created_at text
                )
                """
            )
        )


def _seed_source(engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO contacts (
                    external_userid, customer_name, remark, description, owner_userid, updated_at, created_at
                )
                VALUES (
                    :external_userid, 'masked customer', 'masked remark', 'masked description',
                    'owner_masked_001', '2026-06-09T08:00:00+00:00', '2026-06-09T07:00:00+00:00'
                )
                """
            ),
            {"external_userid": MASKED_EXTERNAL_USERID},
        )
        connection.execute(
            text(
                """
                INSERT INTO external_contact_bindings (
                    external_userid, person_id, first_owner_userid, last_owner_userid, updated_at, created_at
                )
                VALUES (
                    :external_userid, 1, 'owner_masked_001', 'owner_masked_001',
                    '2026-06-09T08:05:00+00:00', '2026-06-09T07:05:00+00:00'
                )
                """
            ),
            {"external_userid": MASKED_EXTERNAL_USERID},
        )
        connection.execute(
            text(
                """
                INSERT INTO people (id, mobile, third_party_user_id, updated_at)
                VALUES (1, :mobile, 'third_party_user_masked_001', '2026-06-09T08:06:00+00:00')
                """
            ),
            {"mobile": MASKED_MOBILE},
        )
        connection.execute(
            text(
                """
                INSERT INTO archived_messages (
                    msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, created_at
                )
                VALUES (
                    'msg_masked_001', 'single', :external_userid, 'owner_masked_001',
                    :external_userid, 'owner_masked_001', 'text', 'masked message',
                    '2026-06-09T08:10:00+00:00', '2026-06-09T08:10:01+00:00'
                )
                """
            ),
            {"external_userid": MASKED_EXTERNAL_USERID},
        )


def _session(engine):
    return sessionmaker(bind=engine, future=True)()


def _count(engine, table: str) -> int:
    with engine.begin() as connection:
        return int(connection.execute(text(f"select count(*) from {table}")).scalar_one() or 0)


def test_sync_customer_read_model_dry_run_does_not_write_projection() -> None:
    engine = _engine()
    _seed_source(engine)
    session = _session(engine)

    result = CustomerReadModelBackfillService(
        source=LiveSourceCustomerReadModelSource(session),
        target_repo=SqlAlchemyCustomerReadModelRepository(session),
    ).run(dry_run=True)

    assert result.dry_run is True
    assert result.source_customer_count == 1
    assert result.projected_customer_count == 1
    assert _count(engine, "customer_detail_snapshot_next") == 0


def test_live_source_generates_projection_payload_from_contacts_bindings_people() -> None:
    engine = _engine()
    _seed_source(engine)
    source = LiveSourceCustomerReadModelSource(_session(engine))

    customers = source.list_customers()

    assert len(customers) == 1
    customer = customers[0]
    assert customer["external_userid"] == MASKED_EXTERNAL_USERID
    assert customer["customer_name"] == "masked customer"
    assert customer["binding"]["is_bound"] is True
    assert customer["mobile"] == MASKED_MOBILE


def test_sync_customer_read_model_empty_source_returns_zero_counts() -> None:
    engine = _engine()
    session = _session(engine)

    result = CustomerReadModelBackfillService(
        source=LiveSourceCustomerReadModelSource(session),
        target_repo=SqlAlchemyCustomerReadModelRepository(session),
    ).run(dry_run=False)

    assert result.source_customer_count == 0
    assert result.projected_customer_count == 0
    assert result.skipped_count == 0
    assert _count(engine, "customer_detail_snapshot_next") == 0


def test_sync_customer_read_model_writes_detail_snapshot_and_is_idempotent() -> None:
    engine = _engine()
    _seed_source(engine)
    session = _session(engine)
    service = CustomerReadModelBackfillService(
        source=LiveSourceCustomerReadModelSource(session),
        target_repo=SqlAlchemyCustomerReadModelRepository(session),
    )

    first = service.run(dry_run=False)
    second = CustomerReadModelBackfillService(
        source=LiveSourceCustomerReadModelSource(_session(engine)),
        target_repo=SqlAlchemyCustomerReadModelRepository(_session(engine)),
    ).run(dry_run=False)

    assert first.detail_snapshot_count == 1
    assert second.detail_snapshot_count == 1
    assert _count(engine, "customer_list_index_next") == 1
    assert _count(engine, "customer_detail_snapshot_next") == 1
    assert _count(engine, "customer_timeline_event_next") == 1
    assert _count(engine, "customer_recent_message_next") == 1


def test_sync_customer_read_model_output_masks_identifiers() -> None:
    engine = _engine()
    _seed_source(engine)
    session = _session(engine)

    result = CustomerReadModelBackfillService(
        source=LiveSourceCustomerReadModelSource(session),
        target_repo=SqlAlchemyCustomerReadModelRepository(session),
    ).run(dry_run=True)
    payload = json.dumps(result.to_dict(), ensure_ascii=False)

    assert MASKED_EXTERNAL_USERID not in payload
    assert MASKED_MOBILE not in payload
    assert "***" in payload


def test_customer_sidebar_endpoints_do_not_schema_missing_503_after_projection_sync(monkeypatch, tmp_path) -> None:
    TestClient = pytest.importorskip("fastapi.testclient").TestClient

    from aicrm_next.main import create_app
    from aicrm_next.shared.db_session import get_engine, get_session_factory, reset_engine_cache_for_tests

    database_url = f"sqlite:///{tmp_path / 'projection.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("CUSTOMER_READ_MODEL_REPO_BACKEND", "sqlalchemy")
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    reset_engine_cache_for_tests()
    engine = get_engine()
    customer_read_model_metadata.create_all(engine)
    _create_source_tables(engine)
    _seed_source(engine)

    session = get_session_factory()()
    CustomerReadModelBackfillService(
        source=LiveSourceCustomerReadModelSource(session),
        target_repo=SqlAlchemyCustomerReadModelRepository(session),
    ).run(dry_run=False)

    client = TestClient(create_app())
    responses = [
        client.get(f"/api/customers/{MASKED_EXTERNAL_USERID}"),
        client.get(f"/api/customers/{MASKED_EXTERNAL_USERID}/timeline"),
        client.get(f"/api/sidebar/customer-context?external_userid={MASKED_EXTERNAL_USERID}"),
        client.get(f"/api/sidebar/profile?external_userid={MASKED_EXTERNAL_USERID}"),
    ]

    assert all(response.status_code != 503 for response in responses)
    assert all("schema" not in response.text.lower() for response in responses)
    assert responses[0].status_code == 200
