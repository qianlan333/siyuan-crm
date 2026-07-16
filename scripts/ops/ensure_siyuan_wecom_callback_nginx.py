#!/usr/bin/env python3
from __future__ import annotations

import argparse
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

try:
    from scripts.script_runtime import print_json
    from scripts.ops.check_wecom_callback_ingress_cutover import analyze_nginx_config
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from script_runtime import print_json
    from ops.check_wecom_callback_ingress_cutover import analyze_nginx_config


DEFAULT_NGINX_CONFIG = "/etc/nginx/sites-enabled/siyuan-crm"
DEFAULT_ZONE_CONFIG = "/etc/nginx/conf.d/aicrm-wecom-callback-zones.conf"
DEFAULT_SERVER_NAME = "www.xinliushangye.com"
CALLBACK_ROUTES = ("/wecom/external-contact/callback", "/api/wecom/events")
BEGIN_MARKER = "# BEGIN AICRM WECOM CALLBACK INGRESS"
END_MARKER = "# END AICRM WECOM CALLBACK INGRESS"
ZONE_CONTENT = """# Managed by ensure_siyuan_wecom_callback_nginx.py
limit_req_zone $binary_remote_addr zone=aicrm_wecom_callback_req:10m rate=20r/s;
limit_conn_zone $binary_remote_addr zone=aicrm_wecom_callback_conn:10m;
"""


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
        if content[index] == "{":
            depth += 1
        elif content[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _server_blocks(content: str) -> list[tuple[int, int, int, int]]:
    blocks: list[tuple[int, int, int, int]] = []
    for match in re.finditer(r"(?m)^\s*server\s*\{", content):
        opening = content.find("{", match.start(), match.end())
        closing = _closing_brace(content, opening)
        if opening >= 0 and closing >= 0:
            blocks.append((match.start(), opening + 1, closing, closing + 1))
    return blocks


def _callback_block(route: str) -> str:
    return f"""    location = {route} {{
        client_max_body_size 1m;
        limit_req zone=aicrm_wecom_callback_req burst=20 nodelay;
        limit_conn aicrm_wecom_callback_conn 20;
        limit_req_status 429;
        limit_conn_status 429;

        proxy_pass http://127.0.0.1:5002;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 1s;
        proxy_send_timeout 3s;
        proxy_read_timeout 3s;
        proxy_request_buffering on;
        proxy_buffering off;
    }}"""


def managed_callback_section() -> str:
    blocks = "\n\n".join(_callback_block(route) for route in CALLBACK_ROUTES)
    return f"{BEGIN_MARKER}\n{blocks}\n    {END_MARKER}\n\n"


def render_nginx_config(content: str, *, server_name: str = DEFAULT_SERVER_NAME) -> str:
    if (BEGIN_MARKER in content) != (END_MARKER in content):
        raise ValueError("managed callback marker is incomplete")
    if BEGIN_MARKER in content:
        start = content.index(BEGIN_MARKER)
        end = content.index(END_MARKER, start) + len(END_MARKER)
        current = content[start:end]
        expected = managed_callback_section().strip()
        if current.strip() != expected:
            raise ValueError("managed callback section differs from the supported shape")
        return content

    effective = _strip_comments_preserving_offsets(content)
    candidates: list[tuple[int, int, int, int]] = []
    for block in _server_blocks(effective):
        body = effective[block[1] : block[2]]
        names = re.findall(r"(?m)^\s*server_name\s+([^;]+);", body)
        has_name = any(server_name in value.split() for value in names)
        has_tls = bool(re.search(r"(?m)^\s*listen\s+[^;]*\b443\b[^;]*;", body))
        if has_name and has_tls:
            candidates.append(block)
    if len(candidates) != 1:
        raise ValueError("expected exactly one TLS server block for the Siyuan domain")

    block = candidates[0]
    body = effective[block[1] : block[2]]
    for route in CALLBACK_ROUTES:
        if re.search(rf"(?m)^\s*location\s+=\s+{re.escape(route)}\s*\{{", body):
            raise ValueError(f"unmanaged callback route already exists: {route}")
    root_matches = list(re.finditer(r"(?m)^\s*location\s+/\s*\{", body))
    if len(root_matches) != 1:
        raise ValueError("expected exactly one root location in the TLS server block")
    insertion = block[1] + root_matches[0].start()
    return content[:insertion] + managed_callback_section() + content[insertion:]


def _safe_existing_nginx_path(path: Path) -> Path:
    if not path.is_absolute() or not str(path).startswith("/etc/nginx/"):
        raise ValueError("nginx config must be under /etc/nginx")
    target = path.resolve(strict=True)
    metadata = target.stat()
    if not str(target).startswith("/etc/nginx/") or not stat.S_ISREG(metadata.st_mode):
        raise ValueError("nginx config target must be a regular file under /etc/nginx")
    return target


def _safe_zone_path(path: Path) -> Path:
    if not path.is_absolute() or path.parent != Path("/etc/nginx/conf.d") or path.suffix != ".conf":
        raise ValueError("zone config must be a .conf file directly under /etc/nginx/conf.d")
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise ValueError("zone config must be a regular file")
    return path


def _atomic_write(path: Path, content: str, *, mode: int, uid: int, gid: int) -> None:
    temporary_path = ""
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{path.name}.", dir=path.parent, delete=False) as handle:
            temporary_path = handle.name
            os.fchmod(handle.fileno(), mode)
            os.fchown(handle.fileno(), uid, gid)
            handle.write(content.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = ""
    finally:
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)


def _run(*command: str) -> bool:
    return subprocess.run(command, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def apply_nginx_config(*, nginx_config: Path, zone_config: Path, updated_content: str) -> dict[str, Any]:
    if os.geteuid() != 0:
        return {"ok": False, "error_code": "execute_requires_root"}
    try:
        target = _safe_existing_nginx_path(nginx_config)
        zone_target = _safe_zone_path(zone_config)
    except (OSError, ValueError):
        return {"ok": False, "error_code": "nginx_config_path_rejected"}

    metadata = target.stat()
    old_content = target.read_text(encoding="utf-8")
    zone_existed = zone_target.exists()
    old_zone_content = zone_target.read_text(encoding="utf-8") if zone_existed else ""
    zone_metadata = zone_target.stat() if zone_existed else None
    backup_dir = Path("/etc/nginx/backups")
    backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    backup = backup_dir / f"{target.name}.siyuan-wecom-callback-{timestamp}"
    shutil.copy2(target, backup)
    os.chmod(backup, 0o600)
    try:
        _atomic_write(
            zone_target,
            ZONE_CONTENT,
            mode=stat.S_IMODE(zone_metadata.st_mode) if zone_metadata else 0o644,
            uid=zone_metadata.st_uid if zone_metadata else metadata.st_uid,
            gid=zone_metadata.st_gid if zone_metadata else metadata.st_gid,
        )
        _atomic_write(
            target,
            updated_content,
            mode=stat.S_IMODE(metadata.st_mode),
            uid=metadata.st_uid,
            gid=metadata.st_gid,
        )
        if not _run("/usr/sbin/nginx", "-t") or not _run("/usr/bin/systemctl", "reload", "nginx"):
            raise RuntimeError("nginx validation or reload failed")
        state = analyze_nginx_config(str(nginx_config))
        if not all(
            state.get(key)
            for key in (
                "callback_routes_present",
                "callback_routes_proxy_to_5002",
                "short_callback_timeouts_configured",
                "callback_backpressure_configured",
            )
        ) or state.get("emergency_quick_ack_enabled"):
            raise RuntimeError("nginx callback postcondition failed")
    except (OSError, RuntimeError):
        _atomic_write(
            target,
            old_content,
            mode=stat.S_IMODE(metadata.st_mode),
            uid=metadata.st_uid,
            gid=metadata.st_gid,
        )
        if zone_existed and zone_metadata is not None:
            _atomic_write(
                zone_target,
                old_zone_content,
                mode=stat.S_IMODE(zone_metadata.st_mode),
                uid=zone_metadata.st_uid,
                gid=zone_metadata.st_gid,
            )
        else:
            zone_target.unlink(missing_ok=True)
        rollback_ok = _run("/usr/sbin/nginx", "-t") and _run("/usr/bin/systemctl", "reload", "nginx")
        return {"ok": False, "error_code": "nginx_apply_failed", "rollback_ok": rollback_ok}
    return {"ok": True, "error_code": "", "backup_path": str(backup), "rollback_ok": None}


def run(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Route Siyuan WeCom callbacks to the isolated durable inbox ingress.")
    parser.add_argument("--execute", action="store_true", default=False)
    parser.add_argument("--nginx-config", default=DEFAULT_NGINX_CONFIG)
    parser.add_argument("--zone-config", default=DEFAULT_ZONE_CONFIG)
    parser.add_argument("--server-name", default=DEFAULT_SERVER_NAME)
    args = parser.parse_args(argv)
    path = Path(args.nginx_config)
    try:
        content = path.read_text(encoding="utf-8")
        updated = render_nginx_config(content, server_name=str(args.server_name))
    except (OSError, UnicodeError, ValueError) as exc:
        return {"ok": False, "error_code": type(exc).__name__, "mutation_required": None}
    zone_path = Path(args.zone_config)
    try:
        zone_matches = zone_path.read_text(encoding="utf-8") == ZONE_CONTENT
    except (OSError, UnicodeError):
        zone_matches = False
    mutation_required = updated != content or not zone_matches
    if not args.execute:
        return {"ok": True, "error_code": "", "mutation_required": mutation_required}
    applied = apply_nginx_config(
        nginx_config=path,
        zone_config=Path(args.zone_config),
        updated_content=updated,
    )
    return {**applied, "mutation_required": mutation_required}


def main(argv: list[str] | None = None) -> int:
    payload = run(argv)
    print_json(payload, sort_keys=True)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
