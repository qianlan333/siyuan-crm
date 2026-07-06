# CLAUDE.md

## 前端开发第一入口

在 AI-CRM 仓库内执行任何前端开发、页面开发、组件开发、UI 调整或管理后台功能开发之前，必须先阅读并遵守
[docs/skills/frontend-development-skill.md](docs/skills/frontend-development-skill.md)。

该 Skill 优先级高于一般开发习惯；如果未读取该 Skill，不应开始前端实现。后续任何前端任务的最终回复必须输出
`Frontend Skill Checklist`。

## 架构开发第一入口

所有 AI-CRM 开发任务都必须先阅读并遵守
[docs/development/ai_crm_next_architecture_skill.md](docs/development/ai_crm_next_architecture_skill.md)。
这是 AI-CRM Next 架构、生产安全、legacy freeze、外呼审批和 PR 输出格式的 canonical preflight。

## 生产诊断入口

主仓入口不记录具体生产 host、SSH alias、identity、本机权限配置、白名单命令、
生产路径或查询 cookbook。需要生产诊断时，先确认任务已获得生产读取授权，再使用
私有 ops handoff 中的当前入口；不要在 PR、issue、公开文档或 agent entry 里新增
连接细节。

本文件只保留安全边界：

- 生产诊断默认只读；任何写操作、DDL、部署切换、systemd/nginx 修改都需要单独人工审批。
- 不把本地 checker、dry-run 或只读诊断写成 production canary evidence。
- 真实外呼按架构门禁处理：WeCom External Effect 仅限 PR #1505 批准范围；Payment / OAuth / OpenClaw / MCP / Webhook 仍需单独审批。
