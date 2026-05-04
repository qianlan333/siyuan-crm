# Automation Engine Remaining Exceptions Ledger

日期：2026-04-21

## 说明

下表只记录当前仍保留、但本轮不继续清理的 automation engine 例外。判断标准不是“是否还存在 legacy 痕迹”，而是“是否阻塞 Wave 4 closeout”。

| 例外 | 当前形态 | 为什么这次不拆 | 类别 | 是否阻塞 Wave 4 closeout | 后续归位建议 |
| --- | --- | --- | --- | --- | --- |
| `wecom_ability_service/services.py` 的 automation wrappers | 历史 shim / compatibility façade | 需要保留旧 import、tool registry、monkeypatch 与历史测试稳定面；本轮优先先把 formal owner 与 primary caller 收口 | `shim` / `bridge` | 否 | 后续可先把 `services.py` 缩到 exception export + compatibility façade，再逐步压缩 tool registry 对它的依赖 |
| `wecom_ability_service/application/integration_gateway/mcp_dispatch.py` 中 automation tool bridge | MCP 仍直接消费 legacy automation surface | 本轮用户范围不包含 MCP cleanup，也不允许把 Wave 4 扩成 integration_gateway 收尾 | `bridge` | 否 | 后续在 MCP cleanup 小 PR 中统一改成只调 `application/automation_engine/*` |
| `wecom_ability_service/domains/admin_console/service.py` 的 automation `service_paths` | admin tool registry 仍指向 `wecom_ability_service.services.*` | 当前只是 tool metadata / console glue，不是 automation truth owner | `bridge` / `maintenance` | 否 | 后续把 automation tool registry 改成 formal application API 描述或稳定 adapter path |
| `wecom_ability_service/http/customer_automation.py::_candidate_context` | controller 侧 customer context 聚合 helper | 这是 Wave 1 保留下来的兼容聚合点；本轮目标是 automation owner 收口，不重新打开 customer read 结构调整 | `read` / `bridge` | 否 | 后续如继续收缩该 controller，可把 candidate context 聚合下沉到 application read model |
| `wecom_ability_service/http/automation_conversion.py` 仍直接 import `domains.automation_conversion` façade | 同 context admin transport 仍沿用 legacy façade | 本轮没有继续做 `http/automation_conversion.py` application-only cutover；继续推进会显著扩大变更面 | `maintenance` / `transport` | 否 | 后续单开一轮 automation workspace transport 收缩，把 member/workflow/SOP 页面按 application 边界切分 |
| `wecom_ability_service/domains/marketing_automation/service.py` 仍持有 config / preview / recompute / marketing truth 大量逻辑 | internal owner 尚未完全细拆 | 本轮只拆 message dispatch；继续拆 config / preview / truth 会把 Wave 4 扩成第二轮内部重构 | `maintenance` | 否 | 后续可按 `config` / `truth` / `segmentation` 三块继续内部模块化 |
| `wecom_ability_service/domains/automation_conversion/orchestration_service.py` 仍混有 agent orchestration / review / publish / callback façade | 新 router/runtime owner 已建立，但 orchestration 大文件仍大 | 本轮只先把 router/runtime owner 落下，不进入 agent runtime / prompt infra 深拆 | `maintenance` | 否 | 后续若进入 automation 深化阶段，优先拆 `agent orchestration` 与 `review console` |
| `wecom_ability_service/domains/automation_conversion/workflow_runtime.py` 与 `workflow_service.py` 仍是 delegate target | new owner wrapper 之下的 legacy implementation | 本轮目标是 owner 转移，不是一次性重写 workflow internals | `maintenance` | 否 | 后续继续把 runtime/execution shared helper 从 legacy target 向新 owner 模块内收 |
| `wecom_ability_service/domains/outbound_webhook/service.py` 仍保留 config / retry policy / requests helper | outbound send/retry 已抽走，但基础 helper 还在旧 service | 继续拆会触发 transport/runtime config 边界调整，不适合放在 closeout PR | `maintenance` / `transport` | 否 | 后续可再拆成 `outbound_webhook_runtime.py` / `outbound_webhook_transport.py` |
| `wecom_ability_service/domains/tasks/service.py::dispatch_wecom_task` 仍被 workflow / message dispatch 间接依赖 | automation 运行时下游 transport 依赖 | 这是跨 context integration 问题，不属于本轮 automation owner closeout 的必做项 | `bridge` | 否 | 后续如进入 integration/runtime 治理，再把 task dispatch 统一适配成稳定 adapter |

## 结论

当前 remaining exceptions 仍然存在，但都已经被限制在：

- compatibility shim
- MCP / admin tool registry bridge
- 同 context admin transport façade
- legacy delegate target
- transport/runtime 基础设施债

它们不再构成 automation engine 主写入口或 primary caller 的 owner 漂移，因此不阻塞 Wave 4 closeout。
