# User Ops Primitive Boundary

日期：2026-04-20

## 目标

明确 `lead-pool current/history` 相关 primitive 从现在开始视为 internal primitive，不再允许 caller 层把它们当正式业务入口使用。

## Primitive 清单

| Symbol | 当前 owner | 定位 | 说明 |
| --- | --- | --- | --- |
| `upsert_user_ops_lead_pool_member` | `wecom_ability_service/domains/user_ops/user_ops_pool_core_service.py` | internal primitive | lead-pool current row upsert + dedupe + history 写入 |
| `write_user_ops_lead_pool_history` | `wecom_ability_service/domains/user_ops/user_ops_pool_core_service.py` | internal primitive | lead-pool history append primitive |
| `plan_user_ops_lead_pool_member_upsert` / `_plan_user_ops_lead_pool_member_upsert` | `user_ops_pool_core_service.py` / `service.py` facade | internal primitive | pool current row merge planning，仅供内部 owner 复用 |
| `normalize_user_ops_lead_pool_activation_state` / `_normalize_user_ops_lead_pool_activation_state` | `user_ops_pool_core_service.py` / `service.py` facade | internal helper | activation state 归一，不应作为 caller 业务入口 |
| `serialize_user_ops_lead_pool_current_row` / `_serialize_user_ops_lead_pool_current_row` | `user_ops_pool_core_service.py` / `service.py` facade | internal helper | current row serialization，仅供内部 owner / 测试兼容使用 |
| `get_user_ops_lead_pool_current_row_by_id` / `_get_user_ops_lead_pool_current_row_by_id` | `user_ops_pool_core_service.py` / `service.py` facade | internal helper | 单 row 读取 helper |
| `list_user_ops_lead_pool_matches` / `_list_user_ops_lead_pool_matches` | `user_ops_pool_core_service.py` / `service.py` facade | internal helper | duplicate / merge 匹配 helper |
| `apply_user_ops_huangxiaocan_activation_source_to_existing_member` | `user_ops_pool_core_service.py` | internal helper | activation import patch 只允许内部 owner 调用 |

## 允许调用范围

- `wecom_ability_service/application/user_ops/*`
  - 仅允许正式 query/command 或 `_legacy_delegate.py` 为兼容而调用
- `wecom_ability_service/domains/user_ops/*`
  - 仅允许已拆出的内部 owner 子模块之间复用
- `wecom_ability_service/services.py`
  - 仅允许作为 compatibility shim 暴露旧符号，不得再长出新业务逻辑
- 测试
  - 仅允许 freeze/contract/helper 测试在必要时直接触达 compatibility surface

## 禁止调用范围

- `wecom_ability_service/http/*`
- `wecom_ability_service/domains/admin_console/*`
- `wecom_ability_service/domains/admin_jobs/*`
- background / callback / sidebar caller 层
- `services.py` 之外的外层 glue 入口
- 任何新的跨 context 调用方

## 调用规则

1. caller 层如果需要改 lead-pool current/history，必须先进入 `application/user_ops/*`
2. 不允许新增 `from ...services import upsert_user_ops_lead_pool_member`
3. 不允许新增 `from ...services import write_user_ops_lead_pool_history`
4. 不允许新增 `from ...domains.user_ops.service import upsert_user_ops_lead_pool_member`
5. 不允许新增 `from ...domains.user_ops.service import write_user_ops_lead_pool_history`

## 兼容说明

- `services.py` 中仍保留这两个符号，是为了兼容旧测试和旧 import 面。
- `domains/user_ops/service.py` 中仍保留 facade，是为了兼容已完成的内部拆分阶段，不代表它们仍是正式业务入口。
- 正式入口口径不变：caller 只能走 `application/user_ops/*`。

