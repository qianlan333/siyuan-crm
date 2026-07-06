from __future__ import annotations

from conftest import make_client


def _card_map(payload: dict) -> dict[str, int]:
    return {item["key"]: item["value"] for item in payload["cards"]}


def _ids(payload: dict) -> set[int]:
    return {item["id"] for item in payload["items"]}


def test_user_ops_overview_returns_8_cards() -> None:
    payload = make_client().get("/api/admin/user-ops/overview").json()
    assert payload["ok"] is True
    assert [card["label"] for card in payload["cards"]] == [
        "引流品总数",
        "已加微",
        "未加微",
        "已绑手机号",
        "未绑手机号",
        "黄小璨已激活",
        "黄小璨未激活",
        "激活待录入",
    ]


def test_user_ops_overview_counts_match_list_filter_scope() -> None:
    client = make_client()
    overview = client.get("/api/admin/user-ops/overview?wecom_status=added&class_term_no=2026-05-A").json()
    items = client.get("/api/admin/user-ops/list?wecom_status=added&class_term_no=2026-05-A").json()["items"]
    assert _card_map(overview)["lead_pool_total_count"] == len(items) == 2


def test_user_ops_list_item_fields_complete() -> None:
    item = make_client().get("/api/admin/user-ops/list").json()["items"][0]
    for key in [
        "id",
        "mobile",
        "external_userid",
        "customer_name",
        "owner_userid",
        "owner_display_name",
        "class_term_no",
        "class_term_label",
        "source_type",
        "created_at",
        "updated_at",
        "is_added_wecom",
        "is_wecom_added",
        "is_mobile_bound",
        "activation_bucket",
        "activation_bucket_label",
        "huangxiaocan_activation_state",
        "huangxiaocan_activation_state_label",
        "do_not_disturb",
        "do_not_disturb_reasons",
        "can_open_customer_detail",
        "can_batch_send",
    ]:
        assert key in item


def test_user_ops_filter_wecom_added_and_not_added() -> None:
    client = make_client()
    assert _ids(client.get("/api/admin/user-ops/list?wecom_status=added").json()) == {1, 2, 4}
    assert _ids(client.get("/api/admin/user-ops/list?wecom_status=not_added").json()) == {3}


def test_user_ops_filter_mobile_bound_and_unbound() -> None:
    client = make_client()
    assert _ids(client.get("/api/admin/user-ops/list?mobile_binding_status=bound").json()) == {1, 3, 4}
    assert _ids(client.get("/api/admin/user-ops/list?mobile_binding_status=unbound").json()) == {2}


def test_user_ops_filter_activation_buckets() -> None:
    client = make_client()
    assert _ids(client.get("/api/admin/user-ops/list?activation_bucket=activated").json()) == {1}
    assert _ids(client.get("/api/admin/user-ops/list?activation_bucket=not_activated").json()) == {3, 4}
    assert _ids(client.get("/api/admin/user-ops/list?activation_bucket=pending_input").json()) == {2}


def test_user_ops_keyword_filter_matches_owner_and_customer_fields() -> None:
    client = make_client()
    assert _ids(client.get("/api/admin/user-ops/list?keyword=赵燕芳").json()) == {1, 3}
    assert _ids(client.get("/api/admin/user-ops/list?keyword=wx_ext_004").json()) == {4}
    assert _ids(client.get("/api/admin/user-ops/list?keyword=13900139000").json()) == {3}


def test_user_ops_multiple_filters_are_and() -> None:
    payload = make_client().get(
        "/api/admin/user-ops/list?class_term_no=2026-05-B&wecom_status=added&activation_bucket=not_activated"
    ).json()
    assert _ids(payload) == {4}


def test_user_ops_do_not_disturb_enable_by_external_userid() -> None:
    payload = make_client().post(
        "/api/admin/user-ops/do-not-disturb",
        json={"external_userid": "wx_ext_001", "reason_code": "manual_set", "reason_text": "运营设置"},
    ).json()
    assert payload["ok"] is True
    assert payload["target"]["external_userid"] == "wx_ext_001"
    assert payload["do_not_disturb"] is True
    assert any(reason["source"] == "manual" for reason in payload["do_not_disturb_reasons"])


