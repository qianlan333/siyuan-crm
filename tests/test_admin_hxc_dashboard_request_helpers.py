"""HXC admin request parsing helpers."""
from __future__ import annotations

from flask import Flask

from wecom_ability_service.http.admin_hxc_dashboard import (
    _int_field,
    _int_list_field,
    _json_body,
    _optional_int_field,
    _string_list_field,
)


def test_hxc_json_body_ignores_non_object_payloads():
    app = Flask(__name__)
    with app.test_request_context(json=["not", "a", "mapping"]):
        assert _json_body() == {}


def test_hxc_request_fields_coerce_safe_defaults():
    payload = {
        "priority": "bad",
        "miniprogram_library_id": "12",
        "external_userids": "ext1",
        "image_library_ids": ["1", "bad", 2, 3, 4],
    }

    assert _int_field(payload, "priority", default=100) == 100
    assert _optional_int_field(payload, "miniprogram_library_id") == 12
    assert _string_list_field(payload, "external_userids") == ["ext1"]
    assert _int_list_field(payload, "image_library_ids", limit=3) == [1, 2]
