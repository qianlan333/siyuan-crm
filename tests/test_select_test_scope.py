from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SELECTOR = ROOT / "scripts" / "ci" / "select_test_scope.py"


def _select(*changed_files: str) -> dict:
    command = [sys.executable, str(SELECTOR), "--json"]
    for changed_file in changed_files:
        command.extend(["--changed-file", changed_file])
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        check=True,
        capture_output=True,
    )
    return json.loads(completed.stdout)


def test_media_library_change_runs_small_no_pg_slice() -> None:
    result = _select("aicrm_next/commerce/templates/wechat_products.html")

    assert "commerce" in result["matched_scopes"]
    assert "media_library" in result["matched_scopes"]
    assert "tests/test_image_upload_client_static.py" in result["python_tests"]
    assert "tests/test_image_library_template.py" in result["python_tests"]
    assert "tests/test_wechat_products_admin_page_contract.py" in result["python_tests"]
    assert result["frontend_tests"] == []
    assert result["needs_postgres"] is False
    assert result["architecture_gate"] == "fast"
    assert result["needs_full_ci"] is False


def test_identity_contact_change_selects_pg_and_db_architecture_gate() -> None:
    result = _select("aicrm_next/identity_contact/application.py")

    assert "identity_contact" in result["matched_scopes"]
    assert "tests/test_identity_application_contract.py" in result["python_tests"]
    assert result["needs_postgres"] is True
    assert result["architecture_gate"] == "db"


def test_ai_assist_external_campaign_change_selects_focused_python_slice() -> None:
    result = _select("aicrm_next/ai_assist/external_campaigns.py")

    assert "ai_assist_external_campaigns" in result["matched_scopes"]
    assert "tests/test_ai_assist_external_campaigns.py" in result["python_tests"]
    assert result["needs_postgres"] is False
    assert result["architecture_gate"] == "fast"


def test_user_ops_change_selects_batch_send_contract_slice() -> None:
    result = _select("aicrm_next/ops_enrollment/application.py")

    assert "user_ops" in result["matched_scopes"]
    assert "tests/test_user_ops_api.py" in result["python_tests"]
    assert "tests/test_user_ops_external_effect_enqueue.py" in result["python_tests"]
    assert "tests/test_user_ops_send_record_projection.py" in result["python_tests"]
    assert result["needs_postgres"] is False
    assert result["architecture_gate"] == "fast"


def test_ci_change_selects_contract_tests_and_full_gate() -> None:
    result = _select(".github/workflows/ci-fast.yml")

    assert "ci_deploy" in result["matched_scopes"]
    assert "tests/test_ci_workflow_contract.py" in result["python_tests"]
    assert "tests/test_select_test_scope.py" in result["python_tests"]
    assert result["needs_postgres"] is False
    assert result["architecture_gate"] == "full"
    assert result["needs_full_ci"] is True


def test_frontend_typescript_change_runs_frontend_tests_and_build() -> None:
    result = _select("frontend/admin/push_center/push_center_status.ts")

    assert "frontend_p1" in result["matched_scopes"]
    assert "tests/frontend/p1_push_center_status.test.mjs" in result["frontend_tests"]
    assert result["needs_frontend_build"] is True
    assert result["python_tests"] == []


def test_next_native_sync_surface_change_selects_baseline_scope() -> None:
    result = _select("aicrm_next/admin_shell/routes.py")

    assert "next_native_full_sync" in result["matched_scopes"]
    assert "tests/test_startup_entrypoint_next_only.py" in result["python_tests"]
    assert "tests/test_router_registry_contract.py" in result["python_tests"]
    assert result["architecture_gate"] == "fast"


def test_unmapped_path_fails_instead_of_falling_back_to_full_regression() -> None:
    completed = subprocess.run(
        [sys.executable, str(SELECTOR), "--changed-file", "aicrm_next/new_context/api.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 2
    assert "No CI test scope matched" in completed.stderr
    assert "aicrm_next/new_context/api.py" in completed.stderr
