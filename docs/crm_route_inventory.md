# CRM Route Inventory

## 目标与原则

这份清单只做 CRM 底层能力的路由盘点，给后续 `customer_center`、`customer_timeline`、问卷协同和 internal auth 提供可信护栏。

本轮原则：

- 不改变任何现有 API path
- 不改变任何现有核心 JSON 字段
- 不改变现有业务语义
- “当前已实现”只认代码和 `create_app().url_map`
- “未来规划/预留”单独列出，不能混入现状

## 来源校验方式

本次 inventory 同时使用两层证据：

1. 运行时校验  
   通过 `create_app({...}).url_map.iter_rules()` 导出当前 Flask 已注册路由，确认 method + path + endpoint。

2. 源码校验  
   通过静态扫描 [routes.py](../wecom_ability_service/routes.py) 中 `@bp.route(...)` 装饰器，补充 handler 函数名与行号。

说明：

- “来源证据”列统一写成：`routes.py:行号 handler；url_map endpoint=...`
- 少数 customer_center / customer_timeline 路由的真正实现逻辑位于：
  - [customer_center/__init__.py](../wecom_ability_service/customer_center/__init__.py)
  - [customer_timeline/__init__.py](../wecom_ability_service/customer_timeline/__init__.py)

## Current Implemented Routes

### Ops / Settings / Archive

| Domain | Method | Path | 当前用途 | 是否为 customer_center / customer_timeline 输入 | 是否敏感 | 来源证据 |
| --- | --- | --- | --- | --- | --- | --- |
| ops | `GET` | `/health` | 服务存活检查 | 否 | 否 | `routes.py:1923 health；url_map endpoint=api.health` |
| ops | `GET` | `/api/ops/status` | 查看服务状态、同步状态、数据计数 | 否 | 是 | `routes.py:5698 ops_status；url_map endpoint=api.ops_status` |
| settings | `GET` | `/api/settings` | 读取当前配置快照 | 否 | 是 | `routes.py:1960 get_settings；url_map endpoint=api.get_settings` |
| settings | `PUT` | `/api/settings` | 更新当前配置 | 否 | 是 | `routes.py:1965 update_settings；url_map endpoint=api.update_settings` |
| admin | `POST` | `/api/init-db` | 初始化数据库 | 否 | 是 | `routes.py:1954 api_init_db；url_map endpoint=api.api_init_db` |
| archive | `GET` | `/archive/messages` | 读取指定时间窗口的会话存档消息 | 否，偏底层输入 | 是 | `routes.py:1940 archive_messages；url_map endpoint=api.archive_messages` |
| archive | `GET` | `/api/archive/health` | 检查会话存档 SDK 与配置状态 | 否 | 是 | `routes.py:5490 archive_health；url_map endpoint=api.archive_health` |
| archive | `POST` | `/api/archive/sync` | 手动触发会话存档同步 | 是，timeline 上游输入 | 是 | `routes.py:5500 archive_sync；url_map endpoint=api.archive_sync` |

### Contacts / Identity / Group Chats

| Domain | Method | Path | 当前用途 | 是否为 customer_center / customer_timeline 输入 | 是否敏感 | 来源证据 |
| --- | --- | --- | --- | --- | --- | --- |
| contacts | `GET` | `/api/contacts` | 读取联系人列表 | 是，customer_center 输入 | 是 | `routes.py:5598 list_contacts；url_map endpoint=api.list_contacts` |
| contacts | `GET` | `/api/contacts/<external_userid>` | 读取单客户详情 | 是，customer_center 输入 | 是 | `routes.py:5618 get_contact；url_map endpoint=api.get_contact` |
| contacts | `POST` | `/api/contacts/description` | 更新联系人 description | 否 | 是 | `routes.py:5637 update_contact_description；url_map endpoint=api.update_contact_description` |
| contacts | `POST` | `/api/contacts/full-sync` | 全量同步 contacts | 否 | 是 | `routes.py:5662 full_sync_contacts；url_map endpoint=api.full_sync_contacts` |
| contacts | `POST` | `/api/contacts/sync-new` | 同步新 contacts | 否 | 是 | `routes.py:5671 sync_new_contacts；url_map endpoint=api.sync_new_contacts` |
| contacts | `POST` | `/api/contacts/normalize-description` | 纠正 description 历史格式 | 否 | 是 | `routes.py:5680 normalize_contact_descriptions；url_map endpoint=api.normalize_contact_descriptions` |
| identity | `GET` | `/api/identity/resolve` | 通过 external_userid / mobile / unionid / openid 解析身份 | 是，customer_center 输入 | 是 | `routes.py:1912 api_identity_resolve；url_map endpoint=api.api_identity_resolve` |
| identity | `POST` | `/internal/wecom/external-contact/full-sync` | 全量同步外部联系人 identity 映射 | 否 | 是 | `routes.py:5689 full_sync_external_contact_identity；url_map endpoint=api.full_sync_external_contact_identity` |
| group_chats | `POST` | `/api/group-chats/full-sync` | 全量同步客户群目录 | 是，customer_center / timeline 输入 | 是 | `routes.py:5726 full_sync_group_chats；url_map endpoint=api.full_sync_group_chats` |
| group_chats | `POST` | `/api/group-chats/sync-new` | 增量同步客户群目录 | 是，customer_center / timeline 输入 | 是 | `routes.py:5735 sync_new_group_chats；url_map endpoint=api.sync_new_group_chats` |

