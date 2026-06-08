from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from tools import check_questionnaire_h5_oauth_readiness as checker


def test_questionnaire_h5_oauth_readiness_checker_passes_locally():
    result = checker.run_check()

    assert result["ok"] is True
    assert result["post_requests_executed"] == 0
    assert result["real_oauth_executed"] is False
    assert result["safe_to_enable_real_oauth"] is False
    assert result["evidence_classification"]["local_checker_evidence"] is True
    assert result["evidence_classification"]["production_canary_evidence"] is False


def test_shape_checker_accepts_items_and_questionnaires_datetime_strings():
    probes = {
        "GET /api/admin/questionnaires?limit=1": {
            "json": {
                "ok": True,
                "items": [
                    {
                        "slug": "prod-questionnaire",
                        "title": "Production questionnaire",
                        "created_at": "2026-05-22T00:00:00Z",
                        "updated_at": "2026-05-22T00:01:00Z",
                    }
                ],
                "questionnaires": [
                    {
                        "slug": "prod-questionnaire",
                        "title": "Production questionnaire",
                        "created_at": "2026-05-22T00:00:00Z",
                        "updated_at": "2026-05-22T00:01:00Z",
                    }
                ],
            }
        },
        "GET /api/h5/questionnaires/hxc-activation-v1": {
            "json": {"ok": True, "questionnaire": {"slug": "prod-questionnaire"}, "questions": []}
        },
        "GET /api/h5/questionnaires/hxc-activation-v1/result/sub_fixture_001": {
            "json": {"ok": True, "result": {}, "result_message": "ok"}
        },
    }

    blockers, warnings = checker._add_shape_blockers(probes)

    assert blockers == []
    assert warnings == []


def test_production_fixture_slug_success_is_blocker():
    probes = {
        "GET /api/admin/questionnaires?limit=1": {
            "status_code": 200,
            "json": {
                "ok": True,
                "questionnaires": [
                    {
                        "slug": "hxc-activation-v1",
                        "title": "fixture",
                        "created_at": "2026-05-01T00:00:00Z",
                        "updated_at": "2026-05-01T00:00:00Z",
                    }
                ],
            },
            "body_preview": "",
        }
    }

    blockers, warnings = checker._production_fixture_blockers(probes, local_probe_database=False)

    assert warnings == []
    assert "production_questionnaire_fixture_slug_success:GET /api/admin/questionnaires?limit=1" in blockers


def test_oauth_checker_requires_explicit_fake_or_guarded_source_status():
    probes = {
        "GET /api/h5/wechat/oauth/start?slug=hxc-activation-v1": {
            "status_code": 200,
            "json": {"ok": True, "redirect_url": "/api/h5/wechat/oauth/callback?state=x"},
        },
        "GET /api/h5/wechat/oauth/callback?state=hxc-activation-v1": {
            "status_code": 200,
            "json": {"ok": True, "source_status": "real", "redirect_url": "/s/x"},
        },
    }

    blockers = checker._oauth_blockers(probes, production=True)

    assert "oauth_missing_source_status:GET /api/h5/wechat/oauth/start?slug=hxc-activation-v1" in blockers
    assert any(item.endswith(":real") for item in blockers)


def test_oauth_checker_flags_localhost_redirect_in_production():
    probes = {
        "GET /api/h5/wechat/oauth/start?slug=hxc-activation-v1": {
            "status_code": 200,
            "json": {
                "ok": True,
                "source_status": "fake",
                "redirect_url": "http://localhost/api/h5/wechat/oauth/callback",
            },
        },
        "GET /api/h5/wechat/oauth/callback?state=hxc-activation-v1": {
            "status_code": 200,
            "json": {"ok": True, "source_status": "fake", "redirect_url": "/s/hxc-activation-v1"},
        },
    }

    blockers = checker._oauth_blockers(probes, production=True)

    assert "oauth_redirect_uri_localhost:GET /api/h5/wechat/oauth/start?slug=hxc-activation-v1" in blockers


