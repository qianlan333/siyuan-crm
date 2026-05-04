# Wave 2 Identity Callers Map

日期：2026-04-19

## 1. 目的

本文件只回答 3 个问题：

1. 现在哪些 caller 还在直接使用 legacy identity 入口。
2. 每个 caller 未来应该切到哪个正式 application contract。
3. 哪些跨 context 副作用本轮必须显式保留在 caller 侧，不能悄悄并进 identity command。

## 2. 调用方总表

| 调用方 | 当前 direct import / direct call | 当前职责 | 目标正式入口 | 暂时保留在 caller 侧的跨 context 副作用 | 推荐切换 PR |
| --- | --- | --- | --- | --- | --- |
| `wecom_ability_service/http/sidebar.py` | `get_contact_binding_status`、`get_primary_follow_user_userid`、`bind_mobile_to_external_contact` 来自 `services.py` | sidebar 读绑定状态、执行手机号绑定 | `GetContactBindingStatusQuery`、`GetPrimaryFollowUserUseridQuery`、`BindExternalContactIdentityCommand` | 无新增副作用；mobile bind 仍需保留 owner 解析、third-party user id 同步、lead-pool merge 的兼容行为，但这些应沉到 application command 内部 delegate | PR 3 |
| `wecom_ability_service/domains/questionnaire/service.py` | `resolve_external_contact_identity`、`bind_mobile_to_external_contact`、`bind_openid_to_external_contact` | questionnaire submit 身份识别与手机号/`openid` 回填 | `ResolveExternalContactIdentityQuery`、`BindExternalContactIdentityCommand` | questionnaire submission 写入、外部 webhook、SCRM apply log 仍留在 questionnaire；identity command 不负责这些补偿 | PR 3 |
| `wecom_ability_service/http/background_jobs.py` | `upsert_external_contact_identity`、`replace_external_contact_follow_users`、`refresh_external_contact_identity_owner`、`mark_external_contact_identity_status`、`mark_external_contact_follow_user_status` | callback 事件驱动的 identity map / follow-user / owner 状态更新 | `UpsertExternalContactIdentityCommand`、`ReplaceFollowUsersCommand`、`RefreshExternalContactIdentityOwnerCommand`、`MarkExternalContactIdentityStatusCommand`、`MarkExternalContactFollowUserStatusCommand` | `upsert_contacts`、`customer_pulse` 重算、`automation_conversion` 二维码处理、`schedule_user_ops_auto_assign_class_term_job` 先保留在 callback caller | PR 4 |
| `wecom_ability_service/http/sync_support.py` | `resolve_external_contact_identity`、`upsert_external_contact_identity`、`replace_external_contact_follow_users`、`refresh_external_contact_identity_owner`、`count_external_contact_identity_maps` | 全量/增量 sync 时刷新 identity map 与 follow-user 关系 | `ResolveExternalContactIdentityQuery`、`UpsertExternalContactIdentityCommand`、`ReplaceFollowUsersCommand`、`RefreshExternalContactIdentityOwnerCommand`、`CountExternalContactIdentityMapsQuery` | contact detail 拉取、tag snapshot 更新、contacts upsert 仍保留在 sync support | PR 4 |
| `wecom_ability_service/http/admin_support.py` | `upsert_external_contact_identity`、`replace_external_contact_follow_users`、`refresh_external_contact_identity_owner`、`get_primary_follow_user_userid` | admin support 的 live refresh / signup tag 相关 identity 刷新 | `UpsertExternalContactIdentityCommand`、`ReplaceFollowUsersCommand`、`RefreshExternalContactIdentityOwnerCommand`、`GetPrimaryFollowUserUseridQuery` | `save_tag_snapshot`、`remove_tag_snapshot`、`remove_tag_snapshots_for_other_users`、class-user management view-model 组装先留在 admin support | PR 4 |
| `wecom_ability_service/http/identity.py` | `resolve_person_identity` 来自 `services.py` | `/api/identity/resolve` 读接口 | `ResolvePersonIdentityQuery` | 无 | PR 3 |

## 3. 逐调用方说明

### 3.1 `http/sidebar.py`

当前 identity 相关入口：

- `sidebar_contact_binding_status()` -> `get_contact_binding_status()`
- `_sidebar_marketing_target_exists()` -> `get_primary_follow_user_userid()` + `get_contact_binding_status()`
- `sidebar_bind_mobile()` -> `bind_mobile_to_external_contact()`

切换口径：

