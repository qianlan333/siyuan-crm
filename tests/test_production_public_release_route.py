from __future__ import annotations

from pathlib import Path

from scripts.ops import ensure_production_public_release_route as release_route
from scripts.ops.ensure_production_public_release_route import analyze_nginx_config, render_updated_config


EXPECTED_SHA = "1" * 40
OLD_SHA = "2" * 40


def _config(web_endpoint: str, *, direct: bool = False, extra_web_server: str = "") -> str:
    root_target = f"http://{web_endpoint}" if direct else "http://aicrm_web"
    upstream = "" if direct else f"""
upstream aicrm_web {{
    server {web_endpoint};
    {extra_web_server}
    keepalive 32;
}}
"""
    return f"""
{upstream}
upstream aicrm_wecom_ingress {{
    server 127.0.0.1:5002;
}}

server {{
    listen 80;
    server_name www.youcangogogo.com;
    return 301 https://$host$request_uri;
}}

server {{
    listen 443 ssl;
    server_name www.youcangogogo.com;

    location / {{
        proxy_pass {root_target};
    }}

    location = /wecom/external-contact/callback {{
        proxy_pass http://aicrm_wecom_ingress;
    }}

    location = /api/wecom/events {{
        proxy_pass http://aicrm_wecom_ingress;
    }}
}}
"""


def test_named_legacy_web_upstream_has_one_safe_5001_replacement() -> None:
    source = _config("127.0.0.1:5000")

    report = analyze_nginx_config(source, server_name="www.youcangogogo.com")
    updated = render_updated_config(source, report)

    assert report["server_block_count"] == 2
    assert report["selected_tls_server"] is True
    assert report["root_proxy_target"] == "http://aicrm_web"
    assert report["root_upstream_endpoints"] == ["127.0.0.1:5000"]
    assert report["mutation_required"] is True
    assert report["mutation_supported"] is True
    assert updated.count("server 127.0.0.1:5001;") == 1
    assert "server 127.0.0.1:5000;" not in updated
    assert updated.count("server 127.0.0.1:5002;") == 1
    assert updated.count("proxy_pass http://aicrm_wecom_ingress;") == 2


def test_direct_legacy_web_proxy_has_one_safe_5001_replacement() -> None:
    source = _config("127.0.0.1:5000", direct=True)

    report = analyze_nginx_config(source, server_name="www.youcangogogo.com")
    updated = render_updated_config(source, report)

    assert report["root_proxy_target"] == "http://127.0.0.1:5000"
    assert report["root_upstream_endpoints"] == ["127.0.0.1:5000"]
    assert report["mutation_supported"] is True
    assert "proxy_pass http://127.0.0.1:5001;" in updated
    assert "proxy_pass http://127.0.0.1:5000;" not in updated


def test_current_5001_route_is_idempotent_and_needs_no_rewrite() -> None:
    source = _config("127.0.0.1:5001")

    report = analyze_nginx_config(source, server_name="www.youcangogogo.com")

    assert report["root_upstream_endpoints"] == ["127.0.0.1:5001"]
    assert report["mutation_required"] is False
    assert report["mutation_supported"] is True
    assert render_updated_config(source, report) == source


def test_multiple_or_non_loopback_upstreams_fail_closed_without_rendering() -> None:
    multiple = _config("127.0.0.1:5000", extra_web_server="server 127.0.0.1:5010;")
    non_loopback = _config("10.0.0.12:5000")

    multiple_report = analyze_nginx_config(multiple, server_name="www.youcangogogo.com")
    non_loopback_report = analyze_nginx_config(non_loopback, server_name="www.youcangogogo.com")

    assert multiple_report["mutation_required"] is True
    assert multiple_report["mutation_supported"] is False
    assert multiple_report["error_code"] == "web_upstream_not_singleton"
    assert non_loopback_report["mutation_required"] is True
    assert non_loopback_report["mutation_supported"] is False
    assert non_loopback_report["error_code"] == "web_upstream_not_approved_legacy_endpoint"
    for source, report in ((multiple, multiple_report), (non_loopback, non_loopback_report)):
        try:
            render_updated_config(source, report)
        except ValueError as exc:
            assert str(exc) == "nginx web upstream mutation is not supported"
        else:  # pragma: no cover - assertion helper
            raise AssertionError("unsupported nginx topology must not be rendered")


def test_web_upstream_shared_with_callback_fails_closed() -> None:
    source = _config("127.0.0.1:5000").replace(
        "proxy_pass http://aicrm_wecom_ingress;",
        "proxy_pass http://aicrm_web;",
        1,
    )

    report = analyze_nginx_config(source, server_name="www.youcangogogo.com")

    assert report["mutation_supported"] is False
    assert report["error_code"] == "web_upstream_shared_with_callback"


def test_missing_domain_or_root_route_fails_closed() -> None:
    missing_domain = _config("127.0.0.1:5000").replace("www.youcangogogo.com", "other.example.com")
    missing_root = _config("127.0.0.1:5000").replace("location / {", "location /admin {")

    domain_report = analyze_nginx_config(missing_domain, server_name="www.youcangogogo.com")
    root_report = analyze_nginx_config(missing_root, server_name="www.youcangogogo.com")

    assert domain_report["mutation_supported"] is False
    assert domain_report["error_code"] == "domain_server_not_found"
    assert root_report["mutation_supported"] is False
    assert root_report["error_code"] == "domain_root_location_not_found"


