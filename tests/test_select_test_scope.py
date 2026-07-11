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


def test_h5_wechat_pay_mobile_projection_test_selects_commerce_scope() -> None:
    result = _select("tests/test_h5_wechat_pay_mobile_projection.py")

    assert result["matched_scopes"][:1] == ["commerce"]
    assert "tests/test_h5_wechat_pay_mobile_projection.py" in result["python_tests"]
    assert result["needs_postgres"] is False
    assert result["architecture_gate"] == "fast"
    assert result["needs_full_ci"] is False


def test_public_pay_landing_test_selects_commerce_scope() -> None:
    result = _select("tests/test_public_pay_landing.py")

    assert result["matched_scopes"][:1] == ["commerce"]
    assert "next_native_full_sync" in result["matched_scopes"]
    assert "tests/test_public_pay_landing.py" in result["python_tests"]
    assert result["needs_postgres"] is False
    assert result["architecture_gate"] == "fast"
    assert result["needs_full_ci"] is False


def test_commerce_admin_order_tests_select_commerce_scope() -> None:
    result = _select(
        "aicrm_next/commerce/templates/admin_orders.html",
        "tests/test_admin_p0_commerce_api.py",
        "tests/test_commerce_admin_transaction_detail.py",
    )

    assert result["matched_scopes"][:1] == ["commerce"]
    assert "tests/test_admin_p0_commerce_api.py" in result["python_tests"]
    assert "tests/test_commerce_admin_transaction_detail.py" in result["python_tests"]
    assert result["needs_postgres"] is False
    assert result["architecture_gate"] == "fast"
    assert result["needs_full_ci"] is False


def test_service_period_change_selects_service_period_slice() -> None:
    result = _select(
        "aicrm_next/service_period/api.py",
        "aicrm_next/service_period/templates/service_period_products.html",
        "tests/test_service_period_frontend_contract.py",
    )

    assert result["matched_scopes"][:1] == ["service_period"]
    assert "next_native_full_sync" in result["matched_scopes"]
    assert "tests/test_service_period_application.py" in result["python_tests"]
    assert "tests/test_service_period_h5_payment.py" in result["python_tests"]
    assert "tests/test_service_period_frontend_contract.py" in result["python_tests"]
    assert "tests/test_service_period_schema.py" in result["python_tests"]
    assert "tests/test_router_registry_contract.py" in result["python_tests"]
    assert result["needs_postgres"] is False
    assert result["architecture_gate"] == "fast"
    assert result["needs_full_ci"] is False


def test_questionnaire_mobile_change_selects_questionnaire_and_commerce_slices() -> None:
    result = _select(
        "aicrm_next/questionnaire/domain.py",
        "aicrm_next/questionnaire/h5_write.py",
        "aicrm_next/frontend_compat/templates/questionnaire_h5_page.html",
        "aicrm_next/shared/mobile.py",
        "aicrm_next/commerce/application.py",
        "tests/test_questionnaire_h5_submit_validation.py",
        "tests/test_questionnaire_mobile_normalization.py",
        "tests/test_checkout_api_contract.py",
    )

    assert "questionnaire" in result["matched_scopes"]
    assert "commerce" in result["matched_scopes"]
    assert "mobile_validation" in result["matched_scopes"]
    assert "tests/test_questionnaire_h5_submit_validation.py" in result["python_tests"]
    assert "tests/test_questionnaire_mobile_normalization.py" in result["python_tests"]
    assert "tests/test_checkout_api_contract.py" in result["python_tests"]
    assert result["unmatched_files"] == []
    assert result["needs_postgres"] is False
    assert result["architecture_gate"] == "fast"
    assert result["needs_full_ci"] is False


def test_identity_contact_change_selects_pg_and_db_architecture_gate() -> None:
    result = _select("aicrm_next/identity_contact/application.py")

    assert "identity_contact" in result["matched_scopes"]
    assert "tests/test_identity_application_contract.py" in result["python_tests"]
    assert result["needs_postgres"] is True
    assert result["architecture_gate"] == "db"


