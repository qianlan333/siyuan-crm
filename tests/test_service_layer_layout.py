from __future__ import annotations

import ast
from pathlib import Path

from wecom_ability_service.domains import DOMAIN_LAYOUTS


# Domains that exist as directories but don't yet follow the standard
# service.py / repo.py layout convention. Excluded from both registry-match
# and file-mode checks until they are fleshed out.
_STUB_DOMAINS = {"image_library", "miniprogram_library", "media_library", "campaigns", "cloud_orchestrator", "segments", "admin_auth", "broadcast_jobs"}


def test_domain_layout_registry_matches_domain_directories():
    domains_dir = Path(__file__).resolve().parents[1] / "wecom_ability_service" / "domains"
    actual = {
        path.name
        for path in domains_dir.iterdir()
        if path.is_dir() and not path.name.startswith("__")
    }
    assert set(DOMAIN_LAYOUTS.keys()) | _STUB_DOMAINS == actual | _STUB_DOMAINS


def test_domain_layout_files_match_declared_mode():
    domains_dir = Path(__file__).resolve().parents[1] / "wecom_ability_service" / "domains"
    for domain_name, spec in DOMAIN_LAYOUTS.items():
        domain_dir = domains_dir / domain_name
        assert (domain_dir / "service.py").exists(), f"{domain_name} must expose service.py"
        if spec.mode == "simple":
            assert (domain_dir / "repo.py").exists(), f"{domain_name} simple mode must expose repo.py"
        elif spec.mode == "complex":
            assert (domain_dir / "queries.py").exists(), f"{domain_name} complex mode must expose queries.py"
            assert (domain_dir / "writers.py").exists(), f"{domain_name} complex mode must expose writers.py"
        else:
            raise AssertionError(f"unknown mode: {spec.mode}")


