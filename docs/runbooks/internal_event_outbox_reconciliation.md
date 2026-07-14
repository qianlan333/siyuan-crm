# Internal Event Outbox 对账与修复 Runbook

## 安全前提

- 默认命令只读、count-only，不输出业务 payload 或身份明文。
- 修复命令只补技术 outbox/event/consumer-run，不执行 consumer，不调用企微、支付或 webhook。
- 在真实外部执行恢复前，先确认 internal-event 和 external-effect allowlist/mode。

## 只读诊断

```bash
python scripts/ops/reconcile_internal_event_outbox.py
```

重点字段：

- `paid_without_outbox_count`
- `legacy_paid_without_outbox_count`（只作历史库存展示，不修复）
- `relayed_outbox_without_event_count`
- `event_missing_consumer_run_count`
- `legacy_event_missing_consumer_run_count`（只作历史库存展示，不修复）
- `manual_only_in_automatic_due_count`（必须为 0）
- `stale_running_consumer_count`
- `stale_running_outbox_count`
- `outbox_metrics.failed_terminal_count`

支付 outbox 与 consumer-run 缺口只在 R08 生产切换点
`2026-07-13T09:46:09Z` 之后视为可执行异常。切换前订单与事件保留为
`legacy_*` 计数，`--repair` 不会为其创建 outbox 或 consumer-run，避免历史订单
被批量重放。

## Dry-run 修复预览

代码 API 默认 `repair(dry_run=True)`；CLI 未传 `--repair` 时不会写数据库。

## 执行幂等修复

先暂停 internal-event timer，保留 web 与 callback worker：

```bash
sudo systemctl stop openclaw-internal-event-worker.timer
python scripts/ops/reconcile_internal_event_outbox.py --repair --limit 100
python scripts/ops/reconcile_internal_event_outbox.py
```

验收：

- 三类 gap 计数为 0，或剩余项有明确 terminal 原因；
- `manual_only_in_automatic_due_count=0`；
- 修复结果 `real_external_call_executed=false`、`pii_in_output=false`；
- consumer attempt_count 未因 repair 增加。

确认后恢复 timer：

```bash
sudo systemctl start openclaw-internal-event-worker.timer
sudo systemctl status openclaw-internal-event-worker.timer --no-pager
```

## 回滚

- 若 repair 失败，保持 timer 停止；pending/running outbox 会保留，禁止手工删除。
- 回滚 application release；`0099` 为 expand-only，可保留表/列。
- 不把 `failed_terminal/blocked` 直接改成 pending；必须使用带 reason 的 retry/skip API。
