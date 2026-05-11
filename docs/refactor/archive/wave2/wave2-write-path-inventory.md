# Wave 2 Write Path Inventory

日期：2026-04-19

用途：

- 盘点当前仍在修改关键写面的位置
- 明确当前写入口、调用方、跨 context 情况
- 作为 Wave 2 application API 收口的输入

判定口径：

- “当前写入口”按实际落写函数记录
- “调用方”列出直接 HTTP / background / domain caller
- “跨 context”关注是否由别的业务上下文直接触发该写路径
- “需要 application API 收口”表示当前仍缺正式 application write/read contract

## 1. `person_id` / `external_userid` 绑定写面

| 数据面 | 当前写入口 | 直接调用方 | 是否跨 context | 是否需要 application API 收口 | 说明 |
| --- | --- | --- | --- | --- | --- |
| mobile -> `person_id` + `external_userid` 绑定 | `wecom_ability_service/services.py::bind_mobile_to_external_contact` -> `domains/identity/service.py::bind_mobile_to_external_contact` | `http/sidebar.py::sidebar_bind_mobile`、`domains/questionnaire/service.py::apply_questionnaire_mobile_binding` | 是 | 是 | 当前一条命令内还会解析 owner、同步 third-party user id、合并 lead pool |
| openid/unionid 反绑回 `external_userid` | `services.py::bind_openid_to_external_contact` -> `domains/identity/service.py::bind_openid_to_external_contact` | `domains/questionnaire/service.py::submit_questionnaire` | 是 | 是 | 问卷上下文直接触发 identity 写 |
| identity map upsert | `services.py::upsert_external_contact_identity` -> `domains/identity/service.py::upsert_external_contact_identity` | `http/background_jobs.py`、`http/sync_support.py`、`http/admin_support.py` | 是 | 是 | callback/sync/admin support 都能直接改 identity map |
| follow-user 全量替换 | `services.py::replace_external_contact_follow_users` -> `domains/identity/service.py::replace_external_contact_follow_users` | `http/background_jobs.py`、`http/sync_support.py`、`http/admin_support.py` | 是 | 是 | callback/sync/admin support 直接写 follow-user 关系 |
| identity owner 刷新 | `services.py::refresh_external_contact_identity_owner` -> `domains/identity/service.py::refresh_external_contact_identity_owner` | `http/background_jobs.py`、`http/sync_support.py`、`http/admin_support.py` | 是 | 是 | 通常紧跟 identity/follow-user 写后调用 |
| follow-user / identity 状态写 | `services.py::mark_external_contact_follow_user_status`、`services.py::mark_external_contact_identity_status` | 目前主要为 domain / callback 生命周期保留 | 是 | 是 | 仍是 binding 生命周期的一部分，但没有正式 application owner |

## 2. `class_user_status*` 写面

| 数据面 | 当前写入口 | 直接调用方 | 是否跨 context | 是否需要 application API 收口 | 说明 |
| --- | --- | --- | --- | --- | --- |
| 班级状态变更主入口 | `services.py::apply_class_user_status_change` -> `domains/class_user/service.py::apply_class_user_status_change` | `http/admin_support.py::_apply_signup_sidebar_tag`、`domains/marketing_automation/service.py`、`domains/user_ops/service.py` | 是 | 是 | 当前 admin、marketing、user_ops 都能直接改 class user 状态 |
| 班级状态 current 写 | `services.py::upsert_class_user_status_current` -> `domains/class_user/service.py::upsert_class_user_status_current` | 主要由 `domains/class_user/service.py` 内部调用 | 否 | 是 | 属于底层写 primitive，不应继续从 shim 暴露 |
| 班级状态 history 写 | `services.py::append_class_user_status_history` -> `domains/class_user/service.py::append_class_user_status_history` | 主要由 `domains/class_user/service.py` 内部调用 | 否 | 是 | 同上 |
| WeCom tag sync 结果写回 | `services.py::update_class_user_status_sync_result` -> `domains/class_user/service.py::update_class_user_status_sync_result` | `http/admin_support.py::_apply_signup_sidebar_tag` | 是 | 是 | 当前 admin 支持流程在状态变更后还直接回写 sync 结果 |
| contact-tags -> class-user 初始化迁移 | `services.py::migrate_class_user_status_from_contact_tags` -> `domains/class_user/service.py::migrate_class_user_status_from_contact_tags` | 维护/初始化场景 | 否 | 是 | 应迁成 maintenance command，不留在 shim |

## 3. `user_ops_pool*` 写面

