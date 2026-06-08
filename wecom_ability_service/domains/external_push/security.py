from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse


class WebhookUrlValidationError(ValueError):
    pass


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _is_blocked_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(_normalized_text(address).strip("[]"))
    except ValueError as exc:
        raise WebhookUrlValidationError("webhook_url DNS resolved to an invalid IP") from exc
    if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
        return True
    if str(ip) == "169.254.169.254":
        return True
    return False


def validate_webhook_url(url: str) -> str:
    parsed = urlparse(_normalized_text(url))
    if parsed.scheme.lower() != "https":
        raise WebhookUrlValidationError("webhook_url must be an https URL")
    if not parsed.hostname:
        raise WebhookUrlValidationError("webhook_url host is required")
    hostname = parsed.hostname.strip().lower()
    if hostname in {"localhost", "127.0.0.1", "0.0.0.0", "::1"} or hostname.endswith(".localhost"):
        raise WebhookUrlValidationError("webhook_url host is not allowed")
    try:
        if _is_blocked_ip(hostname):
            raise WebhookUrlValidationError("webhook_url host must resolve to a public IP")
    except WebhookUrlValidationError as exc:
        if "invalid IP" not in str(exc):
            raise
    return parsed.geturl()


def resolve_and_validate_public_https_url(url: str) -> str:
    normalized = validate_webhook_url(url)
    parsed = urlparse(normalized)
    hostname = parsed.hostname or ""
    try:
        addr_infos = socket.getaddrinfo(hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise WebhookUrlValidationError("webhook_url DNS resolution failed") from exc
    resolved_ips = {item[4][0] for item in addr_infos if item and item[4]}
    if not resolved_ips:
        raise WebhookUrlValidationError("webhook_url DNS resolution returned no IP")
    for address in resolved_ips:
        if _is_blocked_ip(address):
            raise WebhookUrlValidationError("webhook_url resolved to a non-public IP")
    return normalized
