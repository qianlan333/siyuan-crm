from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


DataQualityGroup = Literal[
    "identity",
    "payment",
    "questionnaire",
    "delivery",
    "customer_projection",
]
DataQualityProbeStatus = Literal["registered", "needs_probe"]


@dataclass(frozen=True)
class DataQualityCheckDefinition:
    check_id: str
    group: DataQualityGroup
    title: str
    description: str
    severity: Literal["red", "yellow"]
    signal: str
    threshold: str
    source_tables: tuple[str, ...]
    remediation: str
    probe_status: DataQualityProbeStatus = "needs_probe"

    def model_dump(self) -> dict:
        payload = asdict(self)
        payload["source_tables"] = list(self.source_tables)
        return payload


@dataclass(frozen=True)
class DataQualityGroupDefinition:
    group: DataQualityGroup
    title: str
    description: str

    def model_dump(self) -> dict:
        return asdict(self)


GROUPS: tuple[DataQualityGroupDefinition, ...] = (
    DataQualityGroupDefinition(
        group="identity",
        title="Identity",
        description="Identity queue, conflict, and impossible mapping checks.",
    ),
    DataQualityGroupDefinition(
        group="payment",
        title="Payment",
        description="Order, product, refund, and provider-state consistency checks.",
    ),
    DataQualityGroupDefinition(
        group="questionnaire",
        title="Questionnaire",
        description="Submission, answer, question, and final tag integrity checks.",
    ),
    DataQualityGroupDefinition(
        group="delivery",
        title="Delivery",
        description="Broadcast, external effect, and outbound task failure checks.",
    ),
    DataQualityGroupDefinition(
        group="customer_projection",
        title="Customer Projection",
        description="Read-model freshness and activity timeline completeness checks.",
    ),
)


