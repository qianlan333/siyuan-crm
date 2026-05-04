from __future__ import annotations

from typing import Any

from .domains.archive import repo as archive_repo
from .domains.archive import service as archive_domain_service
from .domains.callbacks import service as callbacks_domain_service
from .domains.contacts import repo as contacts_repo
from .domains.contacts import service as contacts_domain_service
from .domains.group_chats import repo as group_chat_repo
from .domains.group_chats import service as group_chat_domain_service
from .domains.identity import service as identity_domain_service
from .domains.marketing_automation import service as marketing_automation_domain_service
from .domains.outbound_webhook import service as outbound_webhook_domain_service
from .domains.questionnaire import service as questionnaire_domain_service
from .domains.routing_config.service import (
    get_owner_class_term_backfill_entry_source_override,
)
from .domains.tags import repo as tags_repo
from .domains.tags import service as tags_domain_service
from .domains.tasks import service as tasks_domain_service
from .domains.user_ops import page_service as user_ops_page_service
from .domains.user_ops import service as user_ops_domain_service
from .infra.helpers import (
    db_bool as _db_bool,
    normalize_optional_timestamp as _normalize_optional_timestamp,
    stringify_db_timestamp as _stringify_db_timestamp,
)
from .infra import user_ops_runtime


# Thin compatibility facade:
# - re-export stable helpers from domain/infra modules
# - keep a small number of wrappers where backward-compatible call signatures,
#   dependency injection, or monkeypatch points still matter
# - do not place new domain implementation here

QUESTIONNAIRE_TYPES = questionnaire_domain_service.QUESTIONNAIRE_TYPES
questionnaire_logger = questionnaire_domain_service.questionnaire_logger
owner_backfill_logger = user_ops_domain_service.owner_backfill_logger

QuestionnaireAlreadySubmittedError = questionnaire_domain_service.QuestionnaireAlreadySubmittedError
ContactBindingConflictError = identity_domain_service.ContactBindingConflictError
ThirdPartyUserSyncError = user_ops_domain_service.ThirdPartyUserSyncError

_select_follow_user = contacts_domain_service._select_follow_user
_parse_send_time = archive_repo._parse_send_time
_batch_window_for_send_time = archive_repo._batch_window_for_send_time

normalize_contact_record = contacts_domain_service.normalize_contact_record
target_contact_description = contacts_domain_service.target_contact_description
contact_description_state = contacts_domain_service.contact_description_state
needs_contact_description_update = contacts_domain_service.needs_contact_description_update
plan_contact_description_fix = contacts_domain_service.plan_contact_description_fix
upsert_contacts = contacts_repo.upsert_contacts
list_contacts = contacts_repo.list_contacts
get_contact_tag_snapshots = tags_repo.get_contact_tag_snapshots
list_signup_tag_rules = tags_repo.list_signup_tag_rules
_signup_tag_group_name = tags_domain_service.signup_tag_group_name
get_signup_status_definitions = tags_domain_service.get_signup_status_definitions
get_signup_status_definition = tags_domain_service.get_signup_status_definition
get_signup_status_definition_by_tag_name = tags_domain_service.get_signup_status_definition_by_tag_name
upsert_signup_tag_rule = tags_repo.upsert_signup_tag_rule
get_signup_tag_rules_config = tags_domain_service.get_signup_tag_rules_config
resolve_signup_status_from_tags = tags_domain_service.resolve_signup_status_from_tags
build_class_user_tag_view = tags_domain_service.build_class_user_tag_view

update_contact_description_snapshot = contacts_repo.update_contact_description_snapshot
count_contacts = contacts_repo.count_contacts
get_last_contacts_sync_time = contacts_repo.get_last_contacts_sync_time

normalize_external_contact_identity = identity_domain_service.normalize_external_contact_identity
_normalize_mobile = identity_domain_service.normalize_mobile

_normalize_legacy_user_ops_current_status = user_ops_domain_service._normalize_legacy_user_ops_current_status
_legacy_user_ops_status_rank = user_ops_domain_service._legacy_user_ops_status_rank
_user_ops_merge_key = user_ops_domain_service._user_ops_merge_key
_extract_third_party_user_id = user_ops_domain_service._extract_third_party_user_id
_normalize_user_ops_lead_pool_activation_state = user_ops_domain_service._normalize_user_ops_lead_pool_activation_state
_serialize_user_ops_lead_pool_current_row = user_ops_domain_service._serialize_user_ops_lead_pool_current_row
_get_user_ops_lead_pool_current_row_by_id = user_ops_domain_service._get_user_ops_lead_pool_current_row_by_id
_list_user_ops_lead_pool_matches = user_ops_domain_service._list_user_ops_lead_pool_matches
_current_user_ops_operator = user_ops_domain_service._current_user_ops_operator
_user_ops_class_term_options = user_ops_domain_service._user_ops_class_term_options
_get_active_class_term_mapping_by_no = user_ops_domain_service._get_active_class_term_mapping_by_no

log_external_contact_event = callbacks_domain_service.log_external_contact_event
mark_external_contact_event_processing = callbacks_domain_service.mark_external_contact_event_processing
get_external_contact_event_log = callbacks_domain_service.get_external_contact_event_log
finish_external_contact_event_log = callbacks_domain_service.finish_external_contact_event_log
get_recent_external_contact_event_logs = callbacks_domain_service.get_recent_external_contact_event_logs

normalize_group_chat_record = group_chat_domain_service.normalize_group_chat_record
upsert_group_chats = group_chat_repo.upsert_group_chats
get_group_chat_by_chat_id = group_chat_repo.get_group_chat_by_chat_id
get_group_chat_map = group_chat_repo.get_group_chat_map
list_group_chats = group_chat_repo.list_group_chats
count_group_chats = group_chat_repo.count_group_chats

count_archived_messages = archive_domain_service.count_archived_messages
normalize_archived_message = archive_domain_service.normalize_archived_message
format_message_row = archive_domain_service.format_message_row
extract_roomid_from_raw_payload = archive_domain_service.extract_roomid_from_raw_payload
insert_archived_messages = archive_domain_service.insert_archived_messages
create_sync_run = archive_domain_service.create_sync_run
finish_sync_run = archive_domain_service.finish_sync_run
_normalize_chat_type_filter = archive_domain_service._normalize_chat_type_filter
list_archived_messages_by_window = archive_domain_service.list_archived_messages_by_window
get_archive_last_seq = archive_domain_service.get_archive_last_seq
set_archive_last_seq = archive_domain_service.set_archive_last_seq
get_last_sync_run = archive_domain_service.get_last_sync_run
materialize_message_batches = archive_domain_service.materialize_message_batches
list_message_batches = archive_domain_service.list_message_batches
ack_message_batch = archive_domain_service.ack_message_batch

save_outbound_task = tasks_domain_service.save_outbound_task
get_conversion_batch = marketing_automation_domain_service.get_conversion_batch
get_customer_trial_opening_fact = marketing_automation_domain_service.get_customer_trial_opening_fact
evaluate_customer_marketing_state = marketing_automation_domain_service.evaluate_customer_marketing_state
evaluate_customer_value_segment = marketing_automation_domain_service.evaluate_customer_value_segment
get_openclaw_customer_marketing_profile = marketing_automation_domain_service.get_openclaw_customer_marketing_profile
get_pending_conversion_batches = marketing_automation_domain_service.get_pending_conversion_batches
process_inbound_messages_for_openclaw = marketing_automation_domain_service.process_inbound_messages_for_openclaw
send_pool_private_message = marketing_automation_domain_service.send_pool_private_message
route_signup_conversion_batch_candidates = marketing_automation_domain_service.route_signup_conversion_batch_candidates
list_signup_conversion_question_rules = marketing_automation_domain_service.list_signup_conversion_question_rules
trigger_openclaw_focus_message_webhook = marketing_automation_domain_service.trigger_openclaw_focus_message_webhook
upsert_customer_trial_opening_fact = marketing_automation_domain_service.upsert_customer_trial_opening_fact

save_tag_snapshot = tags_repo.save_tag_snapshot
remove_tag_snapshot = tags_repo.remove_tag_snapshot
remove_tag_snapshots_for_other_users = tags_repo.remove_tag_snapshots_for_other_users
_list_contact_tag_ids_for_user = tags_repo.list_contact_tag_ids_for_user
remove_all_tag_snapshots_for_other_users = tags_repo.remove_all_tag_snapshots_for_other_users