def test_wecom_callback_ops_change_selects_identity_contact_slice() -> None:
    result = _select(
        "scripts/ops/check_wecom_callback_deploy_smoke.py",
        "scripts/ops/check_wecom_callback_permanent_fix_readiness.py",
        "scripts/ops/prepare_wecom_callback_ingress_cutover.py",
        "tests/test_wecom_callback_deploy_smoke.py",
        "tests/test_wecom_callback_ingress_runtime.py",
        "tests/test_wecom_callback_permanent_fix_readiness.py",
    )

    assert "identity_contact" in result["matched_scopes"]
    assert set(result["matched_scopes"]) <= {"identity_contact", "next_native_full_sync"}
    assert "tests/test_wecom_callback_inbox.py" in result["python_tests"]
    assert "tests/test_wecom_callback_deploy_smoke.py" in result["python_tests"]
    assert "tests/test_wecom_callback_ingress_runtime.py" in result["python_tests"]
    assert "tests/test_wecom_callback_permanent_fix_readiness.py" in result["python_tests"]
    assert result["unmatched_files"] == []
    assert result["needs_postgres"] is True
    assert result["architecture_gate"] == "db"


def test_sidebar_write_change_selects_write_command_regression() -> None:
    result = _select("aicrm_next/sidebar_write/repo.py")

    assert "customer_read_model_sidebar" in result["matched_scopes"]
    assert "tests/test_sidebar_write_commands.py" in result["python_tests"]
    assert result["needs_postgres"] is True
    assert result["architecture_gate"] == "db"


def test_signed_session_change_selects_sidebar_shared_runtime_slice() -> None:
    result = _select("aicrm_next/shared/signed_session.py")

    assert "shared_sidebar_runtime" in result["matched_scopes"]
    assert "tests/test_sidebar_jssdk_adapter.py" in result["python_tests"]
    assert "tests/test_shared_flask_config_retirement.py" in result["python_tests"]
    assert result["needs_postgres"] is False
    assert result["architecture_gate"] == "fast"


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


def test_admin_read_override_selects_focused_slice_without_pg() -> None:
    result = _select(
        "aicrm_next/ai_audience_ops/admin_api.py",
        "aicrm_next/automation_engine/group_ops/application.py",
        "aicrm_next/ops_enrollment/api.py",
    )

    assert result["matched_scopes"] == ["admin_read_pages"]
    assert "tests/test_ai_audience_admin_pages.py" in result["python_tests"]
    assert "tests/test_group_ops_plans_api.py" in result["python_tests"]
    assert "tests/test_user_ops_api.py" in result["python_tests"]
    assert "tests/test_ai_audience_ops.py" not in result["python_tests"]
    assert "tests/test_group_ops_queue_contract.py" not in result["python_tests"]
    assert "tests/test_user_ops_application_contract.py" not in result["python_tests"]
    assert result["needs_postgres"] is False
    assert result["architecture_gate"] == "fast"


def test_admin_read_smoke_test_file_selects_admin_read_scope() -> None:
    result = _select("tests/test_admin_read_pages_smoke.py")

    assert "admin_read_pages" in result["matched_scopes"]
    assert "tests/test_admin_read_pages_smoke.py" in result["python_tests"]
    assert result["needs_postgres"] is False
    assert result["architecture_gate"] == "fast"


def test_admin_config_page_change_selects_config_scope() -> None:
    result = _select(
        "aicrm_next/admin_config/api.py",
        "aicrm_next/frontend_compat/static/admin_console/config_center.js",
        "aicrm_next/frontend_compat/templates/admin_console/config_admin_access_detail.html",
        "tests/test_admin_config_next.py",
    )

    assert "admin_config" in result["matched_scopes"]
    assert set(result["matched_scopes"]) <= {"admin_config", "next_native_full_sync"}
    assert "tests/test_admin_config_next.py" in result["python_tests"]
    assert "tests/test_operation_member_picker_frontend.py" in result["python_tests"]
    assert "tests/test_admin_auth_login_pages.py" in result["python_tests"]
    assert "tests/test_admin_pages_real_data_binding.py" in result["python_tests"]
    assert result["needs_postgres"] is False
    assert result["architecture_gate"] == "fast"


def test_operation_member_picker_static_assets_select_admin_config_scope() -> None:
    result = _select(
        "aicrm_next/frontend_compat/static/admin_console/admin_console.css",
        "aicrm_next/frontend_compat/static/admin_console/operation_member_picker.js",
        "tests/test_operation_member_picker_frontend.py",
    )

    assert "admin_config" in result["matched_scopes"]
    assert set(result["matched_scopes"]) <= {"admin_config", "next_native_full_sync"}
    assert "tests/test_operation_member_picker_frontend.py" in result["python_tests"]
    assert result["needs_postgres"] is False
    assert result["architecture_gate"] == "fast"
    assert result["needs_full_ci"] is False


