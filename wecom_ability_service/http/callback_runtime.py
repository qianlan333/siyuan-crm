from __future__ import annotations

from xml.etree import ElementTree as ET

from flask import Response, jsonify, request

from ..archive_sdk import WeComArchiveError
from ..domains.callbacks.service import log_external_contact_event
from ..wecom_callback import (
    WeComCallbackError,
    build_encrypted_reply,
    decrypt_message,
    get_callback_config,
    parse_callback_xml,
    verify_signature,
)
from ..wecom_client import WeComClientError
from .common import callback_logger
from .sync_support import _build_external_contact_event_key


def _callback_config_or_error() -> tuple[dict[str, str], tuple[object, int] | None]:
    config = get_callback_config()
    token = config["token"]
    aes_key = config["aes_key"]
    corp_id = config["corp_id"]
    if not token or not aes_key or not corp_id:
        return config, (jsonify({"ok": False, "error": "callback config is not complete"}), 500)
    return config, None


def _callback_request_args() -> tuple[str, str, str]:
    return (
        request.args.get("msg_signature", ""),
        request.args.get("timestamp", ""),
        request.args.get("nonce", ""),
    )


def _handle_callback_verify(*, token: str, aes_key: str, corp_id: str, msg_signature: str, timestamp: str, nonce: str):
    echostr = request.args.get("echostr", "")
    verify_signature(token, timestamp, nonce, echostr, msg_signature)
    return Response(decrypt_message(echostr, aes_key, corp_id), mimetype="text/plain")


def _decrypt_callback_event(*, token: str, aes_key: str, corp_id: str, msg_signature: str, timestamp: str, nonce: str) -> dict[str, str]:
    xml_text = request.data.decode("utf-8")
    envelope = parse_callback_xml(xml_text)
    encrypted = envelope.get("Encrypt", "")
    verify_signature(token, timestamp, nonce, encrypted, msg_signature)
    plain_xml = decrypt_message(encrypted, aes_key, corp_id)
    event_data = parse_callback_xml(plain_xml)
    event_data["_plain_xml"] = plain_xml
    return event_data


def _log_and_dispatch_external_contact_event(
    routes_compat,
    *,
    corp_id: str,
    event_data: dict[str, str],
    plain_xml: str,
) -> dict[str, object]:
    event_type = (event_data.get("Event") or "").strip()
    change_type = (event_data.get("ChangeType") or "").strip()
    external_userid = (event_data.get("ExternalUserID") or "").strip()
    user_id = (event_data.get("UserID") or "").strip()
    event_time = int((event_data.get("CreateTime") or "0").strip() or 0)
    event_key = _build_external_contact_event_key(corp_id, event_data)

    logged = log_external_contact_event(
        corp_id=corp_id,
        event_type=event_type,
        change_type=change_type,
        external_userid=external_userid,
        user_id=user_id,
        event_time=event_time,
        event_key=event_key,
        payload_xml=plain_xml,
        payload_json=event_data,
    )
    callback_logger.info(
        "external contact event received event=%s change_type=%s external_userid=%s user_id=%s duplicate=%s",
        event_type.lower(),
        change_type.lower(),
        external_userid,
        user_id,
        logged.get("is_duplicate", False),
    )

    if not (logged.get("is_duplicate") and logged.get("process_status") == "success"):
        routes_compat._dispatch_background_task(
            "external_contact_event",
            routes_compat._process_external_contact_event,
            int(logged["id"]),
        )
    return logged


def handle_external_contact_callback_request():
    from .. import routes as routes_compat

    config, error_response = _callback_config_or_error()
    if error_response is not None:
        return error_response
    token = config["token"]
    aes_key = config["aes_key"]
    corp_id = config["corp_id"]
    msg_signature, timestamp, nonce = _callback_request_args()

    try:
        if request.method == "GET":
            callback_logger.info("external contact callback verify success timestamp=%s nonce=%s", timestamp, nonce)
            return _handle_callback_verify(
                token=token,
                aes_key=aes_key,
                corp_id=corp_id,
                msg_signature=msg_signature,
                timestamp=timestamp,
                nonce=nonce,
            )

        event_data = _decrypt_callback_event(
            token=token,
            aes_key=aes_key,
            corp_id=corp_id,
            msg_signature=msg_signature,
            timestamp=timestamp,
            nonce=nonce,
        )
        plain_xml = event_data.pop("_plain_xml", "")
        _log_and_dispatch_external_contact_event(
            routes_compat,
            corp_id=corp_id,
            event_data=event_data,
            plain_xml=plain_xml,
        )

        reply_xml = build_encrypted_reply("success", token, aes_key, corp_id, nonce=nonce)
        return Response(reply_xml, mimetype="application/xml")
    except (WeComCallbackError, WeComClientError, ET.ParseError, ValueError) as exc:
        callback_logger.exception("external contact callback handling failed")
        return jsonify({"ok": False, "error": str(exc)}), 400


def handle_wecom_event_request():
    from .. import routes as routes_compat

    config, error_response = _callback_config_or_error()
    if error_response is not None:
        return error_response
    token = config["token"]
    aes_key = config["aes_key"]
    corp_id = config["corp_id"]
    msg_signature, timestamp, nonce = _callback_request_args()

    try:
        if request.method == "GET":
            callback_logger.info("callback verify success timestamp=%s nonce=%s", timestamp, nonce)
            return _handle_callback_verify(
                token=token,
                aes_key=aes_key,
                corp_id=corp_id,
                msg_signature=msg_signature,
                timestamp=timestamp,
                nonce=nonce,
            )

        event_data = _decrypt_callback_event(
            token=token,
            aes_key=aes_key,
            corp_id=corp_id,
            msg_signature=msg_signature,
            timestamp=timestamp,
            nonce=nonce,
        )
        plain_xml = event_data.pop("_plain_xml", "")
        event_name = (event_data.get("Event") or "").lower()
        change_type = (event_data.get("ChangeType") or "").lower()
        callback_logger.info(
            "callback event received event=%s change_type=%s",
            event_name,
            change_type,
        )

        if event_name == "msgaudit_notify":
            routes_compat._dispatch_background_task(
                "msgaudit_notify",
                routes_compat._trigger_incremental_archive_sync,
            )
        elif event_name == "change_external_contact":
            _log_and_dispatch_external_contact_event(
                routes_compat,
                corp_id=corp_id,
                event_data=event_data,
                plain_xml=plain_xml,
            )
        elif event_name == "change_external_chat" or change_type in {"create", "update", "dismiss"}:
            routes_compat._dispatch_background_task(
                "change_external_chat",
                routes_compat._handle_group_chat_change,
                event_data,
            )

        reply_xml = build_encrypted_reply("success", token, aes_key, corp_id, nonce=nonce)
        return Response(reply_xml, mimetype="application/xml")
    except (WeComCallbackError, WeComClientError, WeComArchiveError, ET.ParseError) as exc:
        callback_logger.exception("callback handling failed")
        return jsonify({"ok": False, "error": str(exc)}), 400
