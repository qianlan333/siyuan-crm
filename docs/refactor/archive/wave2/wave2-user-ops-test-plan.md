# Wave 2 User Ops Test Plan

日期：2026-04-20

目标：

- 在真正做 `user_ops` caller cutover 前，先冻结 contract 和高风险副作用。
- 本计划只覆盖准备阶段，不要求本轮补齐全部测试实现。

## 1. 本轮必须保证的基础验证

| 项目 | 目的 | 当前验证方式 |
| --- | --- | --- |
| `application/user_ops/*` 可 import | 确认 formal namespace 已建立 | `tests/test_service_layer_layout.py` import smoke |
| 新 adapter 锚点可 monkeypatch | 给后续测试稳定 patch 位置 | `tests/test_service_layer_layout.py` monkeypatch `wecom_ability_service.infra.user_ops_runtime.*` |
| 旧 `services.py` 锚点仍兼容 | 不打断现有 tests 和 legacy import | 继续跑依赖 `services._user_ops_contact_client` 的最小回归 |

## 2. 后续 caller cutover 前需要冻结的 contract

### 2.1 Read 面

- `GetUserOpsOverviewQuery`
  - 总数卡片不变
  - `generated_at` 仍返回字符串
  - 过滤条件兼容现有 `admin_user_ops` 请求参数

- `ListLeadPoolQuery`
  - `items[] / total / filters / filter_options / meta` 结构不变
  - owner/class-term/filter 组合查询结果不漂移

### 2.2 Write 面

- `ImportExperienceLeadsCommand`
  - 重复手机号 dedupe 语义不变
  - import batch / history 写入不丢

- `ImportMobileClassTermCommand`
  - 同一手机号“最后一行生效”不变
  - 绑定用户会补 current/history；未绑定用户仍可入池

- `ImportActivationStatusCommand`
  - 激活状态写回不要求 class-term 同步存在
  - 非法行仍抛现有 `ValueError`

- `BackfillOwnerClassTermsCommand`
  - single match / conflict / no match 分类不变
  - `owner_mismatch_samples`、`invalid_test_candidate_samples` 语义不变

- `ScheduleUserOpsAutoAssignClassTermJobCommand`
  - 默认 delay 兼容现有行为
  - 重复调度/补偿逻辑不变

- `RunDueUserOpsDeferredJobsCommand`
  - due job limit 行为不变
  - tag refresh / lead pool upsert 副作用不变

### 2.3 Internal primitive

- `UpsertLeadPoolMemberCommand`
  - insert / update / noop 判定不变
  - current/history 对应关系不变

- `WriteLeadPoolHistoryCommand`
  - 只作为内部 primitive 使用
  - 不允许新的 HTTP/admin caller 直接依赖

## 3. 建议补的测试分层

### 3.1 Adapter / skeleton 层

- `tests/test_service_layer_layout.py`
  - import `application/user_ops/*`
  - monkeypatch `wecom_ability_service.infra.user_ops_runtime.get_user_ops_contact_client`
  - monkeypatch `wecom_ability_service.infra.user_ops_runtime.resolve_third_party_user_id_by_mobile`
  - 断言 `services._user_ops_contact_client` / `services._resolve_third_party_user_id_by_mobile` 仍兼容

### 3.2 兼容 regression

- `tests/test_user_ops_api.py`
  - 任选一条依赖 `services._user_ops_contact_client` 的 owner backfill 用例
  - 证明旧 patch 位置未断

- `tests/test_mcp_business_tools.py`
  - 任选一条 `refresh_tags` 用例
  - 证明 customer context 读取仍兼容旧 patch 位置

## 4. 后续 caller cutover 的推荐测试顺序

1. `GetUserOpsOverviewQuery` / `ListLeadPoolQuery`
2. `ImportExperienceLeadsCommand`
3. `ImportMobileClassTermCommand`
4. `ImportActivationStatusCommand`
5. `BackfillOwnerClassTermsCommand`
6. `ScheduleUserOpsAutoAssignClassTermJobCommand`
7. `RunDueUserOpsDeferredJobsCommand`
8. `UpsertLeadPoolMemberCommand` / `WriteLeadPoolHistoryCommand`

## 5. 本轮明确不做的测试扩张

- 不补 user_ops 大规模 API 套件
- 不补 background_jobs / sidebar class-term patch 新测试
- 不补 schema / migration 测试

## 结论

完成本轮后，`user_ops` 会具备：

- formal namespace
- 稳定 adapter 锚点
- 最小 import + monkeypatch 护栏

真正的大规模 caller cutover 仍需后续单独 PR。