### Messages / Tags / Tasks

| Domain | Method | Path | 当前用途 | 是否为 customer_center / customer_timeline 输入 | 是否敏感 | 来源证据 |
| --- | --- | --- | --- | --- | --- | --- |
| messages | `GET` | `/api/messages/<external_userid>` | 查询单客户消息全集 | 是，timeline 主输入 | 是 | `routes.py:5566 list_messages；url_map endpoint=api.list_messages` |
| messages | `GET` | `/api/messages/<external_userid>/recent` | 查询单客户最近消息 | 是，customer_center / timeline 输入 | 是 | `routes.py:5576 list_recent_messages；url_map endpoint=api.list_recent_messages` |
| messages | `GET` | `/api/messages/search` | 按关键词检索消息 | 是，timeline 输入 | 是 | `routes.py:5589 query_messages；url_map endpoint=api.query_messages` |
| tags | `GET` | `/api/tags` | 读取企微标签库 | 是，customer_center 标签上下文输入 | 是 | `routes.py:5878 list_tags；url_map endpoint=api.list_tags` |
| tags | `POST` | `/api/tags` | 创建企微标签 / 标签组 | 否 | 是 | `routes.py:5893 create_tag；url_map endpoint=api.create_tag` |
| tags | `POST` | `/api/tags/mark` | 给客户打标签 | 否 | 是 | `routes.py:5904 mark_tag；url_map endpoint=api.mark_tag` |
| tags | `POST` | `/api/tags/unmark` | 给客户移除标签 | 否 | 是 | `routes.py:5923 unmark_tag；url_map endpoint=api.unmark_tag` |
| tasks | `POST` | `/api/tasks/private-message` | 创建客户私信群发任务 | 否 | 是 | `routes.py:5863 create_private_message_task；url_map endpoint=api.create_private_message_task` |
| tasks | `POST` | `/api/tasks/moment` | 创建朋友圈任务 | 否 | 是 | `routes.py:5868 create_moment_task；url_map endpoint=api.create_moment_task` |
| tasks | `POST` | `/api/tasks/group-message` | 创建客户群群发任务 | 否 | 是 | `routes.py:5873 create_group_message_task；url_map endpoint=api.create_group_message_task` |

### Sidebar / Class User

| Domain | Method | Path | 当前用途 | 是否为 customer_center / customer_timeline 输入 | 是否敏感 | 来源证据 |
| --- | --- | --- | --- | --- | --- | --- |
| sidebar | `GET` | `/sidebar/bind-mobile` | 侧边栏手机号绑定页面入口 | 否 | 否 | `routes.py:1306 sidebar_bind_mobile_page；url_map endpoint=api.sidebar_bind_mobile_page` |
| sidebar | `GET` | `/api/sidebar/contact-binding-status` | 查询 external contact 的手机号绑定状态 | 是，customer_center 输入 | 是 | `routes.py:1817 sidebar_contact_binding_status；url_map endpoint=api.sidebar_contact_binding_status` |
| sidebar | `GET` | `/api/sidebar/jssdk-config` | 输出侧边栏 JSSDK 配置 | 否 | 中 | `routes.py:1830 sidebar_jssdk_config；url_map endpoint=api.sidebar_jssdk_config` |
| sidebar | `POST` | `/api/sidebar/bind-mobile` | 写入 external contact 与手机号绑定 | 否 | 是 | `routes.py:1856 sidebar_bind_mobile；url_map endpoint=api.sidebar_bind_mobile` |
| class_user | `GET` | `/api/sidebar/signup-tags/status` | 读取当前客户的报名状态定义与当前状态 | 是，customer_center 输入 | 是 | `routes.py:1875 sidebar_signup_tag_status；url_map endpoint=api.sidebar_signup_tag_status` |
| class_user | `POST` | `/api/sidebar/signup-tags/mark` | 修改报名标签状态 | 否 | 是 | `routes.py:1896 sidebar_signup_tag_mark；url_map endpoint=api.sidebar_signup_tag_mark` |
| admin/class_user | `POST` | `/api/admin/class-user-management/bootstrap` | 初始化 class_user 规则/数据 | 否 | 是 | `routes.py:1988 admin_class_user_management_bootstrap；url_map endpoint=api.admin_class_user_management_bootstrap` |
| admin/class_user | `POST` | `/api/admin/class-user-management/migrate` | 迁移 class_user 历史/现状数据 | 否 | 是 | `routes.py:1997 admin_class_user_management_migrate；url_map endpoint=api.admin_class_user_management_migrate` |
| admin/class_user | `GET` | `/api/admin/class-user-management` | 查看 class_user 当前管理视图 | 是，customer_center 输入 | 是 | `routes.py:2003 admin_class_user_management_list；url_map endpoint=api.admin_class_user_management_list` |
| admin/class_user | `GET` | `/api/admin/class-user-management/export` | 导出 class_user 数据 | 否 | 是 | `routes.py:2015 admin_class_user_management_export；url_map endpoint=api.admin_class_user_management_export` |
| admin/class_user | `GET` | `/api/admin/class-user-management/history` | 查看 class_user 历史 | 是，timeline 输入 | 是 | `routes.py:2033 admin_class_user_management_history；url_map endpoint=api.admin_class_user_management_history` |
| admin/class_user | `GET` | `/api/admin/wecom/tags` | admin 侧读取企微标签视图 | 否 | 是 | `routes.py:1980 admin_list_wecom_tags；url_map endpoint=api.admin_list_wecom_tags` |
| admin-ui | `GET` | `/admin/class-user-management/ui` | class_user 管理后台页面 | 否 | 是 | `routes.py:2116 admin_class_user_management_ui；url_map endpoint=api.admin_class_user_management_ui` |
| admin-ui | `GET` | `/admin/class-user-backoffice/ui` | class_user 新后台页面 | 否 | 是 | `routes.py:2420 admin_class_user_backoffice_ui；url_map endpoint=api.admin_class_user_backoffice_ui` |

