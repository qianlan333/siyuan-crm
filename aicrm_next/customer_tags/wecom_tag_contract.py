from __future__ import annotations

from typing import Any, Protocol


Json = dict[str, Any]


class WeComTagAdapterContract(Protocol):
    def list_wecom_tags(self) -> Json: ...

    def validate_tag_ids(self, tag_ids: list[str]) -> Json: ...

    def dry_run_mark_tags(
        self,
        *,
        external_userid: str,
        tag_ids: list[str],
        operator: str,
        idempotency_key: str,
    ) -> Json: ...

    def dry_run_unmark_tags(
        self,
        *,
        external_userid: str,
        tag_ids: list[str],
        operator: str,
        idempotency_key: str,
    ) -> Json: ...


class WeComTagLiveAdapterContract(Protocol):
    def list_wecom_tags_live(self) -> Json: ...

    def mark_tags_live(
        self,
        *,
        external_userid: str,
        tag_ids: list[str],
        operator: str,
        idempotency_key: str,
    ) -> Json: ...

    def unmark_tags_live(
        self,
        *,
        external_userid: str,
        tag_ids: list[str],
        operator: str,
        idempotency_key: str,
    ) -> Json: ...
