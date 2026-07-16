# ADR: Internal Event 单一 Relay Owner 与 fan-out manifest

- 状态：Accepted
- 日期：2026-07-16
- 范围：P0 relay ownership + P1 fan-out completeness

## 背景

`InternalEventWorker.run_due()` 过去会先 relay 全局 `internal_event_outbox`，再按 event/consumer allowlist 执行 consumer。AI Audience scheduler 只注册自身 consumer，却同样具备 relay 能力；当它先抢到支付 outbox 时，会用局部 registry 创建不完整的 consumer-run 集合并把 outbox 标记为 `relayed`。pair allowlist 只能限制执行，不能证明 fan-out 完整，也不能解决多个 relay 进程之间的竞态。

## 决策

1. 所有 `InternalEventWorker` 默认 `consumer_only`，不能实例化或调用 outbox relay。
2. 只有 `scripts/run_internal_event_worker.py` 显式构造常驻 runtime 的 `relay_role="owner"`；生产 runtime manifest 中也只能声明一个 owner。AI Audience scheduler 显式为 `consumer_only`。人工执行 `reconcile_internal_event_outbox.py --repair` 是受控、短生命周期的技术修复入口，使用同一 sealed canonical registry，不构成第二个定时 relay runtime。
3. Canonical composition 构建完整 consumer registry 后 seal。Seal 后禁止新增 consumer，或修改 consumer type/max attempts；允许同名同契约的 handler 重绑定，因为 handler 不是 fan-out 形状的一部分。
4. Relay 为每个 event type 生成排序、版本化、SHA-256 标识的 manifest，包含 consumer name/type/max attempts。
5. 同一数据库事务内完成：创建或取得 event、首次绑定 manifest、幂等创建全部 consumer-run、校验实际 consumer 名集合与 manifest 完全相等、最后把 outbox 标记为 `relayed`。manifest 不一致或 run 集合不完整时事务失败，outbox 进入可重试失败流程。
6. Reconciliation 对 manifest-backed event 只按该事件已存 manifest 补缺，不调用 handler、不增加 attempt、不创建当前 registry 新增但旧 manifest 未声明的 consumer。仅对切换点后的 manifest-less 旧 payment event 使用当前 canonical registry 兼容回退。

## 安全边界

- Relay 和 reconciliation 只写内部技术表，不调用企微、支付、Webhook 等 provider。
- `webhook_order_paid_consumer` 仍只规划 `external_effect_job`；本决策不打开真实 Webhook 执行开关，不改变 External Effect worker 的审批与 allowlist 边界。
- 本 PR 不执行生产修复、不切换外部执行开关，也不删除旧数据。
- `0122_internal_event_fanout_manifest` 是 expand-only：旧 event 使用非空默认值兼容读取，新的 manifest 仅在 relay 时绑定。

## 故障模式与可观测性

- 非 owner worker 返回 `relay_role=consumer_only`、`outbox_relay.enabled=false`，outbox 保持待处理。
- 未 seal/局部 registry 在 relay 构造阶段 fail closed。
- 同一幂等 event 绑定不同 manifest 时返回 `internal_event_fanout_manifest_mismatch`，不会标记 outbox relayed。
- 缺少或多出 consumer-run 时返回 `internal_event_fanout_incomplete`。
- 对账输出区分 manifest-backed 与 manifest-less 缺口；manifest 校验失败时不回退并报告 `manifest_validation_error_count`。

## 发布与回滚

发布顺序保持现有 GitHub/Alembic 流程：先执行 `alembic upgrade head`，再安装并启动 runtime units。验收时确认生产 runtime manifest 仅有一个 owner、AI Audience 为 consumer-only，并运行 count-only reconciliation。

应用回滚到上一版本时可保留 `0122` 列和索引；其默认值对旧代码无破坏。若 owner 异常，停止 internal-event timer，保留 pending/failed outbox，禁止手工删行或把 terminal 状态直接改回 pending。修复或回滚应用后再恢复 canonical timer。

## 后续

P2 可增加 manifest 演进策略、历史 manifest 数据治理和 owner lease/告警，但不得重新赋予 scoped scheduler 全局 relay 能力。
