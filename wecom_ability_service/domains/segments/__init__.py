"""Segments — 命名分层注册表 + SQL 沙箱执行 + 互斥分配。

核心抽象：
- ``segment``：一个命名的、可保存的、可调用的筛选视角。底层是一段 SELECT SQL，
  返回的每行必须含 ``member_id``（外加 ``external_contact_id`` 作为兜底键）。
- ``source_type``：``system_default``（CRM 自带的池子/画像/行为分层）/ ``ai_generated``
  （由 Claude Code 等外部 Agent 通过 API 创建）。CRM 前端**没有任何**新建分层
  入口；想加新分层只能通过 Agent 调 API。
- ``status``：``draft`` / ``active`` / ``archived``。Agent 创建出来默认 ``draft``，
  人工或 Agent 自己确认 OK 后切 ``active``，被引用过的分层不能直接删，只能归档。

互斥保障：``campaign_members.uq_campaign_members_one_per_campaign`` 在数据库
层上做了 UNIQUE(campaign_id, member_id)，所以一个用户哪怕被 N 个分层同时
命中，在同一个 Campaign 里也只会被分配到 1 个分层（按 priority 优先级），这
是绝对保证、不依赖 AI 自觉。
"""

from .sql_sandbox import SqlSandboxError, run_segment_query, validate_segment_sql
from .service import (
    archive_segment,
    create_segment,
    get_segment,
    list_segments,
    preview_segment_members,
    refresh_segment_cache,
    seed_default_segments,
    update_segment,
)
from .questionnaire_explorer import (
    compose_segment_sql_from_questionnaire,
    inspect_questionnaire,
    list_questionnaires,
    preview_questionnaire_population,
)


__all__ = [
    "SqlSandboxError",
    "run_segment_query",
    "validate_segment_sql",
    "archive_segment",
    "create_segment",
    "get_segment",
    "list_segments",
    "preview_segment_members",
    "refresh_segment_cache",
    "seed_default_segments",
    "update_segment",
    "compose_segment_sql_from_questionnaire",
    "inspect_questionnaire",
    "list_questionnaires",
    "preview_questionnaire_population",
]
