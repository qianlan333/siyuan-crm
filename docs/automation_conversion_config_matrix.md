# 自动化转化配置清单

| 配置项名 | 用途 | 是否必填 | 未配置时行为 | 是否生产必填 |
| --- | --- | --- | --- | --- |
| `AUTOMATION_INTERNAL_API_TOKEN` | 统一保护自动化内部动作接口；用于 `/mcp`、激活回写、webhook 手动重试、到期重试、jobs 动作型 API | 建议必填 | 为空时回退到各入口 legacy token；如果 legacy 也没配，则内部动作接口按现有兼容行为运行 | 是 |
| `MCP_BEARER_TOKEN` | `/mcp` 的 legacy Bearer Token；已兼容统一内部接口令牌 | 否 | 当统一内部令牌未配置时仍可单独保护 `/mcp`；两者都没配则 `/mcp` 不做 Bearer 校验 | 否 |
| `OPENCLAW_FOCUS_MESSAGE_WEBHOOK_URL` | 重点跟进池客户来消息时，CRM 推送 OpenClaw webhook | 第 5 块必填 | 不推送，记录 `webhook_not_configured` | 是 |
| `OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TOKEN` | 重点消息 webhook Bearer Token | 否 | 不带 `Authorization` 头 | 建议 |
| `OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TIMEOUT_SECONDS` | 重点消息 webhook 超时秒数 | 否 | 默认 10 秒 | 建议 |
| `AUTOMATION_ACTIVATION_WEBHOOK_TOKEN` | 激活回写 webhook legacy token；已兼容统一内部接口令牌 | 否 | 当统一内部令牌未配置时仍可单独保护激活回写；两者都没配则接口按兼容行为运行 | 否 |
| `QUESTIONNAIRE_SUBMIT_WEBHOOK_URL` | 问卷提交成功后的外发 webhook 地址 | 第 7 块必填 | 问卷提交仍成功，但不外发 webhook | 是 |
| `QUESTIONNAIRE_SUBMIT_WEBHOOK_TOKEN` | 问卷提交 webhook Bearer Token | 否 | 不带 `Authorization` 头 | 建议 |
| `QUESTIONNAIRE_SUBMIT_WEBHOOK_TIMEOUT_SECONDS` | 问卷提交 webhook 超时秒数 | 否 | 默认 10 秒 | 建议 |
| `WECOM_CORP_ID` | 企业微信 corp id | 真实企微联调必填 | 无法完成真实联系人、标签和消息链路 | 是 |
| `WECOM_SECRET` | 企业微信应用 secret | 真实企微联调必填 | 无法完成真实发送链路 | 是 |
| `WECOM_CONTACT_SECRET` | 企业微信通讯录 secret | 真实企微联调必填 | 无法完成真实联系人/标签链路 | 是 |
| `WECOM_AGENT_ID` | 企业微信 agent id | 真实企微联调必填 | 无法完成真实发送链路 | 是 |
| `WECOM_API_BASE` | 企业微信 API base | 真实企微联调必填 | 真实 API 调用不可用 | 是 |
| `WECOM_DEFAULT_OWNER_USERID` | 现有全局默认负责人 | 否 | 仅在极少数缺失 owner 数据的兼容场景下做回退；正常第 4/5 块按真实 owner 生效 | 否 |

## 说明

- 统一内部鉴权覆盖的动作型入口：
  - `/mcp`
  - `/api/customers/automation/activation-webhook`
  - `/api/customers/automation/webhook-deliveries/<id>/retry`
  - `/api/customers/automation/webhook-deliveries/retry-due`
  - `/api/admin/jobs/*` 下会触发真实执行的 POST 接口
- 后台页 `/admin/jobs/actions` 不直接暴露机器 Bearer Token，改用 session 绑定的 `admin_action_token` 防止匿名提交动作。
- 公开业务接口不纳入这次统一鉴权：
  - `/api/h5/questionnaires/<slug>/submit`
- 第 4 块和第 5 块当前支持多个负责人，调用时直接传真实 `owner_userid`。
- 第 6 块和第 7 块不依赖固定负责人配置。
- 生产环境至少要把 `AUTOMATION_INTERNAL_API_TOKEN` 和所有 webhook 目标配置填完整，不能依赖默认留空行为。
