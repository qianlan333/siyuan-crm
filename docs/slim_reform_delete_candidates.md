# 第二阶段硬删候选

## 模块候删

### AI Assist

- `wecom_ability_service/http/admin_customer_pulse.py`
- `wecom_ability_service/http/admin_followup_orchestrator.py`
- `wecom_ability_service/domains/customer_pulse/`
- `wecom_ability_service/domains/followup_orchestrator/`
- `wecom_ability_service/application/ai_assist/`
- 对应模板与测试

### MCP 控制台

- `wecom_ability_service/http/admin_mcp.py` 里的旧控制台逻辑
- `wecom_ability_service/templates/admin_console/mcp.html`
- `wecom_ability_service/templates/admin_console/config_mcp_tools.html`
- `tests/test_admin_mcp_console.py` 中旧控制台交互断言部分

## 数据表候删

### Customer Pulse

- `customer_pulse_signal_events`
- `customer_pulse_snapshots`
- `customer_pulse_cards`
- `customer_pulse_feedback_logs`
- `customer_pulse_execution_logs`
- `customer_pulse_activity_logs`
- `customer_pulse_action_feedback`
- `customer_pulse_metric_events`

### Followup Orchestrator

- `followup_orchestrator_policies`
- `followup_orchestrator_missions`
- `followup_orchestrator_mission_items`
- `followup_orchestrator_assignment_decisions`
- `followup_orchestrator_mission_feedback`
- `followup_orchestrator_execution_logs`

### MCP

- `mcp_tool_settings`

前提：确认 `/mcp` 协议入口本身也不再需要。

## 删除前检查

- 最近 7 天无后台人工访问
- 最近 7 天无外部 API 调用
- 最近 7 天无自动化任务依赖
- 自动化运营、问卷、配置、API 文档四条主入口回归通过
- `/admin/config/login-access` 中的登录审计无异常失败峰值
- 企业微信 SSO 与 break-glass 应急切换演练通过