class _ServerHandler(BaseHTTPRequestHandler):
    seen_methods: list[str] = []
    include_fixture = False
    oauth_localhost = False

    def do_GET(self):  # noqa: N802
        self.seen_methods.append("GET")
        payload = {"ok": True}
        body = "ok"
        content_type = "text/plain"
        if self.path.startswith("/api/admin/questionnaires"):
            payload = {
                "ok": True,
                "questionnaires": [
                    {
                        "slug": "prod-questionnaire",
                        "title": "Production questionnaire",
                        "created_at": "2026-05-22T00:00:00Z",
                        "updated_at": "2026-05-22T00:01:00Z",
                    }
                ],
                "source_status": "production_postgres",
            }
            if self.include_fixture:
                payload["questionnaires"][0]["slug"] = "hxc-activation-v1"
            body = json.dumps(payload)
            content_type = "application/json"
        elif self.path.startswith("/api/h5/wechat/oauth/start"):
            payload = {
                "ok": True,
                "source_status": "fake",
                "redirect_url": "http://localhost/callback" if self.oauth_localhost else "/api/h5/wechat/oauth/callback?state=hxc",
            }
            body = json.dumps(payload)
            content_type = "application/json"
        elif self.path.startswith("/api/h5/wechat/oauth/callback"):
            payload = {"ok": True, "source_status": "fake", "redirect_url": "/s/hxc"}
            body = json.dumps(payload)
            content_type = "application/json"
        elif self.path.startswith("/api/h5/questionnaires") and "/result/" in self.path:
            payload = {"ok": True, "result": {"submission_id": "server-sub"}, "result_message": "ok"}
            body = json.dumps(payload)
            content_type = "application/json"
        elif self.path.startswith("/api/h5/questionnaires"):
            payload = {"ok": True, "questionnaire": {"slug": "prod-questionnaire"}, "questions": []}
            body = json.dumps(payload)
            content_type = "application/json"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("X-AICRM-Route-Owner", "ai_crm_next")
        self.send_header("X-AICRM-App", "ai_crm_next")
        self.send_header("X-AICRM-Release-SHA", "test-sha")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_POST(self):  # noqa: N802
        self.seen_methods.append("POST")
        self.send_response(405)
        self.end_headers()

    def log_message(self, format, *args):  # noqa: A002
        return


def _server_url(handler_cls: type[_ServerHandler]):
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}"


def test_server_evidence_uses_only_get_requests():
    _ServerHandler.seen_methods = []
    _ServerHandler.include_fixture = False
    _ServerHandler.oauth_localhost = False
    server, url = _server_url(_ServerHandler)
    try:
        result = checker.collect_server_evidence(url, timeout=2)
    finally:
        server.shutdown()

    assert result["ok"] is True
    assert set(_ServerHandler.seen_methods) == {"GET"}
    assert result["post_requests_executed"] == 0
    assert result["evidence_classification"]["server_readonly_evidence"] is True


def test_server_evidence_flags_fixture_slug_and_localhost_redirect():
    _ServerHandler.seen_methods = []
    _ServerHandler.include_fixture = True
    _ServerHandler.oauth_localhost = True
    server, url = _server_url(_ServerHandler)
    try:
        result = checker.collect_server_evidence(url, timeout=2)
    finally:
        server.shutdown()

    assert result["ok"] is False
    assert any("production_questionnaire_fixture_slug_success" in blocker for blocker in result["blockers"])
    assert any("oauth_redirect_uri_localhost" in blocker for blocker in result["blockers"])


def test_write_outputs_create_markdown_and_json(tmp_path: Path):
    result = checker.run_check()
    output_md = tmp_path / "questionnaire.md"
    output_json = tmp_path / "questionnaire.json"

    checker.write_outputs(result, str(output_md), str(output_json))

    assert "Questionnaire H5 / OAuth Readiness" in output_md.read_text(encoding="utf-8")
    assert json.loads(output_json.read_text(encoding="utf-8"))["safe_to_enable_real_oauth"] is False
