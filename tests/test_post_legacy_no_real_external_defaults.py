from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from tests.post_legacy_baseline import API_CONTRACT_CASES, assert_no_legacy_flags, baseline_env

ROOT = Path(__file__).resolve().parents[1]

GUARDED_EXTERNAL_CLIENT_ALLOWLIST = {
    Path("aicrm_next/admin_jobs/application.py"),
    Path("aicrm_next/admin_jobs/notification_settings.py"),
    Path("aicrm_next/channel_entry/wecom_adapter.py"),
    Path("aicrm_next/commerce/wechat_pay_client.py"),
    Path("aicrm_next/integration_gateway/wecom_jssdk_adapter.py"),
    Path("aicrm_next/integration_gateway/wecom_tag_live_gateway.py"),
    Path("aicrm_next/questionnaire/external_push.py"),
}


def test_post_legacy_representative_commands_do_not_execute_real_external_calls_by_default(monkeypatch) -> None:
    baseline_env(monkeypatch)
    client = TestClient(create_app())
    by_key = {case.key: case for case in API_CONTRACT_CASES}

    for key in (
        "wecom_tags_write",
        "wecom_tags_live_mutation_blocked",
        "cloud_campaigns_run_due_plan",
        "automation_jobs_run_due_preview",
        "customer_activation_webhook",
        "hxc_dashboard_refresh",
        "checkout_wechat_fake",
    ):
        case = by_key[key]
        response = client.request(case.method, case.path, json=case.json, content=case.content, params=case.params)
        assert response.status_code in case.expected_statuses
        if response.headers.get("content-type", "").startswith("application/json"):
            assert_no_legacy_flags(response.json())


def test_post_legacy_real_external_clients_are_explicitly_guarded() -> None:
    offenders: list[str] = []
    for path in (ROOT / "aicrm_next").rglob("*.py"):
        rel = path.relative_to(ROOT)
        text = path.read_text(encoding="utf-8")
        if not any(marker in text for marker in ("requests.", "urlopen(", "urllib.request")):
            continue
        if rel in GUARDED_EXTERNAL_CLIENT_ALLOWLIST:
            continue
        offenders.append(str(rel))

    assert offenders == []
