# 运营闭环周维度文档调整

- 左侧入口按“本周发送数据 / 本周复盘明细 / 下周执行策略 / 历史发送记录”展示。
- 前三项继续复用同一个安全、只读 Markdown 阅读器，不新增编辑器、表单或业务字段拆分。
- 在 `operation_cycle_snapshot.v1.documents` 中新增可选 `retrospective_details`；旧快照默认空值并继续可读。
- `broadcast_details` 和 `execution_strategy` 保持原字段名，避免破坏已保存快照和 Agent 调用方。
- 历史发送记录继续通过精确 `cloud_orchestrator_plan` 引用复用 AI 助手原列表与详情页。
- 新增 Agent 使用手册并从根 `AGENTS.md` 建立能力入口，确保后续 Agent 能发现上报契约。
- 本次不新增 route、数据库迁移、外部调用或页面操作能力，回滚方式为回退本 PR。
