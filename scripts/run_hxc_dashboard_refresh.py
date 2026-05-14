"""用户激活漏斗看板 — 刷新快照表入口脚本

定时任务 (cron / launchd / systemd) 拉这个脚本; 它创建 Flask app context 后
调用 ``refresh_hxc_dashboard_snapshot``, 把 CRM × 黄小璨 数据聚合写入
``user_ops_hxc_dashboard_snapshot``.

用法::

    python scripts/run_hxc_dashboard_refresh.py [trigger_source]

``trigger_source`` 可选, 默认 ``scheduled``; 手动跑写 ``manual`` 便于审计。
"""
from __future__ import annotations

import json
import sys

from wecom_ability_service import create_app
from wecom_ability_service.domains.user_ops.hxc_dashboard_snapshot_service import (
    refresh_hxc_dashboard_snapshot,
)


def main() -> int:
    trigger_source = (sys.argv[1].strip() if len(sys.argv) > 1 else "") or "scheduled"
    app = create_app()
    with app.app_context():
        result = refresh_hxc_dashboard_snapshot(trigger_source=trigger_source)
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
