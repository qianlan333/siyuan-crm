"""定时调度脚本 — 推进 Campaign 节奏。

cron 例（每 5 分钟跑一次）：
    */5 * * * * cd /opt/crm && python3 scripts/run_campaign_scheduler.py

每次跑：
1. 扫所有 status='pending' 且 next_due_at <= now 的 campaign_member
2. 对每个 member 取下一步 step → 走频次预算 → 调发送管道
3. 推进 current_step_index → 算下一步 next_due_at 或标记完成

环境变量：
- ``CAMPAIGN_SCHEDULER_BATCH_SIZE``（默认 200）
- ``DATABASE_PATH`` / ``DATABASE_URL`` 同主程序
"""
from __future__ import annotations

import os
import sys


def main() -> None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from wecom_ability_service import create_app
    from wecom_ability_service.domains.campaigns.scheduler import process_due_campaign_members

    batch_size = int(os.environ.get("CAMPAIGN_SCHEDULER_BATCH_SIZE", "200"))

    app = create_app()
    with app.app_context():
        result = process_due_campaign_members(batch_size=batch_size)
        print(
            f"campaign_scheduler "
            f"processed={result['processed']} "
            f"sent_ok={result['sent_ok']} "
            f"sent_failed={result['sent_failed']} "
            f"skipped_budget={result['skipped_budget']} "
            f"scanned_at={result['scanned_at']}"
        )


if __name__ == "__main__":
    main()
