from __future__ import annotations

import base64
from datetime import datetime
from io import BytesIO
import json
from zipfile import ZipFile

import pytest

from wecom_ability_service import create_app
from wecom_ability_service import wecom_client as wecom_client_module
from wecom_ability_service.db import get_db, init_db
from wecom_ability_service.domains.routing_config import (
    DEFAULT_DELIVERY_ROUTE_OWNER_USERID,
    DEFAULT_SALES_ROUTE_OWNER_USERID,
)
from wecom_ability_service.routes import _process_external_contact_event
from wecom_ability_service.http.common import _contact_sync_retry_limit
from wecom_ability_service.services import (
    _default_owner_class_term_backfill_entry_source,
    backfill_class_term_for_owner,
    backfill_owner_class_terms_into_lead_pool,
    get_routing_config,
    import_experience_leads,
    log_external_contact_event,
    migrate_legacy_user_ops_pool_to_lead_pool,
    refresh_contact_tags_for_external_userid,
    refresh_user_ops_contact_tags_for_external_userid,
    refresh_user_ops_contact_tags_for_owner,
    resolve_contact_routing_context,
    schedule_user_ops_auto_assign_class_term_job,
    sync_user_ops_class_term_tag_definitions,
    upsert_user_ops_lead_pool_member,
)


def _test_image_data_url(label: str = "page") -> str:
    encoded = base64.b64encode(f"page-image-{label}".encode("utf-8")).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _test_png_bytes() -> bytes:
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+b5f0AAAAASUVORK5CYII="
    )


def _build_batch_send_form_data(
    *,
    selection_mode: str,
    content: str = "",
    selected_ids: list[int] | None = None,
    excluded_ids: list[int] | None = None,
    filters: dict | None = None,
    include_do_not_disturb: bool = False,
    confirm: bool = False,
    operator: str = "",
    images: list[tuple[str, bytes, str]] | None = None,
):
    payload = {
        "selection_mode": selection_mode,
        "content": content,
        "filters_json": json.dumps(filters or {}, ensure_ascii=False),
        "selected_ids_json": json.dumps(selected_ids or []),
        "excluded_ids_json": json.dumps(excluded_ids or []),
        "include_do_not_disturb": "true" if include_do_not_disturb else "false",
    }
    if confirm:
        payload["confirm"] = "true"
    if operator:
        payload["operator"] = operator
    if images:
        payload["images"] = [(BytesIO(file_bytes), file_name, mime_type) for file_name, file_bytes, mime_type in images]
    return payload


@pytest.fixture()
def app(tmp_path):
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(tmp_path) as app:
        yield app


@pytest.fixture()
def client(app):
    c = app.test_client()
    # 注入 break-glass 管理员 session，让 admin 页面不被 302 重定向
    with c.session_transaction() as sess:
        sess["admin_session_user_id"] = 0
        sess["admin_session_wecom_userid"] = ""
        sess["admin_session_role_list"] = ["super_admin"]
        sess["admin_session_login_type"] = "break_glass"
        sess["admin_session_display_name"] = "test-admin"
        sess["admin_session_break_glass_username"] = "test-admin"
    return c


def _seed_user_ops_sources(app) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO owner_role_map (userid, display_name, role, active)
            VALUES (?, ?, ?, ?), (?, ?, ?, ?)
            """,
            ("sales_01", "ZhaoYanFang", "sales", True, "sales_02", "QianLan", "sales", True),
        )
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?)
            """,
            (
                "wm_signed_999",
                "已报999用户",
                "sales_01",
                "",
                "wm_signed_999",
                now,
                "wm_signed_3999",
                "已报3999用户",
                "sales_02",
                "",
                "wm_signed_3999",
                now,
                "wm_lead_bound",
                "已绑定引流用户",
                "sales_01",
                "",
                "wm_lead_bound",
                now,
            ),
        )
        db.execute(
            """
            INSERT INTO people (id, mobile, third_party_user_id, created_at, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP), (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (1, "13800138000", "tp-001", 2, "13800138002", "tp-002"),
        )
        db.execute(
            """
            INSERT INTO external_contact_bindings (
                external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                   (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                "wm_signed_999",
                1,
                "sales_01",
                "sales_01",
                "sales_01",
                "wm_lead_bound",
                2,
                "sales_01",
                "sales_01",
                "sales_01",
            ),
        )
        db.execute(
            """
            INSERT INTO class_user_status_current (
                external_userid, signup_status, signup_label_name, customer_name_snapshot, owner_userid_snapshot,
                mobile_snapshot, set_by_userid, set_at, wecom_tag_sync_status, wecom_tag_sync_error, status_flags_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?),
                   (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
            """,
            (
                "wm_signed_999",
                "signed_999",
                "已报名999",
                "999快照用户",
                "sales_01",
                "13800138000",
                "sales_01",
                "success",
                "",
                "{}",
                "wm_signed_3999",
                "signed_3999",
                "已报名3999",
                "3999快照用户",
                "sales_02",
                "13800138001",
                "sales_02",
                "success",
                "",
                "{}",
            ),
        )
        db.commit()


def _insert_contact_tags(app, rows: list[tuple[str, str, str, str]]) -> None:
    with app.app_context():
        db = get_db()
        for external_userid, userid, tag_id, tag_name in rows:
            db.execute(
                """
                INSERT INTO contact_tags (external_userid, userid, tag_id, tag_name)
                VALUES (?, ?, ?, ?)
                """,
                (external_userid, userid, tag_id, tag_name),
            )
        db.commit()


def _seed_zhao_contact(
    app,
    *,
    external_userid: str,
    customer_name: str = "赵顾问新客",
) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with app.app_context():
        db = get_db()
        existing_owner = db.execute(
            "SELECT 1 FROM owner_role_map WHERE userid = ? LIMIT 1",
            ("ZhaoYanFang",),
        ).fetchone()
        if not existing_owner:
            db.execute(
                """
                INSERT INTO owner_role_map (userid, display_name, role, active)
                VALUES (?, ?, ?, ?)
                """,
                ("ZhaoYanFang", "ZhaoYanFang", "sales", True),
            )
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                external_userid,
                customer_name,
                "ZhaoYanFang",
                "",
                external_userid,
                now,
            ),
        )
        db.commit()


def _seed_owner_backfill_follow_relation(
    app,
    *,
    external_userid: str,
    owner_userid: str = "ZhaoYanFang",
    relation_status: str = "active",
) -> None:
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO wecom_external_contact_follow_users (
                corp_id, external_userid, user_id, relation_status, is_primary, remark, description,
                raw_follow_user, first_seen_at, last_seen_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                "ww-test",
                external_userid,
                owner_userid,
                relation_status,
                True,
                "",
                "",
                "{}",
            ),
        )
        db.commit()


def _seed_owner_backfill_binding(
    app,
    *,
    external_userid: str,
    mobile: str,
    owner_userid: str = "ZhaoYanFang",
    person_id: int = 101,
) -> None:
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO people (id, mobile, third_party_user_id, created_at, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (person_id, mobile, f"tp-{person_id}"),
        )
        db.execute(
            """
            INSERT INTO external_contact_bindings (
                external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (external_userid, person_id, owner_userid, owner_userid, owner_userid),
        )
        db.commit()


def _seed_sidebar_contact(
    app,
    *,
    external_userid: str,
    owner_userid: str = "sales_01",
    customer_name: str = "侧边栏客户",
) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with app.app_context():
        db = get_db()
        existing_owner = db.execute(
            "SELECT 1 FROM owner_role_map WHERE userid = ? LIMIT 1",
            (owner_userid,),
        ).fetchone()
        if not existing_owner:
            db.execute(
                """
                INSERT INTO owner_role_map (userid, display_name, role, active)
                VALUES (?, ?, ?, ?)
                """,
                (owner_userid, owner_userid, "sales", True),
            )
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                external_userid,
                customer_name,
                owner_userid,
                "",
                external_userid,
                now,
            ),
        )
        db.commit()


def _build_external_contact_detail(
    *,
    external_userid: str,
    owner_userid: str,
    customer_name: str = "回调客户",
    follow_user_tags: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    return {
        "external_contact": {
            "external_userid": external_userid,
            "name": customer_name,
            "unionid": f"union-{external_userid}",
            "openid": f"openid-{external_userid}",
        },
        "follow_user": [
            {
                "userid": owner_userid,
                "remark": "",
                "description": external_userid,
                "tags": list(follow_user_tags or []),
            }
        ],
    }


class _FakeCallbackContactClient:
    def __init__(self, detail: dict[str, object]):
        self._detail = detail

    def get_contact(self, external_userid: str) -> dict[str, object]:
        assert external_userid == self._detail["external_contact"]["external_userid"]
        return dict(self._detail)

    def update_contact_description(self, payload: dict[str, object]) -> dict[str, object]:
        return {"errcode": 0, "errmsg": "ok", **payload}


def _build_corp_tag_payload(
    tags: list[tuple[str, str]],
    *,
    group_name: str = "9.9元改变计划",
    group_id: str = "group-term",
) -> dict[str, object]:
    return {
        "tag_group": [
            {
                "group_name": group_name,
                "group_id": group_id,
                "tag": [{"id": tag_id, "name": tag_name} for tag_id, tag_name in tags],
            }
        ]
    }


class _FakeUserOpsContactClient:
    def __init__(
        self,
        *,
        corp_tag_payload: dict[str, object] | None = None,
        contact_details: dict[str, dict[str, object]] | None = None,
    ) -> None:
        self._corp_tag_payload = corp_tag_payload or _build_corp_tag_payload(
            [
                ("tag-term-1", "首期7天改变计划"),
                ("tag-term-3", "0322改变计划-第3期"),
                ("tag-term-4", "0330改变计划-第4期"),
            ]
        )
        self._contact_details = dict(contact_details or {})

    def set_contact_detail(self, external_userid: str, detail: dict[str, object]) -> None:
        self._contact_details[external_userid] = detail

    def list_external_contact_tags(self, payload: dict[str, object] | None = None) -> dict[str, object]:
        return dict(self._corp_tag_payload)

    def get_contact(self, external_userid: str) -> dict[str, object]:
        if external_userid not in self._contact_details:
            return _build_external_contact_detail(
                external_userid=external_userid,
                owner_userid="",
                follow_user_tags=[],
            )
        return dict(self._contact_details[external_userid])


@pytest.fixture()
def user_ops_contact_client(monkeypatch):
    fake_client = _FakeUserOpsContactClient()
    monkeypatch.setattr("wecom_ability_service.services._user_ops_contact_client", lambda: fake_client)
    monkeypatch.setattr("wecom_ability_service.infra.user_ops_runtime.get_user_ops_contact_client", lambda: fake_client)
    return fake_client


def _build_test_xlsx(rows: list[list[str] | str]) -> bytes:
    normalized_rows: list[list[str]] = []
    shared_values: list[str] = []
    for row in rows:
        if isinstance(row, str):
            normalized = [row]
        else:
            normalized = [str(item) for item in row]
        normalized_rows.append(normalized)
        shared_values.extend(normalized)
    shared_strings = "".join(f"<si><t>{value}</t></si>" for value in shared_values)
    sheet_rows = []
    shared_index = 0
    for row_index, row in enumerate(normalized_rows, start=1):
        cells = []
        for column_index, _ in enumerate(row, start=1):
            column_name = chr(64 + column_index)
            cells.append(f'<c r="{column_name}{row_index}" t="s"><v>{shared_index}</v></c>')
            shared_index += 1
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "xl/sharedStrings.xml",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f"{shared_strings}"
                "</sst>"
            ),
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                "<sheetData>"
                f"{''.join(sheet_rows)}"
                "</sheetData>"
                "</worksheet>"
            ),
        )
    return buffer.getvalue()


def test_user_ops_reload_endpoint_is_deprecated_internal_only(client):
    response = client.post("/api/admin/user-ops/reload")
    payload = response.get_json()

    assert response.status_code == 410
    assert payload["ok"] is False
    assert payload["error"] == "deprecated_internal_only"


def _seed_user_ops_lead_pool_read_model(app) -> None:
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO owner_role_map (userid, display_name, role, active)
            VALUES (?, ?, ?, ?), (?, ?, ?, ?)
            ON CONFLICT(userid) DO UPDATE SET display_name = excluded.display_name, role = excluded.role, active = excluded.active
            """,
            ("sales_01", "ZhaoYanFang", "sales", True, "sales_02", "QianLan", "sales", True),
        )
        db.execute(
            """
            INSERT INTO user_ops_lead_pool_current (
                mobile, external_userid, customer_name, owner_userid,
                is_wecom_added, is_mobile_bound, huangxiaocan_activation_state,
                class_term_no, class_term_label, first_entry_source, last_entry_source,
                created_at, updated_at
            )
            VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                "13800138002",
                "wm_lead_bound",
                "已绑定引流用户",
                "sales_01",
                True,
                True,
                "activated",
                6,
                "6期",
                "student_import",
                "student_import",
                "",
                "wm_external_only_001",
                "外部联系人",
                "sales_02",
                True,
                False,
                "unknown",
                5,
                "5期",
                "sidebar_class_term",
                "verify_class_term_tag_and_upsert_lead_pool",
                "13800138061",
                "",
                "",
                "",
                False,
                False,
                "not_activated",
                4,
                "4期",
                "student_import",
                "huangxiaocan_activation_import",
                "13800138062",
                "",
                "",
                "",
                False,
                False,
                "unknown",
                None,
                "",
                "student_import",
                "student_import",
            ),
        )
        db.execute(
            """
            INSERT INTO people (id, mobile, third_party_user_id, created_at, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (201, "13800138002", "tp-page-201"),
        )
        db.execute(
            """
            INSERT INTO external_contact_bindings (
                external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            ("wm_lead_bound", 201, "sales_01", "sales_01", "sales_01"),
        )
        db.execute(
            """
            INSERT INTO user_ops_pool_current (
                mobile, external_userid, customer_name, owner_userid, current_status, is_wecom_bound,
                activation_status, activation_remark, class_term_no, class_term_label, source_type,
                created_at, updated_at
            )
            VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                "13800138002",
                "wm_lead_bound",
                "已绑定引流用户",
                "sales_01",
                "lead_trial",
                True,
                "activated",
                "已激活",
                6,
                "6期",
                "student_import",
                "",
                "wm_external_only_001",
                "外部联系人",
                "sales_02",
                "lead_trial",
                True,
                "not_activated",
                "",
                5,
                "5期",
                "sidebar_class_term",
                "13800138061",
                "",
                "",
                "",
                "lead_trial",
                False,
                "not_activated",
                "未激活",
                4,
                "4期",
                "activation_import",
                "13800138062",
                "",
                "",
                "",
                "lead_trial",
                False,
                "not_activated",
                "",
                None,
                "",
                "student_import",
            ),
        )
        db.execute(
            """
            INSERT INTO user_ops_activation_status_source (
                mobile, activation_status, activation_remark, created_by, is_active, created_at, updated_at
            )
            VALUES
            (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                "13800138002",
                "activated",
                "已激活",
                "test",
                True,
                "13800138061",
                "not_activated",
                "未激活",
                "test",
                True,
            ),
        )
        db.execute(
            """
            INSERT INTO user_ops_lead_pool_history (
                mobile, external_userid, action_type, source_type, operator, before_json, after_json, remark, created_at
            )
            VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP),
            (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                "13800138002",
                "wm_lead_bound",
                "lead_pool_insert",
                "student_import",
                "admin_user_ops",
                "{}",
                '{"mobile":"13800138002","class_term_label":"6期"}',
                "initial insert",
                "",
                "wm_external_only_001",
                "mobile_bind_merge",
                "bind_mobile",
                "sidebar_bind_mobile",
                '{"external_userid":"wm_external_only_001"}',
                '{"mobile":"13800138002","external_userid":"wm_lead_bound"}',
                "merged external-only record",
            ),
        )
        db.commit()


