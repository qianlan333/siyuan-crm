from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import yaml

from scripts.p0_1_validate_test_targets import load_manifest, validate_file, validate_manifest

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "docs/queue/p0-1-production-test-targets.yaml"


def test_p0_1_production_test_targets_manifest_is_valid() -> None:
    result = validate_file(MANIFEST)

    assert result["ok"] is True
    assert result["error_count"] == 0
    assert result["section_count"] >= 10
    assert result["enabled_for_real_execute_sections"] == ["ai_assist", "group_ops"]


def test_p0_1_manifest_rejects_real_execute_without_target() -> None:
    data = load_manifest(MANIFEST)
    invalid = copy.deepcopy(data)
    invalid["sections"]["ai_assist"].pop("owner_userid", None)
    invalid["sections"]["ai_assist"].pop("allowed_external_userids", None)

    errors = validate_manifest(invalid)

    assert "sections.ai_assist.explicit_target_required" in errors


def test_p0_1_manifest_rejects_wildcard_effect_types() -> None:
    data = load_manifest(MANIFEST)
    invalid = copy.deepcopy(data)
    invalid["sections"]["questionnaire"]["allowed_effect_types"] = ["*"]

    errors = validate_manifest(invalid)

    assert "sections.questionnaire.allowed_effect_types_wildcard_forbidden" in errors


def test_p0_1_manifest_allows_disabled_section_without_target() -> None:
    data = load_manifest(MANIFEST)
    valid = copy.deepcopy(data)
    valid["sections"]["private_broadcast"].pop("owner_userid", None)
    valid["sections"]["private_broadcast"].pop("allowed_external_userids", None)
    valid["sections"]["private_broadcast"]["enabled_for_real_execute"] = False

    errors = validate_manifest(valid)

    assert not [error for error in errors if error.startswith("sections.private_broadcast.")]


def test_p0_1_manifest_rejects_group_broadcast_without_chat_id_when_enabled() -> None:
    data = load_manifest(MANIFEST)
    invalid = copy.deepcopy(data)
    invalid["sections"]["group_broadcast"]["enabled_for_real_execute"] = True

    errors = validate_manifest(invalid)

    assert "sections.group_broadcast.chat_id_required_for_real_execute" in errors


def test_p0_1_manifest_rejects_payment_without_test_order_when_enabled() -> None:
    data = load_manifest(MANIFEST)
    invalid = copy.deepcopy(data)
    invalid["sections"]["payment"]["enabled_for_real_execute"] = True

    errors = validate_manifest(invalid)

    assert "sections.payment.test_order_no_required_for_real_execute" in errors


def test_p0_1_manifest_rejects_tags_without_user_and_tag_when_enabled() -> None:
    data = load_manifest(MANIFEST)
    invalid = copy.deepcopy(data)
    invalid["sections"]["tags"]["enabled_for_real_execute"] = True

    errors = validate_manifest(invalid)

    assert "sections.tags.test_external_userid_required_for_real_execute" in errors
    assert "sections.tags.tag_id_required_for_real_execute" in errors


def test_p0_1_manifest_validation_cli(tmp_path: Path) -> None:
    data = load_manifest(MANIFEST)
    manifest = tmp_path / "targets.yaml"
    manifest.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "app.py", "p0-1-test-targets", "validate", str(manifest)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    body = json.loads(result.stdout)

    assert result.returncode == 0
    assert body["ok"] is True
    assert body["manifest"] == str(manifest)
