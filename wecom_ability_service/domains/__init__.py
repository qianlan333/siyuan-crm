from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DomainLayoutMode = Literal["simple", "complex"]


@dataclass(frozen=True)
class DomainLayoutSpec:
    name: str
    mode: DomainLayoutMode
    service_module: str
    persistence_modules: tuple[str, ...]
    companion_service_modules: tuple[str, ...] = ()
    allowed_companion_modules: tuple[str, ...] = ()
    notes: str = ""


# Service-layer layout contract:
# - simple: service.py + declared persistence modules
# - complex: service.py + queries.py + writers.py, optional repo.py aggregator
# Domain-local companion services/repos must be explicitly declared here.
DOMAIN_LAYOUTS: dict[str, DomainLayoutSpec] = {
    "admin_jobs": DomainLayoutSpec(
        name="admin_jobs",
        mode="simple",
        service_module="service.py",
        persistence_modules=("repo.py",),
        notes="Sync runs, callback runtime, message batches, and deferred jobs console aggregates.",
    ),
    "admin_audit": DomainLayoutSpec(
        name="admin_audit",
        mode="simple",
        service_module="service.py",
        persistence_modules=("repo.py",),
        notes="Admin audit query, governance policies, and legacy-path compatibility decisions.",
    ),
    "admin_console": DomainLayoutSpec(
        name="admin_console",
        mode="simple",
        service_module="service.py",
        persistence_modules=("repo.py", "customer_profile_repo.py"),
        companion_service_modules=("customer_profile_service.py",),
        notes="Admin console page-level read models, previews, and audited action wrappers.",
    ),
    "admin_config": DomainLayoutSpec(
        name="admin_config",
        mode="simple",
        service_module="service.py",
        persistence_modules=("repo.py",),
        notes="Admin configuration center read models, validation, persistence, and audit.",
    ),
    "admin_api_docs": DomainLayoutSpec(
        name="admin_api_docs",
        mode="simple",
        service_module="service.py",
        persistence_modules=("repo.py",),
        notes="Static API documentation metadata, quick reference, and Markdown export view model.",
    ),
    "admin_dashboard": DomainLayoutSpec(
        name="admin_dashboard",
        mode="simple",
        service_module="service.py",
        persistence_modules=("repo.py",),
        notes="Admin shell navigation, environment badges, and dashboard status cards.",
    ),
    "archive": DomainLayoutSpec(
        name="archive",
        mode="simple",
        service_module="service.py",
        persistence_modules=("repo.py",),
        notes="Archived messages, sync runs, and message batches.",
    ),
    "automation_conversion": DomainLayoutSpec(
        name="automation_conversion",
        mode="simple",
        service_module="service.py",
        persistence_modules=("repo.py", "program_repo.py", "workflow_repo.py", "operation_task_repo.py"),
        companion_service_modules=(
            "action_template_service.py",
            "channel_service.py",
            "copy_workorder_service.py",
            "customer_acquisition_service.py",
            "due_jobs_service.py",
            "focus_send_service.py",
            "interaction_stats_service.py",
            "laohuang_chat_service.py",
            "manual_send_service.py",
            "member_segment_search_service.py",
            "member_state_service.py",
            "message_activity_service.py",
            "model_infra_service.py",
            "operation_task_service.py",
            "orchestration_service.py",
            "program_service.py",
            "program_setup_service.py",
            "reply_monitor_service.py",
            "router_dispatch_service.py",
            "signup_conversion_service.py",
            "sop_service.py",
            "workflow_execution_service.py",
            "workflow_runtime_service.py",
            "workflow_service.py",
        ),
        notes="Automation conversion settings, member pool transitions, and provider-backed QR generation.",
    ),
    "automation_state": DomainLayoutSpec(
        name="automation_state",
        mode="simple",
        service_module="service.py",
        persistence_modules=("repo.py",),
        notes="Shared automation state constants and pure helpers; repo.py remains an empty contract placeholder.",
    ),
    "callbacks": DomainLayoutSpec(
        name="callbacks",
        mode="simple",
        service_module="service.py",
        persistence_modules=("repo.py",),
        notes="External contact callback business orchestration and event logs.",
    ),
    "class_user": DomainLayoutSpec(
        name="class_user",
        mode="simple",
        service_module="service.py",
        persistence_modules=("repo.py",),
        notes="Signup status state machine and class-user history.",
    ),
    "contacts": DomainLayoutSpec(
        name="contacts",
        mode="simple",
        service_module="service.py",
        persistence_modules=("repo.py",),
        notes="Contact snapshot, description sync, and WeCom contact reads.",
    ),
    "group_chats": DomainLayoutSpec(
        name="group_chats",
        mode="simple",
        service_module="service.py",
        persistence_modules=("repo.py",),
        notes="Group chat snapshot and persistence.",
    ),
    "identity": DomainLayoutSpec(
        name="identity",
        mode="simple",
        service_module="service.py",
        persistence_modules=("repo.py",),
        notes="People, bindings, external contact identity map, resolve flow.",
    ),
    "marketing_automation": DomainLayoutSpec(
        name="marketing_automation",
        mode="simple",
        service_module="service.py",
        persistence_modules=("repo.py",),
        companion_service_modules=(
            "enrollment_service.py",
            "frequency_budget_service.py",
            "message_dispatch_service.py",
            "router_dispatch_service.py",
            "value_segment_service.py",
        ),
        notes="Signup-conversion automation state, value segments, and pending-batch candidate filtering.",
    ),
    "outbound_webhook": DomainLayoutSpec(
        name="outbound_webhook",
        mode="simple",
        service_module="service.py",
        persistence_modules=("repo.py",),
        companion_service_modules=("message_dispatch_service.py",),
        notes="Outbound webhook delivery records, retries, and admin audit reads.",
    ),
    "questionnaire": DomainLayoutSpec(
        name="questionnaire",
        mode="simple",
        service_module="service.py",
        persistence_modules=("repo.py",),
        companion_service_modules=("preflight_service.py",),
        notes="Questionnaire definition, submission, export; preflight stays domain-local.",
    ),
    "wechat_pay": DomainLayoutSpec(
        name="wechat_pay",
        mode="simple",
        service_module="service.py",
        companion_service_modules=("product_service.py", "admin_service.py"),
        persistence_modules=("repo.py", "product_repo.py"),
        allowed_companion_modules=("exceptions.py", "client.py"),
        notes=(
            "WeChat Pay H5/JSAPI checkout, product management, transaction admin, refunds, "
            "and payment notification handling; admin_service.py owns admin transaction read models."
        ),
    ),
    "routing_config": DomainLayoutSpec(
        name="routing_config",
        mode="simple",
        service_module="service.py",
        persistence_modules=("repo.py",),
        notes="Owner role map, routing config, domain-local definitions.py rules.",
    ),
    "sidebar_v2": DomainLayoutSpec(
        name="sidebar_v2",
        mode="simple",
        service_module="service.py",
        persistence_modules=("repo.py",),
        notes="WeCom customer sidebar V2 workbench read and write adapters.",
    ),
    "tags": DomainLayoutSpec(
        name="tags",
        mode="simple",
        service_module="service.py",
        persistence_modules=("repo.py",),
        notes="Tag snapshot, signup tag rules, live tag refresh helpers.",
    ),
    "tasks": DomainLayoutSpec(
        name="tasks",
        mode="simple",
        service_module="service.py",
        persistence_modules=("repo.py",),
        notes="Outbound task dispatch and feedback persistence.",
    ),
    "user_ops": DomainLayoutSpec(
        name="user_ops",
        mode="simple",
        service_module="service.py",
        persistence_modules=("repo.py",),
        companion_service_modules=(
            "hxc_dashboard_snapshot_service.py",
            "hxc_dashboard_view_service.py",
            "hxc_send_config_service.py",
            "page_service.py",
            "user_ops_class_term_service.py",
            "user_ops_deferred_job_service.py",
            "user_ops_import_service.py",
            "user_ops_pool_core_service.py",
            "user_ops_sidebar_service.py",
            "user_ops_tag_refresh_service.py",
        ),
        notes="Lead pool, import, activation, deferred jobs, class-term mapping.",
    ),
}

SIMPLE_DOMAIN_NAMES = tuple(sorted(name for name, spec in DOMAIN_LAYOUTS.items() if spec.mode == "simple"))
COMPLEX_DOMAIN_NAMES = tuple(sorted(name for name, spec in DOMAIN_LAYOUTS.items() if spec.mode == "complex"))

__all__ = [
    "COMPLEX_DOMAIN_NAMES",
    "DOMAIN_LAYOUTS",
    "DomainLayoutMode",
    "DomainLayoutSpec",
    "SIMPLE_DOMAIN_NAMES",
]