def test_user_ops_do_not_disturb_enable_by_mobile() -> None:
    payload = make_client().post(
        "/api/admin/user-ops/do-not-disturb",
        json={"mobile": "13800138000", "reason_code": "manual_set", "reason_text": "手动暂停"},
    ).json()
    assert payload["ok"] is True
    assert payload["target"]["external_userid"] == "wx_ext_001"
    assert any(reason["reason_text"] == "手动暂停" for reason in payload["do_not_disturb_reasons"])


def test_user_ops_do_not_disturb_cancel_manual_reason() -> None:
    client = make_client()
    client.post("/api/admin/user-ops/do-not-disturb", json={"external_userid": "wx_ext_001", "reason_code": "manual_set"})
    payload = client.post(
        "/api/admin/user-ops/do-not-disturb",
        json={"external_userid": "wx_ext_001", "reason_code": "manual_set", "action": "cancel"},
    ).json()
    assert payload["ok"] is True
    assert payload["do_not_disturb"] is False
    assert payload["do_not_disturb_reasons"] == []


def test_user_ops_do_not_disturb_cancel_manual_does_not_remove_auto_reason() -> None:
    client = make_client()
    client.post("/api/admin/user-ops/do-not-disturb", json={"external_userid": "wx_ext_002", "reason_code": "manual_set"})
    payload = client.post(
        "/api/admin/user-ops/do-not-disturb",
        json={"external_userid": "wx_ext_002", "reason_code": "manual_set", "action": "cancel"},
    ).json()
    assert payload["ok"] is True
    assert payload["do_not_disturb"] is True
    assert [reason["source"] for reason in payload["do_not_disturb_reasons"]] == ["auto"]


def test_user_ops_do_not_disturb_target_not_found() -> None:
    response = make_client().post(
        "/api/admin/user-ops/do-not-disturb",
        json={"external_userid": "missing_ext", "reason_code": "manual_set"},
    )
    assert response.status_code == 404
    assert "target is not in user_ops_pool_current" in response.text


def test_user_ops_do_not_disturb_missing_target_returns_400() -> None:
    response = make_client().post("/api/admin/user-ops/do-not-disturb", json={"reason_code": "manual_set"})
    assert response.status_code == 400
    assert "external_userid or mobile is required" in response.text


def test_user_ops_preview_all_filtered() -> None:
    payload = make_client().post(
        "/api/admin/user-ops/batch-send/preview",
        json={"selection_mode": "all_filtered", "content": "hello"},
    ).json()
    assert payload["selected_count"] == 4
    assert payload["eligible_count"] == 1
    assert payload["final_targets"][0]["external_userid"] == "wx_ext_001"


def test_user_ops_preview_manual_selected_ids() -> None:
    payload = make_client().post(
        "/api/admin/user-ops/batch-send/preview",
        json={"selection_mode": "manual", "selected_ids": [1, 4], "content": "hello"},
    ).json()
    assert payload["selected_count"] == 2
    assert payload["eligible_count"] == 1
    assert payload["skipped_by_reason"]["missing_owner_userid"] == 1


def test_user_ops_preview_excluded_ids() -> None:
    payload = make_client().post(
        "/api/admin/user-ops/batch-send/preview",
        json={"selection_mode": "all_filtered", "excluded_ids": [1], "content": "hello"},
    ).json()
    assert payload["selected_count"] == 3
    assert payload["eligible_count"] == 0


def test_user_ops_preview_skips_missing_external_userid() -> None:
    payload = make_client().post(
        "/api/admin/user-ops/batch-send/preview",
        json={"selection_mode": "manual", "selected_ids": [3], "content": "hello"},
    ).json()
    assert payload["skipped_by_reason"]["missing_external_userid"] == 1


def test_user_ops_preview_skips_do_not_disturb() -> None:
    payload = make_client().post(
        "/api/admin/user-ops/batch-send/preview",
        json={"selection_mode": "manual", "selected_ids": [2], "content": "hello"},
    ).json()
    assert payload["skipped_by_reason"]["do_not_disturb"] == 1


def test_user_ops_preview_skips_missing_owner_userid() -> None:
    payload = make_client().post(
        "/api/admin/user-ops/batch-send/preview",
        json={"selection_mode": "manual", "selected_ids": [4], "content": "hello"},
    ).json()
    assert payload["skipped_by_reason"]["missing_owner_userid"] == 1


