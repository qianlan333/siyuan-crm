#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aicrm_next.platform_foundation.external_effects.adapters import WECOM_EFFECT_TYPES
from scripts.ops.migrate_app_setting_secrets import _persist_environment_values


DEPRECATED_WECOM_RUNTIME_KEYS = frozenset(
    {
        "AICRM_NEXT_WECOM_REAL_CALLS_ENABLED",
        "AICRM_EXTERNAL_EFFECT_WECOM_EXECUTE",
        "AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES",
        "AICRM_EXTERNAL_EFFECT_ALLOWED_OWNER_USERIDS",
        "AICRM_EXTERNAL_EFFECT_REALTIME_ENABLED",
        "AICRM_EXTERNAL_EFFECT_REALTIME_ALLOWED_TYPES",
        "AICRM_EXTERNAL_EFFECT_REALTIME_MAX_CONCURRENCY",
    }
)


def siyuan_production_runtime_values() -> dict[str, str]:
    return {
        "AICRM_EXTERNAL_EFFECT_RUN_DUE_SCHEDULER_ENABLED": "1",
        "AICRM_EXTERNAL_EFFECT_RUN_DUE_INTERVAL_SECONDS": "60",
        "AICRM_EXTERNAL_EFFECT_RUN_DUE_BATCH_SIZE": "20",
        "AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY": "0",
        "AICRM_WECOM_EXECUTION_MODE": "execute",
        "AICRM_WECOM_ENABLED_EFFECT_TYPES": ",".join(WECOM_EFFECT_TYPES),
        "AICRM_WECOM_PRIVATE_ADAPTER_MODE": "production",
        "AICRM_WECOM_GROUP_ADAPTER_MODE": "production",
        "AICRM_ENABLE_REAL_WECOM_PRIVATE_MESSAGE": "1",
        "AICRM_ENABLE_REAL_WECOM_GROUP_MESSAGE": "1",
        "AICRM_ENABLE_REAL_WECOM_GROUP_SYNC": "1",
    }


def ensure_siyuan_production_runtime_env(environment_file: Path) -> dict[str, str]:
    values = siyuan_production_runtime_values()
    _persist_environment_values(
        environment_file,
        values,
        remove_keys=DEPRECATED_WECOM_RUNTIME_KEYS,
    )
    return values


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Persist non-secret Siyuan production defaults for approved WeCom external effects."
    )
    parser.add_argument("--environment-file", required=True, type=Path)
    args = parser.parse_args()
    values = ensure_siyuan_production_runtime_env(args.environment_file)
    print(
        "siyuan WeCom runtime configured: "
        f"scheduler={values['AICRM_EXTERNAL_EFFECT_RUN_DUE_SCHEDULER_ENABLED']} "
        f"mode={values['AICRM_WECOM_EXECUTION_MODE']} "
        f"effect_type_count={len(WECOM_EFFECT_TYPES)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
