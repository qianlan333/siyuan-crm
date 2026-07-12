#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from scripts.script_runtime import print_json
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from script_runtime import print_json


DEFAULT_SERVER_NAME = "www.youcangogogo.com"
DEFAULT_NGINX_CONFIG = "/etc/nginx/sites-enabled/youcangogogo.conf"
DEFAULT_LOCAL_HEALTH_URL = "http://127.0.0.1:5001/health"
DEFAULT_PUBLIC_HEALTH_URL = "https://www.youcangogogo.com/health"
APPROVED_LEGACY_ENDPOINT = "127.0.0.1:5000"
EXPECTED_WEB_ENDPOINT = "127.0.0.1:5001"
CALLBACK_ROUTES = ("/wecom/external-contact/callback", "/api/wecom/events")
_SHA_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
_SERVER_HEAD = re.compile(r"(?m)^\s*server\s*\{")
_UPSTREAM_HEAD = re.compile(r"(?m)^\s*upstream\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\{")
_ROOT_LOCATION_HEAD = re.compile(r"(?m)^\s*location\s+(?:=\s*)?/\s*\{")
_UPSTREAM_SERVER = re.compile(r"(?m)^\s*server\s+(?P<endpoint>[^\s;]+)(?:\s+[^;]*)?;")


def _strip_comments_preserving_offsets(content: str) -> str:
    rendered: list[str] = []
    for line in content.splitlines(keepends=True):
        comment_index = line.find("#")
        if comment_index < 0:
            rendered.append(line)
            continue
        ending = "\n" if line.endswith("\n") else ""
        body_length = len(line) - len(ending)
        rendered.append(line[:comment_index] + (" " * (body_length - comment_index)) + ending)
    return "".join(rendered)


