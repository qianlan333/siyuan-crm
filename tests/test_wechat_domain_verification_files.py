from __future__ import annotations


def test_wechat_domain_verification_file_is_served_from_root(next_client) -> None:
    response = next_client.get("/MP_verify_QqaW4cYDK8GxBbuG.txt")

    assert response.status_code == 200
    assert response.text.strip()
    assert response.headers["cache-control"] == "no-store"


def test_root_verification_file_route_rejects_non_verification_paths(next_client) -> None:
    response = next_client.get("/not-a-verification-file.txt")

    assert response.status_code == 404


def test_domain_verification_file_can_live_outside_repository(next_client, tmp_path, monkeypatch) -> None:
    verification_file = tmp_path / "WW_verify_environment.txt"
    verification_file.write_text("environment-token\n", encoding="utf-8")
    monkeypatch.setenv("AICRM_DOMAIN_VERIFICATION_DIR", str(tmp_path))

    response = next_client.get("/WW_verify_environment.txt")

    assert response.status_code == 200
    assert response.text == "environment-token"
