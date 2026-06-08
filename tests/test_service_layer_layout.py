from __future__ import annotations

import ast
from pathlib import Path

from wecom_ability_service.domains import DOMAIN_LAYOUTS


# Domains that exist as directories but don't yet follow the standard
# service.py / repo.py layout convention. Excluded from both registry-match
# and file-mode checks until they are fleshed out.
_STUB_DOMAINS = {"image_library", "miniprogram_library", "attachment_library", "media_library", "campaigns", "cloud_orchestrator", "segments", "admin_auth", "broadcast_jobs"}


def test_domain_layout_registry_matches_domain_directories():
    domains_dir = Path(__file__).resolve().parents[1] / "wecom_ability_service" / "domains"
    actual = {
        path.name
        for path in domains_dir.iterdir()
        if path.is_dir() and not path.name.startswith("__")
    }
    assert set(DOMAIN_LAYOUTS.keys()) | _STUB_DOMAINS == actual | _STUB_DOMAINS


def test_domain_layout_registry_source_has_no_duplicate_domain_keys():
    registry_path = Path(__file__).resolve().parents[1] / "wecom_ability_service" / "domains" / "__init__.py"
    tree = ast.parse(registry_path.read_text(encoding="utf-8"))
    assignments = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "DOMAIN_LAYOUTS"
        and isinstance(node.value, ast.Dict)
    ]
    assert len(assignments) == 1
    keys = [
        key.value
        for key in assignments[0].value.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    ]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    assert duplicates == []


def test_domain_layout_files_match_declared_mode():
    domains_dir = Path(__file__).resolve().parents[1] / "wecom_ability_service" / "domains"
    for domain_name, spec in DOMAIN_LAYOUTS.items():
        domain_dir = domains_dir / domain_name
        assert (domain_dir / spec.service_module).exists(), f"{domain_name} must expose {spec.service_module}"
        for module_name in spec.companion_service_modules:
            assert (domain_dir / module_name).exists(), f"{domain_name} must declare an existing companion service {module_name}"
        for module_name in spec.persistence_modules:
            assert (domain_dir / module_name).exists(), f"{domain_name} must declare an existing persistence module {module_name}"
        if spec.mode == "simple":
            assert spec.persistence_modules, f"{domain_name} simple mode must declare persistence modules"
        elif spec.mode == "complex":
            assert (domain_dir / "queries.py").exists(), f"{domain_name} complex mode must expose queries.py"
            assert (domain_dir / "writers.py").exists(), f"{domain_name} complex mode must expose writers.py"
        else:
            raise AssertionError(f"unknown mode: {spec.mode}")


def test_split_domain_companion_modules_are_declared():
    domains_dir = Path(__file__).resolve().parents[1] / "wecom_ability_service" / "domains"
    for domain_name, spec in DOMAIN_LAYOUTS.items():
        domain_dir = domains_dir / domain_name
        declared = {
            spec.service_module,
            *spec.companion_service_modules,
            *spec.persistence_modules,
            *spec.allowed_companion_modules,
        }
        for path in domain_dir.glob("*.py"):
            if path.name == "__init__.py":
                continue
            requires_declaration = (
                path.name == "admin_service.py"
                or path.name == "product_repo.py"
                or path.name.endswith("_service.py")
                or path.name.endswith("_repo.py")
            )
            if requires_declaration:
                assert path.name in declared, f"{domain_name}/{path.name} must be declared in DOMAIN_LAYOUTS"


def test_wechat_pay_contract_declares_split_product_modules():
    spec = DOMAIN_LAYOUTS["wechat_pay"]

    assert spec.service_module == "service.py"
    assert {"product_service.py", "admin_service.py"}.issubset(spec.companion_service_modules)
    assert {"repo.py", "product_repo.py"}.issubset(spec.persistence_modules)
    assert {"exceptions.py", "client.py"}.issubset(spec.allowed_companion_modules)


def test_wechat_pay_product_service_does_not_import_automation_repos_directly():
    source_path = (
        Path(__file__).resolve().parents[1]
        / "wecom_ability_service"
        / "domains"
        / "wechat_pay"
        / "product_service.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    forbidden = {
        ("wecom_ability_service.domains.automation_conversion", "repo"),
        ("wecom_ability_service.domains.automation_conversion", "program_repo"),
        ("..automation_conversion", "repo"),
        ("..automation_conversion", "program_repo"),
    }
    imports: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            for alias in node.names:
                imports.append((module, alias.name))
    assert sorted(set(imports) & forbidden) == []


def test_wechat_pay_order_repo_does_not_reexport_product_repo_functions():
    source_path = (
        Path(__file__).resolve().parents[1]
        / "wecom_ability_service"
        / "domains"
        / "wechat_pay"
        / "repo.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    forbidden_names = {
        "add_product_slice",
        "count_orders_for_product_code",
        "delete_product",
        "delete_product_slice",
        "get_product_by_code",
        "get_product_by_id",
        "insert_product",
        "list_active_db_products",
        "list_admin_products",
        "list_product_slices",
        "replace_product_slices",
        "reorder_product_slices",
        "update_product",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("product_repo"):
            imported = {alias.name for alias in node.names}
            assert sorted(imported & forbidden_names) == []


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
    expected_application_fragments = {"wecom_ability_service/domains/admin_console/service.py": []}

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
        if not required_fragments:
            assert "application.user_ops" not in source, f"{relative_path} must not keep retired user_ops page imports"
        for fragment in required_fragments:
            assert fragment in source, f"{relative_path} must import the formal user_ops application owner"
