from __future__ import annotations
from .automation_conversion_delivery import (
    api_admin_automation_conversion_focus_send_batch_detail,
    api_admin_automation_conversion_focus_send_batch_run_due,
    api_admin_automation_conversion_sop_config_list,
    api_admin_automation_conversion_sop_config_save,
    api_admin_automation_conversion_sop_run_due,
    api_admin_automation_conversion_sop_template_delete,
    api_admin_automation_conversion_sop_template_save,
    api_admin_automation_conversion_sop_templates,
)
from .automation_conversion_agent_api import (
    api_admin_automation_conversion_agent_create,
    api_admin_automation_conversion_agent_delete,
    api_admin_automation_conversion_agent_detail,
    api_admin_automation_conversion_agent_draft,
    api_admin_automation_conversion_agent_options,
    api_admin_automation_conversion_agent_output_detail,
    api_admin_automation_conversion_agent_outputs,
    api_admin_automation_conversion_agent_outputs_export,
    api_admin_automation_conversion_agent_outputs_export_detail,
    api_admin_automation_conversion_agent_publish,
    api_admin_automation_conversion_agent_replay,
    api_admin_automation_conversion_agent_run_detail,
    api_admin_automation_conversion_pending_publish,
)
from .automation_conversion_router_callback_api import (
    api_admin_automation_conversion_router_callback_replay,
    api_admin_automation_conversion_router_pending_callback_check,
    api_admin_automation_conversion_router_pending_callbacks,
)
from .automation_conversion_member_api import (
    api_admin_automation_conversion_focus_send_batch_create,
    api_admin_automation_conversion_mark_won,
    api_admin_automation_conversion_member,
    api_admin_automation_conversion_push_openclaw,
    api_admin_automation_conversion_put_in_pool,
    api_admin_automation_conversion_remove_from_pool,
    api_admin_automation_conversion_set_focus,
    api_admin_automation_conversion_set_normal,
    api_admin_automation_conversion_stage_manual_send,
    api_admin_automation_conversion_stage_manual_send_preview,
    api_admin_automation_conversion_unmark_won,
)
from .automation_conversion_pages import (
    admin_automation_conversion,
    admin_automation_conversion_auto_reply,
    admin_automation_conversion_runtime,
    admin_automation_conversion_runtime_debug,
    admin_automation_conversion_runtime_logs,
    admin_automation_conversion_runtime_router,
    admin_automation_conversion_runtime_sync,
    admin_automation_conversion_shared_agents,
    admin_automation_conversion_shared_model_infra,
    admin_automation_conversion_shared_profile_segments,
    admin_automation_program_activate,
    admin_automation_program_archive,
    admin_automation_program_copy,
    admin_automation_program_create,
    admin_automation_program_executions,
    admin_automation_program_entry_channels,
    admin_automation_program_flow_design,
    admin_automation_program_member_ops,
    admin_automation_program_new,
    admin_automation_program_operations,
    admin_automation_program_overview,
    admin_automation_program_pause,
    admin_automation_program_setup,
    admin_automation_program_update,
    admin_automation_program_workflow_edit,
    admin_automation_program_workflow_new,
    admin_automation_program_workflow_nodes,
    admin_automation_program_workflows,
    admin_channel_edit_page,
    admin_channel_new_page,
    admin_channels_page,
)
from .automation_conversion_agent_page_actions import (
    admin_automation_conversion_agent_orchestration_replay,
    admin_automation_conversion_agent_orchestration_review_output,
    admin_automation_conversion_agent_orchestration_save_draft,
)
from .automation_conversion_auto_reply_actions import (
    admin_automation_auto_reply_monitor_capture,
    admin_automation_auto_reply_monitor_run_due,
    admin_automation_auto_reply_monitor_toggle,
)
from .automation_conversion_channels import register_routes as register_channel_admission_routes
from .automation_conversion_page_actions import (
    admin_automation_conversion_generate_default_channel,
    admin_automation_conversion_save_settings,
    admin_automation_program_member_ops_stage_send,
    admin_automation_program_overview_message_activity_sync_run,
    admin_automation_program_overview_signup_tag_apply,
)
from .automation_conversion_operation_tasks import (
    api_admin_automation_conversion_task_activate,
    api_admin_automation_conversion_task_copy,
    api_admin_automation_conversion_task_delete,
    api_admin_automation_conversion_task_detail,
    api_admin_automation_conversion_task_group_delete,
    api_admin_automation_conversion_task_group_update,
    api_admin_automation_conversion_task_groups,
    api_admin_automation_conversion_task_pause,
    api_admin_automation_conversion_task_preview_audience,
    api_admin_automation_conversion_tasks,
    api_admin_automation_conversion_tasks_run_due,
)
from .automation_conversion_segments import (
    api_admin_automation_program_member_segment_broadcast,
    api_admin_automation_program_member_segment_search,
)
from .automation_conversion_review import (
    api_admin_automation_conversion_review_output,
    api_admin_automation_conversion_review_output_send_via_bazhuayu,
    api_admin_automation_conversion_review_output_send_via_webhook,
    api_admin_automation_conversion_review_output_send_via_wecom,
    api_admin_automation_conversion_review_outputs,
)
from .automation_conversion_runtime_api import (
    api_admin_automation_conversion_jobs_run_due,
    api_admin_automation_conversion_reply_monitor_capture,
    api_admin_automation_conversion_reply_monitor_run_due,
    api_admin_automation_conversion_run_message_activity_sync,
    api_internal_automation_conversion_laohuang_chat_results,
    api_internal_automation_conversion_lobster_results,
    api_internal_automation_conversion_router_test_dispatch,
)
from .automation_conversion_settings import (
    api_admin_automation_conversion_default_channel_generate_qr,
    api_admin_automation_conversion_default_channel_settings,
    api_admin_automation_conversion_default_channel_settings_save,
    api_admin_automation_conversion_model_settings,
    api_admin_automation_conversion_model_settings_save,
    api_admin_automation_conversion_model_settings_test,
    api_admin_automation_conversion_settings_default_channel_generate_qr,
    api_admin_automation_conversion_settings_payload,
    api_admin_automation_conversion_settings_save,
)
from .automation_conversion_setup import (
    api_admin_automation_program_customer_acquisition_links,
    api_admin_automation_program_publish_entry,
    api_admin_automation_program_publish_full,
    api_admin_automation_program_setup,
    api_admin_automation_program_setup_audience_entry_rule,
    api_admin_automation_program_setup_basic,
    api_admin_automation_program_setup_entry_channel,
    api_admin_automation_program_setup_publish_check,
    api_admin_automation_program_setup_segmentation,
)
from .automation_conversion_templates import (
    api_admin_automation_conversion_action_template_from_workflow,
    api_admin_automation_conversion_action_template_generate,
    api_admin_automation_conversion_action_templates,
    api_admin_automation_conversion_profile_segment_catalog,
    api_admin_automation_conversion_profile_segment_template_create,
    api_admin_automation_conversion_profile_segment_template_detail,
    api_admin_automation_conversion_profile_segment_template_options,
    api_admin_automation_conversion_profile_segment_template_update,
    api_admin_automation_conversion_profile_segment_templates,
    api_admin_automation_program_action_from_template,
)
from .automation_conversion_workflows import (
    api_admin_automation_conversion_dashboard,
    api_admin_automation_conversion_execution_batches,
    api_admin_automation_conversion_execution_detail,
    api_admin_automation_conversion_execution_item_detail,
    api_admin_automation_conversion_execution_item_send_via_bazhuayu,
    api_admin_automation_conversion_execution_items,
    api_admin_automation_conversion_workflow_activate,
    api_admin_automation_conversion_workflow_create,
    api_admin_automation_conversion_workflow_delete,
    api_admin_automation_conversion_workflow_detail,
    api_admin_automation_conversion_workflow_node_create,
    api_admin_automation_conversion_workflow_node_delete,
    api_admin_automation_conversion_workflow_node_list,
    api_admin_automation_conversion_workflow_node_update,
    api_admin_automation_conversion_workflow_pause,
    api_admin_automation_conversion_workflow_registry,
    api_admin_automation_conversion_workflow_summary,
    api_admin_automation_conversion_workflow_update,
    api_admin_automation_conversion_workflows,
)
def register_routes(bp):
    bp.route("/admin/automation-conversion", methods=["GET"])(admin_automation_conversion)
    bp.route("/admin/automation-conversion/programs/new", methods=["GET"])(admin_automation_program_new)
    bp.route("/admin/automation-conversion/programs", methods=["POST"])(admin_automation_program_create)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/update", methods=["POST"])(admin_automation_program_update)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/copy", methods=["POST"])(admin_automation_program_copy)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/activate", methods=["POST"])(admin_automation_program_activate)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/pause", methods=["POST"])(admin_automation_program_pause)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/archive", methods=["POST"])(admin_automation_program_archive)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/setup", methods=["GET"])(admin_automation_program_setup)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/overview", methods=["GET"])(admin_automation_program_overview)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/operations", methods=["GET"])(admin_automation_program_operations)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/operations/workflows", methods=["GET"])(admin_automation_program_workflows)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/operations/workflows/new", methods=["GET"])(admin_automation_program_workflow_new)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/operations/workflows/<int:workflow_id>/edit", methods=["GET"])(admin_automation_program_workflow_edit)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/operations/workflows/<int:workflow_id>/nodes", methods=["GET"])(admin_automation_program_workflow_nodes)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/executions", methods=["GET"])(admin_automation_program_executions)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/entry-channels", methods=["GET"])(admin_automation_program_entry_channels)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/flow-design", methods=["GET"])(admin_automation_program_flow_design)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/member-ops", methods=["GET"])(admin_automation_program_member_ops)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/member-ops/stage/<stage_key>/send", methods=["POST"])(admin_automation_program_member_ops_stage_send)
    bp.route(
        "/api/admin/automation-conversion/programs/<int:program_id>/members/segment-search",
        methods=["GET", "POST"],
    )(api_admin_automation_program_member_segment_search)
    bp.route(
        "/api/admin/automation-conversion/programs/<int:program_id>/members/segment-broadcast",
        methods=["POST"],
    )(api_admin_automation_program_member_segment_broadcast)
    bp.route("/admin/automation-conversion/shared/agents", methods=["GET"])(admin_automation_conversion_shared_agents)
    bp.route("/admin/automation-conversion/shared/profile-segments", methods=["GET"])(admin_automation_conversion_shared_profile_segments)
    bp.route("/admin/automation-conversion/shared/model-infra", methods=["GET"])(admin_automation_conversion_shared_model_infra)
    bp.route("/admin/channels", methods=["GET"])(admin_channels_page)
    bp.route("/admin/channels/new", methods=["GET"])(admin_channel_new_page)
    bp.route("/admin/channels/<int:channel_id>/edit", methods=["GET"])(admin_channel_edit_page)
    bp.route("/admin/automation-conversion/runtime", methods=["GET"])(admin_automation_conversion_runtime)
    bp.route("/admin/automation-conversion/runtime/sync", methods=["GET"])(admin_automation_conversion_runtime_sync)
    bp.route("/admin/automation-conversion/runtime/router", methods=["GET"])(admin_automation_conversion_runtime_router)
    bp.route("/admin/automation-conversion/runtime/logs", methods=["GET"])(admin_automation_conversion_runtime_logs)
    bp.route("/admin/automation-conversion/runtime/debug", methods=["GET"])(admin_automation_conversion_runtime_debug)
    bp.route("/admin/automation-conversion/settings/save", methods=["POST"])(admin_automation_conversion_save_settings)
    bp.route("/admin/automation-conversion/settings/default-channel/generate", methods=["POST"])(admin_automation_conversion_generate_default_channel)
    bp.route("/admin/automation-conversion/auto-reply", methods=["GET"])(admin_automation_conversion_auto_reply)
    bp.route("/admin/automation-conversion/agent-orchestration/agents/<agent_code>/save-draft", methods=["POST"])(admin_automation_conversion_agent_orchestration_save_draft)
    bp.route("/admin/automation-conversion/agent-orchestration/outputs/<output_id>/review", methods=["POST"])(admin_automation_conversion_agent_orchestration_review_output)
    bp.route("/admin/automation-conversion/agent-orchestration/replay/<run_id>", methods=["POST"])(admin_automation_conversion_agent_orchestration_replay)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/overview/signup-tag/apply", methods=["POST"])(admin_automation_program_overview_signup_tag_apply)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/overview/message-activity-sync/run", methods=["POST"])(admin_automation_program_overview_message_activity_sync_run)
    bp.route("/admin/automation-conversion/auto-reply/reply-monitor/toggle", methods=["POST"])(admin_automation_auto_reply_monitor_toggle)
    bp.route("/admin/automation-conversion/auto-reply/reply-monitor/capture", methods=["POST"])(admin_automation_auto_reply_monitor_capture)
    bp.route("/admin/automation-conversion/auto-reply/reply-monitor/run-due", methods=["POST"])(admin_automation_auto_reply_monitor_run_due)
    bp.route("/api/admin/automation-conversion/member", methods=["GET"])(api_admin_automation_conversion_member)
    bp.route("/api/admin/automation-conversion/member/put-in-pool", methods=["POST"])(api_admin_automation_conversion_put_in_pool)
    bp.route("/api/admin/automation-conversion/member/remove-from-pool", methods=["POST"])(api_admin_automation_conversion_remove_from_pool)
    bp.route("/api/admin/automation-conversion/member/set-focus", methods=["POST"])(api_admin_automation_conversion_set_focus)
    bp.route("/api/admin/automation-conversion/member/set-normal", methods=["POST"])(api_admin_automation_conversion_set_normal)
    bp.route("/api/admin/automation-conversion/member/mark-won", methods=["POST"])(api_admin_automation_conversion_mark_won)
    bp.route("/api/admin/automation-conversion/member/unmark-won", methods=["POST"])(api_admin_automation_conversion_unmark_won)
    bp.route("/api/admin/automation-conversion/member/push-openclaw", methods=["POST"])(api_admin_automation_conversion_push_openclaw)
    bp.route("/api/admin/automation-conversion/stage/<stage_key>/manual-send/preview", methods=["POST"])(api_admin_automation_conversion_stage_manual_send_preview)
    bp.route("/api/admin/automation-conversion/stage/<stage_key>/manual-send", methods=["POST"])(api_admin_automation_conversion_stage_manual_send)
    bp.route("/api/admin/automation-conversion/stage/<stage_key>/focus-send-batches", methods=["POST"])(api_admin_automation_conversion_focus_send_batch_create)
    bp.route("/api/admin/automation-conversion/focus-send-batches/<batch_id>", methods=["GET"])(api_admin_automation_conversion_focus_send_batch_detail)
    bp.route("/api/admin/automation-conversion/focus-send-batches/run-due", methods=["POST"])(api_admin_automation_conversion_focus_send_batch_run_due)
    bp.route("/api/admin/automation-conversion/sop/config", methods=["GET"])(api_admin_automation_conversion_sop_config_list)
    bp.route("/api/admin/automation-conversion/sop/config/<pool_key>", methods=["PUT"])(api_admin_automation_conversion_sop_config_save)
    bp.route("/api/admin/automation-conversion/sop/templates/<pool_key>", methods=["GET"])(api_admin_automation_conversion_sop_templates)
    bp.route("/api/admin/automation-conversion/sop/templates/<pool_key>/<int:day_index>", methods=["PUT"])(api_admin_automation_conversion_sop_template_save)
    bp.route("/api/admin/automation-conversion/sop/templates/<pool_key>/<int:day_index>", methods=["DELETE"])(api_admin_automation_conversion_sop_template_delete)
    bp.route("/api/admin/automation-conversion/sop/run-due", methods=["POST"])(api_admin_automation_conversion_sop_run_due)
    bp.route("/api/admin/automation-conversion/dashboard", methods=["GET"])(api_admin_automation_conversion_dashboard)
    bp.route("/api/admin/automation-conversion/settings", methods=["GET"])(api_admin_automation_conversion_settings_payload)
    bp.route("/api/admin/automation-conversion/settings", methods=["POST"])(api_admin_automation_conversion_settings_save)
    bp.route("/api/admin/automation-conversion/settings/default-channel/generate", methods=["POST"])(api_admin_automation_conversion_settings_default_channel_generate_qr)
    bp.route("/api/admin/automation-conversion/programs/<int:program_id>/setup", methods=["GET"])(api_admin_automation_program_setup)
    bp.route("/api/admin/automation-conversion/programs/<int:program_id>/setup/basic", methods=["POST"])(api_admin_automation_program_setup_basic)
    bp.route("/api/admin/automation-conversion/programs/<int:program_id>/setup/entry-channel", methods=["POST"])(api_admin_automation_program_setup_entry_channel)
    bp.route("/api/admin/automation-conversion/programs/<int:program_id>/setup/segmentation", methods=["POST"])(api_admin_automation_program_setup_segmentation)
    bp.route("/api/admin/automation-conversion/programs/<int:program_id>/setup/audience-entry-rule", methods=["POST"])(api_admin_automation_program_setup_audience_entry_rule)
    bp.route("/api/admin/automation-conversion/programs/<int:program_id>/setup/publish-check", methods=["GET"])(api_admin_automation_program_setup_publish_check)
    bp.route("/api/admin/automation-conversion/programs/<int:program_id>/publish-entry", methods=["POST"])(api_admin_automation_program_publish_entry)
    bp.route("/api/admin/automation-conversion/programs/<int:program_id>/publish-full", methods=["POST"])(api_admin_automation_program_publish_full)
    bp.route("/api/admin/automation-conversion/programs/<int:program_id>/customer-acquisition-links", methods=["GET", "POST"])(api_admin_automation_program_customer_acquisition_links)
    register_channel_admission_routes(bp)
    bp.route("/api/admin/automation-conversion/task-groups", methods=["GET", "POST"])(api_admin_automation_conversion_task_groups)
    bp.route("/api/admin/automation-conversion/task-groups/<int:group_id>", methods=["PUT"])(api_admin_automation_conversion_task_group_update)
    bp.route("/api/admin/automation-conversion/task-groups/<int:group_id>", methods=["DELETE"])(api_admin_automation_conversion_task_group_delete)
    bp.route("/api/admin/automation-conversion/tasks", methods=["GET", "POST"])(api_admin_automation_conversion_tasks)
    bp.route("/api/admin/automation-conversion/tasks/<int:task_id>", methods=["GET", "PUT"])(api_admin_automation_conversion_task_detail)
    bp.route("/api/admin/automation-conversion/tasks/<int:task_id>/copy", methods=["POST"])(api_admin_automation_conversion_task_copy)
    bp.route("/api/admin/automation-conversion/tasks/<int:task_id>/activate", methods=["POST"])(api_admin_automation_conversion_task_activate)
    bp.route("/api/admin/automation-conversion/tasks/<int:task_id>/pause", methods=["POST"])(api_admin_automation_conversion_task_pause)
    bp.route("/api/admin/automation-conversion/tasks/<int:task_id>", methods=["DELETE"])(api_admin_automation_conversion_task_delete)
    bp.route("/api/admin/automation-conversion/tasks/<int:task_id>/preview-audience", methods=["POST"])(api_admin_automation_conversion_task_preview_audience)
    bp.route("/api/admin/automation-conversion/tasks/run-due", methods=["POST"])(api_admin_automation_conversion_tasks_run_due)
    bp.route("/api/admin/automation-conversion/action-templates", methods=["GET", "POST"])(api_admin_automation_conversion_action_templates)
    bp.route("/api/admin/automation-conversion/action-templates/generate", methods=["POST"])(api_admin_automation_conversion_action_template_generate)
    bp.route("/api/admin/automation-conversion/action-templates/from-workflow", methods=["POST"])(api_admin_automation_conversion_action_template_from_workflow)
    bp.route("/api/admin/automation-conversion/programs/<int:program_id>/actions/from-template", methods=["POST"])(api_admin_automation_program_action_from_template)
    bp.route("/api/admin/automation-conversion/agent-outputs", methods=["GET"])(api_admin_automation_conversion_agent_outputs)
    bp.route("/api/admin/automation-conversion/agent-outputs/<output_id>", methods=["GET"])(api_admin_automation_conversion_agent_output_detail)
    bp.route("/api/admin/automation-conversion/agent-runs/<run_id>", methods=["GET"])(api_admin_automation_conversion_agent_run_detail)
    bp.route("/api/admin/automation-conversion/agent-outputs/export", methods=["POST"])(api_admin_automation_conversion_agent_outputs_export)
    bp.route("/api/admin/automation-conversion/agent-outputs/export/<job_id>", methods=["GET"])(api_admin_automation_conversion_agent_outputs_export_detail)
    bp.route("/api/admin/automation-conversion/agent-replay", methods=["GET"])(api_admin_automation_conversion_agent_replay)
    bp.route("/api/admin/automation-conversion/agent-orchestration/pending-publish", methods=["GET"])(api_admin_automation_conversion_pending_publish)
    bp.route("/api/admin/automation-conversion/agents", methods=["POST"])(api_admin_automation_conversion_agent_create)
    bp.route("/api/admin/automation-conversion/agents/options", methods=["GET"])(api_admin_automation_conversion_agent_options)
    bp.route("/api/admin/automation-conversion/agents/<agent_code>", methods=["GET"])(api_admin_automation_conversion_agent_detail)
    bp.route("/api/admin/automation-conversion/agents/<agent_code>", methods=["DELETE"])(api_admin_automation_conversion_agent_delete)
    bp.route("/api/admin/automation-conversion/agents/<agent_code>/draft", methods=["POST"])(api_admin_automation_conversion_agent_draft)
    bp.route("/api/admin/automation-conversion/agents/<agent_code>/publish", methods=["POST"])(api_admin_automation_conversion_agent_publish)
    bp.route("/api/admin/automation-conversion/default-channel-settings", methods=["GET"])(api_admin_automation_conversion_default_channel_settings)
    bp.route("/api/admin/automation-conversion/default-channel-settings", methods=["PUT"])(api_admin_automation_conversion_default_channel_settings_save)
    bp.route("/api/admin/automation-conversion/default-channel-settings/generate-qr", methods=["POST"])(api_admin_automation_conversion_default_channel_generate_qr)
    bp.route("/api/admin/automation-conversion/model-settings", methods=["GET"])(api_admin_automation_conversion_model_settings)
    bp.route("/api/admin/automation-conversion/model-settings", methods=["PUT"])(api_admin_automation_conversion_model_settings_save)
    bp.route("/api/admin/automation-conversion/model-settings/test", methods=["POST"])(api_admin_automation_conversion_model_settings_test)
    bp.route("/api/admin/automation-conversion/router-pending-callbacks", methods=["GET"])(api_admin_automation_conversion_router_pending_callbacks)
    bp.route("/api/admin/automation-conversion/router-callback-replay/<run_id>", methods=["POST"])(api_admin_automation_conversion_router_callback_replay)
    bp.route("/api/admin/automation-conversion/router-pending-callback-check", methods=["POST"])(api_admin_automation_conversion_router_pending_callback_check)
    bp.route("/api/admin/automation-conversion/profile-segment-templates/catalog", methods=["GET"])(api_admin_automation_conversion_profile_segment_catalog)
    bp.route("/api/admin/automation-conversion/profile-segment-templates", methods=["GET"])(api_admin_automation_conversion_profile_segment_templates)
    bp.route("/api/admin/automation-conversion/profile-segment-templates/options", methods=["GET"])(api_admin_automation_conversion_profile_segment_template_options)
    bp.route("/api/admin/automation-conversion/profile-segment-templates/<int:template_id>", methods=["GET"])(api_admin_automation_conversion_profile_segment_template_detail)
    bp.route("/api/admin/automation-conversion/profile-segment-templates", methods=["POST"])(api_admin_automation_conversion_profile_segment_template_create)
    bp.route("/api/admin/automation-conversion/profile-segment-templates/<int:template_id>", methods=["PUT"])(api_admin_automation_conversion_profile_segment_template_update)
    bp.route("/api/admin/automation-conversion/review-outputs", methods=["GET"])(api_admin_automation_conversion_review_outputs)
    bp.route("/api/admin/automation-conversion/review-outputs/<output_id>/review", methods=["POST"])(api_admin_automation_conversion_review_output)
    bp.route("/api/admin/automation-conversion/review-outputs/<output_id>/send-via-webhook", methods=["POST"])(api_admin_automation_conversion_review_output_send_via_webhook)
    bp.route("/api/admin/automation-conversion/review-outputs/<output_id>/send-via-wecom", methods=["POST"])(api_admin_automation_conversion_review_output_send_via_wecom)
    bp.route("/api/admin/automation-conversion/review-outputs/<output_id>/send-via-bazhuayu", methods=["POST"])(api_admin_automation_conversion_review_output_send_via_bazhuayu)
    bp.route("/api/admin/automation-conversion/workflows/registry", methods=["GET"])(api_admin_automation_conversion_workflow_registry)
    bp.route("/api/admin/automation-conversion/workflows", methods=["GET"])(api_admin_automation_conversion_workflows)
    bp.route("/api/admin/automation-conversion/workflows/<int:workflow_id>", methods=["GET"])(api_admin_automation_conversion_workflow_detail)
    bp.route("/api/admin/automation-conversion/workflows/<int:workflow_id>/summary", methods=["GET"])(api_admin_automation_conversion_workflow_summary)
    bp.route("/api/admin/automation-conversion/workflows", methods=["POST"])(api_admin_automation_conversion_workflow_create)
    bp.route("/api/admin/automation-conversion/workflows/<int:workflow_id>", methods=["PUT"])(api_admin_automation_conversion_workflow_update)
    bp.route("/api/admin/automation-conversion/workflows/<int:workflow_id>", methods=["DELETE"])(api_admin_automation_conversion_workflow_delete)
    bp.route("/api/admin/automation-conversion/workflows/<int:workflow_id>/activate", methods=["POST"])(api_admin_automation_conversion_workflow_activate)
    bp.route("/api/admin/automation-conversion/workflows/<int:workflow_id>/pause", methods=["POST"])(api_admin_automation_conversion_workflow_pause)
    bp.route("/api/admin/automation-conversion/workflows/<int:workflow_id>/nodes", methods=["GET"])(api_admin_automation_conversion_workflow_node_list)
    bp.route("/api/admin/automation-conversion/workflows/<int:workflow_id>/nodes", methods=["POST"])(api_admin_automation_conversion_workflow_node_create)
    bp.route("/api/admin/automation-conversion/workflow-nodes/<int:node_id>", methods=["PUT"])(api_admin_automation_conversion_workflow_node_update)
    bp.route("/api/admin/automation-conversion/workflow-nodes/<int:node_id>", methods=["DELETE"])(api_admin_automation_conversion_workflow_node_delete)
    bp.route("/api/admin/automation-conversion/executions", methods=["GET"])(api_admin_automation_conversion_execution_batches)
    bp.route("/api/admin/automation-conversion/executions/<int:execution_id>", methods=["GET"])(api_admin_automation_conversion_execution_detail)
    bp.route("/api/admin/automation-conversion/executions/<int:execution_id>/items", methods=["GET"])(api_admin_automation_conversion_execution_items)
    bp.route("/api/admin/automation-conversion/execution-items/<int:execution_item_id>", methods=["GET"])(api_admin_automation_conversion_execution_item_detail)
    bp.route("/api/admin/automation-conversion/execution-items/<int:execution_item_id>/send-via-bazhuayu", methods=["POST"])(api_admin_automation_conversion_execution_item_send_via_bazhuayu)
    bp.route("/api/admin/automation-conversion/message-activity-sync/run", methods=["POST"])(api_admin_automation_conversion_run_message_activity_sync)
    bp.route("/api/admin/automation-conversion/reply-monitor/capture", methods=["POST"])(api_admin_automation_conversion_reply_monitor_capture)
    bp.route("/api/admin/automation-conversion/reply-monitor/run-due", methods=["POST"])(api_admin_automation_conversion_reply_monitor_run_due)
    bp.route("/api/internal/automation-conversion/lobster-results", methods=["POST"])(api_internal_automation_conversion_lobster_results)
    bp.route("/api/internal/automation-conversion/laohuang-chat-results", methods=["POST"])(api_internal_automation_conversion_laohuang_chat_results)
    bp.route("/api/internal/automation-conversion/router-test-dispatch", methods=["POST"])(api_internal_automation_conversion_router_test_dispatch)
    bp.route("/api/admin/automation-conversion/jobs/run-due", methods=["POST"])(api_admin_automation_conversion_jobs_run_due)
