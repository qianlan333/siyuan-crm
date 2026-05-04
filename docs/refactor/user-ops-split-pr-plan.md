# User Ops Split PR Plan

## 目标

- 在不改 caller、不改 contract、不改 schema 的前提下，逐步把 `wecom_ability_service/domains/user_ops/service.py` 从超大实现文件拆成若干内部模块。
- 每个 PR 都必须满足：
  - `application/user_ops/*` 无需改动或只做 import 路径微调
  - `domains/user_ops/service.py` 仍保留原函数名 facade
  - 任何一个 PR 回滚都不会影响 Wave 2 已完成的 caller cutover

## PR 1：Lead Pool Primitive Split

- 目标
  - 抽出 `user_ops_pool`，把 current/history、dedupe、activation patch、legacy reload 投影实现搬出 `service.py`
  - 保留 `write_user_ops_lead_pool_history` / `upsert_user_ops_lead_pool_member` 的 facade，但明确标为 internal primitive
- 涉及文件
  - `wecom_ability_service/domains/user_ops/service.py`
  - `wecom_ability_service/domains/user_ops/__init__.py`
  - 新增 `wecom_ability_service/domains/user_ops/pool_service.py`
- 不涉及文件
  - `wecom_ability_service/http/background_jobs.py`
  - `wecom_ability_service/http/sidebar.py`
  - `wecom_ability_service/http/admin_user_ops.py`
  - `wecom_ability_service/application/user_ops/*`
- 风险
  - lead-pool current/history 一致性最容易被破坏
  - duplicate row 清理和 activation patch 容易出现“当前表正确、历史表漏写”
- 回滚方式
  - 整体回退到 `service.py` 内联实现
  - 保持对外函数签名不变，只撤回内部 import/forward
- 必跑测试
  - `PYTHONPATH=. ./.venv311/bin/pytest tests/test_user_ops_lead_pool_helpers.py -q`
  - `PYTHONPATH=. ./.venv311/bin/pytest tests/test_user_ops_api.py -k "lead_pool or activation_status_source or migrate_legacy_user_ops_pool_to_lead_pool" -q`
  - `PYTHONPATH=. ./.venv311/bin/pytest tests/test_service_layer_layout.py tests/test_refactor_guardrails.py -q`

## PR 2：Deferred Jobs + Sidebar Split

- 目标
  - 抽出 `user_ops_deferred_job` 和 `user_ops_sidebar`
  - 把 due job orchestration、sidebar lead-pool status、sidebar class-term patch、mobile bind merge 从 `service.py` 迁走
- 涉及文件
  - `wecom_ability_service/domains/user_ops/service.py`
  - `wecom_ability_service/domains/user_ops/__init__.py`
  - 新增 `wecom_ability_service/domains/user_ops/deferred_job_service.py`
  - 新增 `wecom_ability_service/domains/user_ops/sidebar_service.py`
- 不涉及文件
  - `wecom_ability_service/http/admin_user_ops.py`
  - `wecom_ability_service/http/background_jobs.py`
  - `wecom_ability_service/http/sidebar.py`
  - `wecom_ability_service/application/user_ops/*`
- 风险
  - `_sidebar_contact_profile` / `_resolve_binding_owner_userid` / `_merge_lead_pool_after_mobile_bind` 仍被 identity legacy delegate 直接使用
  - deferred jobs 的 schedule/run 结果结构不能变
- 回滚方式
  - 只撤回两个新模块，并把 facade 重新改回本文件实现
  - 不回滚 caller 层
- 必跑测试
  - `PYTHONPATH=. ./.venv311/bin/pytest tests/test_admin_jobs_console.py -q`
  - `PYTHONPATH=. ./.venv311/bin/pytest tests/test_user_ops_api.py -k "sidebar_lead_pool or due_deferred_job or schedule_user_ops_auto_assign_class_term_job" -q`
  - `PYTHONPATH=. ./.venv311/bin/pytest tests/test_api.py -k "user_ops or sidebar or ops_status or admin_user_ops" -q`
  - `PYTHONPATH=. ./.venv311/bin/pytest tests/test_service_layer_layout.py tests/test_refactor_guardrails.py -q`

## PR 3：Class-Term + Tag Refresh Split

- 目标
  - 抽出 `user_ops_class_term` 和 `user_ops_tag_refresh`
  - 把 owner backfill、class-term mapping、full/scoped refresh、cross-owner snapshot cleanup 从 `service.py` 迁走
- 涉及文件
  - `wecom_ability_service/domains/user_ops/service.py`
  - `wecom_ability_service/domains/user_ops/__init__.py`
  - 新增 `wecom_ability_service/domains/user_ops/class_term_service.py`
  - 新增 `wecom_ability_service/domains/user_ops/tag_refresh_service.py`
- 不涉及文件
  - `wecom_ability_service/http/admin_user_ops.py`
  - `wecom_ability_service/http/background_jobs.py`
  - `wecom_ability_service/http/sidebar.py`
  - `wecom_ability_service/application/user_ops/*`
- 风险
  - 这块跨 context 依赖最多：`tags`、`identity_contact`、`class_user`、`routing_config`
  - refresh 行为若有回归，会表现成 customer 视图、class_user sync result、owner scoped snapshots 同时脏掉