### Questionnaire

| Domain | Method | Path | 当前用途 | 是否为 customer_center / customer_timeline 输入 | 是否敏感 | 来源证据 |
| --- | --- | --- | --- | --- | --- | --- |
| admin/questionnaire | `GET` | `/api/admin/questionnaires` | admin 问卷列表 | 否 | 是 | `routes.py:1975 admin_list_questionnaires；url_map endpoint=api.admin_list_questionnaires` |
| admin/questionnaire | `POST` | `/api/admin/questionnaires` | 创建问卷 | 否 | 是 | `routes.py:4721 admin_create_questionnaire；url_map endpoint=api.admin_create_questionnaire` |
| admin/questionnaire | `GET` | `/api/admin/questionnaires/preflight` | 问卷发布前检查 | 否 | 是 | `routes.py:2043 admin_questionnaires_preflight；url_map endpoint=api.admin_questionnaires_preflight` |
| admin/questionnaire | `GET` | `/api/admin/questionnaires/<int:questionnaire_id>` | 读取单个问卷详情 | 否 | 是 | `routes.py:4731 admin_get_questionnaire；url_map endpoint=api.admin_get_questionnaire` |
| admin/questionnaire | `PUT` | `/api/admin/questionnaires/<int:questionnaire_id>` | 更新问卷 | 否 | 是 | `routes.py:4749 admin_update_questionnaire；url_map endpoint=api.admin_update_questionnaire` |
| admin/questionnaire | `POST` | `/api/admin/questionnaires/<int:questionnaire_id>/disable` | 停用问卷 | 否 | 是 | `routes.py:4761 admin_disable_questionnaire；url_map endpoint=api.admin_disable_questionnaire` |
| admin/questionnaire | `DELETE` | `/api/admin/questionnaires/<int:questionnaire_id>` | 删除问卷 | 否 | 是 | `routes.py:4770 admin_delete_questionnaire；url_map endpoint=api.admin_delete_questionnaire` |
| admin/questionnaire | `GET` | `/api/admin/questionnaires/<int:questionnaire_id>/latest-submit-debug` | 查看最近一次问卷提交调试信息 | 否 | 是 | `routes.py:4739 admin_questionnaire_latest_submit_debug；url_map endpoint=api.admin_questionnaire_latest_submit_debug` |
| admin/questionnaire | `GET` | `/api/admin/questionnaires/<int:questionnaire_id>/export` | 导出问卷提交 | 否 | 是 | `routes.py:4778 admin_export_questionnaire；url_map endpoint=api.admin_export_questionnaire` |
| questionnaire/public | `GET` | `/s/<slug>` | H5 问卷公开页 | 否 | 否 | `routes.py:4790 questionnaire_h5_page；url_map endpoint=api.questionnaire_h5_page` |
| questionnaire/public | `GET` | `/s/<slug>/submitted` | H5 问卷提交完成页 | 否 | 否 | `routes.py:5246 questionnaire_h5_submitted；url_map endpoint=api.questionnaire_h5_submitted` |
| questionnaire/public | `GET` | `/api/h5/questionnaires/<slug>` | 获取问卷公开配置 | 否 | 否 | `routes.py:5332 public_get_questionnaire；url_map endpoint=api.public_get_questionnaire` |
| questionnaire/public | `POST` | `/api/h5/questionnaires/<slug>/submit` | 提交问卷 | 是，timeline 输入源 | 否 | `routes.py:5342 public_submit_questionnaire；url_map endpoint=api.public_submit_questionnaire` |
| questionnaire/debug | `GET` | `/api/debug/questionnaire/session` | 问卷调试会话查看 | 否 | 是 | `routes.py:5360 debug_questionnaire_session；url_map endpoint=api.debug_questionnaire_session` |
| questionnaire/oauth | `GET` | `/api/h5/wechat/oauth/start` | 微信 OAuth 启动 | 否 | 否 | `routes.py:5367 h5_wechat_oauth_start；url_map endpoint=api.h5_wechat_oauth_start` |
| questionnaire/oauth | `GET` | `/api/h5/wechat/oauth/callback` | 微信 OAuth 回调 | 否 | 否 | `routes.py:5397 h5_wechat_oauth_callback；url_map endpoint=api.h5_wechat_oauth_callback` |
| admin-ui | `GET` | `/admin/questionnaires/ui` | 问卷后台页面 | 否 | 是 | `routes.py:2755 admin_questionnaires_ui；url_map endpoint=api.admin_questionnaires_ui` |

