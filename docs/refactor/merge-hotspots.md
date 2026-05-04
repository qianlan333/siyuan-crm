# Merge Hotspots

日期：2026-04-17

## 1. 历史质量说明

当前仓库 git 历史可读，但**不可用于精确 churn 统计**：

- `git rev-list --count HEAD = 1`
- `HEAD` 是 `grafted merge commit`
- 当前 clone 中没有足够的非合并提交来恢复真实的 30/90 天热点、共改对、冲突频率

因此本文件采用两层结论：

1. `git` 可见事实  
   当前副本只能看到 1 次大 merge，无法形成可信的“最近最常被修改文件”排名

2. 替代分析  
   使用当前目录依赖关系、大文件 inventory、冻结文件清单、Wave 1 入口范围，推导**最容易引发冲突的真实热点**

## 2. 可见 git 结论

当前 clone 可见历史里：

- 近 30/90 天改动次数几乎全部退化为 `0` 或 `1`
- 最常一起被改的文件组合被同一个 merge commit 污染
- 因此“最近最常被修改的文件”“最常一起被修改的文件组合”这两项，**不具备统计意义**

结论：

- 不应基于当前 clone 的 git 次数来安排 Wave 1 PR 粒度
- 需要改用“入口收口范围 + 依赖扇出 + 冻结文件”来切 PR

## 3. 当前树推导出的热点文件

| 文件 | 热点原因 | 冲突来源 | 建议 |
| --- | --- | --- | --- |
| `wecom_ability_service/mcp_adapter.py` | Wave 1 冻结文件；2,772 行；既是 transport，又直接耦合 customer read、business task、wecom task | 任何人同时动 MCP tool、customer context、internal auth、OpenClaw adapter 都会碰到它 | 单独 PR；只做 transport 收口，不和 read model / controller 改造同 PR |
| `wecom_ability_service/services.py` | 共享 facade；大量测试、脚本、旧入口都还依赖它 | 一边做兼容 shim，一边继续新增业务入口，会立刻产生语义冲突 | 单独 PR；只做 re-export / shim；禁止和 domain/service 大改混在一起 |
| `wecom_ability_service/domains/admin_console/service.py` | 1,502 行；跨 customer、timeline、MCP、questionnaire 多处拼装 | admin shell、MCP console、customer profile 同时推进时极易冲突 | 单独 PR；只收口 admin shell，不顺手改别的 admin 页面 |
| `wecom_ability_service/domains/admin_console/customer_profile_service.py` | 同时被 admin shell、automation、marketing 依赖 | customer profile、automation candidate context、marketing presenter 会一起争用它 | 单独 PR；仅切换读入口，不改 view-model 结构 |
| `wecom_ability_service/customer_center/service.py` | 旧 read model 主入口，Wave 1 要被 wrapper 化 | controller、admin profile、MCP customer context 都会改这里 | 不和 `customer_timeline/service.py`、`mcp_adapter.py` 同 PR 大改 |
| `wecom_ability_service/customer_timeline/service.py` | 旧 timeline 聚合入口，且被 mcp / automation orchestration 依赖 | timeline、MCP、automation candidate context 易交叉 | 先包 wrapper，再切单个调用方 |
| `wecom_ability_service/http/customer_automation.py` | 虽然只有 155 行，但它是多个旧入口的交叉点 | signup batch、recent messages、detail、timeline、internal auth 都在这里汇合 | 只改 controller 调用方向，不改底层 domain/service |
| `wecom_ability_service/domains/automation_conversion/service.py` | 4,447 行；最大 automation 聚合点之一 | customer_automation、questionnaire、background jobs 都会碰它 | Wave 1 延后拆分；只允许通过 application API 改调用方向 |
| `wecom_ability_service/domains/automation_conversion/orchestration_service.py` | 4,507 行；workflow / runtime / customer context 混在一起 | 与 `customer_timeline/service.py`、`admin_console/customer_profile_service.py` 强耦合 | 不和 customer read model PR 混改 |
| `wecom_ability_service/domains/customer_pulse/service.py` | 5,512 行；AI Assist 最大聚合点 | inbox、dashboard、action、feedback 任何一块都可能冲突 | Wave 1 不进；只消费正式 read API |
| `wecom_ability_service/db.py` | 2,938 行；schema init、runtime helper、平台装配都在这里 | schema、migration、tests、scripts 会把它拖进任何大 PR | 平台类 PR 单独处理；不要和 domain / controller 改造并行大改 |

## 4. 最常一起被动到的文件组合

由于 git 统计不可用，下表基于当前依赖图推导“最容易一起被改、也最容易一起冲突”的组合。

