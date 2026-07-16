from __future__ import annotations

from pathlib import Path

from aicrm_next.platform_foundation.external_effects.adapters import WECOM_EFFECT_TYPES
from scripts.ops.ensure_siyuan_production_runtime_env import (
    ensure_siyuan_production_runtime_env,
    siyuan_production_runtime_values,
)


def test_siyuan_runtime_values_enable_supported_wecom_effects_only() -> None:
    values = siyuan_production_runtime_values()

    assert values == {
        "AICRM_WECOM_EXECUTION_MODE": "execute",
        "AICRM_WECOM_ENABLED_EFFECT_TYPES": ",".join(WECOM_EFFECT_TYPES),
        "AICRM_WECOM_PRIVATE_ADAPTER_MODE": "production",
        "AICRM_WECOM_GROUP_ADAPTER_MODE": "production",
        "AICRM_ENABLE_REAL_WECOM_PRIVATE_MESSAGE": "1",
        "AICRM_ENABLE_REAL_WECOM_GROUP_MESSAGE": "1",
        "AICRM_ENABLE_REAL_WECOM_GROUP_SYNC": "1",
    }
    assert all(not effect_type.startswith(("payment.", "oauth.", "webhook.", "mcp.")) for effect_type in WECOM_EFFECT_TYPES)


def test_siyuan_runtime_env_migration_is_idempotent_and_preserves_secrets(tmp_path: Path) -> None:
    environment_file = tmp_path / "siyuan.env"
    environment_file.write_text(
        "SECRET_KEY='keep-me'\n"
        "WECOM_CONTACT_SECRET='keep-contact-secret'\n"
        "AICRM_NEXT_WECOM_REAL_CALLS_ENABLED='true'\n"
        "AICRM_EXTERNAL_EFFECT_WECOM_EXECUTE='1'\n"
        "AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES='wecom.contact.tag.mark'\n"
        "AICRM_WECOM_EXECUTION_MODE='disabled'\n",
        encoding="utf-8",
    )
    environment_file.chmod(0o600)

    first = ensure_siyuan_production_runtime_env(environment_file)
    first_body = environment_file.read_text(encoding="utf-8")
    second = ensure_siyuan_production_runtime_env(environment_file)

    assert first == second == siyuan_production_runtime_values()
    assert environment_file.read_text(encoding="utf-8") == first_body
    assert "SECRET_KEY='keep-me'" in first_body
    assert "WECOM_CONTACT_SECRET='keep-contact-secret'" in first_body
    assert "AICRM_WECOM_EXECUTION_MODE='execute'" in first_body
    assert f"AICRM_WECOM_ENABLED_EFFECT_TYPES='{','.join(WECOM_EFFECT_TYPES)}'" in first_body
    assert "AICRM_NEXT_WECOM_REAL_CALLS_ENABLED" not in first_body
    assert "AICRM_EXTERNAL_EFFECT_WECOM_EXECUTE" not in first_body
    assert "AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES" not in first_body
