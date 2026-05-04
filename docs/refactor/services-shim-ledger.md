# Services Shim Ledger

日期：2026-04-19

用途：

- 记录 `wecom_ability_service/services.py` 当前仍保留的 compatibility surface
- 说明为什么这些 symbol 还在
- 给出下一步迁移出口
- 标记是否属于 Wave 2 范围

范围说明：

- 本台账只覆盖“可被调用的兼容符号”和“明确保留的 monkeypatch / DI 锚点”。
- 不展开常量、异常类、简单 parser/helper alias，例如 `_parse_send_time`、`QUESTIONNAIRE_TYPES` 这类非迁移边界符号。

## 1. 已切到正式 application API 的兼容 wrapper

| Symbol | 当前保留原因 | 下一步迁移出口 | Wave 2 |
| --- | --- | --- | --- |
| `list_outbound_webhook_deliveries` | 仍有 legacy import 依赖 `services.py`，但内部已经转到正式 application query | 保留 shim；调用方逐步直连 `application/automation_engine/ListOutboundWebhookDeliveriesQuery` | 否 |
| `retry_outbound_webhook_delivery` | admin / legacy 兼容入口仍可能通过 `services.py` 使用 | 保留 shim；调用方逐步直连 `RetryOutboundWebhookDeliveryCommand` | 否 |
| `run_due_outbound_webhook_retries` | legacy jobs/admin 兼容入口 | 保留 shim；调用方逐步直连 `RunDueOutboundWebhookRetriesCommand` | 否 |
| `apply_activation_webhook` | 兼容旧调用点，不打断 activation webhook 处理链 | 保留 shim；调用方逐步直连 `ApplyActivationWebhookCommand` | 否 |
| `list_signup_conversion_batches` | 兼容 conversion/admin/MCP 历史 import | 保留 shim；调用方逐步直连 `ListSignupConversionBatchesQuery` | 否 |
| `get_signup_conversion_batch` | 兼容 conversion/admin/MCP 历史 import | 保留 shim；调用方逐步直连 `GetSignupConversionBatchQuery` | 否 |

## 2. Identity / Binding 兼容符号

| Symbol | 当前保留原因 | 下一步迁移出口 | Wave 2 |
| --- | --- | --- | --- |
| `resolve_person_identity` | 历史读取与绑定流程大量通过 `services.py` 解人/手机号/unionid | 新建 `application/identity/*` read/query contract | 是 |
| `get_contact_binding_status` | sidebar/questionnaire/admin 仍通过该符号读绑定状态 | 新建 `application/identity/*` read/query contract | 是 |
| `bind_mobile_to_external_contact` | 当前是 sidebar 与问卷手机号绑定的统一兼容入口 | 新建 `application/identity/*` command，收口绑定副作用 | 是 |
| `bind_openid_to_external_contact` | 问卷提交中仍有 openid rebound 兼容流程 | 新建 `application/identity/*` command | 是 |
| `resolve_external_contact_identity` | callback/sync/identity read 路径仍依赖 | 新建 `application/identity/*` query | 是 |
| `normalize_external_contact_identity` | callback/sync 支撑函数的兼容暴露点 | 收回 `domains/identity` 内部，外部改走 application API | 是 |
| `upsert_external_contact_identity` | callback / sync / admin support 仍直接通过该写入口落库 | 新建 `application/identity/*` command | 是 |
| `replace_external_contact_follow_users` | callback / sync / admin support 仍直接改 follow-user 绑定 | 新建 `application/identity/*` command | 是 |
| `mark_external_contact_follow_user_status` | 仍是 identity 写模型的一部分，服务层保留兼容可见性 | 收回 identity application write API | 是 |
| `refresh_external_contact_identity_owner` | callback / sync 后仍要刷新 owner 指向 | 新建 `application/identity/*` command | 是 |
| `mark_external_contact_identity_status` | 仍是 identity 生命周期写操作的一部分 | 收回 identity application write API | 是 |
| `count_external_contact_identity_maps` | 兼容 admin/support 统计读取 | 新建 `application/identity/*` query 或保留 domain read facade | 是 |
| `get_primary_follow_user_userid` | sidebar/admin 等读 owner 主跟进人仍经由 `services.py` | 新建 `application/identity/*` query | 是 |

## 3. Class User 兼容符号

