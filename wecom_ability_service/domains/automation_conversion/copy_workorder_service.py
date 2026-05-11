"""话术工单 — 群发/激活场景的内容生成接入。

复用现有 DeepSeek + automation_agent_run / automation_agent_output 工单状态机，
用 ``scenario_code`` 区分场景：
- ``one_to_one``       — 现有单人对话（push_openclaw 已实现，此模块不动）
- ``bulk_activation``  — 群发激活（本模块）
- ``silent_wake``      — 沉默唤醒
- ``journey_step``     — 节奏节点的话术变体

Cloud 端通过 MCP tool ``request_copy_workorder`` 创建工单 → 本模块同步调用
DeepSeek（已有 timeout / retry / fallback）→ 写工单 + 输出 → 返回多变体话术
（按 profile_segment_key 分组）。

设计上**复用工单链路**而非另起一套，理由：
1. 已有 prompt 编辑界面（admin_console agent_configs 页），运营调话术不动代码
2. 已有错误降级、版本审计、采用追溯
3. trace_id 串联，commit_broadcast_plan 出问题时一查到底
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from ...db import get_db
from .agents import llm_client


logger = logging.getLogger(__name__)


SCENARIO_ONE_TO_ONE = "one_to_one"
SCENARIO_BULK_ACTIVATION = "bulk_activation"
SCENARIO_SILENT_WAKE = "silent_wake"
SCENARIO_JOURNEY_STEP = "journey_step"

VALID_SCENARIO_CODES = (
    SCENARIO_ONE_TO_ONE,
    SCENARIO_BULK_ACTIVATION,
    SCENARIO_SILENT_WAKE,
    SCENARIO_JOURNEY_STEP,
)


_DEFAULT_FALLBACK_TEMPLATES = {
    SCENARIO_BULK_ACTIVATION: (
        "你好，我们最近做了一些功能更新，挑了你可能感兴趣的部分想给你介绍下。"
        "如果方便的话欢迎回复，我们也想听听你的想法。"
    ),
    SCENARIO_SILENT_WAKE: (
        "好久没和你聊了，最近有空吗？我们这边有些新内容想让你看看，方便的话回我一句。"
    ),
    SCENARIO_JOURNEY_STEP: (
        "你好！这是我们运营计划中的一次提醒——希望最近这段时间里你有所收获，期待你的反馈。"
    ),
}


def _resolve_agent_code_by_scenario(scenario_code: str) -> tuple[str, str, str]:
    """按 scenario_code 找到对应的 agent_code + role_prompt + task_prompt。

    Returns: (agent_code, role_prompt, task_prompt)
    """
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT agent_code, published_role_prompt, draft_role_prompt,
               published_task_prompt, draft_task_prompt, published_version
        FROM automation_agent_config
        WHERE scenario_code = ? AND enabled
        ORDER BY published_version DESC, updated_at DESC
        LIMIT 1
        """,
        (str(scenario_code),),
    )
    row = cur.fetchone()
    if not row:
        return "", "", ""
    role = (row["published_role_prompt"] or row["draft_role_prompt"] or "").strip()
    task = (row["published_task_prompt"] or row["draft_task_prompt"] or "").strip()
    return str(row["agent_code"] or ""), role, task


def _build_user_input(
    *,
    intent: str,
    audience_summary: dict[str, Any],
    target_segments: list[str],
    sample_recipients: list[dict[str, Any]] | None = None,
) -> str:
    """组合给 DeepSeek 的 user 输入：intent + 人群摘要 + 待生成的 segment 列表。"""
    lines = []
    lines.append(f"【运营意图】\n{intent.strip() or '无显式意图'}\n")
    lines.append("【人群摘要】")
    lines.append(json.dumps(audience_summary, ensure_ascii=False, indent=2))
    if target_segments:
        lines.append("\n【需要为这些 profile_segment_key 各生成一条话术】")
        for seg in target_segments:
            lines.append(f"- {seg}")
    if sample_recipients:
        lines.append("\n【样例画像（前 5 条）】")
        for sample in sample_recipients[:5]:
            lines.append(json.dumps(sample, ensure_ascii=False))
    lines.append(
        "\n请严格按 JSON 返回：{\"variants\": [{\"profile_segment_key\": str, "
        "\"content_text\": str, \"reasoning\": str}, ...], \"shared_principles\": [str]}"
    )
    return "\n".join(lines)


def _parse_variants(raw: str) -> tuple[list[dict[str, Any]], list[str]]:
    """从 LLM 返回中解析 variants + shared_principles，失败时返回空列表。"""
    if not raw:
        return [], []
    text = raw.strip()
    # 兼容代码块包裹
    if text.startswith("```"):
        idx = text.find("\n")
        if idx > 0:
            text = text[idx + 1 :]
        if text.endswith("```"):
            text = text[: -3]
    try:
        obj = json.loads(text)
    except (TypeError, ValueError):
        return [], []
    variants = obj.get("variants") if isinstance(obj, dict) else None
    if not isinstance(variants, list):
        return [], []
    cleaned: list[dict[str, Any]] = []
    for v in variants:
        if not isinstance(v, dict):
            continue
        cleaned.append(
            {
                "profile_segment_key": str(v.get("profile_segment_key") or ""),
                "content_text": str(v.get("content_text") or "").strip(),
                "reasoning": str(v.get("reasoning") or "").strip(),
            }
        )
    principles = obj.get("shared_principles") if isinstance(obj, dict) else []
    if not isinstance(principles, list):
        principles = []
    principles = [str(p) for p in principles if str(p).strip()]
    return cleaned, principles


