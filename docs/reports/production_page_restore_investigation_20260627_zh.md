# 生产页面与企微侧边栏加载失败调查报告

日期：2026-06-27
时区：Asia/Shanghai
生产主机：150.158.82.186
公网域名：https://www.youcangogogo.com

## 1. 结论摘要

2026-06-27 11:10-11:17 CST 左右，生产后台页面和企微侧边栏出现加载失败。直接原因不是数据库、主机 CPU、内存或 nginx 本身不可用，而是企微 callback 重试流量与正常页面/API 流量共用同一个 `127.0.0.1:5001` FastAPI/Uvicorn runtime。

事故窗口内，企微 callback POST 流量达到约 900-1200 次/分钟，导致 5001 upstream 出现连接重置、连接拒绝、超时和大量客户端 499。由于后台页面、侧边栏 API、企微 callback 都压在同一个进程上，callback 风暴把页面请求一起拖慢或拖挂。

当前页面恢复依赖的是生产 nginx 层 emergency quick ACK：对企微 callback POST 直接返回 `200 success`，不再转发给 5001 app。这能快速恢复页面可用性，但也意味着 callback 事件没有进入应用层验签、解密、入库、worker 处理链路。

所以当前状态应拆成两句话：

- 页面/侧边栏已临时恢复。
- 企微 callback 永久修复尚未完成，仍不能认为业务事件已被可靠处理。

## 2. 用户可见影响

用户看到的问题：

- 企微侧边栏加载不出来。
- 后台页面加载不出来或明显变慢。
- 部分 admin 页面请求超时或被 nginx 记录为 upstream 失败。

受影响的典型路径：

- `/sidebar/bind-mobile`
- `/api/sidebar/v2/*`
- `/admin/automation-conversion`
- `/wecom/external-contact/callback`
- `/api/wecom/events`

## 3. 时间线

| 时间 CST | 事件 |
| --- | --- |
| 11:10-11:17 | callback POST 重试风暴集中出现，每分钟约 900-1200 个 callback 请求。 |
| 11:10-11:17 | nginx 记录大量 upstream reset/refused/timeout 和客户端 499。 |
| 11:14、11:15 | `/admin/automation-conversion` 出现页面请求超时证据。 |
| 11:17 后 | emergency quick ACK 生效后，callback POST 不再进入 app，页面逐步恢复。 |
| 15:49-15:56 | 复查确认 `/health`、侧边栏、admin 页面恢复可访问。 |
| 16:38 | 公网复查确认页面可用，但 `/admin/webhook-inbox` 仍 404，callback invalid POST 仍返回 `success`。 |
| 17:53-17:56 | 双 callback URL 复查，`/wecom/external-contact/callback` 和 `/api/wecom/events` invalid POST 都仍返回 `success`。 |
| 18:12 | 复查确认状态无变化：页面可用，永久修复未上线，deploy smoke 用同一公网 URL 会被拒绝，因为不能证明 5001/5002 隔离。 |
| 18:17 | 再次公网复查确认状态仍无变化：页面可用，`/admin/webhook-inbox` 仍 404，双 callback URL invalid POST 仍返回 `success`。 |
| 18:25 | 再次公网复查确认状态仍无变化：页面可用，webhook inbox 路由仍 404，双 callback URL invalid POST 仍返回 `success`。 |

## 4. 关键证据

事故窗口 nginx 错误日志采样：

| 错误类型 | 采样数量 |
| --- | ---: |
| `recv() failed (104: Connection reset by peer)` | 119 |
| `connect() failed (111: Connection refused)` | 65 |
| `upstream timed out` | 2 |
| 合计 | 186 |

事故窗口 callback POST 流量：

| 分钟 CST | callback POST 数 | 状态特征 |
| --- | ---: | --- |
| 11:10 | 890 | 802 x 499, 88 x 502 |
| 11:11 | 672 | 82 x 200, 582 x 499, 8 x 502 |
| 11:12 | 1027 | 1027 x 499 |
| 11:13 | 1025 | 1025 x 499 |
| 11:14 | 1233 | 1233 x 499 |
| 11:15 | 1089 | 1089 x 499 |
| 11:16 | 1142 | 1142 x 499 |
| 11:17 | 955 | 514 x 200, 352 x 499, 88 x 502, 1 x 301 |

公网复查证据：

