from __future__ import annotations

from wecom_ability_service.infra.error_codes import (
    CRMError,
    ERROR_REGISTRY,
    WECOM_TOKEN_EXPIRED,
    WECOM_PERMISSION_DENIED,
    WECOM_RATE_LIMITED,
    WECOM_CONTACT_NOT_FOUND,
    WECOM_API_ERROR,
    WECOM_CIRCUIT_OPEN,
    WECOM_NETWORK_ERROR,
    CONFIG_MISSING_REQUIRED,
    TASK_RETRY_EXHAUSTED,
    classify_wecom_errcode,
    get_error_info,
)


def test_error_registry_all_codes_have_entries():
    code_constants = [
        WECOM_TOKEN_EXPIRED, WECOM_PERMISSION_DENIED, WECOM_RATE_LIMITED,
        WECOM_CONTACT_NOT_FOUND, WECOM_API_ERROR, WECOM_NETWORK_ERROR,
        WECOM_CIRCUIT_OPEN, CONFIG_MISSING_REQUIRED, TASK_RETRY_EXHAUSTED,
    ]
    for code in code_constants:
        info = get_error_info(code)
        assert info is not None, f"missing registry entry for {code}"
        assert "message" in info
        assert "category" in info
        assert "troubleshoot" in info


def test_classify_wecom_errcode_token_expired():
    assert classify_wecom_errcode(42001) == WECOM_TOKEN_EXPIRED
    assert classify_wecom_errcode(40014) == WECOM_TOKEN_EXPIRED
    assert classify_wecom_errcode(40001) == WECOM_TOKEN_EXPIRED


def test_classify_wecom_errcode_permission():
    assert classify_wecom_errcode(60011) == WECOM_PERMISSION_DENIED
    assert classify_wecom_errcode(48002) == WECOM_PERMISSION_DENIED


def test_classify_wecom_errcode_rate_limit():
    assert classify_wecom_errcode(45009) == WECOM_RATE_LIMITED


def test_classify_wecom_errcode_contact_not_found():
    assert classify_wecom_errcode(84069) == WECOM_CONTACT_NOT_FOUND


def test_classify_wecom_errcode_unknown_defaults_to_api_error():
    assert classify_wecom_errcode(99999) == WECOM_API_ERROR


def test_crm_error_uses_registry():
    err = CRMError(WECOM_TOKEN_EXPIRED)
    assert err.code == WECOM_TOKEN_EXPIRED
    assert "Token" in err.message
    assert err.retryable is True
    assert err.category == "wecom_api"


def test_crm_error_custom_message():
    err = CRMError(CONFIG_MISSING_REQUIRED, "缺少 WECOM_CORP_ID")
    assert err.message == "缺少 WECOM_CORP_ID"
    assert err.retryable is False


def test_crm_error_to_dict():
    err = CRMError(WECOM_NETWORK_ERROR, detail="connection refused")
    d = err.to_dict()
    assert d["error_code"] == WECOM_NETWORK_ERROR
    assert d["retryable"] is True
    assert d["detail"] == "connection refused"
    assert "category" in d


def test_wecom_client_error_carries_error_code():
    from wecom_ability_service.wecom_client import WeComClientError
    exc = WeComClientError("test", error_code="E1007", category="circuit_breaker")
    assert exc.error_code == "E1007"
