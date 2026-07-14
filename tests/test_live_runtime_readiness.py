from __future__ import annotations

import json
from pathlib import Path

from tools.check_live_runtime_readiness import run_check


SHA = "a" * 40
TOKEN = "secret-runtime-route-token"
ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    def __init__(self, status_code: int, payload: dict, *, release_sha: str = SHA) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = {"x-aicrm-release-sha": release_sha}

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def get(self, url: str, *, headers: dict[str, str], timeout: float) -> FakeResponse:
        self.calls.append({"url": url, "headers": dict(headers), "timeout": timeout})
        return self.responses.pop(0)


def _health() -> dict:
    return {
        "ok": True,
        "status": "ok",
        "service": "aicrm-next",
        "database_mode": "postgres",
        "production_data_ready": True,
        "legacy_runtime_enabled": False,
    }


def _readiness(*, release_sha: str = SHA) -> dict:
    return {
        "ok": True,
        "status": "ready",
        "http_status": 200,
        "failed_components": [],
        "warning_components": [],
        "components": {
            "database": {"status": "ok", "critical": True, "ping": True},
            "migration": {"status": "ok", "critical": True, "matches_head": True},
            "queues": {"status": "ok", "critical": True, "metrics": {}},
            "wecom": {"status": "ok", "critical": True, "conflict": False},
            "release": {"status": "ok", "critical": True, "release_sha": release_sha, "exact_sha": True},
            "runtime_units": {"status": "external_gate", "critical": False},
        },
        "pii_in_output": False,
        "secrets_in_output": False,
    }


def _route_map(*, web_sha: str = SHA, worker_sha: str = SHA) -> dict:
    return {
        "web_release_sha": web_sha,
        "worker_release_sha": worker_sha,
        "route_owner": "ai_crm_next",
        "app_name": "aicrm-next",
        "legacy_callback_fallback_enabled": False,
    }


def _session(*, readiness: dict | None = None, route_map: dict | None = None) -> FakeSession:
    return FakeSession(
        [
            FakeResponse(200, _health()),
            FakeResponse(200, readiness or _readiness()),
            FakeResponse(200, route_map or _route_map()),
        ]
    )


def test_live_readiness_requires_configuration_before_network_access() -> None:
    session = FakeSession([])

    missing_url = run_check(base_url="", expected_sha=SHA, env={"AICRM_RUNTIME_ROUTE_READ_TOKEN": TOKEN}, session=session)
    invalid_sha = run_check(base_url="https://crm.example.test", expected_sha="main", env={"AICRM_RUNTIME_ROUTE_READ_TOKEN": TOKEN}, session=session)
    missing_token = run_check(base_url="https://crm.example.test", expected_sha=SHA, env={}, session=session)

    assert missing_url["blocking_reasons"] == ["base_url_required"]
    assert invalid_sha["blocking_reasons"] == ["expected_exact_sha_required"]
    assert missing_token["blocking_reasons"] == ["runtime_route_read_token_required"]
    assert session.calls == []


def test_live_readiness_fails_closed_on_liveness_and_readiness_errors() -> None:
    liveness_session = FakeSession([FakeResponse(503, {"ok": False})])
    liveness = run_check(
        base_url="https://crm.example.test",
        expected_sha=SHA,
        env={"AICRM_RUNTIME_ROUTE_READ_TOKEN": TOKEN},
        session=liveness_session,
    )
    readiness_session = FakeSession(
        [
            FakeResponse(200, _health()),
            FakeResponse(503, {**_readiness(), "ok": False, "status": "not_ready", "http_status": 503}),
        ]
    )
    readiness = run_check(
        base_url="https://crm.example.test",
        expected_sha=SHA,
        env={"AICRM_RUNTIME_ROUTE_READ_TOKEN": TOKEN},
        session=readiness_session,
    )

    assert liveness["ok"] is False
    assert "liveness_http_status:503" in liveness["blocking_reasons"]
    assert readiness["ok"] is False
    assert "readiness_http_status:503" in readiness["blocking_reasons"]
    assert len(readiness_session.calls) == 2


def test_live_readiness_rejects_release_and_worker_drift() -> None:
    wrong_release = run_check(
        base_url="https://crm.example.test",
        expected_sha=SHA,
        env={"AICRM_RUNTIME_ROUTE_READ_TOKEN": TOKEN},
        session=_session(readiness=_readiness(release_sha="b" * 40)),
    )
    wrong_worker = run_check(
        base_url="https://crm.example.test",
        expected_sha=SHA,
        env={"AICRM_RUNTIME_ROUTE_READ_TOKEN": TOKEN},
        session=_session(route_map=_route_map(worker_sha="b" * 40)),
    )

    assert "readiness_release_sha_mismatch" in wrong_release["blocking_reasons"]
    assert "worker_release_sha_mismatch" in wrong_worker["blocking_reasons"]


def test_live_readiness_treats_route_map_unauthorized_as_failure_not_readiness() -> None:
    session = FakeSession(
        [
            FakeResponse(200, _health()),
            FakeResponse(200, _readiness()),
            FakeResponse(401, {"error": "unauthorized"}),
        ]
    )

    result = run_check(
        base_url="https://crm.example.test",
        expected_sha=SHA,
        env={"AICRM_RUNTIME_ROUTE_READ_TOKEN": TOKEN},
        session=session,
    )

    assert result["ok"] is False
    assert "runtime_route_map_http_status:401" in result["blocking_reasons"]


def test_live_readiness_success_proves_exact_web_worker_and_auth_contract() -> None:
    session = _session()

    result = run_check(
        base_url="https://crm.example.test/",
        expected_sha=SHA,
        env={"AICRM_RUNTIME_ROUTE_READ_TOKEN": TOKEN},
        session=session,
        timeout=3.0,
    )

    assert result["ok"] is True
    assert result["status"] == "ready"
    assert result["blocking_reasons"] == []
    assert result["evidence"]["web_release_sha"] == SHA
    assert result["evidence"]["worker_release_sha"] == SHA
    assert [call["url"] for call in session.calls] == [
        "https://crm.example.test/health",
        "https://crm.example.test/api/system/health",
        "https://crm.example.test/api/system/runtime-route-map",
    ]
    assert session.calls[0]["headers"] == {}
    assert session.calls[1]["headers"] == {}
    assert session.calls[2]["headers"] == {"Authorization": f"Bearer {TOKEN}"}
    assert all(call["timeout"] == 3.0 for call in session.calls)
    assert TOKEN not in json.dumps(result, ensure_ascii=False)


def test_live_readiness_rejects_release_header_drift() -> None:
    session = _session()
    session.responses[1].headers["x-aicrm-release-sha"] = "b" * 40

    result = run_check(
        base_url="https://crm.example.test",
        expected_sha=SHA,
        env={"AICRM_RUNTIME_ROUTE_READ_TOKEN": TOKEN},
        session=session,
    )

    assert result["ok"] is False
    assert "readiness_release_header_mismatch" in result["blocking_reasons"]


def test_obsolete_synthetic_production_diagnostics_are_physically_retired() -> None:
    assert not (ROOT / "tools/check_next_production_runtime_gaps.py").exists()
    assert not (ROOT / "tools/check_next_production_cutover_readiness.py").exists()

    source = (ROOT / "tools/check_live_runtime_readiness.py").read_text(encoding="utf-8")
    assert "AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE" not in source
    assert "127.0.0.1:1/aicrm_probe" not in source
    assert "status_code != 404" not in source
    assert "TestClient" not in source