| 检查项 | 当前结论 |
| --- | --- |
| `GET /health` | HTTP 200 |
| `GET /sidebar/bind-mobile` | HTTP 200 |
| `GET /admin/automation-conversion` | HTTP 200 登录页或可达响应 |
| `GET /admin/webhook-inbox` | HTTP 404 |
| `GET /api/admin/webhook-inbox/metrics` | HTTP 404 |
| invalid `POST /wecom/external-contact/callback?...` | HTTP 200，body 为 `success` |
| invalid `POST /api/wecom/events?...` | HTTP 200，body 为 `success` |

最近一次公网复查时间：2026-06-27 18:25 CST。`check_wecom_callback_public_state.py`
返回 `ok=false`、`user_facing_available=true`、
`admin_webhook_inbox_deployed=false`、`invalid_callback_plain_success=true`。
用同一个公网 URL 同时作为 web 和 ingress 的 deploy-smoke 也按预期失败，
其中 `base_urls_distinct=false`。

这些证据组合说明：

- 页面 runtime 当前能响应。
- webhook inbox 管理页面和 API 还没有部署到生产。
- callback invalid POST 没有被 app-level 验签/解密拒绝，而是在 nginx quick ACK 层直接返回成功。

## 5. 根因分析

### 5.1 直接原因

企微 callback 重试风暴占满或拖垮了共享 web runtime，导致正常页面请求无法稳定得到 5001 upstream 响应。

### 5.2 架构原因

1. 企微 callback ingress 和后台/侧边栏页面共用 `127.0.0.1:5001`。
2. callback POST 原链路在 ACK 前做了过多同步业务处理。
3. 生产没有独立 `127.0.0.1:5002` callback ingress runtime。
4. 生产没有通用 `webhook_inbox` 承接外部 webhook 原始输入。
5. 生产没有 callback worker 做异步处理、重试和 dead-letter。
6. 当前恢复手段是 nginx quick ACK，它保护页面，但牺牲 callback 业务处理可靠性。

## 6. 当前临时恢复机制

生产 nginx 目前对 callback POST 做 quick ACK，等价于：

```nginx
location = /wecom/external-contact/callback {
    default_type text/plain;
    if ($request_method = POST) {
        return 200 "success";
    }
    proxy_pass http://127.0.0.1:5001;
}

location = /api/wecom/events {
    default_type text/plain;
    if ($request_method = POST) {
        return 200 "success";
    }
    proxy_pass http://127.0.0.1:5001;
}
```

这个策略的好处：

- callback POST 不再消耗 5001。
- 页面和侧边栏能恢复。
- 可以作为短期止血方案。

这个策略的代价：

- 有效 callback 事件不会进入应用层。
- 不会创建 `webhook_inbox` 记录。
- worker 无法处理、重试或 dead-letter。
- 运营侧看不到 callback backlog 和失败明细。
- 如果长期保留，会掩盖真实业务事件丢失。

## 7. 永久修复方案

推荐架构是：

```text
Nginx
  |- /admin /sidebar /api normal web -> aicrm-web:5001
  `- /wecom callback              -> aicrm-wecom-ingress:5002

aicrm-wecom-ingress:5002
  -> verify signature
  -> decrypt callback
  -> build idempotency key
  -> ingest webhook_inbox
  -> ACK

webhook_inbox
  -> callback worker
  -> internal_event
  -> external_effect_job
