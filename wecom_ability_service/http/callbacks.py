from __future__ import annotations

_RETIREMENT_MESSAGE = "Legacy WeCom callback routes are retired. Use aicrm_next.channel_entry."


def receive_external_contact_callback():
    raise RuntimeError(_RETIREMENT_MESSAGE)


def receive_wecom_event():
    raise RuntimeError(_RETIREMENT_MESSAGE)


def register_routes(bp):
    return None
