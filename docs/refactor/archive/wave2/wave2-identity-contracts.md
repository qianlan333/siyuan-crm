# Wave 2 Identity Contracts

日期：2026-04-19

## 1. 现状与约束

Wave 2 当前只处理 `identity` 这一条主线，不进入 `class_user` / `user_ops` / `routing_config` 代码实现。

本文件的目的不是改写 legacy 逻辑，而是先把 identity 的正式 application contract 命名清楚，供后续 PR 2 / PR 3 / PR 4 串行切换调用方时使用。

正式 application owner 统一约定为：

- `wecom_ability_service/application/identity_contact/queries.py`
- `wecom_ability_service/application/identity_contact/commands.py`

兼容原则：

- 先建 contract，再切 caller。
- PR 2 只建立 application skeleton 与 contract tests，不切调用方。
- PR 3 / PR 4 切调用方时，legacy symbol 先保留 wrapper，不破坏现有业务行为。
- 不允许把新逻辑重新塞回 `services.py`、legacy controller、`mcp_adapter.py` 或其他超大 service。

## 2. Contract 清单

### 2.1 `ResolvePersonIdentityQuery`

| 项目 | 内容 |
| --- | --- |
| contract 名称 | `ResolvePersonIdentityQuery` |
| 输入 DTO | `ResolvePersonIdentityQueryDTO { external_userid?: str, mobile?: str, unionid?: str, corp_id?: str, request_meta?: { operator?: str, source?: str, request_id?: str } }` |
| 输出 DTO | `ResolvePersonIdentityResultDTO { person_id?: int, mobile: str, external_userid: str, unionid: str, openid: str, customer_name: str, owner_userid: str, remark: str, follow_user_userid: str, signup_status: str, is_bound: bool }` |
| 当前 legacy 入口 | `wecom_ability_service/services.py::resolve_person_identity` -> `wecom_ability_service/domains/identity/service.py::resolve_person_identity` |
| 直接调用方 | `wecom_ability_service/http/identity.py` |
| 跨 context 副作用 | 无写副作用；但当前结果带 `signup_status`，会额外读取报名/班级侧状态作为只读补充 |
| 禁止绕过的旧入口 | `services.resolve_person_identity`、`domains.identity.service.resolve_person_identity`、controller 直连 identity repo |
| 兼容策略 | PR 2 先提供 query wrapper；PR 3 再把 `http/identity.py` 切到 query；返回字段继续保持当前 `/api/identity/resolve` contract |
| 推荐切换顺序 | PR 2 建 skeleton 与 contract test -> PR 3 切 `http/identity.py` |

### 2.2 `GetContactBindingStatusQuery`

| 项目 | 内容 |
| --- | --- |
| contract 名称 | `GetContactBindingStatusQuery` |
| 输入 DTO | `GetContactBindingStatusQueryDTO { external_userid: str, owner_userid?: str, request_meta?: { operator?: str, source?: str, request_id?: str } }` |
| 输出 DTO | `GetContactBindingStatusResultDTO { is_bound: bool, person_id?: int, external_userid: str, owner_userid: str, customer_name: str, remark: str, display_name: str, mobile?: str, third_party_user_id?: str, first_bound_by_userid?: str, first_owner_userid?: str, last_owner_userid?: str, created_at?: str, updated_at?: str }` |
| 当前 legacy 入口 | `wecom_ability_service/services.py::get_contact_binding_status` -> `wecom_ability_service/domains/identity/service.py::get_contact_binding_status` |
| 直接调用方 | `wecom_ability_service/http/sidebar.py` |
| 跨 context 副作用 | 无写副作用；会通过 sidebar contact profile loader 读取 contacts / user-ops 侧展示字段 |
| 禁止绕过的旧入口 | `services.get_contact_binding_status`、`domains.identity.service.get_contact_binding_status`、controller 直连 binding repo |
| 兼容策略 | 继续保留 `owner_userid` 作为可选输入，保持 `is_bound`、`person_id`、`third_party_user_id` 等核心 key 不变 |
| 推荐切换顺序 | PR 2 建 query -> PR 3 切 `http/sidebar.py` |

### 2.3 `BindExternalContactIdentityCommand`

