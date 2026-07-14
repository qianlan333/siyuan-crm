# R06 Internal Event / Outbox / Consumer 可靠性设计

Issue: #95

Parent: #67

## 边界

本包只修复既有内部事件执行链，不新增用户能力、页面、菜单、业务 API、业务模型或外部调用。支付、退款、权益的完整业务闭环仍由 R08 负责。

## 旧链问题

```text
payment business transaction commit
  -> another DB connection creates internal_event
  -> N additional transactions create consumer runs
  -> exceptions are logged and swallowed
```

因此存在 paid-without-event、event-without-run、终态反复领取、过期 worker 覆盖新 owner、consumer 失败但进程 exit 0。

## 新链

```text
existing business transaction
  -> internal_event_outbox (same DB connection, no commit inside helper)
  -> relay claim with lease token
  -> one local transaction:
       internal_event (idempotent)
       + all registered internal_event_consumer_run (idempotent)
       + outbox relayed
  -> consumer claim with lease token
  -> one local transaction:
       internal_event_consumer_attempt
       + consumer-run result CAS
  -> external_effect_job only (no provider call in internal-event worker)
```

## 状态契约

自动 due 只有：

- `pending` 且未被有效 lease 持有；
- `failed_retryable` 且到期、未被有效 lease 持有；
- `running` 且 lease 超过 5 分钟。

以下状态绝不被定时 worker 自动领取：

- `failed_terminal`；
- `blocked`；
- `succeeded`；
- `skipped`。

`failed_terminal/blocked` 只能通过带 actor hash 和必填 reason 的人工 retry/skip。人工操作写 attempt audit，但不伪增一次 consumer 执行 attempt。

## CAS 与崩溃恢复

- 每次 claim 生成新的 `lease_token`，不能只依赖 `locked_by`。
- attempt insert 和 run result 在一个事务内校验 `status=running AND lease_token=:expected`。
- lost lease 返回 `lost_lease`；不插 attempt、不覆盖状态。
- relay claim 后崩溃时，超时 `running` outbox 可被新 lease 领取。
- relay 事务中任一点失败都会整体回滚；重复 relay 由 event/run 唯一键收敛。

## Worker 进程语义

以下任一项出现时顶层 `ok=false`、`exit_code=1`：

- outbox relay retryable/terminal/lost lease/unhandled；
- consumer `failed_retryable/failed_terminal/blocked`；
- consumer lost lease；
- repository/worker 未处理异常。

空队列、全部 succeeded/skipped 为 exit 0；dry-run 永远不执行且 exit 0。

## Migration

`0099_internal_event_outbox_and_consumer_lease` 是 expand-only：

- 新增技术表 `internal_event_outbox`；
- `internal_event_consumer_run.lease_token`；
- partial due indexes；
- attempt status 增加 `manual_retry`。

回滚代码时表和列可以安全保留；停止 worker 即可暂停 relay/consumer，不需要删除数据。

## 对账与修复

`scripts/ops/reconcile_internal_event_outbox.py` 默认只输出计数：

- paid order 缺 outbox；
- relayed outbox 缺 event；
- payment event 缺注册 consumer-run；
- manual-only 状态和 automatic due；
- stale running outbox/run。

`--repair` 只补 outbox/event/run，不调用 handler、external effect worker 或 provider。输出不包含手机号、unionid、external_userid 或完整 payload。

## 无新功能声明

```text
User-visible capability delta: none
New product route/page/menu: none
New business metric/model: none
Existing behavior changed: yes — 修复原子性、状态机、lease 和 exit code
Security breaking change: no; manual action now requires auditable reason
Old path removed in this PR: yes — payment best-effort cross-connection event write
Rollback path: rollback release, stop worker, retain expand-only schema and pending outbox
```