def test_operation_member_wecom_sync_change_selects_admin_config_and_db_scope() -> None:
    result = _select(
        "aicrm_next/common_operation_members.py",
        "aicrm_next/operation_members/application.py",
        "aicrm_next/operation_members/repository.py",
        "aicrm_next/integration_gateway/wecom_operation_members_client.py",
        "aicrm_next/frontend_compat/static/admin_console/operation_member_picker.js",
        "aicrm_next/frontend_compat/templates/admin_console/base.html",
        "migrations/versions/0096_admin_wecom_directory_members.py",
        "docs/architecture/route_ownership_manifest.yml",
        "docs/ci/test_scope_manifest.yml",
        "tests/test_wecom_operation_members_sync.py",
        "tests/test_operation_member_picker_frontend.py",
    )

    assert "admin_config" in result["matched_scopes"]
    assert "migration_db" in result["matched_scopes"]
    assert "ci_scope_selector" in result["matched_scopes"]
    assert "tests/test_wecom_operation_members_sync.py" in result["python_tests"]
    assert "tests/test_operation_member_picker_frontend.py" in result["python_tests"]
    assert result["unmatched_files"] == []
    assert result["needs_postgres"] is True
    assert result["architecture_gate"] == "full"
    assert result["needs_full_ci"] is True


def test_wecom_tag_catalog_write_change_selects_real_tag_crud_slice() -> None:
    result = _select(
        "aicrm_next/customer_tags/admin_write.py",
        "aicrm_next/integration_gateway/wecom_tag_live_gateway.py",
        "docs/architecture/wecom_tag_read_route_inventory.md",
        "docs/architecture/wecom_tag_write_route_inventory.md",
        "tests/test_wecom_tag_next_sync.py",
        "tests/test_wecom_tag_write_no_real_side_effects.py",
    )

    assert result["matched_scopes"][0] == "wecom_tag_catalog_write"
    assert "docs_only" in result["matched_scopes"]
    assert "tests/test_wecom_tag_write_no_real_side_effects.py" in result["python_tests"]
    assert "tests/test_wecom_tag_next_sync.py" in result["python_tests"]
    assert "tests/test_wecom_tag_write_commands.py" in result["python_tests"]
    assert "tests/test_wecom_tag_write_idempotency.py" in result["python_tests"]
    assert "tests/test_wecom_tag_write_inventory.py" in result["python_tests"]
    assert "tests/test_wecom_tag_read_selectors.py" in result["python_tests"]
    assert "tests/test_group_ops_queue_contract.py" not in result["python_tests"]
    assert result["needs_postgres"] is False
    assert result["architecture_gate"] == "full"
    assert result["needs_full_ci"] is True


def test_ci_change_selects_contract_tests_and_full_gate() -> None:
    result = _select(".github/workflows/ci-fast.yml")

    assert "ci_deploy" in result["matched_scopes"]
    assert "tests/test_ci_workflow_contract.py" in result["python_tests"]
    assert "tests/test_select_test_scope.py" in result["python_tests"]
    assert result["needs_postgres"] is False
    assert result["architecture_gate"] == "full"
    assert result["needs_full_ci"] is True


def test_runtime_units_change_selects_deploy_contract_tests() -> None:
    result = _select(
        "deploy/production_runtime_units.json",
        "scripts/ops/manage_production_runtime_units.py",
        "tests/test_runtime_units_autostart.py",
        "tests/test_retired_runtime_gap_timer_report.py",
    )

    assert "ci_deploy" in result["matched_scopes"]
    assert "tests/test_deploy_workflow_contract.py" in result["python_tests"]
    assert "tests/test_runtime_units_autostart.py" in result["python_tests"]
    assert "tests/test_retired_runtime_gap_timer_report.py" in result["python_tests"]
    assert result["unmatched_files"] == []
    assert result["needs_postgres"] is False
    assert result["architecture_gate"] == "full"
    assert result["needs_full_ci"] is True


def test_ci_manifest_change_selects_lightweight_selector_scope() -> None:
    result = _select("docs/ci/test_scope_manifest.yml", "tests/test_select_test_scope.py")

    assert result["matched_scopes"] == ["ci_scope_selector"]
    assert result["python_tests"] == ["tests/test_select_test_scope.py", "tests/test_ci_workflow_contract.py"]
    assert result["unmatched_files"] == []
    assert result["needs_postgres"] is False
    assert result["architecture_gate"] == "full"


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
