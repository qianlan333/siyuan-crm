from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "migrations" / "versions"
NUMERIC_BIND_PATTERN = re.compile(r"(?<![:\\]):(?:30|3|1)(?![0-9])")
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


def _migration_revisions() -> dict[str, dict[str, Any]]:
    revisions: dict[str, dict[str, Any]] = {}
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


def _heads(revisions: dict[str, dict[str, Any]]) -> list[str]:
    children = {
        parent
        for item in revisions.values()
        for parent in _parents(item["down_revision"])
    }
    return sorted(set(revisions) - children)


def test_all_revisions_are_unique_and_down_revisions_exist() -> None:
    revisions = _migration_revisions()

    missing = {
        revision: parent
        for revision, item in revisions.items()
        for parent in _parents(item["down_revision"])
        if parent not in revisions
    }

    assert missing == {}


def test_alembic_graph_has_single_head() -> None:
    revisions = _migration_revisions()

    assert _heads(revisions) == ["0036_wechat_shop_sync_runs"]


def test_low_revision_closeout_bridge_and_canonical_ids() -> None:
    revisions = _migration_revisions()

    assert "0013" in revisions
    assert revisions["0013"]["down_revision"] == "0012_wechat_pay_products"
    assert revisions["0014"]["down_revision"] == "0013"
    assert revisions["0012_hxc_growth_cols"]["down_revision"] == "0012"
    assert revisions["0012_wechat_pay_products"]["down_revision"] == "0012_hxc_growth_cols"
    assert revisions["0016_wecom_corp_tag_catalog"]["down_revision"] == "0016"
    assert revisions["0017"]["down_revision"] == "0016_wecom_corp_tag_catalog"
    assert revisions["0022_next_automation_agents"]["down_revision"] == "0021"
    assert revisions["0024_cloud_plan_approval"]["down_revision"] == (
        "0023_product_external_push",
        "0023_group_ops_webhook_rules",
    )
    assert revisions["0025_radar_pdf_preview_assets"]["down_revision"] == "0024_cloud_plan_approval"
    assert "0028_owner_excel_sessions" in revisions


def test_pr3_schema_revision_chain() -> None:
    revisions = _migration_revisions()

    assert revisions["0029_user_ops_prod_tables"]["down_revision"] == "0028_owner_excel_sessions"
    assert revisions["0030_wechat_pay_unionid_idx"]["down_revision"] == "0029_user_ops_prod_tables"
    assert revisions["0031_automation_runtime_v2"]["down_revision"] == "0030_wechat_pay_unionid_idx"
    assert revisions["0032_miniprogram_only_resend_20260611"]["down_revision"] == "0031_automation_runtime_v2"
    assert revisions["0033_complete_miniprogram_only_resend_20260611"]["down_revision"] == "0032_miniprogram_only_resend_20260611"
    assert revisions["0034_reset_miniprogram_only_material_jobs_20260611"]["down_revision"] == "0033_complete_miniprogram_only_resend_20260611"
    assert revisions["0035_wechat_shop_refunds"]["down_revision"] == "0034_reset_miniprogram_only_material_jobs_20260611"
    assert revisions["0036_wechat_shop_sync_runs"]["down_revision"] == "0035_wechat_shop_refunds"

    if "0036_channel_multi_staff_assignment" in revisions:
        assert revisions["0036_channel_multi_staff_assignment"]["down_revision"] == "0035_wechat_shop_refunds"
        assert "0037_siyuan_merge_0036_schema_heads" in revisions
        assert _heads(revisions) == ["0037_siyuan_merge_0036_schema_heads"]


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


def test_alembic_env_widens_version_table_without_printing_secrets() -> None:
    alembic_env = (ROOT / "migrations" / "env.py").read_text(encoding="utf-8")

    assert f"ALEMBIC_VERSION_NUM_LENGTH = {ALEMBIC_VERSION_NUM_LENGTH}" in alembic_env
    assert "CREATE TABLE IF NOT EXISTS alembic_version" in alembic_env
    assert "ALTER COLUMN version_num TYPE VARCHAR" in alembic_env
    assert 'url.startswith("postgres://")' in alembic_env
    assert 'url.startswith("postgresql://")' in alembic_env
    assert "postgresql+psycopg://" in alembic_env
    assert "print(" not in alembic_env


def test_raw_migration_sql_does_not_expose_numeric_bind_literals() -> None:
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

    assert numeric_bind_risks == {}


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
            assert heads == ["0036_wechat_shop_sync_runs (head)"]