_json_dumps = questionnaire_domain_service._json_dumps
_json_array = questionnaire_domain_service._json_array
_dedupe_strings = questionnaire_domain_service._dedupe_strings
_normalize_bool = questionnaire_domain_service._normalize_bool
_normalize_float = questionnaire_domain_service._normalize_float
_normalize_int = questionnaire_domain_service._normalize_int
_normalize_required_integer = questionnaire_domain_service._normalize_required_integer
_validate_tag_codes_payload = questionnaire_domain_service._validate_tag_codes_payload
_slugify_questionnaire = questionnaire_domain_service._slugify_questionnaire
_normalize_tag_codes = questionnaire_domain_service._normalize_tag_codes


def _bind_questionnaire_domain() -> None:
    questionnaire_domain_service.QuestionnaireAlreadySubmittedError = QuestionnaireAlreadySubmittedError
    questionnaire_domain_service.resolve_external_contact_identity = resolve_external_contact_identity
    questionnaire_domain_service.bind_openid_to_external_contact = bind_openid_to_external_contact
    questionnaire_domain_service.bind_mobile_to_external_contact = bind_mobile_to_external_contact
    questionnaire_domain_service._normalize_mobile = _normalize_mobile


def _user_ops_contact_client():
    # Historical monkeypatch / DI hook. Keep the symbol stable for tests and
    # user-ops runtime overrides even as callers move away from services.py.
    return user_ops_runtime.get_user_ops_contact_client()


def _bind_user_ops_domain() -> None:
    user_ops_domain_service._user_ops_contact_client = _user_ops_contact_client
    user_ops_domain_service._resolve_third_party_user_id_by_mobile = _resolve_third_party_user_id_by_mobile
    user_ops_domain_service._db_bool = _db_bool
    user_ops_domain_service._normalize_mobile = _normalize_mobile
    user_ops_domain_service._list_contact_tag_ids_for_user = _list_contact_tag_ids_for_user
    user_ops_domain_service._stringify_db_timestamp = _stringify_db_timestamp
    user_ops_domain_service.resolve_person_identity = resolve_person_identity
    user_ops_domain_service.get_contact_binding_status = get_contact_binding_status
    user_ops_domain_service.save_tag_snapshot = save_tag_snapshot
    user_ops_domain_service.remove_tag_snapshot = remove_tag_snapshot
    user_ops_domain_service.remove_tag_snapshots_for_other_users = remove_tag_snapshots_for_other_users
    user_ops_domain_service.remove_all_tag_snapshots_for_other_users = remove_all_tag_snapshots_for_other_users
    user_ops_domain_service.get_owner_class_term_backfill_entry_source_override = (
        get_owner_class_term_backfill_entry_source_override
    )
    user_ops_domain_service.get_signup_status_definition_by_tag_name = get_signup_status_definition_by_tag_name
    user_ops_domain_service.get_class_user_status_definition = get_class_user_status_definition
    user_ops_domain_service.get_class_user_status_current = get_class_user_status_current
    user_ops_domain_service.upsert_class_user_status_current = upsert_class_user_status_current
    user_ops_domain_service.append_class_user_status_history = append_class_user_status_history
    user_ops_domain_service.update_class_user_status_sync_result = update_class_user_status_sync_result


def _resolve_signup_status_for_contact(external_userid: str, owner_userid: str) -> str:
    payload = enrich_contact_context(
        {
            "external_userid": str(external_userid or "").strip(),
            "owner_userid": str(owner_userid or "").strip(),
        }
    )
    return str(payload.get("signup_status") or "").strip()


# Wave 1 compatibility wrappers:
# prefer the formal application API where it already exists, but keep the
# historical services.py symbols stable for legacy imports and monkeypatching.