def _seed_user_ops_page_action_data(app) -> None:
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO owner_role_map (userid, display_name, role, active)
            VALUES (?, ?, ?, ?), (?, ?, ?, ?)
            ON CONFLICT(userid) DO UPDATE SET display_name = excluded.display_name, role = excluded.role, active = excluded.active
            """,
            ("sales_01", "ZhaoYanFang", "sales", True, "sales_02", "QianLan", "sales", True),
        )
        db.execute(
            """
            INSERT INTO people (id, mobile, third_party_user_id, created_at, updated_at)
            VALUES
            (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                301,
                "13800138111",
                "tp-page-301",
                302,
                "13800138112",
                "tp-page-302",
                303,
                "13800138113",
                "tp-page-303",
            ),
        )
        db.execute(
            """
            INSERT INTO external_contact_bindings (
                external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid, created_at, updated_at
            )
            VALUES
            (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                "wm_send_auto_dnd",
                301,
                "sales_01",
                "sales_01",
                "sales_01",
                "wm_send_manual_dnd",
                302,
                "sales_01",
                "sales_01",
                "sales_01",
                "wm_send_eligible",
                303,
                "sales_02",
                "sales_02",
                "sales_02",
            ),
        )
        db.execute(
            """
            INSERT INTO class_user_status_current (
                external_userid, signup_status, signup_label_name, customer_name_snapshot, owner_userid_snapshot,
                mobile_snapshot, set_by_userid, set_at, wecom_tag_sync_status, wecom_tag_sync_error, status_flags_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
            """,
            (
                "wm_send_auto_dnd",
                "signed_3999",
                "已报名3999",
                "正价用户",
                "sales_01",
                "13800138111",
                "sales_01",
                "success",
                "",
                "{}",
            ),
        )
        db.execute(
            """
            INSERT INTO user_ops_pool_current (
                mobile, external_userid, customer_name, owner_userid, current_status, is_wecom_bound,
                activation_status, activation_remark, class_term_no, class_term_label, source_type,
                created_at, updated_at
            )
            VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                "13800138111",
                "wm_send_auto_dnd",
                "正价用户",
                "sales_01",
                "lead_trial",
                True,
                "activated",
                "已激活",
                8,
                "8期",
                "student_import",
                "13800138112",
                "wm_send_manual_dnd",
                "手动免打扰用户",
                "sales_01",
                "lead_trial",
                True,
                "not_activated",
                "",
                8,
                "8期",
                "student_import",
                "13800138113",
                "wm_send_eligible",
                "可发送用户",
                "sales_02",
                "lead_trial",
                True,
                "activated",
                "已激活",
                9,
                "9期",
                "student_import",
                "13800138114",
                "",
                "手机号名单用户",
                "sales_02",
                "lead_trial",
                False,
                "not_activated",
                "",
                9,
                "9期",
                "student_import",
                "13800138115",
                "wm_send_no_class_term",
                "无班期用户",
                "sales_02",
                "lead_trial",
                True,
                "activated",
                "已激活",
                None,
                "",
                "student_import",
            ),
        )
        db.execute(
            """
            INSERT INTO user_ops_activation_status_source (
                mobile, activation_status, activation_remark, created_by, is_active, created_at, updated_at
            )
            VALUES
            (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                "13800138111",
                "activated",
                "已激活",
                "test",
                True,
                "13800138112",
                "not_activated",
                "未激活",
                "test",
                True,
                "13800138113",
                "activated",
                "已激活",
                "test",
                True,
                "13800138115",
                "activated",
                "已激活",
                "test",
                True,
            ),
        )
        db.commit()


def test_user_ops_overview_counts_are_correct(client, app):
    _seed_user_ops_lead_pool_read_model(app)

    response = client.get("/api/admin/user-ops/overview")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["lead_pool_total_count"] == 3
    assert payload["wecom_added_count"] == 2
    assert payload["wecom_not_added_count"] == 1
    assert payload["mobile_bound_count"] == 1
    assert payload["mobile_unbound_count"] == 2
    assert payload["huangxiaocan_activated_count"] == 1
    assert payload["huangxiaocan_not_activated_count"] == 2
    assert "huangxiaocan_unknown_count" not in payload
    assert "signed_999_count" not in payload
    assert "signed_3999_count" not in payload


def test_user_ops_overview_counts_phone_centric_union_without_double_count(client, app):
    _seed_user_ops_lead_pool_read_model(app)

    response = client.get("/api/admin/user-ops/overview")
    payload = response.get_json()

    assert response.status_code == 200
    cards = {item["key"]: item["value"] for item in payload["cards"]}
    assert cards["lead_pool_total_count"] == 3
    assert cards["wecom_added_count"] == 2
    assert cards["wecom_not_added_count"] == 1
    assert cards["mobile_bound_count"] == 1
    assert cards["mobile_unbound_count"] == 2
    assert cards["huangxiaocan_activated_count"] == 1
    assert cards["huangxiaocan_not_activated_count"] == 2
    assert "huangxiaocan_unknown_count" not in cards
    assert "signed_999_count" not in cards
    assert "signed_3999_count" not in cards

def test_user_ops_list_ignores_legacy_current_status_filter(client, app):
    _seed_user_ops_lead_pool_read_model(app)

    response = client.get("/api/admin/user-ops/list?current_status=signed_999")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["total"] == 3
    assert "current_status" not in payload["items"][0]


def test_user_ops_list_filters_by_is_wecom_added(client, app):
    _seed_user_ops_lead_pool_read_model(app)

    response = client.get("/api/admin/user-ops/list?is_wecom_added=true")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["total"] == 2
    assert {item["external_userid"] for item in payload["items"]} == {"wm_lead_bound", "wm_external_only_001"}


def test_user_ops_list_filters_by_owner_userid(client, app):
    _seed_user_ops_lead_pool_read_model(app)

    response = client.get("/api/admin/user-ops/list?is_mobile_bound=true&huangxiaocan_activation_state=activated&class_term_no=6")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["total"] == 1
    assert payload["items"][0]["mobile"] == "13800138002"
    assert payload["items"][0]["is_wecom_added"] is True
    assert payload["items"][0]["is_mobile_bound"] is True
    assert payload["items"][0]["huangxiaocan_activation_state"] == "activated"
    assert payload["items"][0]["class_term_no"] == 6


def test_user_ops_export_returns_current_pool_rows(client, app):
    _seed_user_ops_lead_pool_read_model(app)

    response = client.get("/api/admin/user-ops/export?is_wecom_added=true")
    content = response.get_data(as_text=True)

    assert response.status_code == 200
    assert response.mimetype == "application/vnd.ms-excel"
    assert "已绑定引流用户" in content
    assert "13800138062" not in content
    assert "黄小璨激活状态" in content
    assert "是否已绑手机号" in content
    assert "当前状态" not in content
    assert "高意向备注" not in content


def test_user_ops_base_pool_excludes_records_without_class_term_marker(client, app):
    _seed_user_ops_lead_pool_read_model(app)

    overview_payload = client.get("/api/admin/user-ops/overview").get_json()
    list_payload = client.get("/api/admin/user-ops/list").get_json()
    export_response = client.get("/api/admin/user-ops/export")
    export_content = export_response.get_data(as_text=True)

    assert overview_payload["lead_pool_total_count"] == 3
    assert {item["mobile"] for item in list_payload["items"]} == {"13800138002", "13800138061", ""}
    assert all(item["class_term_no"] is not None or item["class_term_label"] for item in list_payload["items"])
    assert "13800138062" not in export_content


def test_user_ops_overview_accepts_new_filters_and_keeps_total_view_for_cards(client, app):
    _seed_user_ops_lead_pool_read_model(app)

    response = client.get("/api/admin/user-ops/overview?wecom_status=added&class_term_no=4")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["filters"]["wecom_status"] == "added"
    cards = {item["key"]: item["value"] for item in payload["cards"]}
    assert cards["lead_pool_total_count"] == 1
    assert cards["wecom_added_count"] == 0
    assert cards["wecom_not_added_count"] == 1
    assert cards["mobile_bound_count"] == 0
    assert cards["mobile_unbound_count"] == 1
    assert cards["huangxiaocan_activated_count"] == 0
    assert cards["huangxiaocan_not_activated_count"] == 1
    assert "huangxiaocan_unknown_count" not in cards


def test_user_ops_list_supports_new_filters_and_derived_fields(client, app):
    _seed_user_ops_lead_pool_read_model(app)

    response = client.get(
        "/api/admin/user-ops/list?wecom_status=added&mobile_binding_status=bound&activation_bucket=activated&class_term_no=6"
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["total"] == 1
    item = payload["items"][0]
    assert item["external_userid"] == "wm_lead_bound"
    assert item["is_added_wecom"] is True
    assert item["is_mobile_bound"] is True
    assert item["activation_bucket"] == "activated"
    assert item["do_not_disturb"] is False
    assert item["do_not_disturb_reasons"] == []
    assert item["can_open_customer_detail"] is True
    assert item["can_batch_send"] is True


def test_user_ops_list_unbound_member_without_external_userid_disables_actions(client, app):
    _seed_user_ops_lead_pool_read_model(app)

    response = client.get("/api/admin/user-ops/list?wecom_status=not_added&mobile_binding_status=unbound&class_term_no=4")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["total"] == 1
    item = payload["items"][0]
    assert item["mobile"] == "13800138061"
    assert item["external_userid"] == ""
    assert item["activation_bucket"] == "not_activated"
    assert item["can_open_customer_detail"] is False
    assert item["can_batch_send"] is False


def test_user_ops_list_bound_member_with_external_userid_keeps_detail_enabled(client, app):
    _seed_user_ops_lead_pool_read_model(app)

    response = client.get("/api/admin/user-ops/list?wecom_status=added&class_term_no=6")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["total"] == 1
    item = payload["items"][0]
    assert item["external_userid"] == "wm_lead_bound"
    assert item["can_open_customer_detail"] is True


def test_user_ops_list_treats_missing_mobile_activation_as_not_activated(client, app):
    _seed_user_ops_lead_pool_read_model(app)

    response = client.get("/api/admin/user-ops/list?wecom_status=added&mobile_binding_status=unbound")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["total"] == 1
    item = payload["items"][0]
    assert item["external_userid"] == "wm_external_only_001"
    assert item["mobile"] == ""
    assert item["activation_bucket"] == "not_activated"
    assert item["activation_bucket_label"] == "黄小璨未激活"


def test_user_ops_do_not_disturb_manual_reason_can_be_enabled_and_cleared(client, app):
    _seed_user_ops_page_action_data(app)

    enable_response = client.post(
        "/api/admin/user-ops/do-not-disturb",
        json={
            "external_userid": "wm_send_auto_dnd",
            "reason_code": "manual_note",
            "reason_text": "运营手动设置",
            "operator": "test_operator",
        },
    )
    enable_payload = enable_response.get_json()

    assert enable_response.status_code == 200
    reason_codes = {item["reason_code"] for item in enable_payload["do_not_disturb_reasons"]}
    assert enable_payload["do_not_disturb"] is True
    assert reason_codes == {"signed_paid_course", "manual_note"}

    disable_response = client.post(
        "/api/admin/user-ops/do-not-disturb",
        json={
            "external_userid": "wm_send_auto_dnd",
            "reason_code": "manual_note",
            "action": "disable",
        },
    )
    disable_payload = disable_response.get_json()

    assert disable_response.status_code == 200
    assert disable_payload["do_not_disturb"] is True
    assert disable_payload["do_not_disturb_reasons"] == [
        {"source_type": "auto", "reason_code": "signed_paid_course", "reason_text": "已报名正价课"}
    ]


def test_user_ops_batch_send_preview_respects_dnd_and_external_userid(client, app):
    _seed_user_ops_page_action_data(app)
    client.post(
        "/api/admin/user-ops/do-not-disturb",
        json={
            "external_userid": "wm_send_manual_dnd",
            "reason_code": "manual_note",
            "reason_text": "运营手动设置",
            "operator": "test_operator",
        },
    )

    response = client.post(
        "/api/admin/user-ops/batch-send/preview",
        json={"selection_mode": "all_filtered", "content": "今天统一跟进"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["selected_count"] == 4
    assert payload["eligible_count"] == 1
    assert payload["skipped_count"] == 3
    assert payload["skipped_by_reason"] == {"do_not_disturb": 2, "missing_external_userid": 1}
    assert payload["skipped_summary"] == "已跳过 3 人：2 人免打扰，1 人缺少 external_userid"
    assert payload["image_count"] == 0
    assert payload["final_targets"] == [
        {
            "id": payload["final_targets"][0]["id"],
            "external_userid": "wm_send_eligible",
            "customer_name": "可发送用户",
            "owner_userid": "sales_02",
            "owner_display_name": "QianLan",
            "mobile": "13800138113",
        }
    ]
    assert payload["sender_buckets"] == [
        {"owner_userid": "sales_02", "owner_display_name": "QianLan", "count": 1}
    ]

    include_response = client.post(
        "/api/admin/user-ops/batch-send/preview",
        json={"selection_mode": "all_filtered", "content": "今天统一跟进", "include_do_not_disturb": True},
    )
    include_payload = include_response.get_json()

    assert include_response.status_code == 200
    assert include_payload["eligible_count"] == 3
    assert include_payload["skipped_by_reason"] == {"missing_external_userid": 1}
    assert include_payload["image_count"] == 0


def test_user_ops_batch_send_preview_supports_manual_selected_items(client, app):
    _seed_user_ops_page_action_data(app)
    client.post(
        "/api/admin/user-ops/do-not-disturb",
        json={
            "external_userid": "wm_send_manual_dnd",
            "reason_code": "manual_note",
            "reason_text": "运营手动设置",
            "operator": "test_operator",
        },
    )

    list_payload = client.get("/api/admin/user-ops/list").get_json()
    items_by_external = {item["external_userid"]: item for item in list_payload["items"]}
    manual_ids = [
        items_by_external["wm_send_manual_dnd"]["id"],
        items_by_external["wm_send_eligible"]["id"],
        next(item["id"] for item in list_payload["items"] if item["external_userid"] == ""),
    ]

    response = client.post(
        "/api/admin/user-ops/batch-send/preview",
        json={
            "selection_mode": "manual",
            "selected_ids": manual_ids,
            "content": "今天统一跟进",
        },
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["selected_count"] == 3
    assert payload["eligible_count"] == 1
    assert payload["skipped_count"] == 2
    assert payload["skipped_by_reason"] == {"do_not_disturb": 1, "missing_external_userid": 1}
    assert [item["external_userid"] for item in payload["final_targets"]] == ["wm_send_eligible"]


def test_user_ops_batch_send_preview_and_execute_exclude_manual_selected_rows_without_class_term(client, app, monkeypatch):
    _seed_user_ops_page_action_data(app)

    with app.app_context():
        db = get_db()
        no_class_term_id = db.execute(
            "SELECT id FROM user_ops_pool_current WHERE external_userid = ?",
            ("wm_send_no_class_term",),
        ).fetchone()["id"]
        eligible_id = db.execute(
            "SELECT id FROM user_ops_pool_current WHERE external_userid = ?",
            ("wm_send_eligible",),
        ).fetchone()["id"]

    preview_response = client.post(
        "/api/admin/user-ops/batch-send/preview",
        json={
            "selection_mode": "manual",
            "selected_ids": [int(eligible_id), int(no_class_term_id)],
            "content": "只测有班期基础池",
        },
    )
    preview_payload = preview_response.get_json()

    assert preview_response.status_code == 200
    assert preview_payload["selected_count"] == 1
    assert preview_payload["eligible_count"] == 1
    assert [item["external_userid"] for item in preview_payload["final_targets"]] == ["wm_send_eligible"]

    calls: list[dict[str, object]] = []

    def fake_dispatch(task_type: str, fn_name: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append({"task_type": task_type, "fn_name": fn_name, "payload": payload})
        return {"task_id": 980 + len(calls), "wecom_result": {"msgid": f"page-task-class-{len(calls)}"}}

    monkeypatch.setattr("wecom_ability_service.domains.user_ops.page_service.dispatch_wecom_task", fake_dispatch)

    execute_response = client.post(
        "/api/admin/user-ops/batch-send/execute",
        json={
            "selection_mode": "manual",
            "selected_ids": [int(eligible_id), int(no_class_term_id)],
            "content": "只测有班期基础池",
            "confirm": True,
        },
    )
    execute_payload = execute_response.get_json()

    assert execute_response.status_code == 200
    assert execute_payload["selected_count"] == 1
    assert execute_payload["eligible_count"] == 1
    assert execute_payload["sent_count"] == 1
    assert len(calls) == 1
    assert calls[0]["payload"]["external_userid"] == ["wm_send_eligible"]


def test_user_ops_batch_send_preview_supports_emoji_and_images(client, app):
    _seed_user_ops_page_action_data(app)
    list_payload = client.get("/api/admin/user-ops/list").get_json()
    items_by_external = {item["external_userid"]: item for item in list_payload["items"]}

    response = client.post(
        "/api/admin/user-ops/batch-send/preview",
        data=_build_batch_send_form_data(
            selection_mode="manual",
            selected_ids=[items_by_external["wm_send_eligible"]["id"]],
            content="今天统一跟进🙂",
            images=[("hello.png", _test_png_bytes(), "image/png")],
        ),
        content_type="multipart/form-data",
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["content_preview"] == "今天统一跟进🙂"
    assert payload["image_count"] == 1
    assert payload["eligible_count"] == 1


def test_user_ops_batch_send_preview_rejects_fourth_image(client, app):
    _seed_user_ops_page_action_data(app)

    response = client.post(
        "/api/admin/user-ops/batch-send/preview",
        data=_build_batch_send_form_data(
            selection_mode="all_filtered",
            images=[(f"img-{index}.png", _test_png_bytes(), "image/png") for index in range(1, 5)],
        ),
        content_type="multipart/form-data",
    )
    payload = response.get_json()

    assert response.status_code == 400
    assert payload["error"] == "at most 3 images are allowed"


def test_user_ops_batch_send_preview_rejects_non_image_file(client, app):
    _seed_user_ops_page_action_data(app)
    response = client.post(
        "/api/admin/user-ops/batch-send/preview",
        data=_build_batch_send_form_data(
            selection_mode="all_filtered",
            images=[("bad.txt", b"not-an-image", "text/plain")],
        ),
        content_type="multipart/form-data",
    )
    payload = response.get_json()

    assert response.status_code == 400
    assert payload["ok"] is False
    assert payload["error"] == "only image files are allowed"


def test_user_ops_batch_send_preview_rejects_empty_content_and_images(client, app):
    _seed_user_ops_page_action_data(app)
    response = client.post(
        "/api/admin/user-ops/batch-send/preview",
        data=_build_batch_send_form_data(selection_mode="all_filtered"),
        content_type="multipart/form-data",
    )
    payload = response.get_json()

    assert response.status_code == 400
    assert payload["ok"] is False
    assert payload["error"] == "content, images, or attachments is required"


def test_user_ops_batch_send_execute_requires_confirm_and_writes_send_record(client, app, monkeypatch):
    _seed_user_ops_page_action_data(app)
    client.post(
        "/api/admin/user-ops/do-not-disturb",
        json={
            "external_userid": "wm_send_manual_dnd",
            "reason_code": "manual_note",
            "reason_text": "运营手动设置",
            "operator": "test_operator",
        },
    )

    calls: list[dict[str, object]] = []

    def fake_dispatch(task_type: str, fn_name: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append({"task_type": task_type, "fn_name": fn_name, "payload": payload})
        return {"task_id": 900 + len(calls), "wecom_result": {"msgid": f"page-task-{len(calls)}"}}

    monkeypatch.setattr("wecom_ability_service.domains.user_ops.page_service.dispatch_wecom_task", fake_dispatch)

    bad_response = client.post(
        "/api/admin/user-ops/batch-send/execute",
        json={"selection_mode": "all_filtered", "content": "今天统一跟进"},
    )
    bad_payload = bad_response.get_json()

    assert bad_response.status_code == 400
    assert bad_payload["error"] == "confirm=true is required"

    response = client.post(
        "/api/admin/user-ops/batch-send/execute",
        data=_build_batch_send_form_data(
            selection_mode="all_filtered",
            content="今天统一跟进🙂",
            include_do_not_disturb=True,
            confirm=True,
            operator="test_operator",
            images=[
                ("first.png", _test_png_bytes(), "image/png"),
                ("second.png", _test_png_bytes(), "image/png"),
            ],
        ),
        content_type="multipart/form-data",
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["eligible_count"] == 3
    assert payload["sent_count"] == 3
    assert payload["execution_summary"]["selected_count"] == 4
    assert payload["execution_summary"]["eligible_count"] == 3
    assert payload["execution_summary"]["sent_count"] == 3
    assert payload["execution_summary"]["sender_count"] == 2
    assert payload["execution_summary"]["status"] == "sent"
    assert payload["skip_summary"]["skipped_count"] == 1
    assert payload["skip_summary"]["skipped_by_reason"] == {"missing_external_userid": 1}
    assert len(payload["task_results"]) == 2
    assert {item["owner_userid"] for item in payload["task_results"]} == {"sales_01", "sales_02"}
    assert payload["image_count"] == 2
    assert payload["execution_summary"]["image_count"] == 2
    assert len(calls) == 2
    assert calls[0]["payload"]["text"]["content"] == "今天统一跟进🙂"
    assert len(calls[0]["payload"]["images"]) == 2

    records_response = client.get("/api/admin/user-ops/send-records")
    records_payload = records_response.get_json()

    assert records_response.status_code == 200
    assert records_payload["total"] == 1
    assert records_payload["items"][0]["id"] == payload["record_id"]
    assert records_payload["items"][0]["operator"] == "test_operator"
    assert records_payload["items"][0]["content_preview"] == "今天统一跟进🙂"
    assert records_payload["items"][0]["image_count"] == 2
    assert "image_meta" not in records_payload["items"][0]
    assert "image_file_names" not in records_payload["items"][0]
    assert records_payload["items"][0]["status"] == "sent"
    assert records_payload["items"][0]["status_label"] == "已创建完成"
    assert records_payload["items"][0]["selected_count"] == 4
    assert records_payload["items"][0]["eligible_count"] == 3
    assert records_payload["items"][0]["sent_count"] == 3
    assert records_payload["items"][0]["skipped_count"] == 1
    assert records_payload["items"][0]["include_do_not_disturb"] is True
    assert records_payload["items"][0]["sender_count"] == 2
    assert records_payload["items"][0]["owner_count"] == 2
    assert records_payload["items"][0]["outbound_task_ids"] == [901, 902]

    detail_response = client.get(f"/api/admin/user-ops/send-records/{payload['record_id']}")
    detail_payload = detail_response.get_json()

    assert detail_response.status_code == 200
    assert detail_payload["record"]["id"] == payload["record_id"]
    assert detail_payload["record"]["status"] == "sent"
    assert detail_payload["record"]["status_label"] == "已创建完成"
    assert detail_payload["record"]["status_source"] == "task_creation"
    assert detail_payload["record"]["delivery_status_supported"] is False
    assert "暂无官方发送结果轮询能力" in detail_payload["record"]["status_note"]
    assert "image_meta" not in detail_payload["record"]
    assert "image_file_names" not in detail_payload["record"]
    assert len(detail_payload["record"]["task_results"]) == 2
    assert {item["owner_userid"] for item in detail_payload["record"]["task_results"]} == {"sales_01", "sales_02"}
    assert all(item["status"] == "created" for item in detail_payload["record"]["task_results"])
    assert all(item["msgid"] for item in detail_payload["record"]["task_results"])
    assert all(item["error_message"] == "" for item in detail_payload["record"]["task_results"])

    refresh_response = client.post(f"/api/admin/user-ops/send-records/{payload['record_id']}/refresh")
    refresh_payload = refresh_response.get_json()

    assert refresh_response.status_code == 200
    assert refresh_payload["record"]["id"] == payload["record_id"]
    assert refresh_payload["record"]["status"] == "sent"
    assert refresh_payload["record"]["last_status_sync_at"]


def test_user_ops_batch_send_execute_marks_partial_failed_with_sender_error_details(client, app, monkeypatch):
    _seed_user_ops_page_action_data(app)

    def fake_dispatch(task_type: str, fn_name: str, payload: dict[str, object]) -> dict[str, object]:
        sender = ((payload.get("sender") or [""]) if isinstance(payload.get("sender"), list) else [payload.get("sender")])[0]
        if sender == "sales_02":
            raise wecom_client_module.WeComClientError(
                "sales_02 create failed",
                stage="/cgi-bin/externalcontact/add_msg_template",
                category="wecom_api",
                payload={"errmsg": "sales_02 create failed"},
            )
        return {"task_id": 990, "wecom_result": {"msgid": "page-task-success"}}

    monkeypatch.setattr("wecom_ability_service.domains.user_ops.page_service.dispatch_wecom_task", fake_dispatch)

    response = client.post(
        "/api/admin/user-ops/batch-send/execute",
        json={
            "selection_mode": "all_filtered",
            "content": "今天统一跟进",
            "include_do_not_disturb": True,
            "confirm": True,
            "operator": "partial_operator",
        },
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["sent_count"] == 2
    assert payload["execution_summary"]["status"] == "partial_failed"
    assert len(payload["task_results"]) == 2
    assert {item["status"] for item in payload["task_results"]} == {"created", "failed"}
    failed_item = next(item for item in payload["task_results"] if item["status"] == "failed")
    assert failed_item["owner_userid"] == "sales_02"
    assert failed_item["error_message"] == "sales_02 create failed"

    detail_response = client.get(f"/api/admin/user-ops/send-records/{payload['record_id']}")
    detail_payload = detail_response.get_json()

    assert detail_response.status_code == 200
    assert detail_payload["record"]["status"] == "partial_failed"
    assert detail_payload["record"]["status_label"] == "部分创建失败"
    assert len(detail_payload["record"]["task_results"]) == 2
    failed_detail = next(item for item in detail_payload["record"]["task_results"] if item["status"] == "failed")
    assert failed_detail["owner_userid"] == "sales_02"
    assert failed_detail["error_message"] == "sales_02 create failed"
    assert failed_detail["task_id"] is None
    assert failed_detail["msgid"] == ""


def test_user_ops_batch_send_execute_marks_failed_when_all_sender_tasks_fail(client, app, monkeypatch):
    _seed_user_ops_page_action_data(app)

    def fake_dispatch(task_type: str, fn_name: str, payload: dict[str, object]) -> dict[str, object]:
        sender = ((payload.get("sender") or [""]) if isinstance(payload.get("sender"), list) else [payload.get("sender")])[0]
        raise wecom_client_module.WeComClientError(
            f"{sender} create failed",
            stage="/cgi-bin/externalcontact/add_msg_template",
            category="wecom_api",
            payload={"errmsg": f"{sender} create failed"},
        )

    monkeypatch.setattr("wecom_ability_service.domains.user_ops.page_service.dispatch_wecom_task", fake_dispatch)

    response = client.post(
        "/api/admin/user-ops/batch-send/execute",
        json={
            "selection_mode": "all_filtered",
            "content": "今天统一跟进",
            "include_do_not_disturb": True,
            "confirm": True,
        },
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["sent_count"] == 0
    assert payload["execution_summary"]["status"] == "failed"
    assert len(payload["task_results"]) == 2
    assert all(item["status"] == "failed" for item in payload["task_results"])

    detail_response = client.get(f"/api/admin/user-ops/send-records/{payload['record_id']}")
    detail_payload = detail_response.get_json()

    assert detail_response.status_code == 200
    assert detail_payload["record"]["status"] == "failed"
    assert detail_payload["record"]["status_label"] == "创建失败"
    assert len(detail_payload["record"]["task_results"]) == 2
    assert all(item["error_message"] for item in detail_payload["record"]["task_results"])


def test_user_ops_batch_send_execute_supports_pure_image(client, app, monkeypatch):
    _seed_user_ops_page_action_data(app)
    list_payload = client.get("/api/admin/user-ops/list").get_json()
    items_by_external = {item["external_userid"]: item for item in list_payload["items"]}

    calls: list[dict[str, object]] = []

    def fake_dispatch(task_type: str, fn_name: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append({"task_type": task_type, "fn_name": fn_name, "payload": payload})
        return {"task_id": 950 + len(calls), "wecom_result": {"msgid": f"page-task-img-{len(calls)}"}}

    monkeypatch.setattr("wecom_ability_service.domains.user_ops.page_service.dispatch_wecom_task", fake_dispatch)

    response = client.post(
        "/api/admin/user-ops/batch-send/execute",
        data=_build_batch_send_form_data(
            selection_mode="manual",
            selected_ids=[items_by_external["wm_send_eligible"]["id"]],
            confirm=True,
            images=[("only-image.png", _test_png_bytes(), "image/png")],
        ),
        content_type="multipart/form-data",
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["image_count"] == 1
    assert payload["sent_count"] == 1
    assert "text" not in calls[0]["payload"]
    assert len(calls[0]["payload"]["images"]) == 1


def test_user_ops_history_returns_lead_pool_records(client, app):
    _seed_user_ops_lead_pool_read_model(app)

    response = client.get("/api/admin/user-ops/history")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert isinstance(payload["items"], list)
    assert payload["total"] == 2
    assert payload["items"][0]["action_type"] in {"lead_pool_insert", "mobile_bind_merge"}
    assert "before_json" in payload["items"][0]
    assert "after_json" in payload["items"][0]


def test_user_ops_ui_route_renders_conversion_page(client):
    # /admin/user-ops/ui is sunset (410)
    response = client.get("/admin/user-ops/ui")
    assert response.status_code == 410


def test_user_ops_shell_page_exists(client):
    # /admin/user-ops is sunset (410)
    response = client.get("/admin/user-ops")
    assert response.status_code == 410


def test_user_ops_batch_send_modal_removes_large_stats_and_sender_bucket_from_main_ui(client):
    # /admin/user-ops/ui is sunset (410)
    response = client.get("/admin/user-ops/ui")
    assert response.status_code == 410


def test_user_ops_detail_column_is_removed_and_dnd_action_copy_is_simplified(client):
    # /admin/user-ops/ui is sunset (410)
    response = client.get("/admin/user-ops/ui")
    assert response.status_code == 410


def test_user_ops_template_keeps_detail_button_and_dnd_actions(client):
    # /admin/user-ops/ui is sunset (410)
    response = client.get("/admin/user-ops/ui")
    assert response.status_code == 410


def test_sync_user_ops_class_term_tag_definitions_updates_tag_identity_fields(app, user_ops_contact_client):
    user_ops_contact_client._corp_tag_payload = _build_corp_tag_payload(
        [
            ("tag-term-1", "首期7天改变计划"),
            ("tag-term-3", "0322改变计划-第3期"),
            ("tag-term-4", "0330改变计划-第4期"),
        ],
        group_id="group-verified",
    )

    with app.app_context():
        payload = sync_user_ops_class_term_tag_definitions()

        assert payload["ok"] is True
        assert payload["synced_count"] == 3
        rows = get_db().execute(
            """
            SELECT tag_name, strategy_id, group_id, tag_id
            FROM class_term_tag_mapping
            ORDER BY class_term_no ASC
            """
        ).fetchall()
        assert rows[0]["strategy_id"] == ""
        assert rows[0]["group_id"] == "group-verified"
        assert rows[0]["tag_id"] == "tag-term-1"


def test_refresh_contact_tags_for_external_userid_writes_all_tags_when_scope_is_none(app, user_ops_contact_client):
    user_ops_contact_client.set_contact_detail(
        "wm_refresh_all_001",
        _build_external_contact_detail(
            external_userid="wm_refresh_all_001",
            owner_userid="sales_01",
            follow_user_tags=[
                {"id": "tag-all-1", "name": "全量标签1"},
                {"id": "tag-all-2", "name": "全量标签2"},
            ],
        ),
    )

    with app.app_context():
        payload = refresh_contact_tags_for_external_userid(
            external_userid="wm_refresh_all_001",
            owner_userid="sales_01",
            scoped_tag_ids=None,
        )

        assert payload["ok"] is True
        assert payload["scoped_all_tags"] is True
        rows = get_db().execute(
            """
            SELECT tag_id, tag_name
            FROM contact_tags
            WHERE external_userid = ? AND userid = ?
            ORDER BY tag_id ASC
            """,
            ("wm_refresh_all_001", "sales_01"),
        ).fetchall()
        assert [row["tag_id"] for row in rows] == ["tag-all-1", "tag-all-2"]


def test_refresh_contact_tags_for_external_userid_only_refreshes_scoped_tags(app, user_ops_contact_client):
    user_ops_contact_client.set_contact_detail(
        "wm_refresh_scope_001",
        _build_external_contact_detail(
            external_userid="wm_refresh_scope_001",
            owner_userid="sales_01",
            follow_user_tags=[
                {"id": "tag-term-1", "name": "首期7天改变计划"},
                {"id": "tag-other-9", "name": "其他标签"},
            ],
        ),
    )

    with app.app_context():
        payload = refresh_contact_tags_for_external_userid(
            external_userid="wm_refresh_scope_001",
            owner_userid="sales_01",
            scoped_tag_ids=["tag-term-1"],
        )

        assert payload["ok"] is True
        assert payload["scoped_all_tags"] is False
        rows = get_db().execute(
            """
            SELECT tag_id, tag_name
            FROM contact_tags
            WHERE external_userid = ? AND userid = ?
            ORDER BY tag_id ASC
            """,
            ("wm_refresh_scope_001", "sales_01"),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["tag_id"] == "tag-term-1"


def test_refresh_user_ops_contact_tags_for_external_userid_uses_active_class_term_scope(app, user_ops_contact_client):
    user_ops_contact_client.set_contact_detail(
        "wm_refresh_scope_002",
        _build_external_contact_detail(
            external_userid="wm_refresh_scope_002",
            owner_userid="sales_01",
            follow_user_tags=[
                {"id": "tag-term-1", "name": "首期7天改变计划"},
                {"id": "tag-other-9", "name": "其他标签"},
            ],
        ),
    )

    with app.app_context():
        sync_user_ops_class_term_tag_definitions()
        payload = refresh_user_ops_contact_tags_for_external_userid(
            external_userid="wm_refresh_scope_002",
            owner_userid="sales_01",
        )

        rows = get_db().execute(
            """
            SELECT tag_id, tag_name
            FROM contact_tags
            WHERE external_userid = ? AND userid = ?
            ORDER BY tag_id ASC
            """,
            ("wm_refresh_scope_002", "sales_01"),
        ).fetchall()

    assert payload["ok"] is True
    assert payload["refreshed"] is True
    assert payload["owner_userid"] == "sales_01"
    assert payload["scoped_all_tags"] is False
    assert rows[0]["tag_id"] == "tag-term-1"
    assert len(rows) == 1


def test_refresh_user_ops_contact_tags_for_owner_sweeps_owner_external_userids(app, user_ops_contact_client):
    user_ops_contact_client.set_contact_detail(
        "wm_refresh_owner_001",
        _build_external_contact_detail(
            external_userid="wm_refresh_owner_001",
            owner_userid="sales_01",
            follow_user_tags=[{"id": "tag-term-1", "name": "首期7天改变计划"}],
        ),
    )
    user_ops_contact_client.set_contact_detail(
        "wm_refresh_owner_002",
        _build_external_contact_detail(
            external_userid="wm_refresh_owner_002",
            owner_userid="sales_01",
            follow_user_tags=[{"id": "tag-term-3", "name": "0322改变计划-第3期"}],
        ),
    )
    user_ops_contact_client.set_contact_detail(
        "wm_refresh_owner_003",
        _build_external_contact_detail(
            external_userid="wm_refresh_owner_003",
            owner_userid="sales_02",
            follow_user_tags=[{"id": "tag-term-4", "name": "0330改变计划-第4期"}],
        ),
    )

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO user_ops_lead_pool_current (
                mobile, external_userid, customer_name, owner_userid,
                is_wecom_added, is_mobile_bound, huangxiaocan_activation_state,
                class_term_no, class_term_label, first_entry_source, last_entry_source,
                created_at, updated_at
            )
            VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                "",
                "wm_refresh_owner_001",
                "Owner One",
                "sales_01",
                True,
                False,
                "unknown",
                1,
                "首期",
                "sidebar_class_term",
                "sidebar_class_term",
                "",
                "wm_refresh_owner_002",
                "Owner Two",
                "sales_01",
                True,
                False,
                "unknown",
                3,
                "3期",
                "sidebar_class_term",
                "sidebar_class_term",
                "",
                "wm_refresh_owner_003",
                "Other Owner",
                "sales_02",
                True,
                False,
                "unknown",
                4,
                "4期",
                "sidebar_class_term",
                "sidebar_class_term",
            ),
        )
        db.commit()

        sync_user_ops_class_term_tag_definitions()
        payload = refresh_user_ops_contact_tags_for_owner("sales_01")
        rows = db.execute(
            """
            SELECT external_userid, userid, tag_id
            FROM contact_tags
            WHERE external_userid IN (?, ?, ?)
            ORDER BY external_userid ASC, userid ASC, tag_id ASC
            """,
            ("wm_refresh_owner_001", "wm_refresh_owner_002", "wm_refresh_owner_003"),
        ).fetchall()

    assert payload["ok"] is True
    assert payload["owner_userid"] == "sales_01"
    assert payload["external_user_count"] == 2
    assert payload["refreshed_count"] == 2
    assert [item["external_userid"] for item in payload["items"]] == [
        "wm_refresh_owner_001",
        "wm_refresh_owner_002",
    ]
    assert [(row["external_userid"], row["userid"], row["tag_id"]) for row in rows] == [
        ("wm_refresh_owner_001", "sales_01", "tag-term-1"),
        ("wm_refresh_owner_002", "sales_01", "tag-term-3"),
    ]


def test_import_experience_leads_endpoint_is_deprecated_internal_only(client):
    response = client.post(
        "/api/admin/user-ops/import-experience-leads",
        json={"pasted_text": "13800138009"},
    )
    payload = response.get_json()

    assert response.status_code == 410
    assert payload["ok"] is False
    assert payload["error"] == "deprecated_internal_only"


def test_import_experience_leads_service_records_sources_and_history(app):
    with app.app_context():
        payload = import_experience_leads(
            pasted_text="手机号\n13800138009\nbad-mobile\n13800138009\n13800138010",
            created_by="tester",
        )

        rows = get_db().execute(
            """
            SELECT mobile, source_type, import_batch_id, created_by, is_active
            FROM user_ops_experience_leads
            ORDER BY mobile ASC
            """
        ).fetchall()
        history = get_db().execute(
            """
            SELECT mobile, action_type, source_type
            FROM user_ops_pool_history
            WHERE action_type = 'experience_import_source_upsert'
            ORDER BY mobile ASC
            """
        ).fetchall()

    assert payload["ok"] is True
    assert payload["import_type"] == "experience_leads"
    assert payload["total_rows"] == 4
    assert payload["success_rows"] == 3
    assert payload["failed_rows"] == 1
    assert payload["duplicate_count"] == 1
    assert payload["unique_mobile_count"] == 2
    assert payload["invalid_rows"] == ["bad-mobile"]
    assert payload["reload"] == {"mode": "legacy_pool_disabled", "triggered": False}
    assert [row["mobile"] for row in rows] == ["13800138009", "13800138010"]
    assert all(row["source_type"] == "experience_import" for row in rows)
    assert all(str(row["created_by"]) == "tester" for row in rows)
    assert all(bool(row["is_active"]) is True for row in rows)
    assert {str(row["import_batch_id"]) for row in rows} == {str(payload["batch_id"])}
    assert [row["mobile"] for row in history] == ["13800138009", "13800138010"]
    assert all(row["action_type"] == "experience_import_source_upsert" for row in history)
    assert all(row["source_type"] == "experience_import" for row in history)


def test_sidebar_bind_mobile_page_uses_single_customer_automation_layout(client):
    response = client.get("/sidebar/bind-mobile")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "自动化转化操作区" in html
    assert "放入自动化转化池" in html
    assert "移除自动化转化池" in html
    assert "一键自动化写话术" in html
    assert "实时标签" in html
    assert "已填写问卷及答案" in html
    assert "/api/admin/automation-conversion/member" in html
    assert "/api/admin/customers/profile/tags" in html
    assert "/api/admin/customers/profile/questionnaire-answers" in html
    assert "班期快捷设置" not in html
    assert "自动化转化卡片" not in html
    assert "/api/sidebar/signup-tags/status" not in html
    assert "/api/sidebar/signup-tags/mark" not in html


def test_sidebar_lead_pool_upsert_class_term_creates_external_only_member(client, app):
    _seed_sidebar_contact(app, external_userid="wm_sidebar_term_001", owner_userid="sales_01")
    applied_tags: list[dict[str, object]] = []
    app.config["SIDEBAR_LEAD_POOL_TAG_APPLIER"] = lambda **payload: applied_tags.append(payload)

    response = client.post(
        "/api/sidebar/lead-pool/upsert-class-term",
        json={
            "external_userid": "wm_sidebar_term_001",
            "owner_userid": "sales_01",
            "class_term_no": 4,
        },
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["current_class_term_no"] == 4
    assert payload["current_class_term_label"] == "4期"
    with app.app_context():
        row = get_db().execute(
            """
            SELECT mobile, external_userid, class_term_no, class_term_label, is_wecom_added, is_mobile_bound
            FROM user_ops_lead_pool_current
            WHERE external_userid = ?
            """,
            ("wm_sidebar_term_001",),
        ).fetchone()
        history = get_db().execute(
            """
            SELECT action_type, source_type
            FROM user_ops_lead_pool_history
            WHERE external_userid = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            ("wm_sidebar_term_001",),
        ).fetchone()
        tag_row = get_db().execute(
            """
            SELECT tag_id, tag_name
            FROM contact_tags
            WHERE external_userid = ? AND userid = ?
            ORDER BY tag_id ASC
            LIMIT 1
            """,
            ("wm_sidebar_term_001", "sales_01"),
        ).fetchone()
        mapping = get_db().execute(
            """
            SELECT tag_id, tag_name
            FROM class_term_tag_mapping
            WHERE class_term_no = ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (4,),
        ).fetchone()

    assert row["mobile"] == ""
    assert row["external_userid"] == "wm_sidebar_term_001"
    assert row["class_term_no"] == 4
    assert row["class_term_label"] == "4期"
    assert bool(row["is_wecom_added"]) is True
    assert bool(row["is_mobile_bound"]) is False
    assert history["source_type"] == "sidebar_class_term"
    assert history["action_type"] == "lead_pool_insert"
    assert tag_row["tag_id"] == mapping["tag_id"]
    assert tag_row["tag_name"] == mapping["tag_name"]
    assert applied_tags[0]["add_tags"] == [mapping["tag_id"]]


def test_sidebar_lead_pool_status_returns_current_member(client, app):
    _seed_sidebar_contact(app, external_userid="wm_sidebar_term_002", owner_userid="sales_01")
    app.config["SIDEBAR_LEAD_POOL_TAG_APPLIER"] = lambda **payload: None
    client.post(
        "/api/sidebar/lead-pool/upsert-class-term",
        json={
            "external_userid": "wm_sidebar_term_002",
            "owner_userid": "sales_01",
            "class_term_no": 3,
        },
    )

    response = client.get(
        "/api/sidebar/lead-pool/status?external_userid=wm_sidebar_term_002&owner_userid=sales_01"
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["current_class_term_no"] == 3
    assert payload["current_class_term_label"] == "3期"
    assert payload["is_wecom_added"] is True
    assert payload["is_mobile_bound"] is False
    assert any(option["class_term_no"] == 3 for option in payload["class_term_options"])


def test_sidebar_lead_pool_status_does_not_fallback_to_other_owner_member(client, app):
    _seed_sidebar_contact(app, external_userid="wm_sidebar_status_owner_scope_001", owner_userid="sales_01")
    app.config["SIDEBAR_LEAD_POOL_TAG_APPLIER"] = lambda **payload: None

    with app.app_context():
        upsert_user_ops_lead_pool_member(
            mobile="13800138099",
            external_userid="wm_sidebar_status_owner_scope_001",
            customer_name="跨 owner 客户",
            owner_userid="WangWei",
            is_wecom_added=True,
            is_mobile_bound=True,
            class_term_no=10,
            class_term_label="10期",
            entry_source="sidebar_class_term",
            operator="tester",
            remark="seed cross-owner member for sidebar status scope test",
        )
        db = get_db()
        db.execute(
            """
            INSERT INTO contact_tags (external_userid, userid, tag_id, tag_name)
            VALUES (?, ?, ?, ?)
            """,
            ("wm_sidebar_status_owner_scope_001", "sales_01", "tag_term_sales_01", "第5期"),
        )
        db.commit()

    response = client.get(
        "/api/sidebar/lead-pool/status?external_userid=wm_sidebar_status_owner_scope_001&owner_userid=sales_01"
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["owner_userid"] == "sales_01"
    assert payload["current_class_term_no"] is None
    assert payload["current_class_term_label"] == ""
    assert payload["member"] == {}


def test_sidebar_lead_pool_upsert_class_term_replaces_old_tag_and_returns_success(client, app, monkeypatch):
    _seed_sidebar_contact(app, external_userid="wm_sidebar_term_replace_001", owner_userid="sales_01")
    wecom_calls: list[dict[str, object]] = []

    class FakeWeComClient:
        def mark_external_contact_tags(
            self,
            *,
            external_userid: str,
            follow_user_userid: str,
            add_tags: list[str],
            remove_tags: list[str] | None = None,
        ) -> dict[str, object]:
            wecom_calls.append(
                {
                    "external_userid": external_userid,
                    "follow_user_userid": follow_user_userid,
                    "add_tags": list(add_tags),
                    "remove_tags": list(remove_tags or []),
                }
            )
            return {"errcode": 0}

    monkeypatch.setattr(
        wecom_client_module.WeComClient,
        "from_app",
        classmethod(lambda cls: FakeWeComClient()),
    )
    monkeypatch.setattr(
        "wecom_ability_service.services._user_ops_contact_client",
        lambda: type(
            "FakeContactClient",
            (),
            {
                "get_contact": staticmethod(
                    lambda external_userid: {
                        "external_contact": {"external_userid": external_userid},
                        "follow_user": [
                            {"userid": "sales_01", "tags": [{"tag_id": "tag_term_4_cleanup", "tag_name": "第4期"}]},
                            {"userid": "QianLan", "tags": [{"tag_id": "tag_term_3_cleanup", "tag_name": "第3期"}]},
                        ],
                    }
                )
            },
        )(),
    )
    monkeypatch.setattr(
        "wecom_ability_service.infra.user_ops_runtime.get_user_ops_contact_client",
        lambda: type(
            "FakeContactClient",
            (),
            {
                "get_contact": staticmethod(
                    lambda external_userid: {
                        "external_contact": {"external_userid": external_userid},
                        "follow_user": [
                            {"userid": "sales_01", "tags": [{"tag_id": "tag_term_4_cleanup", "tag_name": "第4期"}]},
                            {"userid": "QianLan", "tags": [{"tag_id": "tag_term_3_cleanup", "tag_name": "第3期"}]},
                        ],
                    }
                )
            },
        )(),
    )

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO class_term_tag_mapping (
                class_term_no, class_term_label, tag_id, tag_group_name, tag_name, strategy_id, group_id, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                5,
                "5期",
                "tag_term_5",
                "9.9元改变计划",
                "第5期",
                "strategy_sidebar_test",
                "group_sidebar_test",
                True,
                6,
                "6期",
                "tag_term_6",
                "9.9元改变计划",
                "第6期",
                "strategy_sidebar_test",
                "group_sidebar_test",
                True,
            ),
        )
        db.commit()
        mapping_5 = get_db().execute(
            """
            SELECT tag_id, tag_name
            FROM class_term_tag_mapping
            WHERE class_term_no = ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (5,),
        ).fetchone()
        mapping_6 = get_db().execute(
            """
            SELECT tag_id, tag_name
            FROM class_term_tag_mapping
            WHERE class_term_no = ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (6,),
        ).fetchone()

    response_5 = client.post(
        "/api/sidebar/lead-pool/upsert-class-term",
        json={
            "external_userid": "wm_sidebar_term_replace_001",
            "owner_userid": "sales_01",
            "class_term_no": 5,
        },
    )
    payload_5 = response_5.get_json()

    response_6 = client.post(
        "/api/sidebar/lead-pool/upsert-class-term",
        json={
            "external_userid": "wm_sidebar_term_replace_001",
            "owner_userid": "sales_01",
            "class_term_no": 6,
        },
    )
    payload_6 = response_6.get_json()

    assert response_5.status_code == 200
    assert payload_5["ok"] is True
    assert payload_5["current_class_term_no"] == 5
    assert response_6.status_code == 200
    assert payload_6["ok"] is True
    assert payload_6["current_class_term_no"] == 6
    assert payload_6["current_class_term_label"] == "6期"

    with app.app_context():
        current_row = get_db().execute(
            """
            SELECT class_term_no, class_term_label
            FROM user_ops_lead_pool_current
            WHERE external_userid = ?
            """,
            ("wm_sidebar_term_replace_001",),
        ).fetchone()
        tag_rows = get_db().execute(
            """
            SELECT tag_id, tag_name
            FROM contact_tags
            WHERE external_userid = ? AND userid = ?
            ORDER BY tag_id ASC
            """,
            ("wm_sidebar_term_replace_001", "sales_01"),
        ).fetchall()

    assert current_row["class_term_no"] == 6
    assert current_row["class_term_label"] == "6期"
    assert len(tag_rows) == 1
    assert tag_rows[0]["tag_id"] == mapping_6["tag_id"]
    assert tag_rows[0]["tag_name"] == mapping_6["tag_name"]
    assert wecom_calls[0]["add_tags"] == [mapping_5["tag_id"]]
    assert mapping_6["tag_id"] in wecom_calls[1]["add_tags"]
    assert mapping_5["tag_id"] in wecom_calls[1]["remove_tags"]


def test_sidebar_lead_pool_upsert_class_term_respects_explicit_owner_context(client, app, monkeypatch):
    _seed_sidebar_contact(app, external_userid="wm_sidebar_owner_pin_001", owner_userid="sales_01")
    wecom_calls: list[dict[str, object]] = []

    class FakeWeComClient:
        def mark_external_contact_tags(
            self,
            *,
            external_userid: str,
            follow_user_userid: str,
            add_tags: list[str],
            remove_tags: list[str] | None = None,
        ) -> dict[str, object]:
            wecom_calls.append(
                {
                    "external_userid": external_userid,
                    "follow_user_userid": follow_user_userid,
                    "add_tags": list(add_tags),
                    "remove_tags": list(remove_tags or []),
                }
            )
            return {"errcode": 0}

    monkeypatch.setattr(
        wecom_client_module.WeComClient,
        "from_app",
        classmethod(lambda cls: FakeWeComClient()),
    )

    with app.app_context():
        db = get_db()
        existing_owner = db.execute("SELECT 1 FROM owner_role_map WHERE userid = ?", ("WangWei",)).fetchone()
        if not existing_owner:
            db.execute(
                """
                INSERT INTO owner_role_map (userid, display_name, role, active)
                VALUES (?, ?, ?, ?)
                """,
                ("WangWei", "WangWei", "sales", True),
            )
        db.execute(
            "UPDATE contacts SET owner_userid = ? WHERE external_userid = ?",
            ("WangWei", "wm_sidebar_owner_pin_001"),
        )
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name, status, raw_profile
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ww-test",
                "wm_sidebar_owner_pin_001",
                "union-wm_sidebar_owner_pin_001",
                "openid-wm_sidebar_owner_pin_001",
                "WangWei",
                "侧边栏客户",
                "active",
                "{}",
            ),
        )
        db.commit()

    response = client.post(
        "/api/sidebar/lead-pool/upsert-class-term",
        json={
            "external_userid": "wm_sidebar_owner_pin_001",
            "owner_userid": "sales_01",
            "class_term_no": 4,
        },
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["owner_userid"] == "sales_01"
    assert payload["current_class_term_no"] == 4

    with app.app_context():
        current_row = get_db().execute(
            """
            SELECT owner_userid, class_term_no
            FROM user_ops_lead_pool_current
            WHERE external_userid = ?
            """,
            ("wm_sidebar_owner_pin_001",),
        ).fetchone()

    assert current_row["owner_userid"] == "sales_01"
    assert current_row["class_term_no"] == 4
    assert wecom_calls[0]["follow_user_userid"] == "sales_01"


def test_sidebar_lead_pool_upsert_class_term_cleans_cross_owner_stale_tag_snapshots(client, app, monkeypatch):
    _seed_sidebar_contact(app, external_userid="wm_sidebar_cleanup_001", owner_userid="sales_01")
    wecom_calls: list[dict[str, object]] = []
    app.config["SIDEBAR_LEAD_POOL_TAG_APPLIER"] = lambda **payload: wecom_calls.append(
        {
            "external_userid": payload["external_userid"],
            "follow_user_userid": payload["owner_userid"],
            "add_tags": list(payload.get("add_tags") or []),
            "remove_tags": list(payload.get("remove_tags") or []),
        }
    )
    monkeypatch.setattr(
        "wecom_ability_service.services._user_ops_contact_client",
        lambda: type(
            "FakeContactClient",
            (),
            {
                "get_contact": staticmethod(
                    lambda external_userid: {
                        "external_contact": {"external_userid": external_userid},
                        "follow_user": [
                            {"userid": "sales_01", "tags": [{"tag_id": "tag_term_4_cleanup", "tag_name": "第4期"}]},
                            {"userid": "QianLan", "tags": [{"tag_id": "tag_term_3_cleanup", "tag_name": "第3期"}]},
                        ],
                    }
                )
            },
        )(),
    )
    monkeypatch.setattr(
        "wecom_ability_service.infra.user_ops_runtime.get_user_ops_contact_client",
        lambda: type(
            "FakeContactClient",
            (),
            {
                "get_contact": staticmethod(
                    lambda external_userid: {
                        "external_contact": {"external_userid": external_userid},
                        "follow_user": [
                            {"userid": "sales_01", "tags": [{"tag_id": "tag_term_4_cleanup", "tag_name": "第4期"}]},
                            {"userid": "QianLan", "tags": [{"tag_id": "tag_term_3_cleanup", "tag_name": "第3期"}]},
                        ],
                    }
                )
            },
        )(),
    )

    with app.app_context():
        db = get_db()
        existing_owner = db.execute("SELECT 1 FROM owner_role_map WHERE userid = ?", ("QianLan",)).fetchone()
        if not existing_owner:
            db.execute(
                """
                INSERT INTO owner_role_map (userid, display_name, role, active)
                VALUES (?, ?, ?, ?)
                """,
                ("QianLan", "QianLan", "sales", True),
            )
        db.execute(
            """
            INSERT INTO class_term_tag_mapping (
                class_term_no, class_term_label, tag_id, tag_group_name, tag_name, strategy_id, group_id, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                3,
                "3期",
                "tag_term_3_cleanup",
                "9.9元改变计划",
                "第3期",
                "strategy_sidebar_cleanup_test",
                "group_sidebar_cleanup_test",
                True,
                4,
                "4期",
                "tag_term_4_cleanup",
                "9.9元改变计划",
                "第4期",
                "strategy_sidebar_cleanup_test",
                "group_sidebar_cleanup_test",
                True,
            ),
        )
        mapping_4 = db.execute(
            """
            SELECT tag_id, tag_name
            FROM class_term_tag_mapping
            WHERE class_term_no = ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (4,),
        ).fetchone()
        mapping_3 = db.execute(
            """
            SELECT tag_id, tag_name
            FROM class_term_tag_mapping
            WHERE class_term_no = ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (3,),
        ).fetchone()
        db.execute(
            """
            INSERT INTO contact_tags (external_userid, userid, tag_id, tag_name)
            VALUES (?, ?, ?, ?), (?, ?, ?, ?)
            """,
            (
                "wm_sidebar_cleanup_001",
                "sales_01",
                mapping_4["tag_id"],
                mapping_4["tag_name"],
                "wm_sidebar_cleanup_001",
                "QianLan",
                mapping_3["tag_id"],
                mapping_3["tag_name"],
            ),
        )
        db.commit()

    response = client.post(
        "/api/sidebar/lead-pool/upsert-class-term",
        json={
            "external_userid": "wm_sidebar_cleanup_001",
            "owner_userid": "sales_01",
            "class_term_no": 4,
        },
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True

    with app.app_context():
        tag_rows = get_db().execute(
            """
            SELECT userid, tag_id, tag_name
            FROM contact_tags
            WHERE external_userid = ?
            ORDER BY userid ASC, tag_id ASC
            """,
            ("wm_sidebar_cleanup_001",),
        ).fetchall()

    assert [dict(row) for row in tag_rows] == [
        {"userid": "sales_01", "tag_id": mapping_4["tag_id"], "tag_name": mapping_4["tag_name"]}
    ]
    assert wecom_calls[0]["follow_user_userid"] == "sales_01"
    assert wecom_calls[1]["external_userid"] == "wm_sidebar_cleanup_001"
    assert wecom_calls[1]["follow_user_userid"] == "QianLan"
    assert wecom_calls[1]["add_tags"] == []
    assert mapping_3["tag_id"] in wecom_calls[1]["remove_tags"]
    assert mapping_4["tag_id"] in wecom_calls[1]["remove_tags"]


def test_sidebar_bind_mobile_merges_external_only_and_mobile_only_members(client, app):
    _seed_sidebar_contact(app, external_userid="wm_sidebar_bind_001", owner_userid="sales_01", customer_name="待绑定客户")
    app.config["SIDEBAR_LEAD_POOL_TAG_APPLIER"] = lambda **payload: None
    response = client.post(
        "/api/sidebar/lead-pool/upsert-class-term",
        json={
            "external_userid": "wm_sidebar_bind_001",
            "owner_userid": "sales_01",
            "class_term_no": 4,
        },
    )
    assert response.status_code == 200

    with app.app_context():
        upsert_user_ops_lead_pool_member(
            mobile="13800138111",
            huangxiaocan_activation_state="activated",
            entry_source="student_import",
            operator="tester",
            remark="seed mobile-only before sidebar bind merge",
        )

    bind_response = client.post(
        "/api/sidebar/bind-mobile",
        json={
            "external_userid": "wm_sidebar_bind_001",
            "owner_userid": "sales_01",
            "bind_by_userid": "sales_01",
            "mobile": "13800138111",
        },
    )
    bind_payload = bind_response.get_json()

    assert bind_response.status_code == 200
    assert bind_payload["ok"] is True
    assert bind_payload["binding"]["mobile"] == "13800138111"
    assert bind_payload["binding"]["lead_pool_merge"]["merge_applied"] is True
    with app.app_context():
        rows = get_db().execute(
            """
            SELECT id, mobile, external_userid, customer_name, owner_userid, is_wecom_added, is_mobile_bound,
                   huangxiaocan_activation_state, class_term_no, class_term_label
            FROM user_ops_lead_pool_current
            WHERE mobile = ? OR external_userid = ?
            ORDER BY id ASC
            """,
            ("13800138111", "wm_sidebar_bind_001"),
        ).fetchall()
        merge_history = get_db().execute(
            """
            SELECT action_type, source_type, before_json, after_json, remark
            FROM user_ops_lead_pool_history
            WHERE external_userid = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            ("wm_sidebar_bind_001",),
        ).fetchone()

    assert len(rows) == 1
    merged = rows[0]
    assert merged["mobile"] == "13800138111"
    assert merged["external_userid"] == "wm_sidebar_bind_001"
    assert merged["class_term_no"] == 4
    assert merged["class_term_label"] == "4期"
    assert merged["huangxiaocan_activation_state"] == "activated"
    assert merged["customer_name"] == "待绑定客户"
    assert merged["owner_userid"] == "sales_01"
    assert bool(merged["is_wecom_added"]) is True
    assert bool(merged["is_mobile_bound"]) is True
    assert merge_history["action_type"] == "mobile_bind_merge"
    assert merge_history["source_type"] == "mobile_bind"
    # PG JSON/JSONB 列返回 dict，不能用 in 查子串
    before = merge_history["before_json"]
    if isinstance(before, dict):
        assert before.get("external_userid") == "wm_sidebar_bind_001"
    else:
        assert '"external_userid": "wm_sidebar_bind_001"' in before
    after = merge_history["after_json"]
    if isinstance(after, dict):
        assert after.get("mobile") == "13800138111"
    else:
        assert '"mobile": "13800138111"' in after


def test_lead_pool_upsert_same_external_userid_keeps_current_row_and_appends_history(app):
    with app.app_context():
        first = upsert_user_ops_lead_pool_member(
            external_userid="wm_pool_core_001",
            customer_name="初始客户",
            owner_userid="sales_01",
            entry_source="student_import",
            operator="tester_a",
        )
        second = upsert_user_ops_lead_pool_member(
            external_userid="wm_pool_core_001",
            customer_name="更新客户",
            owner_userid="sales_02",
            huangxiaocan_activation_state="activated",
            class_term_no=6,
            class_term_label="6期",
            entry_source="sidebar_manual_set_class_term",
            operator="tester_b",
            remark="pool core stability check",
        )
        current_rows = get_db().execute(
            """
            SELECT id, external_userid, customer_name, owner_userid, huangxiaocan_activation_state,
                   class_term_no, class_term_label
            FROM user_ops_lead_pool_current
            WHERE external_userid = ?
            ORDER BY id ASC
            """,
            ("wm_pool_core_001",),
        ).fetchall()
        history_rows = get_db().execute(
            """
            SELECT action_type, source_type, operator, remark, after_json
            FROM user_ops_lead_pool_history
            WHERE external_userid = ?
            ORDER BY id ASC
            """,
            ("wm_pool_core_001",),
        ).fetchall()

    assert first["action_type"] == "lead_pool_insert"
    assert second["action_type"] == "lead_pool_update"
    assert len(current_rows) == 1
    current = current_rows[0]
    assert current["customer_name"] == "更新客户"
    assert current["owner_userid"] == "sales_02"
    assert current["huangxiaocan_activation_state"] == "activated"
    assert current["class_term_no"] == 6
    assert current["class_term_label"] == "6期"
    assert len(history_rows) == 2
    assert history_rows[0]["action_type"] == "lead_pool_insert"
    assert history_rows[1]["action_type"] == "lead_pool_update"
    assert history_rows[1]["source_type"] == "sidebar_manual_set_class_term"
    assert history_rows[1]["operator"] == "tester_b"
    assert history_rows[1]["remark"] == "pool core stability check"
    # PG JSON/JSONB 列返回 dict
    after = history_rows[1]["after_json"]
    if isinstance(after, dict):
        assert after.get("customer_name") == "更新客户"
        assert after.get("huangxiaocan_activation_state") == "activated"
    else:
        assert '"customer_name": "更新客户"' in after
        assert '"huangxiaocan_activation_state": "activated"' in after


def test_import_mobile_class_terms_from_pasted_text_updates_pool(client, app):
    response = client.post(
        "/api/admin/user-ops/import-mobile-class-terms",
        json={"pasted_text": "13800138015,5期"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["unique_mobile_count"] == 1

    with app.app_context():
        item = get_db().execute(
            """
            SELECT mobile, class_term_no, class_term_label, external_userid, is_wecom_added, is_mobile_bound
            FROM user_ops_lead_pool_current
            WHERE mobile = ?
            """,
            ("13800138015",),
        ).fetchone()
        history = get_db().execute(
            """
            SELECT action_type, source_type
            FROM user_ops_lead_pool_history
            WHERE mobile = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            ("13800138015",),
        ).fetchone()

    assert item["mobile"] == "13800138015"
    assert item["class_term_no"] == 5
    assert item["class_term_label"] == "5期"
    assert item["external_userid"] == ""
    assert bool(item["is_wecom_added"]) is False
    assert bool(item["is_mobile_bound"]) is False
    assert history["action_type"] == "lead_pool_insert"
    assert history["source_type"] == "student_import"


def test_import_mobile_class_terms_matching_binding_marks_wecom_bound(client, app):
    _seed_user_ops_sources(app)

    response = client.post(
        "/api/admin/user-ops/import-mobile-class-terms",
        json={"pasted_text": "13800138002,6期"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["bound_count"] == 1

    with app.app_context():
        item = get_db().execute(
            """
            SELECT mobile, external_userid, is_wecom_added, is_mobile_bound, class_term_label
            FROM user_ops_lead_pool_current
            WHERE mobile = ?
            """,
            ("13800138002",),
        ).fetchone()

    assert item["mobile"] == "13800138002"
    assert item["external_userid"] == "wm_lead_bound"
    assert bool(item["is_wecom_added"]) is True
    assert bool(item["is_mobile_bound"]) is True
    assert item["class_term_label"] == "6期"


def test_import_mobile_class_terms_keeps_latest_row_for_same_mobile(client, app):
    response = client.post(
        "/api/admin/user-ops/import-mobile-class-terms",
        data={
            "file": (
                BytesIO(_build_test_xlsx([["手机号", "班期"], ["13800138016", "5期"], ["13800138016", "6期"]])),
                "class-term.xlsx",
            )
        },
        content_type="multipart/form-data",
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["duplicate_count"] == 1
    assert payload["reload"] == {"mode": "incremental", "triggered": False}

    with app.app_context():
        row = get_db().execute(
            """
            SELECT class_term_no, class_term_label
            FROM user_ops_lead_pool_current
            WHERE mobile = ?
            """,
            ("13800138016",),
        ).fetchone()
    assert row["class_term_no"] == 6
    assert row["class_term_label"] == "6期"


def test_import_mobile_class_terms_does_not_trigger_legacy_reload(client, monkeypatch):
    monkeypatch.setattr(
        "wecom_ability_service.services.reload_user_ops_pool",
        lambda: (_ for _ in ()).throw(AssertionError("legacy reload should not run")),
    )
    response = client.post(
        "/api/admin/user-ops/import-mobile-class-terms",
        json={"pasted_text": "13800138017,7期"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["reload"] == {"mode": "incremental", "triggered": False}


def test_import_activation_status_from_pasted_text_updates_pool(client, app):
    client.post(
        "/api/admin/user-ops/import-mobile-class-terms",
        json={"pasted_text": "13800138020,5期"},
    )
    response = client.post(
        "/api/admin/user-ops/import-activation-status",
        json={"pasted_text": "13800138020,已激活"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True

    with app.app_context():
        source_row = get_db().execute(
            """
            SELECT mobile, activation_state
            FROM user_ops_huangxiaocan_activation_source
            WHERE mobile = ?
            """,
            ("13800138020",),
        ).fetchone()
        lead_row = get_db().execute(
            """
            SELECT mobile, huangxiaocan_activation_state
            FROM user_ops_lead_pool_current
            WHERE mobile = ?
            """,
            ("13800138020",),
        ).fetchone()

    assert payload["matched_member_count"] == 1
    assert source_row["activation_state"] == "activated"
    assert lead_row["huangxiaocan_activation_state"] == "activated"


def test_import_activation_status_from_excel_updates_pool(client, app):
    response = client.post(
        "/api/admin/user-ops/import-activation-status",
        data={
            "file": (
                BytesIO(_build_test_xlsx([["手机号", "状态"], ["13800138021", "已激活"]])),
                "activation.xlsx",
            )
        },
        content_type="multipart/form-data",
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True

    with app.app_context():
        source_row = get_db().execute(
            """
            SELECT mobile, activation_state
            FROM user_ops_huangxiaocan_activation_source
            WHERE mobile = ?
            """,
            ("13800138021",),
        ).fetchone()
        lead_row = get_db().execute(
            """
            SELECT mobile
            FROM user_ops_lead_pool_current
            WHERE mobile = ?
            """,
            ("13800138021",),
        ).fetchone()
    assert source_row["activation_state"] == "activated"
    assert lead_row is None


def test_import_activation_status_accepts_not_activated_label(client, app):
    response = client.post(
        "/api/admin/user-ops/import-activation-status",
        json={"pasted_text": "13800138031,未激活"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True

    with app.app_context():
        source_row = get_db().execute(
            """
            SELECT activation_state
            FROM user_ops_huangxiaocan_activation_source
            WHERE mobile = ?
            """,
            ("13800138031",),
        ).fetchone()
    assert source_row["activation_state"] == "not_activated"


def test_import_activation_status_accepts_legacy_activated_label(client, app):
    response = client.post(
        "/api/admin/user-ops/import-activation-status",
        json={"pasted_text": "13800138032,激活"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True

    with app.app_context():
        source_row = get_db().execute(
            """
            SELECT activation_state
            FROM user_ops_huangxiaocan_activation_source
            WHERE mobile = ?
            """,
            ("13800138032",),
        ).fetchone()
    assert source_row["activation_state"] == "activated"


def test_import_activation_status_rejects_invalid_value(client):
    response = client.post(
        "/api/admin/user-ops/import-activation-status",
        json={"pasted_text": "13800138022,高意向"},
    )
    payload = response.get_json()

    assert response.status_code == 400
    assert payload["ok"] is False
    assert payload["error"] == "invalid activation rows: 13800138022,高意向 -> activation_status is invalid: 高意向 (allowed: 已激活, 未激活)"


def test_import_activation_status_source_keeps_latest_row(client, app):
    response = client.post(
        "/api/admin/user-ops/import-activation-status",
        json={"pasted_text": "13800138023,未激活\n13800138023,激活"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["duplicate_count"] == 1

    with app.app_context():
        row = get_db().execute(
            "SELECT COUNT(*) AS total FROM user_ops_huangxiaocan_activation_source WHERE mobile = ?",
            ("13800138023",),
        ).fetchone()
        assert row["total"] == 1
        current = get_db().execute(
            """
            SELECT activation_state
            FROM user_ops_huangxiaocan_activation_source
            WHERE mobile = ?
            """,
            ("13800138023",),
        ).fetchone()
        assert current["activation_state"] == "activated"


def test_phone_centric_imports_keep_external_userid_binding_derived(client, app):
    _seed_user_ops_sources(app)

    class_term_response = client.post(
        "/api/admin/user-ops/import-mobile-class-terms",
        json={
            "pasted_text": "13800138002,6期",
            "external_userid": "wm_should_not_be_written",
        },
    )
    activation_response = client.post(
        "/api/admin/user-ops/import-activation-status",
        json={
            "pasted_text": "13800138002,激活",
            "external_userid": "wm_should_not_be_written",
        },
    )

    assert class_term_response.status_code == 200
    assert activation_response.status_code == 200

    with app.app_context():
        item = get_db().execute(
            """
            SELECT mobile, external_userid, is_wecom_added, is_mobile_bound, class_term_label, huangxiaocan_activation_state
            FROM user_ops_lead_pool_current
            WHERE mobile = ?
            """,
            ("13800138002",),
        ).fetchone()
    assert item["mobile"] == "13800138002"
    assert item["external_userid"] == "wm_lead_bound"
    assert bool(item["is_wecom_added"]) is True
    assert bool(item["is_mobile_bound"]) is True
    assert item["class_term_label"] == "6期"
    assert item["huangxiaocan_activation_state"] == "activated"


def test_phone_centric_sources_and_projection_fields_stay_split(client, app):
    client.post(
        "/api/admin/user-ops/import-mobile-class-terms",
        json={"pasted_text": "13800138061,5期"},
    )
    client.post(
        "/api/admin/user-ops/import-activation-status",
        json={"pasted_text": "13800138061,未激活"},
    )
    with app.app_context():
        db = get_db()
        source_row = db.execute(
            """
            SELECT mobile, activation_state, import_batch_id
            FROM user_ops_huangxiaocan_activation_source
            WHERE mobile = ?
            """,
            ("13800138061",),
        ).fetchone()
        current_row = db.execute(
            """
            SELECT mobile, external_userid, is_wecom_added, is_mobile_bound, class_term_no, class_term_label, huangxiaocan_activation_state
            FROM user_ops_lead_pool_current
            WHERE mobile = ?
            """,
            ("13800138061",),
        ).fetchone()

    assert source_row["mobile"] == "13800138061"
    assert source_row["activation_state"] == "not_activated"
    assert current_row["mobile"] == "13800138061"
    assert current_row["external_userid"] == ""
    assert bool(current_row["is_wecom_added"]) is False
    assert bool(current_row["is_mobile_bound"]) is False
    assert current_row["class_term_no"] == 5
    assert current_row["class_term_label"] == "5期"
    assert current_row["huangxiaocan_activation_state"] == "not_activated"


def test_activation_status_survives_lead_pool_reads(client, app):
    client.post(
        "/api/admin/user-ops/import-mobile-class-terms",
        json={"pasted_text": "13800138024,5期"},
    )
    client.post(
        "/api/admin/user-ops/import-activation-status",
        json={"pasted_text": "13800138024,激活"},
    )

    overview_payload = client.get("/api/admin/user-ops/overview").get_json()
    list_payload = client.get("/api/admin/user-ops/list?query=13800138024").get_json()

    with app.app_context():
        source_row = get_db().execute(
            "SELECT activation_state FROM user_ops_huangxiaocan_activation_source WHERE mobile = ?",
            ("13800138024",),
        ).fetchone()
        lead_row = get_db().execute(
            "SELECT huangxiaocan_activation_state FROM user_ops_lead_pool_current WHERE mobile = ?",
            ("13800138024",),
        ).fetchone()
    assert source_row["activation_state"] == "activated"
    assert lead_row["huangxiaocan_activation_state"] == "activated"
    assert overview_payload["huangxiaocan_activated_count"] >= 1
    assert list_payload["items"][0]["huangxiaocan_activation_state"] == "activated"


def test_activation_import_does_not_create_mobile_only_lead_member(client, app):
    response = client.post(
        "/api/admin/user-ops/import-activation-status",
        json={"pasted_text": "13800138025,未激活"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True

    with app.app_context():
        source_row = get_db().execute(
            "SELECT activation_state FROM user_ops_huangxiaocan_activation_source WHERE mobile = ?",
            ("13800138025",),
        ).fetchone()
        lead_row = get_db().execute(
            "SELECT mobile FROM user_ops_lead_pool_current WHERE mobile = ?",
            ("13800138025",),
        ).fetchone()
    assert source_row["activation_state"] == "not_activated"
    assert lead_row is None


def test_history_contains_activation_patch_records_for_existing_member(client, app):
    client.post(
        "/api/admin/user-ops/import-mobile-class-terms",
        json={"pasted_text": "13800138028,5期"},
    )
    client.post(
        "/api/admin/user-ops/import-activation-status",
        json={"pasted_text": "13800138028,激活"},
    )

    with app.app_context():
        history = get_db().execute(
            """
            SELECT action_type, source_type
            FROM user_ops_lead_pool_history
            WHERE mobile = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            ("13800138028",),
        ).fetchone()
    assert history["action_type"] == "lead_pool_activation_patch"
    assert history["source_type"] == "huangxiaocan_activation_import"


def test_activation_import_updates_existing_member_and_not_create_missing_one(client, app):
    client.post(
        "/api/admin/user-ops/import-mobile-class-terms",
        json={"pasted_text": "13800138029,5期"},
    )
    client.post(
        "/api/admin/user-ops/import-activation-status",
        json={"pasted_text": "13800138029,已激活\n13800138030,未激活"},
    )

    with app.app_context():
        updated = get_db().execute(
            """
            SELECT huangxiaocan_activation_state
            FROM user_ops_lead_pool_current
            WHERE mobile = ?
            """,
            ("13800138029",),
        ).fetchone()
        missing = get_db().execute(
            """
            SELECT mobile
            FROM user_ops_lead_pool_current
            WHERE mobile = ?
            """,
            ("13800138030",),
        ).fetchone()
        source = get_db().execute(
            """
            SELECT activation_state
            FROM user_ops_huangxiaocan_activation_source
            WHERE mobile = ?
            """,
            ("13800138030",),
        ).fetchone()
    assert updated["huangxiaocan_activation_state"] == "activated"
    assert missing is None
    assert source["activation_state"] == "not_activated"


def test_migrate_legacy_user_ops_pool_to_lead_pool_ignores_signed_semantics(client, app):
    _seed_user_ops_sources(app)
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO user_ops_pool_current (
                mobile, external_userid, customer_name, owner_userid, current_status, is_wecom_bound,
                activation_status, activation_remark, class_term_no, class_term_label, source_type, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                "13800138111",
                "",
                "",
                "",
                "signed_999",
                False,
                "high_intent",
                "",
                5,
                "5期",
                "manual",
            ),
        )
        db.execute(
            """
            INSERT INTO user_ops_pool_current (
                mobile, external_userid, customer_name, owner_userid, current_status, is_wecom_bound,
                activation_status, activation_remark, class_term_no, class_term_label, source_type, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                "13800138112",
                "",
                "",
                "",
                "signed_3999",
                False,
                "not_activated",
                "",
                None,
                "",
                "experience_import",
            ),
        )
        migrated = migrate_legacy_user_ops_pool_to_lead_pool(operator="tester")
        rows = db.execute(
            """
            SELECT mobile, huangxiaocan_activation_state, class_term_label, first_entry_source, last_entry_source
            FROM user_ops_lead_pool_current
            WHERE mobile IN (?, ?)
            ORDER BY mobile ASC
            """,
            ("13800138111", "13800138112"),
        ).fetchall()

    assert migrated["migrated_count"] >= 2
    assert len(rows) == 2
    assert rows[0]["mobile"] == "13800138111"
    assert rows[0]["class_term_label"] == "5期"
    assert rows[0]["huangxiaocan_activation_state"] == "unknown"
    assert rows[0]["first_entry_source"] == "legacy_pool_migration"
    assert rows[1]["mobile"] == "13800138112"
    assert rows[1]["huangxiaocan_activation_state"] == "not_activated"


def test_external_contact_event_add_external_contact_creates_deferred_verify_job_for_any_owner(app, monkeypatch):
    detail = _build_external_contact_detail(
        external_userid="wm_auto_assign_001",
        owner_userid="sales_01",
    )
    dispatched: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr("wecom_ability_service.routes._contact_client", lambda: _FakeCallbackContactClient(detail))
    monkeypatch.setattr(
        "wecom_ability_service.routes._dispatch_background_task",
        lambda task_name, task_fn, *args, **kwargs: dispatched.append((task_name, args)),
    )

    with app.app_context():
        logged = log_external_contact_event(
            corp_id="ww-test",
            event_type="change_external_contact",
            change_type="add_external_contact",
            external_userid="wm_auto_assign_001",
            user_id="sales_01",
            event_time=1775000000,
            event_key="event-auto-assign-001",
            payload_xml="<xml></xml>",
            payload_json={"ChangeType": "add_external_contact"},
        )
        result = _process_external_contact_event(int(logged["id"]))

        assert result["ok"] is True
        job = get_db().execute(
            """
            SELECT job_type, external_userid, owner_userid, status, run_after
            FROM user_ops_deferred_jobs
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert job["job_type"] == "verify_class_term_tag_and_upsert_lead_pool"
        assert job["external_userid"] == "wm_auto_assign_001"
        assert job["owner_userid"] == "sales_01"
        assert job["status"] == "pending"
        assert str(job["run_after"] or "").strip() != ""
        assert dispatched[0][0] == "user_ops_auto_assign_class_term"


def test_external_contact_event_for_other_owner_also_creates_deferred_job(app, monkeypatch):
    detail = _build_external_contact_detail(
        external_userid="wm_auto_assign_002",
        owner_userid="sales_01",
    )
    monkeypatch.setattr("wecom_ability_service.routes._contact_client", lambda: _FakeCallbackContactClient(detail))
    monkeypatch.setattr("wecom_ability_service.routes._dispatch_background_task", lambda *args, **kwargs: None)

    with app.app_context():
        logged = log_external_contact_event(
            corp_id="ww-test",
            event_type="change_external_contact",
            change_type="add_external_contact",
            external_userid="wm_auto_assign_002",
            user_id="sales_01",
            event_time=1775000001,
            event_key="event-auto-assign-002",
            payload_xml="<xml></xml>",
            payload_json={"ChangeType": "add_external_contact"},
        )
        result = _process_external_contact_event(int(logged["id"]))

        assert result["ok"] is True
        row = get_db().execute(
            "SELECT job_type, owner_userid FROM user_ops_deferred_jobs ORDER BY id DESC LIMIT 1",
        ).fetchone()
        assert row["job_type"] == "verify_class_term_tag_and_upsert_lead_pool"
        assert row["owner_userid"] == "sales_01"


def test_external_contact_event_marks_failed_when_qrcode_automation_raises(app, monkeypatch):
    detail = _build_external_contact_detail(
        external_userid="wm_auto_assign_qrcode_fail_001",
        owner_userid="sales_01",
    )
    monkeypatch.setattr("wecom_ability_service.routes._contact_client", lambda: _FakeCallbackContactClient(detail))
    monkeypatch.setattr("wecom_ability_service.routes._dispatch_background_task", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "wecom_ability_service.http.background_jobs.handle_qrcode_enter_from_callback",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("qrcode automation exploded")),
    )

    with app.app_context():
        logged = log_external_contact_event(
            corp_id="ww-test",
            event_type="change_external_contact",
            change_type="add_external_contact",
            external_userid="wm_auto_assign_qrcode_fail_001",
            user_id="sales_01",
            event_time=1775000002,
            event_key="event-auto-assign-qrcode-fail-001",
            payload_xml="<xml></xml>",
            payload_json={"ChangeType": "add_external_contact", "State": "scene-qrcode"},
        )
        result = _process_external_contact_event(int(logged["id"]))

        assert result["ok"] is False
        assert result["status"] == "failed"
        assert "qrcode automation exploded" in result["error"]
        event_log = get_db().execute(
            """
            SELECT process_status, retry_count, error_message
            FROM wecom_external_contact_event_logs
            WHERE id = ?
            """,
            (int(logged["id"]),),
        ).fetchone()
        assert dict(event_log) == {
            "process_status": "failed",
            "retry_count": _contact_sync_retry_limit(),
            "error_message": "qrcode automation exploded",
        }


def test_deferred_job_does_not_run_before_run_after(client, app):
    _seed_zhao_contact(app, external_userid="wm_auto_due_001")

    with app.app_context():
        scheduled = schedule_user_ops_auto_assign_class_term_job(
            external_userid="wm_auto_due_001",
            owner_userid="ZhaoYanFang",
            delay_seconds=10,
        )
        assert scheduled["scheduled"] is True

    response = client.post("/api/admin/user-ops/run-deferred-jobs", json={"limit": 20})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["scanned_count"] == 0

    with app.app_context():
        job = get_db().execute(
            "SELECT status FROM user_ops_deferred_jobs WHERE external_userid = ?",
            ("wm_auto_due_001",),
        ).fetchone()
        assert job["status"] == "pending"


def test_due_deferred_job_writes_class_term_for_single_match(client, app, user_ops_contact_client):
    _seed_zhao_contact(app, external_userid="wm_auto_due_002")
    user_ops_contact_client.set_contact_detail(
        "wm_auto_due_002",
        _build_external_contact_detail(
            external_userid="wm_auto_due_002",
            owner_userid="ZhaoYanFang",
            follow_user_tags=[{"id": "tag-term-1", "name": "首期7天改变计划"}],
        ),
    )

    with app.app_context():
        scheduled = schedule_user_ops_auto_assign_class_term_job(
            external_userid="wm_auto_due_002",
            owner_userid="ZhaoYanFang",
            delay_seconds=0,
        )
        assert scheduled["scheduled"] is True

    response = client.post("/api/admin/user-ops/run-deferred-jobs", json={"limit": 20})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["success_count"] == 1
    with app.app_context():
        pool_row = get_db().execute(
            """
            SELECT mobile, external_userid, class_term_no, class_term_label, is_wecom_added, is_mobile_bound
            FROM user_ops_lead_pool_current
            WHERE external_userid = ?
            """,
            ("wm_auto_due_002",),
        ).fetchone()
        assert pool_row["class_term_no"] == 1
        assert pool_row["class_term_label"] == "1期"
        assert bool(pool_row["is_wecom_added"]) is True
        assert bool(pool_row["is_mobile_bound"]) is False
        job = get_db().execute(
            "SELECT status, job_type FROM user_ops_deferred_jobs WHERE external_userid = ?",
            ("wm_auto_due_002",),
        ).fetchone()
        assert job["status"] == "success"
        assert job["job_type"] == "verify_class_term_tag_and_upsert_lead_pool"
        history = get_db().execute(
            "SELECT source_type FROM user_ops_lead_pool_history WHERE external_userid = ? ORDER BY id DESC LIMIT 1",
            ("wm_auto_due_002",),
        ).fetchone()
        assert history["source_type"] == "verify_class_term_tag_and_upsert_lead_pool"
        refreshed_tag = get_db().execute(
            "SELECT tag_id, tag_name FROM contact_tags WHERE external_userid = ? AND userid = ?",
            ("wm_auto_due_002", "ZhaoYanFang"),
        ).fetchone()
        assert refreshed_tag["tag_id"] == "tag-term-1"


def test_due_deferred_job_conflict_is_skipped(client, app, user_ops_contact_client):
    _seed_zhao_contact(app, external_userid="wm_auto_due_003")
    user_ops_contact_client.set_contact_detail(
        "wm_auto_due_003",
        _build_external_contact_detail(
            external_userid="wm_auto_due_003",
            owner_userid="ZhaoYanFang",
            follow_user_tags=[
                {"id": "tag-term-1", "name": "首期7天改变计划"},
                {"id": "tag-term-4", "name": "0330改变计划-第4期"},
            ],
        ),
    )

    with app.app_context():
        schedule_user_ops_auto_assign_class_term_job(
            external_userid="wm_auto_due_003",
            owner_userid="ZhaoYanFang",
            delay_seconds=0,
        )

    response = client.post("/api/admin/user-ops/run-deferred-jobs", json={"limit": 20})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["conflict_count"] == 1
    with app.app_context():
        pool_row = get_db().execute(
            "SELECT class_term_no, class_term_label FROM user_ops_lead_pool_current WHERE external_userid = ?",
            ("wm_auto_due_003",),
        ).fetchone()
        assert pool_row is None
        job = get_db().execute(
            "SELECT status FROM user_ops_deferred_jobs WHERE external_userid = ?",
            ("wm_auto_due_003",),
        ).fetchone()
        assert job["status"] == "conflict"


def test_due_deferred_job_without_match_is_skipped(client, app, user_ops_contact_client):
    _seed_zhao_contact(app, external_userid="wm_auto_due_004")
    user_ops_contact_client.set_contact_detail(
        "wm_auto_due_004",
        _build_external_contact_detail(
            external_userid="wm_auto_due_004",
            owner_userid="ZhaoYanFang",
            follow_user_tags=[],
        ),
    )

    with app.app_context():
        schedule_user_ops_auto_assign_class_term_job(
            external_userid="wm_auto_due_004",
            owner_userid="ZhaoYanFang",
            delay_seconds=0,
        )

    response = client.post("/api/admin/user-ops/run-deferred-jobs", json={"limit": 20})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["skipped_count"] == 1
    with app.app_context():
        job = get_db().execute(
            "SELECT status FROM user_ops_deferred_jobs WHERE external_userid = ?",
            ("wm_auto_due_004",),
        ).fetchone()
        assert job["status"] == "skipped"
        history = get_db().execute(
            "SELECT COUNT(*) AS total FROM user_ops_lead_pool_history WHERE external_userid = ?",
            ("wm_auto_due_004",),
        ).fetchone()
        assert history["total"] == 0


def test_backfill_class_term_endpoint_is_deprecated_internal_only(client):
    response = client.post(
        "/api/admin/user-ops/backfill-class-term",
        json={"owner_userid": "sales_01", "dry_run": True},
    )
    payload = response.get_json()

    assert response.status_code == 410
    assert payload["ok"] is False
    assert payload["error"] == "deprecated_internal_only"


def test_internal_owner_backfill_route_defaults_to_dry_run(client, app, user_ops_contact_client):
    _seed_zhao_contact(app, external_userid="wmb_owner_backfill_route_001")
    _seed_owner_backfill_follow_relation(app, external_userid="wmb_owner_backfill_route_001")
    user_ops_contact_client.set_contact_detail(
        "wmb_owner_backfill_route_001",
        _build_external_contact_detail(
            external_userid="wmb_owner_backfill_route_001",
            owner_userid="ZhaoYanFang",
            follow_user_tags=[{"id": "tag-term-1", "name": "首期7天改变计划"}],
        ),
    )

    response = client.post(
        "/api/internal/user-ops/lead-pool/backfill-owner-class-terms",
        json={"owner_userid": "ZhaoYanFang", "class_term_min": 1, "class_term_max": 5},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["candidate_total"] == 1


def test_owner_backfill_candidate_enumeration_uses_active_follow_and_contact_fallback(app, user_ops_contact_client):
    _seed_zhao_contact(app, external_userid="wmb_owner_enum_001")
    _seed_owner_backfill_follow_relation(app, external_userid="wmb_owner_enum_001", relation_status="active")
    _seed_zhao_contact(app, external_userid="wmb_owner_enum_002")
    _seed_owner_backfill_follow_relation(app, external_userid="wmb_owner_enum_002", relation_status="inactive")
    _seed_sidebar_contact(app, external_userid="wmb_owner_enum_003", owner_userid="QianLan", customer_name="非赵顾问客户")
    _seed_owner_backfill_follow_relation(app, external_userid="wmb_owner_enum_003", owner_userid="QianLan", relation_status="active")
    _seed_zhao_contact(app, external_userid="wmb_owner_enum_004")

    for external_userid in [
        "wmb_owner_enum_001",
        "wmb_owner_enum_002",
        "wmb_owner_enum_003",
        "wmb_owner_enum_004",
    ]:
        user_ops_contact_client.set_contact_detail(
            external_userid,
            _build_external_contact_detail(
                external_userid=external_userid,
                owner_userid="ZhaoYanFang",
                follow_user_tags=[],
            ),
        )

    with app.app_context():
        payload = backfill_owner_class_terms_into_lead_pool(
            owner_userid="ZhaoYanFang",
            class_term_min=1,
            class_term_max=5,
            dry_run=True,
        )

    assert payload["candidate_total"] == 3
    sample_ids = {item["external_userid"] for item in payload["samples"]}
    assert "wmb_owner_enum_001" in sample_ids
    assert "wmb_owner_enum_002" in sample_ids
    assert "wmb_owner_enum_004" in sample_ids
    assert "wmb_owner_enum_003" not in sample_ids


def test_owner_backfill_only_matches_class_terms_in_requested_range(app, user_ops_contact_client):
    user_ops_contact_client._corp_tag_payload = _build_corp_tag_payload(
        [
            ("tag-term-1", "首期7天改变计划"),
            ("tag-term-6", "第6期"),
        ]
    )
    _seed_zhao_contact(app, external_userid="wmb_owner_range_001")
    _seed_owner_backfill_follow_relation(app, external_userid="wmb_owner_range_001")
    _seed_zhao_contact(app, external_userid="wmb_owner_range_002")
    _seed_owner_backfill_follow_relation(app, external_userid="wmb_owner_range_002")
    user_ops_contact_client.set_contact_detail(
        "wmb_owner_range_001",
        _build_external_contact_detail(
            external_userid="wmb_owner_range_001",
            owner_userid="ZhaoYanFang",
            follow_user_tags=[{"id": "tag-term-1", "name": "首期7天改变计划"}],
        ),
    )
    user_ops_contact_client.set_contact_detail(
        "wmb_owner_range_002",
        _build_external_contact_detail(
            external_userid="wmb_owner_range_002",
            owner_userid="ZhaoYanFang",
            follow_user_tags=[{"id": "tag-term-6", "name": "第6期"}],
        ),
    )

    with app.app_context():
        payload = backfill_owner_class_terms_into_lead_pool(
            owner_userid="ZhaoYanFang",
            class_term_min=1,
            class_term_max=5,
            dry_run=True,
        )

    decisions = {item["external_userid"]: item["decision"] for item in payload["samples"]}
    assert decisions["wmb_owner_range_001"] == "insert"
    assert decisions["wmb_owner_range_002"] == "skip"
    assert payload["class_term_distribution"]["1"] == 1


def test_owner_backfill_conflict_candidate_is_not_written(app, user_ops_contact_client):
    _seed_zhao_contact(app, external_userid="wmb_owner_conflict_001")
    _seed_owner_backfill_follow_relation(app, external_userid="wmb_owner_conflict_001")
    user_ops_contact_client.set_contact_detail(
        "wmb_owner_conflict_001",
        _build_external_contact_detail(
            external_userid="wmb_owner_conflict_001",
            owner_userid="ZhaoYanFang",
            follow_user_tags=[
                {"id": "tag-term-1", "name": "首期7天改变计划"},
                {"id": "tag-term-4", "name": "0330改变计划-第4期"},
            ],
        ),
    )

    with app.app_context():
        payload = backfill_owner_class_terms_into_lead_pool(
            owner_userid="ZhaoYanFang",
            class_term_min=1,
            class_term_max=5,
            dry_run=False,
        )
        row = get_db().execute(
            "SELECT external_userid FROM user_ops_lead_pool_current WHERE external_userid = ?",
            ("wmb_owner_conflict_001",),
        ).fetchone()

    assert payload["conflict_total"] == 1
    assert row is None


def test_owner_backfill_apply_uses_mobile_bound_merge(app, user_ops_contact_client):
    _seed_zhao_contact(app, external_userid="wmb_owner_mobile_bound_001")
    _seed_owner_backfill_follow_relation(app, external_userid="wmb_owner_mobile_bound_001")
    _seed_owner_backfill_binding(
        app,
        external_userid="wmb_owner_mobile_bound_001",
        mobile="13800138188",
        person_id=301,
    )
    with app.app_context():
        upsert_user_ops_lead_pool_member(
            mobile="13800138188",
            entry_source="student_import",
            operator="tester",
            remark="seed phone-keyed member",
        )
    user_ops_contact_client.set_contact_detail(
        "wmb_owner_mobile_bound_001",
        _build_external_contact_detail(
            external_userid="wmb_owner_mobile_bound_001",
            owner_userid="ZhaoYanFang",
            follow_user_tags=[{"id": "tag-term-4", "name": "0330改变计划-第4期"}],
        ),
    )

    with app.app_context():
        payload = backfill_owner_class_terms_into_lead_pool(
            owner_userid="ZhaoYanFang",
            class_term_min=1,
            class_term_max=5,
            dry_run=False,
        )
        row = get_db().execute(
            """
            SELECT mobile, external_userid, is_mobile_bound, class_term_no, class_term_label
            FROM user_ops_lead_pool_current
            WHERE mobile = ?
            """,
            ("13800138188",),
        ).fetchone()

    assert payload["estimated_update_total"] == 1
    assert row["external_userid"] == "wmb_owner_mobile_bound_001"
    assert bool(row["is_mobile_bound"]) is True
    assert row["class_term_no"] == 4
    assert row["class_term_label"] == "4期"


def test_owner_backfill_apply_allows_external_only_member(app, user_ops_contact_client):
    _seed_zhao_contact(app, external_userid="wmb_owner_external_only_001")
    _seed_owner_backfill_follow_relation(app, external_userid="wmb_owner_external_only_001")
    user_ops_contact_client.set_contact_detail(
        "wmb_owner_external_only_001",
        _build_external_contact_detail(
            external_userid="wmb_owner_external_only_001",
            owner_userid="ZhaoYanFang",
            follow_user_tags=[{"id": "tag-term-5", "name": "第5期"}],
        ),
    )

    with app.app_context():
        payload = backfill_owner_class_terms_into_lead_pool(
            owner_userid="ZhaoYanFang",
            class_term_min=1,
            class_term_max=5,
            dry_run=False,
        )
        row = get_db().execute(
            """
            SELECT mobile, external_userid, is_mobile_bound, class_term_no
            FROM user_ops_lead_pool_current
            WHERE external_userid = ?
            """,
            ("wmb_owner_external_only_001",),
        ).fetchone()

    assert payload["estimated_insert_total"] == 1
    assert row["mobile"] == ""
    assert bool(row["is_mobile_bound"]) is False
    assert row["class_term_no"] == 5


def test_owner_backfill_reports_missing_term_two_mapping_when_real_tag_absent(app, user_ops_contact_client):
    _seed_zhao_contact(app, external_userid="wmb_owner_term2_missing_001")
    _seed_owner_backfill_follow_relation(app, external_userid="wmb_owner_term2_missing_001")
    user_ops_contact_client.set_contact_detail(
        "wmb_owner_term2_missing_001",
        _build_external_contact_detail(
            external_userid="wmb_owner_term2_missing_001",
            owner_userid="ZhaoYanFang",
            follow_user_tags=[],
        ),
    )

    with app.app_context():
        payload = backfill_owner_class_terms_into_lead_pool(
            owner_userid="ZhaoYanFang",
            class_term_min=1,
            class_term_max=5,
            dry_run=True,
        )

    assert payload["term_2_mapping"]["exists"] is False
    assert "2期 mapping missing" in payload["warnings"]
    assert "2期 skipped because no real tag mapping found" in payload["warnings"]


def test_owner_backfill_discovers_term_two_from_live_tags(app, user_ops_contact_client):
    user_ops_contact_client._corp_tag_payload = _build_corp_tag_payload(
        [
            ("tag-term-1", "首期7天改变计划"),
            ("tag-term-2", "0315改变计划-第2期"),
            ("tag-term-4", "0330改变计划-第4期"),
        ]
    )
    _seed_zhao_contact(app, external_userid="wmb_owner_term2_live_001")
    _seed_owner_backfill_follow_relation(app, external_userid="wmb_owner_term2_live_001")
    user_ops_contact_client.set_contact_detail(
        "wmb_owner_term2_live_001",
        _build_external_contact_detail(
            external_userid="wmb_owner_term2_live_001",
            owner_userid="ZhaoYanFang",
            follow_user_tags=[{"id": "tag-term-2", "name": "0315改变计划-第2期"}],
        ),
    )

    with app.app_context():
        payload = backfill_owner_class_terms_into_lead_pool(
            owner_userid="ZhaoYanFang",
            class_term_min=1,
            class_term_max=5,
            dry_run=True,
        )

    assert payload["term_2_mapping"]["exists"] is True
    sample = next(item for item in payload["samples"] if item["external_userid"] == "wmb_owner_term2_live_001")
    assert sample["matched_class_term_no"] == 2
    assert sample["matched_class_term_label"] == "2期"


def test_owner_backfill_dry_run_does_not_write_tables(app, user_ops_contact_client):
    _seed_zhao_contact(app, external_userid="wmb_owner_dry_run_001")
    _seed_owner_backfill_follow_relation(app, external_userid="wmb_owner_dry_run_001")
    user_ops_contact_client.set_contact_detail(
        "wmb_owner_dry_run_001",
        _build_external_contact_detail(
            external_userid="wmb_owner_dry_run_001",
            owner_userid="ZhaoYanFang",
            follow_user_tags=[{"id": "tag-term-1", "name": "首期7天改变计划"}],
        ),
    )

    with app.app_context():
        before_current = get_db().execute("SELECT COUNT(*) AS total FROM user_ops_lead_pool_current").fetchone()["total"]
        before_history = get_db().execute("SELECT COUNT(*) AS total FROM user_ops_lead_pool_history").fetchone()["total"]
        backfill_owner_class_terms_into_lead_pool(
            owner_userid="ZhaoYanFang",
            class_term_min=1,
            class_term_max=5,
            dry_run=True,
        )
        after_current = get_db().execute("SELECT COUNT(*) AS total FROM user_ops_lead_pool_current").fetchone()["total"]
        after_history = get_db().execute("SELECT COUNT(*) AS total FROM user_ops_lead_pool_history").fetchone()["total"]

    assert before_current == after_current
    assert before_history == after_history


def test_owner_backfill_apply_writes_current_and_history(app, user_ops_contact_client):
    _seed_zhao_contact(app, external_userid="wmb_owner_apply_001")
    _seed_owner_backfill_follow_relation(app, external_userid="wmb_owner_apply_001")
    user_ops_contact_client.set_contact_detail(
        "wmb_owner_apply_001",
        _build_external_contact_detail(
            external_userid="wmb_owner_apply_001",
            owner_userid="ZhaoYanFang",
            follow_user_tags=[{"id": "tag-term-3", "name": "0322改变计划-第3期"}],
        ),
    )

    with app.app_context():
        payload = backfill_owner_class_terms_into_lead_pool(
            owner_userid="ZhaoYanFang",
            class_term_min=1,
            class_term_max=5,
            dry_run=False,
        )
        current = get_db().execute(
            """
            SELECT external_userid, owner_userid, class_term_no, class_term_label, first_entry_source, last_entry_source
            FROM user_ops_lead_pool_current
            WHERE external_userid = ?
            """,
            ("wmb_owner_apply_001",),
        ).fetchone()
        history = get_db().execute(
            """
            SELECT external_userid, source_type
            FROM user_ops_lead_pool_history
            WHERE external_userid = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            ("wmb_owner_apply_001",),
        ).fetchone()

    assert payload["applied_total"] == 1
    assert current["owner_userid"] == "ZhaoYanFang"
    assert current["class_term_no"] == 3
    assert current["class_term_label"] == "3期"
    assert current["first_entry_source"] == "zhaoyanfang_owner_backfill_20260329"
    assert current["last_entry_source"] == "zhaoyanfang_owner_backfill_20260329"
    assert history["source_type"] == "zhaoyanfang_owner_backfill_20260329"


def test_owner_backfill_invalid_test_candidate_is_skipped_without_error(app, user_ops_contact_client):
    _seed_zhao_contact(app, external_userid="wm_auto_assign_001")
    _seed_owner_backfill_follow_relation(app, external_userid="wm_auto_assign_001")

    with app.app_context():
        payload = backfill_owner_class_terms_into_lead_pool(
            owner_userid="ZhaoYanFang",
            class_term_min=1,
            class_term_max=5,
            dry_run=True,
        )

    sample = next(item for item in payload["samples"] if item["external_userid"] == "wm_auto_assign_001")
    invalid_sample = next(
        item for item in payload["invalid_test_candidate_samples"] if item["external_userid"] == "wm_auto_assign_001"
    )
    assert payload["error_total"] == 0
    assert payload["invalid_test_candidate_total"] == 1
    assert payload["matched_candidate_total"] == 0
    assert sample["decision"] == "skip"
    assert sample["decision_reason"] == "invalid_test_candidate"
    assert sample["final_owner_userid"] == "ZhaoYanFang"
    assert invalid_sample["decision_reason"] == "invalid_test_candidate"


def test_owner_backfill_apply_pins_target_owner_and_audits_owner_mismatch(app, user_ops_contact_client):
    _seed_zhao_contact(app, external_userid="wmb_owner_mismatch_001")
    _seed_owner_backfill_follow_relation(app, external_userid="wmb_owner_mismatch_001")
    user_ops_contact_client.set_contact_detail(
        "wmb_owner_mismatch_001",
        _build_external_contact_detail(
            external_userid="wmb_owner_mismatch_001",
            owner_userid="ZhaoYanFang",
            follow_user_tags=[{"id": "tag-term-1", "name": "首期7天改变计划"}],
        ),
    )

    with app.app_context():
        db = get_db()
        db.execute(
            "UPDATE contacts SET owner_userid = ?, customer_name = ? WHERE external_userid = ?",
            ("ZhaoJingZi", "Owner Drift", "wmb_owner_mismatch_001"),
        )
        db.commit()
        payload = backfill_owner_class_terms_into_lead_pool(
            owner_userid="ZhaoYanFang",
            class_term_min=1,
            class_term_max=5,
            dry_run=False,
        )
        current = get_db().execute(
            """
            SELECT external_userid, owner_userid, class_term_no
            FROM user_ops_lead_pool_current
            WHERE external_userid = ?
            """,
            ("wmb_owner_mismatch_001",),
        ).fetchone()

    sample = next(item for item in payload["samples"] if item["external_userid"] == "wmb_owner_mismatch_001")
    mismatch_sample = next(
        item for item in payload["owner_mismatch_samples"] if item["external_userid"] == "wmb_owner_mismatch_001"
    )
    assert payload["owner_mismatch_total"] == 1
    assert sample["target_owner_userid"] == "ZhaoYanFang"
    assert sample["resolved_owner_userid"] == "ZhaoJingZi"
    assert sample["final_owner_userid"] == "ZhaoYanFang"
    assert current["owner_userid"] == "ZhaoYanFang"
    assert current["class_term_no"] == 1


def test_backfill_class_term_for_owner_dry_run_routes_through_application_owner(app, user_ops_contact_client):
    _seed_zhao_contact(app, external_userid="wmb_owner_compat_001")
    _seed_owner_backfill_follow_relation(app, external_userid="wmb_owner_compat_001")
    user_ops_contact_client.set_contact_detail(
        "wmb_owner_compat_001",
        _build_external_contact_detail(
            external_userid="wmb_owner_compat_001",
            owner_userid="ZhaoYanFang",
            follow_user_tags=[{"id": "tag-term-1", "name": "首期7天改变计划"}],
        ),
    )

    with app.app_context():
        payload = backfill_class_term_for_owner(
            owner_userid="ZhaoYanFang",
            operator="tester",
        )

    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["owner_userid"] == "ZhaoYanFang"
    assert "tag_definition_sync" in payload
    assert "tag_refresh" in payload


def test_routing_config_keeps_existing_owner_targets(app):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO owner_role_map (userid, display_name, role, active)
            VALUES (?, ?, ?, ?), (?, ?, ?, ?)
            """,
            (
                "sales_01",
                "销售顾问",
                "sales",
                True,
                "delivery_01",
                "交付顾问",
                "delivery",
                True,
            ),
        )
        db.execute(
            """
            INSERT INTO signup_tag_rules (tag_id, tag_name, signup_status, active, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            ("tag_3999", "已报名3999", "signed_3999", True),
        )
        db.commit()

        payload = get_routing_config()

    assert payload["routing_rules"]["pre_signup"]["route_owner_userid"] == DEFAULT_SALES_ROUTE_OWNER_USERID
    assert payload["routing_rules"]["signed_999"]["route_owner_userid"] == DEFAULT_SALES_ROUTE_OWNER_USERID
    assert payload["routing_rules"]["signed_3999"]["route_owner_userid"] == DEFAULT_DELIVERY_ROUTE_OWNER_USERID
    assert payload["routing_rules"]["signed_3999"]["when_owner_role_sales"] == "delivery_redirect"
    assert payload["routing_rules"]["signed_3999"]["when_owner_role_delivery"] == "delivery_handle"


def test_resolve_contact_routing_context_keeps_existing_behavior():
    assert resolve_contact_routing_context("sales_01", "", "lead") == {
        "routing_target": "manual_review",
        "route_owner_userid": "",
        "reason": "owner_role_missing",
    }
    assert resolve_contact_routing_context("sales_01", "sales", "lead") == {
        "routing_target": "sales_handle",
        "route_owner_userid": DEFAULT_SALES_ROUTE_OWNER_USERID,
    }
    assert resolve_contact_routing_context("sales_01", "sales", "signed_3999") == {
        "routing_target": "delivery_redirect",
        "route_owner_userid": DEFAULT_DELIVERY_ROUTE_OWNER_USERID,
    }
    assert resolve_contact_routing_context("delivery_01", "delivery", "signed_3999") == {
        "routing_target": "delivery_handle",
        "route_owner_userid": DEFAULT_DELIVERY_ROUTE_OWNER_USERID,
    }


def test_owner_backfill_entry_source_override_moves_out_of_services():
    assert _default_owner_class_term_backfill_entry_source(DEFAULT_SALES_ROUTE_OWNER_USERID) == (
        "zhaoyanfang_owner_backfill_20260329"
    )
    assert _default_owner_class_term_backfill_entry_source("Owner A") == "owner_a_owner_backfill_20260329"
