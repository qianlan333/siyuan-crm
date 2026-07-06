# Active Automation Retirement Guardrails

旧自动化运营 jobs runner 已退场：

- `/api/admin/automation-conversion/jobs/run-due` 必须返回 `404` 或 `410`。
- `/api/admin/automation-conversion/jobs/run-due/preview` 必须返回 `404` 或 `410`。
- `aicrm-automation-jobs-run-due.timer` 是 retired timer，不允许重新启用。

AI 自动化运营人群包刷新由 `openclaw-ai-audience-scheduler.timer` 通过
`internal_event` 消费器驱动；外推继续走 `external_effect_job`。

Cloud campaign run-due 不属于旧 automation jobs runner，保留 scheduled safe
mode 服务器验证 payload：

```json
{"operator":"aicrm-campaign-run-due","batch_size":200,"scheduled_safe_mode":true}
```
