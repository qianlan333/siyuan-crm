# Customer Pulse RBAC Matrix

更新时间：2026-04-11

## 目标

Customer Pulse 不再只有“能不能进 AI推进 页面”这一层控制。当前实现把页面、列表、widget、evidence、动作执行、反馈全部挂到现有 `owner_role_map + CUSTOMER_PULSE_TENANT_ACCESS_POLICY_JSON` 链路上，继续复用现有 request-scoped tenant context、owner scope、admin token、审计日志和 metrics 体系。

## 权限矩阵

| 权限 key | 作用 | 后端强校验入口 | 前端控制点 |
| --- | --- | --- | --- |
| `page_visible` | 是否显示 AI推进 导航与首页入口 | `/admin/customer-pulse` 页面断言 | 后台导航、工作台 quick link、客户详情“查看 AI推进”链接 |
| `inbox_view` | 是否查看收件箱列表与卡片详情 | `/api/admin/customer-pulse`、`/api/internal/customer-pulse/inbox` | 收件箱入口页 |
| `widget_view` | 是否查看客户详情 AI 下一步 widget | `/api/admin/customers/profile/pulse` | 客户详情侧边栏 widget |
| `evidence_view` | 是否展开原始 evidence | `/api/admin/customer-pulse/cards/<id>/evidence` | evidence 展开按钮 |
| `generate_reply_draft` | 是否生成/编辑会话草稿 | preview / execute / undo action service | 草稿动作按钮、草稿编辑器 |
| `create_followup_task` | 是否创建跟进任务 | preview / execute / undo action service | 创建任务按钮 |
| `update_followup_segment` | 是否更新阶段/跟进分层 | preview / execute / undo action service | 更新阶段按钮 |
| `update_tags` | 是否更新标签 | preview / execute / undo action service | 更新标签按钮 |
| `set_followup_reminder` | 是否设置下次跟进提醒 | preview / execute / undo action service | 设置提醒按钮 |
| `submit_feedback` | 是否提交采纳/忽略/误判等反馈 | `/feedback` service | 反馈按钮 |

## 角色与配置来源

权限不新建平行表，继续来自 tenant policy：

```json
{
  "tenant-acme": {
    "owner_userids": ["owner-a"],
    "member_userids": ["owner-a", "ops-1"],
    "viewer_roles": ["sales", "ops"],
    "operator_roles": ["ops"],
    "internal_roles": ["ops", "admin"],
    "permissions_by_role": {
      "sales": ["page_visible", "inbox_view", "widget_view"],
      "ops": ["all"]
    },
    "permissions_by_userid": {
      "owner-a": ["page_visible", "widget_view", "generate_reply_draft"]
    }
  }
}
```

解析规则：

1. `permissions_by_userid` 优先级最高。
2. 其次使用 `permissions_by_role`。
3. 若未显式配置，回退到现有 `viewer_roles / operator_roles` 派生默认权限：
   - viewer 默认包含 `page_visible + inbox_view + widget_view + evidence_view`
   - operator 额外包含全部 action + `submit_feedback`
4. `legacy internal mode` 维持全权限，但日志里显式标记 `auth_mode=legacy_internal`。

## 后端控制点

### 页面与列表

- `/admin/customer-pulse`：同时要求 `page_visible` 和 `inbox_view`
- `/api/admin/customer-pulse`：要求 `inbox_view`
- `/api/internal/customer-pulse/inbox`：要求 `inbox_view`
- `/api/admin/customer-pulse/cards/<id>`：要求 `inbox_view` 或 `widget_view`
- `/api/internal/customer-pulse/customers/<external_userid>`：要求 `inbox_view` 或 `widget_view`

### 客户详情 widget

- `/api/admin/customers/profile/pulse`：要求 `widget_view`
- 客户详情模板只在 `customer_pulse_access.permissions.widget_view=true` 时渲染 widget

### 动作与反馈

- preview / execute / undo：先走 tenant + owner scope，再由 `assert_customer_pulse_action_permission` 校验具体 action
- feedback：单独走 `assert_customer_pulse_feedback_permission`
- action token 仍保留，保证所有写操作继续走“预览/确认”链路

## Evidence 二次校验

有卡片权限不等于能看所有原始证据。当前 evidence 展开接口增加两层校验：

1. 先要求 `evidence_view`
2. 再按 `evidenceRefs.sourceType/sourceId/external_userid` 回查原始表，只放行仍在原始访问边界内的记录

当前已覆盖的原始来源：

- `archived_messages`
- `automation_reply_monitor_queue`
- `questionnaire_submissions`
- `questionnaire_scrm_apply_logs`
- `conversion_dispatch_log`
- `customer_marketing_state_current`
- `external_contact_bindings`

未通过原始边界校验的 ref 会进入 `inaccessible_refs`，前端只展示安全 refs，不展示原始内容。
每次 evidence 展开成功或拒绝都会额外写审计日志；拒绝场景会累计 `access_denied` 安全计数，避免越权探测无痕。

## 前端控制点

- 导航、工作台 quick link：只认 `page_visible`
- 收件箱列表：服务端直接过滤动作按钮和 feedback 按钮；前端不再自己猜权限
- 收件箱详情：默认只加载卡片详情，动作 preview 和 evidence 展开必须显式点击
- 客户详情 widget：默认只展示安全 refs；无 `evidence_view` 时不显示展开按钮
- 所有动作按钮、草稿编辑器、反馈按钮都消费服务端返回的 `card.permissions`

## 已知边界

- `operator_roles` 仍用于刷新全量行动卡等后台管理动作；card action 的细粒度执行权限已下沉到 capability 断言
- 当前前端主要做隐藏/禁用，真正的授权结果以后端 403 为准
- 若 tenant policy 未配置 `permissions_by_role / permissions_by_userid`，系统会继续使用旧 viewer/operator 语义，避免灰度租户直接失效
