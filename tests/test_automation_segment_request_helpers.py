from __future__ import annotations

from flask import Flask

from wecom_ability_service.http.automation_conversion_segments import (
    _request_segment_broadcast_keys,
    _request_segment_broadcast_keyword,
    _segment_broadcast_payload,
)


def test_segment_broadcast_helpers_read_json_lists_and_keyword():
    app = Flask(__name__)

    with app.test_request_context(
        method="POST",
        json={
            "pool_keys": ["inactive_focus", " ", "active_focus"],
            "profile_keys": "core",
            "behavior_keys[]": ["clicked"],
            "keyword": "  张三  ",
        },
    ):
        payload = _segment_broadcast_payload()

        assert _request_segment_broadcast_keys("pool_keys", payload) == ["inactive_focus", "active_focus"]
        assert _request_segment_broadcast_keys("profile_keys", payload) == ["core"]
        assert _request_segment_broadcast_keys("behavior_keys", payload) == ["clicked"]
        assert _request_segment_broadcast_keyword(payload) == "张三"


def test_segment_broadcast_helpers_fallback_to_form_values():
    app = Flask(__name__)

    with app.test_request_context(
        method="POST",
        data={
            "pool_keys": ["inactive_normal", ""],
            "profile_keys[]": ["top"],
            "keyword": "  李四  ",
        },
    ):
        payload = _segment_broadcast_payload()

        assert payload == {}
        assert _request_segment_broadcast_keys("pool_keys", payload) == ["inactive_normal"]
        assert _request_segment_broadcast_keys("profile_keys", payload) == ["top"]
        assert _request_segment_broadcast_keyword(payload) == "李四"
