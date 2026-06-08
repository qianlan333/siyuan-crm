from __future__ import annotations

from aicrm_next.hxc_dashboard.application import CreateHxcBroadcastTaskCommand
from aicrm_next.hxc_dashboard.dto import HxcBroadcastTaskRequest
from aicrm_next.hxc_dashboard.repo import InMemoryHxcDashboardBroadcastRepository
from aicrm_next.shared.repository_provider import RepositoryProviderError


def test_fixture_repo_returns_predictable_audience_preview() -> None:
    repo = InMemoryHxcDashboardBroadcastRepository()

    preview = repo.preview_audience(
        selected_customer_ids=["ext_hxc_001", "ext_hxc_002", "mobile_only_001"],
        audience_filter={},
        sender_userid="QianLan",
    )

    assert preview["audience_total"] == 3
    assert preview["eligible_count"] == 1
    assert preview["skipped_count"] == 2
    assert preview["skipped_by_reason"] == {
        "do_not_disturb": 1,
        "missing_external_userid": 1,
    }


class UnavailablePostgresLikeRepo:
    source_status = "production_postgres_hxc_dashboard"

    def preview_audience(self, **kwargs):
        raise RepositoryProviderError("database unavailable")

    def get_task_by_key(self, **kwargs):
        raise RepositoryProviderError("database unavailable")

    def create_task(self, payload):
        raise RepositoryProviderError("database unavailable")


def test_production_repo_unavailable_returns_production_unavailable_without_fake_success() -> None:
    request = HxcBroadcastTaskRequest(
        source_type="hxc_dashboard_broadcast",
        source_id="pytest",
        idempotency_key="postgres-unavailable",
        sender_userid="QianLan",
        selected_customer_ids=["ext_hxc_001"],
        content_package={"content_text": "hello"},
    )

    result = CreateHxcBroadcastTaskCommand(repo=UnavailablePostgresLikeRepo())(request)

    assert result["ok"] is True
    assert result["task"]["status"] == "production_unavailable"
    assert result["task"]["dispatch_status"] == "not_created"
    assert result["task"]["task_id"] == ""
