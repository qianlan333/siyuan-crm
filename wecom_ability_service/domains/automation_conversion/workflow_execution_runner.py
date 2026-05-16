from __future__ import annotations

from typing import Any

from ...db import get_db
from . import workflow_repo
from .private_message_dispatch import _dispatch_private_message_batch
from .workflow_service import get_conversion_workflow_model_bundle


def _runtime():
    from . import workflow_runtime

    return workflow_runtime


def _send_private_message_to_members_batch(
    *,
    members: list[dict[str, Any]],
    sender_userid: str,
    content_text: str,
    operator_id: str,
    filter_snapshot: dict[str, Any],
    miniprogram_library_ids: list[int] | None = None,
) -> dict[str, Any]:
    runtime = _runtime()
    target_items = [
        {
            "external_userid": runtime._normalized_text(member.get("external_contact_id")),
            "owner_display_name": sender_userid,
        }
        for member in members
        if runtime._normalized_text(member.get("external_contact_id"))
    ]
    return _dispatch_private_message_batch(
        target_items=target_items,
        sender_userid=sender_userid,
        content=runtime._normalized_text(content_text),
        miniprogram_library_ids=list(miniprogram_library_ids or []),
        operator_id=runtime._normalized_text(operator_id) or "automation_conversion_workflow",
        filter_snapshot=filter_snapshot,
    )


def _prepare_execution_item_for_send(
    *,
    execution: dict[str, Any],
    execution_item: dict[str, Any],
    workflow_bundle: dict[str, Any],
    node: dict[str, Any],
) -> dict[str, Any]:
    runtime = _runtime()
    member = workflow_repo.get_automation_member_row(int(execution_item.get("member_id") or 0)) or {}
    if not member:
        updated = workflow_repo.update_workflow_execution_item_row(
            int(execution_item["id"]),
            {
                **execution_item,
                "status": "skipped",
                "error_message": "automation_member_not_found",
                "content_snapshot_json": {"reason": "automation_member_not_found"},
                "rendered_content_text": "",
                "send_record_id": None,
                "sent_at": "",
            },
        )
        return {"ready": False, "item": updated}

    existing_content = runtime._normalized_text(execution_item.get("rendered_content_text"))
    existing_snapshot = dict(execution_item.get("content_snapshot_json") or {})
    if existing_content and existing_snapshot:
        final_content = existing_content
        snapshot = {
            **existing_snapshot,
            "rendered_content_text": existing_content,
        }
        rendered = {
            "agent_code": runtime._normalized_text(execution_item.get("agent_code")),
            "agent_run_id": runtime._normalized_text(execution_item.get("agent_run_id")),
            "agent_output_id": runtime._normalized_text(execution_item.get("agent_output_id")),
        }
    else:
        rendered = runtime._render_node_content(
            member=member,
            workflow_bundle=workflow_bundle,
            node=node,
            execution_request_id=f"workflow-node-{int(node['id'])}-item-{int(execution_item['id'])}",
        )
        final_content = runtime._normalized_text(rendered.get("content_text"))
        snapshot = {
            "workflow_code": runtime._normalized_text((workflow_bundle.get("workflow") or {}).get("workflow_code")),
            "workflow_name": runtime._normalized_text((workflow_bundle.get("workflow") or {}).get("workflow_name")),
            "node_code": runtime._normalized_text(node.get("node_code")),
            "node_name": runtime._normalized_text(node.get("node_name")),
            "node_content_mode": runtime._node_content_mode(node, workflow_bundle),
            "node_generation_mode": runtime._node_generation_mode(node, workflow_bundle),
            "node_segmentation_basis": runtime._node_segmentation_basis(node, workflow_bundle),
            "workflow_generation_mode": runtime._normalized_text((workflow_bundle.get("workflow") or {}).get("generation_mode")),
            "workflow_segmentation_basis": runtime._normalized_text((workflow_bundle.get("workflow") or {}).get("segmentation_basis")),
            "standard_content_text": runtime._normalized_text(node.get("standard_content_text")),
            "rendered_content_text": final_content,
            "content_source": runtime._normalized_text(rendered.get("content_source")),
            "fallback_reason": runtime._normalized_text(rendered.get("fallback_reason")),
            "agent_code": runtime._normalized_text(rendered.get("agent_code")),
            "segment_match": dict(rendered.get("segment_match") or {}),
            "behavior_match": dict(rendered.get("behavior_match") or {}),
        }

    node_content_mode = runtime._node_content_mode(node, workflow_bundle)
    miniprogram_library_ids = runtime._node_miniprogram_library_ids(node=node, workflow_bundle=workflow_bundle)
    if not runtime._normalized_text(member.get("external_contact_id")):
        updated = workflow_repo.update_workflow_execution_item_row(
            int(execution_item["id"]),
            {
                **execution_item,
                "status": "skipped",
                "error_message": "missing_external_contact_id",
                "content_snapshot_json": snapshot,
                "rendered_content_text": final_content,
                "agent_code": rendered.get("agent_code"),
                "agent_run_id": rendered.get("agent_run_id"),
                "agent_output_id": rendered.get("agent_output_id"),
                "send_record_id": None,
                "sent_at": "",
            },
        )
        return {"ready": False, "item": updated}
    if not final_content:
        updated = workflow_repo.update_workflow_execution_item_row(
            int(execution_item["id"]),
            {
                **execution_item,
                "status": "failed",
                "error_message": "rendered_content_empty",
                "content_snapshot_json": snapshot,
                "rendered_content_text": "",
                "agent_code": rendered.get("agent_code"),
                "agent_run_id": rendered.get("agent_run_id"),
                "agent_output_id": rendered.get("agent_output_id"),
                "send_record_id": None,
                "sent_at": "",
            },
        )
        return {"ready": False, "item": updated}

    sender_userid = runtime._normalized_text(member.get("owner_staff_id")) or runtime.DEFAULT_AUTOMATION_SENDER
    return {
        "ready": True,
        "item": execution_item,
        "member": member,
        "content_text": final_content,
        "snapshot": snapshot,
        "sender_userid": sender_userid,
        "owner_staff_id_missing": not bool(runtime._normalized_text(member.get("owner_staff_id"))),
        "agent_code": rendered.get("agent_code"),
        "agent_run_id": rendered.get("agent_run_id"),
        "agent_output_id": rendered.get("agent_output_id"),
        "miniprogram_library_ids": miniprogram_library_ids,
        "send_isolation_key": str(execution_item.get("id") or "") if node_content_mode == "personalized_single" else "",
        "filter_snapshot": {
            "selection_mode": "automation_conversion_workflow_node",
            "workflow_id": int(execution.get("workflow_id") or 0),
            "node_id": int(execution.get("node_id") or 0),
            "execution_id": runtime._normalized_text(execution.get("execution_id")),
            "miniprogram_library_ids": miniprogram_library_ids,
        },
    }


