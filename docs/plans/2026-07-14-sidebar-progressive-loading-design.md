# 侧边栏渐进加载与连接池背压设计

## 问题与生产证据

2026-07-14 生产事故中，`/api/sidebar/v2/workbench` 于 09:28:59 成功后，浏览器在 160ms 后并发预取 `questionnaires`、`orders`、`periodic-orders`。面板请求默认自动重试一次，已完成结果才进入缓存，因此用户立即点击正在预取的页签会再发相同请求。生产连接池为 `pool_size=5`、`max_overflow=0`、`pool_timeout=5s`；09:29:52 起出现 PII 审计写入失败，09:30:57 起全站出现 QueuePool timeout。PostgreSQL 没有长事务、锁等待或长 SQL，故障边界是应用请求并发、请求级 session 释放时机和审计写连接竞争，而不是数据库锁。同日 JSSDK config 共出现 63 次成功请求，而侧边栏页面只有 28 次成功打开，说明启动链还会重复获取相同配置。

## 方案选择

采用渐进式按需加载，不扩大连接池、不把七个面板合并成大接口。首屏只加载客户头部和核心画像；删除问卷、订单、周期订单的立即预取。点击页签时只加载该面板；同一客户、同一 URL 的进行中请求共享 Promise，避免预取/点击或连续点击产生重复请求。面板请求不再自动重试，失败后展示明确的手动重试按钮。JSSDK config 同样按完整 URL 做页面内 single-flight 和 resolved cache；无客户 ID 与有客户 ID 的 URL 分开缓存，OAuth 整页跳转后缓存自然销毁。继续保留 `Cache-Control: no-store` 和仅页面内缓存，避免跨客户持久化 PII。

后端使用 FastAPI function-scoped DB dependency，使侧边栏 route handler 返回后、PII 审计执行前归还请求连接。`SidebarWorkbenchReadModel` 抽出轻量客户快照路径：完整 workbench 在快照上补 profile/workflow；问卷和订单只使用快照，不再反向构造完整 workbench。纯客户字段合并逻辑下沉到独立的 `sidebar_customer_resolution.py`，避免继续扩大已接近模块上限的 SQL/read-model 文件。侧边栏上下文查询增加不加载 timeline/recent messages 的模式，因为这些字段未被该页面消费。所有现有 URL、响应字段、owner token、owner scope 与 Next route owner 保持不变。

## 错误处理与安全边界

超时、5xx 或网络错误立即结束单次面板请求并清除 in-flight key；用户可在当前面板手动重试。旧页签响应可以写入内存数据，但只有当前 active tab 会重新渲染，避免覆盖用户刚切换的页面。失败不触发真实外呼。Capability owner 保持 `identity_contact`（页面/JSSDK）和 `customer_read_model`（读接口）；不新增 legacy facade、生产配置或 fixture fallback。

## 验证与回滚

行为测试必须证明首屏无重型预取、同一面板请求 single-flight、JSSDK 同 URL 只获取一次、面板无自动重放、失败后可手动重试、请求 session 在 PII 审计前关闭、轻量上下文不查询 timeline/messages。随后运行侧边栏 API、JSSDK、request-scope、Next owner 回归，完整架构门禁和性能 checker。生产发布后对比 `/health`、5001 backlog、QueuePool timeout、侧边栏各路请求数量与状态。回滚为上一发布版本；本改动不需要数据回滚。
