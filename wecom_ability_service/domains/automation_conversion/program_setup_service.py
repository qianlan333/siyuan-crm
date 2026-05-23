from __future__ import annotations

import re
from typing import Any

from ...db import get_db
from ..tags import service as tags_domain_service
from ..wechat_pay.service import list_products as list_wechat_pay_products
from . import program_repo, repo, workflow_repo
from .channel_service import save_default_channel_settings
from .customer_acquisition_service import create_customer_acquisition_link, list_customer_acquisition_links
from .operation_task_service import list_operation_tasks
from .program_service import (
    PROGRAM_STATUS_ACTIVE,
    get_automation_program,
    get_default_automation_program_id,
    update_automation_program_status,
)
from .service import _normalized_text, get_settings_payload
from .workflow_service import list_conversion_profile_segment_templates

BLOCK_BASIC = "basic"
BLOCK_ENTRY_CHANNEL = "entry_channel"
BLOCK_SEGMENTATION = "questionnaire_segmentation"
BLOCK_AUDIENCE_ENTRY_RULE = "audience_entry_rule"
BLOCK_PUBLISH_STATE = "publish_state"
CONFIG_BLOCK_KEYS = (
    BLOCK_BASIC,
    BLOCK_ENTRY_CHANNEL,
    BLOCK_SEGMENTATION,
    BLOCK_AUDIENCE_ENTRY_RULE,
    BLOCK_PUBLISH_STATE,
)

SETUP_STEPS = (
    ("basic", "基础信息"),
    ("entry", "入口渠道"),
    ("segmentation", "分层规则"),
    ("entry-rule", "入池规则"),
    ("operations", "运营编排"),
    ("publish", "检查并发布"),
)

DEFAULT_AUDIENCE_ENTRY_RULES = [
    {
        "event": "channel_enter",
        "condition": "any_entry_channel",
        "target_audience_code": "pending_questionnaire",
        "enabled": True,
    },
    {
        "event": "questionnaire_submitted",
        "condition": "questionnaire_id_matched",
        "target_audience_code": "operating",
        "enabled": True,
    },
]

AUDIENCE_LABELS = {
    "pending_questionnaire": "待填问卷",
    "operating": "运营中",
    "converted": "已转化",
}

ENTRY_CONDITION_LABELS = {
    "any_entry_channel": "任意当前方案入口",
    "specific_qrcode_channel": "指定二维码入口",
    "specific_customer_acquisition_link": "指定获客助手入口",
}

QUESTIONNAIRE_CONDITION_LABELS = {
    "questionnaire_id_matched": "问卷提交后",
    "normal_question_rule_hit": "命中普通问卷规则",
    "score_segment_hit": "命中总分分层",
    "any_submission": "任意提交",
}

QUESTION_OPTION_CATEGORY_MODE = "single_question_option_category"
QUESTION_CHOICE_TYPES = {"single_choice", "multi_choice"}
SETUP_PROFILE_TEMPLATE_CODE_PREFIX = "setup_normal_option_category"
AUDIENCE_REVIEW_STEP_KEYS = {"order_product", "questionnaire", "conversion_product"}


def _program_code(value: Any) -> str:
    text = _normalized_text(value).lower()
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def _is_default_program(program_id: int) -> bool:
    try:
        return int(program_id) == int(get_default_automation_program_id())
    except Exception:
        return False


def initialize_empty_config_blocks(program_id: int) -> None:
    for block_key in CONFIG_BLOCK_KEYS:
        if program_repo.get_config_block_row(int(program_id), block_key):
            continue
        program_repo.upsert_config_block_row(int(program_id), block_key, {}, status="draft")


def copy_config_blocks(source_program_id: int, target_program_id: int) -> list[dict[str, Any]]:
    return program_repo.copy_config_blocks(int(source_program_id), int(target_program_id))


def _blocks_by_key(program_id: int) -> dict[str, dict[str, Any]]:
    return {str(item.get("block_key") or ""): item for item in program_repo.list_config_block_rows(int(program_id))}


def _legacy_segmentation_payload() -> dict[str, Any]:
    settings = get_settings_payload(program_id=None)
    return {
        "questionnaire_id": int(((settings.get("config") or {}).get("questionnaire_id")) or 0) or None,
        "default_strategy": "normal_question_rules",
        "strategies": {
            "normal_question_rules": {
                "enabled": True,
                "core_threshold": int(((settings.get("config") or {}).get("core_threshold")) or 0),
                "rules": list(((settings.get("rule_editor") or {}).get("rules")) or []),
            },
            "score_segments": {"enabled": False, "ranges": []},
            "profile_dimension": {"enabled": False, "usage": "content_variable_only"},
        },
        "priority": ["normal_question_rules", "score_segments"],
        "source": "legacy_singleton",
    }


def _payload_from_block(blocks: dict[str, dict[str, Any]], block_key: str) -> dict[str, Any]:
    return dict((blocks.get(block_key) or {}).get("payload_json") or {})


def _list_owner_candidates() -> list[dict[str, Any]]:
    db = get_db()
    rows: list[dict[str, Any]] = []
    try:
        rows.extend(
            dict(row)
            for row in db.execute(
                """
                SELECT
                    wecom_userid AS owner_staff_id,
                    display_name,
                    position,
                    is_active,
                    'directory' AS source
                FROM admin_wecom_directory_members
                WHERE is_active = TRUE
                ORDER BY display_name ASC, wecom_userid ASC
                """
            ).fetchall()
        )
    except Exception:
        rows = []
    try:
        rows.extend(
            dict(row)
            for row in db.execute(
                """
                SELECT
                    wecom_userid AS owner_staff_id,
                    display_name,
                    '' AS position,
                    is_active,
                    'admin_user' AS source
                FROM admin_users
                WHERE is_active = TRUE
                ORDER BY display_name ASC, wecom_userid ASC
                """
            ).fetchall()
        )
    except Exception:
        pass
    try:
        rows.extend(
            dict(row)
            for row in db.execute(
                """
                SELECT
                    userid AS owner_staff_id,
                    display_name,
                    role AS position,
                    active AS is_active,
                    'owner_role' AS source
                FROM owner_role_map
                WHERE active = TRUE
                ORDER BY display_name ASC, userid ASC
                """
            ).fetchall()
        )
    except Exception:
        pass
    seen: set[str] = set()
    candidates: list[dict[str, Any]] = []
    for row in rows:
        owner_staff_id = _normalized_text(row.get("owner_staff_id"))
        if not owner_staff_id or owner_staff_id in seen:
            continue
        seen.add(owner_staff_id)
        display_name = _normalized_text(row.get("display_name")) or owner_staff_id
        candidates.append(
            {
                "owner_staff_id": owner_staff_id,
                "display_name": display_name,
                "position": _normalized_text(row.get("position")),
                "source": _normalized_text(row.get("source")),
            }
        )
    return candidates


def _owner_from_basic_payload(payload: dict[str, Any]) -> dict[str, str]:
    owner_staff_id = _normalized_text(payload.get("owner_staff_id") or payload.get("owner_userid"))
    owner_display_name = _normalized_text(payload.get("owner_display_name") or payload.get("owner_name")) or owner_staff_id
    if not owner_staff_id:
        return {"owner_staff_id": "", "owner_display_name": ""}
    return {"owner_staff_id": owner_staff_id, "owner_display_name": owner_display_name}


def _program_owner_payload(program_id: int, blocks: dict[str, dict[str, Any]] | None = None) -> dict[str, str]:
    source_blocks = blocks if blocks is not None else _blocks_by_key(int(program_id))
    return _owner_from_basic_payload(_payload_from_block(source_blocks, BLOCK_BASIC))