def test_services_py_remains_a_thin_facade():
    services_path = Path(__file__).resolve().parents[1] / "wecom_ability_service" / "services.py"
    source = services_path.read_text(encoding="utf-8")
    assert "Thin compatibility facade" in source
    assert "do not place new domain implementation here" in source
    forbidden_fragments = [
        "get_db(",
        ".execute(",
        "requests.",
        "import requests",
        "WeComClient.from_app(",
        "WeComClient.from_contact_app(",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in source, f"services.py must not contain {fragment}"


def test_services_wave1_symbols_route_through_application_wrappers():
    services_path = Path(__file__).resolve().parents[1] / "wecom_ability_service" / "services.py"
    source = services_path.read_text(encoding="utf-8")

    required_fragments = [
        "ListSignupConversionBatchesQuery",
        "GetSignupConversionBatchQuery",
        "ListOutboundWebhookDeliveriesQuery",
        "RetryOutboundWebhookDeliveryCommand",
        "RunDueOutboundWebhookRetriesCommand",
        "ApplyActivationWebhookCommand",
    ]
    for fragment in required_fragments:
        assert fragment in source, f"services.py must keep the Wave 1 application wrapper for {fragment}"

    forbidden_aliases = [
        "apply_activation_webhook = marketing_automation_domain_service.apply_activation_webhook",
        "list_outbound_webhook_deliveries = outbound_webhook_domain_service.list_outbound_webhook_deliveries",
        "list_signup_conversion_batches = marketing_automation_domain_service.list_signup_conversion_batches",
        "get_signup_conversion_batch = marketing_automation_domain_service.get_signup_conversion_batch",
        "retry_outbound_webhook_delivery = outbound_webhook_domain_service.retry_outbound_webhook_delivery",
        "run_due_outbound_webhook_retries = outbound_webhook_domain_service.run_due_outbound_webhook_retries",
    ]
    for fragment in forbidden_aliases:
        assert fragment not in source, f"services.py must not regress to direct domain alias: {fragment}"


def test_service_layer_layout_doc_exists():
    doc_path = Path(__file__).resolve().parents[1] / "docs" / "architecture" / "service_layer_layout.md"
    assert doc_path.exists()
    source = doc_path.read_text(encoding="utf-8")
    assert "Only two domain layout modes are allowed" in source
    assert "`wecom_ability_service/services.py` stays as a thin compatibility facade" in source
    assert "`admin_api_docs`" in source
    assert "http_route_consolidation_check.md" in source


def test_http_route_consolidation_check_doc_tracks_current_matrix():
    doc_path = Path(__file__).resolve().parents[1] / "docs" / "architecture" / "http_route_consolidation_check.md"
    assert doc_path.exists()
    source = doc_path.read_text(encoding="utf-8")

    required_fragments = [
        "Registry And Ownership",
        "Test Matrix",
        "Remaining Large Files",
        "tests/test_http_registration_contract.py",
        "tests/test_route_inventory_contract.py",
        "scripts/export_flask_routes.py",
        "admin_questionnaire_console.py",
    ]
    for fragment in required_fragments:
        assert fragment in source


def test_admin_api_docs_service_owns_docs_model_without_flask_dependencies():
    service_path = Path(__file__).resolve().parents[1] / "wecom_ability_service" / "domains" / "admin_api_docs" / "service.py"
    source = service_path.read_text(encoding="utf-8")

    assert "def build_api_docs_view_model" in source
    for forbidden in ("from flask", "import flask", "_render_admin_template", "url_for("):
        assert forbidden not in source


def test_user_ops_application_skeleton_and_runtime_adapter_are_importable(monkeypatch):
    from wecom_ability_service import services
    from wecom_ability_service.application.user_ops import (
        BackfillOwnerClassTermsCommand,
        GetUserOpsOverviewQuery,
        ImportActivationStatusCommand,
        ImportExperienceLeadsCommand,
        ImportMobileClassTermCommand,
        ListLeadPoolQuery,
        RefreshUserOpsContactTagsCommand,
        RunDueUserOpsDeferredJobsCommand,
        ScheduleUserOpsAutoAssignClassTermJobCommand,
        UpsertLeadPoolMemberCommand,
    )
    from wecom_ability_service.application.user_ops.commands import (
        BackfillClassTermForOwnerCommand,
        MigrateLegacyUserOpsPoolToLeadPoolCommand,
        RefreshContactTagsForExternalUseridCommand,
        UpsertUserOpsHuangxiaocanActivationSourceCommand,
    )
    from wecom_ability_service.infra import user_ops_runtime

    fake_client = object()

    monkeypatch.setattr(user_ops_runtime, "get_user_ops_contact_client", lambda: fake_client)
    monkeypatch.setattr(
        user_ops_runtime,
        "resolve_third_party_user_id_by_mobile",
        lambda mobile: f"tp-{mobile}",
    )

    assert GetUserOpsOverviewQuery
    assert ListLeadPoolQuery
    assert UpsertLeadPoolMemberCommand
    assert ScheduleUserOpsAutoAssignClassTermJobCommand
    assert RunDueUserOpsDeferredJobsCommand
    assert ImportExperienceLeadsCommand
    assert ImportMobileClassTermCommand
    assert ImportActivationStatusCommand
    assert BackfillOwnerClassTermsCommand
    assert BackfillClassTermForOwnerCommand
    assert RefreshUserOpsContactTagsCommand
    assert RefreshContactTagsForExternalUseridCommand
    assert UpsertUserOpsHuangxiaocanActivationSourceCommand
    assert MigrateLegacyUserOpsPoolToLeadPoolCommand
    assert services._user_ops_contact_client() is fake_client
    assert services._resolve_third_party_user_id_by_mobile("13800138000") == "tp-13800138000"


def test_services_user_ops_maintenance_symbols_route_through_application_wrappers():
    services_path = Path(__file__).resolve().parents[1] / "wecom_ability_service" / "services.py"
    source = services_path.read_text(encoding="utf-8")

    required_fragments = [
        "GetSidebarLeadPoolStatusQuery",
        "UpsertSidebarLeadPoolClassTermCommand",
        "RefreshContactTagsForExternalUseridCommand",
        "BackfillClassTermForOwnerCommand",
        "UpsertUserOpsHuangxiaocanActivationSourceCommand",
        "MigrateLegacyUserOpsPoolToLeadPoolCommand",
    ]
    for fragment in required_fragments:
        assert fragment in source, f"services.py must route user_ops maintenance symbol through {fragment}"

    forbidden_fragments = [
        "return user_ops_domain_service.get_sidebar_lead_pool_status(",
        "return user_ops_domain_service.upsert_sidebar_lead_pool_class_term(",
        "return user_ops_domain_service.refresh_contact_tags_for_external_userid(",
        "return user_ops_domain_service.backfill_class_term_for_owner(",
        "return user_ops_domain_service.upsert_user_ops_huangxiaocan_activation_source(",
        "return user_ops_domain_service.migrate_legacy_user_ops_pool_to_lead_pool(",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in source, f"services.py must not regress to direct user_ops domain call: {fragment}"

    assert "Internal primitive compatibility shim" in source


def test_admin_user_ops_and_admin_console_do_not_import_user_ops_legacy_service_symbols():
    target_symbols = {
        "get_user_ops_overview",
        "list_user_ops_pool",
        "list_user_ops_history",
        "export_user_ops_pool",
        "backfill_class_term_for_owner",
        "backfill_owner_class_terms_into_lead_pool",
        "import_experience_leads",
        "import_mobile_class_term_source",
        "import_activation_status_source",
        "migrate_legacy_user_ops_pool_to_lead_pool",
        "refresh_contact_tags_for_external_userid",
        "run_due_user_ops_deferred_jobs",
        "refresh_user_ops_contact_tags_for_owner",
        "upsert_user_ops_huangxiaocan_activation_source",
    }
    expected_application_fragments = {
        "wecom_ability_service/http/admin_user_ops.py": ["application.user_ops"],
        "wecom_ability_service/domains/admin_console/service.py": ["application.user_ops"],
    }

    root = Path(__file__).resolve().parents[1]
    for relative_path, required_fragments in expected_application_fragments.items():
        path = root / relative_path
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        imported_from_services: set[str] = set()
        imported_from_user_ops_domain = False

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = ("." * node.level + (node.module or "")).lstrip(".")
                if module == "services":
                    imported_from_services.update(alias.name for alias in node.names)
                if module == "domains.user_ops.service":
                    imported_from_user_ops_domain = True

        assert not (target_symbols & imported_from_services), (
            f"{relative_path} must use application.user_ops owner instead of services.py for "
            f"{sorted(target_symbols & imported_from_services)}"
        )
        assert not imported_from_user_ops_domain, (
            f"{relative_path} must not import domains.user_ops.service directly"
        )
        for fragment in required_fragments:
            assert fragment in source, f"{relative_path} must import the formal user_ops application owner"
