from __future__ import annotations

import pytest

from aicrm_next.automation_engine.member_actions import AutomationMemberActionInputError, normalize_identity


def test_automation_identity_accepts_external_contact_or_phone() -> None:
    assert normalize_identity(external_contact_id=" wm_shared ", phone="") == {
        "external_contact_id": "wm_shared",
        "phone": "",
    }
    assert normalize_identity(external_contact_id="", phone=" 13800138000 ") == {
        "external_contact_id": "",
        "phone": "13800138000",
    }


def test_automation_identity_requires_one_identifier() -> None:
    with pytest.raises(AutomationMemberActionInputError, match="external_contact_id or phone"):
        normalize_identity(external_contact_id="", phone="")