### Customer Center / Customer Timeline Aggregation

| Domain | Method | Path | 当前用途 | 是否为 customer_center / customer_timeline 输入 | 是否敏感 | 来源证据 |
| --- | --- | --- | --- | --- | --- | --- |
| customer_center | `GET` | `/api/customers` | 客户中心列表聚合接口 | 是，本体 | 是 | `routes.py:2077 customer_center_list；url_map endpoint=api.customer_center_list；实现委托 customer_center.list_customers` |
| customer_center | `GET` | `/api/customers/<external_userid>` | 客户中心详情聚合接口 | 是，本体 | 是 | `routes.py:2094 customer_center_detail；url_map endpoint=api.customer_center_detail；实现委托 customer_center.get_customer_detail` |
| customer_timeline | `GET` | `/api/customers/<external_userid>/timeline` | 客户时间线聚合接口 | 是，本体 | 是 | `routes.py:2102 customer_timeline_detail；url_map endpoint=api.customer_timeline_detail；实现委托 customer_timeline.get_customer_timeline` |

### Callback / MCP / Verification

| Domain | Method | Path | 当前用途 | 是否为 customer_center / customer_timeline 输入 | 是否敏感 | 来源证据 |
| --- | --- | --- | --- | --- | --- | --- |
| callback | `GET,POST` | `/wecom/external-contact/callback` | 接收外部联系人变更回调与 URL 验证 | 是，identity 上游输入 | 否，走企微验签 | `routes.py:5744 receive_external_contact_callback；url_map endpoint=api.receive_external_contact_callback` |
| callback | `GET,POST` | `/api/wecom/events` | 接收通用企微事件回调 | 是，消息/群目录上游输入 | 否，走企微验签 | `routes.py:5807 receive_wecom_event；url_map endpoint=api.receive_wecom_event` |
| mcp | `GET,POST` | `/mcp` | OpenClaw 使用的 MCP adapter | 否 | 是 | `mcp_adapter.py + create_app 注册；当前不在 routes.py 静态装饰器内，但存在于运行时 url_map` |
| verify-file | `GET` | `/<path:filename>` | 根路径校验文件下载，如 `WW_verify_*.txt` / `MP_verify_*.txt` | 否 | 否 | `routes.py:1928 serve_root_verification_file；url_map endpoint=api.serve_root_verification_file` |

## Planned / Reserved Routes

本次用 `url_map` 与源码双重校验后，在当前 CRM 范围内没有发现“已经有明确 path 但尚未注册到 Flask 的预留路由”。

也就是说：

- 上表全部属于当前真实已实现路由
- 本轮不再把“概念上的 future API”混写进现状清单

如果后续要新增 `customer_center v2`、`customer_timeline v2` 或新的 internal-only aggregation API，应在新增代码后再进入 Current Implemented Routes，而不是先写进 inventory。

## 纠偏结论

- `/api/customers`
- `/api/customers/<external_userid>`
- `/api/customers/<external_userid>/timeline`

这三条在当前代码和 `url_map` 中都真实存在，因此仍保留在 Current Implemented Routes，不应被当作“仅规划”移出。

本轮真正纠正的是：

- 把“当前实现”和“未来规划”强制拆开
- 把 questionnaire 路由改成真实的 slug / h5 / admin / oauth 分层路径
- 给每条现有路由补上来源证据，降低文档靠猜的风险
