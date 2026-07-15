# 运营闭环 Agent Markdown 契约

运营闭环二级页只提供两个只读文档槽位。CRM 不理解或拆分文档中的业务章节；Agent 在每次完整 `operation_cycle_snapshot.v1` 上报中提交 Markdown，最新被接受的快照立即成为当前展示版本。

```json
{
  "documents": {
    "broadcast_details": {
      "markdown": "# 群发数据明细\n\n...",
      "generated_at": "2026-07-14T09:00:00+08:00"
    },
    "execution_strategy": {
      "markdown": "# 执行策略文档\n\n...",
      "generated_at": "2026-07-14T09:00:00+08:00"
    }
  }
}
```

## Markdown 能力

- CommonMark 标题、段落、列表、引用、链接、图片和代码块。
- GFM 表格、删除线和任务清单。
- `mermaid` 代码块支持 `flowchart` / `graph` 基础流程以及 `sequenceDiagram` 基础时序消息。
- `chart` 或 `echarts` 代码块支持 `bar`、`line`、`pie`、`funnel` 四种安全声明式图表。
- 原始 HTML、脚本和任意浏览器代码不会执行。

图表示例：

````markdown
```chart
{
  "type": "funnel",
  "title": "本轮发送漏斗",
  "unit": "人",
  "labels": ["候选", "审计", "建议发送", "有效发送"],
  "series": [
    {"name": "人数", "data": [1275, 895, 848, 845]}
  ]
}
```
````

## AI 助手记录关联

历史群发记录不复制 AI 助手的数据。Agent 在 `references` 中使用现有 `other` 类型和以下固定来源标识，CRM 仅保存精确 `plan_id` 关联；页面随后从 AI 助手原接口读取最新记录并跳转原详情页。

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

不得通过标题或日期模糊匹配计划，也不得在 Markdown、引用或其他快照字段中写入手机号、unionid、external_userid、openid、原始消息或凭据。