```

关键原则：

- callback HTTP path 只做验签、解密、入库、ACK。
- 入库成功或重复事件返回 200。
- 验签失败或解密失败返回 400。
- DB 入库失败返回 500/503，不能假 ACK。
- worker 处理失败不能影响 HTTP ACK，由队列重试。
- 真实外发必须进入 `external_effect_job`，不能在 callback worker 或 internal event worker 里直接外呼。
- callback ingress、callback worker、internal event worker、external effect worker 必须与 web/admin/sidebar runtime 隔离。

## 8. 本地修复资产状态

本地仓库已经准备好的关键资产：

| 模块 | 状态 |
| --- | --- |
| `webhook_inbox` migration/repository/service/models | 本地完成 |
| callback fast ACK route | 本地完成 |
| isolated ingress app `127.0.0.1:5002` | 本地完成 |
| callback inbox worker | 本地完成 |
| retry/dead-letter/replay | 本地完成 |
| admin `/admin/webhook-inbox` 页面/API | 本地完成 |
| public-state / deploy-smoke / readiness checker | 本地完成 |
| nginx cutover template | 本地完成 |
| rollback drill evidence checker | 本地完成 |
| approved-window dry-run command plan | 本地完成 |

本地覆盖检查结果：

- `check_wecom_callback_objective_coverage.py`：`local_contract_ready=true`
- `production_completion_ready=false`
- 原因：生产 readiness JSON、压测证据、ingestion/processing 证据、rollback drill 证据仍未生成。

## 9. 生产仍缺的证据

永久修复不能标记完成，直到生产上拿到以下证据：

| 证据 | 通过标准 |
| --- | --- |
| schema | `alembic current` 显示 `0054_webhook_inbox` |
| 5002 ingress | `127.0.0.1:5002/health` 返回 2xx |
| worker | callback inbox worker timer active |
| nginx cutover | callback routes proxy 到 5002，不再有 `return 200 "success"` |
| invalid callback | 两个 callback URL 都返回 app-level 4xx，而不是 plain `success` |
| valid callback | 能写入 `webhook_inbox`，并 ACK |
| pressure | 1200/min callback 压测下页面不 5xx，延迟达标 |
| same-sample | pressure/ingestion/processing 三份 JSON 指向同一 idempotency key |
| worker isolation | 停 callback worker 时 callback 仍可 ACK，只增加 backlog |
| downstream isolation | 停 external effect worker 时 callback 和页面不受影响 |
| internal-event isolation | 停 internal event worker 时 callback 和页面不受影响 |
| admin ops | `/admin/webhook-inbox` 可看 metrics、retry、skip、dispatch、处理链 |
| rollback drill | 能恢复 quick ACK，并能重新切回 5002 permanent cutover |
| final readiness | `check_wecom_callback_permanent_fix_readiness.py` 全量通过 |

## 10. 推荐生产上线顺序

1. 申请生产发布窗口。
2. 部署代码。
3. 执行 `webhook_inbox` migration。
4. 启动 `openclaw-wecom-callback-ingress.service`。
5. 启动 `openclaw-wecom-callback-inbox-worker.timer`，先 dry-run。
6. 确认 `127.0.0.1:5002/health`。
7. 跑 deploy smoke，必须使用不同 base URL：`5001` web、`5002` ingress。
8. 手工合并 nginx callback route，把 POST 从 quick ACK 切到 5002。
9. `nginx -t` 后 reload nginx。
10. 跑 cutover checker。
11. 生成合法 callback sample。
12. 跑 1200/min pressure probe。
13. 生成 ingestion evidence、processing evidence。
14. 跑 worker/downstream/internal-event 三类 isolation canary。
15. 做 rollback drill：恢复 quick ACK，再重新切回 5002。
16. 生成 public-state、deploy-smoke、rollback evidence。
17. 跑 final readiness。
18. 只有 final readiness 全绿后，才移除“临时恢复”口径，改称“永久修复完成”。

## 11. 风险与控制

| 风险 | 控制方式 |
| --- | --- |
| 提前移除 quick ACK 后 callback 风暴复发 | 必须先启动 5002 ingress 和 worker，并通过 cutover checker |
| 假 ACK 导致业务事件丢失 | DB 入库失败必须返回 500/503，不允许 200 |
| worker 慢导致 ACK 慢 | worker 不在 HTTP path 内；HTTP path 只入库 |
| external effect 慢或失败 | 所有真实外发通过 `external_effect_job`，由独立 worker 处理 |
| internal event backlog | internal event worker 独立，页面和 callback ACK 不受影响 |
| 回滚不可用 | 发布窗口内必须完成 rollback drill 并保存证据 |
| 误判同一公网 URL 为 runtime 隔离 | deploy smoke 要求 `--web-base-url` 和 `--ingress-base-url` 不同 |

## 12. 当前建议

短期：

- 继续保留 quick ACK，确保页面可用。
- 不要把 callback HTTP 200 当成业务处理成功。
- 持续用 public-state checker 观察是否还是 emergency quick ACK。

中期：

- 安排生产发布窗口，按 `prepare_wecom_callback_ingress_cutover.py` 输出的 dry-run command plan 执行。
- 发布窗口里必须保留 nginx backup 和 rollback drill。

长期：

- 把所有 inbound webhook 都统一走 `webhook_inbox`。
- 把内部事实用 internal events 表达。
- 把真实外发统一纳入 external effects。
- 保持 runtime isolation，避免外部风暴再次拖死用户页面。

## 13. 相关文档

- `docs/reports/production_page_restore_investigation_20260627.md`
- `docs/reports/wecom_callback_permanent_fix_acceptance_audit_20260627.md`
- `docs/reports/production_wecom_callback_storm_20260627.md`
- `docs/runbooks/wecom_callback_storm.md`
- `docs/runbooks/wecom_callback_production_cutover_zh.md`
- `docs/deploy_runbook.md`
