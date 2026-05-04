from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from flask import abort, current_app, jsonify, request, send_from_directory

from ..db import init_db
from ..domains.archive.service import list_archived_messages_by_window
from .ops_runtime import build_ops_status_payload


def health():
    return jsonify({"ok": True, "service": "openclaw-wecom-ability-service"})


def _temporary_webhook_receipts_path() -> Path:
    configured = str(current_app.config.get("TEMP_WEBHOOK_RECEIPTS_PATH", "") or "").strip()
    return Path(configured or "/tmp/openclaw-temporary-webhook-receiver.jsonl")


def _read_temporary_webhook_receipts(*, limit: int = 20) -> list[dict]:
    path = _temporary_webhook_receipts_path()
    if not path.exists():
        return []
    items: list[dict] = []
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        text = line.strip()
        if not text:
            continue
        try:
            items.append(json.loads(text))
        except json.JSONDecodeError:
            continue
        if len(items) >= limit:
            break
    return items


def temporary_webhook_receiver():
    body_text = request.get_data(as_text=True) or ""
    receipt = {
        "received_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "method": request.method,
        "path": request.path,
        "remote_addr": request.remote_addr or "",
        "headers": {
            key.lower(): value
            for key, value in request.headers.items()
            if key.lower() in {"host", "content-type", "user-agent", "x-forwarded-for", "x-request-id"}
        },
        "query": request.args.to_dict(flat=True),
        "json": request.get_json(silent=True),
        "raw_body": body_text[:20000],
    }
    path = _temporary_webhook_receipts_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(receipt, ensure_ascii=False) + "\n")
    current_app.logger.info(
        "temporary webhook receipt stored path=%s content_type=%s body_length=%s",
        path,
        request.headers.get("Content-Type", ""),
        len(body_text),
    )
    return jsonify({"ok": True, "stored": True, "receipt": {"received_at": receipt["received_at"]}})


def list_temporary_webhook_receipts():
    try:
        limit = max(1, min(int(request.args.get("limit", "20") or "20"), 100))
    except ValueError:
        limit = 20
    items = _read_temporary_webhook_receipts(limit=limit)
    return jsonify({"ok": True, "count": len(items), "items": items})


def clear_temporary_webhook_receipts():
    path = _temporary_webhook_receipts_path()
    if path.exists():
        path.unlink()
    return jsonify({"ok": True, "cleared": True})


def serve_root_verification_file(filename: str):
    is_supported_verify_file = (
        (filename.startswith("WW_verify_") or filename.startswith("MP_verify_"))
        and filename.endswith(".txt")
    )
    if not is_supported_verify_file:
        abort(404)
    project_root = Path(current_app.root_path).parent
    return send_from_directory(project_root, filename, mimetype="text/plain")


def archive_messages():
    start_time = request.args.get("start_time", "").strip()
    end_time = request.args.get("end_time", "").strip()
    owner_userid = request.args.get("owner_userid", "").strip() or current_app.config["WECOM_DEFAULT_OWNER_USERID"]
    cursor = request.args.get("cursor", "").strip()

    if not start_time or not end_time or not owner_userid:
        return jsonify({"ok": False, "error": "start_time, end_time and owner_userid are required"}), 400

    result = list_archived_messages_by_window(start_time, end_time, owner_userid, cursor=cursor)
    return jsonify(result)


def api_init_db():
    init_db()
    return jsonify({"ok": True})


def ops_status():
    return jsonify(build_ops_status_payload())


def register_routes(bp):
    bp.route('/health', methods=['GET'])(health)
    bp.route('/api/tmp/webhook-receiver', methods=['POST'])(temporary_webhook_receiver)
    bp.route('/api/tmp/webhook-receiver/receipts', methods=['GET'])(list_temporary_webhook_receipts)
    bp.route('/api/tmp/webhook-receiver/receipts', methods=['DELETE'])(clear_temporary_webhook_receipts)
    bp.route('/<path:filename>', methods=['GET'])(serve_root_verification_file)
    bp.route('/archive/messages', methods=['GET'])(archive_messages)
    bp.route('/api/init-db', methods=['POST'])(api_init_db)
    bp.route('/api/ops/status', methods=['GET'])(ops_status)
