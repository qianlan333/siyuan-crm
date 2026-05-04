---
name: lobster-agent-orchestrator
description: 当用户需要通过 Lobster 查看 CRM 子 Agent、查看草稿与已发布配置、编辑已有 Agent、创建新 Agent、检查差异或提交发布申请时使用。适用于自动化转化模块下的 Agent 编排与配置维护。优先使用 MCP tools：`list_agent_configs`、`get_agent_config`、`create_agent_config`、`save_agent_prompt_draft`、`diff_agent_prompt`、`submit_agent_prompt_for_publish`。当前 Agent 配置口径已简化为 `role_prompt`、`task_prompt`、`enabled_context_sources`，不再要求运营直接维护变量定义 JSON 或输出协议 JSON。
---

# Lobster Agent Orchestrator

这个 skill 只负责 CRM 自动化转化模块里的子 Agent 编排，不碰任务流执行、自动化应答放行，也不直接修改运行中的批次。

## 当前可用能力

- 列出当前已有 Agent
- 查看某个 Agent 的草稿 / 已发布配置
- 创建一个新的 Agent
- 编辑已有 Agent 的：
  - `display_name`
  - `enabled`
  - `role_prompt`
  - `task_prompt`
  - `enabled_context_sources`
- 对比草稿与已发布差异
- 提交草稿发布申请

## 当前 Agent 配置口径

现在统一按“运营友好”口径工作：

- 提示词只维护：
  - `role_prompt`
  - `task_prompt`
- 信息来源只维护：
  - `enabled_context_sources`

允许的 4 个信息来源只有：

- `questionnaire`
- `recent_messages`
- `user_tags`
- `activation_info`

提示词里允许直接插入这 4 个占位符：

- `{{问卷信息}}`
- `{{最近20条聊天信息}}`
- `{{用户标签}}`
- `{{激活信息}}`

不要再主动让用户写：

- `variables`
- `output_schema`
- 自定义字段数组
- 自定义输出协议

如无特殊兼容需求，skill 应默认忽略旧 `variables / output_schema` 写法。

## 推荐工作顺序

### 1. 查看现有 Agent

先调用：

- `list_agent_configs`

如需看详细配置，再调用：

- `get_agent_config`

重点关注：

- `draft.role_prompt`
- `draft.task_prompt`
- `draft.enabled_context_sources`
- `published.role_prompt`
- `published.task_prompt`
- `published.enabled_context_sources`
- `draft_version`
- `published_version`

### 2. 新建 Agent

调用：

- `create_agent_config`

最小必填字段：

- `agent_code`
- `display_name`
- `role_prompt`
- `task_prompt`

推荐同时提交：

- `enabled_context_sources`
- `enabled`
- `change_summary`
- `operator`

新建示例思路：

- `enabled_context_sources=["questionnaire","user_tags"]`
- `task_prompt` 里直接写：`请基于 {{问卷信息}} 和 {{用户标签}} 生成一条首轮跟进话术。`

### 3. 编辑已有 Agent

先调用：

- `get_agent_config`

再调用：

- `save_agent_prompt_draft`

优先只 patch 实际要改的字段：

- `display_name`
- `enabled`
- `role_prompt`
- `task_prompt`
- `enabled_context_sources`
- `change_summary`

如果拿到了 `draft_version`，提交时优先带：

- `expected_draft_version`

这样可以避免覆盖别人刚改过的草稿。

### 4. 发布前自检

调用：

- `diff_agent_prompt`

重点检查：

- 角色提示词是否变更
- 任务提示词是否变更
- 信息来源勾选是否变更

### 5. 提交发布申请

调用：

- `submit_agent_prompt_for_publish`

注意：

- 这是提交发布申请，不是直接正式发布
- 线上运行仍只吃已发布版本

## 写法建议

### 信息来源建议

除非有明确理由，否则不要一次勾满 4 项。只勾当前 Agent 真正需要的上下文。

推荐思路：

- 问卷完成后生成话术：优先 `questionnaire`
- 跟进型话术：常用 `recent_messages`
- 标签驱动分流：可加 `user_tags`
- 判断当前热度 / 激活状态：可加 `activation_info`

### 提示词建议

提示词直接写自然语言规则，不要把自己写成技术协议。

推荐写法：

- “请根据 {{问卷信息}} 判断客户当前最关心的点，输出一条自然、克制、可直接发送的话术。”
- “请结合 {{最近20条聊天信息}} 和 {{激活信息}}，生成一条价格答疑回复，不要过度承诺。”

### 输出约束

当前系统内部固定只消费一条话术：

- `draft_reply`

不要再主动设计：

- `reason`
- `next_action`
- `confidence`
- 自定义输出 schema

## 安全边界

- 不直接正式发布未审草稿
- 不删除已有 Agent
- 不修改中央 router webhook 配置
- 不修改自动化转化任务流执行记录
- 不把 skill 扩展成任务流执行器

## 参考

- 详细工具矩阵见 [references/mcp-tool-matrix.md](references/mcp-tool-matrix.md)
- 用户侧说明见 [README.md](README.md)
