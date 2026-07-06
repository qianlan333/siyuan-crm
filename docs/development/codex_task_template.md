# Codex Task Template

每个 AI-CRM 开发任务开始前，先读：

- `docs/development/ai_crm_next_architecture_skill.md`
- 若任务涉及前端 / 页面 / 组件 / UI / 管理后台功能，再读 `docs/skills/frontend-development-skill.md`
- 与本任务相关的 route ownership / checker 文档

## Task Intake

- Capability owner:
- Routes involved:
- Current route owner: Next / legacy facade / blocked
- Production data involved: yes / no
- Fixture or local_contract risk: yes / no
- Real external call involved: yes / no
- Checker impact: add / update / not needed
- Rollback:

## Required Boundaries

- Do not change runtime behavior unless the task explicitly asks for it.
- Do not restore `production_compat` or describe it as a live rollback/fallback owner.
- 不要新增 Next 兼容层或兼容 shim，必须完全基于 AI-CRM Next 架构实现需求。
- Do not restore `openclaw_service/` or `legacy_flask/openclaw_legacy/`.
- Do not restore the deleted legacy package.
- Do not modify deploy/nginx/systemd production config unless explicitly approved.
- Do not enable unauthorized real external calls. WeCom External Effect may run
  only inside the PR #1505 approved boundary; Payment / OAuth / OpenClaw / MCP /
  Webhook still need separate approval.
- Do not present local checker output as production canary evidence.

## Completion Checks

- Run the task-specific tests/checkers named in the task prompt before marking a Codex task complete.

## PR Summary Template

### Summary

### Architecture boundary

### Safety / non-goals

### Verification

### Risk / rollback

### Next action
