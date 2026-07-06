from __future__ import annotations

import json
import re
from pathlib import Path

from conftest import make_client

from aicrm_next.customer_read_model.parity_spec import (
    ENDPOINT_SPECS,
    compare_required_keys,
    compare_type_family,
    validate_payload,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OLD_FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "old_customer_read_model"


def _fixture_payload(name: str) -> dict:
    return json.loads((OLD_FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))["payload"]


def test_customer_read_model_parity_spec_covers_required_endpoints() -> None:
    assert set(ENDPOINT_SPECS) == {
        "customers.default",
        "customers.owner_filter",
        "customer_detail.default",
        "customer_timeline.default",
        "recent_messages.default",
    }


def test_old_customer_read_model_fixtures_conform_to_parity_spec() -> None:
    for name in ENDPOINT_SPECS:
        assert validate_payload(name, _fixture_payload(name)) == []


def test_next_customer_list_detail_timeline_messages_conform_to_parity_spec() -> None:
    client = make_client()
    endpoint_to_payload = {
        "customers.default": client.get("/api/customers").json(),
        "customers.owner_filter": client.get("/api/customers?owner_userid=ZhaoYanFang").json(),
        "customer_detail.default": client.get("/api/customers/wx_ext_001").json(),
        "customer_timeline.default": client.get("/api/customers/wx_ext_001/timeline").json(),
        "recent_messages.default": client.get("/api/messages/wx_ext_001/recent").json(),
    }
    for endpoint_name, payload in endpoint_to_payload.items():
        assert validate_payload(endpoint_name, payload) == []


def test_customer_comparison_detects_missing_required_key() -> None:
    issues = compare_required_keys({"ok": True}, ["ok", "items"])
    assert issues == [{"rule": "required_key", "location": "$", "key": "items", "severity": "fail"}]


def test_customer_comparison_detects_type_family_mismatch() -> None:
    issues = compare_type_family({"ok": True, "items": []}, {"ok": "true", "items": {}})
    assert any(issue["rule"] == "type_family" and issue["location"] == "$.ok" for issue in issues)
    assert any(issue["rule"] == "type_family" and issue["location"] == "$.items" for issue in issues)


def test_old_customer_read_model_fixtures_use_masked_values() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in OLD_FIXTURE_DIR.glob("*.json"))
    assert "mobile_masked_001" in combined
    assert "external_user_masked_001" in combined
    assert "customer_masked_001" in combined
    assert re.search(r"1[3-9]\d{9}", combined) is None
    assert "wx_ext_" not in combined
