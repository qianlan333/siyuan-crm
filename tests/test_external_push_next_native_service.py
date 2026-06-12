from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace

from aicrm_next.external_push import repo, security, service


class FakeExternalPushRepository:
    def __init__(self) -> None:
        self.order = {
            "id": 101,
            "out_trade_no": "WXP_NEXT_NATIVE_PUSH",
            "product_code": "subscription_trial_month",
            "product_name": "外推测试商品",
            "amount_total": 9900,
            "payer_total": 9900,
            "paid_at": "2026-06-01T07:30:10+00:00",
            "external_userid": "wm_product_push",
            "payer_openid": "openid_product_push",
            "unionid": "unionid_product_push",
            "mobile_snapshot": "13800000000",
        }
        self.product = {
            "id": 202,
            "product_code": "subscription_trial_month",
            "name": "外推测试商品",
            "amount_total": 9900,
        }
        self.config = {
            "id": 303,
            "tenant_id": "aicrm",
            "enabled": True,
            "webhook_url": "https://example.com/hook",
            "push_type": "premium",
            "day": 31,
            "frequency": 3,
            "remark": "69元1个月续费",
            "custom_params": {"source": "ai-crm"},
            "secret": "secret",
        }
        self.outbox = {
            "id": 404,
            "aggregate_id": str(self.order["id"]),
            "payload": {"order_id": str(self.order["id"])},
        }
        self.delivery = {
            "id": 505,
            "config_id": self.config["id"],
            "event_type": "transaction.paid",
            "delivery_id": "deliv_next_native",
            "target_type": "product",
            "target_id": str(self.product["id"]),
            "order_id": self.order["id"],
            "product_id": self.product["id"],
            "status": "pending",
            "attempt_count": 0,
            "request_url": self.config["webhook_url"],
            "request_headers": {},
            "request_body": {},
        }
        self.due_outbox_events = [deepcopy(self.outbox)]
        self.due_deliveries: list[dict] = []
        self.outbox_statuses: list[tuple[int, str]] = []
        self.updated_deliveries: list[dict] = []

    def list_due_outbox_events(self, *, limit: int = 20):
        assert limit > 0
        return deepcopy(self.due_outbox_events[:limit])

    def list_due_deliveries(self, *, limit: int = 20):
        assert limit > 0
        return deepcopy(self.due_deliveries[:limit])

    def mark_outbox_status(self, outbox_id: int, *, status: str, retry_count=None, next_retry_at=None):
        self.outbox_statuses.append((outbox_id, status))
        return {"id": outbox_id, "status": status, "retry_count": retry_count, "next_retry_at": next_retry_at}

    def get_order_by_id(self, order_id: int):
        return deepcopy(self.order) if int(order_id) == int(self.order["id"]) else None

    def get_product_for_order(self, order: dict):
        return deepcopy(self.product) if order else {}

    def get_product_by_id(self, product_id: int):
        return deepcopy(self.product) if int(product_id) == int(self.product["id"]) else None

    def get_product_config(self, product_id: int):
        return deepcopy(self.config) if int(product_id) == int(self.product["id"]) else None

    def get_config_with_secret(self, config_id: int):
        return deepcopy(self.config) if int(config_id) == int(self.config["id"]) else None

    def create_delivery_once(self, payload: dict):
        delivery = deepcopy(self.delivery)
        delivery.update(
            {
                "config_id": int(payload["config_id"]),
                "event_type": payload["event_type"],
                "delivery_id": payload["delivery_id"],
                "target_type": payload["target_type"],
                "target_id": payload["target_id"],
                "order_id": int(payload["order_id"]),
                "product_id": int(payload["product_id"]),
                "request_url": payload["request_url"],
            }
        )
        self.delivery = delivery
        return deepcopy(delivery)

    def create_test_delivery(self, payload: dict):
        delivery = deepcopy(self.delivery)
        delivery.update(
            {
                "event_type": "external_push.test",
                "delivery_id": payload["delivery_id"],
                "order_id": 0,
                "product_id": int(payload["product_id"]),
                "request_url": payload["request_url"],
            }
        )
        self.delivery = delivery
        return deepcopy(delivery)

    def update_delivery_result(self, delivery_id: str, **payload):
        updated = deepcopy(self.delivery)
        updated.update(payload)
        updated["delivery_id"] = delivery_id
        self.delivery = updated
        self.updated_deliveries.append(deepcopy(updated))
        return deepcopy(updated)

    def get_delivery_by_delivery_id(self, delivery_id: str):
        return deepcopy(self.delivery) if delivery_id == self.delivery["delivery_id"] else None

    def list_deliveries_for_order(self, order_id: int):
        return [deepcopy(self.delivery)] if int(order_id) == int(self.order["id"]) else []


def _fake_response(status_code: int, text: str):
    return SimpleNamespace(status_code=status_code, text=text, is_redirect=False, headers={})


def _allow_no_dns(monkeypatch) -> None:
    monkeypatch.setattr(service, "resolve_and_validate_public_https_url", lambda url: url)


