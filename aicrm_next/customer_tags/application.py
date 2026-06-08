from __future__ import annotations

from typing import Any

from .wecom_tag_adapter import FakeStubWeComTagAdapter, build_fake_stub_wecom_tag_adapter
from .wecom_tag_contract import WeComTagAdapterContract


Json = dict[str, Any]
_DEFAULT_ADAPTER = build_fake_stub_wecom_tag_adapter()


def reset_wecom_tag_fake_stub_state() -> None:
    _DEFAULT_ADAPTER.reset_idempotency()


class WeComTagApplicationService:
    def __init__(self, adapter: WeComTagAdapterContract | None = None) -> None:
        self._adapter = adapter or _DEFAULT_ADAPTER

    def list_wecom_tags(self) -> Json:
        return self._adapter.list_wecom_tags()

    def validate_tag_ids(self, tag_ids: list[str]) -> Json:
        return self._adapter.validate_tag_ids(tag_ids)

    def dry_run_mark_tags(
        self,
        *,
        external_userid: str,
        tag_ids: list[str],
        operator: str,
        idempotency_key: str,
    ) -> Json:
        return self._adapter.dry_run_mark_tags(
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
        return self._adapter.dry_run_unmark_tags(
            external_userid=external_userid,
            tag_ids=tag_ids,
            operator=operator,
            idempotency_key=idempotency_key,
        )

    def live_call_attempt(self) -> Json:
        if hasattr(self._adapter, "live_call_attempt"):
            return self._adapter.live_call_attempt()  # type: ignore[attr-defined]
        return {"ok": False, "error_code": "live_call_not_enabled", "live_call_executed": False}


def build_wecom_tag_application_service() -> WeComTagApplicationService:
    return WeComTagApplicationService()
