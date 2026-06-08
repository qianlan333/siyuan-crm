from __future__ import annotations

import os
from copy import deepcopy
from typing import Any, Protocol

from aicrm_next.shared.db_session import get_engine
from aicrm_next.shared.errors import ContractError, NotFoundError
from aicrm_next.shared.repository_provider import assert_repository_allowed
from aicrm_next.shared.runtime import production_data_ready, raw_database_url

from .agent_outputs import agent_output_projection, normalize_agent_output_filters
from .agent_runs import agent_run_projection, normalize_agent_run_filters
from .agents import AGENT_ROUTE_FAMILY, agent_projection, agent_side_effect_safety, normalize_agent_create_payload
from .domain import member_matches_filters
from .profile_segments import normalize_profile_segment_template_payload, profile_segment_template_projection
from .state_machine import POOL_DEFINITIONS, project_member, utc_now_iso
from .task_groups import TASK_GROUP_ROUTE_FAMILY, normalize_task_group_create_payload, task_group_projection, task_group_side_effect_safety
from .tasks import TASK_ROUTE_FAMILY, normalize_task_create_payload, task_projection, task_side_effect_safety
from .workflow_nodes import (
    WORKFLOW_NODE_ROUTE_FAMILY,
    normalize_workflow_node_create_payload,
    normalize_workflow_node_update_payload,
    workflow_node_projection,
    workflow_node_side_effect_safety,
)
from .workflows import WORKFLOW_ROUTE_FAMILY, normalize_workflow_create_payload, workflow_projection, workflow_side_effect_safety

TASK_GROUP_BACKEND_ENV = "AICRM_TASK_GROUPS_REPO_BACKEND"
TASK_GROUP_TEST_DATABASE_URL_ENV = "AICRM_TASK_GROUPS_TEST_DATABASE_URL"
TASK_GROUP_STAGING_DATABASE_URL_ENV = "AICRM_TASK_GROUPS_STAGING_DATABASE_URL"
TASK_GROUP_SQL_BACKENDS = {"sql", "sqlalchemy", "postgres", "postgresql"}
WORKFLOW_BACKEND_ENV = "AICRM_WORKFLOWS_REPO_BACKEND"
WORKFLOW_TEST_DATABASE_URL_ENV = "AICRM_WORKFLOWS_TEST_DATABASE_URL"
WORKFLOW_STAGING_DATABASE_URL_ENV = "AICRM_WORKFLOWS_STAGING_DATABASE_URL"
WORKFLOW_SQL_BACKENDS = {"sql", "sqlalchemy", "postgres", "postgresql"}
WORKFLOW_NODE_BACKEND_ENV = "AICRM_WORKFLOW_NODES_REPO_BACKEND"
WORKFLOW_NODE_TEST_DATABASE_URL_ENV = "AICRM_WORKFLOW_NODES_TEST_DATABASE_URL"
WORKFLOW_NODE_STAGING_DATABASE_URL_ENV = "AICRM_WORKFLOW_NODES_STAGING_DATABASE_URL"
WORKFLOW_NODE_SQL_BACKENDS = {"sql", "sqlalchemy", "postgres", "postgresql"}
TASK_BACKEND_ENV = "AICRM_TASKS_REPO_BACKEND"
TASK_TEST_DATABASE_URL_ENV = "AICRM_TASKS_TEST_DATABASE_URL"
TASK_STAGING_DATABASE_URL_ENV = "AICRM_TASKS_STAGING_DATABASE_URL"
TASK_SQL_BACKENDS = {"sql", "sqlalchemy", "postgres", "postgresql"}
AGENT_BACKEND_ENV = "AICRM_AGENTS_REPO_BACKEND"
AGENT_TEST_DATABASE_URL_ENV = "AICRM_AGENTS_TEST_DATABASE_URL"
AGENT_STAGING_DATABASE_URL_ENV = "AICRM_AGENTS_STAGING_DATABASE_URL"
AGENT_SQL_BACKENDS = {"sql", "sqlalchemy", "postgres", "postgresql"}
AGENT_OUTPUT_BACKEND_ENV = "AICRM_AGENT_OUTPUTS_REPO_BACKEND"
AGENT_OUTPUT_TEST_DATABASE_URL_ENV = "AICRM_AGENT_OUTPUTS_TEST_DATABASE_URL"
AGENT_OUTPUT_STAGING_DATABASE_URL_ENV = "AICRM_AGENT_OUTPUTS_STAGING_DATABASE_URL"
AGENT_OUTPUT_SQL_BACKENDS = {"sql", "sqlalchemy", "postgres", "postgresql"}
AGENT_RUN_BACKEND_ENV = "AICRM_AGENT_RUNS_REPO_BACKEND"
AGENT_RUN_TEST_DATABASE_URL_ENV = "AICRM_AGENT_RUNS_TEST_DATABASE_URL"
AGENT_RUN_STAGING_DATABASE_URL_ENV = "AICRM_AGENT_RUNS_STAGING_DATABASE_URL"
AGENT_RUN_SQL_BACKENDS = {"sql", "sqlalchemy", "postgres", "postgresql"}

DEFAULT_AGENT_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {"agent_code": "central_router_agent", "agent_name": "中央路由 Agent", "agent_type": "classifier", "sort_order": 10},
    {"agent_code": "welcome_agent", "agent_name": "欢迎接待 Agent", "agent_type": "assistant", "sort_order": 20},
    {"agent_code": "pricing_agent", "agent_name": "价格答疑 Agent", "agent_type": "assistant", "sort_order": 30},
    {"agent_code": "proof_agent", "agent_name": "案例证明 Agent", "agent_type": "assistant", "sort_order": 40},
    {"agent_code": "closing_agent", "agent_name": "成交推进 Agent", "agent_type": "followup", "sort_order": 50},
)


def _sqlalchemy_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


class AutomationRepository(Protocol):
    def list_pools(self) -> list[dict[str, Any]]: ...
    def list_members(self, filters: dict[str, Any] | None = None, *, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]: ...
    def get_member(self, member_id: str) -> dict[str, Any] | None: ...
    def find_member(self, *, external_userid: str | None = None, mobile: str | None = None, person_id: str | None = None) -> dict[str, Any] | None: ...
    def save_member(self, member: dict[str, Any]) -> dict[str, Any]: ...
    def append_history(self, member_id: str, event: dict[str, Any]) -> None: ...
    def list_history(self, member_id: str) -> list[dict[str, Any]]: ...
    def create_execution_record(self, record: dict[str, Any]) -> dict[str, Any]: ...
    def list_execution_records(self, *, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]: ...
    def profile_segment_template_catalog(self) -> dict[str, Any]: ...
    def list_profile_segment_templates(
        self,
        *,
        enabled_only: bool = False,
        program_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]: ...
    def get_profile_segment_template(self, template_id: int) -> dict[str, Any] | None: ...
    def create_profile_segment_template(self, payload: dict[str, Any], *, idempotency_key: str, operator: str) -> dict[str, Any]: ...
    def update_profile_segment_template(self, template_id: int, payload: dict[str, Any], *, operator: str) -> dict[str, Any]: ...
    def list_profile_segment_template_audit_events(self) -> list[dict[str, Any]]: ...
    def list_task_groups(self, filters: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], int]: ...
    def create_task_group(self, payload: dict[str, Any], *, idempotency_key: str, operator: str) -> dict[str, Any]: ...
    def list_task_group_audit_events(self) -> list[dict[str, Any]]: ...
    def list_workflows(self, filters: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], int]: ...
    def create_workflow(self, payload: dict[str, Any], *, idempotency_key: str, operator: str) -> dict[str, Any]: ...
    def list_workflow_audit_events(self) -> list[dict[str, Any]]: ...
    def list_workflow_nodes(self, filters: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], int]: ...
    def get_workflow_node(self, node_id: int) -> dict[str, Any] | None: ...
    def create_workflow_node(self, payload: dict[str, Any], *, idempotency_key: str, operator: str) -> dict[str, Any]: ...
    def update_workflow_node(self, node_id: int, payload: dict[str, Any], *, operator: str) -> dict[str, Any]: ...
    def delete_workflow_node(self, node_id: int, *, operator: str) -> dict[str, Any]: ...
    def list_workflow_node_audit_events(self) -> list[dict[str, Any]]: ...
    def list_tasks(self, filters: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], int]: ...
    def get_task(self, task_id: int) -> dict[str, Any] | None: ...
    def create_task(self, payload: dict[str, Any], *, idempotency_key: str, operator: str) -> dict[str, Any]: ...
    def update_task(self, task_id: int, payload: dict[str, Any], *, operator: str) -> dict[str, Any]: ...
    def list_task_audit_events(self) -> list[dict[str, Any]]: ...
    def list_agents(self, filters: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], int]: ...
    def create_agent(self, payload: dict[str, Any], *, idempotency_key: str, operator: str) -> dict[str, Any]: ...
    def list_agent_audit_events(self) -> list[dict[str, Any]]: ...
    def list_agent_outputs(self, filters: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], int, dict[str, Any]]: ...
    def get_agent_output(self, output_id: str, filters: dict[str, Any] | None = None) -> dict[str, Any] | None: ...
    def list_agent_runs(self, filters: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], int, dict[str, Any]]: ...
    def get_agent_run(self, run_id: str, filters: dict[str, Any] | None = None) -> dict[str, Any] | None: ...