- 不再从 `services.py` 进入 identity。
- `sidebar_bind_mobile()` 的 caller 仍然可以拿到当前绑定结果、`third_party_sync_status`、`lead_pool_merge` 等兼容字段。
- owner 缺省补全、third-party user id 同步失败降级、force rebind 逻辑全部留在 application command delegate，不回流到 controller。

### 3.2 `domains/questionnaire/service.py`

当前 identity 相关入口：

- `resolve_questionnaire_submit_identity()` -> `resolve_external_contact_identity()`
- `apply_questionnaire_mobile_binding()` -> `bind_mobile_to_external_contact(... force_rebind=True ...)`
- questionnaire submit 主流程在 `matched_by="unionid"` 且缺 `openid` 时调用 `bind_openid_to_external_contact()`

切换口径：

- questionnaire 继续保有“问卷提交上下文”的 owner，不把 submission / webhook / SCRM apply log 逻辑挪进 identity。
- `BindExternalContactIdentityCommand` 需要兼容 mobile bind 和 openid backfill 两种模式。
- questionnaire 的 identity 去重顺序必须显式冻结为：`unionid` -> `openid` -> `external_userid`。

### 3.3 `http/background_jobs.py`

当前 identity 写链：

- add/edit external contact:
  - `upsert_external_contact_identity()`
  - `replace_external_contact_follow_users()`
  - `refresh_external_contact_identity_owner()`
- delete / delete follow-user:
  - `mark_external_contact_identity_status()`
  - `mark_external_contact_follow_user_status()`
  - `refresh_external_contact_identity_owner()`

当前仍存在的跨 context 副作用：

- `upsert_contacts([normalized_contact])`
- `customer_pulse.enqueue_customer_pulse_recompute(...)`
- `handle_qrcode_enter_from_callback(...)`
- `schedule_user_ops_auto_assign_class_term_job(...)`

切换口径：

- PR 4 只把 identity 写路径 owner 切到 `application/identity_contact/*`。
- 上述非 identity 副作用先保留在 callback caller，并在 PR 输出中逐条列示。

### 3.4 `http/sync_support.py`

当前 identity 写链：

- 增量判断：`resolve_external_contact_identity()`
- 数据写入：`upsert_external_contact_identity()` + `replace_external_contact_follow_users()` + `refresh_external_contact_identity_owner()`
- 汇总输出：`count_external_contact_identity_maps()`

当前仍存在的跨 context 副作用：

- detail 拉取和 `upsert_contacts(...)`
- tag snapshot 保存 / 清理
- archive / contacts sync 统计汇总

切换口径：

- PR 4 不拆 sync_support 内部流程，只把 identity 读写入口正式化。
- `identity_map_total` 继续保留在 sync summary 中。

### 3.5 `http/admin_support.py`

当前 identity 写链：

- 刷 live data 时：
  - `upsert_external_contact_identity()`
  - `replace_external_contact_follow_users()`
  - `refresh_external_contact_identity_owner()`
- owner 回退时：
  - `get_primary_follow_user_userid()`

当前仍存在的跨 context 副作用：

- `save_tag_snapshot(...)`
- `remove_tag_snapshot(...)`
- `remove_tag_snapshots_for_other_users(...)`
- class-user management 读模型拼装

切换口径：

- PR 4 只把 identity map / follow-user / owner refresh 的 owner 收到 `application/identity_contact/*`。
- tag snapshot 仍归 admin support / tags 相关逻辑处理，不并入 identity command。

## 4. 禁止新增的旁路

从本调用方地图开始，禁止新增以下旁路：

- `http/sidebar.py` 新增 direct import `services.bind_mobile_to_external_contact`
- `domains/questionnaire/service.py` 新增 direct import `domains.identity.service.*`
- `http/background_jobs.py`、`http/sync_support.py`、`http/admin_support.py` 继续直接写 identity repo
- 新的 callback / sync / admin support 入口绕过 application contract，直接调 `services.py` identity 写函数

## 5. 切换顺序结论

推荐顺序固定为：

1. PR 2: 先建 application contract skeleton，不切任何 caller。
2. PR 3: 先切 `sidebar` + `questionnaire` + `/api/identity/resolve`。
3. PR 4: 再切 `background_jobs` + `sync_support` + `admin_support`。

原因：

- `sidebar` / `questionnaire` 更依赖绑定兼容行为，先切可以把“绑定 contract”稳住。
- callback / sync / admin support 写链条副作用更多，必须在 contract 已稳定后单独切，避免一个 PR 同时改绑定和同步两类逻辑。
