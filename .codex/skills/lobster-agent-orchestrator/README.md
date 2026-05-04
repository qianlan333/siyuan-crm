# Lobster Agent Orchestrator README

## 这套 skill 现在能不能用

可以用。

当前仓库里，龙虾访问 Agent 编排相关能力的 MCP tools 仍然存在，并且这次已经补齐到新版简化口径：

- `list_agent_configs`
- `get_agent_config`
- `create_agent_config`
- `save_agent_prompt_draft`
- `diff_agent_prompt`
- `submit_agent_prompt_for_publish`

本次更新后，龙虾不需要再按旧的 `variables JSON / output_schema JSON` 方式编辑 Agent，推荐统一按下面的新口径使用：

- `role_prompt`
- `task_prompt`
- `enabled_context_sources`

## enabled_context_sources 允许值

- `questionnaire`
- `recent_messages`
- `user_tags`
- `activation_info`

## 提示词里允许插入的占位符

- `{{问卷信息}}`
- `{{最近20条聊天信息}}`
- `{{用户标签}}`
- `{{激活信息}}`

## 最推荐的调用方式

### 1. 查看已有 Agent

先调：

- `list_agent_configs`

再按需调：

- `get_agent_config`

重点看：

- `draft.role_prompt`
- `draft.task_prompt`
- `draft.enabled_context_sources`
- `published.role_prompt`
- `published.task_prompt`
- `published.enabled_context_sources`

### 2. 新建 Agent

调：

- `create_agent_config`

建议最小 payload：

```json
{
  "agent_code": "questionnaire_followup_agent",
  "display_name": "问卷跟进 Agent",
  "enabled": true,
  "role_prompt": "你是问卷跟进 Agent。",
  "task_prompt": "请基于 {{问卷信息}} 和 {{用户标签}} 生成一条首轮跟进话术。",
  "enabled_context_sources": ["questionnaire", "user_tags"],
  "change_summary": "新建问卷跟进 Agent",
  "operator": "lobster"
}
```

### 3. 编辑已有 Agent

调：

- `save_agent_prompt_draft`

示例：

```json
{
  "agent_code": "pricing_agent",
  "task_prompt": "请结合 {{最近20条聊天信息}} 和 {{激活信息}}，输出一条自然的价格答疑话术。",
  "enabled_context_sources": ["recent_messages", "activation_info"],
  "change_summary": "收紧价格答疑话术",
  "expected_draft_version": 7,
  "operator": "lobster"
}
```

### 4. 发布前检查

调：

- `diff_agent_prompt`

### 5. 提交发布申请

调：

- `submit_agent_prompt_for_publish`

## 现在不要再怎么用

不推荐龙虾继续引导运营手工写这些：

- `variables`
- `output_schema`
- `reason`
- `next_action`
- `confidence`

这几层当前都不是运营主口径。

## 运行时实际怎么生效

系统会根据 `enabled_context_sources` 自动收集：

- 问卷信息
- 最近 20 条聊天信息
- 用户标签
- 激活信息

然后把提示词中的占位符替换成可读文本块。

系统内部固定只消费一条输出：

- `draft_reply`

## Skill 包文件

- `SKILL.md`
- `agents/openai.yaml`
- `references/mcp-tool-matrix.md`
- `README.md`