def _fixture_members() -> list[dict[str, Any]]:
    return [
        {
            "member_id": "member_001",
            "person_id": "person_001",
            "external_userid": "wx_ext_001",
            "mobile": "13800138000",
            "customer_name": "黄小璨学员 A",
            "owner_userid": "owner_001",
            "current_pool": "new_user",
            "followup_type": "normal",
            "questionnaire_followup_type": "normal",
            "manual_followup_type": "",
            "trial_opened": False,
            "activated": False,
            "converted": False,
            "exited": False,
            "silent": False,
            "latest_event_at": "2026-05-20T09:00:00Z",
            "history": [],
            "warnings": [],
        },
        {
            "member_id": "member_002",
            "person_id": "person_002",
            "external_userid": "wx_ext_002",
            "mobile": "13800138001",
            "customer_name": "黄小璨学员 B",
            "owner_userid": "owner_002",
            "current_pool": "unactivated_priority",
            "followup_type": "priority",
            "questionnaire_followup_type": "priority",
            "manual_followup_type": "",
            "trial_opened": True,
            "activated": False,
            "converted": False,
            "exited": False,
            "silent": False,
            "latest_event_at": "2026-05-20T09:30:00Z",
            "history": [
                {
                    "event_id": "hist_member_002_1",
                    "member_id": "member_002",
                    "before_pool": "new_user",
                    "after_pool": "unactivated_priority",
                    "trigger": "trial_opened",
                    "source": "fixture",
                    "operator": "system",
                    "reason": "fixture_seed",
                    "occurred_at": "2026-05-20T09:30:00Z",
                }
            ],
            "warnings": [],
        },
        {
            "member_id": "member_003",
            "person_id": "person_003",
            "external_userid": "wx_ext_003",
            "mobile": "13800138002",
            "customer_name": "黄小璨学员 C",
            "owner_userid": "",
            "current_pool": "silent",
            "followup_type": "normal",
            "questionnaire_followup_type": "normal",
            "manual_followup_type": "",
            "trial_opened": True,
            "activated": True,
            "converted": False,
            "exited": False,
            "silent": True,
            "latest_event_at": "2026-05-20T10:00:00Z",
            "history": [],
            "warnings": ["fixture_missing_owner"],
        },
    ]


