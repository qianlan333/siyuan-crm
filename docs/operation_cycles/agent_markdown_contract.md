# 运营闭环 Agent Markdown 契约

完整接入流程见 [`agent_usage_guide.md`](agent_usage_guide.md)。本文件只定义页面直接读取的三份 Markdown 和历史发送记录的关联方式。

运营闭环二级页提供三个只读文档槽位。CRM 不理解或拆分文档中的业务章节；Agent 在每次完整 `operation_cycle_snapshot.v1` 上报中提交 Markdown，最新被接受的快照立即成为当前展示版本。

```json
{
  "documents": {
    "broadcast_details": {
      "markdown": "# 本周发送数据\n\n...",
      "generated_at": "2026-07-15T09:00:00+08:00"
    },
    "retrospective_details": {
      "markdown": "# 本周复盘明细\n\n...",
      "generated_at": "2026-07-15T09:05:00+08:00"
    },
    "execution_strategy": {
      "markdown": "# 下周执行策略\n\n...",
      "generated_at": "2026-07-15T09:10:00+08:00"
    }
  }
}
```

## 三份文档的职责

| 字段 | 页面入口 | 应放内容 | 不应放内容 |
| --- | --- | --- | --- |
| `broadcast_details` | 本周发送数据 | 候选、审计、建议发送、计划目标、有效发送、失败、数据源与发送窗口 | 逐人名单、原始消息、无法核验的效果结论 |
| `retrospective_details` | 本周复盘明细 | 已核验结论、观察、限制、冲突、缺口和本周经验 | 下周尚未确认的动作冒充已执行结果 |
| `execution_strategy` | 下周执行策略 | 下周目标、执行顺序、前置条件、验证口径和待确认项 | 在 CRM 页面触发批准、发送或模板修改的指令 |

旧快照没有 `retrospective_details` 时仍然可以读取；页面显示标准空态，直到 Agent 上报更高 revision 的完整快照。

## Markdown 能力

- CommonMark 标题、段落、列表、引用、链接、图片和代码块。
- GFM 表格、删除线和任务清单。
- `mermaid` 代码块支持基础 `flowchart` / `graph` 和基础 `sequenceDiagram`。
- `chart` 或 `echarts` 代码块支持 `bar`、`line`、`pie`、`funnel` 四种安全声明式图表。
- 原始 HTML、脚本、任意浏览器代码和外部图表配置不会执行。

图表示例：

````markdown
```chart
{
  "type": "funnel",
  "title": "本周发送漏斗",
  "unit": "人",
  "labels": ["候选", "审计", "建议发送", "有效发送"],
  "series": [
    {"name": "人数", "data": [1275, 895, 848, 845]}
  ]
}
```
````

## 历史发送记录关联

历史发送记录不复制 AI 助手的数据。Agent 在 `references` 中使用以下固定来源标识，CRM 仅保存精确 `plan_id` 关联；页面随后从 AI 助手原接口读取记录并跳转原详情页。

```json
{
  "reference_key": "ai-assistant-plan:<stable-key>",
  "reference_type": "other",
  "label": "本轮 AI 助手计划",
  "source_system": "cloud_orchestrator_plan",
  "source_id": "<plan_id>",
  "href": "/admin/cloud-orchestrator/plans/<plan_id>",
  "evidence_hash": "",
  "data_status": "unknown"
}
```

不得通过标题或日期模糊匹配计划，也不得在 Markdown、引用或其他快照字段中写入手机号、邮箱、unionid、external_userid、openid、原始消息、逐人名单、凭据或本地文件路径。