def _list_available_questionnaires() -> list[dict[str, Any]]:
    try:
        rows = get_db().execute(
            """
            SELECT
                q.id,
                q.title,
                q.name,
                q.slug,
                q.is_disabled,
                COUNT(qq.id) AS question_count
            FROM questionnaires q
            LEFT JOIN questionnaire_questions qq ON qq.questionnaire_id = q.id
            GROUP BY q.id, q.title, q.name, q.slug, q.is_disabled
            ORDER BY q.updated_at DESC, q.id DESC
            LIMIT 80
            """
        ).fetchall()
    except Exception:
        return []
    return [
        {
            "id": int(row["id"]),
            "title": _normalized_text(row["title"]) or _normalized_text(row["name"]) or _normalized_text(row["slug"]),
            "name": _normalized_text(row["name"]),
            "slug": _normalized_text(row["slug"]),
            "status": "停用" if row["is_disabled"] else "启用",
            "is_disabled": bool(row["is_disabled"]),
            "question_count": int(row["question_count"] or 0),
        }
        for row in rows
    ]


def _selected_questionnaire(questionnaire_id: int | None, available: list[dict[str, Any]]) -> dict[str, Any]:
    normalized_id = int(questionnaire_id or 0)
    if not normalized_id:
        return {}
    for item in available:
        if int(item.get("id") or 0) == normalized_id:
            return dict(item)
    try:
        row = get_db().execute(
            """
            SELECT q.id, q.title, q.name, q.slug, q.is_disabled, COUNT(qq.id) AS question_count
            FROM questionnaires q
            LEFT JOIN questionnaire_questions qq ON qq.questionnaire_id = q.id
            WHERE q.id = ?
            GROUP BY q.id, q.title, q.name, q.slug, q.is_disabled
            """,
            (normalized_id,),
        ).fetchone()
    except Exception:
        row = None
    if not row:
        return {"id": normalized_id, "title": f"问卷 {normalized_id}", "status": "未找到", "question_count": 0}
    return {
        "id": int(row["id"]),
        "title": _normalized_text(row["title"]) or _normalized_text(row["name"]) or _normalized_text(row["slug"]),
        "status": "停用" if row["is_disabled"] else "启用",
        "question_count": int(row["question_count"] or 0),
    }


def _money_text(amount_total: Any, currency: str = "CNY") -> str:
    try:
        cents = int(amount_total or 0)
    except (TypeError, ValueError):
        cents = 0
    prefix = "¥" if (_normalized_text(currency) or "CNY").upper() == "CNY" else ""
    return f"{prefix}{cents / 100:.2f}" if cents else f"{prefix}0.00"


def _available_products() -> list[dict[str, Any]]:
    try:
        products = list_wechat_pay_products()
    except Exception:
        products = []
    return [
        {
            "id": _normalized_text(item.get("product_code") or item.get("id")),
            "name": _normalized_text(item.get("name") or item.get("title") or item.get("description")),
            "price_text": _money_text(item.get("amount_total"), _normalized_text(item.get("currency")) or "CNY"),
        }
        for item in products
        if _normalized_text(item.get("product_code") or item.get("id"))
    ]


