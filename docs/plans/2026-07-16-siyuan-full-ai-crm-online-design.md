# 思媛完整同步 AI-CRM 主线并恢复生产能力设计

## 目标

让 `qianlan333/siyuan-crm` 在保留思媛域名、验证文件、数据库和迁移交接资料的前提下，完整吸收 AI-CRM 最新 `main` 的业务能力，并让主线声明的生产 worker、队列消费者与已批准企微外部动作在思媛生产环境真实运行。

## 方案比较

### 方案 A：主线增量同步 + 主线运行时清单落地（采用）

从思媛当前已经同步的 AI-CRM 边界 `08aec40f` 继续应用到最新 `f38339f6` 的完整增量，原样复用上游服务周期成员网格、分享权限、前端资源、迁移、路由清单和测试。运行时部分不复制 AI-CRM 的测试环境/人工晋级工作流，而是把上游 `deploy/production_runtime_units.json`、systemd 单元和运行时管理器接入思媛现有的 merge-to-production 流程。这样既保持能力一致，也不会把 AI-CRM 的域名、测试服务器或生产 IP 带入思媛。

### 方案 B：只修渠道码 worker

仅安装 callback inbox worker 和 external effect worker，改动最小，但不能满足“所有能力完全搬过来”，也会继续遗漏 internal event、identity resolution、customer read model、AI audience、订单对账等主线 worker，因此不采用。

### 方案 C：原样复制 AI-CRM 全部部署工作流

代码和流程表面最一致，但上游工作流绑定 AI-CRM 的 id-dev、正式域名和人工确认目标，直接复制会把思媛部署指向错误环境，因此不采用。

## 架构与数据流

生产入口仍由 `openclaw-wecom-postgres.service` 承载 AI-CRM Next。部署完成 Web 健康检查后，运行时管理器按主线 manifest 安装并启用 callback ingress、callback inbox worker、external effect、internal event、identity resolution、customer read model、automation ops、AI audience 和订单对账等单元，同时移除已退休的 timer/service。

企微执行只开启架构已批准的 effect types；Payment、OAuth、OpenClaw、MCP、Webhook 等未批准真实外呼继续保持 blocked。渠道码链路恢复为：企微回调持久化 → callback worker 消费 → channel_entry 生成效果任务 → effect worker/实时 gate 调用企微 → attempt 与 effect log 可审计。

思媛专属 overlay 保留：`README.md`、`.env.example`、企业微信验证文件、验证文件路由、`scripts/siyuan_migration/`、思媛迁移报告与现有数据库迁移历史。前端不重新设计，直接复用 AI-CRM 主线现有 service-period member-grid 页面、脚本、样式和 API 合同。

## 发布与回滚

发布走中文 PR、CI Fast、合并后自动生产部署。部署前记录原 SHA；若 schema、Web 健康、运行时安装或验证失败，工作流失败并保留 GitHub/服务日志，生产回滚到上一 release SHA。历史积压只在新 runtime 健康后由幂等 worker 消费；过期 WelcomeCode 不承诺重放，但 fallback 私聊、标签和后续可重放效果按主线幂等策略执行。
