# CRM Assistant Rules

1. Real sends only start from CRM-approved tokens.
2. Segment SQL must pass the sandbox before being proposed.
3. Campaign segments need explicit priorities when overlap is possible.
4. Frequency budgets are guardrails, not obstacles to bypass.
5. Keep campaign cadence short; long journeys belong in SOP-style workflows.
6. Do not write final copy directly when the copy-workorder flow is available.
7. Avoid oversized batches; narrow the audience or split the plan.
8. Include returned ids and trace ids in the handoff.

## Common Failures

- `forbidden_keyword:*`: rewrite SQL without destructive terms.
- `forbidden_tables:*`: use allowed CRM audience tables.
- `sql_missing_member_id_column`: return `member_id`.
- `approval_token rejected:*`: ask the operator to reissue the CRM approval.
- `budget_exceeded:*`: report that the budget guard blocked execution.
- `do_not_disturb`: skip the customer.
