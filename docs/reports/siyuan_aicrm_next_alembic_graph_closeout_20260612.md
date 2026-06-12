# siyuan AI-CRM Next Alembic Graph Closeout - 2026-06-12

## Scope

This PR closes the Alembic revision graph for `siyuan-crm` after the PR-1 and
PR-2 Next-native baseline work. It repairs duplicate revision IDs, missing
parents, and multi-head drift, then adds schema-only migrations required by the
current Next runtime.

This PR is code and migration-graph governance only. It does not run production
database migrations and it does not perform production cutover.

## Graph Result

- Revision graph has no duplicate revision IDs.
- Revision graph has no missing `down_revision` parent.
- Revision graph has one head: `0036_wechat_shop_sync_runs`.
- `0013` exists as a no-op bridge so historical `0014_alipay_pay.py` can keep
  `down_revision = "0013"`.
- `0024_cloud_plan_approval` merges the two existing `0023` schema branches.

## Schema Migrations

The PR adds or repairs these schema-only revisions:

- `0013` - no-op bridge after `0012_wechat_pay_products`.
- `0029_user_ops_prod_tables` - User Ops production read-model tables.
- `0030_wechat_pay_unionid_idx` - guarded WeChat Pay `unionid` lookup index.
- `0031_automation_runtime_v2` - Automation Runtime v2 tables and runtime check
  constraints.
- `0032_miniprogram_only_resend_20260611` - siyuan-safe no-op placeholder.
- `0033_complete_miniprogram_only_resend_20260611` - siyuan-safe no-op
  placeholder.
- `0034_reset_miniprogram_only_material_jobs_20260611` - siyuan-safe no-op
  placeholder.
- `0035_wechat_shop_refunds` - WeChat Shop refund audit table.
- `0036_wechat_shop_sync_runs` - WeChat Shop sync run audit table.

Channel multi-staff assignment schema is deferred because the current
`siyuan-crm` runtime code does not reference `automation_channel` assignment
columns or `automation_channel_assignee` / `automation_channel_assignment_event`
tables.

## Production Data Boundary

The AI-CRM `0032`, `0033`, and `0034` migrations are production data migrations
in the source project. In `siyuan-crm` they are intentionally no-op placeholders
to preserve the revision chain without importing source business data.

This PR does not import:

- AI-CRM campaign data.
- AI-CRM campaign member data.
- AI-CRM broadcast job mutations.
- AI-CRM product/order/user data.
- Real `group_code`, `external_userid`, `scene_value`, `mobile`, `unionid`, or
  `openid` values.

## Alembic Runtime

`migrations/env.py` now:

- reads `DATABASE_URL` from the environment;
- rewrites `postgres://` and `postgresql://` to `postgresql+psycopg://`;
- keeps `ALEMBIC_VERSION_NUM_LENGTH = 128`;
- creates `alembic_version` with `VARCHAR(128)` when needed on PostgreSQL;
- widens existing `alembic_version.version_num` to `VARCHAR(128)`;
- does not print the database URL or any secret.

Offline mode remains available for SQL generation.

## Validation

Commands run locally for this PR:

```bash
python3 -m compileall app.py aicrm_next scripts tools tests
```

Result: passed.

```bash
python3 -m pytest tests/test_alembic_revision_chain.py -q
```

Result:

```text
8 passed
```

```bash
python3 -m alembic heads
```

Result:

```text
0036_wechat_shop_sync_runs (head)
```

```bash
python3 -m alembic history --verbose > /tmp/pr3_alembic_history.txt
```

Result: passed.

