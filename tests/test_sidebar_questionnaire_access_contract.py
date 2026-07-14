from scripts.ci.check_sidebar_questionnaire_access_contract import check


def test_sidebar_questionnaire_access_contract_has_no_unsafe_legacy_path() -> None:
    assert check() == []
