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
    notes: str = ""


# Service-layer layout contract:
# - simple: service.py + repo.py
# - complex: service.py + queries.py + writers.py, optional repo.py aggregator
# Optional domain-local companion modules such as definitions.py or
# preflight_service.py are allowed when they do not introduce a third pattern.
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
        persistence_modules=("repo.py",),
        notes="Admin console page-level read models, previews, and audited action wrappers.",
    ),
    "admin_config": DomainLayoutSpec(
        name="admin_config",
        mode="simple",
        service_module="service.py",
        persistence_modules=("repo.py",),
        notes="Admin configuration center read models, validation, persistence, and audit.",
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
        persistence_modules=("repo.py",),
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
        notes="Signup-conversion automation state, value segments, and pending-batch candidate filtering.",
    ),
    "outbound_webhook": DomainLayoutSpec(
        name="outbound_webhook",
        mode="simple",
        service_module="service.py",
        persistence_modules=("repo.py",),
        notes="Outbound webhook delivery records, retries, and admin audit reads.",
    ),
    "questionnaire": DomainLayoutSpec(
        name="questionnaire",
        mode="simple",
        service_module="service.py",
        persistence_modules=("repo.py",),
        notes="Questionnaire definition, submission, export; preflight stays domain-local.",
    ),
    "routing_config": DomainLayoutSpec(
        name="routing_config",
        mode="simple",
        service_module="service.py",
        persistence_modules=("repo.py",),
        notes="Owner role map, routing config, domain-local definitions.py rules.",
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
