from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..client import CrmApiClient


class TagsAdapter:
    def __init__(self, client: CrmApiClient) -> None:
        self.client = client

    def list_tags(self) -> list[dict[str, str]]:
        payload = self.client.get("/api/tags")
        groups = []
        if isinstance(payload, dict):
            result = payload.get("result")
            if isinstance(result, dict) and isinstance(result.get("tag_group"), list):
                groups = result.get("tag_group") or []
            elif isinstance(payload.get("tag_group"), list):
                groups = payload.get("tag_group") or []

        items: list[dict[str, str]] = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            group_id = str(group.get("group_id") or "").strip()
            group_name = str(group.get("group_name") or "").strip()
            for tag in group.get("tag") or []:
                if not isinstance(tag, dict):
                    continue
                tag_id = str(tag.get("id") or tag.get("tag_id") or "").strip()
                tag_name = str(tag.get("name") or tag.get("tag_name") or "").strip()
                if not tag_id or not tag_name:
                    continue
                items.append(
                    {
                        "tag_id": tag_id,
                        "tag_name": tag_name,
                        "group_id": group_id,
                        "group_name": group_name,
                    }
                )
        return items

    def mark_tags(self, userid: str, external_userid: str, add_tags: Sequence[str]) -> Any:
        return self.client.post(
            "/api/tags/mark",
            json={
                "userid": userid,
                "external_userid": external_userid,
                "add_tag": list(add_tags),
            },
        )

    def unmark_tags(self, userid: str, external_userid: str, remove_tags: Sequence[str]) -> Any:
        return self.client.post(
            "/api/tags/unmark",
            json={
                "userid": userid,
                "external_userid": external_userid,
                "remove_tag": list(remove_tags),
            },
        )
