from __future__ import annotations

from aicrm_next.customer_read_model.reconciliation import reconcile_customer_read_model
from aicrm_next.customer_read_model.repo import FixtureCustomerReadRepository


def test_customer_read_model_reconciliation_records_counts_and_diffs() -> None:
    target = FixtureCustomerReadRepository()
    target.replace_all(
        customers=[
            {
                "external_userid": "wx_ext_001",
                "customer_name": "目标客户",
                "owner_userid": "owner-a",
                "mobile": "13800138000",
                "binding": {"is_bound": True, "binding_status": "bound"},
            }
        ],
        timeline_by_external_userid={},
        messages_by_external_userid={},
    )

    run = reconcile_customer_read_model(
        source_customers=[
            {"external_userid": "wx_ext_001", "customer_name": "来源客户", "owner_userid": "owner-a", "mobile": "13800138000", "binding_status": "bound"},
            {"external_userid": "wx_ext_002", "customer_name": "来源二", "owner_userid": "owner-b", "mobile": "13900139000", "binding_status": "unbound"},
        ],
        target_repo=target,
    )

    assert run.status == "completed"
    assert run.source_count == 2
    assert run.target_count == 1
    assert run.diff_count >= 1
    assert run.missing_in_target == ["wx***02"]
    assert run.field_diffs[0]["field"] == "customer_name"
