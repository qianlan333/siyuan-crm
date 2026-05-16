from __future__ import annotations

from wecom_ability_service.domains.marketing_automation.router_dispatch_service import (
    _build_disabled_batch_result,
)


def test_disabled_batch_result_uses_unique_sorted_skip_entries():
    payload = _build_disabled_batch_result(
        {
            "batch": {"id": 7, "status": "pending"},
            "messages": [
                {"external_userid": "wm_b"},
                {"external_userid": "wm_a"},
                {"external_userid": "wm_b"},
                {"external_userid": ""},
                {"content": "missing external userid"},
            ],
            "paging": {"next_cursor": "cursor-1"},
        },
        scenario_key="signup_conversion_v1",
    )

    assert payload["scenario_key"] == "signup_conversion_v1"
    assert payload["candidate_count"] == 0
    assert payload["blocked_count"] == 0
    assert payload["skipped_count"] == 2
    assert payload["skipped_customers"] == [
        {"external_userid": "wm_a", "reason": "automation_disabled"},
        {"external_userid": "wm_b", "reason": "automation_disabled"},
    ]
    assert payload["paging"] == {"next_cursor": "cursor-1"}