| 项目 | 内容 |
| --- | --- |
| contract 名称 | `BindExternalContactIdentityCommand` |
| 输入 DTO | `BindExternalContactIdentityCommandDTO { external_userid: str, mobile?: str, openid?: str, unionid?: str, owner_userid?: str, bind_by_userid?: str, force_rebind?: bool, corp_id?: str, request_meta?: { operator?: str, source?: str, request_id?: str } }` |
| 输出 DTO | `BindExternalContactIdentityResultDTO { ok: bool, binding: { person_id?: int, external_userid: str, mobile?: str, owner_userid?: str, third_party_user_id?: str, third_party_sync_status?: str, third_party_sync_error?: str, lead_pool_merge?: object, unionid?: str, openid?: str }, warnings: list[str] }` |
| 当前 legacy 入口 | `wecom_ability_service/services.py::bind_mobile_to_external_contact`、`wecom_ability_service/services.py::bind_openid_to_external_contact`，底层分别委托 `domains/identity/service.py::bind_mobile_to_external_contact` 与 `bind_openid_to_external_contact` |
| 直接调用方 | `wecom_ability_service/http/sidebar.py::sidebar_bind_mobile`、`wecom_ability_service/domains/questionnaire/service.py::apply_questionnaire_mobile_binding`、`wecom_ability_service/domains/questionnaire/service.py` 提交流程中的 `bind_openid_to_external_contact` 回填 |
| 跨 context 副作用 | mobile 绑定当前会顺带解析 owner、同步 third-party user id、合并 `user_ops_lead_pool_*`；questionnaire 路径还会回填 submission identity |
| 禁止绕过的旧入口 | `services.bind_mobile_to_external_contact`、`services.bind_openid_to_external_contact`、`domains.identity.service.bind_mobile_to_external_contact`、`domains.identity.service.bind_openid_to_external_contact` |
| 兼容策略 | PR 2 先做 command shell，内部继续 delegate 到现有 mobile/openid 绑定实现；PR 3 先切 sidebar，再切 questionnaire；保留现有异常语义与返回 key |
| 推荐切换顺序 | PR 2 建 command -> PR 3 先切 `http/sidebar.py` -> PR 3 再切 questionnaire mobile bind -> PR 3 最后切 questionnaire openid 回填 |

### 2.4 `ResolveExternalContactIdentityQuery`

| 项目 | 内容 |
| --- | --- |
| contract 名称 | `ResolveExternalContactIdentityQuery` |
| 输入 DTO | `ResolveExternalContactIdentityQueryDTO { corp_id?: str, external_userid?: str, unionid?: str, openid?: str, request_meta?: { operator?: str, source?: str, request_id?: str } }` |
| 输出 DTO | `ResolveExternalContactIdentityResultDTO { identity_map_id?: int, corp_id?: str, external_userid?: str, unionid?: str, openid?: str, follow_user_userid?: str, name?: str, status?: str, raw_profile?: object }` |
| 当前 legacy 入口 | `wecom_ability_service/domains/identity/service.py::resolve_external_contact_identity` |
| 直接调用方 | `wecom_ability_service/domains/questionnaire/service.py::resolve_questionnaire_submit_identity`、`wecom_ability_service/http/sync_support.py::_sync_external_contact_identity_map` |
| 跨 context 副作用 | 无写副作用；当前主要作为 questionnaire 去重和 sync 增量判断的只读前置 |
| 禁止绕过的旧入口 | `domains.identity.service.resolve_external_contact_identity`、`services.resolve_external_contact_identity` 风格新增 shim |
| 兼容策略 | PR 2 先提供 query；PR 3 切 questionnaire；PR 4 再切 `http/sync_support.py` |
| 推荐切换顺序 | PR 2 建 query -> PR 3 切 questionnaire -> PR 4 切 sync support |

### 2.5 `UpsertExternalContactIdentityCommand`

| 项目 | 内容 |
| --- | --- |
| contract 名称 | `UpsertExternalContactIdentityCommand` |
| 输入 DTO | `UpsertExternalContactIdentityCommandDTO { record: { corp_id: str, external_userid: str, unionid?: str, openid?: str, follow_user_userid?: str, name?: str, status?: str, raw_profile?: object }, request_meta?: { operator?: str, source?: str, request_id?: str } }` |
| 输出 DTO | `UpsertExternalContactIdentityResultDTO { ok: bool, identity_map_id?: int, external_userid: str, status?: str }` |
| 当前 legacy 入口 | `wecom_ability_service/services.py::upsert_external_contact_identity` -> `wecom_ability_service/domains/identity/service.py::upsert_external_contact_identity` |
| 直接调用方 | `wecom_ability_service/http/background_jobs.py`、`wecom_ability_service/http/sync_support.py`、`wecom_ability_service/http/admin_support.py` |
| 跨 context 副作用 | 命令本身不应再夹带其他上下文副作用；现有 caller 链路仍会在其后串接 follow-user 替换、owner refresh、tag snapshot、customer pulse、automation conversion、user_ops 调度 |
| 禁止绕过的旧入口 | `services.upsert_external_contact_identity`、`domains.identity.service.upsert_external_contact_identity`、任何 callback/sync/admin 直接写 repo |
| 兼容策略 | PR 2 做 command wrapper，保持 record payload 不变；PR 4 切 background/sync/admin support |
| 推荐切换顺序 | PR 2 建 command -> PR 4 切 `background_jobs.py`、`sync_support.py`、`admin_support.py` |