| Symbol | 当前保留原因 | 下一步迁移出口 | Wave 2 |
| --- | --- | --- | --- |
| `get_class_user_status_definition` | 历史 controller / admin logic 仍直接读班级状态定义 | 新建 `application/class_user/*` query | 是 |
| `get_class_user_status_current` | 仍是 sidebar/admin/marketing read 兼容入口 | 新建 `application/class_user/*` query | 是 |
| `upsert_class_user_status_current` | 仍作为底层写 primitive 暴露在 shim 层 | 收回 `application/class_user/*` command 内部，不再直接透出 | 是 |
| `append_class_user_status_history` | 同上，仍是底层历史写 primitive | 收回 `application/class_user/*` command 内部 | 是 |
| `update_class_user_status_sync_result` | admin/manual tag sync 仍通过它记录 WeCom 同步结果 | 新建 `application/class_user/*` command | 是 |
| `list_class_user_status_history` | admin/support 仍通过 shim 读取历史 | 新建 `application/class_user/*` query | 是 |
| `apply_class_user_status_change` | admin manual status change、marketing automation、user_ops 都会用到 | 新建 `application/class_user/*` command，切断跨 context 直调 | 是 |
| `get_class_user_snapshot` | sidebar/admin 手工改状态前仍经该兼容入口取快照 | 新建 `application/class_user/*` query | 是 |
| `list_class_user_management_records` | admin class-user console 兼容读入口 | 新建 `application/class_user/*` read facade | 是 |
| `export_class_user_management_records` | admin export 兼容入口 | 新建 `application/class_user/*` read facade | 是 |
| `migrate_class_user_status_from_contact_tags` | 仍是班级状态初始化/迁移工具入口 | 迁入 `application/class_user/*` maintenance command | 是 |

## 4. Routing / Contact Context 兼容符号

| Symbol | 当前保留原因 | 下一步迁移出口 | Wave 2 |
| --- | --- | --- | --- |
| `get_owner_role` | contact enrich、routing resolve、legacy admin shell 仍会经 shim 读取 | 新建 `application/routing_config/*` query | 是 |
| `list_owner_role_map` | 同上，仍是 routing 读取兼容入口 | 新建 `application/routing_config/*` query | 是 |
| `get_routing_config` | 当前由 `services.py` 组装 owner role + signup rules + routing rules | 新建 `application/routing_config/*` query；避免继续放在 shim 层聚合 | 是 |
| `resolve_contact_routing_context` | 当前 contact enrich 仍通过 shim 计算 routing context | 新建 `application/routing_config/*` query/service | 是 |
| `get_contact_by_external_userid` | 仍是多处 legacy 详情读取入口，并带 tags/context enrich | 未来迁到 identity/contact read API；本轮不放进 Wave 2 主干 | 否 |
| `enrich_contact_context` | 仍是 contact read 聚合 helper 的兼容可见点 | 同上，迁到 identity/contact read API | 否 |

## 5. User Ops / Lead Pool 兼容符号

