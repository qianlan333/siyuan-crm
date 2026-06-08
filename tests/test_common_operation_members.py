from __future__ import annotations

from urllib.parse import quote

from flask import Flask

from aicrm_next.shared.operation_members import operation_members_payload
from wecom_ability_service.db import get_db


PRIMARY_MEMBERS = [
    ("WangJiaYin", "Anne嘉茵"),
    ("ZhangKaiRui", "Summer乔几木"),
    ("HuangYouCan_1", "Celine倪忆菁"),
    ("support1", "YoYo"),
]

FILLER_MEMBERS = [
    ("ops_alpha_01", "运营 Alpha 01"),
    ("ops_alpha_02", "运营 Alpha 02"),
    ("ops_alpha_03", "运营 Alpha 03"),
    ("ops_alpha_04", "运营 Alpha 04"),
    ("ops_alpha_05", "运营 Alpha 05"),
    ("ops_alpha_06", "运营 Alpha 06"),
    ("ops_alpha_07", "运营 Alpha 07"),
    ("ops_alpha_08", "运营 Alpha 08"),
]


def _seed_operation_members(app) -> None:
    with app.app_context():
        db = get_db()
        for user_id, display_name in [*PRIMARY_MEMBERS, *FILLER_MEMBERS]:
            db.execute(
                """
                INSERT INTO admin_users (wecom_userid, wecom_corpid, display_name, is_active)
                VALUES (?, ?, ?, TRUE)
                ON CONFLICT (wecom_corpid, wecom_userid)
                DO UPDATE SET display_name = EXCLUDED.display_name, is_active = TRUE
                """,
                (user_id, app.config["WECOM_CORP_ID"], display_name),
            )
        db.execute(
            """
            INSERT INTO owner_role_map (userid, display_name, role, active)
            VALUES (?, ?, ?, TRUE)
            ON CONFLICT (userid)
            DO UPDATE SET display_name = EXCLUDED.display_name, role = EXCLUDED.role, active = TRUE
            """,
            ("support1", "YoYo", "自动化运营"),
        )
        db.execute(
            """
            INSERT INTO owner_role_map (userid, display_name, role, active)
            VALUES (?, ?, ?, FALSE)
            ON CONFLICT (userid)
            DO UPDATE SET display_name = EXCLUDED.display_name, role = EXCLUDED.role, active = FALSE
            """,
            ("inactive_owner", "停用负责人", "渠道运营"),
        )
        db.commit()


def _get_json(client, query: str = "") -> dict:
    response = client.get(f"/api/admin/common/operation-members{query}")
    assert response.status_code == 200
    return response.get_json()


def test_common_operation_members_default_contract(app, client):
    _seed_operation_members(app)

    payload = _get_json(client)
    assert {"items", "total", "page", "page_size"} <= set(payload)
    assert payload["page"] == 1
    assert payload["page_size"] == 30
    assert payload["total"] >= len(PRIMARY_MEMBERS) + len(FILLER_MEMBERS)
    assert isinstance(payload["items"], list)
    assert payload["items"]

    by_user_id = {item["user_id"]: item for item in payload["items"]}
    assert "inactive_owner" not in by_user_id
    assert by_user_id["WangJiaYin"] == {
        "user_id": "WangJiaYin",
        "display_name": "Anne嘉茵",
        "avatar_url": "",
        "department_name": "",
        "status": "active",
        "source": "admin_user",
        "extra": {},
    }
    for item in payload["items"]:
        assert {"user_id", "display_name", "avatar_url", "status"} <= set(item)
        assert item["user_id"]
        assert isinstance(item["avatar_url"], str)
        assert not item["avatar_url"].startswith("data:")
        assert "ui-avatars" not in item["avatar_url"]