CHECK_DEFINITIONS: tuple[DataQualityCheckDefinition, ...] = (
    DataQualityCheckDefinition(
        check_id="identity_pending_queue_threshold",
        group="identity",
        title="Pending identity queue exceeds threshold",
        description="Pending identity resolution rows are above the operational threshold.",
        severity="yellow",
        signal="count pending/queued crm_user_identity_resolution_queue rows by age bucket",
        threshold="warn when pending_count > 100 or oldest_pending_age_minutes > 30",
        source_tables=("crm_user_identity_resolution_queue",),
        remediation="Drain or replay the identity resolution queue before relying on downstream projections.",
    ),
    DataQualityCheckDefinition(
        check_id="identity_conflict_count",
        group="identity",
        title="Identity conflict count",
        description="Identity rows or resolution attempts report conflicts that require manual review.",
        severity="red",
        signal="count conflict state identities and resolution queue rows",
        threshold="fail when conflict_count > 0",
        source_tables=("crm_user_identity", "crm_user_identity_resolution_queue"),
        remediation="Resolve the conflicting unionid/external contact/mobile evidence before promotion.",
    ),
    DataQualityCheckDefinition(
        check_id="identity_unionid_duplicate",
        group="identity",
        title="Unionid duplicate impossible check",
        description="A unionid must resolve to exactly one canonical CRM identity.",
        severity="red",
        signal="group canonical crm_user_identity rows by unionid",
        threshold="fail when any non-empty unionid maps to more than one active identity",
        source_tables=("crm_user_identity",),
        remediation="Merge duplicate identities or quarantine the conflicting rows before release.",
    ),
    DataQualityCheckDefinition(
        check_id="identity_external_userid_multi_unionid",
        group="identity",
        title="External user id maps to multiple unionids",
        description="The same external_userid cannot be attached to multiple active unionids.",
        severity="red",
        signal="expand primary_external_userid and external_userids_json then group by external_userid",
        threshold="fail when any external_userid maps to more than one active unionid",
        source_tables=("crm_user_identity",),
        remediation="Correct the external contact binding and replay affected contact projections.",
    ),
    DataQualityCheckDefinition(
        check_id="identity_mobile_multi_active_unionid",
        group="identity",
        title="Mobile maps to multiple active unionids",
        description="A normalized mobile number should not bind multiple active unionids without review.",
        severity="yellow",
        signal="group active crm_user_identity rows by mobile_hash or mobile_normalized digest",
        threshold="warn when any mobile maps to more than one active unionid",
        source_tables=("crm_user_identity",),
        remediation="Review household/shared-phone cases and mark approved exceptions explicitly.",
    ),
    DataQualityCheckDefinition(
        check_id="payment_paid_order_missing_identity",
        group="payment",
        title="Paid order without CRM identity",
        description="Paid orders must be linkable to crm_user_identity before CRM automation uses them.",
        severity="red",
        signal="count paid order rows with no resolved crm_user_identity join",
        threshold="fail when missing_identity_count > 0",
        source_tables=("wechat_pay_orders", "alipay_pay_orders", "crm_user_identity"),
        remediation="Backfill order identity evidence or replay payment identity resolution.",
    ),
    DataQualityCheckDefinition(
        check_id="payment_paid_order_missing_product_code",
        group="payment",
        title="Paid order without product code",
        description="Paid orders need a product_code so entitlement and segmentation rules can run.",
        severity="red",
        signal="count paid orders where product_code is empty",
        threshold="fail when missing_product_code_count > 0",
        source_tables=("wechat_pay_orders", "alipay_pay_orders"),
        remediation="Map provider SKU/package metadata to a CRM product_code and replay entitlement projection.",
    ),
    DataQualityCheckDefinition(
        check_id="payment_refund_amount_exceeds_paid",
        group="payment",
        title="Refund amount exceeds paid amount",
        description="Refund totals should never exceed the captured paid amount for an order.",
        severity="red",
        signal="sum refund amount per order and compare with paid amount",
        threshold="fail when refunded_amount > paid_amount",
        source_tables=("wechat_pay_orders", "alipay_pay_orders", "wechat_pay_refunds"),
        remediation="Reconcile provider refund records and hold affected entitlement changes.",
    ),
    DataQualityCheckDefinition(
        check_id="payment_provider_status_inconsistent",
        group="payment",
        title="Payment status inconsistent with provider state",
        description="Local payment status should match the latest trusted provider state.",
        severity="yellow",
        signal="compare local status with provider status snapshot or callback state",
        threshold="warn when local_status != provider_status after callback settling window",
        source_tables=("wechat_pay_orders", "alipay_pay_orders"),
        remediation="Refresh provider state and replay the order status projector.",
    ),
    DataQualityCheckDefinition(
        check_id="questionnaire_submission_missing_unionid",
        group="questionnaire",
        title="Submission without unionid",
        description=(
            "Questionnaire submissions that affect CRM segmentation must resolve to a unionid; unresolved "
            "submissions may remain only behind the durable continuation guard with no identity-dependent effect."
        ),
        severity="red",
        signal="count unresolved questionnaire submissions without a durable no-effect quarantine guard",
        threshold="fail when unguarded_missing_unionid_count > 0 or missing_identity_count > 0",
        source_tables=(
            "questionnaire_submissions",
            "crm_user_identity",
            "internal_event_outbox",
            "internal_event",
            "external_effect_job",
        ),
        remediation="Resolve the submitter identity or restore the durable quarantine guard before replaying automation.",
    ),
    DataQualityCheckDefinition(
        check_id="questionnaire_submission_missing_answers",
        group="questionnaire",
        title="Submission without answers",
        description="A completed questionnaire submission should include at least one answer payload.",
        severity="yellow",
        signal="count completed submissions with empty answers",
        threshold="warn when completed submission has no answers",
        source_tables=("questionnaire_submissions",),
        remediation="Check submit pipeline payload parsing and retry affected webhook imports.",
    ),
    DataQualityCheckDefinition(
        check_id="questionnaire_answer_missing_question",
        group="questionnaire",
        title="Answer references missing question",
        description="Answer payload keys should match the questionnaire definition used at submit time.",
        severity="yellow",
        signal="compare answer question ids with active or snapshotted questionnaire definition",
        threshold="warn when answer references an unknown question id",
        source_tables=("questionnaire_submissions", "questionnaire_definitions"),
        remediation="Restore the missing definition snapshot or exclude orphan answer fields from tag projection.",
    ),
    DataQualityCheckDefinition(
        check_id="questionnaire_final_tags_malformed",
        group="questionnaire",
        title="Final tags malformed",
        description="final_tags must be structured data that downstream CRM rules can read safely.",
        severity="red",
        signal="parse final_tags payload and validate expected list/object shape",
        threshold="fail when final_tags cannot be parsed or contains invalid tag objects",
        source_tables=("questionnaire_submissions",),
        remediation="Fix the tag projection and replay affected questionnaire submissions.",
    ),
    DataQualityCheckDefinition(
        check_id="delivery_broadcast_job_blocked",
        group="delivery",
        title="Broadcast job blocked",
        description="Broadcast jobs blocked by validation or material issues need an operator-facing queue.",
        severity="yellow",
        signal="count broadcast jobs in blocked status by reason",
        threshold="warn when blocked_count > 0",
        source_tables=("broadcast_jobs", "broadcast_job_events"),
        remediation="Fix blocked recipients/materials or cancel the broadcast before promotion.",
    ),
    DataQualityCheckDefinition(
        check_id="delivery_external_effect_retryable_failures",
        group="delivery",
        title="External effect retryable failures",
        description="Retryable external-effect failures should not accumulate unnoticed.",
        severity="yellow",
        signal="count retryable failed external effects by effect type and age",
        threshold="warn when retryable_failed_count > 0 or oldest_retryable_age_minutes > 15",
        source_tables=("external_effect_job", "external_effect_attempt"),
        remediation="Replay retryable jobs or fix provider/config errors before customer-facing launch.",
    ),
    DataQualityCheckDefinition(
        check_id="delivery_outbound_task_failed",
        group="delivery",
        title="Outbound task failed",
        description="Failed outbound tasks represent customer-visible delivery gaps.",
        severity="yellow",
        signal="count failed outbound_tasks by task type",
        threshold="warn when failed_count > 0",
        source_tables=("outbound_tasks",),
        remediation="Review failure reasons, replay safe tasks, and mark terminal failures explicitly.",
    ),
    DataQualityCheckDefinition(
        check_id="delivery_stuck_queued_claimed",
        group="delivery",
        title="Stuck queued or claimed too long",
        description="Queued or claimed delivery rows that age out usually indicate a worker or lock issue.",
        severity="yellow",
        signal="count queued/claimed jobs older than the SLA window",
        threshold="warn when queued_or_claimed_age_minutes > 30",
        source_tables=("broadcast_jobs", "external_effect_job", "outbound_tasks"),
        remediation="Restart or unblock workers, then release stale claims with an audited recovery job.",
    ),
    DataQualityCheckDefinition(
        check_id="customer_projection_read_model_stale",
        group="customer_projection",
        title="Customer read model stale",
        description="The customer list/detail projection should track recent identity and fact changes.",
        severity="yellow",
        signal="compare latest fact update with customer read-model refreshed_at",
        threshold="warn when projection lag exceeds 30 minutes",
        source_tables=("customer_list_index_next", "customer_detail_snapshot_next", "crm_user_identity"),
        remediation="Replay customer read-model projection for stale unionids.",
    ),
    DataQualityCheckDefinition(
        check_id="customer_projection_customer_360_stale",
        group="customer_projection",
        title="Customer 360 stale",
        description="Customer 360 aggregates should include recent identity, order, questionnaire, and message facts.",
        severity="yellow",
        signal="compare latest source fact timestamp with customer_360 freshness probes",
        threshold="warn when any source probe lags projection refresh by more than 30 minutes",
        source_tables=(
            "crm_user_identity",
            "wechat_pay_orders",
            "alipay_pay_orders",
            "questionnaire_submissions",
            "archived_messages",
            "customer_detail_snapshot_next",
        ),
        remediation="Replay the stale Customer 360 source projector and verify the unionid timeline.",
    ),
    DataQualityCheckDefinition(
        check_id="customer_projection_timeline_missing_recent_activity",
        group="customer_projection",
        title="Timeline missing recent activity",
        description="Recent customer-facing activity should appear in the operational timeline projection.",
        severity="yellow",
        signal="compare recent orders/questionnaires/messages/effects with timeline event coverage",
        threshold="warn when recent activity is absent from timeline projection",
        source_tables=(
            "wechat_pay_orders",
            "alipay_pay_orders",
            "questionnaire_submissions",
            "archived_messages",
            "external_effect_job",
        ),
        remediation="Replay timeline projection for the affected unionids and source event windows.",
    ),
)


def list_data_quality_groups() -> list[dict]:
    return [group.model_dump() for group in GROUPS]


def list_data_quality_check_definitions() -> list[dict]:
    return [definition.model_dump() for definition in CHECK_DEFINITIONS]


def get_data_quality_check_definition(check_id: str) -> dict | None:
    for definition in CHECK_DEFINITIONS:
        if definition.check_id == check_id:
            return definition.model_dump()
    return None


def data_quality_checks_by_group() -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {group.group: [] for group in GROUPS}
    for definition in CHECK_DEFINITIONS:
        grouped[definition.group].append(definition.model_dump())
    return grouped
