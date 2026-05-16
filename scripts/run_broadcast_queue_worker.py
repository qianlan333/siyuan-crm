"""单一 worker — 轮询 broadcast_jobs 表把到期的群发任务真发出去。

替代分散在 6 条链路里各自的 cron 脚本。各 domain 只负责把"未来该发的批次"
展平到 broadcast_jobs（status='queued' + scheduled_for），本脚本统一消费。

cron 例（每分钟）：
    * * * * * cd /opt/crm && python3 scripts/run_broadcast_queue_worker.py

每次跑：
1. claim_due_jobs(limit=N) — 原子地把到期 queued 任务标 claimed
2. 对每个 job：
   - 按 source_type 路由到对应 handler
   - handler 负责现场计算收件人、组装企微 payload、真发并写回业务执行明细
   - 成功：mark_sent(job_id, outbound_task_id, sent_count)
   - 失败：mark_failed(job_id, error)（v1 不自动重试，由运营手动 retry）
3. 输出结构化 summary

环境变量：
- ``BROADCAST_QUEUE_BATCH_SIZE``  默认 50，单次最多 claim 多少 job
- ``DATABASE_URL`` 同主程序
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from typing import Any

from script_runtime import ensure_repo_root_on_path, print_json, read_int_env

ensure_repo_root_on_path()


logger = logging.getLogger("broadcast_queue_worker")


def _process_one_job(job: dict[str, Any]) -> dict[str, Any]:
    from wecom_ability_service.db import get_db
    from wecom_ability_service.domains.broadcast_jobs import service as queue_service
    from wecom_ability_service.domains.broadcast_jobs.handlers import execute_job

    job_id = int(job["id"])
    result = execute_job(job)
    if result.get("ok"):
        queue_service.mark_sent(
            job_id,
            outbound_task_id=result.get("outbound_task_id"),
            sent_count=int(result.get("sent_count") or 0),
            failed_count=int(result.get("failed_count") or 0),
        )
        return {
            "id": job_id,
            "status": "sent",
            "outbound_task_id": result.get("outbound_task_id"),
            "sent_count": int(result.get("sent_count") or 0),
        }
    error_msg = str(result.get("error") or "unknown error")
    try:
        get_db().rollback()
    except Exception:
        pass
    queue_service.mark_failed(job_id, error=error_msg)
    logger.error("broadcast_job dispatch failed id=%s: %s", job_id, error_msg)
    return {"id": job_id, "status": "failed", "reason": error_msg}


def run(batch_size: int) -> dict[str, Any]:
    from wecom_ability_service.domains.broadcast_jobs import service as queue_service

    started_at = datetime.now(timezone.utc)
    claimed = queue_service.claim_due_jobs(limit=batch_size, now=started_at)
    results: list[dict[str, Any]] = []
    sent_ok = 0
    sent_failed = 0
    for job in claimed:
        try:
            outcome = _process_one_job(job)
        except Exception as exc:
            logger.exception("broadcast_job id=%s crashed: %s", job.get("id"), exc)
            outcome = {"id": job.get("id"), "status": "crashed", "reason": str(exc)}
        results.append(outcome)
        if outcome["status"] == "sent":
            sent_ok += 1
        else:
            sent_failed += 1
    return {
        "scanned_at": started_at.isoformat(),
        "claimed": len(claimed),
        "sent_ok": sent_ok,
        "sent_failed": sent_failed,
        "results": results,
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    batch_size = read_int_env("BROADCAST_QUEUE_BATCH_SIZE", 50)
    from wecom_ability_service import create_app

    app = create_app()
    with app.app_context():
        summary = run(batch_size)
    print_json(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
