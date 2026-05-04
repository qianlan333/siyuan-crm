# CRM Data Inventory

## Scope

本清单只描述当前 CRM 底层能力的核心表用途，不涉及页面设计或业务重构。

## Core Tables

### `contacts`

- 主要用途：本地联系人主表，承接企微客户基础信息快照
- 主键 / 核心关联键：`id`，唯一键 `external_userid`
- 更偏：`customer_center`
- 后续建议：保持主表只读聚合来源之一，不要把太多派生状态直接写死在这里
- 风险：同一个客户可能被多个员工跟进，`owner_userid` 只能表达一个当前快照

### `people`

- 主要用途：系统内部“人”表，承接手机号和第三方用户 ID
- 主键 / 核心关联键：`id`，唯一键 `mobile`
- 更偏：`customer_center`
- 后续建议：作为统一 person_id 锚点，保持相对稳定
- 风险：手机号绑定冲突会直接影响 CRM 与外部系统对人关系的统一

### `external_contact_bindings`

- 主要用途：把 `external_userid` 绑定到 `people.id`
- 主键 / 核心关联键：主键 `external_userid`，外键 `person_id`
- 更偏：`customer_center`
- 后续建议：保持只读聚合 + 明确绑定动作来源，不要让下游随意覆盖
- 风险：一旦误绑定，身份解析会串人

### `wecom_external_contact_identity_map`

- 主要用途：企微外部联系人身份映射主表，承接 `unionid/openid/external_userid`
- 主键 / 核心关联键：`id`，唯一键 `(corp_id, external_userid)`
- 更偏：`customer_center`
- 后续建议：保持为权威身份表，后续问卷、OAuth、标签回写都应基于它
- 风险：如果把“多个跟进人”压缩到单字段，会丢失完整服务关系

### `wecom_external_contact_follow_users`

- 主要用途：一个外部联系人与多个服务人 `user_id` 的关系子表
- 主键 / 核心关联键：`id`，唯一键 `(corp_id, external_userid, user_id)`
- 更偏：`customer_center`
- 后续建议：保持关系型来源表，供 customer_center 做多客服/多跟进人聚合
- 风险：若状态更新不全，删除/转移关系会残留脏数据

### `archived_messages`

- 主要用途：企微会话存档解密后的消息事实表
- 主键 / 核心关联键：`id`，唯一键 `msgid`，同步游标 `seq`
- 更偏：`customer_timeline`
- 后续建议：保持事实表只追加/幂等 upsert，不要混入判断结果
- 风险：`send_time`、`chat_type`、`roomid/chat_id` 一旦解析错误，会直接污染时间线

### `outbound_tasks`

- 主要用途：官方私信/朋友圈/群发任务创建记录
- 主键 / 核心关联键：`id`
- 更偏：`customer_center`
- 后续建议：保持动作审计表，不要在这里承载复杂流程状态机
- 风险：只记录创建结果，不代表实际触达完成

### `contact_tags`

- 主要用途：本地标签快照表，记录给某客户打过哪些 tag
- 主键 / 核心关联键：`id`，唯一键 `(external_userid, userid, tag_id)`
- 更偏：`customer_center`
- 后续建议：作为标签现状/审计来源之一，可供 customer_center 展示
- 风险：如果只靠本地快照、不定期回刷企微，会出现本地与企微不一致

### `class_user_status_current`

- 主要用途：class_user 当前状态池，表达某客户当前报名/班级状态
- 主键 / 核心关联键：主键 `external_userid`
- 更偏：`customer_center`
- 后续建议：作为聚合态表保留，供管理端和 customer_center 快速读取
- 风险：这是一张派生状态表，规则变更时需要明确回刷策略

### `class_user_status_history`

- 主要用途：class_user 状态变更历史
- 主键 / 核心关联键：`id`，`external_userid`
- 更偏：`customer_timeline`
- 后续建议：保持历史不可改，适合作为时间线事件源
- 风险：如果补写/重跑时没有注明来源，历史会混淆“真实操作”和“迁移修复”

### `questionnaire_submissions`

- 主要用途：问卷提交主记录
- 主键 / 核心关联键：`id`，`questionnaire_id`，`respondent_key`
- 更偏：`customer_center`
- 后续建议：保持问卷域自己的事实主表，供 customer_center 聚合展示
- 风险：身份回填链路复杂，`openid/unionid/external_userid` 关联不稳时容易重复提交或错绑

### `questionnaire_submission_answers`

- 主要用途：问卷答案明细
- 主键 / 核心关联键：`id`，`submission_id`
- 更偏：`customer_timeline`
- 后续建议：适合作为时间线事件来源或问卷详情 drill-down 数据
- 风险：字段结构灵活，后续查询和索引成本可能上升

### `wecom_external_contact_event_logs`

- 主要用途：外部联系人变更事件日志
- 主键 / 核心关联键：`id`，唯一键 `event_key`
- 更偏：`customer_timeline`
- 后续建议：保持事件日志只追加、结果可重试，不建议下游直接修改
- 风险：如果回调消费失败重试策略不清晰，会出现 pending / failed 堆积

## Table Role Summary

### 更偏 customer_center

- `contacts`
- `people`
- `external_contact_bindings`
- `wecom_external_contact_identity_map`
- `wecom_external_contact_follow_users`
- `outbound_tasks`
- `contact_tags`
- `class_user_status_current`
- `questionnaire_submissions`

### 更偏 customer_timeline

- `archived_messages`
- `class_user_status_history`
- `questionnaire_submission_answers`
- `wecom_external_contact_event_logs`

## Read-Only Aggregation Suggestions

后续更建议保持只读聚合的表：
- `contacts`
- `wecom_external_contact_identity_map`
- `wecom_external_contact_follow_users`
- `archived_messages`
- `class_user_status_history`
- `questionnaire_submissions`
- `questionnaire_submission_answers`
- `wecom_external_contact_event_logs`

原因：
- 这些表更像事实来源或稳定聚合来源
- `customer_center` 和 `customer_timeline` 应优先从它们读，而不是回写业务判断结果
