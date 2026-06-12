# siyuan AI-CRM baseline merge gate - 2026-06-12

## 1. Executive Summary

Conclusion: READY_FOR_CUTOVER

This report records the merge gate for PR #87 only. It does not start PR-13 and does not perform production cutover.

PR #87 was merged only after the `Deploy to Production` workflow was manually disabled to prevent main-push production deployment. PR #88 remains Draft/open and unmerged as PR-12 restored-data rehearsal evidence.

## 2. Inputs

- PR-12 conclusion: `PASS_WITH_NOTES`
- PR #87 pre-merge head commit: `b1e601baab56bb8e6713a7b2a3646bfdf331d0e9`
- PR #88 head commit at merge gate start: `491ef86df03bbd8b233f0f7a11897952426506e4`
- PR #88 status: Draft/open/unmerged
- PR #88 purpose: restored-data rehearsal evidence only; not intended for merge

## 3. Deploy Workflow Risk Check

Current `main` contained `.github/workflows/deploy.yml` with:

- `on: push` to `main`
- SSH deployment via `appleboy/ssh-action`
- production checkout reset in `/home/ubuntu/极简 crm` using `git reset --hard refs/remotes/origin/main`
- production environment load from `/home/ubuntu/.openclaw-wecom-pg.env`
- `python3 app.py init-next-schema-safe`
- `python3 -m alembic upgrade head`
- `python3 scripts/ensure_channel_multi_staff_schema.py`
- `sudo systemctl restart openclaw-wecom-postgres.service`
- deploy worker/timer unit copy into `/etc/systemd/system/`
- `systemctl daemon-reload`, timer enable/restart, and worker start

Risk result: main-push automatic production deployment existed and was unsafe for PR-11 merge without disabling the workflow first.

## 4. Workflow Disable Gate

`Deploy to Production` was manually disabled through GitHub Actions before merging PR #87.

Observed workflow state before merge:

```text
CI                    active
Deploy to Production  disabled_manually
```

No workflow file was modified in git to disable deployment.

## 5. PR #87 Head / CI Gate

| gate | result | evidence |
|---|---|---|
| expected head unchanged | PASS | `b1e601baab56bb8e6713a7b2a3646bfdf331d0e9` |
| mergeable | PASS | GitHub reported `MERGEABLE` / `CLEAN` |
| draft | PASS | PR #87 was not draft |
| `pr-smoke` | PASS | GitHub check completed successfully |
| blocking failed checks | PASS | no failed required check was observed |

## 6. Merge Result

- PR #87 merged: yes
- merge method: merge commit
- merge commit / main commit: `97c9bf68c789500eb636607e6d3529d6ab9514a9`
- merged at: `2026-06-12T11:33:56Z`

## 7. Post-Merge Production Boundary Confirmation

After merge:

- `Deploy to Production` workflow still showed `disabled_manually`
- recent `Deploy to Production` workflow runs did not include the new main commit `97c9bf68c789500eb636607e6d3529d6ab9514a9`
- only the `CI` workflow started for the new main commit
- production directory `/home/ubuntu/极简 crm` remained at `a43da560dffdf11ffcd350368123e5bcf42ddf15`
- production directory had zero git status changes
- production service was observed only; no restart/reload was issued
- rehearsal port `5016` was free

No production deployment, cutover, production DB migration, systemd/nginx/env change, or production service restart was performed by this merge gate step.

## 8. Security / Boundary Statement

- PR #88 was not merged
- PR-13 was not started
- `.github/workflows/deploy.yml` was not modified
- `deploy/` was not modified
- systemd/nginx/env were not modified
- production service was not restarted or reloaded
- production DB was not migrated, initialized, dropped, deleted, truncated, updated, or schema-changed
- `/home/ubuntu/.openclaw-wecom-pg.env` was not edited
- `/home/ubuntu/极简 crm` was not modified
- no production deployment script was executed

## 9. Next Step

PR #87 is merged and the automatic production deploy workflow is disabled. The repository is ready for the operator-approved PR-13 blue-green cutover phase.

Do not start PR-13 until explicitly approved.
