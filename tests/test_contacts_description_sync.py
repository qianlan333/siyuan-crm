from __future__ import annotations

from wecom_ability_service.domains.contacts import service


def _contact_detail(description: str) -> dict[str, object]:
    return {
        "external_contact": {"external_userid": "wm_ext_desc_001", "name": "Customer"},
        "follow_user": [
            {
                "userid": "sales_01",
                "remark": "",
                "description": description,
                "tags": [],
            }
        ],
    }


def test_plan_contact_description_fix_updates_empty_and_legacy_descriptions() -> None:
    empty_plan = service.plan_contact_description_fix(_contact_detail(""), owner_userid="sales_01")
    legacy_plan = service.plan_contact_description_fix(
        _contact_detail("external_userid: wm_ext_desc_001"),
        owner_userid="sales_01",
    )
    custom_plan = service.plan_contact_description_fix(_contact_detail("manual note"), owner_userid="sales_01")

    assert empty_plan["should_update"] is True
    assert empty_plan["update_payload"] == {
        "userid": "sales_01",
        "external_userid": "wm_ext_desc_001",
        "description": "wm_ext_desc_001",
    }
    assert empty_plan["normalized"]["description"] == "wm_ext_desc_001"
    assert legacy_plan["should_update"] is True
    assert legacy_plan["normalized"]["description"] == "wm_ext_desc_001"
    assert custom_plan["should_update"] is False
    assert custom_plan["normalized"]["description"] == "manual note"


def test_sync_contact_detail_with_description_fix_calls_wecom_remark(monkeypatch) -> None:
    captured: list[dict[str, object] | None] = []

    class FakeClient:
        def update_contact_description(self, payload: dict[str, object]) -> dict[str, object]:
            captured.append(payload)
            return {"errcode": 0, "errmsg": "ok"}

    monkeypatch.setattr(service.repo, "get_contact_row_by_external_userid", lambda external_userid: None)

    normalized, updated = service.sync_contact_detail_with_description_fix(
        FakeClient(),
        _contact_detail(""),
        owner_userid="sales_01",
        default_owner_userid="fallback_owner",
        tolerate_update_error=False,
        log_stage="test",
    )

    assert updated is True
    assert captured == [
        {
            "userid": "sales_01",
            "external_userid": "wm_ext_desc_001",
            "description": "wm_ext_desc_001",
        }
    ]
    assert normalized["description"] == "wm_ext_desc_001"
