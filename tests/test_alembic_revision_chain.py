from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "migrations" / "versions"
NUMERIC_BIND_PATTERN = re.compile(r"(?<![:\\]):[0-9]+")
ALEMBIC_VERSION_NUM_LENGTH = 128
PLACEHOLDER_REVISIONS = (
    "0032_miniprogram_only_resend_20260611",
    "0033_complete_miniprogram_only_resend_20260611",
    "0034_reset_miniprogram_only_material_jobs_20260611",
)
FORBIDDEN_PRODUCTION_DATA_MARKERS = (
    "HuangYouCan",
    "external_second_push_feishu",
    "mini_only_20260611",
    "INSERT INTO campaigns",
    "INSERT INTO campaign_members",
    "INSERT INTO campaign_steps",
    "UPDATE broadcast_jobs",
)


def _literal_assignment(tree: ast.Module, name: str) -> Any:
    for node in tree.body:
        target_name = None
        value = None
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    target_name = target.id
                    value = node.value
                    break
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_name = node.target.id
            value = node.value
        if target_name == name and value is not None:
            return ast.literal_eval(value)
    raise AssertionError(f"{name} assignment not found")


def _migration_revisions() -> dict[str, Any]:
    revisions: dict[str, Any] = {}
    for path in sorted(VERSIONS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        revision = _literal_assignment(tree, "revision")
        down_revision = _literal_assignment(tree, "down_revision")
        assert revision not in revisions, f"duplicate Alembic revision id {revision}"
        revisions[revision] = {"path": path, "down_revision": down_revision}
    return revisions


def _parents(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (tuple, list)):
        return [str(item) for item in value]
    raise AssertionError(f"unsupported down_revision value: {value!r}")


def test_all_alembic_down_revisions_exist() -> None:
    revisions = _migration_revisions()

    missing = {
        revision: parent
        for revision, item in revisions.items()
        for parent in _parents(item["down_revision"])
        if parent not in revisions
    }

    assert missing == {}


def test_alembic_revision_storage_supports_deployed_revision_ids() -> None:
    revisions = _migration_revisions()
    old_hxc_revision = "0012_hxc_dashboard_v6_" + "growth_columns"
    old_cloud_revision = "0024_cloud_plan_recipient_" + "approval"
    old_owner_revision = "0028_owner_migration_excel_" + "sessions"
    old_wechat_unionid_revision = "0029_wechat_pay_order_" + "unionid_index"

    beyond_runtime_limit = {
        revision: {"length": len(revision), "path": str(item["path"])}
        for revision, item in revisions.items()
        if len(revision) > ALEMBIC_VERSION_NUM_LENGTH
    }
    alembic_env = (ROOT / "migrations" / "env.py").read_text(encoding="utf-8")

    assert beyond_runtime_limit == {}
    assert f"ALEMBIC_VERSION_NUM_LENGTH = {ALEMBIC_VERSION_NUM_LENGTH}" in alembic_env
    assert "CREATE TABLE IF NOT EXISTS alembic_version" in alembic_env
    assert "ALTER COLUMN version_num TYPE VARCHAR" in alembic_env
    assert old_hxc_revision not in revisions
    assert old_cloud_revision not in revisions
    assert old_owner_revision not in revisions
    assert old_wechat_unionid_revision not in revisions
    assert "0012_hxc_growth_cols" in revisions
    assert "0024_cloud_plan_approval" in revisions
    assert "0028_owner_excel_sessions" in revisions
    assert "0029_user_ops_prod_tables" in revisions
    assert "0030_wechat_pay_unionid_idx" in revisions
    assert "0032_miniprogram_only_resend_20260611" in revisions
    assert "0033_complete_miniprogram_only_resend_20260611" in revisions


def test_alembic_chain_keeps_0014_parent_available() -> None:
    revisions = _migration_revisions()

    assert "0013" in revisions
    assert revisions["0014"]["down_revision"] == "0013"
    assert revisions["0013"]["down_revision"] == "0012_wechat_pay_products"


def test_user_ops_production_tables_migration_is_parent_of_wechat_unionid_index() -> None:
    revisions = _migration_revisions()

    assert revisions["0029_user_ops_prod_tables"]["down_revision"] == "0028_owner_excel_sessions"
    assert revisions["0030_wechat_pay_unionid_idx"]["down_revision"] == "0029_user_ops_prod_tables"


def test_siyuan_production_channel_assignment_revision_is_locatable() -> None:
    revisions = _migration_revisions()
    revision_id = "0037_channel_multi_staff_assignment"
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))

    assert revision_id in revisions
    assert revisions[revision_id]["path"].name == "0037_channel_multi_staff_assignment.py"
    assert revisions[revision_id]["down_revision"] == "0036_wechat_shop_sync_runs"
    assert script.get_revision(revision_id).revision == revision_id