| 组合 | 证据 | 风险 |
| --- | --- | --- |
| `mcp_adapter.py` + `customer_center/service.py` + `customer_timeline/service.py` | `mcp_adapter.py` 直接依赖 customer read 旧实现 | 任何 MCP customer context 改动都会把 3 个文件拖进同一个 PR |
| `customer_center/service.py` + `domains/admin_console/customer_profile_service.py` | admin customer profile 直接依赖 customer read 旧实现 | 改 read model 和 admin profile 容易互相改坏 |
| `customer_timeline/service.py` + `mcp_adapter.py` + `http/customer_automation.py` | timeline 被 MCP 和 automation candidate context 同时消费 | timeline contract 改动会同时冲击 MCP 和 automation 页 |
| `http/customer_automation.py` + `domains/automation_conversion/service.py` + `domains/marketing_automation/service.py` | controller 当前直接读取 signup batch / recent messages / activation sync | 一个小 controller PR 很容易演变成 automation 大修 |
| `domains/admin_console/service.py` + `mcp_adapter.py` | admin shell 当前引用 MCP 私有函数 | admin console 和 MCP tool 改造会互相卡住 |
| `db.py` + `schema.sql` + `schema_postgres.sql` | schema 初始化都从 `db.py` 走 | 一边改 schema 一边改业务调用，排错成本最高 |
| `domains/customer_pulse/service.py` + `http/admin_customer_pulse.py` + `domains/followup_orchestrator/service.py` | AI inbox / action / followup 编排强耦合 | 很容易把一个 UI PR 变成 AI Assist 大改 |

## 5. 最容易引发冲突的入口文件

按 Wave 1 口径，以下入口文件最应该单独排班，不要多人同时大改：

1. `wecom_ability_service/mcp_adapter.py`
2. `wecom_ability_service/services.py`
3. `wecom_ability_service/http/customer_automation.py`
4. `wecom_ability_service/http/automation_conversion.py`
5. `wecom_ability_service/http/admin_customer_pulse.py`
6. `wecom_ability_service/domains/admin_console/service.py`
7. `wecom_ability_service/domains/admin_console/customer_profile_service.py`

排班规则：

- 同一时间只允许一个 PR 大改其中一个
- 其他 PR 只能做只读适配、wrapper、新测试或 guardrail
- 如果必须同时碰两个，优先拆成“新增入口 / 切调用方”两个 PR

## 6. 如何把一个大改动拆成小 PR

推荐拆法固定为 5 步：

1. 先加 contract / wrapper / smoke test，不切调用方  
   目标是先把未来路径搭出来，让 diff 可 review

2. 一次只切一个入口  
   例如先切 `http/customer_center.py`，不要同 PR 顺手切 `mcp_adapter.py`

3. 旧入口保留、只降级为 shim  
   这样回滚时只需要把调用方切回旧路径

4. schema / db / runtime 与业务 PR 分离  
   `db.py`、`schema*.sql`、环境脚本必须单独 PR

5. 大测试文件只增不改，优先新建窄测试文件  
   避免所有人都去改 `tests/test_api.py`、`tests/test_automation_conversion_v1.py`

## 7. 明确不能在同一个 PR 里一起大改的文件

以下组合不建议放在同一个 PR 里做“大改”：

- `wecom_ability_service/mcp_adapter.py` + `wecom_ability_service/customer_center/service.py`
- `wecom_ability_service/mcp_adapter.py` + `wecom_ability_service/customer_timeline/service.py`
- `wecom_ability_service/services.py` + `wecom_ability_service/domains/automation_conversion/service.py`
- `wecom_ability_service/services.py` + `wecom_ability_service/domains/customer_pulse/service.py`
- `wecom_ability_service/http/customer_automation.py` + `wecom_ability_service/domains/automation_conversion/service.py`
- `wecom_ability_service/http/customer_automation.py` + `wecom_ability_service/domains/marketing_automation/service.py`
- `wecom_ability_service/domains/admin_console/service.py` + `wecom_ability_service/mcp_adapter.py`
- `wecom_ability_service/domains/admin_console/customer_profile_service.py` + `wecom_ability_service/customer_center/service.py` + `wecom_ability_service/customer_timeline/service.py`
- `wecom_ability_service/db.py` + `wecom_ability_service/schema.sql` + 任何 Wave 1 入口收口 PR

如果不可避免，拆法必须是：

- PR A：新增正式入口 / wrapper / tests
- PR B：单一调用方切换
- PR C：旧入口降级或去冗余

## 8. 当前最稳的 PR 粒度

基于当前仓库状态，最稳的 PR 粒度是：

- 每个 PR 最多碰 1 个冻结文件
- 每个 PR 最多碰 1 个超大入口文件
- 每个 PR 最多切 1 条旧入口到新入口的映射
- 每个 PR 最多补 1 组 smoke tests

超过这个粒度，review 成本、合并冲突概率、缓存 / 脏状态排查难度都会明显上升。
