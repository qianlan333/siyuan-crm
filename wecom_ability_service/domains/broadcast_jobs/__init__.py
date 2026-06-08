"""broadcast_jobs — 统一群发任务队列（revision 0008）

把分散在 6 条链路（campaigns / SOP / workflow / cloud_orchestrator /
focus_send / user_ops_deferred）的"未来该发的批次"统一到 broadcast_jobs 表。
单一 worker (run_broadcast_queue_worker.py) 轮询消费，按 batch_key 聚合后
调 dispatch_wecom_task() 真发。

业务语义：
- 一个 job = 一次群发批次（target_external_userids 是 user 数组）
- AI 草稿用 status='waiting_approval' + requires_approval=true
- 取消用软删（status='cancelled'）便于审计
- 失败不自动重试（v1），由运营手动 retry

公共 API（service 层）：
- enqueue_broadcast_job(...) — 标准化入队协议，补业务归类 / 渠道 / 目标类型 / 幂等键
- enqueue_job(...)          — 各 domain 展平器入队
- list_jobs(...)            — 前端列表
- get_job(id)               — 详情
- claim_due_jobs(...)       — worker 原子拉取待发任务
- mark_sent / mark_failed   — worker 回写结果
- cancel_job / approve_job  — 运营操作
"""
from __future__ import annotations

from . import repo, service  # noqa: F401