def test_repository_builder_uses_next_session_factory() -> None:
    repository = repo.build_external_push_repository(session_factory=lambda: object())  # type: ignore[return-value]

    assert isinstance(repository, repo.SQLAlchemyExternalPushRepository)


def test_security_rejects_non_https_urls() -> None:
    try:
        security.validate_webhook_url("http://127.0.0.1/hook")
    except security.WebhookUrlValidationError as exc:
        assert "https" in str(exc) or "public IP" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("local http webhook URL should be rejected")


def test_signature_is_stable_and_sensitive_payload_is_redacted() -> None:
    sig = service.sign_webhook_payload("secret", "1778888888", '{"a":1}')

    assert sig == service.sign_webhook_payload("secret", "1778888888", '{"a":1}')
    assert sig != service.sign_webhook_payload("secret", "1778888888", '{"a":2}')
    assert service.redact_sensitive_fields({"phone": "13800000000", "buyer": {"unionid": "unionid_product_push"}}) == {
        "phone": "138****0000",
        "buyer": {"unionid": "unio***push"},
    }


def test_run_due_events_success_updates_delivery_and_outbox(monkeypatch) -> None:
    repository = FakeExternalPushRepository()
    sent_payloads: list[dict] = []
    _allow_no_dns(monkeypatch)

    def fake_post(*args, **kwargs):
        sent_payloads.append(json.loads(kwargs["data"].decode("utf-8")))
        return _fake_response(200, '{"ok":true}')

    monkeypatch.setattr(service.requests, "post", fake_post)

    result = service.run_due_external_push_events(limit=5, repository=repository)

    assert result["ok"] is True
    assert result["scanned_count"] == 1
    assert result["success_count"] == 1
    assert repository.outbox_statuses == [(repository.outbox["id"], "success")]
    assert repository.delivery["status"] == "success"
    assert repository.delivery["attempt_count"] == 1
    assert repository.delivery["request_headers"]["X-AICRM-Signature"].startswith("sha256=")
    assert repository.delivery["request_body"]["phone_number"] == "138****0000"
    assert repository.delivery["request_body"]["buyer"]["phone"] == "138****0000"
    assert sent_payloads[0]["phone_number"] == "13800000000"
    assert sent_payloads[0]["buyer"]["phone"] == "13800000000"
    assert sent_payloads[0]["event"] == "transaction.paid"


def test_run_due_events_handles_http_failure_as_retry(monkeypatch) -> None:
    repository = FakeExternalPushRepository()
    _allow_no_dns(monkeypatch)
    monkeypatch.setattr(service.requests, "post", lambda *args, **kwargs: _fake_response(500, "x" * 9000))

    result = service.run_due_external_push_events(limit=5, repository=repository)

    assert result["failed_count"] == 1
    assert repository.outbox_statuses == [(repository.outbox["id"], "success")]
    assert repository.delivery["status"] == "retrying"
    assert repository.delivery["response_status"] == 500
    assert len(repository.delivery["response_body"].encode("utf-8")) <= service.MAX_BODY_BYTES
    assert repository.delivery["next_retry_at"]


def test_run_due_events_skips_missing_config_without_http_call(monkeypatch) -> None:
    repository = FakeExternalPushRepository()
    repository.config = {}
    monkeypatch.setattr(
        service.requests,
        "post",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected external call")),
    )

    result = service.run_due_external_push_events(limit=5, repository=repository)

    assert result["skipped_count"] == 1
    assert result["items"][0]["reason"] == "config_not_found"
    assert repository.outbox_statuses == [(repository.outbox["id"], "skipped")]


def test_run_due_retries_uses_existing_delivery_and_mocked_http(monkeypatch) -> None:
    repository = FakeExternalPushRepository()
    failed_delivery = deepcopy(repository.delivery)
    failed_delivery["status"] = "retrying"
    failed_delivery["attempt_count"] = 1
    failed_delivery["request_body"] = {}
    repository.due_deliveries = [failed_delivery]
    _allow_no_dns(monkeypatch)
    monkeypatch.setattr(service.requests, "post", lambda *args, **kwargs: _fake_response(200, "ok"))

    result = service.run_due_external_push_retries(limit=3, repository=repository)

    assert result["ok"] is True
    assert result["retried_count"] == 1
    assert repository.delivery["status"] == "success"
    assert repository.delivery["attempt_count"] == 2


def test_send_product_external_push_test_uses_test_event_payload(monkeypatch) -> None:
    repository = FakeExternalPushRepository()
    sent_payloads: list[dict] = []
    _allow_no_dns(monkeypatch)
    monkeypatch.setattr(
        service.requests,
        "post",
        lambda *args, **kwargs: (sent_payloads.append(json.loads(kwargs["data"].decode("utf-8"))) or _fake_response(200, "ok")),
    )

    result = service.send_product_external_push_test(repository.product["id"], repository=repository)

    assert result["ok"] is True
    assert repository.delivery["event_type"] == "external_push.test"
    assert sent_payloads[0]["event"] == "external_push.test"
