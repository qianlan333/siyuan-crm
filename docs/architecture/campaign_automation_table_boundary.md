# Campaign and Automation Table Boundary

PR #14 documents the runtime boundary instead of deleting active campaign tables.
The current system has three distinct surfaces:

1. Campaign orchestration uses `campaigns`, `campaign_segments`, `campaign_steps`, and `campaign_members`.
   These tables are active because cloud-orchestrator read/write routes and run-due still use them. AI Assist external token creation no longer writes them; it only keeps historical status reads.
2. Group operations automation uses `automation_group_ops_plans`, the `automation_group_ops_*` companion tables, plus `audience_rule*`.
   These tables are active because group plans, webhook intake, segmentation, and execution logs are owned by the group-ops repository.
3. Legacy automation program/workflow tables such as `automation_program` and `automation_workflow` are retired.
   Migration `0053_retire_legacy_automation_tables` removes them; no Next runtime should reintroduce SQL reads or writes.

Campaign execution should converge side effects through `broadcast_jobs` and `external_effect_job`.
Until that convergence is complete, campaign tables remain canonical business state, while send attempts and external calls belong to the broadcast/external-effect ledgers.

`marketing_automation_configs` and `marketing_automation_question_rules` remain active admin config tables.
They are drop candidates only after their settings are reconciled with group-ops plans or a future automation package model.

This boundary gives later cleanup PRs a narrower target:

- Do not delete `campaigns` or `campaign_members` while run-due and campaign admin surfaces depend on them.
- Do not route new business logic back into `automation_program` or `automation_workflow`.
- Prefer new execution/audit work in `broadcast_jobs`, `external_effect_job`, `internal_event`, or the group-ops tables already listed in the lifecycle manifest.