def test_siyuan_production_channel_assignment_revision_can_upgrade_to_head() -> None:
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    upgrade_steps = script._upgrade_revs("heads", "0037_channel_multi_staff_assignment")
    upgrade_revision_ids = {step.revision.revision for step in upgrade_steps}

    assert "0038_merge_duplicate_channel_wechat_shop_heads" in upgrade_revision_ids
    assert "0037_channel_multi_staff_assignment" in _parents(
        _migration_revisions()["0038_merge_duplicate_channel_wechat_shop_heads"]["down_revision"]
    )


def test_siyuan_channel_assignment_migration_is_idempotent_overlay() -> None:
    source = (VERSIONS / "0037_channel_multi_staff_assignment.py").read_text(encoding="utf-8")

    assert "ADD COLUMN IF NOT EXISTS assignment_mode" in source
    assert "ADD COLUMN IF NOT EXISTS assignment_strategy" in source
    assert "ADD COLUMN IF NOT EXISTS overflow_policy" in source
    assert "ADD COLUMN IF NOT EXISTS assignment_config_json" in source
    assert "CREATE TABLE IF NOT EXISTS automation_channel_assignee" in source
    assert "CREATE TABLE IF NOT EXISTS automation_channel_assignment_event" in source
    assert "CREATE INDEX IF NOT EXISTS idx_channel_assignee_active" in source
    assert "CREATE INDEX IF NOT EXISTS idx_channel_assignment_24h" in source
    assert "CREATE INDEX IF NOT EXISTS idx_channel_assignment_external" in source


def test_siyuan_placeholders_do_not_import_ai_crm_production_data() -> None:
    revisions = _migration_revisions()

    for revision in PLACEHOLDER_REVISIONS:
        path = revisions[revision]["path"]
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}

        assert "AI-CRM product data migration intentionally no-op for siyuan" in source
        assert all(marker not in source for marker in FORBIDDEN_PRODUCTION_DATA_MARKERS)
        assert set(functions) >= {"upgrade", "downgrade"}
        for name in ("upgrade", "downgrade"):
            assert len(functions[name].body) == 1
            assert isinstance(functions[name].body[0], ast.Pass)


def test_raw_migration_sql_does_not_expose_numeric_bind_literals() -> None:
    risky_default_prefix = '"default"' + ":"
    old_sqlalchemy_rendered_default = "default" + "%("
    raw_sql_strings: list[tuple[Path, int, str]] = []

    for path in sorted(VERSIONS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "execute"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                continue
            raw_sql_strings.append((path, node.lineno, node.args[0].value))

    numeric_bind_risks = {
        f"{path.relative_to(ROOT)}:{lineno}": NUMERIC_BIND_PATTERN.findall(sql)
        for path, lineno, sql in raw_sql_strings
        if NUMERIC_BIND_PATTERN.search(sql)
    }
    raw_json_default_risks = {
        f"{path.relative_to(ROOT)}:{lineno}": sql
        for path, lineno, sql in raw_sql_strings
        if any(f"{risky_default_prefix}{value}" in sql for value in ("30", "3", "1"))
        or old_sqlalchemy_rendered_default in sql
    }

    assert numeric_bind_risks == {}
    assert raw_json_default_risks == {}

    group_ops_migration = VERSIONS / "0023_group_ops_webhook_rules.py"
    source = group_ops_migration.read_text(encoding="utf-8")
    assert "builtin:has_used_core_feature" in source
    assert '"default"' + ":30" not in source
    assert '"default"' + ":3" not in source
    assert old_sqlalchemy_rendered_default not in source


def test_alembic_commands_can_walk_revision_graph() -> None:
    for args in (("heads",), ("history", "--verbose")):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert "is not present" not in result.stderr
        assert "KeyError" not in result.stderr
        if args == ("heads",):
            heads = [line for line in result.stdout.splitlines() if "(head)" in line]
            assert len(heads) == 1
            assert "0038_merge_duplicate_channel_wechat_shop_heads" in heads[0]