### 2.6 `ReplaceFollowUsersCommand`

| 项目 | 内容 |
| --- | --- |
| contract 名称 | `ReplaceFollowUsersCommand` |
| 输入 DTO | `ReplaceFollowUsersCommandDTO { corp_id: str, external_userid: str, follow_users: list[object], preferred_userid?: str, request_meta?: { operator?: str, source?: str, request_id?: str } }` |
| 输出 DTO | `ReplaceFollowUsersResultDTO { ok: bool, external_userid: str, primary_userid?: str, replaced_count?: int }` |
| 当前 legacy 入口 | `wecom_ability_service/services.py::replace_external_contact_follow_users` -> `wecom_ability_service/domains/identity/service.py::replace_external_contact_follow_users` |
| 直接调用方 | `wecom_ability_service/http/background_jobs.py`、`wecom_ability_service/http/sync_support.py`、`wecom_ability_service/http/admin_support.py` |
| 跨 context 副作用 | 命令本体不应承接其他 context 写入；当前 caller 通常在其后继续做 owner refresh、tag snapshot 清理或 customer pulse 触发 |
| 禁止绕过的旧入口 | `services.replace_external_contact_follow_users`、`domains.identity.service.replace_external_contact_follow_users`、callback/sync/admin support 直连 repo |
| 兼容策略 | 先保持 `follow_users` 原始 schema 不变，避免破坏 callback / sync detail payload |
| 推荐切换顺序 | PR 2 建 command -> PR 4 切 background/sync/admin support |

### 2.7 `RefreshExternalContactIdentityOwnerCommand`

| 项目 | 内容 |
| --- | --- |
| contract 名称 | `RefreshExternalContactIdentityOwnerCommand` |
| 输入 DTO | `RefreshExternalContactIdentityOwnerCommandDTO { corp_id: str, external_userid: str, request_meta?: { operator?: str, source?: str, request_id?: str } }` |
| 输出 DTO | `RefreshExternalContactIdentityOwnerResultDTO { ok: bool, external_userid: str, owner_userid?: str, follow_user_userid?: str }` |
| 当前 legacy 入口 | `wecom_ability_service/services.py::refresh_external_contact_identity_owner` -> `wecom_ability_service/domains/identity/service.py::refresh_external_contact_identity_owner` |
| 直接调用方 | `wecom_ability_service/http/background_jobs.py`、`wecom_ability_service/http/sync_support.py`、`wecom_ability_service/http/admin_support.py` |
| 跨 context 副作用 | owner 刷新会影响 customer center、admin support、user-ops 侧的 owner 展示与后续分配，但命令本身不应再负责这些补偿 |
| 禁止绕过的旧入口 | `services.refresh_external_contact_identity_owner`、`domains.identity.service.refresh_external_contact_identity_owner` |
| 兼容策略 | 保持“先 upsert/replace，再 refresh owner”的调用顺序不变；PR 4 只切调用 owner，不改 owner 选择规则 |
| 推荐切换顺序 | PR 2 建 command -> PR 4 切 background/sync/admin support |

### 2.8 `MarkExternalContactIdentityStatusCommand`

| 项目 | 内容 |
| --- | --- |
| contract 名称 | `MarkExternalContactIdentityStatusCommand` |
| 输入 DTO | `MarkExternalContactIdentityStatusCommandDTO { corp_id: str, external_userid: str, status: str, follow_user_userid?: str, request_meta?: { operator?: str, source?: str, request_id?: str } }` |
| 输出 DTO | `MarkExternalContactIdentityStatusResultDTO { ok: bool, external_userid: str, status: str }` |
| 当前 legacy 入口 | `wecom_ability_service/services.py::mark_external_contact_identity_status` -> `wecom_ability_service/domains/identity/service.py::mark_external_contact_identity_status` |
| 直接调用方 | `wecom_ability_service/http/background_jobs.py` |
| 跨 context 副作用 | 当前 callback 删除链路会在状态标记后继续触发 customer pulse 重算；该补偿先保留在 caller，不并入 identity command |
| 禁止绕过的旧入口 | `services.mark_external_contact_identity_status`、`domains.identity.service.mark_external_contact_identity_status` |
| 兼容策略 | 保持 `status="inactive"` 等现有枚举值和删除 callback 主流程不变 |
| 推荐切换顺序 | PR 2 建 command -> PR 4 切 `background_jobs.py` |

### 2.9 `MarkExternalContactFollowUserStatusCommand`

