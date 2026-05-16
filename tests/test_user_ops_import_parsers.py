from __future__ import annotations

import pytest

from wecom_ability_service.domains.user_ops.user_ops_import_service import (
    ImportRuntime,
    _parse_activation_status_from_text,
)


def _fake_import_runtime() -> ImportRuntime:
    def normalize_mobile(value: str) -> str:
        normalized = str(value or "").strip()
        if len(normalized) != 11 or not normalized.isdigit():
            raise ValueError("mobile is invalid")
        return normalized

    return ImportRuntime(
        db_bool=bool,
        normalize_mobile=normalize_mobile,
        current_operator_resolver=lambda: "tester",
        normalize_lead_pool_activation_state=lambda value, **_: str(value or "").strip(),
        apply_activation_source_to_existing_member=lambda **_: {},
        upsert_user_ops_lead_pool_member=lambda **_: {},
    )


def test_activation_status_parser_accepts_optional_remark_column():
    payload = _parse_activation_status_from_text(
        "手机号,状态,备注\n13800138020,已激活,黄小灿回访确认",
        runtime=_fake_import_runtime(),
    )

    assert payload["total_rows"] == 1
    assert payload["invalid_rows"] == []
    assert payload["rows"] == [
        {
            "mobile": "13800138020",
            "activation_status": "activated",
            "activation_remark": "黄小灿回访确认",
        }
    ]


def test_activation_status_parser_rejects_unbounded_extra_columns():
    payload = _parse_activation_status_from_text(
        "13800138020,已激活,备注,多余列",
        runtime=_fake_import_runtime(),
    )

    assert payload["rows"] == []
    assert payload["invalid_rows"] == [
        "13800138020,已激活,备注,多余列 -> activation_status rows must contain mobile, activation_status and optional remark"
    ]


@pytest.mark.parametrize(
    ("raw_value", "expected_status"),
    [("已激活", "activated"), ("激活", "activated"), ("未激活", "not_activated")],
)
def test_activation_status_parser_keeps_existing_status_aliases(raw_value: str, expected_status: str):
    payload = _parse_activation_status_from_text(
        f"13800138020,{raw_value}",
        runtime=_fake_import_runtime(),
    )

    assert payload["rows"][0]["activation_status"] == expected_status
