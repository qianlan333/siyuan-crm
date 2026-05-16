"""Campaign step payload helper contracts."""
from __future__ import annotations

from wecom_ability_service.domains.campaigns.payload_helpers import (
    normalize_int_list,
    normalize_str_list,
    parse_step_payload,
)


def test_parse_step_payload_accepts_pg_jsonb_dict_copy():
    raw = {"image_library_ids": ["1"], "nested": {"keep": True}}

    parsed = parse_step_payload(raw)

    assert parsed == raw
    assert parsed is not raw


def test_parse_step_payload_accepts_legacy_json_string():
    assert parse_step_payload('{"image_library_ids":[1, "2"]}') == {
        "image_library_ids": [1, "2"]
    }


def test_parse_step_payload_rejects_bad_or_non_object_payloads():
    assert parse_step_payload("{bad json") == {}
    assert parse_step_payload("[1, 2, 3]") == {}
    assert parse_step_payload(None) == {}


def test_normalize_int_list_drops_invalid_values_and_applies_limit():
    assert normalize_int_list(["1", 2, "", None, "bad", 3.0], limit=3) == [1, 2, 3]
    assert normalize_int_list("4") == [4]
    assert normalize_int_list(5) == [5]


def test_normalize_str_list_strips_blanks_and_applies_limit():
    assert normalize_str_list([" a ", "", None, "b", " c "], limit=2) == ["a", "b"]
    assert normalize_str_list("media-id") == ["media-id"]
    assert normalize_str_list(123) == ["123"]
