from __future__ import annotations

from wecom_ability_service.domains.user_ops.page_service import (
    _index_manual_dnd_rows,
    _manual_dnd_reasons_for_identity,
    _normalize_filter_payload,
)


def test_manual_dnd_reason_lookup_uses_identity_indexes_and_dedupes_reasons():
    rows = [
        {
            "external_userid": "wm_001",
            "mobile": "",
            "source_type": "manual",
            "reason_code": "manual_set",
            "reason_text": "运营设置",
        },
        {
            "external_userid": "",
            "mobile": "13800138000",
            "source_type": "manual",
            "reason_code": "manual_set",
            "reason_text": "运营设置",
        },
        {
            "external_userid": "",
            "mobile": "13800138000",
            "source_type": "auto",
            "reason_code": "signed_paid_course",
            "reason_text": "已报名正价课",
        },
        {
            "external_userid": "wm_other",
            "mobile": "13900139000",
            "source_type": "manual",
            "reason_code": "manual_set",
            "reason_text": "无关客户",
        },
    ]
    rows_by_external, rows_by_mobile = _index_manual_dnd_rows(rows)

    reasons = _manual_dnd_reasons_for_identity(
        external_userid="wm_001",
        mobile="13800138000",
        rows_by_external=rows_by_external,
        rows_by_mobile=rows_by_mobile,
    )

    assert reasons == [
        {"source_type": "manual", "reason_code": "manual_set", "reason_text": "运营设置"},
        {"source_type": "auto", "reason_code": "signed_paid_course", "reason_text": "已报名正价课"},
    ]


def test_normalize_filter_payload_keeps_legacy_boolean_filter_aliases():
    assert _normalize_filter_payload({"is_wecom_added": "true"})["wecom_status"] == "added"
    assert _normalize_filter_payload({"is_wecom_added": "0"})["wecom_status"] == "not_added"
    assert _normalize_filter_payload({"is_mobile_bound": "yes"})["mobile_binding_status"] == "bound"
    assert _normalize_filter_payload({"is_mobile_bound": "false"})["mobile_binding_status"] == "unbound"


def test_normalize_filter_payload_prefers_current_status_filters_over_legacy_aliases():
    normalized = _normalize_filter_payload(
        {
            "wecom_status": "added",
            "is_wecom_added": "false",
            "mobile_binding_status": "bound",
            "is_mobile_bound": "0",
        }
    )

    assert normalized["wecom_status"] == "added"
    assert normalized["mobile_binding_status"] == "bound"
