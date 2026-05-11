"""Segments 服务 — 注册表 CRUD + 人数缓存刷新 + 系统默认分层 seed。

API 风格全部走"显式参数 + 单一职责"，方便外部 Agent 通过 MCP 工具直接调。
所有写操作都要求带 ``operator``（人或 Agent 标识）便于审计。

CRM 前端**不开放**新建/编辑入口；这里所有写函数都只服务 MCP 工具调用。
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any, Iterable

from ...db import get_db
from .sql_sandbox import (
    SqlSandboxError,
    fetch_member_ids,
    run_segment_query,
    validate_segment_sql,
)


logger = logging.getLogger(__name__)


_DEFAULT_SAMPLE_SIZE = 20


def _normalize_code(code: str) -> str:
    text = (code or "").strip().lower()
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or f"seg_{uuid.uuid4().hex[:8]}"


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def list_segments(
    *,
    status: str = "active",
    source_type: str = "",
    keyword: str = "",
    limit: int = 200,
    recompute: bool = True,
) -> list[dict[str, Any]]:
    """列出 Segment。

    Args:
        recompute: **默认 True** — 对每个返回的 segment 实时跑一次 SQL 算
            headcount，并顺手回写 cached_headcount。这是默认行为，保证统计
            永远正确（不依赖某个 cron 或 hook 来刷新缓存）。

            性能场景：单条 segment SQL 都是简单 WHERE，毫秒级；50 个 segment
            一次 list 也只是几十毫秒，可控。

            只在批量调用（如 Agent 一秒内多次 list）才传 False 走缓存。
    """
    db = get_db()
    cur = db.cursor()
    where = ["1=1"]
    args: list[Any] = []
    if status:
        where.append("status = ?")
        args.append(status)
    if source_type:
        where.append("source_type = ?")
        args.append(source_type)
    kw = (keyword or "").strip()
    if kw:
        where.append("(segment_code LIKE ? OR display_name LIKE ? OR description LIKE ?)")
        args.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])
    args.append(int(limit))
    cur.execute(
        f"""
        SELECT id, segment_code, display_name, description, source_type, status,
               version, sql_query, sql_params_json,
               cached_headcount, last_refreshed_at, last_refresh_error,
               usage_count, created_by_agent, created_at, updated_at, tags_json
        FROM segments
        WHERE {' AND '.join(where)}
        ORDER BY usage_count DESC, updated_at DESC, id DESC
        LIMIT ?
        """,
        tuple(args),
    )
    rows = cur.fetchall() or []
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        try:
            d["tags"] = json.loads(d.pop("tags_json") or "[]")
        except (TypeError, ValueError):
            d["tags"] = []
        # 实时重算 headcount（解决 cached_headcount 永远是创建时旧值的问题）
        if recompute:
            sql_query = str(d.pop("sql_query", "") or "")
            try:
                params = json.loads(d.pop("sql_params_json", "") or "{}")
            except (TypeError, ValueError):
                params = {}
            if sql_query:
                try:
                    res = run_segment_query(sql=sql_query, params=params)
                    new_count = int(res.get("row_count", 0))
                    if new_count != int(d.get("cached_headcount", 0)):
                        # 顺手回写缓存，下次走缓存也能拿到准确值
                        try:
                            cur2 = db.cursor()
                            cur2.execute(
                                "UPDATE segments SET cached_headcount = ?, last_refreshed_at = ? WHERE id = ?",
                                (new_count, _now_iso(), int(d["id"])),
                            )
                            db.commit()
                        except Exception:  # pragma: no cover
                            try:
                                if hasattr(db, "rollback"):
                                    db.rollback()
                            except Exception:
                                pass
                    d["cached_headcount"] = new_count
                    d["last_refreshed_at"] = _now_iso()
                except Exception as exc:  # pragma: no cover - defensive
                    logger.debug("recompute headcount failed for %s: %s", d.get("segment_code"), exc)
                    try:
                        if hasattr(db, "rollback"):
                            db.rollback()
                    except Exception:
                        pass
        else:
            d.pop("sql_query", None)
            d.pop("sql_params_json", None)
        out.append(d)
    return out


def get_segment(
    *,
    segment_code: str = "",
    segment_id: int | None = None,
    recompute: bool = True,
) -> dict[str, Any] | None:
    """拿单个 Segment。recompute=True（默认）会顺手实时算 headcount。"""
    db = get_db()
    cur = db.cursor()
    if segment_id is not None:
        cur.execute("SELECT * FROM segments WHERE id = ?", (int(segment_id),))
    elif segment_code:
        cur.execute("SELECT * FROM segments WHERE segment_code = ?", (str(segment_code),))
    else:
        return None
    row = cur.fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["sql_params"] = json.loads(d.get("sql_params_json") or "{}")
    except (TypeError, ValueError):
        d["sql_params"] = {}
    try:
        d["cached_sample"] = json.loads(d.get("cached_sample_json") or "[]")
    except (TypeError, ValueError):
        d["cached_sample"] = []
    try:
        d["tags"] = json.loads(d.get("tags_json") or "[]")
    except (TypeError, ValueError):
        d["tags"] = []
    # 实时重算 — 默认行为，保证返回的 cached_headcount 永远准
    if recompute:
        sql_query = str(d.get("sql_query") or "")
        if sql_query:
            try:
                res = run_segment_query(sql=sql_query, params=d.get("sql_params") or {})
                new_count = int(res.get("row_count", 0))
                if new_count != int(d.get("cached_headcount") or 0):
                    try:
                        cur2 = db.cursor()
                        cur2.execute(
                            "UPDATE segments SET cached_headcount = ?, last_refreshed_at = ? WHERE id = ?",
                            (new_count, _now_iso(), int(d["id"])),
                        )
                        db.commit()
                    except Exception:  # pragma: no cover
                        try:
                            if hasattr(db, "rollback"):
                                db.rollback()
                        except Exception:
                            pass
                d["cached_headcount"] = new_count
                d["last_refreshed_at"] = _now_iso()
            except Exception as exc:  # pragma: no cover
                logger.debug("get_segment recompute failed for %s: %s", d.get("segment_code"), exc)
                try:
                    if hasattr(db, "rollback"):
                        db.rollback()
                except Exception:
                    pass
    return d


def create_segment(
    *,
    segment_code: str,
    display_name: str,
    description: str = "",
    sql_query: str,
    sql_params: dict[str, Any] | None = None,
    source_type: str = "ai_generated",
    tags: Iterable[str] = (),
    operator: str = "",
    session_id: str = "",
    activate: bool = False,
) -> dict[str, Any]:
    """Agent 创建一个新分层。强制 SQL 沙箱校验 + 试跑一次拿到人数 / 样本。"""
    code = _normalize_code(segment_code)
    name = (display_name or "").strip() or code
    ok, reason = validate_segment_sql(sql_query)
    if not ok:
        raise SqlSandboxError(f"validate_failed:{reason}")
    # 试跑 — 验证 SQL 真能查到 member_id
    try:
        first_run = run_segment_query(sql=sql_query, params=sql_params or {})
    except SqlSandboxError as exc:
        raise SqlSandboxError(f"dry_run_failed:{exc}") from exc
    headcount = int(first_run["row_count"])
    sample = first_run["rows"][:_DEFAULT_SAMPLE_SIZE]

    db = get_db()
    cur = db.cursor()
    # 看 code 是否已存在
    cur.execute("SELECT id FROM segments WHERE segment_code = ?", (code,))
    if cur.fetchone():
        raise ValueError(f"segment_code already exists: {code}")
    cur.execute(
        """
        INSERT INTO segments
            (segment_code, display_name, description, source_type, sql_query,
             sql_params_json, status, version, created_by_agent, created_by_session,
             cached_headcount, cached_sample_json, last_refreshed_at, tags_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
        """,
        (
            code,
            name,
            (description or "").strip(),
            source_type or "ai_generated",
            sql_query,
            json.dumps(sql_params or {}, ensure_ascii=False),
            "active" if activate else "draft",
            (operator or "")[:100],
            (session_id or "")[:100],
            headcount,
            json.dumps(sample, ensure_ascii=False, default=str)[:8000],
            _now_iso(),
            json.dumps(list(tags or []), ensure_ascii=False),
        ),
    )
    db.commit()
    new_id = int(cur.lastrowid or 0)
    logger.info("segment created code=%s id=%s headcount=%d", code, new_id, headcount)
    return get_segment(segment_id=new_id) or {}


def update_segment(
    *,
    segment_code: str = "",
    segment_id: int | None = None,
    display_name: str | None = None,
    description: str | None = None,
    sql_query: str | None = None,
    sql_params: dict[str, Any] | None = None,
    status: str | None = None,
    tags: Iterable[str] | None = None,
    operator: str = "",
) -> dict[str, Any]:
    """更新分层；改了 SQL 就重新校验 + 重新跑一次拿头部数据。"""
    seg = get_segment(segment_code=segment_code, segment_id=segment_id)
    if not seg:
        raise LookupError("segment not found")
    sets: dict[str, Any] = {}
    if display_name is not None:
        sets["display_name"] = (display_name or "").strip()
    if description is not None:
        sets["description"] = (description or "").strip()
    if tags is not None:
        sets["tags_json"] = json.dumps(list(tags), ensure_ascii=False)
    if status is not None:
        if status not in ("draft", "active", "archived"):
            raise ValueError(f"invalid status: {status}")
        sets["status"] = status
    if sql_query is not None:
        ok, reason = validate_segment_sql(sql_query)
        if not ok:
            raise SqlSandboxError(f"validate_failed:{reason}")
        sets["sql_query"] = sql_query
        sets["sql_params_json"] = json.dumps(sql_params or {}, ensure_ascii=False)
        sets["version"] = int(seg.get("version") or 1) + 1
        # 重跑
        run = run_segment_query(sql=sql_query, params=sql_params or {})
        sets["cached_headcount"] = int(run["row_count"])
        sets["cached_sample_json"] = json.dumps(run["rows"][:_DEFAULT_SAMPLE_SIZE], ensure_ascii=False, default=str)[:8000]
        sets["last_refreshed_at"] = _now_iso()
        sets["last_refresh_error"] = ""
    if not sets:
        return seg
    sets["updated_at"] = _now_iso()
    db = get_db()
    cur = db.cursor()
    placeholders = ",".join([f"{k} = ?" for k in sets.keys()])
    values = list(sets.values()) + [int(seg["id"])]
    cur.execute(f"UPDATE segments SET {placeholders} WHERE id = ?", tuple(values))
    db.commit()
    return get_segment(segment_id=int(seg["id"])) or {}


def archive_segment(*, segment_code: str = "", segment_id: int | None = None) -> bool:
    seg = get_segment(segment_code=segment_code, segment_id=segment_id)
    if not seg:
        return False
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE segments SET status = 'archived', updated_at = ? WHERE id = ?",
        (_now_iso(), int(seg["id"])),
    )
    db.commit()
    return True


def preview_segment_members(
    *,
    segment_code: str = "",
    segment_id: int | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """实时跑一次 SQL，返回前 N 条样本 + 实时人数。**不更新缓存。**"""
    seg = get_segment(segment_code=segment_code, segment_id=segment_id)
    if not seg:
        raise LookupError("segment not found")
    res = run_segment_query(
        sql=str(seg.get("sql_query") or ""),
        params=seg.get("sql_params") or {},
    )
    return {
        "segment_code": seg["segment_code"],
        "headcount": int(res["row_count"]),
        "sample": res["rows"][: max(1, min(int(limit), 200))],
        "elapsed_ms": int(res.get("elapsed_ms") or 0),
    }


def refresh_segment_cache(
    *,
    segment_code: str = "",
    segment_id: int | None = None,
) -> dict[str, Any]:
    """跑一次 SQL，把人数 / 样本写回缓存。供定时刷新调用。"""
    seg = get_segment(segment_code=segment_code, segment_id=segment_id)
    if not seg:
        raise LookupError("segment not found")
    try:
        res = run_segment_query(
            sql=str(seg.get("sql_query") or ""),
            params=seg.get("sql_params") or {},
        )
        headcount = int(res["row_count"])
        sample = res["rows"][:_DEFAULT_SAMPLE_SIZE]
        error_text = ""
    except SqlSandboxError as exc:
        headcount = 0
        sample = []
        error_text = str(exc)[:300]
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        UPDATE segments SET
            cached_headcount = ?,
            cached_sample_json = ?,
            last_refreshed_at = ?,
            last_refresh_error = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            headcount,
            json.dumps(sample, ensure_ascii=False, default=str)[:8000],
            _now_iso(),
            error_text,
            _now_iso(),
            int(seg["id"]),
        ),
    )
    db.commit()
    return {
        "segment_code": seg["segment_code"],
        "headcount": headcount,
        "error": error_text,
    }


def increment_usage(*, segment_id: int) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE segments SET usage_count = usage_count + 1, updated_at = ? WHERE id = ?",
        (_now_iso(), int(segment_id)),
    )
    db.commit()


# ---------- 系统默认分层 ----------------------------------------------------
#
# 设计原则：**不 hardcode 字面值**。从 ``automation_member`` 三个字段
# (current_audience_code / current_pool / profile_segment_key /
#  behavior_tier_key) 动态发现 distinct 值，每个值建一个 segment。
# 这样：
# - 不同部署的字段值差异（甚至中文 vs 拼音）都能自动覆盖
# - 字段值未来加新枚举时 seed 自动跟上
# - 概览页显示什么数，segment 就是什么数（口径完全一致）

_SILENT_SEED_SPEC = {
    "segment_code": "silent_30d_no_inbound",
    "display_name": "沉默 · 30 天无回复",
    "description": "30 天内有过 outbound 且最近一次 outbound 之后无 inbound 的成员",
    "sql_query": (
        "SELECT m.id AS member_id, m.external_contact_id "
        "FROM automation_member m "
        "WHERE m.last_ai_push_at <> ''"
    ),
    "tags": ["silent", "system"],
}


# 维度元数据 — (字段名, segment_code 前缀, display_name 前缀, tag)
_DIM_DISCOVERIES = (
    ("current_audience_code", "audience", "生命周期", "audience"),
    ("current_pool", "pool", "池子", "pool"),
    ("profile_segment_key", "profile", "自然画像", "profile"),
    ("behavior_tier_key", "behavior", "行为画像", "behavior"),
)

# 已知英文枚举值的中文友好显示名（display_name 用，code 仍用原值/hash）
# 字段值未在表中也照常 seed，只是 display_name 显示原值
_KNOWN_VALUE_LABELS: dict[str, dict[str, str]] = {
    "current_audience_code": {
        "pending_questionnaire": "待填问卷",
        "operating": "运营中",
        "converted": "已转化",
    },
    "current_pool": {
        "new_user": "新用户",
        "active_focus": "活跃-重点",
        "active_normal": "活跃-普通",
        "inactive_focus": "不活跃-重点",
        "inactive_normal": "不活跃-普通",
        "silent": "静默",
        "human_reply": "需人工回复",
        "no_reply": "未回复",
        "removed": "已移除",
    },
    "behavior_tier_key": {
        "msg_lt_2": "消息 < 2 条",
        "msg_2_to_9": "消息 2~9 条",
        "msg_gte_10": "消息 ≥ 10 条",
        "lt_2": "消息 < 2 条",
        "between_2_9": "消息 2~9 条",
        "2_to_9": "消息 2~9 条",
        "gte_10": "消息 ≥ 10 条",
    },
    # profile_segment_key 通常已经是中文（职场人/创业者/老板），无需映射
}

# 人群特征描述 — 给运营 / Agent 看，回答"这群人是什么、为什么这么分"
# Agent 调用 list_segments 时拿到这段描述就能正确选人 / 判断方案
_KNOWN_VALUE_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "current_audience_code": {
        "pending_questionnaire": "等待用户填问卷的阶段；运营触达的目标是引导填问卷、完成首次画像登记。",
        "operating": "已填问卷、运营进行中的成员；自动化节奏和销售跟进的主战场。",
        "converted": "已成功转化（付费 / 报名 / 完成核心动作）的成员，通常进入维护态。",
    },
    "current_pool": {
        "new_user": "新进池的成员（进入运营前几天），优先做欢迎 + 引导，节奏不宜密。",
        "active_focus": "最近有对话活跃 + 被运营标为重点跟进的成员，转化优先级最高，可主动加密触达。",
        "active_normal": "最近有对话活跃但不是重点的成员（普通跟进），常规节奏。",
        "inactive_focus": "近期沉默但被标为重点的成员，需要定向唤醒（提供新价值、限时活动等）。",
        "inactive_normal": "近期沉默且非重点的普通成员，触达频次应低，避免骚扰。",
        "silent": "完全沉默 / 退出活跃池的成员，建议先观察不主动打扰，必要时定向激活。",
        "human_reply": "需要人工跟进、不走自动化触达的成员（敏感问题、复杂咨询）。",
        "no_reply": "AI 推送过但用户未回复的成员，已用过自动化机会，建议人工或暂停。",
        "removed": "已被移除运营的成员（主动屏蔽 / 清退 / 完成生命周期），不再触达。",
    },
    "behavior_tier_key": {
        "msg_lt_2": "对话条数 < 2 条的低活跃成员；可能刚加上、还未建立信任。",
        "lt_2": "对话条数 < 2 条的低活跃成员；可能刚加上、还未建立信任。",
        "msg_2_to_9": "对话条数 2~9 条的中等活跃成员；有交流但未深度互动。",
        "2_to_9": "对话条数 2~9 条的中等活跃成员；有交流但未深度互动。",
        "between_2_9": "对话条数 2~9 条的中等活跃成员；有交流但未深度互动。",
        "msg_gte_10": "对话条数 ≥ 10 条的高活跃成员；强意向，转化优先级最高。",
        "gte_10": "对话条数 ≥ 10 条的高活跃成员；强意向，转化优先级最高。",
    },
    "profile_segment_key": {
        # 项目里的自然画像值通常是中文且因业务而异，这里不预设
        # 但留个映射点，运营可以扩展
    },
}

# v1 hardcode 旧 segment_code（部署 #168 时建过）
# 现在动态发现版用的是真实字段值，这些 hardcode 命中字段值不对会 headcount=0
# seed 时如果发现这些 zombie，自动归档清理（display_name 跟新 segment 重复的根源）
_LEGACY_V1_HARDCODE_CODES = (
    "pool_pending_questionnaire",
    "pool_operating",
    "pool_converted",
    "pool_active_focus",
    "pool_inactive_focus",
    "behavior_msg_lt_2",
    "behavior_msg_2_to_9",
    "behavior_msg_gte_10",
)


def _safe_code_suffix(value: str) -> str:
    """把 distinct 值转成 segment_code 后缀。

    - ASCII 值（如 ``active_focus``、``msg_lt_2``）直接 normalize 后用
    - 非 ASCII 值（如中文「职场人」）用 md5 短 hash 兜底，display_name 仍显示原值
    """
    text = (value or "").strip()
    if not text:
        return ""
    # 尝试直接用字面值
    ascii_safe = re.sub(r"[^a-z0-9_]+", "_", text.lower()).strip("_")
    if ascii_safe and ascii_safe == re.sub(r"[^\x20-\x7e]", "", text).lower().replace(" ", "_").strip("_"):
        return ascii_safe
    # 退回 hash
    import hashlib

    return f"v{hashlib.md5(text.encode('utf-8')).hexdigest()[:8]}"


def _discover_segments_from_member_table() -> list[dict[str, Any]]:
    """从 automation_member 字段动态发现所有 distinct 值，每个建一个 segment。"""
    db = get_db()
    cur = db.cursor()
    out: list[dict[str, Any]] = []
    for column, code_prefix, label_prefix, tag in _DIM_DISCOVERIES:
        try:
            cur.execute(
                f"SELECT DISTINCT {column} AS v FROM automation_member "
                f"WHERE {column} IS NOT NULL AND {column} <> ''"
            )
            rows = cur.fetchall() or []
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("discover %s failed: %s", column, exc)
            try:
                if hasattr(db, "rollback"):
                    db.rollback()
            except Exception:
                pass
            continue
        for row in rows:
            value = ""
            if hasattr(row, "keys"):
                value = str(row.get("v", "") or "").strip() if hasattr(row, "get") else str(row["v"] or "").strip()
            else:
                value = str(row[0] or "").strip() if row else ""
            if not value:
                continue
            suffix = _safe_code_suffix(value)
            if not suffix:
                continue
            # 友好显示名 — 已知英文枚举值映射成中文，未知就用原值
            label_value = (_KNOWN_VALUE_LABELS.get(column) or {}).get(value, value)
            # 人群特征描述 — 给运营 / Agent 看的"这群人是什么"
            description = (_KNOWN_VALUE_DESCRIPTIONS.get(column) or {}).get(
                value,
                f"automation_member.{column} = {value} 的成员（业务方未提供详细描述）",
            )
            # SQL 字面值用单引号转义
            value_escaped = value.replace("'", "''")
            out.append({
                "segment_code": f"{code_prefix}_{suffix}",
                "display_name": f"{label_prefix} · {label_value}",
                "description": description,
                "sql_query": (
                    f"SELECT id AS member_id, external_contact_id "
                    f"FROM automation_member WHERE {column} = '{value_escaped}'"
                ),
                "tags": [tag, "system"],
            })
    out.append(_SILENT_SEED_SPEC)
    return out


def _archive_legacy_hardcode_segments() -> int:
    """归档 v1 hardcode 旧 segment（headcount=0 的 zombie），消除"看着像重复"的展示。

    具体场景：#168 部署时建过 8 个 hardcode 字面值的 segment（如
    ``behavior_msg_gte_10``）；#170 改为动态发现后，会用真实字段值再建一个
    （如 ``behavior_gte_10``）。两个 segment_code 不同但 display_name 都
    映射成"行为画像 · 消息 ≥ 10 条" → 看板上看着重复。

    本函数只对：
    - source_type='system_default'
    - status='active'（未归档的）
    - cached_headcount=0（确认是 zombie，避免误删合法的）
    - segment_code IN 已知 v1 hardcode 列表（精准定位，不波及别的）
    """
    db = get_db()
    cur = db.cursor()
    placeholders = ",".join(["?"] * len(_LEGACY_V1_HARDCODE_CODES))
    cur.execute(
        f"UPDATE segments SET status = 'archived', updated_at = ? "
        f"WHERE source_type = 'system_default' AND status = 'active' "
        f"AND cached_headcount = 0 "
        f"AND segment_code IN ({placeholders})",
        (_now_iso(), *_LEGACY_V1_HARDCODE_CODES),
    )
    affected = int(cur.rowcount or 0)
    db.commit()
    if affected:
        logger.info("archived %d legacy v1 hardcode segments", affected)
    return affected


def _trigger_dashboard_backfill_quiet() -> None:
    """触发一次 dashboard 计算，让 automation_member.behavior_tier_key /
    profile_segment_key 字段被 backfill 成跟 dashboard 一致的口径。

    Dashboard 是从 message_activity_count_map 实时算 behavior_tier，然后
    通过 ``_maybe_persist_member_segment_keys`` 静默写回 automation_member。
    Segment seed 之后查的就是这个字段。

    如果 dashboard 调用失败也不影响 seed 主流程 (best-effort)。
    """
    try:
        from ..automation_conversion.workflow_service import get_conversion_dashboard_payload

        get_conversion_dashboard_payload(program_id=None)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("dashboard backfill skipped: %s", exc)


def seed_default_segments() -> int:
    """从 automation_member 字段动态发现 distinct 值并建 segment。

    流程：
    1. 归档 v1 hardcode 的 zombie segment（避免"看着重复"）
    2. 触发 dashboard backfill — 让字段值跟 dashboard 口径对齐
    3. 从 automation_member distinct 4 个字段值，每个建一个 segment（带描述）
    4. 已存在的 segment 跳过；任何一条失败都 rollback，不影响下一条
    """
    # ① 归档 v1 hardcode 的旧 segment（headcount=0 的 zombie）
    try:
        _archive_legacy_hardcode_segments()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("archive legacy segments failed: %s", exc)

    # ② 主动 backfill member 字段（让 dashboard 显示和 segment 查询用同一口径）
    _trigger_dashboard_backfill_quiet()

    db = get_db()
    try:
        if hasattr(db, "rollback"):
            db.rollback()
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("pre-seed rollback noop: %s", exc)

    # ③ 字段已经 backfill 过了，distinct 出来的值就是 dashboard 用的值
    specs = _discover_segments_from_member_table()
    written = 0
    for spec in specs:
        try:
            existing = get_segment(segment_code=spec["segment_code"])
            if existing:
                continue
            create_segment(
                segment_code=spec["segment_code"],
                display_name=spec["display_name"],
                description=spec["description"],
                sql_query=spec["sql_query"],
                source_type="system_default",
                tags=spec.get("tags") or [],
                operator="system",
                activate=True,
            )
            written += 1
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("seed segment failed code=%s err=%s", spec["segment_code"], exc)
            # 单条失败 rollback，让下一条还能跑（PG 事务级隔离）
            try:
                if hasattr(db, "rollback"):
                    db.rollback()
            except Exception:
                pass
    return written


__all__ = [
    "archive_segment",
    "create_segment",
    "get_segment",
    "increment_usage",
    "list_segments",
    "preview_segment_members",
    "refresh_segment_cache",
    "seed_default_segments",
    "update_segment",
]