def test_common_operation_members_searches_names_user_ids_and_case_insensitively(app, client):
    _seed_operation_members(app)

    expected = {
        "嘉茵": "WangJiaYin",
        "乔几木": "ZhangKaiRui",
        "倪忆菁": "HuangYouCan_1",
        "Anne": "WangJiaYin",
        "Summer": "ZhangKaiRui",
        "Celine": "HuangYouCan_1",
        "WangJiaYin": "WangJiaYin",
        "ZhangKaiRui": "ZhangKaiRui",
        "support1": "support1",
        "HuangYouCan_1": "HuangYouCan_1",
        "wangjiayin": "WangJiaYin",
        "WANGJIAYIN": "WangJiaYin",
        "Support1": "support1",
    }
    for keyword, user_id in expected.items():
        payload = _get_json(client, f"?q={quote(keyword)}")
        assert any(item["user_id"] == user_id for item in payload["items"]), keyword
        assert all(item["user_id"] for item in payload["items"])

    missing = _get_json(client, "?q=not_exist_abc_123")
    assert missing["items"] == []
    assert missing["total"] == 0


def test_common_operation_members_pagination_and_page_size_limits(app, client):
    _seed_operation_members(app)

    page_1 = _get_json(client, "?page=1&page_size=5")
    page_2 = _get_json(client, "?page=2&page_size=5")
    assert page_1["page"] == 1
    assert page_2["page"] == 2
    assert page_1["page_size"] == 5
    assert page_2["page_size"] == 5
    assert page_1["total"] == page_2["total"]
    assert len(page_1["items"]) <= 5
    assert len(page_2["items"]) <= 5
    assert {item["user_id"] for item in page_1["items"]}.isdisjoint({item["user_id"] for item in page_2["items"]})

    assert _get_json(client, "?page_size=1")["page_size"] == 1
    assert _get_json(client, "?page_size=100")["page_size"] == 100
    capped = _get_json(client, "?page_size=999")
    assert capped["page_size"] == 100
    assert len(capped["items"]) <= 100


def test_common_operation_members_include_inactive_is_opt_in(app, client):
    _seed_operation_members(app)

    hidden_by_default = _get_json(client, "?q=inactive_owner")
    assert hidden_by_default["items"] == []

    inactive = _get_json(client, "?q=inactive_owner&include_inactive=1")
    assert inactive["items"]
    assert inactive["items"][0]["user_id"] == "inactive_owner"
    assert inactive["items"][0]["status"] == "inactive"


def test_common_operation_members_dedupes_user_ids_in_route_results(app, client):
    _seed_operation_members(app)
    with app.app_context():
        get_db().execute(
            """
            INSERT INTO owner_role_map (userid, display_name, role, active)
            VALUES (?, ?, ?, TRUE)
            ON CONFLICT (userid)
            DO UPDATE SET display_name = EXCLUDED.display_name, role = EXCLUDED.role, active = TRUE
            """,
            ("WangJiaYin", "Anne嘉茵渠道负责人", "渠道运营"),
        )
        get_db().commit()

    payload = _get_json(client, "?q=WangJiaYin")
    user_ids = [item["user_id"] for item in payload["items"]]
    assert user_ids.count("WangJiaYin") == 1
    assert payload["items"][0]["display_name"] == "Anne嘉茵渠道负责人"


def test_operation_members_service_prefers_real_avatar_and_complete_name_when_deduping():
    payload = operation_members_payload(
        [
            {
                "user_id": "WangJiaYin",
                "display_name": "Anne",
                "avatar_url": "",
                "status": "active",
                "source": "admin_user",
                "priority": 20,
            },
            {
                "user_id": "WangJiaYin",
                "display_name": "Anne嘉茵完整姓名",
                "raw_payload_json": '{"avatar":"https://cdn.example.test/avatar/wang.png","mobile":"18800001234"}',
                "department_name": "渠道运营",
                "status": "active",
                "source": "wecom_directory",
                "priority": 10,
            },
            {
                "user_id": "support1",
                "display_name": "YoYo",
                "avatar_url": "",
                "status": "active",
                "source": "owner_role_map",
                "priority": 30,
            },
        ],
        q="1234",
    )

    assert payload["total"] == 1
    assert payload["items"][0]["user_id"] == "WangJiaYin"
    assert payload["items"][0]["display_name"] == "Anne嘉茵完整姓名"
    assert payload["items"][0]["avatar_url"] == "https://cdn.example.test/avatar/wang.png"


