from __future__ import annotations

import json
from typing import Any

from .http_client import OutboundHttpError, get_outbound_client


class WeChatOAuthRequestError(RuntimeError):
    pass


def _decode_wechat_json(response: Any) -> dict[str, Any]:
    content = getattr(response, "content", b"")
    if content:
        if isinstance(content, str):
            raw = content
        else:
            raw = bytes(content).decode("utf-8")
        payload = json.loads(raw)
    else:
        payload = response.json()
    return payload if isinstance(payload, dict) else {}


def _client(timeout: int):
    # The two endpoints share an upstream (WeChat MP), so they share a
    # circuit breaker. ``timeout`` from the caller is informational here —
    # the singleton's value wins after first init; that's fine because both
    # call sites historically used the same value.
    return get_outbound_client(
        "wechat_mp_oauth",
        timeout=float(timeout),
        retry_max=2,
    )


def exchange_wechat_oauth_code(*, app_id: str, app_secret: str, code: str, timeout: int = 15) -> dict[str, Any]:
    try:
        response = _client(timeout).get(
            "https://api.weixin.qq.com/sns/oauth2/access_token",
            params={
                "appid": app_id,
                "secret": app_secret,
                "code": code,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        return _decode_wechat_json(response)
    except OutboundHttpError as exc:
        raise WeChatOAuthRequestError(str(exc)) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WeChatOAuthRequestError("wechat_oauth_response_decode_failed") from exc


def fetch_wechat_userinfo(*, access_token: str, openid: str, timeout: int = 15) -> dict[str, Any]:
    try:
        response = _client(timeout).get(
            "https://api.weixin.qq.com/sns/userinfo",
            params={
                "access_token": access_token,
                "openid": openid,
                "lang": "zh_CN",
            },
        )
        response.raise_for_status()
        return _decode_wechat_json(response)
    except OutboundHttpError as exc:
        raise WeChatOAuthRequestError(str(exc)) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WeChatOAuthRequestError("wechat_oauth_response_decode_failed") from exc