| 项目 | 内容 |
| --- | --- |
| contract 名称 | `MarkExternalContactFollowUserStatusCommand` |
| 输入 DTO | `MarkExternalContactFollowUserStatusCommandDTO { corp_id: str, external_userid: str, user_id?: str, status: str, request_meta?: { operator?: str, source?: str, request_id?: str } }` |
| 输出 DTO | `MarkExternalContactFollowUserStatusResultDTO { ok: bool, external_userid: str, user_id?: str, status: str }` |
| 当前 legacy 入口 | `wecom_ability_service/services.py::mark_external_contact_follow_user_status` -> `wecom_ability_service/domains/identity/service.py::mark_external_contact_follow_user_status` |
| 直接调用方 | `wecom_ability_service/http/background_jobs.py` |
| 跨 context 副作用 | 当前主要服务于 callback 删除 / 失效生命周期；owner refresh 与 customer pulse 仍由 caller 继续触发 |
| 禁止绕过的旧入口 | `services.mark_external_contact_follow_user_status`、`domains.identity.service.mark_external_contact_follow_user_status` |
| 兼容策略 | 保持 `del_external_contact` 与 `del_follow_user` 两条 callback 语义不变 |
| 推荐切换顺序 | PR 2 建 command -> PR 4 切 `background_jobs.py` |

### 2.10 `CountExternalContactIdentityMapsQuery`

| 项目 | 内容 |
| --- | --- |
| contract 名称 | `CountExternalContactIdentityMapsQuery` |
| 输入 DTO | `CountExternalContactIdentityMapsQueryDTO { request_meta?: { operator?: str, source?: str, request_id?: str } }` |
| 输出 DTO | `CountExternalContactIdentityMapsResultDTO { identity_map_total: int }` |
| 当前 legacy 入口 | `wecom_ability_service/domains/identity/service.py::count_external_contact_identity_maps` |
| 直接调用方 | `wecom_ability_service/http/sync_support.py` |
| 跨 context 副作用 | 无 |
| 禁止绕过的旧入口 | `domains.identity.service.count_external_contact_identity_maps`、controller 直连 identity repo 聚合数 |
| 兼容策略 | 保持 sync support 返回中的 `identity_map_total` key 不变 |
| 推荐切换顺序 | PR 2 建 query -> PR 4 切 `sync_support.py` |

### 2.11 `GetPrimaryFollowUserUseridQuery`

| 项目 | 内容 |
| --- | --- |
| contract 名称 | `GetPrimaryFollowUserUseridQuery` |
| 输入 DTO | `GetPrimaryFollowUserUseridQueryDTO { external_userid: str, corp_id?: str, request_meta?: { operator?: str, source?: str, request_id?: str } }` |
| 输出 DTO | `GetPrimaryFollowUserUseridResultDTO { primary_follow_user_userid: str, resolved_from: str }` |
| 当前 legacy 入口 | `wecom_ability_service/services.py::get_primary_follow_user_userid` -> `wecom_ability_service/domains/identity/service.py::get_primary_follow_user_userid` |
| 直接调用方 | `wecom_ability_service/http/sidebar.py`、`wecom_ability_service/http/admin_support.py` |
| 跨 context 副作用 | 无写副作用；当前实现会依次回退读取 active follow-user、contact owner、identity map |
| 禁止绕过的旧入口 | `services.get_primary_follow_user_userid`、`domains.identity.service.get_primary_follow_user_userid` |
| 兼容策略 | application query 可返回 `resolved_from` 便于后续排障；旧调用方切换时仍保持空字符串语义兼容 |
| 推荐切换顺序 | PR 2 建 query -> PR 3 切 `sidebar.py` -> PR 4 切 `admin_support.py` |

## 3. 推荐 contract 分层

建议在 `application/identity_contact/` 中按以下方式放置：

- `queries.py`
  - `ResolvePersonIdentityQuery`
  - `GetContactBindingStatusQuery`
  - `ResolveExternalContactIdentityQuery`
  - `CountExternalContactIdentityMapsQuery`
  - `GetPrimaryFollowUserUseridQuery`
- `commands.py`
  - `BindExternalContactIdentityCommand`
  - `UpsertExternalContactIdentityCommand`
  - `ReplaceFollowUsersCommand`
  - `RefreshExternalContactIdentityOwnerCommand`
  - `MarkExternalContactIdentityStatusCommand`
  - `MarkExternalContactFollowUserStatusCommand`

## 4. 本轮不做的事

本文件明确不把以下逻辑并入 identity command：

- `class_user_status*` 写入
- `user_ops_lead_pool_*` 写入与 deferred jobs 调度
- `routing_rule_config` / `owner_role_map` 保存
- `questionnaire`、`automation_conversion`、`customer_pulse` 内部拆分

这些如果当前仍作为 caller 侧副作用存在，后续 PR 只允许“显式列出并暂时保留”，不允许静默继续扩张。
