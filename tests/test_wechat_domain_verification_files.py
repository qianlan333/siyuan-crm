from __future__ import annotations


def test_wecom_domain_verification_file_is_served_from_root(next_client) -> None:
    response = next_client.get("/WW_verify_XDgKINYU8LF2JoSa.txt")

    assert response.status_code == 200
    assert response.text == "XDgKINYU8LF2JoSa"
    assert response.headers["cache-control"] == "no-store"


def test_root_verification_file_route_rejects_non_verification_paths(next_client) -> None:
    response = next_client.get("/not-a-verification-file.txt")

    assert response.status_code == 404
