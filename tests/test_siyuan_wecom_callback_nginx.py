from __future__ import annotations

from scripts.ops.ensure_siyuan_wecom_callback_nginx import (
    BEGIN_MARKER,
    CALLBACK_ROUTES,
    ZONE_CONTENT,
    render_nginx_config,
)


BASE_CONFIG = """
server {
    listen 80;
    server_name www.xinliushangye.com;
    location / { return 301 https://$host$request_uri; }
}
server {
    listen 443 ssl;
    server_name www.xinliushangye.com xinliushangye.com;
    location = /archetype-test.html { root /var/www/html; }
    location / {
        proxy_pass http://127.0.0.1:5001;
    }
}
"""


def test_render_adds_only_tls_callback_routes_and_preserves_root_web_route() -> None:
    rendered = render_nginx_config(BASE_CONFIG)

    assert rendered.count(BEGIN_MARKER) == 1
    assert rendered.count("proxy_pass http://127.0.0.1:5002;") == len(CALLBACK_ROUTES)
    assert rendered.count("proxy_pass http://127.0.0.1:5001;") == 1
    assert rendered.index(BEGIN_MARKER) > rendered.index("listen 443 ssl;")
    assert rendered.index(BEGIN_MARKER) < rendered.index("proxy_pass http://127.0.0.1:5001;")
    for route in CALLBACK_ROUTES:
        assert f"location = {route}" in rendered
    assert "proxy_connect_timeout 1s;" in rendered
    assert "proxy_send_timeout 3s;" in rendered
    assert "proxy_read_timeout 3s;" in rendered
    assert "limit_req zone=aicrm_wecom_callback_req" in rendered
    assert "limit_conn aicrm_wecom_callback_conn" in rendered
    assert "limit_req_zone $binary_remote_addr" in ZONE_CONTENT
    assert "limit_conn_zone $binary_remote_addr" in ZONE_CONTENT


def test_render_is_idempotent() -> None:
    first = render_nginx_config(BASE_CONFIG)
    assert render_nginx_config(first) == first


def test_render_refuses_unmanaged_callback_route() -> None:
    unsafe = BASE_CONFIG.replace(
        "    location / {\n        proxy_pass http://127.0.0.1:5001;",
        "    location = /api/wecom/events { proxy_pass http://127.0.0.1:5009; }\n"
        "    location / {\n        proxy_pass http://127.0.0.1:5001;",
    )

    try:
        render_nginx_config(unsafe)
    except ValueError as exc:
        assert "unmanaged callback route" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected unmanaged callback route to be rejected")
