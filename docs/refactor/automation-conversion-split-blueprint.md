# automation_conversion domain 拆分蓝图

> 状态：起草于 2026-05-09。这是阶段 4 史山治理的指引，不是已完成的总结。

## 现状

`wecom_ability_service/domains/automation_conversion/` 是单 domain 占整库 18%（约 25k 行 Python）的"黑洞"，30 个顶层 .py 文件，6 个核心 *_service 之间职责重叠：

| 文件 | 行数 | 单文件痛点 |
|---|---|---|
| `repo.py` | 3803 | 全 module-level 168 个 def，0 class，10+ 子主题混在一起 |
| `orchestration_service.py` | 3597 | 跨多个 service 的协调器，跟 service.py / workflow_service.py 职责重叠 |
| `workflow_service.py` | 2690 | 工作流编排 + 业务节点执行 + 第三方 API 调用 |
| `workflow_runtime.py` | 1868 | 节点 dispatch + 运行时段判断 + outbound webhook 触发 |
| `service.py` | 1856 | facade 总入口，含大量 ad-hoc 业务逻辑 |
| `workflow_repo.py` | 1710 | 与 repo.py 同层但分到 workflow 这一片 |

## 关键约束（限制激进重组）

`tests/test_automation_conversion_v1.py` 里有 **31 处 `monkeypatch.setattr` 字符串路径**直接耦合到当前文件物理位置：

```python
monkeypatch.setattr(
    "wecom_ability_service.domains.automation_conversion.workflow_runtime.dispatch_wecom_task",
    fake_dispatch,
)
```

文件物理移动 = 31 处字符串路径要同步改 = 高合并冲突风险。

调用方耦合（外部 import）：
- `workflow_service` / `workflow_runtime` 各被 3 处外部 import
- `repo` 被 5 处外部 import（含 `from ..automation_conversion import repo as automation_repo`）

## 拆分原则

1. **不动 monkeypatch 紧耦合的文件名**（`workflow_service.py`、`workflow_runtime.py` 不改名/不移动）
2. **可以把内部 helper 抽出到独立 module，主文件保留 `from ._helpers import *`** —— 不破坏字符串路径（mock 路径还在主文件 namespace）
3. **可以新增子文件 + 主文件 re-export** —— 同上，不破坏 import API
4. **`repo.py` 是最容易拆的**：168 个独立函数，按命名前缀清晰分组，0 class 继承问题

## 阶段 4 推荐路线（独立小 PR 串）

### 阶段 4.1 ✅ 已完成（本 PR #205）

抽 `repo.py` 的 9 个 helper + 1 个常量到 `_repo_helpers.py`。
- 收益：repo.py 3927 → 3803
- 风险：零（helper 函数无外部引用）
- 模式：与阶段 2 (#204) 抽 test helper 同套路

### 阶段 4.2（下一步）：抽 `repo.py` 的 agent_* 系列函数

`repo.py` 里 `agent_prompt` / `agent_config` / `agent_skill` / `agent_router` / `agent_run` / `agent_llm_call_log` 系列约 **30+ 个函数**，全部和 agents 子领域相关。

**做法**：
- 移到现有的 `agents/` 子包下：`agents/repo.py`
- `repo.py` 顶部加 `from .agents.repo import *`（保持外部 API 不变）
- 测试无 monkeypatch 字符串路径耦合 agent_* 函数（已确认）

预期收益：repo.py 再砍 1000-1500 行。

### 阶段 4.3：抽 `repo.py` 的 message_activity / archived_messages 系列

`*_message_activity_*` (5 个) + `*_archived_messages_*` (3 个) 共 ~300 行。
移到 `_repo_messaging.py`。

### 阶段 4.4：抽 `repo.py` 的 sop / focus_send / manual_send / reply_monitor / member 系列

剩余主题分 1-2 PR 处理。

每个子文件 < 800 行后，repo.py 主体 < 1000 行（只剩 `lookup_person_id_*` / 通用 `get_member_*` / `insert_event` 等核心入口）。

### 阶段 4.5：`workflow_service.py` 内部拆分

最危险的一步——31 处 monkeypatch 字符串路径耦合到 `workflow_service` 和 `workflow_runtime`。

可行做法：
- **保留 `workflow_service.py` 文件名作为 facade**
- 把内部纯逻辑（无 monkeypatch 引用的部分）抽到 `workflow_service/_helpers.py` 等子模块
- mock 路径中"被 patch 的具体函数名"全部留在 facade 里（通常是顶层 `dispatch_wecom_task` / `time.time` / `requests.post` 等）

### 阶段 4.6（可选）：`orchestration_service.py` / `service.py` 边界整理

这两个职责重叠严重——orchestration 在做 facade 该做的事，service 在做 orchestration 该做的事。需要架构判断 + 团队对齐，**不是机械拆分能解决的**。建议留作单独阶段，先用 1-2 周读懂代码再动。

## 验证策略（每个子 PR 都要做）

每个拆分 PR 必须：

1. **0 行为变化**：对外 API 完全保留（外部 import / 调用签名不动）
2. **`pytest --collect-only` 用例数不变**
3. **跑相关测试集合**：至少 `test_automation_conversion_v1.py` 子集 + `test_automation_engine_application_contract.py` + admin_console 相关
4. **无 monkeypatch 字符串路径破坏**：对照 `grep '"wecom_ability_service.domains.automation_conversion'` 列表确认覆盖

## 不要做的事（避免坑）

- ❌ 一个 PR 改 5000+ 行 repo 拆分（review 不动 + 冲突爆炸）
- ❌ 重命名 `workflow_service.py` 或 `workflow_runtime.py` 文件（破坏 31 处测试 monkeypatch）
- ❌ 同时拆 repo + 改业务逻辑（混合 PR，回滚困难）
- ❌ 在没看 mock 路径覆盖前移动文件位置

## 架构问题（拆分之后的下一层）

拆完之后真正的问题暴露出来——**为什么 service.py / orchestration_service.py / workflow_service.py 三者职责重叠？**

这是 v1 时代多次重构没收尾留下的——orchestration 是 v0 时代写的协调器，workflow_service 是 wave 4 引入的"workflow 抽象"，service 是事实上的 facade 入口。三者在不同时期被加上，但旧的没下线。

**长期方向**（不在阶段 4 内）：
- 把 service.py 收敛成纯 facade（只 re-export application 层会用的入口）
- orchestration_service.py 评估是否还有意义——如果 application 层已经做了 orchestration（v1 closeout 后 commands/queries 直接调 domain），这个文件大部分可删
- workflow_service.py 是真实业务，但要把 dispatch 部分（外部 API、第三方调用）和 pure logic 部分（节点解析、segment 匹配）分离

## 蓝图维护

每完成一个阶段（4.1 / 4.2 / ...）后，更新本文档的"已完成"状态，让后续 PR 知道哪里走到。
