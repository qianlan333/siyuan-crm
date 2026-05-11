# V1 Post-Closeout Backlog

日期：2026-04-22

## 目标

本文件用于说明：

- V1 正式关单后，后续工作应如何管理
- 哪些工作还可以继续做
- 这些工作为什么不能再放回 Wave 1–5 主线

## 原则

V1 已 completed and closed。

因此，后续工作不再以“继续推进 Wave 1–5”的方式管理，而应满足以下原则：

- 不重新打开已关单的 wave
- 不再使用 “顺手继续清” 的方式扩 scope
- 每个后续事项都单独建 backlog 项、专题或新阶段
- 若要继续推进，必须重新定义：
  - 目标
  - 边界
  - 测试冻结范围
  - closeout 条件

## 推荐的 backlog 管理方式

### 1. 分层管理，不混到主线

建议把 V1 之后的工作拆成 3 类：

- `Compatibility Shrink`
  - 继续压缩 `services.py`
  - 压缩 legacy `__init__.py` export surface
  - 收缩 legacy delegate target
- `Access / Adapter Cleanup`
  - access layer 统一
  - transport / repo glue 下沉
  - shared provider/runtime adapter 统一
- `Internal Domain Governance`
  - shared helper 继续下沉
  - page adapter / presenter 收口
  - 同 context runtime / maintenance 模块化

### 2. 只在满足条件时才立项

建议只有在以下情况之一出现时，才继续做后续治理：

- 阻塞新业务
- 持续引发线上风险
- 持续制造高频冲突
- 产生明显维护成本
- 明确能换来可量化的复杂度下降

否则默认只记录在 backlog，不立即开发。

### 3. 统一按“新专题”管理

不要再创建：

- `Wave 1.1`
- `Wave 3 cleanup`
- `Wave 5 leftover patch`

应改为创建新的独立专题，例如：

- `MCP / Integration Cleanup`
- `Admin Console Glue Reduction`
- `AI Access Layer Unification`
- `Automation Transport Narrowing`
- `Questionnaire Internal Split Round 2`

## 建议 backlog 主题

### A. Compatibility Shrink

- 压缩 `services.py` compatibility surface
- 压缩 legacy `domain service` public facade
- 清理 `__init__.py` 过宽 export
- 逐步消化 historical monkeypatch / DI anchor

### B. Access / Transport Cleanup

- customer pulse / followup shared access layer 统一
- admin transport/controller 中的 repo/evidence/audit glue 继续下沉
- MCP / integration bridge 继续 application-only 化
- admin tool registry / `service_paths` metadata 改成 formal owner 描述

### C. Runtime / Provider Cleanup

- AI provider/runtime adapter 统一
- automation workflow/runtime target 继续模块化
- outbound transport/runtime 边界继续收缩

### D. Admin Console / Page Adapter Cleanup

- admin customer profile page adapter 独立
- questionnaire admin console glue 收缩
- automation / AI assist console presenter 继续下沉

### E. Domain Internal Governance

- questionnaire 第二轮内部拆分
- automation 第二轮 internal owner 治理
- AI Assist 第二轮 internal owner 治理
- user_ops read/maintenance façade 继续缩薄

## 不建议继续放回当前主线的事项

以下工作不应再用 “继续 V1 重构” 名义推进：

- 再追加 Wave 6、Wave 7 到同一条主线
- 把 non-blocking exception 继续用 closeout patch 零散清理
- 在没有新测试冻结计划的情况下继续拆内部 helper
- 为了“更干净”而重新触碰已稳定的 compatibility 行为

## 关单后的默认工作模式

建议默认采用：

1. 先记录 backlog
2. 再做收益 / 风险判断
3. 再单独立项
4. 再定义新的 contract / callers / test plan / closeout

而不是：

1. 看见 remaining exception
2. 直接继续改
3. 临时补一轮测试
4. 又生成新的 wave 尾巴

## 最终建议

V1 之后的工作应当被当作“新专题治理”来管理，而不是“继续做 V1 收尾”。

推荐结论：

- V1 关单后停止继续沿同一主线开发
- 保留现有 closeout 文档作为已完成基线
- 所有后续事项全部单列进入 backlog 管理
