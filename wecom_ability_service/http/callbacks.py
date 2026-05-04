from __future__ import annotations

from .callback_runtime import handle_external_contact_callback_request, handle_wecom_event_request


def receive_external_contact_callback():
    return handle_external_contact_callback_request()


def receive_wecom_event():
    return handle_wecom_event_request()


def register_routes(bp):
    bp.route('/wecom/external-contact/callback', methods=['GET', 'POST'])(receive_external_contact_callback)
    bp.route('/api/wecom/events', methods=['GET', 'POST'])(receive_wecom_event)
