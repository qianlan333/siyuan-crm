from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from tools import collect_server_readonly_evidence as collector


class _EvidenceHandler(BaseHTTPRequestHandler):
    seen_methods: list[str] = []
    database_mode = "postgres"
    include_fixture_marker = False
    route_owner = "ai_crm_next"
    app_header = "ai_crm_next"
    release_sha = "test-sha"

    def do_GET(self):  # noqa: N802
        self.seen_methods.append("GET")
        payload = {"ok": True}
        body = "ok"
        content_type = "text/plain"
        if self.path in {"/health", "/api/system/health"}:
            payload = {
                "ok": True,
                "database_mode": self.database_mode,
                "production_data_ready": True,
            }
            body = json.dumps(payload)
            content_type = "application/json"
        elif self.path.startswith("/api/customers"):
            payload = {"ok": True, "total": 1, "customers": [{"external_userid": "wm_001"}]}
            body = json.dumps(payload)
            content_type = "application/json"
        elif self.path.startswith("/api/admin/questionnaires"):
            payload = {"ok": True, "total": 1, "questionnaires": [{"slug": "prod-questionnaire"}]}
            body = json.dumps(payload)
            content_type = "application/json"
        elif self.include_fixture_marker and self.path == "/admin/customers":
            body = "local_contract customer"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("X-AICRM-Route-Owner", self.route_owner)
        self.send_header("X-AICRM-App", self.app_header)
        self.send_header("X-AICRM-Release-SHA", self.release_sha)
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_POST(self):  # noqa: N802
        self.seen_methods.append("POST")
        self.send_response(405)
        self.end_headers()

    def log_message(self, format, *args):  # noqa: A002
        return


def _server_url(handler_cls: type[_EvidenceHandler]):
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}"


def test_collect_server_readonly_evidence_uses_only_get_requests():
    _EvidenceHandler.seen_methods = []
    _EvidenceHandler.include_fixture_marker = False
    _EvidenceHandler.route_owner = "ai_crm_next"
    server, url = _server_url(_EvidenceHandler)
    try:
        result = collector.collect(url, timeout=2)
    finally:
        server.shutdown()

    assert result["ok"] is True
    assert result["post_requests_executed"] == 0
    assert set(_EvidenceHandler.seen_methods) == {"GET"}
    assert result["safe_to_enable_timers"] is False
    assert result["safe_to_enable_real_external_calls"] is False
    assert result["safe_to_remove_legacy_fallback"] is False
    assert result["evidence_classification"]["server_readonly_evidence"] is True
    assert result["evidence_classification"]["production_canary_evidence"] is False


def test_fixture_marker_with_postgres_database_is_blocker():
    _EvidenceHandler.seen_methods = []
    _EvidenceHandler.include_fixture_marker = True
    _EvidenceHandler.route_owner = "ai_crm_next"
    server, url = _server_url(_EvidenceHandler)
    try:
        result = collector.collect(url, timeout=2)
    finally:
        server.shutdown()

    assert result["ok"] is False
    assert any(blocker.startswith("fixture_marker_in_postgres_response:GET /admin/customers") for blocker in result["blockers"])


def test_unexpected_route_owner_is_blocker():
    _EvidenceHandler.seen_methods = []
    _EvidenceHandler.include_fixture_marker = False
    _EvidenceHandler.route_owner = "legacy_flask"
    server, url = _server_url(_EvidenceHandler)
    try:
        result = collector.collect(url, timeout=2)
    finally:
        server.shutdown()

    assert result["ok"] is False
    assert any("unexpected_route_owner" in blocker for blocker in result["blockers"])
    _EvidenceHandler.route_owner = "ai_crm_next"


def test_expected_sidebar_bind_mobile_owner_is_next():
    _EvidenceHandler.seen_methods = []
    _EvidenceHandler.include_fixture_marker = False
    _EvidenceHandler.route_owner = "ai_crm_next"
    server, url = _server_url(_EvidenceHandler)
    try:
        result = collector.collect(url, timeout=2)
    finally:
        server.shutdown()

    sidebar_probe = next(probe for probe in result["probes"] if probe["path"] == "/sidebar/bind-mobile")
    sidebar_blockers = [blocker for blocker in result["blockers"] if "/sidebar/bind-mobile" in blocker]
    assert sidebar_probe["runtime_owner"] == "next"
    assert not any("unexpected_route_owner" in blocker for blocker in sidebar_blockers)
    _EvidenceHandler.route_owner = "ai_crm_next"


def test_write_outputs_create_markdown_and_json(tmp_path: Path):
    result = {
        "ok": True,
        "blockers": [],
        "warnings": [],
        "base_url": "http://127.0.0.1:5001",
        "readonly": True,
        "post_requests_executed": 0,
        "database_mode": "postgres",
        "production_data_ready": True,
        "safe_to_enable_timers": False,
        "safe_to_enable_real_external_calls": False,
        "safe_to_remove_legacy_fallback": False,
        "evidence_classification": {
            "local_checker_evidence": False,
            "server_readonly_evidence": True,
            "production_canary_evidence": False,
            "note": "readonly",
        },
        "probes": [],
    }
    output_md = tmp_path / "evidence.md"
    output_json = tmp_path / "evidence.json"

    collector.write_outputs(result, str(output_md), str(output_json))

    assert "Server Readonly Evidence" in output_md.read_text(encoding="utf-8")
    assert json.loads(output_json.read_text(encoding="utf-8"))["readonly"] is True