def _selected_product_snapshot(product_id: Any, provided: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized_id = _normalized_text(product_id)
    provided_snapshot = dict(provided or {})
    if normalized_id:
        for item in _available_products():
            if _normalized_text(item.get("id")) == normalized_id:
                return {"name": _normalized_text(item.get("name")), "price_text": _normalized_text(item.get("price_text"))}
    return {
        "name": _normalized_text(provided_snapshot.get("name")),
        "price_text": _normalized_text(provided_snapshot.get("price_text")),
    }


def _selected_questionnaire_snapshot(questionnaire_id: Any, available: list[dict[str, Any]] | None = None, provided: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized_id = int(questionnaire_id or 0)
    if normalized_id:
        selected = _selected_questionnaire(normalized_id, list(available or _list_available_questionnaires()))
        if selected:
            return {"title": _normalized_text(selected.get("title"))}
    provided_snapshot = dict(provided or {})
    return {"title": _normalized_text(provided_snapshot.get("title"))}


def _questionnaire_questions(questionnaire_id: int | None) -> list[dict[str, Any]]:
    normalized_id = int(questionnaire_id or 0)
    if not normalized_id:
        return []
    try:
        question_rows = get_db().execute(
            """
            SELECT id, title, type, sort_order
            FROM questionnaire_questions
            WHERE questionnaire_id = ?
            ORDER BY sort_order ASC, id ASC
            """,
            (normalized_id,),
        ).fetchall()
        option_rows = get_db().execute(
            """
            SELECT o.id, o.question_id, o.option_text, o.sort_order
            FROM questionnaire_options o
            JOIN questionnaire_questions q ON q.id = o.question_id
            WHERE q.questionnaire_id = ?
            ORDER BY q.sort_order ASC, o.sort_order ASC, o.id ASC
            """,
            (normalized_id,),
        ).fetchall()
    except Exception:
        return []
    options_by_question: dict[int, list[dict[str, Any]]] = {}
    for row in option_rows:
        options_by_question.setdefault(int(row["question_id"]), []).append(
            {"id": int(row["id"]), "option_text": _normalized_text(row["option_text"])}
        )
    questions: list[dict[str, Any]] = []
    for row in question_rows:
        question_type = _normalized_text(row["type"])
        if question_type not in QUESTION_CHOICE_TYPES:
            continue
        question_id = int(row["id"])
        options = options_by_question.get(question_id, [])
        if not options:
            continue
        questions.append({
            "id": int(row["id"]),
            "title": _normalized_text(row["title"]),
            "question_type": question_type,
            "sort_order": int(row["sort_order"] or 0),
            "options": options,
        })
    return questions


def _normalize_normal_rule_row(item: dict[str, Any], *, index: int = 0) -> dict[str, Any]:
    hit_option_ids = item.get("hit_option_ids_json")
    if hit_option_ids is None:
        hit_option_ids = item.get("hit_option_ids") or []
    return {
        "questionnaire_id": int(item.get("questionnaire_id") or 0) or None,
        "questionnaire_question_id": int(item.get("questionnaire_question_id") or item.get("question_id") or 0) or None,
        "question_title": _normalized_text(item.get("question_title")),
        "question_type": _normalized_text(item.get("question_type")) or "single_choice",
        "hit_option_ids_json": [int(value) for value in list(hit_option_ids or []) if str(value).strip().isdigit()],
        "hit_options": list(item.get("hit_options") or []),
        "segment_key": _normalized_text(item.get("segment_key")) or _normalized_text(item.get("hit_segment_key")) or "core",
        "segment_name": _normalized_text(item.get("segment_name")) or _normalized_text(item.get("hit_segment_name")) or "重点",
        "rule_note": _normalized_text(item.get("rule_note") or item.get("description")),
        "sort_order": int(item.get("sort_order") or index + 1),
    }


def _normalize_score_range_row(item: dict[str, Any], *, index: int = 0) -> dict[str, Any]:
    return {
        "min_score": item.get("min_score"),
        "max_score": item.get("max_score"),
        "segment_key": _normalized_text(item.get("segment_key")) or f"score_segment_{index + 1}",
        "segment_name": _normalized_text(item.get("segment_name")) or f"分层 {index + 1}",
        "diagnosis_text": _normalized_text(item.get("diagnosis_text")),
        "recommended_action": _normalized_text(item.get("recommended_action")),
    }


def _category_key_for_index(index: int) -> str:
    if 0 <= index < 26:
        return f"category_{chr(ord('a') + index)}"
    return f"category_{index + 1}"


def _question_option_lookup(question_rows: list[dict[str, Any]], question_id: int | None) -> dict[int, dict[str, Any]]:
    normalized_question_id = int(question_id or 0)
    question = next((item for item in question_rows if int(item.get("id") or 0) == normalized_question_id), {})
    return {int(option.get("id") or 0): dict(option) for option in list(question.get("options") or []) if int(option.get("id") or 0)}


def _normalize_option_category_row(item: dict[str, Any], *, option_lookup: dict[int, dict[str, Any]], index: int = 0) -> dict[str, Any]:
    raw_option_ids = item.get("option_ids") or []
    if isinstance(raw_option_ids, str):
        raw_option_ids = [value.strip() for value in raw_option_ids.split(",")]
    option_ids = []
    for value in list(raw_option_ids or []):
        try:
            option_id = int(value)
        except (TypeError, ValueError):
            continue
        if option_id:
            option_ids.append(option_id)
    snapshots_by_id = {
        int(snapshot.get("id") or 0): dict(snapshot)
        for snapshot in list(item.get("option_snapshots") or [])
        if int(snapshot.get("id") or 0)
    }
    option_snapshots = []
    for option_id in option_ids:
        option = option_lookup.get(option_id) or snapshots_by_id.get(option_id) or {}
        option_snapshots.append(
            {
                "id": option_id,
                "option_text": _normalized_text(option.get("option_text")) or f"选项 {option_id}",
            }
        )
    return {
        "category_key": _normalized_text(item.get("category_key")) or _category_key_for_index(index),
        "category_name": _normalized_text(item.get("category_name")) or f"分类 {index + 1}",
        "description": _normalized_text(item.get("description")),
        "option_ids": option_ids,
        "option_snapshots": option_snapshots,
    }


def _profile_templates_payload(program_id: int) -> list[dict[str, Any]]:
    try:
        payload = list_conversion_profile_segment_templates(enabled_only=False, program_id=int(program_id))
    except Exception:
        return []
    items = []
    for bundle in payload.get("items") or []:
        template = dict(bundle.get("template") or bundle or {})
        items.append(
            {
                "id": int(template.get("id") or 0),
                "template_name": _normalized_text(template.get("template_name")),
                "template_code": _normalized_text(template.get("template_code")),
                "enabled": bool(template.get("enabled", True)),
            }
        )
    return [item for item in items if item["id"]]


def _normalize_segmentation_payload(payload: dict[str, Any], *, program_id: int) -> dict[str, Any]:
    strategies = dict(payload.get("strategies") or {})
    normal = dict(strategies.get("normal_question_rules") or {})
    score = dict(strategies.get("score_segments") or {})
    profile = dict(strategies.get("profile_dimension") or {})
    questionnaire_id = int(payload.get("questionnaire_id") or 0) or None
    question_rows = _questionnaire_questions(questionnaire_id)
    normal_rows = payload.get("normal_question_rules_rows")
    if normal_rows is None:
        normal_rows = normal.get("rules") or []
    category_rows = payload.get("normal_question_categories")
    if category_rows is None:
        category_rows = normal.get("categories") or []
    segmentation_question_id = (
        int(payload.get("segmentation_question_id") or normal.get("segmentation_question_id") or 0)
        or (int(question_rows[0]["id"]) if question_rows else None)
    )
    selected_question = next((item for item in question_rows if int(item.get("id") or 0) == int(segmentation_question_id or 0)), {})
    option_lookup = _question_option_lookup(question_rows, segmentation_question_id)
    normal_mode = (
        _normalized_text(payload.get("normal_question_mode"))
        or _normalized_text(normal.get("mode"))
        or (QUESTION_OPTION_CATEGORY_MODE if category_rows or segmentation_question_id else "legacy_hit_rules")
    )
    score_rows = payload.get("score_segment_rows")
    if score_rows is None:
        score_rows = score.get("ranges") or []
    return {
        "questionnaire_id": questionnaire_id,
        "default_strategy": _normalized_text(payload.get("default_strategy")) or "normal_question_rules",
        "strategies": {
            "normal_question_rules": {
                "enabled": bool(normal.get("enabled", payload.get("default_strategy") != "manual")),
                "mode": normal_mode,
                "segmentation_question_id": segmentation_question_id,
                "segmentation_question_title": _normalized_text(selected_question.get("title")),
                "categories": [
                    _normalize_option_category_row(dict(item or {}), option_lookup=option_lookup, index=index)
                    for index, item in enumerate(list(category_rows or []))
                ],
                "core_threshold": int(normal.get("core_threshold") or payload.get("core_threshold") or 2),
                "rules": [
                    _normalize_normal_rule_row(dict(item or {}), index=index)
                    for index, item in enumerate(list(normal_rows or []))
                ],
            },
            "score_segments": {
                "enabled": bool(score.get("enabled", False)),
                "ranges": [
                    _normalize_score_range_row(dict(item or {}), index=index)
                    for index, item in enumerate(list(score_rows or []))
                ],
            },
            "profile_dimension": {
                "enabled": bool(profile.get("enabled", False)),
                "template_id": int(profile.get("template_id") or payload.get("profile_template_id") or 0) or None,
                "usage": _normalized_text(profile.get("usage")) or "content_variable_only",
            },
        },
        "priority": list(payload.get("priority") or ["normal_question_rules", "score_segments"]),
    }


def _segmentation_view_model(payload: dict[str, Any], *, program_id: int) -> dict[str, Any]:
    normalized = _normalize_segmentation_payload(payload, program_id=int(program_id)) if payload else {
        "questionnaire_id": None,
        "default_strategy": "normal_question_rules",
        "strategies": {
            "normal_question_rules": {
                "enabled": True,
                "mode": QUESTION_OPTION_CATEGORY_MODE,
                "core_threshold": 2,
                "rules": [],
                "categories": [],
                "segmentation_question_id": None,
                "segmentation_question_title": "",
            },
            "score_segments": {"enabled": False, "ranges": []},
            "profile_dimension": {"enabled": False, "template_id": None, "usage": "content_variable_only"},
        },
        "priority": ["normal_question_rules", "score_segments"],
    }
    available = _list_available_questionnaires()
    questionnaire_id = normalized.get("questionnaire_id")
    question_rows = _questionnaire_questions(questionnaire_id)
    selected_questionnaire = _selected_questionnaire(questionnaire_id, available)
    if selected_questionnaire:
        selected_questionnaire["questions"] = question_rows
    normal_strategy = dict(normalized["strategies"]["normal_question_rules"])
    selected_question_id = int(normal_strategy.get("segmentation_question_id") or 0) or (int(question_rows[0]["id"]) if question_rows else None)
    selected_question = next((item for item in question_rows if int(item.get("id") or 0) == int(selected_question_id or 0)), {})
    assigned_option_ids = {
        int(option_id)
        for category in list(normal_strategy.get("categories") or [])
        for option_id in list(category.get("option_ids") or [])
        if int(option_id or 0)
    }
    unassigned_options = [
        dict(option)
        for option in list(selected_question.get("options") or [])
        if int(option.get("id") or 0) not in assigned_option_ids
    ]
    normal_view = {
        "mode": _normalized_text(normal_strategy.get("mode")) or QUESTION_OPTION_CATEGORY_MODE,
        "core_threshold": int(normal_strategy.get("core_threshold") or 2),
        "segmentation_question_id": selected_question_id,
        "segmentation_question_title": _normalized_text(selected_question.get("title")),
        "selected_question": selected_question,
        "category_rows": list(normal_strategy.get("categories") or []),
        "unassigned_options": unassigned_options,
        "legacy_rows": list(normal_strategy.get("rules") or []),
        "rows": list(normal_strategy.get("rules") or []),
    }
    segmentation_ui = {
        "available_questionnaires": available,
        "selected_questionnaire": selected_questionnaire,
        "selected_segmentation_question": selected_question,
        "category_rows": normal_view["category_rows"],
        "unassigned_options": unassigned_options,
    }
    return {
        **normalized,
        "available_questionnaires": available,
        "selected_questionnaire": selected_questionnaire,
        "question_rows": question_rows,
        "segmentation_ui": segmentation_ui,
        "normal_question_rules": normal_view,
        "score_segments": {
            "enabled": bool((normalized["strategies"]["score_segments"]).get("enabled")),
            "rows": list((normalized["strategies"]["score_segments"]).get("ranges") or []),
        },
        "profile_dimension": {
            **dict(normalized["strategies"]["profile_dimension"]),
            "available_templates": _profile_templates_payload(int(program_id)),
        },
    }


def _legacy_rules_from_entry_rule(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rules = list((payload or {}).get("rules") or [])
    if rules:
        return rules
    normalized = _normalize_audience_entry_rule_payload(payload, validate=False)
    order_enabled = bool((normalized.get("order_review") or {}).get("enabled"))
    questionnaire_enabled = bool((normalized.get("questionnaire_review") or {}).get("enabled"))
    return [
        {
            "event": "channel_enter",
            "condition_type": "any_entry_channel",
            "target_audience_code": "pending_questionnaire" if order_enabled or questionnaire_enabled else "operating",
            "enabled": True,
        },
        {
            "event": "questionnaire_submitted",
            "condition_type": "questionnaire_id_matched",
            "target_audience_code": "operating",
            "enabled": questionnaire_enabled,
        },
    ]


def _normalize_audience_review_item(
    item: dict[str, Any],
    *,
    enabled_default: bool,
    product: bool = False,
    questionnaire: bool = False,
    available_questionnaires: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    enabled = bool(item.get("enabled", enabled_default))
    result: dict[str, Any] = {"enabled": enabled}
    if product:
        selected_product_id = _normalized_text(item.get("selected_product_id") or item.get("product_id"))
        result["selected_product_id"] = selected_product_id or None
        result["selected_product_snapshot"] = _selected_product_snapshot(
            selected_product_id,
            item.get("selected_product_snapshot") if isinstance(item.get("selected_product_snapshot"), dict) else {},
        )
    if questionnaire:
        selected_questionnaire_id = int(item.get("selected_questionnaire_id") or item.get("questionnaire_id") or 0) or None
        result["selected_questionnaire_id"] = selected_questionnaire_id
        result["selected_questionnaire_snapshot"] = _selected_questionnaire_snapshot(
            selected_questionnaire_id,
            available=available_questionnaires,
            provided=item.get("selected_questionnaire_snapshot") if isinstance(item.get("selected_questionnaire_snapshot"), dict) else {},
        )
    return result


def _normalize_audience_entry_rule_payload(payload: dict[str, Any], *, validate: bool = True) -> dict[str, Any]:
    payload = dict(payload or {})
    available_questionnaires = _list_available_questionnaires()
    has_v5_review_config = any(
        key in payload
        for key in ("entry_source", "order_review", "questionnaire_review", "operating", "conversion_review")
    )
    if not has_v5_review_config and (payload.get("cards") or payload.get("rules")):
        rules = list(payload.get("rules") or [])
        if payload.get("cards"):
            cards = dict(payload.get("cards") or {})
            submit_card = dict(cards.get("questionnaire_submitted") or {})
            questionnaire_enabled = bool(submit_card.get("enabled", True))
            selected_questionnaire_id = int(payload.get("selected_questionnaire_id") or 0) or None
        else:
            by_event = {str(item.get("event") or ""): dict(item or {}) for item in rules}
            submit_rule = by_event.get("questionnaire_submitted") or DEFAULT_AUDIENCE_ENTRY_RULES[1]
            questionnaire_enabled = bool(submit_rule.get("enabled", True))
            selected_questionnaire_id = int(payload.get("selected_questionnaire_id") or 0) or None
        normalized = {
            "entry_source": "both",
            "order_review": _normalize_audience_review_item({}, enabled_default=False, product=True),
            "questionnaire_review": _normalize_audience_review_item(
                {"enabled": questionnaire_enabled, "selected_questionnaire_id": selected_questionnaire_id},
                enabled_default=questionnaire_enabled,
                questionnaire=True,
                available_questionnaires=available_questionnaires,
            ),
            "operating": {"enabled": True, "fixed": True},
            "conversion_review": _normalize_audience_review_item({}, enabled_default=False, product=True),
            "rules": rules or DEFAULT_AUDIENCE_ENTRY_RULES,
        }
    else:
        normalized = {
            "entry_source": _normalized_text(payload.get("entry_source")) or "both",
            "order_review": _normalize_audience_review_item(
                dict(payload.get("order_review") or {}),
                enabled_default=False,
                product=True,
            ),
            "questionnaire_review": _normalize_audience_review_item(
                dict(payload.get("questionnaire_review") or {}),
                enabled_default=False,
                questionnaire=True,
                available_questionnaires=available_questionnaires,
            ),
            "operating": {"enabled": True, "fixed": True},
            "conversion_review": _normalize_audience_review_item(
                dict(payload.get("conversion_review") or {}),
                enabled_default=False,
                product=True,
            ),
        }
    if validate:
        order_review = dict(normalized.get("order_review") or {})
        questionnaire_review = dict(normalized.get("questionnaire_review") or {})
        conversion_review = dict(normalized.get("conversion_review") or {})
        if order_review.get("enabled") and not _normalized_text(order_review.get("selected_product_id")):
            raise ValueError("订单审核已启用，请先选择商品")
        if questionnaire_review.get("enabled") and not int(questionnaire_review.get("selected_questionnaire_id") or 0):
            raise ValueError("问卷审核已启用，请先选择问卷")
        if conversion_review.get("enabled") and not _normalized_text(conversion_review.get("selected_product_id")):
            raise ValueError("已转化判定已启用，请先选择成交商品")
    return normalized


def _audience_next_steps(payload: dict[str, Any]) -> dict[str, str]:
    order_enabled = bool((payload.get("order_review") or {}).get("enabled"))
    questionnaire_enabled = bool((payload.get("questionnaire_review") or {}).get("enabled"))
    conversion_enabled = bool((payload.get("conversion_review") or {}).get("enabled"))
    scan_next = "订单审核" if order_enabled else ("问卷审核" if questionnaire_enabled else "运营中")
    return {
        "scan_enter": scan_next,
        "order_review": ("问卷审核" if questionnaire_enabled else "运营中") if order_enabled else "本项已跳过",
        "questionnaire_review": "运营中" if questionnaire_enabled else "本项已跳过",
        "operating": "已转化" if conversion_enabled else "结束",
        "conversion_review": "结束" if conversion_enabled else "本项已关闭",
    }


def _audience_rule_view_model(payload: dict[str, Any], *, program_id: int, picker: str = "") -> dict[str, Any]:
    normalized_payload = _normalize_audience_entry_rule_payload(payload or {}, validate=False)
    available_questionnaires = _list_available_questionnaires()
    available_products = _available_products()
    picker_key = _normalized_text(picker)
    if picker_key not in AUDIENCE_REVIEW_STEP_KEYS:
        picker_key = ""
    return {
        **normalized_payload,
        "rules": _legacy_rules_from_entry_rule(normalized_payload),
        "next_steps": _audience_next_steps(normalized_payload),
        "available_products": available_products,
        "available_questionnaires": available_questionnaires,
        "picker": picker_key,
        "picker_title": {
            "order_product": "选择订单审核商品",
            "questionnaire": "选择问卷审核问卷",
            "conversion_product": "选择成交判定商品",
        }.get(picker_key, ""),
    }


def _legacy_audience_rule_view_model(payload: dict[str, Any], *, program_id: int) -> dict[str, Any]:
    rules = list((payload or {}).get("rules") or DEFAULT_AUDIENCE_ENTRY_RULES)
    by_event = {str(item.get("event") or ""): dict(item or {}) for item in rules}
    entry_rule = by_event.get("channel_enter") or DEFAULT_AUDIENCE_ENTRY_RULES[0]
    submit_rule = by_event.get("questionnaire_submitted") or DEFAULT_AUDIENCE_ENTRY_RULES[1]
    return {
        "rules": rules,
        "normalized_cards": {
            "channel_enter": {
                "event": "channel_enter",
                "event_label": "入口进入后",
                "condition_type": _normalized_text(entry_rule.get("condition_type") or entry_rule.get("condition")) or "any_entry_channel",
                "condition_options": ENTRY_CONDITION_LABELS,
                "target_audience_code": _normalized_text(entry_rule.get("target_audience_code")) or "pending_questionnaire",
                "target_options": AUDIENCE_LABELS,
                "enabled": bool(entry_rule.get("enabled", True)),
            },
            "questionnaire_submitted": {
                "event": "questionnaire_submitted",
                "event_label": "问卷提交后",
                "condition_type": _normalized_text(submit_rule.get("condition_type") or submit_rule.get("condition")) or "questionnaire_id_matched",
                "condition_options": QUESTIONNAIRE_CONDITION_LABELS,
                "target_audience_code": _normalized_text(submit_rule.get("target_audience_code")) or "operating",
                "target_options": {"operating": "运营中", "converted": "已转化"},
                "enabled": bool(submit_rule.get("enabled", True)),
            },
        },
        "manual_cards": [
            {"event_label": "人工移除", "target_label": "退出当前方案"},
            {"event_label": "成交标记", "target_label": "已转化"},
            {"event_label": "取消成交", "target_label": "运营中"},
        ],
    }


def _program_entry_payload(program_id: int) -> dict[str, Any]:
    channels = repo.list_channels_by_program(int(program_id), include_inactive=True)
    qrcode_channels = [
        item
        for item in channels
        if not _normalized_text(item.get("channel_code")).startswith("wecom_customer_acquisition_")
    ]
    return {
        "channels": channels,
        "qrcode_channel": qrcode_channels[0] if qrcode_channels else {},
        "customer_acquisition_links": list_customer_acquisition_links(program_id=int(program_id)),
        "wecom_tag_catalog": {"items": [], "groups": [], "total_tags": 0, "tag_limit": 0, "synced_at": ""},
    }


def _program_entry_wecom_tag_catalog() -> dict[str, Any]:
    try:
        catalog = tags_domain_service.list_wecom_tag_catalog()
    except Exception:
        return {
            "items": [],
            "groups": [],
            "total_tags": 0,
            "tag_limit": 1000,
            "synced_at": "",
            "error": "企微标签加载失败，请先同步企微标签或检查企微配置。",
        }
    groups: list[dict[str, Any]] = []
    for group in list(catalog.get("groups") or []):
        tags = [
            {
                "tag_id": _normalized_text(tag.get("tag_id")),
                "tag_name": _normalized_text(tag.get("tag_name")),
                "group_id": _normalized_text(tag.get("group_id")),
                "group_name": _normalized_text(tag.get("group_name")),
            }
            for tag in list(group.get("tags") or [])
            if _normalized_text(tag.get("tag_id")) and _normalized_text(tag.get("tag_name"))
        ]
        if not tags:
            continue
        groups.append(
            {
                "group_id": _normalized_text(group.get("group_id")),
                "group_name": _normalized_text(group.get("group_name")) or "未命名标签组",
                "tags": tags,
            }
        )
    items = [
        {
            "tag_id": _normalized_text(item.get("tag_id")),
            "tag_name": _normalized_text(item.get("tag_name")),
            "group_id": _normalized_text(item.get("group_id")),
            "group_name": _normalized_text(item.get("group_name")),
        }
        for item in list(catalog.get("items") or [])
        if _normalized_text(item.get("tag_id")) and _normalized_text(item.get("tag_name"))
    ]
    return {
        "items": items,
        "groups": groups,
        "total_tags": int(catalog.get("total_tags") or len(items)),
        "tag_limit": int(catalog.get("tag_limit") or 1000),
        "synced_at": _normalized_text(catalog.get("synced_at")),
        "error": "",
    }


def get_program_setup_payload(program_id: int, *, step: str = "basic", audience_picker: str = "") -> dict[str, Any]:
    program = get_automation_program(int(program_id))
    blocks = _blocks_by_key(int(program_id))
    segmentation = _payload_from_block(blocks, BLOCK_SEGMENTATION)
    legacy_fallback_used = False
    if not segmentation and _is_default_program(int(program_id)):
        segmentation = _legacy_segmentation_payload()
        legacy_fallback_used = True
    segmentation_view = _segmentation_view_model(segmentation, program_id=int(program_id))
    audience_payload = _payload_from_block(blocks, BLOCK_AUDIENCE_ENTRY_RULE)
    operations = list_operation_tasks(program_id=int(program_id))
    return {
        "program": program,
        "step": normalize_setup_step(step),
        "steps": [{"key": key, "label": label} for key, label in SETUP_STEPS],
        "is_default_program": _is_default_program(int(program_id)),
        "legacy_fallback_used": legacy_fallback_used,
        "blocks": blocks,
        "basic": _payload_from_block(blocks, BLOCK_BASIC),
        "owner_candidates": _list_owner_candidates(),
        "program_owner": _program_owner_payload(int(program_id), blocks),
        "entry_channel": _payload_from_block(blocks, BLOCK_ENTRY_CHANNEL),
        "entry": _program_entry_payload(int(program_id)),
        "segmentation": segmentation_view,
        "audience_entry_rule": _audience_rule_view_model(
            audience_payload,
            program_id=int(program_id),
            picker=audience_picker,
        ),
        "operations": {"tasks": [dict(item or {}) for item in operations.get("tasks") or []]},
        "publish_state": _payload_from_block(blocks, BLOCK_PUBLISH_STATE),
        "publish_check": build_publish_check(program_id),
    }


def normalize_setup_step(step: str) -> str:
    allowed = {key for key, _ in SETUP_STEPS}
    normalized = _normalized_text(step) or "basic"
    return normalized if normalized in allowed else "basic"


def save_setup_basic(program_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    existing = get_automation_program(int(program_id))
    existing_basic = program_repo.get_config_block_row(int(program_id), BLOCK_BASIC) or {}
    existing_basic_payload = dict(existing_basic.get("payload_json") or {})
    name = _normalized_text(payload.get("program_name")) or _normalized_text(existing.get("program_name"))
    code = _program_code(payload.get("program_code")) or _program_code(existing.get("program_code"))
    if not name:
        raise ValueError("方案名称不能为空")
    if not code:
        raise ValueError("方案编码不能为空")
    duplicate = program_repo.get_program_row_by_code(code)
    if duplicate and int(duplicate.get("id") or 0) != int(program_id):
        raise ValueError("方案编码已存在")
    status = _normalized_text(payload.get("status")) or _normalized_text(existing.get("status")) or "draft"
    if status not in {"draft", "active", "paused", "archived"}:
        raise ValueError("方案状态不正确")
    owner = _owner_from_basic_payload(payload)
    if not owner.get("owner_staff_id"):
        owner = _owner_from_basic_payload(existing_basic_payload)
    program = program_repo.update_program_row(
        int(program_id),
        {
            "program_code": code,
            "program_name": name,
            "description": _normalized_text(payload.get("description")),
            "status": status,
            "config_json": dict(existing.get("config_json") or {}),
            "updated_by": operator_id,
        },
    )
    block = program_repo.upsert_config_block_row(
        int(program_id),
        BLOCK_BASIC,
        {
            "program_name": name,
            "program_code": code,
            "description": _normalized_text(payload.get("description")),
            "status": status,
            "creation_mode": _normalized_text(payload.get("creation_mode")) or _normalized_text(existing_basic_payload.get("creation_mode")) or "blank",
            "copied_from_program_id": existing_basic_payload.get("copied_from_program_id"),
            "owner_staff_id": owner["owner_staff_id"],
            "owner_display_name": owner["owner_display_name"],
            "owner_snapshot": owner,
        },
        status="saved",
    )
    get_db().commit()
    return {"program": program, "block": block}


def save_entry_channel(program_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    owner = _owner_from_basic_payload(payload) or _program_owner_payload(int(program_id))
    if not owner.get("owner_staff_id"):
        owner = _program_owner_payload(int(program_id))
    channel_payload = {
        "program_id": int(program_id),
        "channel_name": _normalized_text(payload.get("channel_name")),
        "welcome_message": _normalized_text(payload.get("welcome_message")),
        "auto_accept_friend": bool(payload.get("auto_accept_friend")),
        "entry_tag_id": _normalized_text(payload.get("entry_tag_id")),
        "entry_tag_name": _normalized_text(payload.get("entry_tag_name")),
        "entry_tag_group_name": _normalized_text(payload.get("entry_tag_group_name")),
        "owner_staff_id": owner.get("owner_staff_id") or "",
        "owner_display_name": owner.get("owner_display_name") or "",
    }
    channel_result = save_default_channel_settings(channel_payload, program_id=int(program_id))
    block = program_repo.upsert_config_block_row(
        int(program_id),
        BLOCK_ENTRY_CHANNEL,
        {"qrcode": channel_payload},
        status="saved",
    )
    get_db().commit()
    return {"entry_channel": channel_result, "block": block}


def create_program_customer_acquisition_link(program_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    result = create_customer_acquisition_link({**dict(payload or {}), "program_id": int(program_id)})
    existing = program_repo.get_config_block_row(int(program_id), BLOCK_ENTRY_CHANNEL)
    entry_payload = dict((existing or {}).get("payload_json") or {})
    link_ids = list(entry_payload.get("customer_acquisition_link_ids") or [])
    link_id = int((result.get("link") or {}).get("id") or 0)
    if link_id and link_id not in link_ids:
        link_ids.append(link_id)
    entry_payload["customer_acquisition_link_ids"] = link_ids
    block = program_repo.upsert_config_block_row(int(program_id), BLOCK_ENTRY_CHANNEL, entry_payload, status="saved")
    get_db().commit()
    return {**result, "block": block}


def _score_ranges(payload: dict[str, Any]) -> list[dict[str, Any]]:
    strategies = dict(payload.get("strategies") or {})
    score_segments = dict(strategies.get("score_segments") or {})
    return [dict(item or {}) for item in list(score_segments.get("ranges") or [])]


def validate_score_ranges(payload: dict[str, Any]) -> None:
    ranges = []
    for item in _score_ranges(payload):
        min_score = item.get("min_score")
        max_score = item.get("max_score")
        if min_score is None or max_score is None:
            raise ValueError("总分分层区间必须填写最低分和最高分")
        min_value = float(min_score)
        max_value = float(max_score)
        if min_value > max_value:
            raise ValueError("总分分层区间最低分不能大于最高分")
        ranges.append((min_value, max_value, _normalized_text(item.get("segment_name"))))
    ranges.sort(key=lambda item: (item[0], item[1]))
    for previous, current in zip(ranges, ranges[1:]):
        if current[0] <= previous[1]:
            raise ValueError("总分分层区间不能重叠")


def validate_option_categories(payload: dict[str, Any]) -> None:
    if _normalized_text(payload.get("default_strategy")) != "normal_question_rules":
        return
    strategies = dict(payload.get("strategies") or {})
    normal = dict(strategies.get("normal_question_rules") or {})
    if not normal.get("enabled", True):
        return
    if _normalized_text(normal.get("mode")) not in {"", QUESTION_OPTION_CATEGORY_MODE}:
        return
    if not int(payload.get("questionnaire_id") or 0):
        raise ValueError("请先选择问卷")
    if not int(normal.get("segmentation_question_id") or 0):
        raise ValueError("请先选择分层题目")
    question_rows = _questionnaire_questions(int(payload.get("questionnaire_id") or 0))
    valid_option_ids = set(_question_option_lookup(question_rows, int(normal.get("segmentation_question_id") or 0)).keys())
    if not valid_option_ids:
        raise ValueError("当前分层题目没有可用选项")
    categories = list(normal.get("categories") or [])
    if not categories:
        raise ValueError("启用普通问卷选项分类时，至少需要一个分类")
    seen: dict[int, str] = {}
    for category in categories:
        category_name = _normalized_text(category.get("category_name"))
        option_ids = [int(option_id) for option_id in list(category.get("option_ids") or []) if int(option_id or 0)]
        if not category_name:
            raise ValueError("分类名称不能为空")
        if not option_ids:
            raise ValueError("每个分类至少需要选择一个选项")
        for option_id in option_ids:
            if option_id not in valid_option_ids:
                raise ValueError("分类选项不属于当前分层题目")
            if option_id in seen:
                raise ValueError("同一个选项不能同时属于多个分类")
            seen[option_id] = category_name


def match_score_segment(payload: dict[str, Any], total_score: float) -> dict[str, Any] | None:
    for item in _score_ranges(payload):
        min_score = float(item.get("min_score"))
        max_score = float(item.get("max_score"))
        if min_score <= float(total_score) <= max_score:
            return item
    return None


def _setup_profile_template_code(program_id: int) -> str:
    return f"{SETUP_PROFILE_TEMPLATE_CODE_PREFIX}_{int(program_id)}"


def _setup_profile_template_categories(payload: dict[str, Any]) -> list[dict[str, Any]]:
    strategies = dict(payload.get("strategies") or {})
    normal = dict(strategies.get("normal_question_rules") or {})
    categories: list[dict[str, Any]] = []
    for index, category in enumerate(list(normal.get("categories") or []), start=1):
        option_ids = [int(option_id) for option_id in list(category.get("option_ids") or []) if int(option_id or 0)]
        if not option_ids:
            continue
        categories.append(
            {
                "category_key": _normalized_text(category.get("category_key")) or _category_key_for_index(index - 1),
                "category_name": _normalized_text(category.get("category_name")) or f"分类 {index}",
                "description": _normalized_text(category.get("description")),
                "sort_order": index,
                "enabled": True,
                "option_ids": option_ids,
            }
        )
    return categories


def _sync_setup_profile_template_categories(template_id: int, question_id: int, categories: list[dict[str, Any]]) -> None:
    workflow_repo.delete_profile_segment_option_mapping_rows(int(template_id))
    workflow_repo.delete_profile_segment_category_rows(int(template_id))
    for category in categories:
        saved_category = workflow_repo.insert_profile_segment_category_row(
            {
                "template_id": int(template_id),
                "category_key": category["category_key"],
                "category_name": category["category_name"],
                "description": category["description"],
                "sort_order": category["sort_order"],
                "enabled": category["enabled"],
            }
        )
        for option_id in category["option_ids"]:
            workflow_repo.insert_profile_segment_option_mapping_row(
                {
                    "template_id": int(template_id),
                    "category_id": int(saved_category["id"]),
                    "question_id": int(question_id),
                    "option_id": int(option_id),
                }
            )


def _sync_setup_profile_segment_template(program_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
    template_code = _setup_profile_template_code(int(program_id))
    existing = workflow_repo.get_profile_segment_template_row_by_code(template_code)
    strategies = dict(payload.get("strategies") or {})
    normal = dict(strategies.get("normal_question_rules") or {})
    should_enable = (
        _normalized_text(payload.get("default_strategy")) == "normal_question_rules"
        and bool(normal.get("enabled", True))
        and _normalized_text(normal.get("mode")) in {"", QUESTION_OPTION_CATEGORY_MODE}
    )
    categories = _setup_profile_template_categories(payload) if should_enable else []
    questionnaire_id = int(payload.get("questionnaire_id") or 0)
    question_id = int(normal.get("segmentation_question_id") or 0)
    if not should_enable or not questionnaire_id or not question_id or not categories:
        if existing and int(existing.get("program_id") or 0) == int(program_id) and bool(existing.get("enabled")):
            return workflow_repo.update_profile_segment_template_row(
                int(existing["id"]),
                {
                    **existing,
                    "program_id": int(program_id),
                    "enabled": False,
                    "version": int(existing.get("version") or 1) + 1,
                    "updated_by": "setup_wizard",
                },
            )
        return existing

    selected_question_title = _normalized_text(normal.get("segmentation_question_title"))
    template_name = selected_question_title or "普通问卷选项分类"
    template_payload = {
        "program_id": int(program_id),
        "template_code": template_code,
        "template_name": f"{template_name} · 自然画像",
        "questionnaire_id": questionnaire_id,
        "segmentation_question_id": question_id,
        "description": "由配置向导的普通问卷选项分类自动同步。",
        "enabled": True,
        "version": int((existing or {}).get("version") or 0) + 1,
        "created_by": "setup_wizard",
        "updated_by": "setup_wizard",
    }
    if existing:
        if int(existing.get("program_id") or 0) not in {0, int(program_id)}:
            raise ValueError("当前方案画像分层模板编码已被其他方案占用")
        saved_template = workflow_repo.update_profile_segment_template_row(int(existing["id"]), template_payload)
    else:
        saved_template = workflow_repo.insert_profile_segment_template_row(template_payload)
    _sync_setup_profile_template_categories(int(saved_template["id"]), question_id, categories)
    return saved_template


def save_segmentation(program_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    payload = _normalize_segmentation_payload(dict(payload or {}), program_id=int(program_id))
    validate_option_categories(payload)
    validate_score_ranges(payload)
    profile_template = _sync_setup_profile_segment_template(int(program_id), payload)
    block = program_repo.upsert_config_block_row(
        int(program_id),
        BLOCK_SEGMENTATION,
        dict(payload or {}),
        status="saved",
    )
    get_db().commit()
    return {"segmentation": block, "profile_segment_template": profile_template}


def save_audience_entry_rule(program_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload or {})
    allow_incomplete = bool(payload.pop("_allow_incomplete", False))
    is_legacy_payload = bool(payload.get("cards") or payload.get("rules"))
    normalized = _normalize_audience_entry_rule_payload(payload, validate=not is_legacy_payload and not allow_incomplete)
    rules = _legacy_rules_from_entry_rule(normalized)
    normalized["rules"] = rules
    block = program_repo.upsert_config_block_row(
        int(program_id),
        BLOCK_AUDIENCE_ENTRY_RULE,
        normalized,
        status="saved",
    )
    get_db().commit()
    return {"audience_entry_rule": block}


def _has_entry_channel(program_id: int) -> bool:
    channels = repo.list_channels_by_program(int(program_id), include_inactive=False)
    if any(_normalized_text(item.get("status")) in {"active", "configured"} for item in channels):
        return True
    return any(_normalized_text(item.get("status")) == "active" for item in list_customer_acquisition_links(program_id=int(program_id)))


def _has_segmentation(payload: dict[str, Any]) -> bool:
    strategies = dict(payload.get("strategies") or {})
    normal = dict(strategies.get("normal_question_rules") or {})
    score = dict(strategies.get("score_segments") or {})
    return bool(normal.get("enabled") and (normal.get("categories") or normal.get("rules"))) or bool(score.get("enabled") and score.get("ranges"))


def _audience_rule_check_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    normalized = _normalize_audience_entry_rule_payload(payload or {}, validate=False)
    order_review = dict(normalized.get("order_review") or {})
    questionnaire_review = dict(normalized.get("questionnaire_review") or {})
    conversion_review = dict(normalized.get("conversion_review") or {})
    checks = [
        ("扫码进入必填", True, "请先配置当前方案入口", "entry"),
        ("运营中不可关闭", bool((normalized.get("operating") or {}).get("enabled", True)), "运营中必须保持启用", "entry-rule"),
    ]
    if order_review.get("enabled"):
        checks.append(("订单审核商品已选择", bool(_normalized_text(order_review.get("selected_product_id"))), "请先选择订单审核商品", "entry-rule"))
    if questionnaire_review.get("enabled"):
        checks.append(("问卷审核问卷已选择", bool(int(questionnaire_review.get("selected_questionnaire_id") or 0)), "请先选择问卷审核问卷", "entry-rule"))
    if conversion_review.get("enabled"):
        checks.append(("成交判定商品已选择", bool(_normalized_text(conversion_review.get("selected_product_id"))), "请先选择成交判定商品", "entry-rule"))
    return [
        {
            "label": label,
            "passed": bool(passed),
            "severity": "pass" if passed else "fail",
            "message": message if not passed else "已完成",
            "fix_step": fix_step,
            "fix_url": f"?step={fix_step}",
        }
        for label, passed, message, fix_step in checks
    ]


def _program_id_from_member(member: dict[str, Any]) -> int:
    source_channel_id = int(member.get("source_channel_id") or 0)
    if source_channel_id <= 0:
        return 0
    row = get_db().execute(
        "SELECT program_id FROM automation_channel WHERE id = ? LIMIT 1",
        (source_channel_id,),
    ).fetchone()
    if not row:
        return 0
    try:
        return int(row["program_id"] or 0)
    except (KeyError, TypeError, ValueError):
        return 0


def _member_has_paid_product(member: dict[str, Any], product_id: Any) -> bool:
    product_code = _normalized_text(product_id)
    if not product_code:
        return False
    external_contact_id = _normalized_text(member.get("external_contact_id"))
    phone = _normalized_text(member.get("phone"))
    filters: list[str] = []
    params: list[Any] = [product_code]
    if external_contact_id:
        filters.append("(external_userid = ? OR userid_snapshot = ? OR respondent_key = ?)")
        params.extend([external_contact_id, external_contact_id, external_contact_id])
    if phone:
        filters.append("mobile_snapshot = ?")
        params.append(phone)
    if not filters:
        return False
    row = get_db().execute(
        """
        SELECT id
        FROM wechat_pay_orders
        WHERE product_code = ?
          AND COALESCE(refunded_amount_total, 0) = 0
          AND (COALESCE(status, '') = 'paid' OR COALESCE(trade_state, '') = 'SUCCESS')
          AND (
        """
        + " OR ".join(filters)
        + """
          )
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        tuple(params),
    ).fetchone()
    return bool(row)


def _member_has_questionnaire_submission(
    member: dict[str, Any],
    questionnaire_id: Any,
    questionnaire_state: dict[str, Any] | None = None,
) -> bool:
    normalized_questionnaire_id = int(questionnaire_id or 0)
    if normalized_questionnaire_id <= 0:
        return False
    state = dict(questionnaire_state or {})
    if (
        int(state.get("questionnaire_id") or 0) == normalized_questionnaire_id
        and _normalized_text(state.get("questionnaire_status")) == "submitted"
    ):
        return True
    submission = workflow_repo.get_latest_questionnaire_submission_row(
        questionnaire_id=normalized_questionnaire_id,
        external_contact_ids=[_normalized_text(member.get("external_contact_id"))],
        phone=_normalized_text(member.get("phone")),
    )
    return bool(submission)


def resolve_member_audience_entry_rule_state(
    member: dict[str, Any],
    *,
    questionnaire_state: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    program_id = _program_id_from_member(member)
    if program_id <= 0:
        return None
    payload = _payload_from_block(_blocks_by_key(program_id), BLOCK_AUDIENCE_ENTRY_RULE)
    if not payload or not any(key in payload for key in ("order_review", "questionnaire_review", "conversion_review")):
        return None
    normalized = _normalize_audience_entry_rule_payload(payload, validate=False)
    order_review = dict(normalized.get("order_review") or {})
    questionnaire_review = dict(normalized.get("questionnaire_review") or {})
    conversion_review = dict(normalized.get("conversion_review") or {})

    if order_review.get("enabled") and not _member_has_paid_product(member, order_review.get("selected_product_id")):
        return {
            "program_id": program_id,
            "audience_code": "pending_questionnaire",
            "entry_reason": "order_review_pending",
            "checkpoint": "order_review",
        }
    if questionnaire_review.get("enabled") and not _member_has_questionnaire_submission(
        member,
        questionnaire_review.get("selected_questionnaire_id"),
        questionnaire_state=questionnaire_state,
    ):
        return {
            "program_id": program_id,
            "audience_code": "pending_questionnaire",
            "entry_reason": "questionnaire_review_pending",
            "checkpoint": "questionnaire_review",
        }
    if conversion_review.get("enabled") and _member_has_paid_product(member, conversion_review.get("selected_product_id")):
        return {
            "program_id": program_id,
            "audience_code": "converted",
            "entry_reason": "conversion_product_paid",
            "checkpoint": "conversion_review",
        }
    return {
        "program_id": program_id,
        "audience_code": "operating",
        "entry_reason": "audience_entry_rule_passed",
        "checkpoint": "operating",
    }


def build_publish_check(program_id: int) -> dict[str, Any]:
    program = get_automation_program(int(program_id))
    setup = _blocks_by_key(int(program_id))
    segmentation = _payload_from_block(setup, BLOCK_SEGMENTATION)
    if not segmentation and _is_default_program(int(program_id)):
        segmentation = _legacy_segmentation_payload()
    active_tasks = list_operation_tasks(program_id=int(program_id), status="active")
    audience_payload = _payload_from_block(setup, BLOCK_AUDIENCE_ENTRY_RULE)
    audience_rule_items = _audience_rule_check_items(audience_payload)
    audience_rule_ok = all(bool(item.get("passed")) for item in audience_rule_items)
    entry_ok = (
        _normalized_text(program.get("status")) != "archived"
        and (_is_default_program(int(program_id)) or bool(setup))
        and _has_entry_channel(int(program_id))
        and audience_rule_ok
    )
    audience_rules = list((audience_payload or {}).get("rules") or _legacy_rules_from_entry_rule(audience_payload))
    full_ok = (
        entry_ok
        and bool(segmentation.get("questionnaire_id"))
        and _has_segmentation(segmentation)
        and audience_rule_ok
        and bool(active_tasks.get("tasks"))
    )
    def item(label: str, passed: bool, message: str, fix_step: str) -> dict[str, Any]:
        return {
            "label": label,
            "passed": bool(passed),
            "severity": "pass" if passed else "fail",
            "message": message if not passed else "已完成",
            "fix_step": fix_step,
            "fix_url": f"?step={fix_step}",
        }

    return {
        "entry": {
            "passed": entry_ok,
            "severity": "pass" if entry_ok else "fail",
            "items": [
                item("方案可用", bool(program), "方案不存在或已被删除", "basic"),
                item("方案未归档", _normalized_text(program.get("status")) != "archived", "归档方案不能发布入口", "basic"),
                item("当前方案未读取默认方案配置", _is_default_program(int(program_id)) or bool(setup), "请先保存当前方案配置", "basic"),
                item("至少有一个当前方案入口", _has_entry_channel(int(program_id)), "请先配置渠道二维码或获客助手入口", "entry"),
                *audience_rule_items,
            ],
        },
        "full": {
            "passed": full_ok,
            "severity": "pass" if full_ok else ("warning" if entry_ok else "fail"),
            "items": [
                item("入口发布检查通过", entry_ok, "请先完成入口发布检查", "entry"),
                item("已绑定问卷", bool(segmentation.get("questionnaire_id")), "请选择当前方案使用的问卷", "segmentation"),
                item("已配置分层策略", _has_segmentation(segmentation), "请配置普通问卷规则或总分分层", "segmentation"),
                item("入池规则完整", bool(audience_rules) and audience_rule_ok, "请保存入池规则", "entry-rule"),
                item("存在启用中的运营任务", bool(active_tasks.get("tasks")), "请至少启用一个运营任务", "operations"),
            ],
        },
    }


def publish_entry(program_id: int, *, operator_id: str) -> dict[str, Any]:
    check = build_publish_check(int(program_id))
    if not check["entry"]["passed"]:
        raise ValueError("入口发布检查未通过")
    block = program_repo.upsert_config_block_row(
        int(program_id),
        BLOCK_PUBLISH_STATE,
        {"entry_published": True, "full_published": False},
        status="published",
    )
    program = update_automation_program_status(int(program_id), status=PROGRAM_STATUS_ACTIVE, operator_id=operator_id)["program"]
    return {"program": program, "publish_state": block, "publish_check": build_publish_check(int(program_id))}


def publish_full(program_id: int, *, operator_id: str) -> dict[str, Any]:
    check = build_publish_check(int(program_id))
    if not check["full"]["passed"]:
        raise ValueError("完整自动化发布检查未通过")
    block = program_repo.upsert_config_block_row(
        int(program_id),
        BLOCK_PUBLISH_STATE,
        {"entry_published": True, "full_published": True},
        status="published",
    )
    program = update_automation_program_status(int(program_id), status=PROGRAM_STATUS_ACTIVE, operator_id=operator_id)["program"]
    return {"program": program, "publish_state": block, "publish_check": build_publish_check(int(program_id))}
