#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

DEFAULT_MANIFEST = Path("docs/queue/p0-1-production-test-targets.yaml")

TARGET_KEYS = {
    "owner_userid",
    "allowed_external_userids",
    "allowed_webhook_keys",
    "allowed_chat_ids",
    "allowed_group_chat_ids",
    "test_order_no",
    "test_order_nos",
    "test_refund_no",
    "test_external_userid",
    "test_external_userids",
    "allowed_tag_ids",
    "test_tag_ids",
    "test_receiver_url",
    "webhook_key",
    "order_no",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _has_nonempty(value: Any) -> bool:
    if isinstance(value, list):
        return any(_text(item) for item in value)
    if isinstance(value, dict):
        return any(_has_nonempty(item) for item in value.values())
    return bool(_text(value))


def load_manifest(path: str | Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest_path = Path(path)
    with manifest_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("manifest_root_must_be_mapping")
    return data


def validate_manifest(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("version") != 1:
        errors.append("version_must_be_1")
    sections = data.get("sections")
    if not isinstance(sections, dict) or not sections:
        errors.append("sections_required")
        return errors

    for section, raw_config in sections.items():
        config = raw_config if isinstance(raw_config, dict) else {}
        prefix = f"sections.{section}"
        if "enabled_for_real_execute" not in config:
            errors.append(f"{prefix}.enabled_for_real_execute_required")
            continue
        if not isinstance(config.get("enabled_for_real_execute"), bool):
            errors.append(f"{prefix}.enabled_for_real_execute_must_be_bool")

        effect_types = _as_list(config.get("allowed_effect_types"))
        if "*" in {_text(item) for item in effect_types}:
            errors.append(f"{prefix}.allowed_effect_types_wildcard_forbidden")
        if config.get("enabled_for_real_execute") is True:
            if not effect_types or not all(_text(item) for item in effect_types):
                errors.append(f"{prefix}.allowed_effect_types_required")
            if not any(_has_nonempty(config.get(key)) for key in TARGET_KEYS):
                errors.append(f"{prefix}.explicit_target_required")

        if section == "group_broadcast" and config.get("enabled_for_real_execute") is True:
            if not (_has_nonempty(config.get("allowed_chat_ids")) or _has_nonempty(config.get("allowed_group_chat_ids"))):
                errors.append(f"{prefix}.chat_id_required_for_real_execute")
        if section == "payment" and config.get("enabled_for_real_execute") is True:
            if not (_has_nonempty(config.get("test_order_no")) or _has_nonempty(config.get("test_order_nos"))):
                errors.append(f"{prefix}.test_order_no_required_for_real_execute")
        if section == "tags" and config.get("enabled_for_real_execute") is True:
            has_user = _has_nonempty(config.get("test_external_userid")) or _has_nonempty(config.get("test_external_userids")) or _has_nonempty(config.get("allowed_external_userids"))
            has_tag = _has_nonempty(config.get("allowed_tag_ids")) or _has_nonempty(config.get("test_tag_ids"))
            if not has_user:
                errors.append(f"{prefix}.test_external_userid_required_for_real_execute")
            if not has_tag:
                errors.append(f"{prefix}.tag_id_required_for_real_execute")
    return errors


def validate_file(path: str | Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    data = load_manifest(path)
    errors = validate_manifest(data)
    enabled_sections = [
        key
        for key, value in (data.get("sections") or {}).items()
        if isinstance(value, dict) and value.get("enabled_for_real_execute") is True
    ]
    return {
        "ok": not errors,
        "error_count": len(errors),
        "errors": errors,
        "section_count": len(data.get("sections") or {}),
        "enabled_for_real_execute_sections": enabled_sections,
        "manifest": str(path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate P0-1 production test target manifest.")
    parser.add_argument("manifest", nargs="?", default=str(DEFAULT_MANIFEST))
    args = parser.parse_args(argv)
    result = validate_file(args.manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
