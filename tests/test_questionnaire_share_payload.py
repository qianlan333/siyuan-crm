from __future__ import annotations

from urllib.parse import unquote

from flask import Flask

from wecom_ability_service.http.questionnaire_support import _build_questionnaire_share_payload


def test_questionnaire_share_payload_builds_public_url_and_qr() -> None:
    app = Flask(__name__)

    with app.test_request_context("/", base_url="https://crm.example.test"):
        share = _build_questionnaire_share_payload(
            {
                "id": 21,
                "slug": "q-20260414135818-5d8fba",
                "title": "填写问卷激活黄小璨AI",
                "name": "黄小璨激活问卷",
            }
        )

    assert share["questionnaire_id"] == 21
    assert share["slug"] == "q-20260414135818-5d8fba"
    assert share["title"] == "填写问卷激活黄小璨AI"
    assert share["public_path"] == "/s/q-20260414135818-5d8fba"
    assert share["url"] == "https://crm.example.test/s/q-20260414135818-5d8fba"
    assert share["qr_data_url"].startswith("data:image/svg+xml;charset=UTF-8,")
    assert "%3Csvg" in share["qr_data_url"]
    assert 'xmlns="http://www.w3.org/2000/svg"' in unquote(share["qr_data_url"])