def test_operation_members_service_covers_search_pagination_and_inactive_contract_without_database():
    rows = [
        {
            "user_id": user_id,
            "display_name": display_name,
            "avatar_url": "",
            "status": "active",
            "source": "admin_user",
            "priority": 20,
        }
        for user_id, display_name in [*PRIMARY_MEMBERS, *FILLER_MEMBERS]
    ]
    rows.append(
        {
            "user_id": "inactive_owner",
            "display_name": "停用负责人",
            "status": "inactive",
            "source": "owner_role_map",
            "priority": 30,
        }
    )

    default_payload = operation_members_payload(rows)
    assert default_payload["page"] == 1
    assert default_payload["page_size"] == 30
    assert default_payload["total"] == len(PRIMARY_MEMBERS) + len(FILLER_MEMBERS)
    assert isinstance(default_payload["items"], list)
    assert all({"user_id", "display_name", "avatar_url", "status"} <= set(item) for item in default_payload["items"])
    assert all(item["user_id"] for item in default_payload["items"])
    assert all(item["avatar_url"] == "" for item in default_payload["items"])

    for keyword, user_id in {
        "嘉茵": "WangJiaYin",
        "乔几木": "ZhangKaiRui",
        "倪忆菁": "HuangYouCan_1",
        "Anne": "WangJiaYin",
        "Summer": "ZhangKaiRui",
        "Celine": "HuangYouCan_1",
        "WangJiaYin": "WangJiaYin",
        "ZhangKaiRui": "ZhangKaiRui",
        "support1": "support1",
        "HuangYouCan_1": "HuangYouCan_1",
        "wangjiayin": "WangJiaYin",
        "WANGJIAYIN": "WangJiaYin",
        "Support1": "support1",
    }.items():
        payload = operation_members_payload(rows, q=keyword)
        assert any(item["user_id"] == user_id for item in payload["items"]), keyword

    assert operation_members_payload(rows, q="not_exist_abc_123")["items"] == []
    assert operation_members_payload(rows, page=1, page_size=5)["page_size"] == 5
    assert operation_members_payload(rows, page=2, page_size=5)["page"] == 2
    assert operation_members_payload(rows, page_size=1)["page_size"] == 1
    assert operation_members_payload(rows, page_size=100)["page_size"] == 100
    assert operation_members_payload(rows, page_size=999)["page_size"] == 100
    assert operation_members_payload(rows, q="inactive_owner")["items"] == []
    inactive = operation_members_payload(rows, q="inactive_owner", include_inactive=True)
    assert inactive["items"][0]["status"] == "inactive"


def test_common_operation_members_http_route_is_registered_at_stable_path(monkeypatch):
    from wecom_ability_service.http import common_operation_members as route_module

    captured = {}

    def fake_search(args):
        captured["args"] = dict(args)
        return {"items": [], "total": 0, "page": 2, "page_size": 100}

    monkeypatch.setattr(route_module, "search_operation_members_from_request_args", fake_search)
    app = Flask(__name__)
    app.add_url_rule(
        "/api/admin/common/operation-members",
        view_func=route_module.api_operation_members,
        methods=["GET"],
    )

    response = app.test_client().get(
        "/api/admin/common/operation-members?q=Anne&scope=automation&page=2&page_size=999&include_inactive=1"
    )

    assert response.status_code == 200
    assert response.get_json() == {"items": [], "total": 0, "page": 2, "page_size": 100}
    assert captured["args"] == {
        "q": "Anne",
        "scope": "automation",
        "page": "2",
        "page_size": "999",
        "include_inactive": "1",
    }
