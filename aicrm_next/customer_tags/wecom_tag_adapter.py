from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from typing import Any


Json = dict[str, Any]
ADAPTER_MODE = "fake_stub"
ERROR_LIVE_CALL_NOT_ENABLED = "live_call_not_enabled"

DETERMINISTIC_TAGS: list[Json] = [
    {"tag_id": "tag_contract_001", "tag_name": "Phase5B Fake A", "group_id": "group_contract", "group_name": "Phase5B Fake"},
    {"tag_id": "tag_contract_002", "tag_name": "Phase5B Fake B", "group_id": "group_contract", "group_name": "Phase5B Fake"},
    {"tag_id": "tag_contract_003", "tag_name": "Phase5B Fake C", "group_id": "group_contract", "group_name": "Phase5B Fake"},
]


@dataclass(frozen=True)
class IdempotencyRecord:
    request_hash: str
    response: Json


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_hash(payload: Json) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_tag_ids(tag_ids: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in tag_ids or []:
        tag_id = str(raw or "").strip()
        if not tag_id or tag_id in seen:
            continue
        seen.add(tag_id)
        normalized.append(tag_id)
    return normalized


def _redact_external_userid(external_userid: str) -> str:
    value = str(external_userid or "").strip()
    if not value:
        return ""
    if len(value) <= 8:
        return "<redacted>"
    return f"{value[:4]}...{value[-4:]}"


def _side_effect_safety() -> Json:
    return {
        "live_call_executed": False,
        "mark_tag_executed": False,
        "unmark_tag_executed": False,
        "outbound_send_executed": False,
        "token_used": False,
        "network_call_executed": False,
        "production_behavior_changed": False,
        "db_write_executed": False,
        "external_userid_write_executed": False,
    }


def _base_response() -> Json:
    return {
        "adapter_mode": ADAPTER_MODE,
        "live_call_executed": False,
        "mark_tag_executed": False,
        "unmark_tag_executed": False,
        "outbound_send_executed": False,
        "token_used": False,
        "network_call_executed": False,
        "production_behavior_changed": False,
        "production_tag_write_executed": False,
        "production_success_claimed": False,
        "side_effect_safety": _side_effect_safety(),
        "timestamp": _timestamp(),
    }


class FakeStubWeComTagAdapter:
    def __init__(self, tags: list[Json] | None = None) -> None:
        self._tags = deepcopy(tags or DETERMINISTIC_TAGS)
        self._idempotency: dict[str, IdempotencyRecord] = {}

    def reset_idempotency(self) -> None:
        self._idempotency.clear()

    def list_wecom_tags(self) -> Json:
        groups: dict[str, Json] = {}
        for tag in self._tags:
            group_id = str(tag.get("group_id") or "")
            group_name = str(tag.get("group_name") or "")
            groups.setdefault(group_id, {"group_id": group_id, "group_name": group_name, "tags": []})
            groups[group_id]["tags"].append(deepcopy(tag))
        return {
            **_base_response(),
            "ok": True,
            "result_status": "fake_stub_tags_listed",
            "tags": deepcopy(self._tags),
            "groups": list(groups.values()),
            "normalized_tag_ids": [str(item["tag_id"]) for item in self._tags],
        }

    def validate_tag_ids(self, tag_ids: list[str]) -> Json:
        requested = [str(item or "") for item in tag_ids or []]
        normalized = _normalize_tag_ids(requested)
        known = {str(item.get("tag_id") or "") for item in self._tags}
        invalid = [tag_id for tag_id in normalized if tag_id not in known]
        ok = bool(normalized) and not invalid
        return {
            **_base_response(),
            "ok": ok,
            "result_status": "valid" if ok else "invalid",
            "error_code": "" if ok else "invalid_tag_id",
            "requested_tag_ids": requested,
            "normalized_tag_ids": normalized,
            "invalid_tag_ids": invalid,
        }

    def dry_run_mark_tags(
        self,
        *,
        external_userid: str,
        tag_ids: list[str],
        operator: str,
        idempotency_key: str,
    ) -> Json:
        return self._dry_run_tag_operation(
            operation="dry_run_mark_tags",
            executed_field="mark_tag_executed",
            external_userid=external_userid,
            tag_ids=tag_ids,
            operator=operator,
            idempotency_key=idempotency_key,
        )

    def dry_run_unmark_tags(
        self,
        *,
        external_userid: str,
        tag_ids: list[str],
        operator: str,
        idempotency_key: str,
    ) -> Json:
        return self._dry_run_tag_operation(
            operation="dry_run_unmark_tags",
            executed_field="unmark_tag_executed",
            external_userid=external_userid,
            tag_ids=tag_ids,
            operator=operator,
            idempotency_key=idempotency_key,
        )

    def live_call_attempt(self) -> Json:
        return {
            **_base_response(),
            "ok": False,
            "result_status": "blocked",
            "error_code": ERROR_LIVE_CALL_NOT_ENABLED,
            "error_message": "Live WeCom calls are not enabled for Phase 5B fake/stub adapter.",
        }

    def _dry_run_tag_operation(
        self,
        *,
        operation: str,
        executed_field: str,
        external_userid: str,
        tag_ids: list[str],
        operator: str,
        idempotency_key: str,
    ) -> Json:
        normalized_external_userid = str(external_userid or "").strip()
        normalized_operator = str(operator or "").strip()
        normalized_key = str(idempotency_key or "").strip()
        if not normalized_external_userid:
            return self._error("external_userid_missing")
        if not normalized_key:
            return self._error("idempotency_key_required")

        validation = self.validate_tag_ids(tag_ids)
        if not validation.get("ok"):
            return {
                **validation,
                "result_status": "invalid",
                "external_userid_redacted": _redact_external_userid(normalized_external_userid),
                "operator": normalized_operator,
                "idempotency_key": normalized_key,
            }

        request_payload = {
            "operation": operation,
            "external_userid": normalized_external_userid,
            "tag_ids": validation["normalized_tag_ids"],
            "operator": normalized_operator,
        }
        request_hash = _canonical_hash(request_payload)
        existing = self._idempotency.get(normalized_key)
        if existing and existing.request_hash != request_hash:
            return {
                **_base_response(),
                "ok": False,
                "result_status": "conflict",
                "error_code": "duplicate_idempotency_key",
                "external_userid_redacted": _redact_external_userid(normalized_external_userid),
                "requested_tag_ids": validation["requested_tag_ids"],
                "normalized_tag_ids": validation["normalized_tag_ids"],
                "operator": normalized_operator,
                "idempotency_key": normalized_key,
                "request_hash": request_hash,
                "idempotency_replay": False,
            }
        if existing:
            replayed = deepcopy(existing.response)
            replayed["idempotency_replay"] = True
            replayed["result_status"] = "replay"
            replayed["timestamp"] = _timestamp()
            replayed["side_effect_safety"] = _side_effect_safety()
            return replayed

        response = {
            **_base_response(),
            "ok": True,
            "result_status": "dry_run_validated",
            "error_code": "",
            executed_field: False,
            "external_userid_redacted": _redact_external_userid(normalized_external_userid),
            "requested_tag_ids": validation["requested_tag_ids"],
            "normalized_tag_ids": validation["normalized_tag_ids"],
            "operator": normalized_operator,
            "idempotency_key": normalized_key,
            "request_hash": request_hash,
            "idempotency_replay": False,
            "environment": os.getenv("AICRM_NEXT_ENV", "local"),
            "production_external_success": False,
            "source_status": "fake_stub_dry_run",
        }
        self._idempotency[normalized_key] = IdempotencyRecord(request_hash=request_hash, response=deepcopy(response))
        return response

    def _error(self, error_code: str) -> Json:
        return {
            **_base_response(),
            "ok": False,
            "result_status": "invalid",
            "error_code": error_code,
        }


def build_fake_stub_wecom_tag_adapter() -> FakeStubWeComTagAdapter:
    return FakeStubWeComTagAdapter()