def _send_prepared_execution_groups(
    *,
    prepared_items: list[dict[str, Any]],
    operator_id: str,
) -> tuple[int, int]:
    runtime = _runtime()
    sent_count = 0
    failed_count = 0
    grouped_items: dict[tuple[str, str, tuple[int, ...], str], list[dict[str, Any]]] = {}
    for prepared in prepared_items:
        key = (
            runtime._normalized_text(prepared.get("sender_userid")),
            runtime._normalized_text(prepared.get("content_text")),
            tuple(int(item) for item in (prepared.get("miniprogram_library_ids") or [])),
            runtime._normalized_text(prepared.get("send_isolation_key")),
        )
        grouped_items.setdefault(key, []).append(prepared)

    for group in grouped_items.values():
        first = group[0]
        filter_snapshot = {
            **dict(first.get("filter_snapshot") or {}),
            "execution_item_ids": [int(dict(item.get("item") or {}).get("id") or 0) for item in group],
            "batch_group_count": len(group),
        }
        send_result = _send_private_message_to_members_batch(
            members=[dict(item.get("member") or {}) for item in group],
            sender_userid=runtime._normalized_text(first.get("sender_userid")) or runtime.DEFAULT_AUTOMATION_SENDER,
            content_text=runtime._normalized_text(first.get("content_text")),
            operator_id=operator_id,
            filter_snapshot=filter_snapshot,
            miniprogram_library_ids=list(first.get("miniprogram_library_ids") or []),
        )
        failed_external_userids = {
            runtime._normalized_text(item)
            for item in (send_result.get("fail_external_userids") or [])
            if runtime._normalized_text(item)
        }
        batch_failed = runtime._normalized_text(send_result.get("status")) == "failed" and not int(send_result.get("sent_count") or 0)
        for prepared in group:
            item = dict(prepared.get("item") or {})
            member = dict(prepared.get("member") or {})
            external_userid = runtime._normalized_text(member.get("external_contact_id"))
            item_failed = batch_failed or external_userid in failed_external_userids
            final_status = "failed" if item_failed else "sent"
            updated = workflow_repo.update_workflow_execution_item_row(
                int(item["id"]),
                {
                    **item,
                    "status": final_status,
                    "error_message": runtime._normalized_text(send_result.get("error_message")) if item_failed else "",
                    "content_snapshot_json": {
                        **dict(prepared.get("snapshot") or {}),
                        "sender_userid": runtime._normalized_text(send_result.get("sender_userid")),
                        "owner_staff_id_missing": bool(prepared.get("owner_staff_id_missing")),
                    },
                    "rendered_content_text": runtime._normalized_text(prepared.get("content_text")),
                    "agent_code": prepared.get("agent_code"),
                    "agent_run_id": prepared.get("agent_run_id"),
                    "agent_output_id": prepared.get("agent_output_id"),
                    "send_record_id": int(send_result.get("record_id") or 0) or None,
                    "sent_at": runtime._iso_now() if final_status == "sent" else "",
                },
            )
            if runtime._normalized_text((updated or {}).get("status")) == "sent":
                sent_count += 1
            else:
                failed_count += 1
    return sent_count, failed_count


