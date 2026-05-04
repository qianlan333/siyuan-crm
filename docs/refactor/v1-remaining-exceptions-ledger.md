# V1 Remaining Exceptions Ledger

日期：2026-04-22

## 说明

本台账用于汇总 Wave 1–5 关单后仍保留的例外，并明确说明：

- 属于哪个 wave
- 当前是什么形态
- 是否阻塞 V1 关单
- 后续应该如何管理

总判断：

- 当前 remaining exceptions 全部为 non-blocking
- 没有任何一项继续阻塞 V1 正式关单

## Wave 1

| 例外 | 当前形态 | 类别 | 是否阻塞 V1 closeout | 后续管理建议 |
| --- | --- | --- | --- | --- |
| `application/integration_gateway/mcp_dispatch.py` 仍偏大 | application bridge / dispatch seam 仍较重 | `bridge` / `maintenance` | 否 | 未来如继续做 integration cleanup，单独开 MCP / integration adapter 小专题 |
| `services.py` 仍保留宽 compatibility surface | legacy shim 仍覆盖多个 context 的历史入口 | `shim` | 否 | 只在后续专题里按 context 缩薄，不再在 V1 主线内扩做 |
| `http/customer_automation.py` 仍是兼容性较强的控制器文件 | Wave 1 已收口 formal owner，但 controller 仍承载一部分兼容 glue | `bridge` | 否 | 如后续继续做 admin / automation transport 收缩，单独立项 |

## Wave 2

| 例外 | 当前形态 | 类别 | 是否阻塞 V1 closeout | 后续管理建议 |
| --- | --- | --- | --- | --- |
| `services.py` 中 identity / class_user / routing / user_ops wrappers 仍保留 | compatibility surface 仍较宽 | `shim` | 否 | 长期按 context 单独做 shim shrink，不再作为 Wave 2 主线继续扩写 |
| `domains/user_ops/service.py` 仍保留 read / maintenance / shim facade | 主写 owner 已迁走，但 read/maintenance 未全部下沉 | `read` / `maintenance` / `shim` | 否 | 仅在未来如确有业务收益时，再开 user_ops 第二轮内部治理专题 |
| identity / class_user / routing 仍存在 legacy delegate target | caller 已切走，但内部 implementation 仍通过 legacy 承接 | `bridge` / `maintenance` | 否 | 后续如需要，再按 domain 内部模块化节奏推进 |
| adapter / monkeypatch 锚点仍需保留 | 例如 user_ops 运行时锚点 | `bridge` | 否 | 只有在兼容依赖彻底消失后才收缩，不作为当前主线工作 |

## Wave 3

| 例外 | 当前形态 | 类别 | 是否阻塞 V1 closeout | 后续管理建议 |
| --- | --- | --- | --- | --- |
| `services.py` 的 questionnaire wrappers 与 runtime bridge 仍保留 | public/admin/submit 兼容层尚未彻底删除 | `shim` / `bridge` | 否 | 后续如继续治理 questionnaire 内部模块，再单独压缩 shim |
| `public_questionnaires.py -> QuestionnaireAlreadySubmittedError` 仍依赖兼容异常出口 | public submit 错误语义兼容点 | `shim` | 否 | 未来如要统一 application exception，再单独迁移 |
| `domains/admin_console/service.py` 中的 questionnaire console glue 仍存在 | admin console 页面 glue 未全部 application-only 化 | `bridge` | 否 | 未来如继续治理 admin console，再单独拆 page adapter |
| 相邻 context 的 questionnaire read-side legacy imports 仍存在 | admin support / automation / dashboard / marketing 侧只读桥接 | `read` / `bridge` | 否 | 留到对应 context 自己收口时再处理 |
| `domains/questionnaire/service.py` 仍是 mixed legacy delegate target | formal owner 已成立，但内部 mixed implementation 仍在 | `maintenance` | 否 | 未来只在 questionnaire 第二轮内部治理时继续拆 |

## Wave 4

| 例外 | 当前形态 | 类别 | 是否阻塞 V1 closeout | 后续管理建议 |
| --- | --- | --- | --- | --- |
| `services.py` 的 automation wrappers 仍保留 | compatibility façade 仍在 | `shim` | 否 | 长期可压缩为 exception export + compatibility facade |
| `application/integration_gateway/mcp_dispatch.py` 中仍保留 automation bridge | MCP 仍消费部分 legacy automation surface | `bridge` | 否 | 后续单开 MCP cleanup 小专题 |
| `domains/admin_console/service.py` 的 automation `service_paths` 仍指向 `services.py` | tool registry / console metadata 仍未改成 formal owner 描述 | `maintenance` / `bridge` | 否 | 未来再统一 tool metadata / adapter 描述 |
| `http/customer_automation.py::_candidate_context` 仍是兼容聚合点 | controller 侧兼容读聚合未继续下沉 | `read` / `bridge` | 否 | 如后续继续缩 controller，再单列 transport 收缩 |
| `http/automation_conversion.py` 与多个 legacy runtime target 仍在 | 同 context transport / runtime façade 仍较重 | `transport` / `maintenance` | 否 | 只有未来继续做 automation 第二轮专题时再推进 |
| `domains/marketing_automation/service.py`、`workflow_runtime.py`、`workflow_service.py` 等仍保留较重 internal target | formal owner 已建立，但 runtime 内核仍有 legacy target | `maintenance` | 否 | 不再纳入 V1，未来若要继续只按内部治理小专题推进 |

## Wave 5

| 例外 | 当前形态 | 类别 | 是否阻塞 V1 closeout | 后续管理建议 |
| --- | --- | --- | --- | --- |
| `http/admin_customer_pulse.py` 仍直接依赖 `domains/customer_pulse/access.py` 与部分 repo read | transport / access / evidence glue | `bridge` / `read` | 否 | 后续如治理 AI Assist shared access layer，再单独抽稳定 adapter |
| `http/admin_followup_orchestrator.py` 仍复用 `domains/customer_pulse/access.py` | pulse/followup 共用 access layer | `bridge` | 否 | 后续如演进 shared access layer，再单独治理 |
| `domains/admin_console/customer_profile_service.py` 仍保留 pulse / followup view-model glue | admin 页面 presenter 未继续拆 | `bridge` | 否 | 未来若继续治理 admin profile，再拆 page adapter |
| `domains/customer_pulse/service.py` 与 `domains/followup_orchestrator/service.py` 仍保留 shared helper / runtime / policy glue | formal owner 已成立，但 shared glue 仍在 facade 文件中 | `shim` / `maintenance` | 否 | 未来只在 AI Assist 第二轮内部治理时继续下沉 |
| `ai_recommendation.py` / `ai_enhancement.py` 仍承担 provider/runtime 实现 | provider/runtime 未继续 infra 化 | `maintenance` | 否 | 未来若统一 AI provider adapter，再独立治理 |

## 汇总结论

- Wave 1–5 均存在 remaining exceptions
- 这些例外都已经被压缩为：
  - compatibility shim
  - access / transport bridge
  - shared runtime / provider helper
  - 同 context console / page glue
  - internal legacy delegate target
- 它们不会破坏 formal owner、caller boundary 或已经建立的 guardrail
- 因此不阻塞 V1 closeout

## 管理规则

- 不再把这些剩余例外塞回 Wave 1–5
- 后续如果要继续处理，必须单独建 backlog 项或新专题
- 默认策略是：
  - 先维持稳定
  - 只在明确有业务价值、工程收益或风险收益时再做后续治理
