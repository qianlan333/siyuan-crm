"""Cloud 编排端的 MCP 工具集 — Tool Catalog + Dispatch Router。

两个出口：
- ``list_cloud_tool_specs()`` 返回工具规格列表（给 orchestrator 转 Claude API
  以及 mcp_adapter 注册）
- ``dispatch_cloud_tool(name, arguments, ...)`` 路由到具体服务函数，自动写
  ``cloud_agent_audit_log``

副作用分级（让安全护栏一目了然）：
- ``read``    — 仅查询，AI 可无门槛调
- ``draft``   — 写 draft 表（cloud_broadcast_plans / agent_run），不影响生产
- ``async_write`` — 创建工单，等异步回填
- ``write``   — 真发送 / 改 production 表，必须 ``approval_token`` 校验
"""
from __future__ import annotations

import json
import logging
from typing import Any

from ..automation_conversion import (
    cadence_engine,
    copy_workorder_service,
    interaction_stats_service,
    member_segment_search_service,
)
from ..campaigns import service as campaign_service
from ..segments import service as segments_service
from ..segments.sql_sandbox import SqlSandboxError, validate_segment_sql
from . import audit, broadcast_planner


logger = logging.getLogger(__name__)


_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "query_segment_dimensions",
        "side_effect": "read",
        "description": (
            "返回当前可用的筛选维度元数据：池子（pool_keys）、画像分层（profile_segment_keys）、"
            "行为分层（behavior_tier_keys）、生命周期（audience_codes）。Cloud Agent 决策前的快速识图。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "search_segment_members",
        "side_effect": "read",
        "description": (
            "按 pool / profile_segment / behavior_tier / keyword 多维筛选会员，"
            "返回候选+总数。pool_keys 例：active_focus / inactive_focus / inactive_normal / active_normal / new_user / silent。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pool_keys": {"type": "array", "items": {"type": "string"}},
                "profile_segment_keys": {"type": "array", "items": {"type": "string"}},
                "behavior_tier_keys": {"type": "array", "items": {"type": "string"}},
                "keyword": {"type": "string"},
                "page": {"type": "integer", "minimum": 1},
                "page_size": {"type": "integer", "minimum": 1, "maximum": 200},
            },
        },
    },
    {
        "name": "query_member_interaction_stats",
        "side_effect": "read",
        "description": (
            "对一批 external_contact_id 返回互动聚合：30 天触达次数、回复率、沉默天数、"
            "AI cooldown 是否生效。最多 500 条。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "external_contact_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 500,
                },
                "lookback_days": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 180,
                    "default": 30,
                },
            },
        },
    },
    {
        "name": "query_recent_touch_outcomes",
        "side_effect": "read",
        "description": (
            "群发后效果回报：sent / delivered / replies / reply_rate。可按 plan_id / "
            "trace_id / send_record_id 任一维度查询。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "trace_id": {"type": "string"},
                "send_record_id": {"type": "integer"},
                "lookback_hours": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 168,
                    "default": 72,
                },
            },
        },
    },
    {
        "name": "scan_silent_for_revival",
        "side_effect": "read",
        "description": (
            "扫描沉默池候选 — 返回 [silent_days_min, silent_days_max] 区间内、之后无 inbound、"
            "未在 cooldown 的成员，给 Cloud Agent 决定是否激活。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "silent_days_min": {"type": "integer", "minimum": 1},
                "silent_days_max": {"type": "integer", "minimum": 2},
                "pool_keys": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            },
        },
    },
    {
        "name": "request_copy_workorder",
        "side_effect": "async_write",
        "description": (
            "给话术 AI 端创建一个群发场景的话术工单。同步等待 LLM 返回（或 fallback）。"
            "scenario_code: bulk_activation / silent_wake / journey_step。"
            "audience_summary 给 AI 写手做参考；target_segments 是需要逐一生成话术的画像 key 列表。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "scenario_code": {"type": "string"},
                "intent": {"type": "string"},
                "audience_summary": {"type": "object"},
                "target_segments": {"type": "array", "items": {"type": "string"}},
                "sample_recipients": {"type": "array", "items": {"type": "object"}},
                "plan_id": {"type": "string"},
            },
            "required": ["intent", "audience_summary", "target_segments"],
        },
    },
    {
        "name": "draft_broadcast_plan",
        "side_effect": "draft",
        "description": (
            "出一份群发计划草稿：选人（按 selection 多维筛选）+ 调话术工单（按 scenario_code）+ "
            "频次预算检查 + 解释报告。写入 cloud_broadcast_plans，TTL 24 小时。返回 plan_id。"
            "**不发送任何消息**。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "intent": {"type": "string"},
                "selection": {
                    "type": "object",
                    "properties": {
                        "pool_keys": {"type": "array", "items": {"type": "string"}},
                        "profile_segment_keys": {"type": "array", "items": {"type": "string"}},
                        "behavior_tier_keys": {"type": "array", "items": {"type": "string"}},
                        "keyword": {"type": "string"},
                        "owner_userid": {"type": "string"},
                    },
                },
                "content_strategy": {"type": "string"},
                "content_template": {"type": "string"},
                "max_recipients": {"type": "integer", "minimum": 1, "maximum": 1000},
                "scenario_code": {"type": "string"},
                "attachments": {
                    "type": "array",
                    "description": (
                        "可选附件：仅支持 miniprogram(library_id) 与 file(media_id)。"
                        "miniprogram 必须从素材库选 library_id，不允许 AI 自由拼 appid。"
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "msgtype": {"type": "string", "enum": ["miniprogram", "file"]},
                            "miniprogram": {
                                "type": "object",
                                "properties": {
                                    "library_id": {"type": "integer"},
                                    "pagepath": {"type": "string"},
                                    "title": {"type": "string"},
                                },
                                "required": ["library_id"],
                            },
                            "file": {
                                "type": "object",
                                "properties": {"media_id": {"type": "string"}},
                                "required": ["media_id"],
                            },
                        },
                        "required": ["msgtype"],
                    },
                },
            },
            "required": ["intent", "selection"],
        },
    },
    {
        "name": "list_miniprogram_library",
        "side_effect": "read",
        "description": (
            "列出当前租户已配置的小程序素材库（appid / pagepath / 标题 / 缩略图状态）。"
            "AI 在 draft_broadcast_plan 用 attachments=[{msgtype:'miniprogram', miniprogram:{library_id:N}}] "
            "前必须先调本工具确认 library_id。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "enabled_only": {"type": "boolean"},
            },
        },
    },
    {
        "name": "simulate_broadcast",
        "side_effect": "draft",
        "description": (
            "对 draft plan 做 dry-run：预估触达人数、跳过原因、频次预算消耗。状态 → simulated。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {"plan_id": {"type": "string"}},
            "required": ["plan_id"],
        },
    },
    {
        "name": "evaluate_transition",
        "side_effect": "read",
        "description": (
            "对一个 condition_kind=ai_decision 的 transition 给出『是否走 to_node、原因』，"
            "结果缓存到 transition.condition_payload_json。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "transition_id": {"type": "integer"},
                "matched": {"type": "boolean"},
                "reason": {"type": "string"},
            },
            "required": ["transition_id", "matched"],
        },
    },
    {
        "name": "commit_broadcast_plan",
        "side_effect": "write",
        "description": (
            "唯一允许真发的 tool。强制 confirm=true + approval_token。"
            "approval_token 必须由后端 /admin/automation-conversion/ai-assistant/approve 端点签发，"
            "5 分钟 TTL，绑定 plan_id + 操作人。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "confirm": {"type": "boolean"},
                "human_approver": {"type": "string"},
                "approval_token": {"type": "string"},
            },
            "required": ["plan_id", "confirm", "human_approver", "approval_token"],
        },
    },
    {
        "name": "list_recent_plans",
        "side_effect": "read",
        "description": "列最近的 cloud_broadcast_plans（可按 status 过滤）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
        },
    },
    # ---- Segments（命名分层）------------------------------------------
    {
        "name": "list_segments",
        "side_effect": "read",
        "description": (
            "列出已注册的命名分层（系统默认 + AI 创建）。CRM 前端永远不开放新建入口，"
            "新分层只能通过 propose_segment 创建。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "active / draft / archived"},
                "source_type": {"type": "string", "description": "system_default / ai_generated"},
                "keyword": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            },
        },
    },
    {
        "name": "get_segment",
        "side_effect": "read",
        "description": "拿单个分层详情，含 SQL、当前人数、样本预览。",
        "input_schema": {
            "type": "object",
            "properties": {"segment_code": {"type": "string"}, "segment_id": {"type": "integer"}},
        },
    },
    {
        "name": "validate_segment_sql",
        "side_effect": "read",
        "description": (
            "纯静态检查一段 SQL 是否能作为分层 SQL（黑名单关键字、白名单表、必含 member_id）。"
            "Agent 写代码前可以先 validate 再正式 propose。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {"sql_query": {"type": "string"}},
            "required": ["sql_query"],
        },
    },
    {
        "name": "preview_segment_members",
        "side_effect": "read",
        "description": "实时跑一次分层 SQL 拿前 N 条样本 + 实时人数。不更新缓存。",
        "input_schema": {
            "type": "object",
            "properties": {
                "segment_code": {"type": "string"},
                "segment_id": {"type": "integer"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
        },
    },
    {
        "name": "propose_segment",
        "side_effect": "draft",
        "description": (
            "Agent 创建一个命名分层。SQL 在沙箱里跑过校验（只读 + 白名单表 + LIMIT）才能落库。"
            "默认 status=draft；activate=true 会直接上架。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "segment_code": {"type": "string", "description": "全局唯一短码，例 silent_30d"},
                "display_name": {"type": "string"},
                "description": {"type": "string"},
                "sql_query": {"type": "string", "description": "SELECT 语句，必须返回 member_id 列"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "activate": {"type": "boolean"},
            },
            "required": ["segment_code", "display_name", "sql_query"],
        },
    },
    {
        "name": "update_segment",
        "side_effect": "draft",
        "description": "更新分层（改 SQL 会重新校验 + 重新跑一次人数）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "segment_code": {"type": "string"},
                "display_name": {"type": "string"},
                "description": {"type": "string"},
                "sql_query": {"type": "string"},
                "status": {"type": "string", "description": "draft / active / archived"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["segment_code"],
        },
    },
    {
        "name": "archive_segment",
        "side_effect": "draft",
        "description": "归档分层（不删，只置 archived）。被引用的分层只能归档不能删。",
        "input_schema": {
            "type": "object",
            "properties": {"segment_code": {"type": "string"}},
            "required": ["segment_code"],
        },
    },
    # ---- 问卷数据探索 — 让 Agent 自助按问卷答案建分层 ------------------
    {
        "name": "list_questionnaires",
        "side_effect": "read",
        "description": (
            "列出所有问卷（带提交数）。Agent 在做'按问卷答案分层'时第一步用，"
            "找到目标问卷的 id 之后再调 inspect_questionnaire 看题目结构。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "问卷标题模糊匹配"},
                "only_with_submissions": {"type": "boolean", "description": "默认 true，过滤掉空问卷"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
        },
    },
    {
        "name": "inspect_questionnaire",
        "side_effect": "read",
        "description": (
            "看单个问卷的题目结构 + 每题每选项的命中人数。Agent 用这个判断"
            "'某选项是否符合预期人群'。返回 questions[].options[].selected_count "
            "对应该选项被多少人选过。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "questionnaire_id": {"type": "integer"},
                "title_keyword": {"type": "string", "description": "也可用标题关键词，取第一个匹配的问卷"},
            },
        },
    },
    {
        "name": "preview_questionnaire_population",
        "side_effect": "read",
        "description": (
            "验证一组 question/option 组合命中多少人。filters 之间是 AND 关系，"
            "每个 filter 内部 option_ids OR option_text_keywords 是 OR 关系。"
            "Agent 用这个在 propose_segment 之前确认人群规模合理。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filters": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question_id": {"type": "integer"},
                            "option_ids": {"type": "array", "items": {"type": "integer"}},
                            "option_text_keywords": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["question_id"],
                    },
                },
                "audience_code": {"type": "string", "description": "默认 operating，空字符串 = 不限"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
            "required": ["filters"],
        },
    },
    {
        "name": "compose_segment_sql_from_questionnaire",
        "side_effect": "read",
        "description": (
            "把 filters 拼成 propose_segment 直接可用的 SQL 字符串 + 试跑拿人数。"
            "Agent 拿到 sql_query 后调 propose_segment(sql_query=<这里>) 即可"
            "落地命名分层。这是'问卷探索 → 分层落地'的最后一步。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filters": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question_id": {"type": "integer"},
                            "option_ids": {"type": "array", "items": {"type": "integer"}},
                            "option_text_keywords": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["question_id"],
                    },
                },
                "audience_code": {"type": "string"},
                "extra_member_constraints": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "可选的额外 WHERE 子句（如 m.current_pool='active_focus'），AND 拼接",
                },
            },
            "required": ["filters"],
        },
    },
    # ---- Campaigns（多分层多步骤运营计划） ----------------------------
    {
        "name": "propose_campaign",
        "side_effect": "draft",
        "description": (
            "一次性提交多分层多步骤运营计划草稿。Agent 给完整的 segments + 每层"
            "的多步节奏，系统会按 priority 互斥分配候选成员（同一用户在同一 Campaign 内"
            "只命中一个分层一条节奏）。返回的 overview 包含分配统计和审阅信息。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "display_name": {"type": "string"},
                "intent": {"type": "string"},
                "anchor_mode": {
                    "type": "string",
                    "description": "campaign_start_date 启动日为 D0；member_joined_at 各人加入日为 D0",
                },
                "anchor_date": {"type": "string", "description": "YYYY-MM-DD"},
                "owner_userid": {"type": "string"},
                "segments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "segment_code": {"type": "string"},
                            "priority": {"type": "integer", "description": "数值越大越优先（先抢人）"},
                            "label": {"type": "string"},
                            "steps": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "step_index": {"type": "integer"},
                                        "day_offset": {"type": "integer"},
                                        "send_time": {"type": "string"},
                                        "content_text": {"type": "string"},
                                        "stop_on_reply": {"type": "boolean"},
                                    },
                                    "required": ["step_index", "day_offset", "content_text"],
                                },
                            },
                        },
                        "required": ["segment_code", "steps"],
                    },
                },
                "auto_allocate": {"type": "boolean"},
            },
            "required": ["display_name", "intent", "segments"],
        },
    },
    {
        "name": "get_campaign",
        "side_effect": "read",
        "description": "拿 Campaign 详情（聚合定义 + 分层 + 节奏 + 成员状态）。",
        "input_schema": {
            "type": "object",
            "properties": {"campaign_code": {"type": "string"}, "campaign_id": {"type": "integer"}},
        },
    },
    {
        "name": "list_campaigns",
        "side_effect": "read",
        "description": "列 Campaign。按 review_status / run_status 过滤。",
        "input_schema": {
            "type": "object",
            "properties": {
                "review_status": {"type": "string"},
                "run_status": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
        },
    },
    {
        "name": "submit_campaign_for_review",
        "side_effect": "draft",
        "description": (
            "把 draft Campaign 切到 pending_review，CRM 后台开始能看到它。"
            "等运营在 CRM 上点 start_campaign 才会真启动。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {"campaign_id": {"type": "integer"}},
            "required": ["campaign_id"],
        },
    },
    {
        "name": "start_campaign",
        "side_effect": "write",
        "description": (
            "[WRITE - 需要 approval_token] 真正启动 Campaign — 调度器接管按节奏推送。"
            "approval_token 必须由 CRM 后台 /api/admin/cloud-orchestrator/campaigns/<code>/approve 端点签发。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "integer"},
                "human_approver": {"type": "string"},
                "approval_token": {"type": "string"},
            },
            "required": ["campaign_id", "human_approver", "approval_token"],
        },
    },
    {
        "name": "pause_campaign",
        "side_effect": "draft",
        "description": "暂停运行中的 Campaign（不撤回已发的，但停止后续节奏）。",
        "input_schema": {
            "type": "object",
            "properties": {"campaign_id": {"type": "integer"}, "reason": {"type": "string"}},
            "required": ["campaign_id"],
        },
    },
    {
        "name": "resume_campaign",
        "side_effect": "draft",
        "description": "恢复 paused 的 Campaign。",
        "input_schema": {
            "type": "object",
            "properties": {"campaign_id": {"type": "integer"}},
            "required": ["campaign_id"],
        },
    },
    {
        "name": "query_recent_audit_logs",
        "side_effect": "read",
        "description": (
            "查最近的 MCP tool 调用审计日志（cloud_agent_audit_log 表）。"
            "按 status='error' 可拿到所有报错及完整 error_message + arguments_json。"
            "Agent 调用别的 tool 失败后第一时间 call 这个就能定位 SQL/参数错误，不用回 UI 截图。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "success / error，不填则全部"},
                "tool_name": {"type": "string", "description": "只看某个 tool 的日志"},
                "trace_id": {"type": "string"},
                "session_id": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
            },
        },
    },
    {
        "name": "query_table_schema",
        "side_effect": "read",
        "description": (
            "查一张表的列定义（PG/SQLite 都支持），便于 Agent 写 SQL 前确认列名/类型。"
            "比让用户截图 schema 文件高效得多。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {"table_name": {"type": "string"}},
            "required": ["table_name"],
        },
    },
]