def test_user_ops_preview_include_do_not_disturb_includes_dnd_target() -> None:
    payload = make_client().post(
        "/api/admin/user-ops/batch-send/preview",
        json={"selection_mode": "manual", "selected_ids": [2], "include_do_not_disturb": True, "content": "hello"},
    ).json()
    assert payload["eligible_count"] == 1
    assert payload["final_targets"][0]["external_userid"] == "wx_ext_002"


def test_user_ops_preview_owner_buckets_grouped_correctly() -> None:
    payload = make_client().post(
        "/api/admin/user-ops/batch-send/preview",
        json={"selection_mode": "manual", "selected_ids": [1, 2], "include_do_not_disturb": True, "content": "hello"},
    ).json()
    assert {bucket["owner_userid"]: bucket["target_count"] for bucket in payload["owner_buckets"]} == {
        "LiuXiao": 1,
        "ZhaoYanFang": 1,
    }


def test_user_ops_execute_without_confirm_returns_400() -> None:
    response = make_client().post(
        "/api/admin/user-ops/batch-send/execute",
        json={"selection_mode": "all_filtered", "content": "hello", "confirm": False},
    )
    assert response.status_code == 400
    assert "confirm=true is required" in response.text


def test_user_ops_execute_with_confirm_creates_send_record() -> None:
    client = make_client()
    executed = client.post(
        "/api/admin/user-ops/batch-send/execute",
        json={"selection_mode": "manual", "selected_ids": [1], "content": "hello", "confirm": True},
    ).json()
    records = client.get("/api/admin/user-ops/send-records").json()
    assert executed["record_id"] == records["items"][0]["record_id"]
    assert records["items"][0]["sent_count"] == 1


def test_user_ops_execute_groups_by_owner_userid() -> None:
    payload = make_client().post(
        "/api/admin/user-ops/batch-send/execute",
        json={
            "selection_mode": "manual",
            "selected_ids": [1, 2],
            "include_do_not_disturb": True,
            "content": "hello",
            "confirm": True,
        },
    ).json()
    assert {result["owner_userid"] for result in payload["task_results"]} == {"ZhaoYanFang", "LiuXiao"}


def test_user_ops_execute_uses_fake_dispatch_not_real_wecom() -> None:
    payload = make_client().post(
        "/api/admin/user-ops/batch-send/execute",
        json={"selection_mode": "manual", "selected_ids": [1], "content": "hello", "confirm": True},
    ).json()
    assert payload["execution_summary"]["dispatch_adapter"] == "fake_wecom"
    assert payload["task_results"][0]["dispatch_adapter"] == "fake_wecom"


def test_user_ops_execute_returns_task_results() -> None:
    payload = make_client().post(
        "/api/admin/user-ops/batch-send/execute",
        json={"selection_mode": "manual", "selected_ids": [1], "content": "hello", "confirm": True},
    ).json()
    result = payload["task_results"][0]
    for key in [
        "owner_userid",
        "sender_userid",
        "owner_display_name",
        "external_userids",
        "external_userid_count",
        "target_count",
        "task_id",
        "status",
        "status_label",
        "error_message",
    ]:
        assert key in result


def test_user_ops_send_records_list_returns_latest() -> None:
    client = make_client()
    executed = client.post(
        "/api/admin/user-ops/batch-send/execute",
        json={"selection_mode": "manual", "selected_ids": [1], "content": "latest record", "confirm": True},
    ).json()
    payload = client.get("/api/admin/user-ops/send-records").json()
    assert payload["items"][0]["record_id"] == executed["record_id"]
    assert payload["items"][0]["content_preview"] == "latest record"


def test_user_ops_send_record_detail_returns_task_results() -> None:
    client = make_client()
    executed = client.post(
        "/api/admin/user-ops/batch-send/execute",
        json={"selection_mode": "manual", "selected_ids": [1], "content": "detail", "confirm": True},
    ).json()
    detail = client.get(f"/api/admin/user-ops/send-records/{executed['record_id']}").json()
    assert detail["ok"] is True
    assert detail["record"]["record_id"] == executed["record_id"]
    assert detail["task_results"]
    assert detail["delivery_status_supported"] is False


def test_user_ops_missing_send_record_returns_404() -> None:
    response = make_client().get("/api/admin/user-ops/send-records/missing")
    assert response.status_code == 404
