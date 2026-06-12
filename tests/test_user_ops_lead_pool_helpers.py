from __future__ import annotations

from aicrm_next.ops_enrollment.dto import BatchSendRequest
from aicrm_next.ops_enrollment.user_ops import build_overview_cards, resolve_batch_targets


def test_user_ops_next_overview_cards_count_current_segments():
    rows = [
        {"is_added_wecom": True, "is_mobile_bound": True, "activation_bucket": "activated"},
        {"is_added_wecom": False, "is_mobile_bound": False, "activation_bucket": "not_activated"},
    ]

    cards = {item["key"]: item["value"] for item in build_overview_cards(rows)}

    assert cards["lead_pool_total_count"] == 2
    assert cards["wecom_added_count"] == 1
    assert cards["mobile_unbound_count"] == 1
    assert cards["huangxiaocan_activated_count"] == 1


def test_user_ops_next_batch_target_resolution_keeps_skip_reasons():
    rows = [
        {
            "id": 1,
            "external_userid": "wx_ext_001",
            "owner_userid": "owner_001",
            "owner_display_name": "Owner",
            "customer_name": "张小蓝",
            "mobile": "13800138000",
            "do_not_disturb": False,
        },
        {
            "id": 2,
            "external_userid": "",
            "owner_userid": "owner_001",
            "owner_display_name": "Owner",
            "customer_name": "无外部联系人",
            "mobile": "13800138001",
            "do_not_disturb": False,
        },
    ]

    payload = resolve_batch_targets(rows, BatchSendRequest(selection_mode="all_filtered", content="hello"))

    assert payload["eligible_count"] == 1
    assert payload["skipped_by_reason"] == {"missing_external_userid": 1}
    assert payload["owner_buckets"][0]["owner_userid"] == "owner_001"
