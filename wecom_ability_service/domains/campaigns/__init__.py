"""Campaigns — 多分层 × 多步节奏的运营计划。

核心保障（系统级，不依赖 Agent 自觉）：
- ``UNIQUE(campaign_id, member_id)`` — 一个用户在同一个 Campaign 内最多
  分配到一个分层、一条节奏；其他分层匹配上的同一个用户**会被丢弃**
- 分配按 ``campaign_segments.priority`` 降序优先；高优先级先抢人
- 跨 Campaign 仍走全局频次预算，跨场景的反复骚扰由频次预算兜底

数据流：
  Agent.propose_campaign → CRM 落 draft + 分配 campaign_members
  CRM 后台审阅 → 人工 start_campaign + token
  Cron 扫 due 的 campaign_member → 取对应 step → 调发送管道 → 推进到下一步
"""
from .service import (
    add_segment_to_campaign,
    add_step_to_campaign,
    allocate_campaign_members,
    assemble_campaign_overview,
    create_campaign_draft,
    finish_campaign,
    get_campaign,
    list_campaigns,
    pause_campaign,
    propose_campaign,
    reject_campaign,
    resume_campaign,
    start_campaign,
    submit_campaign_for_review,
)
from .scheduler import (
    process_due_campaign_members,
    progress_member_after_send,
    register_member_reply,
)


__all__ = [
    "add_segment_to_campaign",
    "add_step_to_campaign",
    "allocate_campaign_members",
    "assemble_campaign_overview",
    "create_campaign_draft",
    "finish_campaign",
    "get_campaign",
    "list_campaigns",
    "pause_campaign",
    "process_due_campaign_members",
    "progress_member_after_send",
    "propose_campaign",
    "register_member_reply",
    "reject_campaign",
    "resume_campaign",
    "start_campaign",
    "submit_campaign_for_review",
]
