# 用户主身份模型

## 主身份定义

- `people.id` 是系统内部唯一的 `person_id`
- `people.mobile` 是该 `person_id` 的主手机号

`people` 是用户主表，也是主身份表。后续所有“这个人是谁”的内部归一结果，都应该落到 `person_id`。

## 各表职责

- `people`
  - 手机号主身份表
  - 承载系统内部统一的人物身份
  - `third_party_user_id` 当前允许为空，不作为绑定成功前置条件

- `external_contact_bindings`
  - `external_userid -> person_id` 绑定表
  - 表示某个企微客户当前绑定到哪个内部 `person_id`

- `wecom_external_contact_identity_map`
  - 企微身份信息表
  - 保存 `external_userid / unionid / openid / follow_user_userid` 等企微身份字段

- `wecom_external_contact_follow_users`
  - 客户与企业成员关系表
  - 保存客户和企业成员之间的跟进关系、备注、状态等

- `contacts`
  - 当前 CRM 联系人快照表
  - 保存面向 CRM 页面展示和业务判断使用的联系人快照，如 `customer_name / owner_userid / remark`

## 统一身份解析

统一身份解析能力由 `GET /api/identity/resolve` 提供，支持两种入口：

- `external_userid`
- `mobile`

返回统一的主身份视图，至少包含：

- `person_id`
- `mobile`
- `external_userid`
- `customer_name`
- `owner_userid`
- `remark`
- `unionid`
- `openid`
- `follow_user_userid`
- `signup_status`
- `is_bound`
