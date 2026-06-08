from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from aicrm_next.send_content.dto import SendContentPackage


class ApplyQuestionnaireResultRequest(BaseModel):
    person_id: str | None = None
    external_userid: str | None = None
    mobile: str | None = None
    customer_name: str | None = None
    followup_type: str = "normal"
    questionnaire_id: int | None = None
    submission_id: str | None = None
    final_tags: list[str] = Field(default_factory=list)
    source: str = "questionnaire"
    operator: str = "system"
    reason: str = "questionnaire_submitted"


class ApplyTrialOpenedFactRequest(BaseModel):
    member_id: str
    source: str = "fixture"
    operator: str = "system"
    reason: str = "trial_opened"
    occurred_at: str | None = None


class ApplyActivationFactRequest(BaseModel):
    member_id: str | None = None
    mobile: str | None = None
    external_userid: str | None = None
    activated_at: str | None = None
    source: str = "fixture"
    operator: str = "system"
    reason: str = "activation_fact"


class OverrideFollowupTypeRequest(BaseModel):
    followup_type: str
    operator: str = "system"
    reason: str = "manual_override"


class AutomationActionRequest(BaseModel):
    operator: str = "system"
    reason: str = ""


class ActivationWebhookRequest(BaseModel):
    mobile: str | None = None
    external_userid: str | None = None
    activated_at: str | None = None
    source: str = "activation_webhook"
    operator: str = "system"


class PushOpenClawContextRequest(BaseModel):
    operator: str = "system"
    reason: str = "manual_fake_push"


class ProfileSegmentTemplateListRequest(BaseModel):
    enabled_only: bool = False
    program_id: int | None = None
    limit: int = 50
    offset: int = 0


class ProfileSegmentTemplateCreateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    segment_key: str | None = None
    code: str | None = None
    conditions: dict[str, Any] | list[Any] = Field(default_factory=dict)
    rules: dict[str, Any] | list[Any] = Field(default_factory=dict)
    status: str = "draft"
    sort_order: int = 0
    idempotency_key: str | None = None
    operator: str = "system"


class ProfileSegmentTemplateUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    segment_key: str | None = None
    code: str | None = None
    conditions: dict[str, Any] | list[Any] | None = None
    rules: dict[str, Any] | list[Any] | None = None
    status: str | None = None
    sort_order: int | None = None
    idempotency_key: str | None = None
    operator: str = "system"


class ActionTemplateListRequest(BaseModel):
    template_source: str = ""
    category: str = ""
    keyword: str = ""
    include_archived: bool = False
    limit: int = 50
    offset: int = 0


class ActionTemplateCreateRequest(BaseModel):
    name: str | None = None
    template_name: str | None = None
    code: str | None = None
    template_code: str | None = None
    template_source: str = "crm_local"
    category: str = ""
    description: str = ""
    status: str = "active"
    default_config: dict[str, Any] = Field(default_factory=dict)
    ui_schema: dict[str, Any] = Field(default_factory=dict)
    workflow_blueprint: dict[str, Any] = Field(default_factory=dict)
    node_blueprints: list[Any] = Field(default_factory=list)
    idempotency_key: str | None = None
    operator: str = "system"


class TaskGroupListRequest(BaseModel):
    program_id: int | None = None
    include_archived: bool = False
    limit: int = 50
    offset: int = 0


class TaskGroupCreateRequest(BaseModel):
    program_id: int = 0
    group_name: str | None = None
    name: str | None = None
    group_code: str | None = None
    code: str | None = None
    sort_order: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None
    operator: str = "system"


class WorkflowListRequest(BaseModel):
    program_id: int | None = None
    status: str = ""
    include_archived: bool = False
    limit: int = 50
    offset: int = 0


class WorkflowCreateRequest(BaseModel):
    program_id: int = 0
    workflow_name: str | None = None
    name: str | None = None
    workflow_code: str | None = None
    code: str | None = None
    description: str = ""
    status: str = "draft"
    segmentation_basis: dict[str, Any] = Field(default_factory=dict)
    behavior_tier_scheme: dict[str, Any] = Field(default_factory=dict)
    profile_segment_template_id: int = 0
    idempotency_key: str | None = None
    operator: str = "system"


class WorkflowNodeListRequest(BaseModel):
    program_id: int | None = None
    workflow_id: int | None = None
    node_type: str = ""
    status: str = ""
    include_archived: bool = False
    limit: int = 50
    offset: int = 0