def run_workflow_execution(*, execution_data: dict[str, Any]) -> dict[str, Any]:
    """broadcast_jobs handler 调用 — 执行一个 workflow execution 的 pending items。"""
    runtime = _runtime()
    execution_id_str = runtime._normalized_text(execution_data.get("execution_id"))
    workflow_id = int(execution_data.get("workflow_id") or 0)
    node_id = int(execution_data.get("node_id") or 0)
    operator_id = runtime._normalized_text(execution_data.get("operator_id")) or "automation_conversion_workflow_runner"

    if not execution_id_str or not workflow_id or not node_id:
        return {"ok": False, "error": "missing execution_id, workflow_id, or node_id"}

    execution = workflow_repo.get_workflow_execution_row_by_execution_id(execution_id_str)
    if not execution:
        return {"ok": False, "error": f"execution not found: {execution_id_str}"}
    if runtime._normalized_text(execution.get("status")) in runtime._FINAL_EXECUTION_STATUSES:
        return {"ok": True, "sent_count": 0, "failed_count": 0, "status": "already_finished"}

    workflow_bundle = get_conversion_workflow_model_bundle(workflow_id)
    node = None
    for item in workflow_bundle.get("nodes") or []:
        if int(item.get("id") or 0) == node_id:
            node = dict(item)
            break
    if not node:
        return {"ok": False, "error": f"node {node_id} not found in workflow {workflow_id}"}

    execution_items = workflow_repo.list_workflow_execution_item_rows(int(execution["id"]))
    sent_count = 0
    failed_count = 0
    prepared_items: list[dict[str, Any]] = []
    for item in execution_items:
        if runtime._normalized_text(item.get("status")) != "pending":
            continue
        prepared = _prepare_execution_item_for_send(
            execution=execution,
            execution_item=item,
            workflow_bundle=workflow_bundle,
            node=node,
        )
        if bool(prepared.get("ready")):
            prepared_items.append(prepared)
            continue
        result_item = dict(prepared.get("item") or {})
        if runtime._normalized_text(result_item.get("status")) == "sent":
            sent_count += 1
        elif runtime._normalized_text(result_item.get("status")) in {"failed", "skipped"}:
            failed_count += 1

    grouped_sent_count, grouped_failed_count = _send_prepared_execution_groups(
        prepared_items=prepared_items,
        operator_id=operator_id,
    )
    sent_count += grouped_sent_count
    failed_count += grouped_failed_count

    refreshed_items = workflow_repo.list_workflow_execution_item_rows(int(execution["id"]))
    final_status, counters = runtime._execution_summary_from_items(refreshed_items)
    prior_summary = execution.get("summary_json") or {}
    diagnostics = {
        **(prior_summary.get("diagnostics") or {}),
        "workflow_id": workflow_id,
        "node_id": node_id,
    }
    summary_json = runtime._execution_summary_json(
        workflow_bundle=workflow_bundle,
        node=node,
        diagnostics=diagnostics,
        counters=counters,
    )
    workflow_repo.update_workflow_execution_row(
        int(execution["id"]),
        {
            **execution,
            "status": final_status,
            "total_count": counters["total_count"],
            "success_count": counters["success_count"],
            "skipped_count": counters["skipped_count"],
            "failed_count": counters["failed_count"],
            "summary_json": summary_json,
            "finished_at": runtime._iso_now() if final_status in runtime._FINAL_EXECUTION_STATUSES else "",
        },
    )
    get_db().commit()
    return {
        "ok": True,
        "sent_count": sent_count,
        "failed_count": failed_count,
    }