| 数据面 | 当前写入口 | 直接调用方 | 是否跨 context | 是否需要 application API 收口 | 说明 |
| --- | --- | --- | --- | --- | --- |
| lead-pool current upsert | `services.py::upsert_user_ops_lead_pool_member` -> `domains/user_ops/service.py::upsert_user_ops_lead_pool_member` | `domains/user_ops/service.py` 内多处流程、导入流程、绑定后合并流程 | 是 | 是 | 是 `user_ops_lead_pool_current` 的核心写入口 |
| lead-pool history 写 | `services.py::write_user_ops_lead_pool_history` -> `domains/user_ops/service.py::write_user_ops_lead_pool_history` | `domains/user_ops/service.py` 内部 | 否 | 是 | 应收回到 application command 内部，不继续暴露在 shim |
| sidebar class-term patch | `services.py::upsert_sidebar_lead_pool_class_term` -> `domains/user_ops/service.py::upsert_sidebar_lead_pool_class_term` | `http/sidebar.py::sidebar_lead_pool_upsert_class_term` | 是 | 是 | sidebar 直接触发 user_ops 写，并伴随 tag/lead-pool 联动 |
| user-ops pool 重载 | `services.py::reload_user_ops_pool` -> `domains/user_ops/service.py::reload_user_ops_pool` | 维护路径 / 历史兼容调用 | 否 | 是 | 属于 maintenance write path |
| 标签刷新到 user-ops / contact snapshot | `services.py::refresh_contact_tags_for_external_userid` | customer/admin/user-ops 相关流程 | 是 | 是 | 当前既是 identity/contact 补偿动作，又影响 user_ops 视图 |
| user-ops owner 维度标签刷新 | `services.py::refresh_user_ops_contact_tags_for_owner` | user-ops 维护流程 | 否 | 是 | 应归 `user_ops` application command |
| owner 班期回填 | `services.py::backfill_owner_class_terms_into_lead_pool` -> `domains/user_ops/service.py::backfill_owner_class_terms_into_lead_pool` | `http/admin_user_ops.py`、`domains/admin_console/service.py` | 是 | 是 | admin/internal 都能直接触发批量写 |
| 单 owner 回填 | `services.py::backfill_class_term_for_owner` | user-ops 维护流程 | 否 | 是 | 应归 `user_ops` application command |
| 延迟作业调度 | `services.py::schedule_user_ops_auto_assign_class_term_job` -> `domains/user_ops/service.py::schedule_user_ops_auto_assign_class_term_job` | `http/background_jobs.py` | 是 | 是 | callback/background 直接创建 deferred job |
| 延迟作业执行 | `services.py::run_due_user_ops_deferred_jobs` -> `domains/user_ops/service.py::run_due_user_ops_deferred_jobs` | `http/background_jobs.py`、`http/admin_user_ops.py`、`domains/admin_jobs/service.py`、`domains/admin_console/service.py` | 是 | 是 | 多上下文共享同一执行入口 |
| 体验课导入 | `services.py::import_experience_leads` -> `domains/user_ops/service.py::import_experience_leads` | `http/admin_user_ops.py` | 是 | 是 | admin 导入直接写 user_ops 池 |
| 手机号班期导入 | `services.py::import_mobile_class_term_source` -> `domains/user_ops/service.py::import_mobile_class_term_source` | `http/admin_user_ops.py`、`domains/admin_console/service.py` | 是 | 是 | 兼容 admin console 与 V2 API 双入口 |
| 激活状态导入 | `services.py::import_activation_status_source` -> `domains/user_ops/service.py::import_activation_status_source` | `http/admin_user_ops.py`、`domains/admin_console/service.py` | 是 | 是 | 同上 |
| activation source upsert | `services.py::upsert_user_ops_huangxiaocan_activation_source` -> `domains/user_ops/service.py::upsert_user_ops_huangxiaocan_activation_source` | user-ops 导入/维护流程 | 是 | 是 | 会进一步回写 lead-pool current/history |
| legacy pool 迁移 | `services.py::migrate_legacy_user_ops_pool_to_lead_pool` | 迁移/维护流程 | 否 | 是 | 应作为 maintenance command 留给 Wave 2，而不是 shim |

## 4. `routing_rule_config` / `owner_role_map` 写面

| 数据面 | 当前写入口 | 直接调用方 | 是否跨 context | 是否需要 application API 收口 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `owner_role_map` 保存 | `domains/admin_config/service.py::save_owner_role_setting` -> `domains/routing_config/service.py::save_owner_role_map_item` | `http/admin_config.py::admin_config_save_owner_role`、`http/admin_config.py::api_admin_config_save_owner_role` | 是 | 是 | 当前写入口 owner 在 admin_config，实际数据 owner 在 routing_config |
| `routing_rule_config` 保存 | `domains/admin_config/service.py::save_routing_rule_setting` -> `domains/routing_config/service.py::save_routing_rule_config_item` | `http/admin_config.py::admin_config_save_routing_rule`、`http/admin_config.py::api_admin_config_save_routing_rule` | 是 | 是 | 同上 |
| owner-role 底层写 primitive | `domains/routing_config/service.py::save_owner_role_map_item` | 直接 caller 仅 `domains/admin_config/service.py` | 否 | 是 | 底层 domain 写 primitive，未来应只被 application command 调用 |
| routing-rule 底层写 primitive | `domains/routing_config/service.py::save_routing_rule_config_item` | 直接 caller 仅 `domains/admin_config/service.py` | 否 | 是 | 同上 |

## 5. 现状判断

当前这 4 组写面都有同一个问题：

- 真实 owner 在某个 domain，但 controller / callback / admin / scheduler 仍能通过 shim 或跨 context service 直接触发写入
- 一条命令里经常夹带别的 context 的副作用
- 正式 application write API 还没成为唯一入口

因此 Wave 2 的第一优先级不是“继续拆大文件”，而是：

1. 先把这些写入口命名化、正式化
2. 再切调用方
3. 最后再继续缩 `services.py` 和 legacy domain 直连
