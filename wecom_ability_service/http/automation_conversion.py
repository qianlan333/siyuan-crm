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
from .automation_conversion_member_api import (
    api_admin_automation_conversion_focus_send_batch_create,
    api_admin_automation_conversion_mark_won,
    api_admin_automation_conversion_push_openclaw,
    api_admin_automation_conversion_put_in_pool,
    api_admin_automation_conversion_remove_from_pool,
    api_admin_automation_conversion_set_focus,
    api_admin_automation_conversion_set_normal,
    api_admin_automation_conversion_stage_manual_send,
    api_admin_automation_conversion_stage_manual_send_preview,
    api_admin_automation_conversion_unmark_won,
)
from .automation_conversion_task_runtime import (
    api_admin_automation_conversion_tasks_run_due,
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
from .automation_conversion_execution_outbound import (
    api_admin_automation_conversion_execution_item_send_via_bazhuayu,
)
def register_routes(bp):
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
    bp.route("/api/admin/automation-conversion/tasks/run-due", methods=["POST"])(api_admin_automation_conversion_tasks_run_due)
    bp.route("/api/admin/automation-conversion/execution-items/<int:execution_item_id>/send-via-bazhuayu", methods=["POST"])(api_admin_automation_conversion_execution_item_send_via_bazhuayu)
    bp.route("/api/admin/automation-conversion/message-activity-sync/run", methods=["POST"])(api_admin_automation_conversion_run_message_activity_sync)
    bp.route("/api/admin/automation-conversion/reply-monitor/capture", methods=["POST"])(api_admin_automation_conversion_reply_monitor_capture)
    bp.route("/api/admin/automation-conversion/reply-monitor/run-due", methods=["POST"])(api_admin_automation_conversion_reply_monitor_run_due)
    bp.route("/api/internal/automation-conversion/lobster-results", methods=["POST"])(api_internal_automation_conversion_lobster_results)
    bp.route("/api/internal/automation-conversion/laohuang-chat-results", methods=["POST"])(api_internal_automation_conversion_laohuang_chat_results)
    bp.route("/api/internal/automation-conversion/router-test-dispatch", methods=["POST"])(api_internal_automation_conversion_router_test_dispatch)
    bp.route("/api/admin/automation-conversion/jobs/run-due", methods=["POST"])(api_admin_automation_conversion_jobs_run_due)