```bash
python3 - <<'PY'
from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

root = Path("migrations/versions")
revisions = {}
paths_by_revision = defaultdict(list)
parents = {}

def literal_assignment(tree, name):
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return ast.literal_eval(node.value)
    raise RuntimeError(f"{name} not found")

def parent_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (tuple, list)):
        return list(value)
    raise RuntimeError(f"bad down_revision {value!r}")

for path in sorted(root.glob("*.py")):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    revision = literal_assignment(tree, "revision")
    down_revision = literal_assignment(tree, "down_revision")
    paths_by_revision[revision].append(str(path))
    revisions[revision] = str(path)
    parents[revision] = parent_list(down_revision)

duplicates = {rev: paths for rev, paths in paths_by_revision.items() if len(paths) > 1}
missing = {
    rev: parent
    for rev, parent_list_ in parents.items()
    for parent in parent_list_
    if parent not in revisions
}
children = defaultdict(list)
for rev, parent_list_ in parents.items():
    for parent in parent_list_:
        children[parent].append(rev)
heads = sorted(set(revisions) - set(children))

print("revision_count", len(revisions))
print("heads", heads)
assert duplicates == {}, duplicates
assert missing == {}, missing
assert len(heads) == 1, heads
print("alembic_static_graph_ok")
PY
```

Result:

```text
revision_count 40
heads ['0036_wechat_shop_sync_runs']
alembic_static_graph_ok
```

```bash
git grep -n -E "HuangYouCan|external_second_push_feishu|mini_only_20260611|INSERT INTO campaigns|INSERT INTO campaign_members|INSERT INTO campaign_steps|UPDATE broadcast_jobs" -- migrations/versions || true
```

Result: `0032` / `0033` / `0034` have no matches. The only matches are
pre-existing `UPDATE broadcast_jobs` statements in
`0021_broadcast_queue_platform_hardening.py`.

```bash
git grep -n -E "DATABASE_URL=|WECOM_SECRET=|WECOM_CALLBACK_AES_KEY=|WECHAT_MP_APP_SECRET=|SECRET_KEY=|CRM_API_TOKEN=|MCP_BEARER_TOKEN=|SIDEBAR_THIRD_PARTY_API_TOKEN=|AUTOMATION_INTERNAL_API_TOKEN=.*[A-Za-z0-9_-]{12,}|BEGIN RSA PRIVATE KEY|BEGIN PRIVATE KEY" -- . ':!*.md' ':!*.example' || true
```

Result: no new secret from this PR; matches are existing scripts, test
placeholders, or config env reads.

```bash
git diff --check
```

Result: passed.

```bash
python3 - <<'PY'
import pathlib, yaml
for path in [
    "docs/architecture/legacy_exit_route_registry.yaml",
    "docs/route_ownership/production_route_ownership_manifest.yaml",
    "docs/development/phase_execution_state.yaml",
]:
    p = pathlib.Path(path)
    if p.exists():
        yaml.safe_load(p.read_text())
        print("yaml_ok", path)
PY
```

Result:

```text
yaml_ok docs/architecture/legacy_exit_route_registry.yaml
yaml_ok docs/route_ownership/production_route_ownership_manifest.yaml
yaml_ok docs/development/phase_execution_state.yaml
```

```bash
python3 app.py health
python3 app.py routes > /tmp/pr3_routes.txt
```

Result:

```text
{'ok': True, 'status_code': 200, 'default_runtime': 'ai_crm_next', 'route_owner': 'ai_crm_next'}
```

```bash
python3 -m pytest \
  tests/test_pr1_core_next_routes.py \
  tests/test_external_orders_api.py \
  tests/test_pr2_external_orders_routes.py \
  -q
```

Result:

```text
13 passed, 1 warning
```

Scratch DB `alembic upgrade head` was not executed because no safe scratch
`DATABASE_URL` was provided in this local environment.

## Production Notes

- PR-3 only repairs code and migration graph state.
- No production DB migration was executed.
- No production cutover was executed.
- Production switching still requires an independent runbook.
- A staging restored DB should rehearse `alembic upgrade head` before any
  production migration.
- If a server rollout continues to use `python3 app.py init-next-schema-safe` as
  a temporary guard, the run result must be recorded separately.

## Security Statement

- No env file committed.
- No dump committed.
- No uploads or instance data committed.
- No pem/key material committed.
- No token, secret, AESKey, AppSecret, or database URL committed.
- No production DB action executed.
- No AI-CRM production data imported.