def list_outbound_webhook_deliveries(
    *,
    event_type: str = "",
    status: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 1 automation-engine query."""

    from .application.automation_engine.dto import OutboundWebhookListQueryDTO
    from .application.automation_engine.queries import ListOutboundWebhookDeliveriesQuery

    return ListOutboundWebhookDeliveriesQuery()(
        OutboundWebhookListQueryDTO(
            event_type=str(event_type or "").strip(),
            status=str(status or "").strip(),
            limit=int(limit),
        )
    )


def retry_outbound_webhook_delivery(delivery_id: int) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 1 automation-engine command."""

    from .application.automation_engine.commands import RetryOutboundWebhookDeliveryCommand
    from .application.automation_engine.dto import OutboundWebhookRetryCommandDTO

    return RetryOutboundWebhookDeliveryCommand()(
        OutboundWebhookRetryCommandDTO(delivery_id=int(delivery_id))
    )


def run_due_outbound_webhook_retries(*, limit: int = 20) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 1 automation-engine command."""

    from .application.automation_engine.commands import RunDueOutboundWebhookRetriesCommand
    from .application.automation_engine.dto import OutboundWebhookRetryBatchCommandDTO

    return RunDueOutboundWebhookRetriesCommand()(
        OutboundWebhookRetryBatchCommandDTO(limit=int(limit))
    )


def apply_activation_webhook(
    *,
    mobile: str,
    activated_at: str = "",
    operator: str = "",
    source: str = "activation_webhook",
) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 1 automation-engine command."""

    from .application.automation_engine.commands import ApplyActivationWebhookCommand
    from .application.automation_engine.dto import ActivationWebhookCommandDTO

    return ApplyActivationWebhookCommand()(
        ActivationWebhookCommandDTO(
            mobile=str(mobile or "").strip(),
            activated_at=str(activated_at or "").strip(),
            operator=str(operator or "").strip(),
            source=str(source or "").strip() or "activation_webhook",
        )
    )


def list_signup_conversion_batches(
    *,
    limit: int = 20,
    cursor: str = "",
    scenario_key: str = "",
) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 1 automation-engine query."""

    from .application.automation_engine.dto import SignupConversionBatchListQueryDTO
    from .application.automation_engine.queries import ListSignupConversionBatchesQuery

    return ListSignupConversionBatchesQuery()(
        SignupConversionBatchListQueryDTO(
            limit=int(limit),
            cursor=str(cursor or ""),
            scenario_key=str(scenario_key or ""),
        )
    )


def get_signup_conversion_batch(batch_id: int, *, scenario_key: str = "") -> dict[str, Any] | None:
    """Backward-compatible wrapper around the Wave 1 automation-engine query."""

    from .application.automation_engine.dto import SignupConversionBatchDetailQueryDTO
    from .application.automation_engine.queries import GetSignupConversionBatchQuery

    return GetSignupConversionBatchQuery()(
        SignupConversionBatchDetailQueryDTO(
            batch_id=int(batch_id),
            scenario_key=str(scenario_key or ""),
        )
    )


def get_outbound_webhook_delivery_counts() -> dict[str, int]:
    """Backward-compatible wrapper around the Wave 4 automation-engine query."""

    from .application.automation_engine.dto import OutboundWebhookCountQueryDTO
    from .application.automation_engine.queries import GetOutboundWebhookDeliveryCountsQuery

    return GetOutboundWebhookDeliveryCountsQuery()(OutboundWebhookCountQueryDTO())


def get_signup_conversion_config(
    *,
    automation_key: str = marketing_automation_domain_service.DEFAULT_SCENARIO_KEY,
) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 4 automation-engine query."""

    from .application.automation_engine.dto import SignupConversionConfigQueryDTO
    from .application.automation_engine.queries import GetSignupConversionConfigQuery

    return GetSignupConversionConfigQuery()(
        SignupConversionConfigQueryDTO(automation_key=str(automation_key or "").strip())
    )


def save_signup_conversion_config(
    payload: dict[str, Any],
    *,
    automation_key: str = marketing_automation_domain_service.DEFAULT_SCENARIO_KEY,
    enforce_required_mobile_question: bool = False,
) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 4 automation-engine command."""

    from .application.automation_engine.commands import SaveSignupConversionConfigCommand
    from .application.automation_engine.dto import SignupConversionConfigCommandDTO

    return SaveSignupConversionConfigCommand()(
        SignupConversionConfigCommandDTO(
            payload=dict(payload or {}),
            automation_key=str(automation_key or "").strip(),
            enforce_required_mobile_question=bool(enforce_required_mobile_question),
        )
    )


def preview_signup_conversion_customer(
    *,
    external_userid: str = "",
    person_id: int | None = None,
    automation_key: str = marketing_automation_domain_service.DEFAULT_SCENARIO_KEY,
    persist: bool = True,
) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 4 automation-engine query."""

    from .application.automation_engine.dto import SignupConversionPreviewQueryDTO
    from .application.automation_engine.queries import PreviewSignupConversionCustomerQuery

    return PreviewSignupConversionCustomerQuery()(
        SignupConversionPreviewQueryDTO(
            external_userid=str(external_userid or "").strip(),
            person_id=person_id,
            automation_key=str(automation_key or "").strip(),
            persist=bool(persist),
        )
    )


def recompute_signup_conversion_customers(
    *,
    external_userid: str = "",
    person_id: int | None = None,
    external_userids: list[Any] | None = None,
    person_ids: list[Any] | None = None,
    automation_key: str = marketing_automation_domain_service.DEFAULT_SCENARIO_KEY,
    persist: bool = True,
) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 4 automation-engine command."""

    from .application.automation_engine.commands import RecomputeSignupConversionCustomersCommand
    from .application.automation_engine.dto import SignupConversionRecomputeCommandDTO

    return RecomputeSignupConversionCustomersCommand()(
        SignupConversionRecomputeCommandDTO(
            external_userid=str(external_userid or "").strip(),
            person_id=person_id,
            external_userids=list(external_userids or []),
            person_ids=list(person_ids or []),
            automation_key=str(automation_key or "").strip(),
            persist=bool(persist),
        )
    )


def record_conversion_feedback(
    *,
    feedback_type: str,
    external_userid: str = "",
    chat_id: str = "",
    actor: str = "",
    feedback_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 4 automation-engine command."""

    from .application.automation_engine.commands import RecordConversionFeedbackCommand
    from .application.automation_engine.dto import ConversionFeedbackCommandDTO

    return RecordConversionFeedbackCommand()(
        ConversionFeedbackCommandDTO(
            feedback_type=str(feedback_type or "").strip(),
            external_userid=str(external_userid or "").strip(),
            chat_id=str(chat_id or "").strip(),
            actor=str(actor or "").strip(),
            feedback_payload=dict(feedback_payload or {}) if feedback_payload else None,
        )
    )


def ack_conversion_batch(
    batch_id: int,
    *,
    acked_by: str = "",
    ack_note: str = "",
    automation_key: str = marketing_automation_domain_service.DEFAULT_SCENARIO_KEY,
) -> dict[str, Any] | None:
    """Backward-compatible wrapper around the Wave 4 automation-engine command."""

    from .application.automation_engine.commands import AcknowledgeConversionBatchCommand
    from .application.automation_engine.dto import ConversionBatchAckCommandDTO

    return AcknowledgeConversionBatchCommand()(
        ConversionBatchAckCommandDTO(
            batch_id=int(batch_id),
            acked_by=str(acked_by or "").strip(),
            ack_note=str(ack_note or "").strip(),
            automation_key=str(automation_key or "").strip(),
        )
    )


def get_customer_marketing_profile(
    external_userid: str,
    *,
    scenario_key: str = marketing_automation_domain_service.DEFAULT_SCENARIO_KEY,
    batch_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 4 automation-engine query."""

    from .application.automation_engine.dto import CustomerMarketingProfileQueryDTO
    from .application.automation_engine.queries import GetCustomerMarketingProfileQuery

    return GetCustomerMarketingProfileQuery()(
        CustomerMarketingProfileQueryDTO(
            external_userid=str(external_userid or "").strip(),
            scenario_key=str(scenario_key or "").strip(),
            batch_context=dict(batch_context or {}) if batch_context else None,
        )
    )


def mark_enrolled(
    *,
    external_userid: str,
    owner_userid: str = "",
    operator: str = "",
    source: str = "manual",
    signup_status: str = marketing_automation_domain_service.DEFAULT_ENROLLED_SIGNUP_STATUS,
    automation_key: str = marketing_automation_domain_service.DEFAULT_SCENARIO_KEY,
) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 4 automation-engine command."""

    from .application.automation_engine.commands import MarkEnrolledCommand
    from .application.automation_engine.dto import MarkEnrolledCommandDTO

    return MarkEnrolledCommand()(
        MarkEnrolledCommandDTO(
            external_userid=str(external_userid or "").strip(),
            owner_userid=str(owner_userid or "").strip(),
            operator=str(operator or "").strip(),
            source=str(source or "").strip() or "manual",
            signup_status=str(signup_status or "").strip(),
            automation_key=str(automation_key or "").strip(),
        )
    )


def unmark_enrolled(
    *,
    external_userid: str,
    owner_userid: str = "",
    operator: str = "",
    source: str = "manual",
    restore_signup_status: str = "",
    automation_key: str = marketing_automation_domain_service.DEFAULT_SCENARIO_KEY,
) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 4 automation-engine command."""

    from .application.automation_engine.commands import UnmarkEnrolledCommand
    from .application.automation_engine.dto import UnmarkEnrolledCommandDTO

    return UnmarkEnrolledCommand()(
        UnmarkEnrolledCommandDTO(
            external_userid=str(external_userid or "").strip(),
            owner_userid=str(owner_userid or "").strip(),
            operator=str(operator or "").strip(),
            source=str(source or "").strip() or "manual",
            restore_signup_status=str(restore_signup_status or "").strip(),
            automation_key=str(automation_key or "").strip(),
        )
    )


def set_manual_followup_segment(
    *,
    external_userid: str,
    followup_segment: str,
    owner_userid: str = "",
    operator: str = "",
    source: str = "manual",
    automation_key: str = marketing_automation_domain_service.DEFAULT_SCENARIO_KEY,
) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 4 automation-engine command."""

    from .application.automation_engine.commands import SetManualFollowupSegmentCommand
    from .application.automation_engine.dto import ManualFollowupSegmentCommandDTO

    return SetManualFollowupSegmentCommand()(
        ManualFollowupSegmentCommandDTO(
            external_userid=str(external_userid or "").strip(),
            followup_segment=str(followup_segment or "").strip(),
            owner_userid=str(owner_userid or "").strip(),
            operator=str(operator or "").strip(),
            source=str(source or "").strip() or "manual",
            automation_key=str(automation_key or "").strip(),
        )
    )


def get_routing_config() -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 2 routing-config query."""

    from .application.routing_config.dto import GetRoutingRuleConfigQueryDTO
    from .application.routing_config.queries import GetRoutingRuleConfigQuery

    return GetRoutingRuleConfigQuery()(
        GetRoutingRuleConfigQueryDTO(
            active_only=True,
            signup_tag_rules=get_signup_tag_rules_config(),
        )
    )


def resolve_contact_routing_context(owner_userid: str, owner_role: str, signup_status: str) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 2 routing-config query."""

    from .application.routing_config.dto import ResolveContactRoutingContextQueryDTO
    from .application.routing_config.queries import ResolveContactRoutingContextQuery

    definition = get_signup_status_definition(signup_status)
    return ResolveContactRoutingContextQuery()(
        ResolveContactRoutingContextQueryDTO(
            owner_userid=str(owner_userid or "").strip(),
            owner_role=str(owner_role or "").strip(),
            signup_status=str(signup_status or "").strip(),
            routing_alias=str(definition.get("routing_alias") or "") if definition else "",
        )
    )


def get_owner_role(userid: str) -> dict[str, Any] | None:
    """Backward-compatible wrapper around the Wave 2 routing-config query."""

    from .application.routing_config.dto import GetOwnerRoleQueryDTO
    from .application.routing_config.queries import GetOwnerRoleQuery

    return GetOwnerRoleQuery()(GetOwnerRoleQueryDTO(userid=str(userid or "").strip()))


def list_owner_role_map(*, active_only: bool = False) -> list[dict[str, Any]]:
    """Backward-compatible wrapper around the Wave 2 routing-config query."""

    from .application.routing_config.dto import GetOwnerRoleMapQueryDTO
    from .application.routing_config.queries import GetOwnerRoleMapQuery

    return GetOwnerRoleMapQuery()(GetOwnerRoleMapQueryDTO(active_only=bool(active_only)))


def enrich_contact_context(contact: dict[str, Any]) -> dict[str, Any]:
    return contacts_domain_service.enrich_contact_context(
        contact,
        get_owner_role=get_owner_role,
        get_contact_tag_snapshots=get_contact_tag_snapshots,
        resolve_signup_status_from_tags=resolve_signup_status_from_tags,
        resolve_contact_routing_context=resolve_contact_routing_context,
    )


def get_contact_by_external_userid(external_userid: str, *, refresh_tags: bool = False) -> dict[str, Any] | None:
    return contacts_domain_service.get_contact_by_external_userid(
        external_userid,
        refresh_tags=refresh_tags,
        refresh_contact_tags_for_external_userid=refresh_contact_tags_for_external_userid,
        enrich_contact_context=enrich_contact_context,
    )


def get_primary_follow_user_userid(external_userid: str) -> str:
    """Backward-compatible wrapper around the Wave 2 identity query."""

    from .application.identity_contact.dto import GetPrimaryFollowUserUseridQueryDTO
    from .application.identity_contact.queries import GetPrimaryFollowUserUseridQuery

    return GetPrimaryFollowUserUseridQuery()(GetPrimaryFollowUserUseridQueryDTO(external_userid=external_userid))


def get_class_user_status_definition(signup_status: str) -> dict[str, Any] | None:
    """Backward-compatible wrapper around the Wave 2 class-user query."""

    from .application.class_user.dto import GetClassUserStatusDefinitionQueryDTO
    from .application.class_user.queries import GetClassUserStatusDefinitionQuery

    return GetClassUserStatusDefinitionQuery()(
        GetClassUserStatusDefinitionQueryDTO(signup_status=str(signup_status or "").strip())
    )


def get_class_user_status_current(external_userid: str) -> dict[str, Any] | None:
    """Backward-compatible wrapper around the Wave 2 class-user query."""

    from .application.class_user.dto import GetClassUserStatusCurrentQueryDTO
    from .application.class_user.queries import GetClassUserStatusCurrentQuery

    return GetClassUserStatusCurrentQuery()(
        GetClassUserStatusCurrentQueryDTO(external_userid=str(external_userid or "").strip())
    )


def get_class_user_snapshot(external_userid: str, owner_userid: str = "") -> dict[str, str]:
    """Backward-compatible wrapper around the Wave 2 class-user query."""

    from .application.class_user.dto import GetClassUserSnapshotQueryDTO
    from .application.class_user.queries import GetClassUserSnapshotQuery

    return GetClassUserSnapshotQuery()(
        GetClassUserSnapshotQueryDTO(
            external_userid=str(external_userid or "").strip(),
            owner_userid=str(owner_userid or "").strip(),
        )
    )


def list_class_user_status_history(limit: int = 100) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 2 class-user query."""

    from .application.class_user.dto import ListClassUserStatusHistoryQueryDTO
    from .application.class_user.queries import ListClassUserStatusHistoryQuery

    return ListClassUserStatusHistoryQuery()(ListClassUserStatusHistoryQueryDTO(limit=int(limit)))


def list_class_user_management_records(signup_status: str = "") -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 2 class-user query."""

    from .application.class_user.dto import ListClassUserManagementRecordsQueryDTO
    from .application.class_user.queries import ListClassUserManagementRecordsQuery

    return ListClassUserManagementRecordsQuery()(
        ListClassUserManagementRecordsQueryDTO(signup_status=str(signup_status or "").strip())
    )


def export_class_user_management_records(signup_status: str = "") -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 2 class-user query."""

    from .application.class_user.dto import ExportClassUserManagementRecordsQueryDTO
    from .application.class_user.queries import ExportClassUserManagementRecordsQuery

    return ExportClassUserManagementRecordsQuery()(
        ExportClassUserManagementRecordsQueryDTO(signup_status=str(signup_status or "").strip())
    )


def list_questionnaires(
    *,
    include_disabled: bool = False,
    include_stats: bool = True,
) -> list[dict[str, Any]]:
    """Backward-compatible wrapper around the Wave 3 questionnaire query."""

    from .application.questionnaire.dto import ListQuestionnairesQueryDTO
    from .application.questionnaire.queries import ListQuestionnairesQuery

    return ListQuestionnairesQuery()(
        ListQuestionnairesQueryDTO(
            include_disabled=bool(include_disabled),
            include_stats=bool(include_stats),
        )
    )


def list_available_wecom_tags() -> list[dict[str, Any]]:
    """Backward-compatible wrapper around the Wave 3 questionnaire query."""

    from .application.questionnaire.queries import ListAvailableWeComTagsQuery

    return ListAvailableWeComTagsQuery()()


def get_latest_questionnaire_submit_debug(questionnaire_id: int) -> dict[str, Any] | None:
    """Backward-compatible wrapper around the Wave 3 questionnaire query."""

    from .application.questionnaire.dto import GetLatestQuestionnaireSubmitDebugQueryDTO
    from .application.questionnaire.queries import GetLatestQuestionnaireSubmitDebugQuery

    return GetLatestQuestionnaireSubmitDebugQuery()(
        GetLatestQuestionnaireSubmitDebugQueryDTO(questionnaire_id=int(questionnaire_id))
    )


def create_questionnaire(payload: dict[str, Any]) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 3 questionnaire command."""

    from .application.questionnaire.commands import CreateQuestionnaireCommand
    from .application.questionnaire.dto import CreateQuestionnaireCommandDTO

    return CreateQuestionnaireCommand()(CreateQuestionnaireCommandDTO(payload=dict(payload or {})))


def get_questionnaire_detail(questionnaire_id: int) -> dict[str, Any] | None:
    """Backward-compatible wrapper around the Wave 3 questionnaire query."""

    from .application.questionnaire.dto import GetQuestionnaireDetailQueryDTO
    from .application.questionnaire.queries import GetQuestionnaireDetailQuery

    return GetQuestionnaireDetailQuery()(GetQuestionnaireDetailQueryDTO(questionnaire_id=int(questionnaire_id)))


def update_questionnaire(questionnaire_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Backward-compatible wrapper around the Wave 3 questionnaire command."""

    from .application.questionnaire.commands import UpdateQuestionnaireCommand
    from .application.questionnaire.dto import UpdateQuestionnaireCommandDTO

    return UpdateQuestionnaireCommand()(
        UpdateQuestionnaireCommandDTO(
            questionnaire_id=int(questionnaire_id),
            payload=dict(payload or {}),
        )
    )


def disable_questionnaire(questionnaire_id: int, is_disabled: bool = True) -> dict[str, Any] | None:
    """Backward-compatible wrapper around the Wave 3 questionnaire command."""

    from .application.questionnaire.commands import DisableQuestionnaireCommand
    from .application.questionnaire.dto import DisableQuestionnaireCommandDTO

    return DisableQuestionnaireCommand()(
        DisableQuestionnaireCommandDTO(
            questionnaire_id=int(questionnaire_id),
            is_disabled=bool(is_disabled),
        )
    )


def delete_questionnaire_submissions_by_slug(slug: str) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 3 questionnaire command."""

    from .application.questionnaire.commands import DeleteQuestionnaireSubmissionsBySlugCommand
    from .application.questionnaire.dto import DeleteQuestionnaireSubmissionsBySlugCommandDTO

    return DeleteQuestionnaireSubmissionsBySlugCommand()(
        DeleteQuestionnaireSubmissionsBySlugCommandDTO(slug=str(slug or "").strip())
    )


def delete_questionnaire(questionnaire_id: int) -> bool:
    """Backward-compatible wrapper around the Wave 3 questionnaire command."""

    from .application.questionnaire.commands import DeleteQuestionnaireCommand
    from .application.questionnaire.dto import DeleteQuestionnaireCommandDTO

    return DeleteQuestionnaireCommand()(DeleteQuestionnaireCommandDTO(questionnaire_id=int(questionnaire_id)))


def export_questionnaire_submissions(questionnaire_id: int) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 3 questionnaire query."""

    from .application.questionnaire.dto import ExportQuestionnaireSubmissionsQueryDTO
    from .application.questionnaire.queries import ExportQuestionnaireSubmissionsQuery

    return ExportQuestionnaireSubmissionsQuery()(
        ExportQuestionnaireSubmissionsQueryDTO(questionnaire_id=int(questionnaire_id))
    )


def get_public_questionnaire_by_slug(slug: str) -> dict[str, Any] | None:
    """Backward-compatible wrapper around the Wave 3 questionnaire query."""

    from .application.questionnaire.dto import GetPublicQuestionnaireBySlugQueryDTO
    from .application.questionnaire.queries import GetPublicQuestionnaireBySlugQuery

    return GetPublicQuestionnaireBySlugQuery()(GetPublicQuestionnaireBySlugQueryDTO(slug=str(slug or "").strip()))


def validate_questionnaire_answers(questionnaire: dict[str, Any], answers: Any) -> list[dict[str, Any]]:
    """Backward-compatible wrapper around the Wave 3 questionnaire query."""

    from .application.questionnaire.dto import ValidateQuestionnaireAnswersQueryDTO
    from .application.questionnaire.queries import ValidateQuestionnaireAnswersQuery

    return ValidateQuestionnaireAnswersQuery()(
        ValidateQuestionnaireAnswersQueryDTO(
            questionnaire=dict(questionnaire or {}),
            answers=answers,
        )
    )


def compute_questionnaire_submission_outcome(questionnaire: dict[str, Any], answers: Any) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 3 questionnaire query."""

    from .application.questionnaire.dto import ComputeQuestionnaireSubmissionOutcomeQueryDTO
    from .application.questionnaire.queries import ComputeQuestionnaireSubmissionOutcomeQuery

    return ComputeQuestionnaireSubmissionOutcomeQuery()(
        ComputeQuestionnaireSubmissionOutcomeQueryDTO(
            questionnaire=dict(questionnaire or {}),
            answers=answers,
        )
    )


def apply_class_user_status_change(
    *,
    external_userid: str,
    signup_status: str,
    set_by_userid: str,
    customer_name_snapshot: str,
    owner_userid_snapshot: str,
    mobile_snapshot: str,
) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 2 class-user command."""

    from .application.class_user.commands import ApplyClassUserStatusChangeCommand
    from .application.class_user.dto import ApplyClassUserStatusChangeCommandDTO

    return ApplyClassUserStatusChangeCommand()(
        ApplyClassUserStatusChangeCommandDTO(
            external_userid=str(external_userid or "").strip(),
            signup_status=str(signup_status or "").strip(),
            set_by_userid=str(set_by_userid or "").strip(),
            customer_name_snapshot=str(customer_name_snapshot or "").strip(),
            owner_userid_snapshot=str(owner_userid_snapshot or "").strip(),
            mobile_snapshot=str(mobile_snapshot or "").strip(),
        )
    )


def update_class_user_status_sync_result(
    external_userid: str,
    *,
    wecom_tag_sync_status: str,
    wecom_tag_sync_error: str = "",
) -> None:
    """Backward-compatible wrapper around the Wave 2 class-user command."""

    from .application.class_user.commands import UpdateClassUserStatusSyncResultCommand
    from .application.class_user.dto import UpdateClassUserStatusSyncResultCommandDTO

    return UpdateClassUserStatusSyncResultCommand()(
        UpdateClassUserStatusSyncResultCommandDTO(
            external_userid=str(external_userid or "").strip(),
            wecom_tag_sync_status=str(wecom_tag_sync_status or "").strip(),
            wecom_tag_sync_error=str(wecom_tag_sync_error or "").strip(),
        )
    )


def migrate_class_user_status_from_contact_tags() -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 2 class-user command."""

    from .application.class_user.commands import MigrateClassUserStatusFromContactTagsCommand

    return MigrateClassUserStatusFromContactTagsCommand()()


def upsert_class_user_status_current(**kwargs: Any) -> None:
    """Compatibility shim around the Wave 2 class-user write primitive.

    This symbol remains visible for legacy monkeypatch and DI paths, but it is a
    low-level primitive and must not be used as a new caller entrypoint.
    """

    from .application.class_user.commands import upsert_class_user_status_current_primitive

    return upsert_class_user_status_current_primitive(**kwargs)


def append_class_user_status_history(**kwargs: Any) -> None:
    """Compatibility shim around the Wave 2 class-user history primitive.

    This symbol remains visible for legacy monkeypatch and DI paths, but it is a
    low-level primitive and must not be used as a new caller entrypoint.
    """

    from .application.class_user.commands import append_class_user_status_history_primitive

    return append_class_user_status_history_primitive(**kwargs)


def resolve_person_identity(*, external_userid: str = "", mobile: str = "", unionid: str = "") -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 2 identity query."""

    from .application.identity_contact.dto import ResolvePersonIdentityQueryDTO
    from .application.identity_contact.queries import ResolvePersonIdentityQuery

    return ResolvePersonIdentityQuery()(
        ResolvePersonIdentityQueryDTO(
            external_userid=external_userid,
            mobile=mobile,
            unionid=unionid,
        )
    )


def _sidebar_contact_profile(external_userid: str, owner_userid: str = "") -> dict[str, str]:
    _bind_user_ops_domain()
    return user_ops_domain_service._sidebar_contact_profile(external_userid, owner_userid)


def _resolve_binding_owner_userid(external_userid: str, owner_userid: str = "") -> str:
    _bind_user_ops_domain()
    return user_ops_domain_service._resolve_binding_owner_userid(external_userid, owner_userid)


def get_contact_binding_status(external_userid: str, owner_userid: str = "") -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 2 identity query."""

    from .application.identity_contact.dto import GetContactBindingStatusQueryDTO
    from .application.identity_contact.queries import GetContactBindingStatusQuery

    return GetContactBindingStatusQuery()(
        GetContactBindingStatusQueryDTO(
            external_userid=external_userid,
            owner_userid=owner_userid,
        )
    )


def _resolve_third_party_user_id_by_mobile(mobile: str) -> str:
    # Historical monkeypatch / DI hook. The stable Wave 2 anchor now lives in
    # infra.user_ops_runtime; keep this wrapper for backward compatibility.
    return user_ops_runtime.resolve_third_party_user_id_by_mobile(mobile)


def _select_user_ops_lead_pool_member_for_sidebar(
    *,
    external_userid: str,
    mobile: str = "",
    owner_userid: str = "",
) -> dict[str, Any] | None:
    _bind_user_ops_domain()
    return user_ops_domain_service._select_user_ops_lead_pool_member_for_sidebar(
        external_userid=external_userid,
        mobile=mobile,
        owner_userid=owner_userid,
    )


def get_sidebar_lead_pool_status(*, external_userid: str, owner_userid: str = "") -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 2 sidebar lead-pool query."""

    from .application.user_ops.queries import (
        GetSidebarLeadPoolStatusQuery,
        GetSidebarLeadPoolStatusQueryDTO,
    )

    return GetSidebarLeadPoolStatusQuery()(
        GetSidebarLeadPoolStatusQueryDTO(
            external_userid=external_userid,
            owner_userid=owner_userid,
        )
    )


def upsert_sidebar_lead_pool_class_term(
    *,
    external_userid: str,
    owner_userid: str = "",
    class_term_no: int,
    operator: str = "",
) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 2 sidebar lead-pool write command."""

    from .application.user_ops.commands import (
        UpsertSidebarLeadPoolClassTermCommand,
        UpsertSidebarLeadPoolClassTermCommandDTO,
    )

    return UpsertSidebarLeadPoolClassTermCommand()(
        UpsertSidebarLeadPoolClassTermCommandDTO(
            external_userid=external_userid,
            owner_userid=owner_userid,
            class_term_no=class_term_no,
            operator=operator,
        )
    )


def _merge_lead_pool_after_mobile_bind(
    *,
    external_userid: str,
    owner_userid: str,
    mobile: str,
    operator: str = "",
) -> dict[str, Any]:
    _bind_user_ops_domain()
    return user_ops_domain_service._merge_lead_pool_after_mobile_bind(
        external_userid=external_userid,
        owner_userid=owner_userid,
        mobile=mobile,
        operator=operator,
    )


def bind_mobile_to_external_contact(
    *,
    external_userid: str,
    owner_userid: str,
    bind_by_userid: str,
    mobile: str,
    force_rebind: bool = False,
) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 2 identity command."""

    from .application.identity_contact.commands import BindExternalContactIdentityCommand
    from .application.identity_contact.dto import BindExternalContactIdentityCommandDTO

    return BindExternalContactIdentityCommand()(
        BindExternalContactIdentityCommandDTO(
            external_userid=external_userid,
            owner_userid=owner_userid,
            bind_by_userid=bind_by_userid,
            mobile=mobile,
            force_rebind=force_rebind,
        )
    )


def bind_openid_to_external_contact(
    corp_id: str,
    external_userid: str,
    openid: str,
    unionid: str = "",
) -> dict[str, Any] | None:
    """Backward-compatible wrapper around the Wave 2 identity command."""

    from .application.identity_contact.commands import BindExternalContactIdentityCommand
    from .application.identity_contact.dto import BindExternalContactIdentityCommandDTO

    return BindExternalContactIdentityCommand()(
        BindExternalContactIdentityCommandDTO(
            corp_id=corp_id,
            external_userid=external_userid,
            openid=openid,
            unionid=unionid,
        )
    )


def resolve_external_contact_identity(
    corp_id: str,
    *,
    unionid: str = "",
    openid: str = "",
    external_userid: str = "",
) -> dict[str, Any] | None:
    """Backward-compatible wrapper around the Wave 2 identity query."""

    from .application.identity_contact.dto import ResolveExternalContactIdentityQueryDTO
    from .application.identity_contact.queries import (
        ResolveExternalContactIdentityQuery,
    )

    return ResolveExternalContactIdentityQuery()(
        ResolveExternalContactIdentityQueryDTO(
            corp_id=corp_id,
            unionid=unionid,
            openid=openid,
            external_userid=external_userid,
        )
    )


def upsert_external_contact_identity(record: dict[str, object]) -> int:
    """Backward-compatible wrapper around the Wave 2 identity command."""

    from .application.identity_contact.commands import (
        UpsertExternalContactIdentityCommand,
    )
    from .application.identity_contact.dto import UpsertExternalContactIdentityCommandDTO

    return UpsertExternalContactIdentityCommand()(UpsertExternalContactIdentityCommandDTO(record=dict(record or {})))


def replace_external_contact_follow_users(
    corp_id: str,
    external_userid: str,
    follow_users: list[dict[str, object]],
    *,
    preferred_userid: str = "",
) -> None:
    """Backward-compatible wrapper around the Wave 2 identity command."""

    from .application.identity_contact.commands import ReplaceFollowUsersCommand
    from .application.identity_contact.dto import ReplaceFollowUsersCommandDTO

    return ReplaceFollowUsersCommand()(
        ReplaceFollowUsersCommandDTO(
            corp_id=corp_id,
            external_userid=external_userid,
            follow_users=list(follow_users or []),
            preferred_userid=preferred_userid,
        )
    )


def refresh_external_contact_identity_owner(corp_id: str, external_userid: str) -> None:
    """Backward-compatible wrapper around the Wave 2 identity command."""

    from .application.identity_contact.commands import (
        RefreshExternalContactIdentityOwnerCommand,
    )
    from .application.identity_contact.dto import RefreshExternalContactIdentityOwnerCommandDTO

    return RefreshExternalContactIdentityOwnerCommand()(
        RefreshExternalContactIdentityOwnerCommandDTO(
            corp_id=corp_id,
            external_userid=external_userid,
        )
    )


def mark_external_contact_follow_user_status(
    corp_id: str,
    external_userid: str,
    *,
    user_id: str = "",
    status: str,
) -> None:
    """Backward-compatible wrapper around the Wave 2 identity command."""

    from .application.identity_contact.commands import (
        MarkExternalContactFollowUserStatusCommand,
    )
    from .application.identity_contact.dto import MarkExternalContactFollowUserStatusCommandDTO

    return MarkExternalContactFollowUserStatusCommand()(
        MarkExternalContactFollowUserStatusCommandDTO(
            corp_id=corp_id,
            external_userid=external_userid,
            user_id=user_id,
            status=status,
        )
    )


def mark_external_contact_identity_status(
    corp_id: str,
    external_userid: str,
    *,
    status: str,
    follow_user_userid: str = "",
) -> None:
    """Backward-compatible wrapper around the Wave 2 identity command."""

    from .application.identity_contact.commands import (
        MarkExternalContactIdentityStatusCommand,
    )
    from .application.identity_contact.dto import MarkExternalContactIdentityStatusCommandDTO

    return MarkExternalContactIdentityStatusCommand()(
        MarkExternalContactIdentityStatusCommandDTO(
            corp_id=corp_id,
            external_userid=external_userid,
            status=status,
            follow_user_userid=follow_user_userid,
        )
    )


def count_external_contact_identity_maps() -> int:
    """Backward-compatible wrapper around the Wave 2 identity query."""

    from .application.identity_contact.queries import CountExternalContactIdentityMapsQuery

    return CountExternalContactIdentityMapsQuery()()


def sync_user_ops_class_term_tag_definitions() -> dict[str, Any]:
    _bind_user_ops_domain()
    return user_ops_domain_service.sync_user_ops_class_term_tag_definitions()


def reload_user_ops_pool() -> dict[str, Any]:
    _bind_user_ops_domain()
    return user_ops_domain_service.reload_user_ops_pool()


def refresh_contact_tags_for_external_userid(
    *,
    external_userid: str,
    owner_userid: str = "",
    scoped_tag_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 2 user-ops maintenance command.

    Compatibility note: this keeps the legacy "full refresh when scoped_tag_ids is None"
    contract, but the formal owner now lives under ``application.user_ops``.
    """

    from .application.user_ops.commands import (
        RefreshContactTagsForExternalUseridCommand,
        RefreshContactTagsForExternalUseridCommandDTO,
    )

    return RefreshContactTagsForExternalUseridCommand()(
        RefreshContactTagsForExternalUseridCommandDTO(
            external_userid=external_userid,
            owner_userid=owner_userid,
            scoped_tag_ids=None if scoped_tag_ids is None else list(scoped_tag_ids),
        )
    )


def refresh_user_ops_contact_tags_for_external_userid(
    *,
    external_userid: str,
    owner_userid: str = "",
) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 2 user-ops maintenance command."""

    from .application.user_ops.commands import RefreshUserOpsContactTagsCommand
    from .application.user_ops.dto import RefreshUserOpsContactTagsCommandDTO

    return RefreshUserOpsContactTagsCommand()(
        RefreshUserOpsContactTagsCommandDTO(
            external_userid=external_userid,
            owner_userid=owner_userid,
            refresh_scope="external_userid",
        )
    )


def refresh_user_ops_contact_tags_for_owner(owner_userid: str) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 2 user-ops maintenance command."""

    from .application.user_ops.commands import RefreshUserOpsContactTagsCommand
    from .application.user_ops.dto import RefreshUserOpsContactTagsCommandDTO

    return RefreshUserOpsContactTagsCommand()(
        RefreshUserOpsContactTagsCommandDTO(
            owner_userid=owner_userid,
            refresh_scope="owner",
        )
    )


def backfill_owner_class_terms_into_lead_pool(
    *,
    owner_userid: str,
    class_term_min: int = 1,
    class_term_max: int = 5,
    dry_run: bool = True,
    operator: str = "",
    entry_source: str = "",
) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 2 owner-backfill command."""

    from .application.user_ops.commands import BackfillOwnerClassTermsCommand
    from .application.user_ops.dto import BackfillOwnerClassTermsCommandDTO

    return BackfillOwnerClassTermsCommand()(
        BackfillOwnerClassTermsCommandDTO(
            owner_userid=owner_userid,
            class_term_min=class_term_min,
            class_term_max=class_term_max,
            dry_run=dry_run,
            operator=operator,
            entry_source=entry_source,
        )
    )


def backfill_class_term_for_owner(owner_userid: str, *, operator: str = "") -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 2 legacy owner-backfill compatibility command."""

    from .application.user_ops.commands import (
        BackfillClassTermForOwnerCommand,
        BackfillClassTermForOwnerCommandDTO,
    )

    return BackfillClassTermForOwnerCommand()(
        BackfillClassTermForOwnerCommandDTO(
            owner_userid=owner_userid,
            operator=operator,
        )
    )


def _default_owner_class_term_backfill_entry_source(owner_userid: str) -> str:
    _bind_user_ops_domain()
    return user_ops_domain_service._default_owner_class_term_backfill_entry_source(owner_userid)


def schedule_user_ops_auto_assign_class_term_job(
    *,
    external_userid: str,
    owner_userid: str,
    delay_seconds: int | None = None,
    run_after_seconds: int = 10,
    operator: str = "",
) -> dict[str, Any]:
    from .application.user_ops.commands import ScheduleUserOpsAutoAssignClassTermJobCommand
    from .application.user_ops.dto import ScheduleUserOpsAutoAssignClassTermJobCommandDTO

    return ScheduleUserOpsAutoAssignClassTermJobCommand()(
        ScheduleUserOpsAutoAssignClassTermJobCommandDTO(
            external_userid=external_userid,
            owner_userid=owner_userid,
            delay_seconds=delay_seconds,
            run_after_seconds=run_after_seconds,
            operator=operator,
        )
    )


def run_due_user_ops_deferred_jobs(limit: int = 20) -> dict[str, Any]:
    from .application.user_ops.commands import RunDueUserOpsDeferredJobsCommand
    from .application.user_ops.dto import RunDueUserOpsDeferredJobsCommandDTO

    return RunDueUserOpsDeferredJobsCommand()(RunDueUserOpsDeferredJobsCommandDTO(limit=limit))


def list_user_ops_pool(
    *,
    wecom_status: str = "",
    mobile_binding_status: str = "",
    activation_bucket: str = "",
    is_wecom_added: str = "",
    is_mobile_bound: str = "",
    huangxiaocan_activation_state: str = "",
    class_term_no: str = "",
    keyword: str = "",
    mobile: str = "",
    owner_userid: str = "",
    query: str = "",
) -> dict[str, Any]:
    from .application.user_ops.dto import LeadPoolFiltersDTO, ListLeadPoolQueryDTO
    from .application.user_ops.queries import ListLeadPoolQuery

    return ListLeadPoolQuery()(
        ListLeadPoolQueryDTO(
            filters=LeadPoolFiltersDTO(
                wecom_status=wecom_status,
                mobile_binding_status=mobile_binding_status,
                activation_bucket=activation_bucket,
                is_wecom_added=is_wecom_added,
                is_mobile_bound=is_mobile_bound,
                huangxiaocan_activation_state=huangxiaocan_activation_state,
                class_term_no=class_term_no,
                keyword=keyword,
                mobile=mobile,
                owner_userid=owner_userid,
                query=query,
            )
        )
    )


def get_user_ops_overview(
    *,
    wecom_status: str = "",
    mobile_binding_status: str = "",
    activation_bucket: str = "",
    is_wecom_added: str = "",
    is_mobile_bound: str = "",
    huangxiaocan_activation_state: str = "",
    class_term_no: str = "",
    keyword: str = "",
    mobile: str = "",
    owner_userid: str = "",
    query: str = "",
) -> dict[str, Any]:
    from .application.user_ops.dto import GetUserOpsOverviewQueryDTO, LeadPoolFiltersDTO
    from .application.user_ops.queries import GetUserOpsOverviewQuery

    return GetUserOpsOverviewQuery()(
        GetUserOpsOverviewQueryDTO(
            filters=LeadPoolFiltersDTO(
                wecom_status=wecom_status,
                mobile_binding_status=mobile_binding_status,
                activation_bucket=activation_bucket,
                is_wecom_added=is_wecom_added,
                is_mobile_bound=is_mobile_bound,
                huangxiaocan_activation_state=huangxiaocan_activation_state,
                class_term_no=class_term_no,
                keyword=keyword,
                mobile=mobile,
                owner_userid=owner_userid,
                query=query,
            )
        )
    )


def list_user_ops_history(limit: int = 100) -> dict[str, Any]:
    from .application.user_ops.dto import ListUserOpsHistoryQueryDTO
    from .application.user_ops.queries import ListUserOpsHistoryQuery

    return ListUserOpsHistoryQuery()(ListUserOpsHistoryQueryDTO(limit=limit))


def export_user_ops_pool(
    *,
    wecom_status: str = "",
    mobile_binding_status: str = "",
    activation_bucket: str = "",
    is_wecom_added: str = "",
    is_mobile_bound: str = "",
    huangxiaocan_activation_state: str = "",
    class_term_no: str = "",
    keyword: str = "",
    mobile: str = "",
    owner_userid: str = "",
    query: str = "",
) -> dict[str, Any]:
    from .application.user_ops.dto import ExportUserOpsPoolQueryDTO, LeadPoolFiltersDTO
    from .application.user_ops.queries import ExportUserOpsPoolQuery

    return ExportUserOpsPoolQuery()(
        ExportUserOpsPoolQueryDTO(
            filters=LeadPoolFiltersDTO(
                wecom_status=wecom_status,
                mobile_binding_status=mobile_binding_status,
                activation_bucket=activation_bucket,
                is_wecom_added=is_wecom_added,
                is_mobile_bound=is_mobile_bound,
                huangxiaocan_activation_state=huangxiaocan_activation_state,
                class_term_no=class_term_no,
                keyword=keyword,
                mobile=mobile,
                owner_userid=owner_userid,
                query=query,
            )
        )
    )


def set_user_ops_do_not_disturb(payload: dict[str, Any]) -> dict[str, Any]:
    return user_ops_page_service.set_user_ops_do_not_disturb(payload)


def preview_user_ops_batch_send(payload: dict[str, Any]) -> dict[str, Any]:
    return user_ops_page_service.preview_user_ops_batch_send(payload)


def execute_user_ops_batch_send(payload: dict[str, Any]) -> dict[str, Any]:
    return user_ops_page_service.execute_user_ops_batch_send(payload)


def list_user_ops_send_records(*, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    return user_ops_page_service.list_user_ops_send_records(limit=limit, offset=offset)


def get_user_ops_send_record_detail(record_id: int) -> dict[str, Any]:
    return user_ops_page_service.get_user_ops_send_record_detail(record_id)


def refresh_user_ops_send_record_status(record_id: int) -> dict[str, Any]:
    return user_ops_page_service.refresh_user_ops_send_record_status(record_id)


def write_user_ops_lead_pool_history(
    *,
    mobile: str,
    external_userid: str,
    action_type: str,
    source_type: str,
    operator: str,
    before_payload: dict[str, Any] | None,
    after_payload: dict[str, Any] | None,
    remark: str = "",
) -> None:
    """Internal primitive compatibility shim.

    This symbol remains visible for legacy monkeypatch and compatibility paths,
    but new caller-layer code must not use it as a primary write entry.
    """

    from .application.user_ops.commands import WriteLeadPoolHistoryCommand
    from .application.user_ops.dto import WriteLeadPoolHistoryCommandDTO

    return WriteLeadPoolHistoryCommand()(
        WriteLeadPoolHistoryCommandDTO(
            mobile=mobile,
            external_userid=external_userid,
            action_type=action_type,
            source_type=source_type,
            operator=operator,
            before_payload=before_payload,
            after_payload=after_payload,
            remark=remark,
        )
    )


def upsert_user_ops_lead_pool_member(**kwargs: Any) -> dict[str, Any]:
    """Internal primitive compatibility shim.

    This symbol remains visible for legacy monkeypatch and compatibility paths,
    but new caller-layer code must not use it as a primary write entry.
    """

    from .application.user_ops.commands import UpsertLeadPoolMemberCommand
    from .application.user_ops.dto import UpsertLeadPoolMemberCommandDTO

    return UpsertLeadPoolMemberCommand()(UpsertLeadPoolMemberCommandDTO(**kwargs))


def upsert_user_ops_huangxiaocan_activation_source(
    *,
    mobile: str,
    activation_state: str,
    activation_remark: str = "",
    is_active: bool = True,
    created_by: str = "",
    import_batch_id: int | None = None,
) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 2 activation-source maintenance command.

    Compatibility note: ``activation_remark`` remains in the public shim
    signature for old callers even though the legacy domain write API does not
    currently persist that field.
    """

    from .application.user_ops.commands import (
        UpsertUserOpsHuangxiaocanActivationSourceCommand,
        UpsertUserOpsHuangxiaocanActivationSourceCommandDTO,
    )

    return UpsertUserOpsHuangxiaocanActivationSourceCommand()(
        UpsertUserOpsHuangxiaocanActivationSourceCommandDTO(
            mobile=mobile,
            activation_state=activation_state,
            activation_remark=activation_remark,
            import_batch_id=import_batch_id,
            created_by=created_by,
            is_active=is_active,
        )
    )


def import_experience_leads(
    *,
    pasted_text: str = "",
    file_name: str = "",
    file_bytes: bytes | None = None,
    created_by: str = "",
) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 2 import command."""

    from .application.user_ops.commands import ImportExperienceLeadsCommand
    from .application.user_ops.dto import ImportExperienceLeadsCommandDTO

    return ImportExperienceLeadsCommand()(
        ImportExperienceLeadsCommandDTO(
            pasted_text=pasted_text,
            file_name=file_name,
            file_bytes=file_bytes,
            created_by=created_by,
        )
    )


def import_mobile_class_term_source(
    *,
    pasted_text: str = "",
    file_name: str = "",
    file_bytes: bytes | None = None,
    created_by: str = "",
) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 2 import command."""

    from .application.user_ops.commands import ImportMobileClassTermCommand
    from .application.user_ops.dto import ImportMobileClassTermCommandDTO

    return ImportMobileClassTermCommand()(
        ImportMobileClassTermCommandDTO(
            pasted_text=pasted_text,
            file_name=file_name,
            file_bytes=file_bytes,
            created_by=created_by,
        )
    )


def import_activation_status_source(
    *,
    pasted_text: str = "",
    file_name: str = "",
    file_bytes: bytes | None = None,
    created_by: str = "",
) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 2 import command."""

    from .application.user_ops.commands import ImportActivationStatusCommand
    from .application.user_ops.dto import ImportActivationStatusCommandDTO

    return ImportActivationStatusCommand()(
        ImportActivationStatusCommandDTO(
            pasted_text=pasted_text,
            file_name=file_name,
            file_bytes=file_bytes,
            created_by=created_by,
        )
    )


def migrate_legacy_user_ops_pool_to_lead_pool(*, operator: str = "") -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 2 legacy-pool migration command."""

    from .application.user_ops.commands import (
        MigrateLegacyUserOpsPoolToLeadPoolCommand,
        MigrateLegacyUserOpsPoolToLeadPoolCommandDTO,
    )

    return MigrateLegacyUserOpsPoolToLeadPoolCommand()(
        MigrateLegacyUserOpsPoolToLeadPoolCommandDTO(operator=operator)
    )


def _list_class_term_matches_for_external_contact(external_userid: str, owner_userid: str = "") -> dict[str, Any]:
    _bind_user_ops_domain()
    return user_ops_domain_service._list_class_term_matches_for_external_contact(external_userid, owner_userid)


def _sync_sidebar_lead_pool_class_term_tag(
    *,
    external_userid: str,
    owner_userid: str,
    class_term_no: int,
) -> dict[str, Any]:
    _bind_user_ops_domain()
    return user_ops_domain_service._sync_sidebar_lead_pool_class_term_tag(
        external_userid=external_userid,
        owner_userid=owner_userid,
        class_term_no=class_term_no,
    )


def _list_other_ownerids_with_scoped_tag_snapshots(
    external_userid: str,
    owner_userid: str,
    scoped_tag_ids: list[str],
) -> list[str]:
    return user_ops_domain_service._list_other_ownerids_with_scoped_tag_snapshots(
        external_userid,
        owner_userid,
        scoped_tag_ids,
    )


def get_messages_by_user(external_userid: str, chat_type: str | None = None) -> list[dict[str, Any]]:
    return archive_domain_service.get_messages_by_user(
        external_userid,
        chat_type,
        group_chat_map_loader=get_group_chat_map,
    )


def get_recent_messages_by_user(external_userid: str, limit: int = 20, chat_type: str | None = None) -> list[dict[str, Any]]:
    return archive_domain_service.get_recent_messages_by_user(
        external_userid,
        limit=limit,
        chat_type=chat_type,
        group_chat_map_loader=get_group_chat_map,
    )


def search_messages(external_userid: str, keyword: str) -> list[dict[str, Any]]:
    return archive_domain_service.search_messages(
        external_userid,
        keyword,
        group_chat_map_loader=get_group_chat_map,
    )


def get_message_batch(batch_id: int, *, limit: int = 200, cursor: str = "") -> dict[str, Any] | None:
    return archive_domain_service.get_message_batch(
        batch_id,
        limit=limit,
        cursor=cursor,
        group_chat_map_loader=get_group_chat_map,
    )


def resolve_questionnaire_submit_identity(
    openid: str = "",
    unionid: str = "",
    external_userid: str = "",
) -> dict[str, Any] | None:
    """Backward-compatible wrapper around the Wave 3 questionnaire query."""

    from .application.questionnaire.dto import ResolveQuestionnaireSubmitIdentityQueryDTO
    from .application.questionnaire.queries import ResolveQuestionnaireSubmitIdentityQuery

    return ResolveQuestionnaireSubmitIdentityQuery()(
        ResolveQuestionnaireSubmitIdentityQueryDTO(
            openid=str(openid or "").strip(),
            unionid=str(unionid or "").strip(),
            external_userid=str(external_userid or "").strip(),
        )
    )


def has_questionnaire_submission(questionnaire_id: int, identity: dict[str, Any] | None) -> bool:
    """Backward-compatible wrapper around the Wave 3 questionnaire query."""

    from .application.questionnaire.dto import HasQuestionnaireSubmissionQueryDTO
    from .application.questionnaire.queries import HasQuestionnaireSubmissionQuery

    return HasQuestionnaireSubmissionQuery()(
        HasQuestionnaireSubmissionQueryDTO(
            questionnaire_id=int(questionnaire_id),
            identity=dict(identity or {}) if identity else None,
        )
    )


def save_questionnaire_submission(
    questionnaire: dict[str, Any],
    identity: dict[str, Any] | None,
    computed_result: dict[str, Any],
    answers: Any,
    request_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 3 questionnaire command."""

    from .application.questionnaire.commands import SaveQuestionnaireSubmissionCommand
    from .application.questionnaire.dto import SaveQuestionnaireSubmissionCommandDTO

    return SaveQuestionnaireSubmissionCommand()(
        SaveQuestionnaireSubmissionCommandDTO(
            questionnaire=dict(questionnaire or {}),
            identity=dict(identity or {}) if identity else None,
            computed_result=dict(computed_result or {}),
            answers=answers,
            request_meta=dict(request_meta or {}) if request_meta else None,
        )
    )


def apply_questionnaire_mobile_binding(submission: dict[str, Any]) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 3 questionnaire command."""

    from .application.questionnaire.commands import ApplyQuestionnaireMobileBindingCommand
    from .application.questionnaire.dto import ApplyQuestionnaireMobileBindingCommandDTO

    submission_snapshot = dict(submission or {})
    return ApplyQuestionnaireMobileBindingCommand()(
        ApplyQuestionnaireMobileBindingCommandDTO(
            submission_id=int(submission_snapshot.get("id") or 0),
            submission_snapshot=submission_snapshot,
        )
    )


def apply_questionnaire_submission_tags_to_scrm(submission_id: int) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 3 questionnaire command."""

    from .application.questionnaire.commands import ApplyQuestionnaireSubmissionTagsCommand
    from .application.questionnaire.dto import ApplyQuestionnaireSubmissionTagsCommandDTO

    return ApplyQuestionnaireSubmissionTagsCommand()(
        ApplyQuestionnaireSubmissionTagsCommandDTO(submission_id=int(submission_id))
    )


def apply_questionnaire_result_to_scrm(submission_id: int) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 3 questionnaire command."""

    from .application.questionnaire.commands import ApplyQuestionnaireResultToScrmCommand
    from .application.questionnaire.dto import ApplyQuestionnaireResultToScrmCommandDTO

    return ApplyQuestionnaireResultToScrmCommand()(
        ApplyQuestionnaireResultToScrmCommandDTO(submission_id=int(submission_id))
    )


def submit_questionnaire(slug: str, payload: dict[str, Any], request_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 3 questionnaire command."""

    from .application.questionnaire.commands import SubmitQuestionnaireCommand
    from .application.questionnaire.dto import SubmitQuestionnaireCommandDTO

    return SubmitQuestionnaireCommand()(
        SubmitQuestionnaireCommandDTO(
            slug=str(slug or "").strip(),
            payload=dict(payload or {}),
            request_meta=dict(request_meta or {}) if request_meta else None,
        )
    )


def retry_questionnaire_external_push_log(push_log_id: int) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 3 questionnaire command."""

    from .application.questionnaire.commands import RetryQuestionnaireExternalPushLogCommand
    from .application.questionnaire.dto import RetryQuestionnaireExternalPushLogCommandDTO

    return RetryQuestionnaireExternalPushLogCommand()(
        RetryQuestionnaireExternalPushLogCommandDTO(push_log_id=int(push_log_id))
    )


def retry_questionnaire_external_push_logs(push_log_ids: list[int]) -> dict[str, Any]:
    """Backward-compatible wrapper around the Wave 3 questionnaire command."""

    from .application.questionnaire.commands import RetryQuestionnaireExternalPushLogsCommand
    from .application.questionnaire.dto import RetryQuestionnaireExternalPushLogsCommandDTO

    return RetryQuestionnaireExternalPushLogsCommand()(
        RetryQuestionnaireExternalPushLogsCommandDTO(push_log_ids=list(push_log_ids or []))
    )
