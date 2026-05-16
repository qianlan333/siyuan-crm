"""media_library 共享工具函数

抽离自 ``image_library`` / ``miniprogram_library`` 两边重复实现：JSON 编解码、
UTC 时间戳序列化、tag 数组归一化、AI metadata dict 校验。两边 ``__init__.py``
以 ``_xxx = xxx`` 别名 re-import 保持向后兼容（测试和外部 import 不变）。

不放上传 / 缓存 / 数据库相关逻辑——那些跟 asset_type 强绑定，留给后续阶段（阶段 2
引入 ``media_library`` 表后再统一）。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def iso(dt: datetime) -> str:
    """秒级精度的 timezone-aware ISO8601 字符串，给 PG TIMESTAMPTZ 写入。"""
    return dt.replace(microsecond=0).isoformat()


def parse_iso(value: Any) -> datetime | None:
    """容错解析 ISO 字符串 / datetime；naive datetime 默认按 UTC 处理。

    返回 None 表示不可解析（空值 / 非法 ISO）；调用方按 None 判过期即可。
    """
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def row_to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    return dict(row)


def to_jsonb_text(payload: Any, *, default: str) -> str:
    """把 dict/list/str 序列化成 JSON 文本，给 PG JSONB 写入用。

    ``default`` 必须是有效 JSON 字面量（``'[]'`` 或 ``'{}'``），用于 None / 空串。
    与 ``broadcast_jobs/repo.py:_to_jsonb_text`` 同源（暂未跨域合并）。
    """
    if payload is None:
        return default
    if isinstance(payload, (dict, list)):
        return json.dumps(payload, ensure_ascii=False)
    if isinstance(payload, str):
        return payload or default
    return json.dumps(payload, ensure_ascii=False)


def decode_jsonb(value: Any, *, default: Any) -> Any:
    """从 PG JSONB 或历史 JSON 文本读出来的值统一解码。

    PG psycopg 已经把 JSONB 反序列化成 dict/list；历史 JSON 字符串仍然兼容。
    """
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def normalize_tags(value: Any) -> list[str]:
    """把外部传入的 tags 标准化成去重 + 去空 + trim 的字符串数组。

    入参可能是 list / 逗号分隔字符串 / None。统一截断每个 tag 到 64 字符，
    最多保留 50 个，避免脏数据撑爆。
    """
    if value is None:
        return []
    if isinstance(value, str):
        # "好评,信任建立" → ["好评", "信任建立"]
        raw = [s.strip() for s in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        raw = [str(s).strip() for s in value]
    else:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for tag in raw:
        if not tag:
            continue
        clipped = tag[:64]
        if clipped in seen:
            continue
        seen.add(clipped)
        out.append(clipped)
        if len(out) >= 50:
            break
    return out


def normalize_ai_metadata(value: Any) -> dict[str, Any]:
    """ai_metadata 必须是 dict；其他形态丢回空 dict 防写脏。"""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {}


__all__ = [
    "decode_jsonb",
    "iso",
    "normalize_ai_metadata",
    "normalize_tags",
    "now_utc",
    "parse_iso",
    "row_to_dict",
    "to_jsonb_text",
]