| Symbol | 当前保留原因 | 下一步迁移出口 | Wave 2 |
| --- | --- | --- | --- |
| `_user_ops_contact_client` | 明确保留的 monkeypatch / DI 锚点，测试仍依赖 | 收回 `application/user_ops/*` adapter 注入点 | 是 |
| `_resolve_third_party_user_id_by_mobile` | 仍是测试和绑定流程的 monkeypatch 锚点 | 收回 `application/user_ops/*` adapter 注入点 | 是 |
| `get_sidebar_lead_pool_status` | sidebar 仍通过 shim 读 lead-pool 视图 | 新建 `application/user_ops/*` query | 是 |
| `upsert_sidebar_lead_pool_class_term` | sidebar 仍通过 shim 改 class-term，并联动 tag/lead-pool | 新建 `application/user_ops/*` command | 是 |
| `reload_user_ops_pool` | 仍是 user-ops 维护动作入口 | 新建 `application/user_ops/*` maintenance command | 是 |
| `refresh_contact_tags_for_external_userid` | customer/admin/user_ops 仍通过 shim 触发标签刷新 | 新建 `application/user_ops/*` command 或 `identity`/`user_ops` 协调 command | 是 |
| `refresh_user_ops_contact_tags_for_external_userid` | user-ops 兼容写入口 | 新建 `application/user_ops/*` command | 是 |
| `refresh_user_ops_contact_tags_for_owner` | user-ops 兼容批处理入口 | 新建 `application/user_ops/*` command | 是 |
| `backfill_owner_class_terms_into_lead_pool` | admin console / internal endpoint 仍通过 shim 触发回填 | 新建 `application/user_ops/*` command | 是 |
| `backfill_class_term_for_owner` | 仍是 owner 维度回填动作 | 收到 `application/user_ops/*` command | 是 |
| `schedule_user_ops_auto_assign_class_term_job` | callback/background job 仍直接调度延迟作业 | 新建 `application/user_ops/*` command | 是 |
| `run_due_user_ops_deferred_jobs` | background/admin jobs/admin user-ops 仍直接跑 deferred jobs | 新建 `application/user_ops/*` command | 是 |
| `list_user_ops_pool` | admin user-ops 页面仍通过 shim 读取列表 | 新建 `application/user_ops/*` query | 是 |
| `get_user_ops_overview` | admin user-ops 页面概览读取 | 新建 `application/user_ops/*` query | 是 |
| `list_user_ops_history` | user-ops 管理视图仍依赖该历史读取 | 新建 `application/user_ops/*` query | 是 |
| `export_user_ops_pool` | admin user-ops 导出入口 | 新建 `application/user_ops/*` query/export facade | 是 |
| `set_user_ops_do_not_disturb` | admin user-ops 写入口 | 新建 `application/user_ops/*` command | 是 |
| `preview_user_ops_batch_send` | admin user-ops 预览写前检查入口 | 新建 `application/user_ops/*` command/query pair | 是 |
| `execute_user_ops_batch_send` | admin user-ops 批量发送写入口 | 新建 `application/user_ops/*` command | 是 |
| `list_user_ops_send_records` | admin user-ops 发送记录读取 | 新建 `application/user_ops/*` query | 是 |
| `get_user_ops_send_record_detail` | admin user-ops 发送详情读取 | 新建 `application/user_ops/*` query | 是 |
| `refresh_user_ops_send_record_status` | admin user-ops 发送状态刷新写入口 | 新建 `application/user_ops/*` command | 是 |
| `write_user_ops_lead_pool_history` | 仍是 lead-pool history 底层写 primitive | 收回 `application/user_ops/*` command 内部 | 是 |
| `upsert_user_ops_lead_pool_member` | 仍是 lead-pool current 主写入口 | 新建 `application/user_ops/*` command | 是 |
| `upsert_user_ops_huangxiaocan_activation_source` | activation source 兼容写入口 | 新建 `application/user_ops/*` command | 是 |
| `import_experience_leads` | admin 批量导入仍通过 shim | 新建 `application/user_ops/*` import command | 是 |
| `import_mobile_class_term_source` | admin 批量导入仍通过 shim | 新建 `application/user_ops/*` import command | 是 |
| `import_activation_status_source` | admin 批量导入仍通过 shim | 新建 `application/user_ops/*` import command | 是 |
| `migrate_legacy_user_ops_pool_to_lead_pool` | 仍是历史迁移工具入口 | 新建 `application/user_ops/*` maintenance command | 是 |

## 6. 仍留在 shim 层的非 Wave 2 兼容符号

| Symbol | 当前保留原因 | 下一步迁移出口 | Wave 2 |
| --- | --- | --- | --- |
| `get_messages_by_user` | archive read 仍有 legacy import | 后续单独归并到 archive/customer read 正式 API | 否 |
| `get_recent_messages_by_user` | 同上；MCP/customer automation 仍有旧依赖链 | 后续并入 archive/customer read 正式 API | 否 |
| `search_messages` | archive search 兼容入口 | 后续并入 archive/customer read 正式 API | 否 |
| `get_message_batch` | message batch read 兼容入口 | 后续并入 archive/admin jobs 正式 API | 否 |
| `resolve_questionnaire_submit_identity` | questionnaire submit 仍通过 shim 做身份解析 | 不在 Wave 2；后续单列 questionnaire scope | 否 |
| `has_questionnaire_submission` | questionnaire submit 兼容入口 | 同上 | 否 |
| `save_questionnaire_submission` | questionnaire 写路径兼容入口 | 同上 | 否 |
| `apply_questionnaire_mobile_binding` | questionnaire -> identity 写桥接仍在 shim 暴露 | 同上；待 questionnaire scope 一并收口 | 否 |
| `apply_questionnaire_submission_tags_to_scrm` | questionnaire -> SCRM 标签写桥接 | 同上 | 否 |
| `submit_questionnaire` | public questionnaire 兼容主入口 | 同上 | 否 |

## 7. 结论

`services.py` 当前已经是 compatibility shim，但还不是“小而薄到只剩少量符号”的最终状态。

Wave 2 的重点不是继续往 `services.py` 里塞东西，而是把上表中标记为 `Wave 2 = 是` 的符号逐步迁到正式 application write/read API，然后让 legacy import 只剩 wrapper。