class WorkflowNodeCreateRequest(BaseModel):
    program_id: int = 0
    workflow_id: int = 0
    node_name: str | None = None
    name: str | None = None
    node_code: str | None = None
    code: str | None = None
    node_type: str = "manual"
    status: str = "draft"
    sort_order: int = 0
    position: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None
    operator: str = "system"


class WorkflowNodeUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    node_name: str | None = None
    name: str | None = None
    node_code: str | None = None
    code: str | None = None
    node_type: str | None = None
    status: str | None = None
    sort_order: int | None = None
    position: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    config: dict[str, Any] | None = None
    operator: str = "system"


class TaskListRequest(BaseModel):
    program_id: int | None = None
    workflow_id: int | None = None
    node_id: int | None = None
    group_id: int | None = None
    task_type: str = ""
    status: str = ""
    include_archived: bool = False
    limit: int = 50
    offset: int = 0


class TaskCreateRequest(BaseModel):
    program_id: int = 0
    workflow_id: int = 0
    node_id: int = 0
    group_id: int = 0
    task_name: str | None = None
    name: str | None = None
    task_code: str | None = None
    code: str | None = None
    task_type: str = "manual"
    status: str = "draft"
    sort_order: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None
    operator: str = "system"


class TaskUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    metadata: dict[str, Any] | None = None
    config: dict[str, Any] | None = None
    content_mode: str | None = None
    profile_segment_template_id: int | None = None
    unified_content_json: dict[str, Any] | None = None
    segment_contents_json: list[dict[str, Any]] | None = None
    agent_config_json: dict[str, Any] | None = None
    operator: str = "system"


class SendStrategyUpdateRequest(BaseModel):
    content_mode: str
    profile_segment_template_id: int | None = None
    agent_code: str | None = None
    operator: str = "system"


class UnifiedSendContentUpdateRequest(BaseModel):
    content_package: SendContentPackage = Field(default_factory=SendContentPackage)
    operator: str = "system"


class ProfileSegmentSendContentUpdateRequest(BaseModel):
    segment_name: str = ""
    profile_segment_template_id: int
    content_package: SendContentPackage = Field(default_factory=SendContentPackage)
    operator: str = "system"


class BehaviorSegmentSendContentUpdateRequest(BaseModel):
    segment_name: str = ""
    content_package: SendContentPackage = Field(default_factory=SendContentPackage)
    operator: str = "system"


class AgentMaterialsUpdateRequest(BaseModel):
    agent_code: str
    content_package: SendContentPackage = Field(default_factory=SendContentPackage)
    requirement: str = ""
    fallback_content: str = ""
    prompt: str = ""
    material_prompt: str = ""
    operator: str = "system"


class AgentListRequest(BaseModel):
    program_id: int | None = None
    workflow_id: int | None = None
    node_id: int | None = None
    task_id: int | None = None
    agent_type: str = ""
    status: str = ""
    include_archived: bool = False
    limit: int = 50
    offset: int = 0


class AgentCreateRequest(BaseModel):
    program_id: int = 0
    workflow_id: int = 0
    node_id: int = 0
    task_id: int = 0
    agent_name: str | None = None
    name: str | None = None
    agent_code: str | None = None
    code: str | None = None
    agent_type: str = "metadata"
    status: str = "draft"
    sort_order: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None
    operator: str = "system"


class AgentOutputListRequest(BaseModel):
    page: int = 1
    page_size: int = 50
    request_id: str = ""
    external_contact_id: str = ""
    userid: str = ""
    agent_code: str = ""
    output_type: str = ""
    applied_status: str = ""
    min_confidence: float | None = None
    max_confidence: float | None = None
    has_error: bool | None = None
    visibility: str = "masked"


class AgentOutputDetailRequest(BaseModel):
    output_id: str
    visibility: str = "masked"


class AgentRunListRequest(BaseModel):
    page: int = 1
    page_size: int = 50
    request_id: str = ""
    run_id: str = ""
    agent_code: str = ""
    run_status: str = ""
    trigger_source: str = ""
    external_contact_id: str = ""
    userid: str = ""
    task_id: int | None = None
    workflow_id: int | None = None
    started_after: str = ""
    started_before: str = ""
    has_error: bool | None = None
    visibility: str = "masked"


class AgentRunDetailRequest(BaseModel):
    run_id: str
    visibility: str = "masked"


class ActionTemplateValidationError(ValueError):
    pass