def _closing_brace(content: str, opening_brace: int) -> int:
    depth = 0
    for index in range(opening_brace, len(content)):
        char = content[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _block_spans(content: str, pattern: re.Pattern[str]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for match in pattern.finditer(content):
        opening_brace = content.find("{", match.start(), match.end())
        closing_brace = _closing_brace(content, opening_brace)
        if opening_brace < 0 or closing_brace < 0:
            continue
        blocks.append(
            {
                "match": match,
                "start": match.start(),
                "body_start": opening_brace + 1,
                "body_end": closing_brace,
                "end": closing_brace + 1,
            }
        )
    return blocks


def _server_names(body: str) -> set[str]:
    names: set[str] = set()
    for match in re.finditer(r"(?m)^\s*server_name\s+(?P<names>[^;]+);", body):
        names.update(token.strip() for token in match.group("names").split() if token.strip())
    return names


def _is_tls_server(body: str) -> bool:
    return bool(re.search(r"(?m)^\s*listen\s+[^;]*\b443\b[^;]*;", body))


def _root_proxy(content: str, server_block: dict[str, Any]) -> dict[str, Any] | None:
    server_body_start = int(server_block["body_start"])
    server_body_end = int(server_block["body_end"])
    server_body = content[server_body_start:server_body_end]
    locations = _block_spans(server_body, _ROOT_LOCATION_HEAD)
    if len(locations) != 1:
        return None
    location = locations[0]
    location_body_start = server_body_start + int(location["body_start"])
    location_body_end = server_body_start + int(location["body_end"])
    location_body = content[location_body_start:location_body_end]
    proxy_matches = list(re.finditer(r"(?m)^\s*proxy_pass\s+(?P<target>[^;\s]+)\s*;", location_body))
    if len(proxy_matches) != 1:
        return None
    proxy = proxy_matches[0]
    return {
        "target": proxy.group("target"),
        "target_start": location_body_start + proxy.start("target"),
        "target_end": location_body_start + proxy.end("target"),
    }


def _callback_digest(content: str) -> str:
    effective = _strip_comments_preserving_offsets(content)
    blocks: list[str] = []
    for route in CALLBACK_ROUTES:
        pattern = re.compile(rf"(?m)^\s*location\s+=\s+{re.escape(route)}\s*\{{")
        spans = _block_spans(effective, pattern)
        if len(spans) != 1:
            blocks.append(f"{route}:missing-or-ambiguous")
            continue
        span = spans[0]
        blocks.append(content[int(span["start"]):int(span["end"])])
    return hashlib.sha256("\n".join(blocks).encode("utf-8")).hexdigest()


def _callback_uses_upstream(content: str, upstream_name: str) -> bool:
    for route in CALLBACK_ROUTES:
        pattern = re.compile(rf"(?m)^\s*location\s+=\s+{re.escape(route)}\s*\{{")
        spans = _block_spans(content, pattern)
        if len(spans) != 1:
            continue
        span = spans[0]
        body = content[int(span["body_start"]):int(span["body_end"])]
        if re.search(rf"(?m)^\s*proxy_pass\s+http://{re.escape(upstream_name)}(?:[/;\s])", body):
            return True
    return False


def _base_report(*, server_block_count: int, error_code: str) -> dict[str, Any]:
    return {
        "server_block_count": server_block_count,
        "selected_tls_server": False,
        "root_proxy_target": "",
        "root_upstream_name": "",
        "root_upstream_endpoints": [],
        "current_web_endpoint": "",
        "expected_web_endpoint": EXPECTED_WEB_ENDPOINT,
        "mutation_required": True,
        "mutation_supported": False,
        "error_code": error_code,
        "_server_name": "",
        "_replacement_start": -1,
        "_replacement_end": -1,
        "_replacement_value": "",
    }


def analyze_nginx_config(content: str, *, server_name: str) -> dict[str, Any]:
    effective = _strip_comments_preserving_offsets(content)
    domain_servers: list[dict[str, Any]] = []
    for block in _block_spans(effective, _SERVER_HEAD):
        body = effective[int(block["body_start"]):int(block["body_end"])]
        if server_name in _server_names(body):
            domain_servers.append({**block, "tls": _is_tls_server(body), "root_proxy": _root_proxy(effective, block)})
    if not domain_servers:
        return _base_report(server_block_count=0, error_code="domain_server_not_found")
    routed = [block for block in domain_servers if block["root_proxy"] is not None]
    tls_routed = [block for block in routed if block["tls"]]
    selected_pool = tls_routed or routed
    if not selected_pool:
        return _base_report(server_block_count=len(domain_servers), error_code="domain_root_location_not_found")
    if len(selected_pool) != 1:
        return _base_report(server_block_count=len(domain_servers), error_code="domain_root_route_ambiguous")

    selected = selected_pool[0]
    proxy = dict(selected["root_proxy"])
    target = str(proxy["target"])
    report = _base_report(server_block_count=len(domain_servers), error_code="")
    report.update(
        {
            "selected_tls_server": bool(selected["tls"]),
            "root_proxy_target": target,
            "_server_name": server_name,
        }
    )
    direct_match = re.fullmatch(r"http://(?P<endpoint>127\.0\.0\.1:\d+)", target)
    if direct_match:
        endpoint = direct_match.group("endpoint")
        report["root_upstream_endpoints"] = [endpoint]
        report["current_web_endpoint"] = endpoint
        report["mutation_required"] = endpoint != EXPECTED_WEB_ENDPOINT
        report["mutation_supported"] = endpoint in {APPROVED_LEGACY_ENDPOINT, EXPECTED_WEB_ENDPOINT}
        report["error_code"] = (
            "" if report["mutation_supported"] else "web_upstream_not_approved_legacy_endpoint"
        )
        if endpoint == APPROVED_LEGACY_ENDPOINT:
            report["_replacement_start"] = int(proxy["target_start"])
            report["_replacement_end"] = int(proxy["target_end"])
            report["_replacement_value"] = f"http://{EXPECTED_WEB_ENDPOINT}"
        return report

    named_match = re.fullmatch(r"http://(?P<name>[A-Za-z_][A-Za-z0-9_]*)", target)
    if not named_match:
        report["error_code"] = "root_proxy_target_not_supported"
        return report
    upstream_name = named_match.group("name")
    report["root_upstream_name"] = upstream_name
    if _callback_uses_upstream(effective, upstream_name):
        report["error_code"] = "web_upstream_shared_with_callback"
        return report
    upstream_blocks = [
        block
        for block in _block_spans(effective, _UPSTREAM_HEAD)
        if block["match"].group("name") == upstream_name
    ]
    if len(upstream_blocks) != 1:
        report["error_code"] = "root_upstream_not_found_or_ambiguous"
        return report
    upstream = upstream_blocks[0]
    upstream_body_start = int(upstream["body_start"])
    upstream_body = effective[upstream_body_start:int(upstream["body_end"])]
    endpoints = list(_UPSTREAM_SERVER.finditer(upstream_body))
    report["root_upstream_endpoints"] = [match.group("endpoint") for match in endpoints]
    if len(endpoints) != 1:
        report["error_code"] = "web_upstream_not_singleton"
        return report
    endpoint_match = endpoints[0]
    endpoint = endpoint_match.group("endpoint")
    report["current_web_endpoint"] = endpoint
    report["mutation_required"] = endpoint != EXPECTED_WEB_ENDPOINT
    report["mutation_supported"] = endpoint in {APPROVED_LEGACY_ENDPOINT, EXPECTED_WEB_ENDPOINT}
    report["error_code"] = "" if report["mutation_supported"] else "web_upstream_not_approved_legacy_endpoint"
    if endpoint == APPROVED_LEGACY_ENDPOINT:
        report["_replacement_start"] = upstream_body_start + endpoint_match.start("endpoint")
        report["_replacement_end"] = upstream_body_start + endpoint_match.end("endpoint")
        report["_replacement_value"] = EXPECTED_WEB_ENDPOINT
    return report


def render_updated_config(content: str, report: dict[str, Any]) -> str:
    if not report.get("mutation_supported"):
        raise ValueError("nginx web upstream mutation is not supported")
    if not report.get("mutation_required"):
        return content
    start = int(report.get("_replacement_start", -1))
    end = int(report.get("_replacement_end", -1))
    replacement = str(report.get("_replacement_value") or "")
    if start < 0 or end <= start or not replacement:
        raise ValueError("nginx web upstream mutation is not supported")
    updated = content[:start] + replacement + content[end:]
    if _callback_digest(updated) != _callback_digest(content):
        raise ValueError("nginx callback routes changed during web upstream render")
    verified = analyze_nginx_config(updated, server_name=str(report.get("_server_name") or DEFAULT_SERVER_NAME))
    if verified.get("current_web_endpoint") != EXPECTED_WEB_ENDPOINT or verified.get("mutation_required"):
        raise ValueError("rendered nginx web upstream did not converge")
    return updated


def _public_topology(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if not key.startswith("_")}


def _probe_release(url: str, *, timeout_seconds: float) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "aicrm-production-release-route/1.0"}, method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return {
                "checked": True,
                "status_code": int(response.status),
                "release_sha": str(response.headers.get("x-aicrm-release-sha") or "").strip(),
                "error_code": "",
            }
    except HTTPError as exc:
        return {
            "checked": True,
            "status_code": int(exc.code),
            "release_sha": str(exc.headers.get("x-aicrm-release-sha") or "").strip(),
            "error_code": "http_error",
        }
    except (OSError, URLError):
        return {"checked": False, "status_code": None, "release_sha": "", "error_code": "connection_error"}


def _safe_nginx_target(path: Path) -> Path:
    if not path.is_absolute() or not str(path).startswith("/etc/nginx/"):
        raise ValueError("nginx config must be under /etc/nginx")
    target = path.resolve(strict=True)
    if not str(target).startswith("/etc/nginx/"):
        raise ValueError("nginx config target must be under /etc/nginx")
    metadata = target.stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("nginx config target must be a regular file")
    return target


def _atomic_write(path: Path, content: str, *, metadata: os.stat_result) -> None:
    encoded = content.encode("utf-8")
    temporary_path = ""
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{path.name}.", dir=path.parent, delete=False) as handle:
            temporary_path = handle.name
            os.fchmod(handle.fileno(), stat.S_IMODE(metadata.st_mode))
            os.fchown(handle.fileno(), metadata.st_uid, metadata.st_gid)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = ""
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary_path:
            try:
                os.unlink(temporary_path)
            except OSError:
                pass


def _nginx_command(*args: str) -> bool:
    result = subprocess.run(
        [*args],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return result.returncode == 0


def _nginx_config_sections(dump: str) -> list[tuple[Path, str]]:
    marker = re.compile(r"(?m)^# configuration file (?P<path>/etc/nginx/[^:\r\n]+):\s*$")
    matches = list(marker.finditer(dump))
    sections: list[tuple[Path, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(dump)
        sections.append((Path(match.group("path")), dump[start:end]))
    return sections


def _discover_nginx_config(*, server_name: str) -> tuple[Path | None, str, dict[str, Any]]:
    try:
        result = subprocess.run(
            ["/usr/sbin/nginx", "-T"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError:
        return None, "", {
            "config_source": "discovery",
            "config_path": "",
            "discovered_config_count": 0,
            "error_code": "nginx_effective_config_unavailable",
        }
    if result.returncode != 0:
        return None, "", {
            "config_source": "discovery",
            "config_path": "",
            "discovered_config_count": 0,
            "error_code": "nginx_effective_config_unavailable",
        }
    sections = _nginx_config_sections(result.stdout + "\n" + result.stderr)
    domain_candidates: list[tuple[Path, dict[str, Any]]] = []
    for path, content in sections:
        report = analyze_nginx_config(content, server_name=server_name)
        if int(report.get("server_block_count") or 0) > 0:
            domain_candidates.append((path, report))
    routed_tls_candidates = [
        item
        for item in domain_candidates
        if item[1].get("selected_tls_server") and item[1].get("root_proxy_target")
    ]
    selected_pool = routed_tls_candidates or domain_candidates
    if len(selected_pool) != 1:
        return None, "", {
            "config_source": "discovery",
            "config_path": "",
            "discovered_config_count": len(domain_candidates),
            "error_code": (
                "nginx_domain_config_not_found"
                if not domain_candidates
                else "nginx_domain_config_ambiguous"
            ),
        }
    path = selected_pool[0][0]
    try:
        target = path.resolve(strict=True)
        content = target.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None, "", {
            "config_source": "discovery",
            "config_path": "",
            "discovered_config_count": len(domain_candidates),
            "error_code": "nginx_discovered_config_unreadable",
        }
    return path, content, {
        "config_source": "discovery",
        "config_path": str(path),
        "discovered_config_count": len(domain_candidates),
        "error_code": "",
    }


def _load_or_discover_nginx_config(
    *,
    configured_path: Path,
    server_name: str,
    allow_discovery: bool,
) -> tuple[Path | None, str, dict[str, Any], dict[str, Any]]:
    try:
        target = configured_path.resolve(strict=True)
        content = target.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        content = ""
    if content:
        topology = analyze_nginx_config(content, server_name=server_name)
        if int(topology.get("server_block_count") or 0) > 0:
            return configured_path, content, topology, {
                "config_source": "configured",
                "config_path": str(configured_path),
                "discovered_config_count": 0,
                "error_code": "",
            }
    if not allow_discovery:
        return None, "", {}, {
            "config_source": "configured",
            "config_path": str(configured_path),
            "discovered_config_count": 0,
            "error_code": "nginx_config_unreadable_or_domain_missing",
        }
    discovered_path, discovered_content, discovery = _discover_nginx_config(server_name=server_name)
    if discovered_path is None:
        return None, "", {}, discovery
    topology = analyze_nginx_config(discovered_content, server_name=server_name)
    return discovered_path, discovered_content, topology, discovery


def _restore_nginx(*, backup: Path, target: Path, metadata: os.stat_result) -> bool:
    try:
        _atomic_write(target, backup.read_text(encoding="utf-8"), metadata=metadata)
    except (OSError, UnicodeError):
        return False
    return _nginx_command("/usr/sbin/nginx", "-t") and _nginx_command(
        "/usr/bin/systemctl", "reload", "nginx"
    )


def _apply_nginx_route(
    *,
    configured_path: Path,
    updated_content: str,
    expected_sha: str,
    public_health_url: str,
    timeout_seconds: float,
    poll_attempts: int,
) -> dict[str, Any]:
    if os.geteuid() != 0:
        return {"ok": False, "error_code": "execute_requires_root", "backup_path": "", "rollback_ok": None}
    try:
        target = _safe_nginx_target(configured_path)
    except (OSError, ValueError):
        return {"ok": False, "error_code": "nginx_config_path_rejected", "backup_path": "", "rollback_ok": None}
    metadata = target.stat()
    backup_dir = Path("/etc/nginx/backups")
    try:
        backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        backup_metadata = backup_dir.lstat()
        if stat.S_ISLNK(backup_metadata.st_mode) or not stat.S_ISDIR(backup_metadata.st_mode):
            raise ValueError("nginx backup directory is unsafe")
        os.chmod(backup_dir, 0o700)
    except (OSError, ValueError):
        return {"ok": False, "error_code": "nginx_backup_directory_rejected", "backup_path": "", "rollback_ok": None}
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    backup = backup_dir / f"{target.name}.aicrm-web-upstream-{timestamp}"
    shutil.copy2(target, backup, follow_symlinks=True)
    os.chmod(backup, 0o600)
    try:
        _atomic_write(target, updated_content, metadata=metadata)
        if not _nginx_command("/usr/sbin/nginx", "-t"):
            raise RuntimeError("nginx_test_failed")
        if not _nginx_command("/usr/bin/systemctl", "reload", "nginx"):
            raise RuntimeError("nginx_reload_failed")
        public_probe: dict[str, Any] = {}
        for _ in range(max(1, poll_attempts)):
            public_probe = _probe_release(public_health_url, timeout_seconds=timeout_seconds)
            if public_probe.get("release_sha") == expected_sha and public_probe.get("status_code") == 200:
                return {
                    "ok": True,
                    "error_code": "",
                    "backup_path": str(backup),
                    "rollback_ok": None,
                    "public_probe": public_probe,
                }
            time.sleep(0.5)
        raise RuntimeError("public_release_sha_mismatch")
    except (OSError, RuntimeError):
        rollback_ok = _restore_nginx(backup=backup, target=target, metadata=metadata)
        return {
            "ok": False,
            "error_code": "nginx_route_apply_failed",
            "backup_path": str(backup),
            "rollback_ok": rollback_ok,
        }


def run(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Require the production public route to serve the exact verified release SHA.")
    parser.add_argument("--execute", action="store_true", default=False)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--server-name", default=DEFAULT_SERVER_NAME)
    parser.add_argument("--nginx-config", default=DEFAULT_NGINX_CONFIG)
    parser.add_argument("--local-health-url", default=DEFAULT_LOCAL_HEALTH_URL)
    parser.add_argument("--public-health-url", default=DEFAULT_PUBLIC_HEALTH_URL)
    parser.add_argument("--probe-timeout", type=float, default=5.0)
    parser.add_argument("--poll-attempts", type=int, default=20)
    args = parser.parse_args(argv)
    expected_sha = str(args.expected_sha or "").strip().lower()
    if not _SHA_PATTERN.fullmatch(expected_sha):
        return {"ok": False, "error_code": "expected_sha_invalid"}
    configured_path = Path(str(args.nginx_config))
    local_probe = _probe_release(str(args.local_health_url), timeout_seconds=float(args.probe_timeout))
    public_probe = _probe_release(str(args.public_health_url), timeout_seconds=float(args.probe_timeout))
    payload: dict[str, Any] = {
        "ok": False,
        "error_code": "",
        "expected_sha": expected_sha,
        "local_probe": local_probe,
        "public_probe": public_probe,
        "nginx_config": {
            "config_source": "not_checked",
            "config_path": "",
            "discovered_config_count": 0,
            "error_code": "",
        },
        "nginx_topology": {},
        "mutation_executed": False,
        "backup_path": "",
        "rollback_ok": None,
    }
    if local_probe.get("status_code") != 200 or local_probe.get("release_sha") != expected_sha:
        payload["error_code"] = "local_release_sha_mismatch"
        return payload
    if public_probe.get("status_code") == 200 and public_probe.get("release_sha") == expected_sha:
        payload["ok"] = True
        return payload
    selected_path, content, topology, config_state = _load_or_discover_nginx_config(
        configured_path=configured_path,
        server_name=str(args.server_name),
        allow_discovery=bool(args.execute),
    )
    payload["nginx_config"] = config_state
    payload["nginx_topology"] = _public_topology(topology)
    if selected_path is None:
        payload["error_code"] = str(config_state.get("error_code") or "nginx_config_unavailable")
        return payload
    if not args.execute:
        payload["error_code"] = "public_release_sha_mismatch"
        return payload
    if not topology.get("mutation_supported") or not topology.get("mutation_required"):
        payload["error_code"] = str(topology.get("error_code") or "public_route_change_not_supported")
        return payload
    try:
        updated = render_updated_config(content, topology)
    except ValueError:
        payload["error_code"] = "nginx_route_render_failed"
        return payload
    applied = _apply_nginx_route(
        configured_path=selected_path,
        updated_content=updated,
        expected_sha=expected_sha,
        public_health_url=str(args.public_health_url),
        timeout_seconds=float(args.probe_timeout),
        poll_attempts=int(args.poll_attempts),
    )
    payload["mutation_executed"] = True
    payload["backup_path"] = str(applied.get("backup_path") or "")
    payload["rollback_ok"] = applied.get("rollback_ok")
    payload["error_code"] = str(applied.get("error_code") or "")
    if applied.get("public_probe"):
        payload["public_probe"] = dict(applied["public_probe"])
    payload["ok"] = bool(applied.get("ok"))
    return payload


def main(argv: list[str] | None = None) -> int:
    try:
        payload = run(argv)
    except Exception as exc:
        payload = {"ok": False, "error_code": f"unexpected_{type(exc).__name__}"}
    print_json(payload, sort_keys=True)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