class InMemoryAutomationRepository:
    def __init__(self, members: list[dict[str, Any]] | None = None) -> None:
        self._members = {item["member_id"]: deepcopy(item) for item in (members or _fixture_members())}
        self._execution_records: list[dict[str, Any]] = [
            {
                "id": "exec_001",
                "record_type": "state_transition",
                "member_id": "member_002",
                "trigger": "trial_opened",
                "status": "succeeded",
                "status_label": "已记录",
                "delivery_status": "fixture",
                "payload_preview": {"after_pool": "unactivated_priority"},
                "created_at": "2026-05-20T09:30:00Z",
            }
        ]
        self._profile_segment_templates: dict[int, dict[str, Any]] = {
            1: profile_segment_template_projection(
                {
                    "id": 1,
                    "name": "高意向用户画像模板",
                    "description": "Fixture local contract profile segment template.",
                    "code": "high_intent",
                    "conditions": {"source": "fixture"},
                    "rules": [{"field": "intent", "operator": "eq", "value": "high"}],
                    "status": "draft",
                    "sort_order": 10,
                    "created_at": "2026-05-20T09:00:00Z",
                    "updated_at": "2026-05-20T09:00:00Z",
                }
            )
        }
        self._profile_segment_idempotency: dict[str, dict[str, Any]] = {}
        self._profile_segment_audit_events: list[dict[str, Any]] = []
        self._task_groups: dict[int, dict[str, Any]] = {
            1: task_group_projection(
                {
                    "id": 1,
                    "program_id": 1,
                    "group_code": "phase4ap_default_group",
                    "group_name": "Fixture 默认任务组",
                    "sort_order": 10,
                    "metadata": {"source": "fixture"},
                    "created_by": "fixture",
                    "updated_by": "fixture",
                    "created_at": "2026-05-20T09:00:00Z",
                    "updated_at": "2026-05-20T09:00:00Z",
                }
            ),
            2: task_group_projection(
                {
                    "id": 2,
                    "program_id": 1,
                    "group_code": "phase4ap_followup_group",
                    "group_name": "Fixture 跟进任务组",
                    "sort_order": 20,
                    "metadata": {"source": "fixture"},
                    "created_by": "fixture",
                    "updated_by": "fixture",
                    "created_at": "2026-05-20T09:05:00Z",
                    "updated_at": "2026-05-20T09:05:00Z",
                }
            ),
        }
        self._task_group_idempotency: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        self._task_group_audit_events: list[dict[str, Any]] = []
        self._workflows: dict[int, dict[str, Any]] = {
            1: workflow_projection(
                {
                    "id": 1,
                    "program_id": 1,
                    "workflow_code": "phase4at_default_workflow",
                    "workflow_name": "Fixture 默认工作流",
                    "description": "Fixture local workflow metadata.",
                    "status": "draft",
                    "segmentation_basis": {"source": "fixture"},
                    "profile_segment_template_id": 1,
                    "behavior_tier_scheme": {"tier": "standard"},
                    "fallback_to_standard_content": True,
                    "created_by": "fixture",
                    "updated_by": "fixture",
                    "created_at": "2026-05-20T09:10:00Z",
                    "updated_at": "2026-05-20T09:10:00Z",
                }
            ),
            2: workflow_projection(
                {
                    "id": 2,
                    "program_id": 1,
                    "workflow_code": "phase4at_followup_workflow",
                    "workflow_name": "Fixture 跟进工作流",
                    "description": "Fixture local follow-up workflow metadata.",
                    "status": "inactive",
                    "segmentation_basis": {"source": "fixture"},
                    "profile_segment_template_id": 1,
                    "behavior_tier_scheme": {"tier": "followup"},
                    "fallback_to_standard_content": True,
                    "created_by": "fixture",
                    "updated_by": "fixture",
                    "created_at": "2026-05-20T09:15:00Z",
                    "updated_at": "2026-05-20T09:15:00Z",
                }
            ),
        }
        self._workflow_idempotency: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        self._workflow_audit_events: list[dict[str, Any]] = []
        self._workflow_nodes: dict[int, dict[str, Any]] = {
            1: workflow_node_projection(
                {
                    "id": 1,
                    "program_id": 1,
                    "workflow_id": 1,
                    "node_code": "phase4ax_entry_node",
                    "node_name": "Fixture 入口节点",
                    "node_type": "manual",
                    "status": "draft",
                    "sort_order": 10,
                    "position": {"x": 120, "y": 80},
                    "metadata": {"source": "fixture"},
                    "config": {"description": "metadata only"},
                    "created_by": "fixture",
                    "updated_by": "fixture",
                    "created_at": "2026-05-20T09:20:00Z",
                    "updated_at": "2026-05-20T09:20:00Z",
                }
            ),
            2: workflow_node_projection(
                {
                    "id": 2,
                    "program_id": 1,
                    "workflow_id": 1,
                    "node_code": "phase4ax_followup_node",
                    "node_name": "Fixture 跟进节点",
                    "node_type": "metadata",
                    "status": "inactive",
                    "sort_order": 20,
                    "position": {"x": 320, "y": 80},
                    "metadata": {"source": "fixture"},
                    "config": {"description": "metadata only"},
                    "created_by": "fixture",
                    "updated_by": "fixture",
                    "created_at": "2026-05-20T09:25:00Z",
                    "updated_at": "2026-05-20T09:25:00Z",
                }
            ),
        }
        self._workflow_node_idempotency: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        self._workflow_node_audit_events: list[dict[str, Any]] = []
        self._tasks: dict[int, dict[str, Any]] = {
            1: task_projection(
                {
                    "id": 1,
                    "program_id": 1,
                    "workflow_id": 1,
                    "node_id": 1,
                    "group_id": 1,
                    "task_code": "phase4bc_followup_task",
                    "task_name": "Fixture 跟进任务",
                    "task_type": "followup",
                    "status": "draft",
                    "sort_order": 10,
                    "metadata": {"source": "fixture"},
                    "config": {"description": "metadata only"},
                    "created_by": "fixture",
                    "updated_by": "fixture",
                    "created_at": "2026-05-20T09:30:00Z",
                    "updated_at": "2026-05-20T09:30:00Z",
                }
            ),
            2: task_projection(
                {
                    "id": 2,
                    "program_id": 1,
                    "workflow_id": 1,
                    "node_id": 2,
                    "group_id": 1,
                    "task_code": "phase4bc_review_task",
                    "task_name": "Fixture 审阅任务",
                    "task_type": "review",
                    "status": "inactive",
                    "sort_order": 20,
                    "metadata": {"source": "fixture"},
                    "config": {"description": "metadata only"},
                    "created_by": "fixture",
                    "updated_by": "fixture",
                    "created_at": "2026-05-20T09:35:00Z",
                    "updated_at": "2026-05-20T09:35:00Z",
                }
            ),
        }
        self._task_idempotency: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        self._task_audit_events: list[dict[str, Any]] = []
        self._agents: dict[int, dict[str, Any]] = {
            index: agent_projection(
                {
                    "id": index,
                    "program_id": 0,
                    "workflow_id": 0,
                    "node_id": 0,
                    "task_id": 0,
                    "status": "active",
                    "metadata": {"source": "next_default_fixture"},
                    "config": {"description": "metadata only"},
                    "enabled": True,
                    "created_by": "fixture",
                    "updated_by": "fixture",
                    "created_at": "2026-05-20T09:40:00Z",
                    "updated_at": "2026-05-20T09:40:00Z",
                    **definition,
                }
            )
            for index, definition in enumerate(DEFAULT_AGENT_DEFINITIONS, start=1)
        }
        self._agent_idempotency: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        self._agent_audit_events: list[dict[str, Any]] = []
        self._agent_outputs: dict[str, dict[str, Any]] = {
            "phase4bk_output_reply_draft": {
                "id": "phase4bk_output_reply_draft",
                "output_id": "phase4bk_output_reply_draft",
                "run_id": "phase4bo_run_draft",
                "request_id": "req_phase4bk_reply",
                "userid": "user_phase4_fixture",
                "external_contact_id": "wm_external_001",
                "agent_code": "phase4bg_review_agent",
                "output_type": "reply_draft",
                "rendered_output_text": "Fixture reply draft for console review only.",
                "target_agent_code": "phase4bg_review_agent",
                "target_pool": "unactivated_priority",
                "confidence": 0.82,
                "reason": "Fixture metadata output; no LLM or live delivery executed.",
                "need_human_review": True,
                "applied_status": "pending_review",
                "error_code": "",
                "error_message": "",
                "created_at": "2026-05-20T09:50:00Z",
            },
            "phase4bk_output_route_decision": {
                "id": "phase4bk_output_route_decision",
                "output_id": "phase4bk_output_route_decision",
                "run_id": "phase4bo_run_route",
                "request_id": "req_phase4bk_route",
                "userid": "user_phase4_fixture",
                "external_contact_id": "wm_external_002",
                "agent_code": "phase4bg_followup_agent",
                "output_type": "route_decision",
                "rendered_output_text": "Fixture route decision metadata for audit-only review.",
                "target_agent_code": "phase4bg_followup_agent",
                "target_pool": "silent",
                "confidence": 0.74,
                "reason": "Fixture local route metadata; no workflow, task, or agent-run execution.",
                "need_human_review": False,
                "applied_status": "draft",
                "error_code": "",
                "error_message": "",
                "created_at": "2026-05-20T09:55:00Z",
            },
        }
        self._agent_runs: dict[str, dict[str, Any]] = {
            "phase4bo_run_completed_metadata": {
                "id": "phase4bo_run_completed_metadata",
                "run_id": "phase4bo_run_completed_metadata",
                "request_id": "req_phase4bo_completed",
                "agent_code": "phase4bg_review_agent",
                "run_status": "completed",
                "trigger_source": "fixture",
                "external_contact_id": "wm_external_001",
                "userid": "user_phase4_fixture",
                "task_id": 1,
                "workflow_id": 1,
                "started_at": "2026-05-20T09:48:00Z",
                "finished_at": "2026-05-20T09:49:00Z",
                "duration_ms": 60000,
                "error_code": "",
                "error_message": "",
                "output_count": 1,
                "metadata": {"source": "fixture", "runtime_enabled": False},
                "created_at": "2026-05-20T09:48:00Z",
                "updated_at": "2026-05-20T09:49:00Z",
            },
            "phase4bo_run_failed_metadata": {
                "id": "phase4bo_run_failed_metadata",
                "run_id": "phase4bo_run_failed_metadata",
                "request_id": "req_phase4bo_failed",
                "agent_code": "phase4bg_followup_agent",
                "run_status": "failed",
                "trigger_source": "fixture",
                "external_contact_id": "wm_external_002",
                "userid": "user_phase4_fixture",
                "task_id": 2,
                "workflow_id": 1,
                "started_at": "2026-05-20T09:52:00Z",
                "finished_at": "2026-05-20T09:52:30Z",
                "duration_ms": 30000,
                "error_code": "fixture_agent_run_failed",
                "error_message": "Fixture local metadata failure; no live runtime path was invoked.",
                "output_count": 0,
                "metadata": {"source": "fixture", "runtime_enabled": False},
                "created_at": "2026-05-20T09:52:00Z",
                "updated_at": "2026-05-20T09:52:30Z",
            },
        }

    def list_pools(self) -> list[dict[str, Any]]:
        return deepcopy(POOL_DEFINITIONS)

    def list_members(self, filters: dict[str, Any] | None = None, *, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        rows = [project_member(member) for member in self._members.values()]
        filters = filters or {}
        rows = [item for item in rows if member_matches_filters(item, filters)]
        total = len(rows)
        return deepcopy(rows[offset : offset + limit]), total

    def get_member(self, member_id: str) -> dict[str, Any] | None:
        member = self._members.get(member_id)
        return project_member(member) if member else None

    def find_member(self, *, external_userid: str | None = None, mobile: str | None = None, person_id: str | None = None) -> dict[str, Any] | None:
        for member in self._members.values():
            if external_userid and member.get("external_userid") == external_userid:
                return project_member(member)
            if mobile and member.get("mobile") == mobile:
                return project_member(member)
            if person_id and member.get("person_id") == person_id:
                return project_member(member)
        return None

    def save_member(self, member: dict[str, Any]) -> dict[str, Any]:
        self._members[member["member_id"]] = deepcopy(project_member(member))
        return self.get_member(member["member_id"]) or deepcopy(member)

    def append_history(self, member_id: str, event: dict[str, Any]) -> None:
        if member_id in self._members:
            self._members[member_id].setdefault("history", []).append(deepcopy(event))

    def list_history(self, member_id: str) -> list[dict[str, Any]]:
        return deepcopy((self._members.get(member_id) or {}).get("history") or [])

    def create_member_from_questionnaire(self, payload: dict[str, Any]) -> dict[str, Any]:
        next_number = len(self._members) + 1
        member_id = f"member_{next_number:03d}"
        member = {
            "member_id": member_id,
            "person_id": payload.get("person_id") or f"person_fixture_{next_number:03d}",
            "external_userid": payload.get("external_userid") or "",
            "mobile": payload.get("mobile") or "",
            "customer_name": payload.get("customer_name") or "问卷提交用户",
            "owner_userid": "",
            "current_pool": "new_user",
            "followup_type": payload.get("followup_type") or "normal",
            "questionnaire_followup_type": payload.get("followup_type") or "normal",
            "manual_followup_type": "",
            "trial_opened": False,
            "activated": False,
            "converted": False,
            "exited": False,
            "silent": False,
            "latest_event_at": utc_now_iso(),
            "history": [],
            "warnings": ["fixture_created_from_questionnaire"],
        }
        self._members[member_id] = member
        return project_member(member)

    def create_execution_record(self, record: dict[str, Any]) -> dict[str, Any]:
        saved = deepcopy(record)
        saved.setdefault("id", f"exec_{len(self._execution_records) + 1:03d}")
        saved.setdefault("created_at", utc_now_iso())
        saved.setdefault("delivery_status", "fake")
        self._execution_records.insert(0, saved)
        return deepcopy(saved)

    def list_execution_records(self, *, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        return deepcopy(self._execution_records[offset : offset + limit]), len(self._execution_records)

    def profile_segment_template_catalog(self) -> dict[str, Any]:
        return {
            "items": [
                {
                    "id": "fixture_questionnaire_001",
                    "name": "Fixture 分层问卷",
                    "slug": "fixture-profile-segment",
                    "questions": [
                        {
                            "id": "fixture_question_001",
                            "title": "用户意向",
                            "type": "single_choice",
                            "sort_order": 1,
                            "options": [
                                {"id": "fixture_option_high", "option_text": "高意向", "sort_order": 1},
                                {"id": "fixture_option_normal", "option_text": "普通意向", "sort_order": 2},
                            ],
                        }
                    ],
                }
            ],
            "total": 1,
        }

    def list_profile_segment_templates(
        self,
        *,
        enabled_only: bool = False,
        program_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [profile_segment_template_projection(item) for item in self._profile_segment_templates.values()]
        if enabled_only:
            rows = [item for item in rows if item.get("status") == "active" or bool(item.get("enabled"))]
        rows.sort(key=lambda item: (int(item.get("sort_order") or 0), int(item.get("id") or 0)))
        total = len(rows)
        return deepcopy(rows[offset : offset + limit]), total

    def get_profile_segment_template(self, template_id: int) -> dict[str, Any] | None:
        item = self._profile_segment_templates.get(int(template_id))
        return profile_segment_template_projection(item) if item else None

    def create_profile_segment_template(self, payload: dict[str, Any], *, idempotency_key: str, operator: str) -> dict[str, Any]:
        key = str(idempotency_key or "").strip()
        if key and key in self._profile_segment_idempotency:
            replay = deepcopy(self._profile_segment_idempotency[key])
            replay["idempotent_replay"] = True
            return replay

        normalized = normalize_profile_segment_template_payload(payload)
        self._assert_profile_segment_unique(normalized["name"], normalized["code"])
        now = utc_now_iso()
        template_id = max(self._profile_segment_templates) + 1 if self._profile_segment_templates else 1
        saved = profile_segment_template_projection(
            {
                **normalized,
                "id": template_id,
                "created_at": now,
                "updated_at": now,
            }
        )
        self._profile_segment_templates[template_id] = deepcopy(saved)
        audit_event = self._append_profile_segment_audit_event(
            action="create",
            template_id=template_id,
            operator=operator,
            idempotency_key=key,
            before=None,
            after=saved,
        )
        result = {
            "template": deepcopy(saved),
            "template_bundle": {"template": deepcopy(saved)},
            "audit_event": audit_event,
            "rollback": {
                "strategy": "compensating_update_or_status_revert",
                "created_template_id": template_id,
                "delete_approved": False,
            },
            "idempotent_replay": False,
        }
        if key:
            self._profile_segment_idempotency[key] = deepcopy(result)
        return result

    def update_profile_segment_template(self, template_id: int, payload: dict[str, Any], *, operator: str) -> dict[str, Any]:
        existing = self.get_profile_segment_template(template_id)
        if not existing:
            raise NotFoundError("profile segment template not found")
        normalized = normalize_profile_segment_template_payload(payload, partial=True, existing=existing)
        duplicate = self._find_duplicate_profile_segment(normalized["name"], normalized["code"], exclude_id=int(template_id))
        if duplicate:
            raise ContractError("profile segment template name or code already exists")
        now = utc_now_iso()
        updated = profile_segment_template_projection(
            {
                **existing,
                **normalized,
                "id": int(template_id),
                "created_at": existing.get("created_at"),
                "updated_at": now,
            }
        )
        self._profile_segment_templates[int(template_id)] = deepcopy(updated)
        audit_event = self._append_profile_segment_audit_event(
            action="update",
            template_id=int(template_id),
            operator=operator,
            idempotency_key=str(payload.get("idempotency_key") or ""),
            before=existing,
            after=updated,
        )
        return {
            "template": deepcopy(updated),
            "template_bundle": {"template": deepcopy(updated)},
            "audit_event": audit_event,
            "rollback": {
                "strategy": "restore_before_snapshot",
                "template_id": int(template_id),
                "before": deepcopy(existing),
                "after": deepcopy(updated),
            },
        }

    def list_profile_segment_template_audit_events(self) -> list[dict[str, Any]]:
        return deepcopy(self._profile_segment_audit_events)

    def list_task_groups(self, filters: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], int]:
        filters = filters or {}
        program_id = filters.get("program_id")
        include_archived = bool(filters.get("include_archived"))
        limit = int(filters.get("limit") or 50)
        offset = int(filters.get("offset") or 0)
        rows = [task_group_projection(item) for item in self._task_groups.values()]
        if program_id not in (None, ""):
            rows = [item for item in rows if int(item.get("program_id") or 0) == int(program_id)]
        if not include_archived:
            rows = [item for item in rows if not str(item.get("archived_at") or "").strip()]
        rows.sort(key=lambda item: (int(item.get("sort_order") or 0), int(item.get("id") or 0)))
        total = len(rows)
        return deepcopy(rows[offset : offset + limit]), total

    def create_task_group(self, payload: dict[str, Any], *, idempotency_key: str, operator: str) -> dict[str, Any]:
        key = str(idempotency_key or "").strip()
        if not key:
            raise ContractError("idempotency_key is required")
        operator_id = str(operator or "system").strip() or "system"
        normalized = normalize_task_group_create_payload({**payload, "operator": operator_id})
        idempotency_scope = (TASK_GROUP_ROUTE_FAMILY, "create", operator_id, key)
        request_hash = self._request_hash(normalized)
        replay = self._task_group_idempotency.get(idempotency_scope)
        if replay:
            if replay.get("request_hash") != request_hash:
                raise ContractError("idempotency key conflicts with a different request payload")
            response = deepcopy(replay.get("response_snapshot") or {})
            response["idempotent_replay"] = True
            return response
        self._assert_unique_task_group(normalized["program_id"], normalized["group_name"], normalized["group_code"])
        now = utc_now_iso()
        group_id = max(self._task_groups) + 1 if self._task_groups else 1
        saved = task_group_projection(
            {
                **normalized,
                "id": group_id,
                "created_at": now,
                "updated_at": now,
            }
        )
        self._task_groups[group_id] = deepcopy(saved)
        rollback_payload = {
            "strategy": "archive_created_group_in_later_approved_phase",
            "created_group_id": group_id,
            "group_code": saved["group_code"],
            "delete_approved": False,
        }
        audit_event = self._append_task_group_audit_event(
            operation="create",
            operator=operator_id,
            resource_id=group_id,
            before={},
            after=saved,
            request_payload=normalized,
            rollback_payload=rollback_payload,
        )
        result = {
            "group": deepcopy(saved),
            "groups": [deepcopy(saved)],
            "audit_event": audit_event,
            "rollback_payload": rollback_payload,
            "idempotent_replay": False,
        }
        self._task_group_idempotency[idempotency_scope] = {
            "request_hash": request_hash,
            "response_snapshot": deepcopy(result),
            "resource_id": group_id,
            "status": "succeeded",
        }
        return result

    def list_task_group_audit_events(self) -> list[dict[str, Any]]:
        return deepcopy(self._task_group_audit_events)

    def list_workflows(self, filters: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], int]:
        filters = filters or {}
        program_id = filters.get("program_id")
        status = str(filters.get("status") or "").strip()
        include_archived = bool(filters.get("include_archived"))
        limit = int(filters.get("limit") or 50)
        offset = int(filters.get("offset") or 0)
        rows = [workflow_projection(item) for item in self._workflows.values()]
        if program_id not in (None, ""):
            rows = [item for item in rows if int(item.get("program_id") or 0) == int(program_id)]
        if status:
            rows = [item for item in rows if str(item.get("status") or "") == status]
        if not include_archived:
            rows = [item for item in rows if not str(item.get("archived_at") or "").strip()]
        rows.sort(key=lambda item: (str(item.get("updated_at") or ""), int(item.get("id") or 0)), reverse=True)
        total = len(rows)
        return deepcopy(rows[offset : offset + limit]), total

    def create_workflow(self, payload: dict[str, Any], *, idempotency_key: str, operator: str) -> dict[str, Any]:
        key = str(idempotency_key or "").strip()
        if not key:
            raise ContractError("idempotency_key is required")
        operator_id = str(operator or "system").strip() or "system"
        normalized = normalize_workflow_create_payload({**payload, "operator": operator_id})
        idempotency_scope = (WORKFLOW_ROUTE_FAMILY, "create", operator_id, key)
        request_hash = self._request_hash(normalized)
        replay = self._workflow_idempotency.get(idempotency_scope)
        if replay:
            if replay.get("request_hash") != request_hash:
                raise ContractError("idempotency key conflicts with a different request payload")
            response = deepcopy(replay.get("response_snapshot") or {})
            response["idempotent_replay"] = True
            return response
        self._assert_unique_workflow(normalized["program_id"], normalized["workflow_code"])
        now = utc_now_iso()
        workflow_id = max(self._workflows) + 1 if self._workflows else 1
        saved = workflow_projection({**normalized, "id": workflow_id, "created_at": now, "updated_at": now})
        self._workflows[workflow_id] = deepcopy(saved)
        rollback_payload = {
            "strategy": "archive_created_workflow_in_later_approved_phase",
            "created_workflow_id": workflow_id,
            "workflow_code": saved["workflow_code"],
            "delete_approved": False,
        }
        audit_event = self._append_workflow_audit_event(
            operation="create",
            operator=operator_id,
            resource_id=workflow_id,
            before={},
            after=saved,
            request_payload=normalized,
            rollback_payload=rollback_payload,
        )
        result = {
            "workflow": deepcopy(saved),
            "workflows": [deepcopy(saved)],
            "audit_event": audit_event,
            "rollback_payload": rollback_payload,
            "idempotent_replay": False,
        }
        self._workflow_idempotency[idempotency_scope] = {
            "request_hash": request_hash,
            "response_snapshot": deepcopy(result),
            "resource_id": workflow_id,
            "status": "succeeded",
        }
        return result

    def list_workflow_audit_events(self) -> list[dict[str, Any]]:
        return deepcopy(self._workflow_audit_events)

    def list_workflow_nodes(self, filters: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], int]:
        filters = filters or {}
        program_id = filters.get("program_id")
        workflow_id = filters.get("workflow_id")
        node_type = str(filters.get("node_type") or "").strip()
        status = str(filters.get("status") or "").strip()
        include_archived = bool(filters.get("include_archived"))
        limit = int(filters.get("limit") or 50)
        offset = int(filters.get("offset") or 0)
        rows = [workflow_node_projection(item) for item in self._workflow_nodes.values()]
        if program_id not in (None, ""):
            rows = [item for item in rows if int(item.get("program_id") or 0) == int(program_id)]
        if workflow_id not in (None, ""):
            rows = [item for item in rows if int(item.get("workflow_id") or 0) == int(workflow_id)]
        if node_type:
            rows = [item for item in rows if str(item.get("node_type") or "") == node_type]
        if status:
            rows = [item for item in rows if str(item.get("status") or "") == status]
        if not include_archived:
            rows = [item for item in rows if not str(item.get("archived_at") or "").strip()]
        rows.sort(key=lambda item: (int(item.get("workflow_id") or 0), int(item.get("sort_order") or 0), int(item.get("id") or 0)))
        total = len(rows)
        return deepcopy(rows[offset : offset + limit]), total

    def get_workflow_node(self, node_id: int) -> dict[str, Any] | None:
        node = self._workflow_nodes.get(int(node_id))
        if not node:
            return None
        return workflow_node_projection(node)

    def create_workflow_node(self, payload: dict[str, Any], *, idempotency_key: str, operator: str) -> dict[str, Any]:
        key = str(idempotency_key or "").strip()
        if not key:
            raise ContractError("idempotency_key is required")
        operator_id = str(operator or "system").strip() or "system"
        normalized = normalize_workflow_node_create_payload({**payload, "operator": operator_id})
        idempotency_scope = (WORKFLOW_NODE_ROUTE_FAMILY, "create", operator_id, key)
        request_hash = self._request_hash(normalized)
        replay = self._workflow_node_idempotency.get(idempotency_scope)
        if replay:
            if replay.get("request_hash") != request_hash:
                raise ContractError("idempotency key conflicts with a different request payload")
            response = deepcopy(replay.get("response_snapshot") or {})
            response["idempotent_replay"] = True
            return response
        self._assert_unique_workflow_node(normalized["workflow_id"], normalized["node_code"])
        now = utc_now_iso()
        node_id = max(self._workflow_nodes) + 1 if self._workflow_nodes else 1
        saved = workflow_node_projection({**normalized, "id": node_id, "created_at": now, "updated_at": now})
        self._workflow_nodes[node_id] = deepcopy(saved)
        rollback_payload = {
            "strategy": "archive_created_workflow_node_in_later_approved_phase",
            "created_node_id": node_id,
            "node_code": saved["node_code"],
            "delete_approved": False,
        }
        audit_event = self._append_workflow_node_audit_event(
            operation="create",
            operator=operator_id,
            resource_id=node_id,
            before={},
            after=saved,
            request_payload=normalized,
            rollback_payload=rollback_payload,
        )
        result = {
            "node": deepcopy(saved),
            "nodes": [deepcopy(saved)],
            "audit_event": audit_event,
            "rollback_payload": rollback_payload,
            "idempotent_replay": False,
        }
        self._workflow_node_idempotency[idempotency_scope] = {
            "request_hash": request_hash,
            "response_snapshot": deepcopy(result),
            "resource_id": node_id,
            "status": "succeeded",
        }
        return result

    def update_workflow_node(self, node_id: int, payload: dict[str, Any], *, operator: str) -> dict[str, Any]:
        current = self.get_workflow_node(node_id)
        if not current:
            raise NotFoundError("automation workflow node not found")
        operator_id = str(operator or payload.get("operator") or "system").strip() or "system"
        patch = normalize_workflow_node_update_payload({**(payload or {}), "operator": operator_id})
        updated = deepcopy(current)
        for key, value in patch.items():
            if key in {"operator"}:
                continue
            updated[key] = deepcopy(value)
        updated["updated_by"] = operator_id
        updated["updated_at"] = utc_now_iso()
        saved = workflow_node_projection(updated)
        self._workflow_nodes[int(node_id)] = deepcopy(saved)
        audit_event = self._append_workflow_node_audit_event(
            operation="update",
            operator=operator_id,
            resource_id=int(node_id),
            before=current,
            after=saved,
            request_payload=patch,
            rollback_payload={
                "strategy": "restore_previous_workflow_node_metadata",
                "node_id": int(node_id),
                "previous_node": current,
                "delete_approved": False,
            },
        )
        return {"node": deepcopy(saved), "nodes": [deepcopy(saved)], "audit_event": audit_event}

    def delete_workflow_node(self, node_id: int, *, operator: str) -> dict[str, Any]:
        current = self.get_workflow_node(node_id)
        if not current:
            raise NotFoundError("automation workflow node not found")
        operator_id = str(operator or "system").strip() or "system"
        archived = workflow_node_projection(
            {
                **current,
                "status": "archived",
                "archived_at": utc_now_iso(),
                "updated_by": operator_id,
                "updated_at": utc_now_iso(),
            }
        )
        self._workflow_nodes[int(node_id)] = deepcopy(archived)
        rollback_payload = {
            "strategy": "restore_archived_workflow_node_metadata",
            "node_id": int(node_id),
            "previous_node": current,
            "hard_delete_executed": False,
        }
        audit_event = self._append_workflow_node_audit_event(
            operation="archive",
            operator=operator_id,
            resource_id=int(node_id),
            before=current,
            after=archived,
            request_payload={"node_id": int(node_id), "operator": operator_id},
            rollback_payload=rollback_payload,
        )
        return {
            "node": deepcopy(archived),
            "nodes": [deepcopy(archived)],
            "audit_event": audit_event,
            "rollback_payload": rollback_payload,
            "hard_delete_executed": False,
        }

    def list_workflow_node_audit_events(self) -> list[dict[str, Any]]:
        return deepcopy(self._workflow_node_audit_events)

    def list_tasks(self, filters: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], int]:
        filters = filters or {}
        program_id = filters.get("program_id")
        workflow_id = filters.get("workflow_id")
        node_id = filters.get("node_id")
        group_id = filters.get("group_id")
        task_type = str(filters.get("task_type") or "").strip()
        status = str(filters.get("status") or "").strip()
        include_archived = bool(filters.get("include_archived"))
        limit = int(filters.get("limit") or 50)
        offset = int(filters.get("offset") or 0)
        rows = [task_projection(item) for item in self._tasks.values()]
        for field, value in (("program_id", program_id), ("workflow_id", workflow_id), ("node_id", node_id), ("group_id", group_id)):
            if value not in (None, ""):
                rows = [item for item in rows if int(item.get(field) or 0) == int(value)]
        if task_type:
            rows = [item for item in rows if str(item.get("task_type") or "") == task_type]
        if status:
            rows = [item for item in rows if str(item.get("status") or "") == status]
        if not include_archived:
            rows = [item for item in rows if not str(item.get("archived_at") or "").strip()]
        rows.sort(key=lambda item: (int(item.get("workflow_id") or 0), int(item.get("node_id") or 0), int(item.get("sort_order") or 0), int(item.get("id") or 0)))
        total = len(rows)
        return deepcopy(rows[offset : offset + limit]), total

    def get_task(self, task_id: int) -> dict[str, Any] | None:
        task = self._tasks.get(int(task_id))
        if not task:
            return None
        return task_projection(task)

    def create_task(self, payload: dict[str, Any], *, idempotency_key: str, operator: str) -> dict[str, Any]:
        key = str(idempotency_key or "").strip()
        if not key:
            raise ContractError("idempotency_key is required")
        operator_id = str(operator or "system").strip() or "system"
        normalized = normalize_task_create_payload({**payload, "operator": operator_id})
        idempotency_scope = (TASK_ROUTE_FAMILY, "create", operator_id, key)
        request_hash = self._request_hash(normalized)
        replay = self._task_idempotency.get(idempotency_scope)
        if replay:
            if replay.get("request_hash") != request_hash:
                raise ContractError("idempotency key conflicts with a different request payload")
            response = deepcopy(replay.get("response_snapshot") or {})
            response["idempotent_replay"] = True
            return response
        self._assert_unique_task(normalized["workflow_id"], normalized["task_code"])
        now = utc_now_iso()
        task_id = max(self._tasks) + 1 if self._tasks else 1
        saved = task_projection({**normalized, "id": task_id, "created_at": now, "updated_at": now})
        self._tasks[task_id] = deepcopy(saved)
        rollback_payload = {
            "strategy": "archive_created_task_in_later_approved_phase",
            "created_task_id": task_id,
            "task_code": saved["task_code"],
            "delete_approved": False,
        }
        audit_event = self._append_task_audit_event(
            operation="create",
            operator=operator_id,
            resource_id=task_id,
            before={},
            after=saved,
            request_payload=normalized,
            rollback_payload=rollback_payload,
        )
        result = {
            "task": deepcopy(saved),
            "tasks": [deepcopy(saved)],
            "audit_event": audit_event,
            "rollback_payload": rollback_payload,
            "idempotent_replay": False,
        }
        self._task_idempotency[idempotency_scope] = {
            "request_hash": request_hash,
            "response_snapshot": deepcopy(result),
            "resource_id": task_id,
            "status": "succeeded",
        }
        return result

    def update_task(self, task_id: int, payload: dict[str, Any], *, operator: str) -> dict[str, Any]:
        current = self.get_task(task_id)
        if not current:
            raise NotFoundError("automation task not found")
        patch = deepcopy(payload or {})
        updated = deepcopy(current)
        if isinstance(patch.get("metadata"), dict):
            updated["metadata"] = deepcopy(patch["metadata"])
        if isinstance(patch.get("config"), dict):
            updated["config"] = deepcopy(patch["config"])
        updated["updated_by"] = str(operator or patch.get("operator") or "system").strip() or "system"
        updated["updated_at"] = utc_now_iso()
        saved = task_projection(updated)
        self._tasks[int(task_id)] = deepcopy(saved)
        audit_event = self._append_task_audit_event(
            operation="update",
            operator=updated["updated_by"],
            resource_id=int(task_id),
            before=current,
            after=saved,
            request_payload=patch,
            rollback_payload={
                "strategy": "restore_previous_task_config",
                "task_id": int(task_id),
                "previous_config": current.get("config") or {},
                "delete_approved": False,
            },
        )
        return {"task": deepcopy(saved), "audit_event": audit_event}

    def list_task_audit_events(self) -> list[dict[str, Any]]:
        return deepcopy(self._task_audit_events)

    def list_agents(self, filters: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], int]:
        filters = filters or {}
        program_id = filters.get("program_id")
        workflow_id = filters.get("workflow_id")
        node_id = filters.get("node_id")
        task_id = filters.get("task_id")
        agent_type = str(filters.get("agent_type") or "").strip()
        status = str(filters.get("status") or "").strip()
        include_archived = bool(filters.get("include_archived"))
        limit = int(filters.get("limit") or 50)
        offset = int(filters.get("offset") or 0)
        rows = [agent_projection(item) for item in self._agents.values()]
        if program_id not in (None, ""):
            rows = [item for item in rows if int(item.get("program_id") or 0) in {0, int(program_id)}]
        for field, value in (("workflow_id", workflow_id), ("node_id", node_id), ("task_id", task_id)):
            if value not in (None, ""):
                rows = [item for item in rows if int(item.get(field) or 0) == int(value)]
        if agent_type:
            rows = [item for item in rows if str(item.get("agent_type") or "") == agent_type]
        if status:
            rows = [item for item in rows if str(item.get("status") or "") == status]
        if not include_archived:
            rows = [item for item in rows if not str(item.get("archived_at") or "").strip()]
        rows.sort(key=lambda item: (int(item.get("workflow_id") or 0), int(item.get("task_id") or 0), int(item.get("sort_order") or 0), int(item.get("id") or 0)))
        total = len(rows)
        return deepcopy(rows[offset : offset + limit]), total

    def create_agent(self, payload: dict[str, Any], *, idempotency_key: str, operator: str) -> dict[str, Any]:
        key = str(idempotency_key or "").strip()
        if not key:
            raise ContractError("idempotency_key is required")
        operator_id = str(operator or "system").strip() or "system"
        normalized = normalize_agent_create_payload({**payload, "operator": operator_id})
        idempotency_scope = (AGENT_ROUTE_FAMILY, "create", operator_id, key)
        request_hash = self._request_hash(normalized)
        replay = self._agent_idempotency.get(idempotency_scope)
        if replay:
            if replay.get("request_hash") != request_hash:
                raise ContractError("idempotency key conflicts with a different request payload")
            response = deepcopy(replay.get("response_snapshot") or {})
            response["idempotent_replay"] = True
            return response
        self._assert_unique_agent(normalized["workflow_id"], normalized["agent_code"])
        now = utc_now_iso()
        agent_id = max(self._agents) + 1 if self._agents else 1
        saved = agent_projection({**normalized, "id": agent_id, "created_at": now, "updated_at": now})
        self._agents[agent_id] = deepcopy(saved)
        rollback_payload = {
            "strategy": "archive_created_agent_in_later_approved_phase",
            "created_agent_id": agent_id,
            "agent_code": saved["agent_code"],
            "delete_approved": False,
        }
        audit_event = self._append_agent_audit_event(
            operation="create",
            operator=operator_id,
            resource_id=agent_id,
            before={},
            after=saved,
            request_payload=normalized,
            rollback_payload=rollback_payload,
        )
        result = {
            "agent": deepcopy(saved),
            "agents": [deepcopy(saved)],
            "audit_event": audit_event,
            "rollback_payload": rollback_payload,
            "idempotent_replay": False,
        }
        self._agent_idempotency[idempotency_scope] = {
            "request_hash": request_hash,
            "response_snapshot": deepcopy(result),
            "resource_id": agent_id,
            "status": "succeeded",
        }
        return result

    def list_agent_audit_events(self) -> list[dict[str, Any]]:
        return deepcopy(self._agent_audit_events)

    def list_agent_outputs(self, filters: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
        normalized = normalize_agent_output_filters(filters)
        rows = [deepcopy(item) for item in self._agent_outputs.values()]
        for field in ("request_id", "external_contact_id", "userid", "agent_code", "output_type", "applied_status"):
            value = str(normalized.get(field) or "").strip()
            if value:
                rows = [item for item in rows if str(item.get(field) or "") == value]
        min_confidence = normalized.get("min_confidence")
        if min_confidence is not None:
            rows = [item for item in rows if float(item.get("confidence") or 0) >= float(min_confidence)]
        max_confidence = normalized.get("max_confidence")
        if max_confidence is not None:
            rows = [item for item in rows if float(item.get("confidence") or 0) <= float(max_confidence)]
        has_error = normalized.get("has_error")
        if has_error is not None:
            expected = bool(has_error)
            rows = [item for item in rows if bool(str(item.get("error_code") or item.get("error_message") or "").strip()) is expected]
        rows.sort(key=lambda item: (str(item.get("created_at") or ""), str(item.get("output_id") or "")), reverse=True)
        total = len(rows)
        page_rows = rows[normalized["offset"] : normalized["offset"] + normalized["page_size"]]
        projected = [agent_output_projection(item, visibility=normalized["visibility"]) for item in page_rows]
        return deepcopy(projected), total, deepcopy(normalized)

    def get_agent_output(self, output_id: str, filters: dict[str, Any] | None = None) -> dict[str, Any] | None:
        normalized = normalize_agent_output_filters(filters)
        item = self._agent_outputs.get(str(output_id or "").strip())
        if not item:
            return None
        return agent_output_projection(item, visibility=normalized["visibility"])

    def list_agent_runs(self, filters: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
        normalized = normalize_agent_run_filters(filters)
        rows = [deepcopy(item) for item in self._agent_runs.values()]
        for field in ("request_id", "run_id", "agent_code", "run_status", "trigger_source", "external_contact_id", "userid"):
            value = str(normalized.get(field) or "").strip()
            if value:
                rows = [item for item in rows if str(item.get(field) or "") == value]
        for field in ("task_id", "workflow_id"):
            value = normalized.get(field)
            if value not in (None, ""):
                rows = [item for item in rows if int(item.get(field) or 0) == int(value)]
        if normalized["started_after"]:
            rows = [item for item in rows if str(item.get("started_at") or "") >= normalized["started_after"]]
        if normalized["started_before"]:
            rows = [item for item in rows if str(item.get("started_at") or "") <= normalized["started_before"]]
        has_error = normalized.get("has_error")
        if has_error is not None:
            expected = bool(has_error)
            rows = [item for item in rows if bool(str(item.get("error_code") or item.get("error_message") or "").strip()) is expected]
        rows.sort(key=lambda item: (str(item.get("started_at") or ""), str(item.get("run_id") or "")), reverse=True)
        total = len(rows)
        page_rows = rows[normalized["offset"] : normalized["offset"] + normalized["page_size"]]
        projected = [agent_run_projection(item, visibility=normalized["visibility"]) for item in page_rows]
        return deepcopy(projected), total, deepcopy(normalized)

    def get_agent_run(self, run_id: str, filters: dict[str, Any] | None = None) -> dict[str, Any] | None:
        normalized = normalize_agent_run_filters(filters)
        item = self._agent_runs.get(str(run_id or "").strip())
        if not item:
            return None
        return agent_run_projection(item, visibility=normalized["visibility"])

    def _request_hash(self, payload: dict[str, Any]) -> str:
        import hashlib
        import json

        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    def _assert_unique_task_group(self, program_id: int, group_name: str, group_code: str) -> None:
        normalized_name = str(group_name or "").strip().lower()
        normalized_code = str(group_code or "").strip().lower()
        for group in self._task_groups.values():
            item = task_group_projection(group)
            if int(item.get("program_id") or 0) != int(program_id):
                continue
            if str(item.get("group_name") or "").strip().lower() == normalized_name:
                raise ContractError("task group name already exists for program")
            if str(item.get("group_code") or "").strip().lower() == normalized_code:
                raise ContractError("task group code already exists for program")

    def _assert_unique_workflow(self, program_id: int, workflow_code: str) -> None:
        normalized_code = str(workflow_code or "").strip().lower()
        for workflow in self._workflows.values():
            item = workflow_projection(workflow)
            if int(item.get("program_id") or 0) != int(program_id):
                continue
            if str(item.get("workflow_code") or "").strip().lower() == normalized_code:
                raise ContractError("workflow code already exists for program")

    def _assert_unique_workflow_node(self, workflow_id: int, node_code: str) -> None:
        normalized_code = str(node_code or "").strip().lower()
        for node in self._workflow_nodes.values():
            item = workflow_node_projection(node)
            if int(item.get("workflow_id") or 0) != int(workflow_id):
                continue
            if str(item.get("node_code") or "").strip().lower() == normalized_code:
                raise ContractError("workflow node code already exists for workflow")

    def _assert_unique_task(self, workflow_id: int, task_code: str) -> None:
        normalized_code = str(task_code or "").strip().lower()
        for task in self._tasks.values():
            item = task_projection(task)
            if int(item.get("workflow_id") or 0) != int(workflow_id):
                continue
            if str(item.get("task_code") or "").strip().lower() == normalized_code:
                raise ContractError("task code already exists for workflow")

    def _assert_unique_agent(self, workflow_id: int, agent_code: str) -> None:
        normalized_code = str(agent_code or "").strip().lower()
        for agent in self._agents.values():
            item = agent_projection(agent)
            if int(item.get("workflow_id") or 0) != int(workflow_id):
                continue
            if str(item.get("agent_code") or "").strip().lower() == normalized_code:
                raise ContractError("agent code already exists for workflow")

    def _append_task_group_audit_event(
        self,
        *,
        operation: str,
        operator: str,
        resource_id: int,
        before: dict[str, Any],
        after: dict[str, Any],
        request_payload: dict[str, Any],
        rollback_payload: dict[str, Any],
    ) -> dict[str, Any]:
        event = {
            "route_family": TASK_GROUP_ROUTE_FAMILY,
            "operation": operation,
            "operator": str(operator or "system"),
            "resource_type": "task_group",
            "resource_id": int(resource_id),
            "before_snapshot": deepcopy(before),
            "after_snapshot": deepcopy(after),
            "request_payload": deepcopy(request_payload),
            "validation_result": {"ok": True},
            "rollback_payload": deepcopy(rollback_payload),
            "side_effect_safety": task_group_side_effect_safety(),
            "created_at": utc_now_iso(),
        }
        self._task_group_audit_events.insert(0, event)
        return deepcopy(event)

    def _append_workflow_audit_event(
        self,
        *,
        operation: str,
        operator: str,
        resource_id: int,
        before: dict[str, Any],
        after: dict[str, Any],
        request_payload: dict[str, Any],
        rollback_payload: dict[str, Any],
    ) -> dict[str, Any]:
        event = {
            "route_family": WORKFLOW_ROUTE_FAMILY,
            "operation": operation,
            "operator": str(operator or "system"),
            "resource_type": "workflow",
            "resource_id": int(resource_id),
            "before_snapshot": deepcopy(before),
            "after_snapshot": deepcopy(after),
            "request_payload": deepcopy(request_payload),
            "validation_result": {"ok": True},
            "rollback_payload": deepcopy(rollback_payload),
            "side_effect_safety": workflow_side_effect_safety(),
            "created_at": utc_now_iso(),
        }
        self._workflow_audit_events.insert(0, event)
        return deepcopy(event)

    def _append_workflow_node_audit_event(
        self,
        *,
        operation: str,
        operator: str,
        resource_id: int,
        before: dict[str, Any],
        after: dict[str, Any],
        request_payload: dict[str, Any],
        rollback_payload: dict[str, Any],
    ) -> dict[str, Any]:
        event = {
            "route_family": WORKFLOW_NODE_ROUTE_FAMILY,
            "operation": operation,
            "operator": str(operator or "system"),
            "resource_type": "workflow_node",
            "resource_id": int(resource_id),
            "before_snapshot": deepcopy(before),
            "after_snapshot": deepcopy(after),
            "request_payload": deepcopy(request_payload),
            "validation_result": {"ok": True},
            "rollback_payload": deepcopy(rollback_payload),
            "side_effect_safety": workflow_node_side_effect_safety(),
            "created_at": utc_now_iso(),
        }
        self._workflow_node_audit_events.insert(0, event)
        return deepcopy(event)

    def _append_task_audit_event(
        self,
        *,
        operation: str,
        operator: str,
        resource_id: int,
        before: dict[str, Any],
        after: dict[str, Any],
        request_payload: dict[str, Any],
        rollback_payload: dict[str, Any],
    ) -> dict[str, Any]:
        event = {
            "route_family": TASK_ROUTE_FAMILY,
            "operation": operation,
            "operator": str(operator or "system"),
            "resource_type": "task",
            "resource_id": int(resource_id),
            "before_snapshot": deepcopy(before),
            "after_snapshot": deepcopy(after),
            "request_payload": deepcopy(request_payload),
            "validation_result": {"ok": True},
            "rollback_payload": deepcopy(rollback_payload),
            "side_effect_safety": task_side_effect_safety(),
            "created_at": utc_now_iso(),
        }
        self._task_audit_events.insert(0, event)
        return deepcopy(event)

    def _append_agent_audit_event(
        self,
        *,
        operation: str,
        operator: str,
        resource_id: int,
        before: dict[str, Any],
        after: dict[str, Any],
        request_payload: dict[str, Any],
        rollback_payload: dict[str, Any],
    ) -> dict[str, Any]:
        event = {
            "route_family": AGENT_ROUTE_FAMILY,
            "operation": operation,
            "operator": str(operator or "system"),
            "resource_type": "agent",
            "resource_id": int(resource_id),
            "before_snapshot": deepcopy(before),
            "after_snapshot": deepcopy(after),
            "request_payload": deepcopy(request_payload),
            "validation_result": {"ok": True},
            "rollback_payload": deepcopy(rollback_payload),
            "side_effect_safety": agent_side_effect_safety(),
            "created_at": utc_now_iso(),
        }
        self._agent_audit_events.insert(0, event)
        return deepcopy(event)

    def _find_duplicate_profile_segment(self, name: str, code: str, *, exclude_id: int | None = None) -> dict[str, Any] | None:
        normalized_name = str(name or "").strip().lower()
        normalized_code = str(code or "").strip().lower()
        for template_id, template in self._profile_segment_templates.items():
            if exclude_id is not None and int(template_id) == int(exclude_id):
                continue
            item = profile_segment_template_projection(template)
            if normalized_name and str(item.get("name") or "").strip().lower() == normalized_name:
                return item
            if normalized_code and str(item.get("code") or "").strip().lower() == normalized_code:
                return item
        return None

    def _assert_profile_segment_unique(self, name: str, code: str) -> None:
        if self._find_duplicate_profile_segment(name, code):
            raise ContractError("profile segment template name or code already exists")

    def _append_profile_segment_audit_event(
        self,
        *,
        action: str,
        template_id: int,
        operator: str,
        idempotency_key: str,
        before: dict[str, Any] | None,
        after: dict[str, Any],
    ) -> dict[str, Any]:
        event = {
            "action": action,
            "route_family": "/api/admin/automation-conversion/profile-segment-templates*",
            "template_id": int(template_id),
            "operator_id": str(operator or "system"),
            "idempotency_key": idempotency_key,
            "before": deepcopy(before),
            "after": deepcopy(after),
            "created_at": utc_now_iso(),
            "external_event_dispatched": False,
        }
        self._profile_segment_audit_events.insert(0, event)
        return deepcopy(event)


_fixture_repo = InMemoryAutomationRepository()


def _task_group_repository_backend() -> str:
    return str(os.getenv(TASK_GROUP_BACKEND_ENV) or "fixture").strip().lower()


def _task_group_database_url() -> str:
    return str(os.getenv(TASK_GROUP_TEST_DATABASE_URL_ENV) or os.getenv(TASK_GROUP_STAGING_DATABASE_URL_ENV) or "").strip()


def _workflow_repository_backend() -> str:
    return str(os.getenv(WORKFLOW_BACKEND_ENV) or "fixture").strip().lower()


def _workflow_database_url() -> str:
    return str(os.getenv(WORKFLOW_TEST_DATABASE_URL_ENV) or os.getenv(WORKFLOW_STAGING_DATABASE_URL_ENV) or "").strip()


def _workflow_node_repository_backend() -> str:
    return str(os.getenv(WORKFLOW_NODE_BACKEND_ENV) or "fixture").strip().lower()


def _workflow_node_database_url() -> str:
    return str(os.getenv(WORKFLOW_NODE_TEST_DATABASE_URL_ENV) or os.getenv(WORKFLOW_NODE_STAGING_DATABASE_URL_ENV) or "").strip()


def _task_repository_backend() -> str:
    return str(os.getenv(TASK_BACKEND_ENV) or "fixture").strip().lower()


def _task_database_url() -> str:
    return str(os.getenv(TASK_TEST_DATABASE_URL_ENV) or os.getenv(TASK_STAGING_DATABASE_URL_ENV) or raw_database_url()).strip()


def task_postgres_enabled() -> bool:
    return _task_repository_backend() in TASK_SQL_BACKENDS or bool(production_data_ready() and raw_database_url())


def _agent_repository_backend() -> str:
    return str(os.getenv(AGENT_BACKEND_ENV) or "fixture").strip().lower()


def _agent_database_url() -> str:
    return str(os.getenv(AGENT_TEST_DATABASE_URL_ENV) or os.getenv(AGENT_STAGING_DATABASE_URL_ENV) or raw_database_url()).strip()


def agent_postgres_enabled() -> bool:
    return _agent_repository_backend() in AGENT_SQL_BACKENDS or bool(production_data_ready() and raw_database_url())


def _agent_output_repository_backend() -> str:
    return str(os.getenv(AGENT_OUTPUT_BACKEND_ENV) or "fixture").strip().lower()


def _agent_output_database_url() -> str:
    return str(os.getenv(AGENT_OUTPUT_TEST_DATABASE_URL_ENV) or os.getenv(AGENT_OUTPUT_STAGING_DATABASE_URL_ENV) or "").strip()


def _agent_run_repository_backend() -> str:
    return str(os.getenv(AGENT_RUN_BACKEND_ENV) or "fixture").strip().lower()


def _agent_run_database_url() -> str:
    return str(os.getenv(AGENT_RUN_TEST_DATABASE_URL_ENV) or os.getenv(AGENT_RUN_STAGING_DATABASE_URL_ENV) or "").strip()


def build_automation_repository(
    *,
    task_group_backend: str | None = None,
    task_group_engine: Any | None = None,
    workflow_backend: str | None = None,
    workflow_engine: Any | None = None,
    workflow_node_backend: str | None = None,
    workflow_node_engine: Any | None = None,
    task_backend: str | None = None,
    task_engine: Any | None = None,
    agent_backend: str | None = None,
    agent_engine: Any | None = None,
    agent_output_backend: str | None = None,
    agent_output_engine: Any | None = None,
    agent_run_backend: str | None = None,
    agent_run_engine: Any | None = None,
) -> AutomationRepository:
    selected_task_group_backend = str(task_group_backend or _task_group_repository_backend()).strip().lower()
    if selected_task_group_backend in TASK_GROUP_SQL_BACKENDS:
        engine = task_group_engine
        if engine is None:
            database_url = _task_group_database_url()
            if not database_url:
                raise ContractError(
                    f"{TASK_GROUP_TEST_DATABASE_URL_ENV} or {TASK_GROUP_STAGING_DATABASE_URL_ENV} is required when {TASK_GROUP_BACKEND_ENV}=sqlalchemy"
                )
            engine = get_engine(database_url)
        from .task_group_sqlalchemy_repository import SqlAlchemyTaskGroupRepository

        return assert_repository_allowed(
            SqlAlchemyTaskGroupRepository(engine),
            capability_owner="automation_engine.task_groups",
        )
    selected_workflow_backend = str(workflow_backend or _workflow_repository_backend()).strip().lower()
    if selected_workflow_backend in WORKFLOW_SQL_BACKENDS:
        engine = workflow_engine
        if engine is None:
            database_url = _workflow_database_url()
            if not database_url:
                raise ContractError(
                    f"{WORKFLOW_TEST_DATABASE_URL_ENV} or {WORKFLOW_STAGING_DATABASE_URL_ENV} is required when {WORKFLOW_BACKEND_ENV}=sqlalchemy"
                )
            engine = get_engine(database_url)
        from .workflow_sqlalchemy_repository import SqlAlchemyWorkflowRepository

        return assert_repository_allowed(
            SqlAlchemyWorkflowRepository(engine),
            capability_owner="automation_engine.workflows",
        )
    selected_workflow_node_backend = str(workflow_node_backend or _workflow_node_repository_backend()).strip().lower()
    if selected_workflow_node_backend in WORKFLOW_NODE_SQL_BACKENDS:
        engine = workflow_node_engine
        if engine is None:
            database_url = _workflow_node_database_url()
            if not database_url:
                raise ContractError(
                    f"{WORKFLOW_NODE_TEST_DATABASE_URL_ENV} or {WORKFLOW_NODE_STAGING_DATABASE_URL_ENV} is required when {WORKFLOW_NODE_BACKEND_ENV}=sqlalchemy"
                )
            engine = get_engine(database_url)
        from .workflow_node_sqlalchemy_repository import SqlAlchemyWorkflowNodeRepository

        return assert_repository_allowed(
            SqlAlchemyWorkflowNodeRepository(engine),
            capability_owner="automation_engine.workflow_nodes",
        )
    explicit_non_task_backend = any(
        value is not None
        for value in (
            task_group_backend,
            workflow_backend,
            workflow_node_backend,
            agent_backend,
            agent_output_backend,
            agent_run_backend,
        )
    )
    selected_task_backend = str(task_backend or _task_repository_backend()).strip().lower()
    if task_backend is None and not explicit_non_task_backend and production_data_ready() and raw_database_url():
        selected_task_backend = "postgres"
    if selected_task_backend in TASK_SQL_BACKENDS:
        engine = task_engine
        if engine is None:
            database_url = _task_database_url()
            if not database_url:
                raise ContractError(
                    f"{TASK_TEST_DATABASE_URL_ENV} or {TASK_STAGING_DATABASE_URL_ENV} is required when {TASK_BACKEND_ENV}=sqlalchemy"
                )
            engine = get_engine(database_url)
        from .postgres_repo import PostgresTaskRepository

        return assert_repository_allowed(
            PostgresTaskRepository(engine),
            capability_owner="automation_engine.tasks",
        )
    selected_agent_backend = str(agent_backend or _agent_repository_backend()).strip().lower()
    if agent_backend is None and not explicit_non_task_backend and production_data_ready() and raw_database_url():
        selected_agent_backend = "postgres"
    if selected_agent_backend in AGENT_SQL_BACKENDS:
        engine = agent_engine
        if engine is None:
            database_url = _agent_database_url()
            if not database_url:
                raise ContractError(
                    f"{AGENT_TEST_DATABASE_URL_ENV} or {AGENT_STAGING_DATABASE_URL_ENV} is required when {AGENT_BACKEND_ENV}=sqlalchemy"
                )
            engine = get_engine(database_url)
        from .agent_postgres_repository import PostgresAgentRepository

        return assert_repository_allowed(
            PostgresAgentRepository(engine),
            capability_owner="automation_engine.agents",
        )
    selected_agent_output_backend = str(agent_output_backend or _agent_output_repository_backend()).strip().lower()
    if selected_agent_output_backend in AGENT_OUTPUT_SQL_BACKENDS:
        engine = agent_output_engine
        if engine is None:
            database_url = _agent_output_database_url()
            if not database_url:
                raise ContractError(
                    f"{AGENT_OUTPUT_TEST_DATABASE_URL_ENV} or {AGENT_OUTPUT_STAGING_DATABASE_URL_ENV} is required when {AGENT_OUTPUT_BACKEND_ENV}=sqlalchemy"
                )
            engine = get_engine(database_url)
        from .agent_output_sqlalchemy_repository import SqlAlchemyAgentOutputRepository

        return assert_repository_allowed(
            SqlAlchemyAgentOutputRepository(engine),
            capability_owner="automation_engine.agent_outputs",
        )
    selected_agent_run_backend = str(agent_run_backend or _agent_run_repository_backend()).strip().lower()
    if selected_agent_run_backend in AGENT_RUN_SQL_BACKENDS:
        engine = agent_run_engine
        if engine is None:
            database_url = _agent_run_database_url()
            if not database_url:
                raise ContractError(
                    f"{AGENT_RUN_TEST_DATABASE_URL_ENV} or {AGENT_RUN_STAGING_DATABASE_URL_ENV} is required when {AGENT_RUN_BACKEND_ENV}=sqlalchemy"
                )
            engine = get_engine(database_url)
        from .agent_run_sqlalchemy_repository import SqlAlchemyAgentRunRepository

        return assert_repository_allowed(
            SqlAlchemyAgentRunRepository(engine),
            capability_owner="automation_engine.agent_runs",
        )
    return assert_repository_allowed(_fixture_repo, capability_owner="automation_engine")


def reset_automation_fixture_state() -> None:
    global _fixture_repo
    _fixture_repo = InMemoryAutomationRepository()


FixtureAutomationRepository = InMemoryAutomationRepository