def test_run_requires_local_exact_sha_before_any_route_mutation(monkeypatch, tmp_path: Path) -> None:
    config = tmp_path / "nginx.conf"
    config.write_text(_config("127.0.0.1:5000"), encoding="utf-8")
    monkeypatch.setattr(
        release_route,
        "_probe_release",
        lambda url, **_: {
            "checked": True,
            "status_code": 200,
            "release_sha": OLD_SHA,
            "error_code": "",
        },
    )
    monkeypatch.setattr(
        release_route,
        "_apply_nginx_route",
        lambda **_: (_ for _ in ()).throw(AssertionError("mutation must not run")),
    )

    payload = release_route.run(
        [
            "--execute",
            "--expected-sha",
            EXPECTED_SHA,
            "--nginx-config",
            str(config),
        ]
    )

    assert payload["ok"] is False
    assert payload["error_code"] == "local_release_sha_mismatch"
    assert payload["mutation_executed"] is False


def test_run_applies_supported_route_and_requires_public_exact_sha(monkeypatch, tmp_path: Path) -> None:
    config = tmp_path / "nginx.conf"
    source = _config("127.0.0.1:5000")
    config.write_text(source, encoding="utf-8")

    def probe(url: str, **_: object) -> dict[str, object]:
        return {
            "checked": True,
            "status_code": 200,
            "release_sha": EXPECTED_SHA if "127.0.0.1" in url else OLD_SHA,
            "error_code": "",
        }

    captured: dict[str, object] = {}

    def apply(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "ok": True,
            "error_code": "",
            "backup_path": "/etc/nginx/backups/safe-backup",
            "rollback_ok": None,
            "public_probe": {
                "checked": True,
                "status_code": 200,
                "release_sha": EXPECTED_SHA,
                "error_code": "",
            },
        }

    monkeypatch.setattr(release_route, "_probe_release", probe)
    monkeypatch.setattr(release_route, "_apply_nginx_route", apply)

    payload = release_route.run(
        [
            "--execute",
            "--expected-sha",
            EXPECTED_SHA,
            "--nginx-config",
            str(config),
        ]
    )

    assert payload["ok"] is True
    assert payload["mutation_executed"] is True
    assert payload["public_probe"]["release_sha"] == EXPECTED_SHA
    updated = str(captured["updated_content"])
    assert "server 127.0.0.1:5001;" in updated
    assert "server 127.0.0.1:5000;" not in updated
    assert updated.count("proxy_pass http://aicrm_wecom_ingress;") == 2
    assert config.read_text(encoding="utf-8") == source


def test_run_fails_closed_when_public_mismatches_but_nginx_already_targets_5001(monkeypatch, tmp_path: Path) -> None:
    config = tmp_path / "nginx.conf"
    config.write_text(_config("127.0.0.1:5001"), encoding="utf-8")

    def probe(url: str, **_: object) -> dict[str, object]:
        return {
            "checked": True,
            "status_code": 200,
            "release_sha": EXPECTED_SHA if "127.0.0.1" in url else OLD_SHA,
            "error_code": "",
        }

    monkeypatch.setattr(release_route, "_probe_release", probe)
    monkeypatch.setattr(
        release_route,
        "_apply_nginx_route",
        lambda **_: (_ for _ in ()).throw(AssertionError("mutation must not run")),
    )

    payload = release_route.run(
        [
            "--execute",
            "--expected-sha",
            EXPECTED_SHA,
            "--nginx-config",
            str(config),
        ]
    )

    assert payload["ok"] is False
    assert payload["error_code"] == "public_route_change_not_supported"
    assert payload["mutation_executed"] is False


def test_effective_nginx_dump_sections_keep_only_absolute_nginx_paths() -> None:
    dump = """
nginx: configuration file /etc/nginx/nginx.conf test is successful
# configuration file /etc/nginx/nginx.conf:
events {}
# configuration file /etc/nginx/sites-enabled/production.conf:
server { listen 443 ssl; }
# configuration file relative.conf:
ignored
"""

    sections = release_route._nginx_config_sections(dump)

    assert [str(path) for path, _ in sections] == [
        "/etc/nginx/nginx.conf",
        "/etc/nginx/sites-enabled/production.conf",
    ]
    assert "events {}" in sections[0][1]
    assert "listen 443 ssl" in sections[1][1]


def test_run_discovers_effective_domain_config_when_documented_path_is_missing(monkeypatch, tmp_path: Path) -> None:
    configured = tmp_path / "documented-missing.conf"
    discovered = tmp_path / "actual-production.conf"
    source = _config("127.0.0.1:5000")
    discovered.write_text(source, encoding="utf-8")

    def probe(url: str, **_: object) -> dict[str, object]:
        return {
            "checked": True,
            "status_code": 200,
            "release_sha": EXPECTED_SHA if "127.0.0.1" in url else OLD_SHA,
            "error_code": "",
        }

    monkeypatch.setattr(release_route, "_probe_release", probe)
    monkeypatch.setattr(
        release_route,
        "_discover_nginx_config",
        lambda **_: (
            discovered,
            source,
            {
                "config_source": "discovery",
                "config_path": str(discovered),
                "discovered_config_count": 1,
                "error_code": "",
            },
        ),
    )
    captured: dict[str, object] = {}

    def apply(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "ok": True,
            "error_code": "",
            "backup_path": "/etc/nginx/backups/safe-backup",
            "rollback_ok": None,
            "public_probe": {
                "checked": True,
                "status_code": 200,
                "release_sha": EXPECTED_SHA,
                "error_code": "",
            },
        }

    monkeypatch.setattr(release_route, "_apply_nginx_route", apply)

    payload = release_route.run(
        [
            "--execute",
            "--expected-sha",
            EXPECTED_SHA,
            "--nginx-config",
            str(configured),
        ]
    )

    assert payload["ok"] is True
    assert payload["nginx_config"]["config_source"] == "discovery"
    assert payload["nginx_config"]["discovered_config_count"] == 1
    assert captured["configured_path"] == discovered