def list_cloud_tool_specs() -> list[dict[str, Any]]:
    return list(_TOOL_SPECS)


def _requires_token(tool_name: str) -> bool:
    return tool_name in {"commit_broadcast_plan", "start_campaign"}


def dispatch_cloud_tool(
    *,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    session_id: str = "",
    trace_id: str = "",
    operator: str = "",
) -> Any:
    """单点路由 — 自动写 audit、按 side_effect 检查 token、调用对应 service。

    入口由两条路径共用：
    1. orchestrator 内部调（内部生成 trace_id）
    2. mcp_adapter 暴露的 HTTP MCP server（trace_id 由调用方传）
    """
    args = arguments or {}
    requires_token = _requires_token(tool_name)
    token_verified = False
    full_payload = {"tool": tool_name, "arguments": args}

    with audit.audited_tool_call(
        session_id=session_id,
        trace_id=trace_id,
        operator=operator,
        tool_name=tool_name,
        arguments=args,
        requires_token=requires_token,
        token_verified=token_verified,
        full_payload=full_payload,
    ) as ctx:
        if tool_name == "query_segment_dimensions":
            ctx["result"] = interaction_stats_service.query_segment_dimensions()
            return ctx["result"]

        if tool_name == "search_segment_members":
            result = member_segment_search_service.search_members(
                pool_keys=args.get("pool_keys"),
                profile_keys=args.get("profile_segment_keys") or args.get("profile_keys"),
                behavior_keys=args.get("behavior_tier_keys") or args.get("behavior_keys"),
                keyword=str(args.get("keyword") or ""),
                page=int(args.get("page") or 1),
                page_size=int(args.get("page_size") or 50),
            )
            ctx["result"] = result
            return result

        if tool_name == "query_member_interaction_stats":
            items = interaction_stats_service.query_member_interaction_stats(
                external_contact_ids=args.get("external_contact_ids") or [],
                member_ids=args.get("member_ids") or [],
                lookback_days=int(args.get("lookback_days") or 30),
            )
            agg = interaction_stats_service.aggregate_population_stats(items)
            ctx["result"] = {"items": items, "aggregate": agg}
            return ctx["result"]

        if tool_name == "query_recent_touch_outcomes":
            ctx["result"] = interaction_stats_service.query_recent_touch_outcomes(
                plan_id=str(args.get("plan_id") or ""),
                trace_id=str(args.get("trace_id") or ""),
                send_record_id=(
                    int(args.get("send_record_id"))
                    if args.get("send_record_id") is not None
                    else None
                ),
                lookback_hours=int(args.get("lookback_hours") or 72),
            )
            return ctx["result"]

        if tool_name == "scan_silent_for_revival":
            ctx["result"] = interaction_stats_service.scan_silent_for_revival(
                silent_days_min=int(args.get("silent_days_min") or 14),
                silent_days_max=int(args.get("silent_days_max") or 60),
                pool_keys=args.get("pool_keys") or ("active_focus", "inactive_focus"),
                limit=int(args.get("limit") or 100),
            )
            return ctx["result"]

        if tool_name == "request_copy_workorder":
            ctx["result"] = copy_workorder_service.request_bulk_copy_workorder(
                scenario_code=str(
                    args.get("scenario_code") or copy_workorder_service.SCENARIO_BULK_ACTIVATION
                ),
                intent=str(args.get("intent") or ""),
                audience_summary=dict(args.get("audience_summary") or {}),
                target_segments=list(args.get("target_segments") or []),
                sample_recipients=list(args.get("sample_recipients") or []),
                trace_id=trace_id,
                operator=operator,
                plan_id=str(args.get("plan_id") or ""),
            )
            return ctx["result"]

        if tool_name == "draft_broadcast_plan":
            ctx["result"] = broadcast_planner.draft_broadcast_plan(
                intent=str(args.get("intent") or ""),
                selection=dict(args.get("selection") or {}),
                content_strategy=str(args.get("content_strategy") or "profile_layered"),
                content_template=str(args.get("content_template") or ""),
                personalization=list(args.get("personalization") or []),
                attachments=list(args.get("attachments") or []),
                max_recipients=int(args.get("max_recipients") or 0),
                operator=operator,
                session_id=session_id,
                trace_id=trace_id,
                scenario_code=str(
                    args.get("scenario_code") or copy_workorder_service.SCENARIO_BULK_ACTIVATION
                ),
                auto_copy_workorder=bool(args.get("auto_copy_workorder", True)),
            )
            return ctx["result"]

        if tool_name == "list_miniprogram_library":
            from .. import miniprogram_library

            enabled_only = args.get("enabled_only")
            ctx["result"] = {
                "items": miniprogram_library.list_miniprograms(
                    enabled_only=bool(enabled_only) if enabled_only is not None else True
                ),
            }
            return ctx["result"]

        if tool_name == "simulate_broadcast":
            ctx["result"] = broadcast_planner.simulate_broadcast(
                plan_id=str(args.get("plan_id") or "")
            )
            return ctx["result"]

        if tool_name == "evaluate_transition":
            cadence_engine.cache_ai_decision(
                transition_id=int(args.get("transition_id") or 0),
                matched=bool(args.get("matched")),
                reason=str(args.get("reason") or ""),
            )
            ctx["result"] = {
                "transition_id": int(args.get("transition_id") or 0),
                "cached": True,
                "matched": bool(args.get("matched")),
            }
            return ctx["result"]

        if tool_name == "list_recent_plans":
            ctx["result"] = broadcast_planner.list_recent_plans(
                status=str(args.get("status") or ""),
                limit=int(args.get("limit") or 20),
            )
            return ctx["result"]

        if tool_name == "commit_broadcast_plan":
            if not args.get("approval_token"):
                raise PermissionError("approval_token is required for commit_broadcast_plan")
            ctx["result"] = broadcast_planner.commit_broadcast_plan(
                plan_id=str(args.get("plan_id") or ""),
                confirm=bool(args.get("confirm")),
                human_approver=str(args.get("human_approver") or ""),
                approval_token_value=str(args.get("approval_token") or ""),
            )
            return ctx["result"]

        # ---- Segments ------------------------------------------------
        if tool_name == "list_segments":
            ctx["result"] = segments_service.list_segments(
                status=str(args.get("status") or "active"),
                source_type=str(args.get("source_type") or ""),
                keyword=str(args.get("keyword") or ""),
                limit=int(args.get("limit") or 200),
            )
            return ctx["result"]

        if tool_name == "get_segment":
            seg = segments_service.get_segment(
                segment_code=str(args.get("segment_code") or ""),
                segment_id=int(args["segment_id"]) if args.get("segment_id") is not None else None,
            )
            ctx["result"] = seg or {}
            return ctx["result"]

        if tool_name == "validate_segment_sql":
            ok, reason = validate_segment_sql(str(args.get("sql_query") or ""))
            ctx["result"] = {"ok": ok, "reason": reason}
            return ctx["result"]

        if tool_name == "preview_segment_members":
            try:
                ctx["result"] = segments_service.preview_segment_members(
                    segment_code=str(args.get("segment_code") or ""),
                    segment_id=(
                        int(args["segment_id"]) if args.get("segment_id") is not None else None
                    ),
                    limit=int(args.get("limit") or 50),
                )
            except SqlSandboxError as exc:
                ctx["result"] = {"ok": False, "error": str(exc)}
            return ctx["result"]

        if tool_name == "propose_segment":
            ctx["result"] = segments_service.create_segment(
                segment_code=str(args.get("segment_code") or ""),
                display_name=str(args.get("display_name") or ""),
                description=str(args.get("description") or ""),
                sql_query=str(args.get("sql_query") or ""),
                tags=list(args.get("tags") or []),
                operator=operator,
                session_id=session_id,
                activate=bool(args.get("activate", False)),
            )
            return ctx["result"]

        if tool_name == "update_segment":
            ctx["result"] = segments_service.update_segment(
                segment_code=str(args.get("segment_code") or ""),
                display_name=args.get("display_name"),
                description=args.get("description"),
                sql_query=args.get("sql_query"),
                status=args.get("status"),
                tags=args.get("tags"),
                operator=operator,
            )
            return ctx["result"]

        if tool_name == "archive_segment":
            ok = segments_service.archive_segment(
                segment_code=str(args.get("segment_code") or "")
            )
            ctx["result"] = {"ok": ok}
            return ctx["result"]

        # ---- 问卷探索 ------------------------------------------------
        if tool_name == "list_questionnaires":
            from ..segments.questionnaire_explorer import list_questionnaires as _lq

            ctx["result"] = {
                "questionnaires": _lq(
                    keyword=str(args.get("keyword") or ""),
                    only_with_submissions=bool(args.get("only_with_submissions", True)),
                    limit=int(args.get("limit") or 50),
                )
            }
            return ctx["result"]

        if tool_name == "inspect_questionnaire":
            from ..segments.questionnaire_explorer import inspect_questionnaire as _iq

            ctx["result"] = _iq(
                questionnaire_id=int(args.get("questionnaire_id") or 0),
                title_keyword=str(args.get("title_keyword") or ""),
            )
            return ctx["result"]

        if tool_name == "preview_questionnaire_population":
            from ..segments.questionnaire_explorer import preview_questionnaire_population as _pp

            ctx["result"] = _pp(
                filters=list(args.get("filters") or []),
                audience_code=str(args.get("audience_code", "operating")),
                limit=int(args.get("limit") or 50),
            )
            return ctx["result"]

        if tool_name == "compose_segment_sql_from_questionnaire":
            from ..segments.questionnaire_explorer import compose_segment_sql_from_questionnaire as _cs

            ctx["result"] = _cs(
                filters=list(args.get("filters") or []),
                audience_code=str(args.get("audience_code", "operating")),
                extra_member_constraints=list(args.get("extra_member_constraints") or []),
            )
            return ctx["result"]

        # ---- Campaigns -----------------------------------------------
        if tool_name == "propose_campaign":
            ctx["result"] = campaign_service.propose_campaign(
                display_name=str(args.get("display_name") or ""),
                intent=str(args.get("intent") or ""),
                segments=list(args.get("segments") or []),
                anchor_mode=str(args.get("anchor_mode") or "campaign_start_date"),
                anchor_date=str(args.get("anchor_date") or ""),
                owner_userid=str(args.get("owner_userid") or ""),
                operator=operator,
                session_id=session_id,
                trace_id=trace_id,
                auto_allocate=bool(args.get("auto_allocate", True)),
            )
            return ctx["result"]

        if tool_name == "get_campaign":
            ctx["result"] = campaign_service.assemble_campaign_overview(
                campaign_id=int(args.get("campaign_id") or 0)
            ) or campaign_service.get_campaign(
                campaign_code=str(args.get("campaign_code") or "")
            ) or {}
            return ctx["result"]

        if tool_name == "list_campaigns":
            ctx["result"] = campaign_service.list_campaigns(
                review_status=str(args.get("review_status") or ""),
                run_status=str(args.get("run_status") or ""),
                limit=int(args.get("limit") or 50),
            )
            return ctx["result"]

        if tool_name == "submit_campaign_for_review":
            ctx["result"] = campaign_service.submit_campaign_for_review(
                campaign_id=int(args.get("campaign_id") or 0),
                operator=operator,
            )
            return ctx["result"]

        if tool_name == "start_campaign":
            if not args.get("approval_token"):
                raise PermissionError("approval_token is required for start_campaign")
            ctx["result"] = campaign_service.start_campaign(
                campaign_id=int(args.get("campaign_id") or 0),
                human_approver=str(args.get("human_approver") or ""),
                approval_token_value=str(args.get("approval_token") or ""),
            )
            return ctx["result"]

        if tool_name == "pause_campaign":
            ctx["result"] = campaign_service.pause_campaign(
                campaign_id=int(args.get("campaign_id") or 0),
                reason=str(args.get("reason") or ""),
            )
            return ctx["result"]

        if tool_name == "resume_campaign":
            ctx["result"] = campaign_service.resume_campaign(
                campaign_id=int(args.get("campaign_id") or 0),
            )
            return ctx["result"]

        if tool_name == "query_recent_audit_logs":
            from . import audit as _audit
            from ...db import get_db
            db = get_db()
            cur = db.cursor()
            where = ["1=1"]
            params: list[Any] = []
            if args.get("status"):
                where.append("status = ?")
                params.append(str(args["status"]))
            if args.get("tool_name"):
                where.append("tool_name = ?")
                params.append(str(args["tool_name"]))
            if args.get("trace_id"):
                where.append("trace_id = ?")
                params.append(str(args["trace_id"]))
            if args.get("session_id"):
                where.append("session_id = ?")
                params.append(str(args["session_id"]))
            params.append(int(args.get("limit") or 10))
            cur.execute(
                f"""
                SELECT id, session_id, trace_id, operator, tool_name, status,
                       latency_ms, error_message, arguments_json, result_summary,
                       created_at
                FROM cloud_agent_audit_log
                WHERE {' AND '.join(where)}
                ORDER BY id DESC LIMIT ?
                """,
                tuple(params),
            )
            ctx["result"] = {"rows": [dict(r) for r in (cur.fetchall() or [])]}
            return ctx["result"]

        if tool_name == "query_table_schema":
            from ...db import get_db, get_db_backend
            table_name = str(args.get("table_name") or "").strip()
            if not table_name or not table_name.replace("_", "").isalnum():
                raise ValueError("invalid table_name")
            db = get_db()
            cur = db.cursor()
            if get_db_backend() == "postgres":
                cur.execute(
                    """
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_name = ?
                    ORDER BY ordinal_position
                    """,
                    (table_name,),
                )
            else:
                cur.execute(f"PRAGMA table_info({table_name})")
            rows = [dict(r) for r in (cur.fetchall() or [])]
            ctx["result"] = {"table_name": table_name, "columns": rows}
            return ctx["result"]

        raise ValueError(f"unknown cloud tool: {tool_name}")


__all__ = ["list_cloud_tool_specs", "dispatch_cloud_tool"]