def _fallback_variants(
    *,
    scenario_code: str,
    target_segments: list[str],
    intent: str,
) -> list[dict[str, Any]]:
    base = _DEFAULT_FALLBACK_TEMPLATES.get(scenario_code) or _DEFAULT_FALLBACK_TEMPLATES[SCENARIO_BULK_ACTIVATION]
    out: list[dict[str, Any]] = []
    for seg in (target_segments or [""]):
        out.append(
            {
                "profile_segment_key": seg,
                "content_text": base,
                "reasoning": f"fallback (scenario={scenario_code}, intent_preview={intent[:30]})",
            }
        )
    return out


def request_bulk_copy_workorder(
    *,
    scenario_code: str = SCENARIO_BULK_ACTIVATION,
    intent: str = "",
    audience_summary: dict[str, Any],
    target_segments: list[str],
    sample_recipients: list[dict[str, Any]] | None = None,
    trace_id: str = "",
    operator: str = "",
    plan_id: str = "",
) -> dict[str, Any]:
    """同步创建一次群发场景的话术工单。

    内部通过 ``call_deepseek_agent`` 真正发起请求，工单写入 ``automation_agent_run``
    （含 trace_id），输出写入 ``automation_agent_output``。LLM 失败或解析失败时
    返回 fallback variants 并标记 ``requires_manual_copy=True``。
    """
    if scenario_code not in VALID_SCENARIO_CODES:
        raise ValueError(f"invalid scenario_code: {scenario_code}")
    agent_code, role_prompt, task_prompt = _resolve_agent_code_by_scenario(scenario_code)
    if not agent_code:
        # 没有该 scenario 的 agent 配置 → 直接走 fallback
        variants = _fallback_variants(
            scenario_code=scenario_code,
            target_segments=target_segments,
            intent=intent,
        )
        return {
            "ok": False,
            "scenario_code": scenario_code,
            "agent_code": "",
            "run_id": "",
            "variants": variants,
            "shared_principles": [],
            "requires_manual_copy": True,
            "error": "no_agent_config_for_scenario",
        }
    user_input = _build_user_input(
        intent=intent,
        audience_summary=audience_summary,
        target_segments=target_segments,
        sample_recipients=sample_recipients,
    )
    full_system = (role_prompt + "\n\n" + task_prompt).strip() if task_prompt else role_prompt
    run_id = f"arun-{uuid.uuid4().hex}"
    request_id = trace_id or run_id
    try:
        result = llm_client.call_deepseek_agent(
            agent_code=agent_code,
            system_prompt=full_system,
            user_input=user_input,
            json_output=True,
            request_id=request_id,
            run_id=run_id,
            userid=operator or "cloud_orchestrator",
            external_contact_id="",
            input_snapshot={
                "scenario_code": scenario_code,
                "intent": intent,
                "audience_summary": audience_summary,
                "target_segments": target_segments,
                "sample_recipients_count": len(sample_recipients or []),
                "plan_id": plan_id,
                "trace_id": trace_id,
            },
            variables_snapshot={"scenario_code": scenario_code, "trace_id": trace_id},
            source="cloud_orchestrator_copy_workorder",
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("call_deepseek_agent failed for bulk copy: %s", exc)
        result = {"status": "failed", "error": str(exc), "rendered_output_text": ""}

    # 把 trace_id 回填到 agent_run（兼容旧 schema 的 run）
    if trace_id:
        try:
            db = get_db()
            cur = db.cursor()
            cur.execute(
                "UPDATE automation_agent_run SET trace_id = ? WHERE run_id = ?",
                (str(trace_id), run_id),
            )
            db.commit()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("trace_id backfill on agent_run failed: %s", exc)

    rendered = ""
    if isinstance(result, dict):
        rendered = (
            result.get("rendered_output_text")
            or result.get("normalized_output_text")
            or result.get("text")
            or ""
        )
    variants, principles = _parse_variants(str(rendered or ""))
    if not variants:
        variants = _fallback_variants(
            scenario_code=scenario_code,
            target_segments=target_segments,
            intent=intent,
        )
        requires_manual = True
        error = "fallback:variants_parse_failed"
    else:
        requires_manual = False
        error = ""

    # 把 plan_id 关联到 agent_run（用 batch_id 字段，工单链路已预留）
    if plan_id:
        try:
            db = get_db()
            cur = db.cursor()
            cur.execute(
                "UPDATE automation_agent_run SET batch_id = ? WHERE run_id = ?",
                (str(plan_id), run_id),
            )
            db.commit()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("batch_id backfill on agent_run failed: %s", exc)

    return {
        "ok": not requires_manual,
        "scenario_code": scenario_code,
        "agent_code": agent_code,
        "run_id": run_id,
        "variants": variants,
        "shared_principles": principles,
        "requires_manual_copy": requires_manual,
        "error": error,
        "trace_id": trace_id,
        "plan_id": plan_id,
        "raw_status": (result or {}).get("status") if isinstance(result, dict) else "",
    }


def get_workorder_result(run_id: str) -> dict[str, Any]:
    """按 run_id 拿话术工单的最新输出。供 Cloud Agent 后续轮询用。"""
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT run_id, agent_code, status, error_message, created_at, updated_at
        FROM automation_agent_run WHERE run_id = ? ORDER BY id DESC LIMIT 1
        """,
        (str(run_id),),
    )
    run_row = cur.fetchone()
    if not run_row:
        return {"ok": False, "error": "not_found"}
    cur.execute(
        """
        SELECT output_id, output_type, rendered_output_text, applied_status, created_at
        FROM automation_agent_output WHERE run_id = ? ORDER BY id DESC LIMIT 1
        """,
        (str(run_id),),
    )
    out_row = cur.fetchone()
    rendered = str(out_row["rendered_output_text"] or "") if out_row else ""
    variants, principles = _parse_variants(rendered)
    return {
        "ok": bool(variants),
        "run_id": str(run_row["run_id"]),
        "agent_code": str(run_row["agent_code"] or ""),
        "status": str(run_row["status"] or ""),
        "error_message": str(run_row["error_message"] or ""),
        "variants": variants,
        "shared_principles": principles,
        "applied_status": str(out_row["applied_status"] or "") if out_row else "",
        "created_at": str(run_row["created_at"] or ""),
    }


def ensure_default_bulk_agent_config() -> None:
    """如果运营还没创建 bulk_activation 场景的 agent 配置，写一个默认行进去。

    运营可在 admin console 修改 prompt；这里只是兜底，让"开箱可跑"。
    """
    db = get_db()
    cur = db.cursor()
    defaults = (
        (
            SCENARIO_BULK_ACTIVATION,
            "cloud_bulk_activation_writer",
            "群发激活话术写手",
            "你是一位资深的客户运营文案写手。基于 Cloud 端给出的人群摘要和运营意图，"
            "为每个 profile_segment_key 生成一条简短、有温度、可直接发送的私聊话术。"
            "原则：1) 不夸张承诺；2) 一句开场+一句价值+一句行动建议；3) 不用感叹号超过 1 个。",
            "请严格按 JSON 输出 {\"variants\": [...], \"shared_principles\": [...]}，"
            "每个 variant 包含 profile_segment_key / content_text / reasoning 三个字段。",
        ),
        (
            SCENARIO_SILENT_WAKE,
            "cloud_silent_wake_writer",
            "沉默唤醒话术写手",
            "你是一位擅长唤醒沉默用户的运营文案写手。请基于人群摘要生成低打扰、有诚意的"
            "唤醒话术，避免推销感，给用户回到对话的轻量入口。",
            "请严格按 JSON 输出 {\"variants\": [...], \"shared_principles\": [...]}。",
        ),
        (
            SCENARIO_JOURNEY_STEP,
            "cloud_journey_step_writer",
            "节奏节点话术写手",
            "你为运营节奏中的某个节点撰写话术。需要符合该节点的目标 KPI，并按 profile 分层。",
            "请严格按 JSON 输出 {\"variants\": [...], \"shared_principles\": [...]}。",
        ),
    )
    for scenario, agent_code, display_name, role, task in defaults:
        cur.execute(
            "SELECT id FROM automation_agent_config WHERE agent_code = ?",
            (agent_code,),
        )
        if cur.fetchone():
            continue
        cur.execute(
            """
            INSERT INTO automation_agent_config
                (agent_code, display_name, scenario_code, pool_keys_json, enabled,
                 draft_role_prompt, draft_task_prompt, draft_variables_json,
                 draft_output_schema_json, published_role_prompt, published_task_prompt,
                 published_variables_json, published_output_schema_json,
                 draft_version, published_version, last_modified_at, last_modified_by,
                 last_modified_source)
            VALUES (?, ?, ?, '[]', 1, ?, ?, '[]', '[]', ?, ?, '[]', '[]', 1, 1,
                    ?, 'system', 'bootstrap')
            """,
            (
                agent_code,
                display_name,
                scenario,
                role,
                task,
                role,
                task,
                datetime.utcnow().isoformat(),
            ),
        )
    db.commit()


__all__ = [
    "SCENARIO_ONE_TO_ONE",
    "SCENARIO_BULK_ACTIVATION",
    "SCENARIO_SILENT_WAKE",
    "SCENARIO_JOURNEY_STEP",
    "VALID_SCENARIO_CODES",
    "request_bulk_copy_workorder",
    "get_workorder_result",
    "ensure_default_bulk_agent_config",
]
