from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

from aicrm_next.platform_foundation.command_bus.models import utcnow_iso
from aicrm_next.shared.typing import JsonDict

from .read_model import _fixture_rows


def _text(value: Any) -> str:
    return str(value or "").strip()


class WeComTagWriteRepository:
    def __init__(self) -> None:
        groups, tags = _fixture_rows()
        self._groups: dict[str, JsonDict] = {str(group["group_id"]): deepcopy(group) for group in groups}
        self._tags: dict[str, JsonDict] = {str(tag["tag_id"]): deepcopy(tag) for tag in tags}
        self._writes: list[JsonDict] = []

    def list_writes(self) -> list[JsonDict]:
        return deepcopy(self._writes)

    def get_group(self, group_id: str) -> JsonDict | None:
        group = self._groups.get(_text(group_id))
        return deepcopy(group) if group else None

    def get_tag(self, tag_id: str) -> JsonDict | None:
        tag = self._tags.get(_text(tag_id))
        return deepcopy(tag) if tag else None

    def create_group(self, *, command_id: str, group_name: str, first_tag_name: str = "") -> JsonDict:
        group_name = _text(group_name)
        if not group_name:
            raise ValueError("group_name is required")
        if any(_text(group.get("group_name")) == group_name for group in self._groups.values()):
            raise ValueError("group_name already exists")
        group_id = f"group_next_{uuid4().hex[:10]}"
        now = utcnow_iso()
        group = {
            "group_id": group_id,
            "tag_group_id": group_id,
            "group_key": group_id,
            "group_name": group_name,
            "tag_count": 0,
            "source": "local_projection",
            "updated_at": now,
            "synced_at": now,
        }
        self._groups[group_id] = group
        created_tags: list[JsonDict] = []
        if _text(first_tag_name):
            created_tags.append(self.create_tag(command_id=command_id, group_id=group_id, tag_name=first_tag_name))
        self._record(command_id, "tag_group_created", {"group": group, "tags": created_tags})
        return {"group": deepcopy(group), "tags": deepcopy(created_tags)}

    def update_group(self, *, command_id: str, group_id: str, group_name: str) -> JsonDict:
        group = self._require_group(group_id)
        group_name = _text(group_name)
        if not group_name:
            raise ValueError("group_name is required")
        group["group_name"] = group_name
        group["updated_at"] = utcnow_iso()
        for tag in self._tags.values():
            if _text(tag.get("group_id")) == _text(group_id):
                tag["group_name"] = group_name
                tag["updated_at"] = group["updated_at"]
        self._record(command_id, "tag_group_updated", {"group": group})
        return deepcopy(group)

    def delete_group(self, *, command_id: str, group_id: str) -> JsonDict:
        group = self._require_group(group_id)
        deleted_tags = [tag_id for tag_id, tag in self._tags.items() if _text(tag.get("group_id")) == _text(group_id)]
        for tag_id in deleted_tags:
            self._tags.pop(tag_id, None)
        self._groups.pop(_text(group_id), None)
        self._record(command_id, "tag_group_deleted", {"group": group, "deleted_tag_ids": deleted_tags})
        return {"group": deepcopy(group), "deleted_tag_ids": deleted_tags}

    def create_tag(self, *, command_id: str, group_id: str, tag_name: str) -> JsonDict:
        group = self._require_group(group_id)
        tag_name = _text(tag_name)
        if not tag_name:
            raise ValueError("tag_name is required")
        if any(_text(tag.get("group_id")) == _text(group_id) and _text(tag.get("tag_name")) == tag_name for tag in self._tags.values()):
            raise ValueError("tag_name already exists in group")
        now = utcnow_iso()
        tag_id = f"tag_next_{uuid4().hex[:10]}"
        tag = {
            "tag_id": tag_id,
            "tag_group_id": _text(group.get("group_id")),
            "tag_name": tag_name,
            "group_id": _text(group.get("group_id")),
            "group_name": _text(group.get("group_name")),
            "order": len([item for item in self._tags.values() if _text(item.get("group_id")) == _text(group_id)]) + 1,
            "status": "active",
            "source": "local_projection",
            "updated_at": now,
            "synced_at": now,
        }
        self._tags[tag_id] = tag
        group["tag_count"] = len([item for item in self._tags.values() if _text(item.get("group_id")) == _text(group_id)])
        group["updated_at"] = now
        self._record(command_id, "tag_created", {"tag": tag})
        return deepcopy(tag)

    def update_tag(self, *, command_id: str, tag_id: str, tag_name: str) -> JsonDict:
        tag = self._require_tag(tag_id)
        tag_name = _text(tag_name)
        if not tag_name:
            raise ValueError("tag_name is required")
        tag["tag_name"] = tag_name
        tag["updated_at"] = utcnow_iso()
        self._record(command_id, "tag_updated", {"tag": tag})
        return deepcopy(tag)

    def delete_tag(self, *, command_id: str, tag_id: str) -> JsonDict:
        tag = self._require_tag(tag_id)
        self._tags.pop(_text(tag_id), None)
        group = self._groups.get(_text(tag.get("group_id")))
        if group:
            group["tag_count"] = len([item for item in self._tags.values() if _text(item.get("group_id")) == _text(group.get("group_id"))])
            group["updated_at"] = utcnow_iso()
        self._record(command_id, "tag_deleted", {"tag": tag})
        return deepcopy(tag)

    def sync_catalog(self, *, command_id: str) -> JsonDict:
        now = utcnow_iso()
        for group in self._groups.values():
            group["synced_at"] = now
            group["updated_at"] = group.get("updated_at") or now
        for tag in self._tags.values():
            tag["synced_at"] = now
            tag["updated_at"] = tag.get("updated_at") or now
        payload = {"synced_at": now, "groups": len(self._groups), "tags": len(self._tags)}
        self._record(command_id, "tag_catalog_sync_planned", payload)
        return payload

    def _require_group(self, group_id: str) -> JsonDict:
        group = self._groups.get(_text(group_id))
        if not group:
            raise KeyError("tag group not found")
        return group

    def _require_tag(self, tag_id: str) -> JsonDict:
        tag = self._tags.get(_text(tag_id))
        if not tag:
            raise KeyError("tag not found")
        return tag

    def _record(self, command_id: str, write_type: str, payload: JsonDict) -> None:
        self._writes.append({"command_id": command_id, "write_type": write_type, "payload": deepcopy(payload), "created_at": utcnow_iso()})
