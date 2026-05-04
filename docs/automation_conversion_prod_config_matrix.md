# 自动化转化线上配置核对表

| 配置项名 | 用途 | 是否线上必填 | 如何核对它已经生效 | 缺失时的影响 | 是否可以临时降级 |
| --- | --- | --- | --- | --- | --- |
| `AUTOMATION_INTERNAL_API_TOKEN` | 统一保护自动化内部动作接口；覆盖 `/mcp`、激活回写、webhook 重试、jobs 动作型 API | 是 | 用正确 Bearer Token 调动作型接口成功；错 token 应统一返回 401 | 内部动作接口失去统一保护，或不同入口口径不一致 | 可以，临时更换 token 实现整体止损 |
| `MCP_BEARER_TOKEN` | `/mcp` 的 legacy token；已兼容统一内部接口令牌 | 否 | 当统一内部令牌未配置时，用它调 `/mcp` 成功；错 token 返回 401 | 仅影响 legacy 兼容调用 | 可以 |
| `OPENCLAW_FOCUS_MESSAGE_WEBHOOK_URL` | 焦点消息 webhook 地址 | 是 | 重点跟进池客户来消息时观察对方 webhook 日志 | 焦点消息不会推送到 OpenClaw | 可以，清空后仅停该链路 |
| `OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TOKEN` | 焦点消息 webhook 鉴权 token | 建议 | 看对方 webhook 日志是否收到 Bearer Token | 对方如果要求鉴权，调用会失败 | 可以，临时清空但会降低安全性 |
| `OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TIMEOUT_SECONDS` | 焦点消息 webhook 超时控制 | 建议 | 查看设置值和日志超时行为 | 超时控制不可预期 | 可以 |
| `AUTOMATION_ACTIVATION_WEBHOOK_TOKEN` | 激活回写 legacy token；已兼容统一内部接口令牌 | 否 | 当统一内部令牌未配置时，用正确 token 调用成功，用错 token 返回 401 | 仅影响 legacy 兼容调用 | 可以 |
| `QUESTIONNAIRE_SUBMIT_WEBHOOK_URL` | 问卷提交成功后的外发 webhook 地址 | 是 | 提交问卷后观察对方 webhook 日志 | 外部系统收不到 mobile / userid / unionid | 可以，清空后不影响问卷主流程 |
| `QUESTIONNAIRE_SUBMIT_WEBHOOK_TOKEN` | 问卷 webhook 鉴权 token | 建议 | 检查对方 webhook 是否收到 Bearer Token | 对方要求鉴权时会失败 | 可以，临时清空但会降低安全性 |
| `QUESTIONNAIRE_SUBMIT_WEBHOOK_TIMEOUT_SECONDS` | 问卷 webhook 超时控制 | 建议 | 查看设置值和日志超时行为 | 超时控制不可预期 | 可以 |
| `WECOM_CORP_ID` | 企业微信 corp id | 是 | `/admin` 和真实企微链路可正常使用 | 真实企微能力不可用 | 否 |
| `WECOM_SECRET` | 企业微信应用 secret | 是 | 真实发送链路成功 | 真实发送不可用 | 否 |
| `WECOM_CONTACT_SECRET` | 通讯录 secret | 是 | 标签/联系人读取正常 | 标签和联系人链路异常 | 否 |
| `WECOM_AGENT_ID` | agent id | 是 | 真实触达成功 | 触达链路不可用 | 否 |
| `WECOM_API_BASE` | 企业微信 API 地址 | 是 | 真实 API 可请求 | 真实企微链路异常 | 否 |
| `WECOM_DEFAULT_OWNER_USERID` | 现有全局默认负责人回退 | 否 | 缺失 owner 的兼容场景下看状态 payload 是否回退到默认值 | 正常多负责人主链路不受影响；仅兼容回退场景受影响 | 可以 |

## 线上核对建议

1. 先核对后台设置页中的值是否已填
2. 再用最小请求验证实际链路
   - `/mcp`
   - `/api/customers/automation/activation-webhook`
   - `/api/customers/automation/webhook-deliveries/retry-due`
3. 再查 service 日志确认配置已生效

## 降级原则

- 优先停单条 webhook，不优先停整套自动化
- 能通过清空 URL 或更换 token 止损的，先用最小止损动作
