from __future__ import annotations

import pytest

from wecom_ability_service.domains.questionnaire import service as questionnaire_service


def _mobile_questionnaire() -> dict[str, object]:
    return {
        "questions": [
            {
                "id": 1,
                "type": "mobile",
                "title": "手机号",
                "required": True,
                "options": [],
            }
        ]
    }


def test_validate_questionnaire_answers_normalizes_mobile_without_runtime_patch():
    validated = questionnaire_service.validate_questionnaire_answers(
        _mobile_questionnaire(),
        {"1": "+86 138-0013-8000"},
    )

    assert validated[0]["text_value"] == "13800138000"


def test_validate_questionnaire_answers_rejects_invalid_mobile_without_runtime_patch():
    with pytest.raises(ValueError, match="mobile must be a valid mainland China mobile number"):
        questionnaire_service.validate_questionnaire_answers(
            _mobile_questionnaire(),
            {"1": "12345"},
        )