- 回滚方式
  - 仅回退 `class_term_service.py` / `tag_refresh_service.py` 的提取
  - 保留 service facade 和 application contract 不动
- 必跑测试
  - `PYTHONPATH=. ./.venv311/bin/pytest tests/test_user_ops_api.py -k "refresh_contact_tags_for_external_userid or owner_backfill or backfill_class_term_for_owner or sync_user_ops_class_term_tag_definitions" -q`
  - `PYTHONPATH=. ./.venv311/bin/pytest tests/test_identity_application_contract.py tests/test_service_layer_layout.py tests/test_refactor_guardrails.py -q`
  - `PYTHONPATH=. ./.venv311/bin/pytest tests/test_http_registration_contract.py -q`

## PR 4：Import Pipeline Split

- 目标
  - 抽出 `user_ops_import`
  - 把 pasted text / xlsx 解析、import batch 创建、三类导入执行、legacy pool migration 从 `service.py` 迁走
- 涉及文件
  - `wecom_ability_service/domains/user_ops/service.py`
  - `wecom_ability_service/domains/user_ops/__init__.py`
  - 新增 `wecom_ability_service/domains/user_ops/import_service.py`
- 不涉及文件
  - `wecom_ability_service/http/admin_user_ops.py`
  - `wecom_ability_service/http/background_jobs.py`
  - `wecom_ability_service/http/sidebar.py`
  - `wecom_ability_service/application/user_ops/*`
- 风险
  - xlsx/text 解析和 lead-pool upsert 同时在一条链上，失败模式很多
  - `import_experience_leads` 当前自动化覆盖明显弱于 mobile/activation 两条链
- 回滚方式
  - 将 import 实现收回 `service.py`
  - 保留新文件但不再被 facade 调用，必要时完整删掉
- 必跑测试
  - `PYTHONPATH=. ./.venv311/bin/pytest tests/test_user_ops_api.py -k "import_mobile_class_terms or import_activation_status or activation_status_survives_lead_pool_reads" -q`
  - `PYTHONPATH=. ./.venv311/bin/pytest tests/test_user_ops_lead_pool_helpers.py -q`
  - `PYTHONPATH=. ./.venv311/bin/pytest tests/test_service_layer_layout.py tests/test_refactor_guardrails.py -q`
- 额外要求
  - 在进入这个 PR 前，先补一条非 deprecated 的 `ImportExperienceLeadsCommand` 冻结测试

## PR 5：Facade Trim + Explicit Bridge Audit

- 目标
  - 把 `domains/user_ops/service.py` 压缩成真正的 facade 文件
  - 明确只保留以下几类符号：
    - `domains/user_ops/__init__.py` 仍导出的兼容函数
    - identity 侧暂时仍在用的 bridge helper
    - `http/ops_runtime.py` / `domains/admin_dashboard/repo.py` 仍在读的 facade
- 涉及文件
  - `wecom_ability_service/domains/user_ops/service.py`
  - `wecom_ability_service/domains/user_ops/__init__.py`
  - 可选：`docs/refactor/wave2-user-ops-closeout.md`
- 不涉及文件
  - `application/user_ops/*`
  - `http/admin_user_ops.py`
  - `http/background_jobs.py`
  - `http/sidebar.py`
- 风险
  - 这里最容易误删兼容桥接，导致不是 user_ops caller 的别处静默失效
  - 典型风险点是 `application/identity_contact/_legacy_delegate.py` 与 `infra/user_ops_runtime.py`
- 回滚方式
  - 回退 facade trim
  - 不需要回退前面已经拆出去的实现文件
- 必跑测试
  - `PYTHONPATH=. ./.venv311/bin/pytest tests/test_user_ops_application_contract.py -q`
  - `PYTHONPATH=. ./.venv311/bin/pytest tests/test_user_ops_api.py tests/test_admin_jobs_console.py -q`
  - `PYTHONPATH=. ./.venv311/bin/pytest tests/test_api.py -k "user_ops or sidebar or ops_status or admin_user_ops" -q`
  - `PYTHONPATH=. ./.venv311/bin/pytest tests/test_http_registration_contract.py tests/test_service_layer_layout.py tests/test_refactor_guardrails.py -q`

## 执行顺序建议

1. 先拆 `user_ops_pool`
2. 再拆 `user_ops_deferred_job + user_ops_sidebar`
3. 然后拆 `user_ops_class_term + user_ops_tag_refresh`
4. 再拆 `user_ops_import`
5. 最后做 `service.py` facade trim

## 为什么是这个顺序

- `user_ops_pool` 是其它模块最底层的共享依赖，先抽出来，后续 PR 才能减少重复 move
- `deferred_job` 和 `sidebar` 虽然风险高，但边界相对清楚，且已完成 caller cutover，最适合第二批处理
- `class_term` / `tag_refresh` 跨 context 最重，应该放在已经有 pool/deferred/sidebar 边界之后
- `import` 最容易受底层 primitive 影响，放在 pool 稳定后拆最安全
- `service.py` 最后再瘦身，才能避免每个 PR 都在改 facade 结构
