# MCP Tool Matrix

## 当前结论

龙虾现在可以继续使用这套 skill 能力，但要按新版口径调用：

- 优先传 `enabled_context_sources`
- 不再把 `variables / output_schema` 当成主输入
- 提示词里直接写占位符：
  - `{{问卷信息}}`
  - `{{最近20条聊天信息}}`
  - `{{用户标签}}`
  - `{{激活信息}}`

## 只读

- `list_agent_configs`
- `get_agent_config`
- `diff_agent_prompt`

## 草稿写入

- `create_agent_config`
- `save_agent_prompt_draft`

## 发布申请

- `submit_agent_prompt_for_publish`

## 推荐调用链

### 查看已有 Agent

1. `list_agent_configs`
2. `get_agent_config`

### 新建 Agent

1. `create_agent_config`
2. `get_agent_config`
3. `diff_agent_prompt`
4. `submit_agent_prompt_for_publish`

### 编辑已有 Agent

1. `get_agent_config`
2. `save_agent_prompt_draft`
3. `diff_agent_prompt`
4. `submit_agent_prompt_for_publish`

## create_agent_config 示例

```json
{
  "agent_code": "questionnaire_followup_agent",
  "display_name": "问卷跟进 Agent",
  "enabled": true,
  "role_prompt": "你是问卷跟进 Agent。",
  "task_prompt": "请基于 {{问卷信息}} 和 {{用户标签}} 生成一条首轮跟进话术。",
  "enabled_context_sources": [
    "questionnaire",
    "user_tags"
  ],
  "change_summary": "新建问卷跟进 Agent",
  "operator": "lobster"
}
```

## save_agent_prompt_draft 示例

```json
{
  "agent_code": "pricing_agent",
  "task_prompt": "请结合 {{最近20条聊天信息}} 和 {{激活信息}}，输出一条自然的价格答疑话术。",
  "enabled_context_sources": [
    "recent_messages",
    "activation_info"
  ],
  "change_summary": "收紧价格话术",
  "expected_draft_version": 7,
  "operator": "lobster"
}
```

## get_agent_config 读取重点

优先看这些字段：

- `agent.agent_code`
- `agent.display_name`
- `agent.draft.role_prompt`
- `agent.draft.task_prompt`
- `agent.draft.enabled_context_sources`
- `agent.published.role_prompt`
- `agent.published.task_prompt`
- `agent.published.enabled_context_sources`
- `agent.draft_version`
- `agent.published_version`

## 注意事项

- `variables / output_schema` 仍可能在返回里保留，用于后端兼容，不是运营主编辑口径
- 当前系统内部固定输出 `draft_reply`
- skill 不应该再引导运营去写数组 JSON 或输出 schema
