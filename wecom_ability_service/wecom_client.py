from __future__ import annotations

import hashlib
import logging
import secrets
import time
from dataclasses import dataclass, field

import requests
from flask import current_app

from .domains.tasks.private_message import build_private_message_request_payload
from .domains.wecom_media_limits import validate_wecom_image_upload
from .infra.circuit_breaker import CircuitBreaker
from .infra.error_codes import classify_wecom_errcode, WECOM_CIRCUIT_OPEN, WECOM_NETWORK_ERROR
from .infra.settings import get_setting, set_settings

wecom_logger = logging.getLogger("wecom_api")

_RETRYABLE_ERRCODES = {-1, 42001, 40014}
_TOKEN_EXPIRED_ERRCODES = {42001, 40014, 40001}
_MAX_RETRIES = 2
_RETRY_BACKOFF_BASE = 1.0

_circuit_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60.0)


class WeComClientError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        stage: str | None = None,
        category: str | None = None,
        payload: dict | None = None,
        error_code: str = "",
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.category = category
        self.payload = payload or {}
        self.error_code = error_code


def _classify_error(errcode: int | None, errmsg: str, stage: str) -> str:
    text = (errmsg or "").lower()
    if stage == "token" or errcode in {40014, 40001, 42001}:
        return "token"
    if errcode in {41001, 41004} or "secret" in text:
        return "secret 类型问题"
    if "visible range" in text or "not in visible range" in text:
        return "应用可见范围问题"
    if "tag" in text and ("not exist" in text or "invalid" in text):
        return "标签不存在"
    if errcode in {40058} or "invalid request parameter" in text or "expect type" in text:
        return "请求体格式问题"
    if errcode in {60011, 61003, 48002, 60020} or "permission" in text or "not allow" in text or "api forbidden" in text:
        return "权限问题"
    if errcode in {84061} or "not external contact" in text:
        return "external_userid 不存在"
    if "external_userid" in text and ("not exist" in text or "invalid" in text):
        return "external_userid 不存在"
    if "userid" in text and ("not exist" in text or "invalid" in text or "match" in text):
        return "userid 不匹配"
    return "wecom_api"


@dataclass
class WeComClient:
    corp_id: str
    secret: str
    api_base: str
    timeout: int = 15
    _access_token: str | None = field(default=None, init=False)
    _token_expires_at: float = field(default=0.0, init=False)
    _corp_jsapi_ticket: str | None = field(default=None, init=False)
    _corp_jsapi_ticket_expires_at: float = field(default=0.0, init=False)
    _agent_jsapi_ticket: str | None = field(default=None, init=False)
    _agent_jsapi_ticket_expires_at: float = field(default=0.0, init=False)

    def _persistent_ticket_keys(self, ticket_type: str) -> tuple[str, str]:
        prefix = "WECOM_AGENT_JSAPI_TICKET" if ticket_type == "agent_config" else "WECOM_CORP_JSAPI_TICKET"
        return f"{prefix}_VALUE", f"{prefix}_EXPIRES_AT"

    @classmethod
    def from_app(cls) -> "WeComClient":
        return cls.from_app_with_secret("WECOM_SECRET")

    @classmethod
    def from_contact_app(cls) -> "WeComClient":
        return cls.from_app_with_secret("WECOM_CONTACT_SECRET")

    @classmethod
    def from_app_with_secret(cls, secret_key: str) -> "WeComClient":
        corp_id = get_setting("WECOM_CORP_ID") or current_app.config["WECOM_CORP_ID"]
        secret = get_setting(secret_key) or current_app.config.get(secret_key, "")
        api_base = get_setting("WECOM_API_BASE") or current_app.config["WECOM_API_BASE"]
        timeout = int(get_setting("WECOM_ARCHIVE_TIMEOUT") or current_app.config["WECOM_ARCHIVE_TIMEOUT"])

        if not corp_id or not secret:
            raise WeComClientError(f"WECOM_CORP_ID or {secret_key} is not configured")
        cache_key = (secret_key, corp_id, secret, api_base.rstrip("/"), timeout)
        app_cache = current_app.extensions.setdefault("wecom_client_instances", {})
        cached_client = app_cache.get(cache_key)
        if cached_client:
            return cached_client
        client = cls(corp_id=corp_id, secret=secret, api_base=api_base.rstrip("/"), timeout=timeout)
        app_cache[cache_key] = client
        return client

    def _get_access_token(self) -> str:
        if self._access_token and self._token_expires_at > time.time():
            return self._access_token

        try:
            response = requests.get(
                f"{self.api_base}/cgi-bin/gettoken",
                params={"corpid": self.corp_id, "corpsecret": self.secret},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            wecom_logger.exception("gettoken request failed")
            raise WeComClientError(
                f"gettoken request failed: {exc}",
                stage="token",
                category="token",
            ) from exc
        if payload.get("errcode") != 0:
            wecom_logger.error("gettoken failed payload=%s", payload)
            raise WeComClientError(
                f"gettoken failed: {payload}",
                stage="token",
                category=_classify_error(payload.get("errcode"), payload.get("errmsg", ""), "token"),
                payload=payload,
            )

        self._access_token = payload["access_token"]
        expires_in = int(payload.get("expires_in", 7200))
        cache_seconds = min(expires_in - 60, current_app.config["ACCESS_TOKEN_CACHE_SECONDS"])
        self._token_expires_at = time.time() + max(cache_seconds, 60)
        return self._access_token

    def post(self, path: str, payload: dict | None = None) -> dict:
        return self._request_with_retry("POST", path, json_payload=payload)

    def _request_with_retry(
        self,
        method: str,
        path: str,
        *,
        json_payload: dict | None = None,
        query_params: dict | None = None,
    ) -> dict:
        if not _circuit_breaker.allow_request():
            raise WeComClientError(
                f"WeCom API circuit breaker open, request to {path} rejected",
                stage=path,
                category="circuit_breaker",
                error_code=WECOM_CIRCUIT_OPEN,
            )
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            access_token = self._get_access_token()
            try:
                result = self._do_request(method, path, access_token, json_payload=json_payload, query_params=query_params)
                errcode = result.get("errcode")
                if errcode in (0, None):
                    _circuit_breaker.record_success()
                    return result
                if errcode in _TOKEN_EXPIRED_ERRCODES and attempt < _MAX_RETRIES:
                    wecom_logger.warning("wecom token expired errcode=%s path=%s, refreshing", errcode, path)
                    self._access_token = None
                    self._token_expires_at = 0.0
                    continue
                if errcode in _RETRYABLE_ERRCODES and attempt < _MAX_RETRIES:
                    wecom_logger.warning("wecom retryable error errcode=%s path=%s attempt=%d", errcode, path, attempt)
                    time.sleep(_RETRY_BACKOFF_BASE * (2 ** attempt))
                    continue
                _circuit_breaker.record_failure()
                wecom_logger.error("wecom %s nonzero path=%s payload=%s", method, path, result)
                raise WeComClientError(
                    f"WeCom API failed: {result}",
                    stage=path,
                    category=_classify_error(errcode, result.get("errmsg", ""), path),
                    payload=result,
                    error_code=classify_wecom_errcode(errcode) if errcode else "",
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
                _circuit_breaker.record_failure()
                if attempt < _MAX_RETRIES:
                    wecom_logger.warning("wecom %s network error path=%s attempt=%d: %s", method, path, attempt, exc)
                    time.sleep(_RETRY_BACKOFF_BASE * (2 ** attempt))
                    continue
                wecom_logger.exception("wecom %s failed after retries path=%s", method, path)
                raise WeComClientError(
                    f"WeCom request failed: {exc}",
                    stage=path,
                    category="wecom_api",
                    error_code=WECOM_NETWORK_ERROR,
                ) from exc
            except requests.RequestException as exc:
                _circuit_breaker.record_failure()
                wecom_logger.exception("wecom %s failed path=%s", method, path)
                raise WeComClientError(
                    f"WeCom request failed: {exc}",
                    stage=path,
                    category="wecom_api",
                ) from exc
        raise WeComClientError(
            f"WeCom request failed after {_MAX_RETRIES + 1} attempts: {last_exc}",
            stage=path,
            category="wecom_api",
        )

    def _do_request(
        self,
        method: str,
        path: str,
        access_token: str,
        *,
        json_payload: dict | None = None,
        query_params: dict | None = None,
    ) -> dict:
        params = {"access_token": access_token}
        if query_params:
            params.update(query_params)
        if method == "POST":
            response = requests.post(
                f"{self.api_base}{path}",
                params=params,
                json=json_payload or {},
                timeout=self.timeout,
            )
        else:
            response = requests.get(
                f"{self.api_base}{path}",
                params=params,
                timeout=self.timeout,
            )
        response.raise_for_status()
        return response.json()

    def get(self, path: str, params: dict | None = None) -> dict:
        return self._request_with_retry("GET", path, query_params=params)

    def list_tags(self, payload: dict | None = None) -> dict:
        return self.post("/cgi-bin/externalcontact/get_corp_tag_list", payload)

    def list_external_contact_tags(self) -> dict:
        return self.list_tags()

    def get_strategy_tag_list(self, payload: dict | None = None) -> dict:
        return self.post("/cgi-bin/externalcontact/get_strategy_tag_list", payload)

    def create_tag(self, payload: dict) -> dict:
        return self.post("/cgi-bin/externalcontact/add_corp_tag", payload)

    def update_tag(self, payload: dict) -> dict:
        return self.post("/cgi-bin/externalcontact/edit_corp_tag", payload)

    def delete_tag(self, payload: dict) -> dict:
        return self.post("/cgi-bin/externalcontact/del_corp_tag", payload)

    def update_tag_group(self, payload: dict) -> dict:
        return self.update_tag(payload)

    def delete_tag_group(self, payload: dict) -> dict:
        return self.delete_tag(payload)

    def mark_tag(self, payload: dict) -> dict:
        return self.post("/cgi-bin/externalcontact/mark_tag", payload)

    def mark_external_contact_tags(
        self,
        external_userid: str,
        follow_user_userid: str,
        add_tags: list[str],
        remove_tags: list[str] | None = None,
    ) -> dict:
        # `add_tag` / `remove_tag` are the exact WeCom tag identifiers expected
        # by externalcontact/mark_tag.
        payload = {
            "userid": follow_user_userid,
            "external_userid": external_userid,
            "add_tag": [tag for tag in add_tags if tag],
        }
        normalized_remove_tags = [tag for tag in (remove_tags or []) if tag]
        if normalized_remove_tags:
            payload["remove_tag"] = normalized_remove_tags
        return self.mark_tag(payload)

    def create_private_message_task(self, payload: dict) -> dict:
        normalized_payload, _ = build_private_message_request_payload(
            payload,
            upload_image=self._upload_private_message_image,
        )
        payload.clear()
        payload.update(normalized_payload)
        return self.post("/cgi-bin/externalcontact/add_msg_template", payload)

    def create_group_message_task(self, payload: dict) -> dict:
        return self.post("/cgi-bin/externalcontact/add_msg_template", payload)

    def send_welcome_msg(self, payload: dict) -> dict:
        return self.post("/cgi-bin/externalcontact/send_welcome_msg", payload)

    def create_moment_task(self, payload: dict) -> dict:
        return self.post("/cgi-bin/externalcontact/add_moment_task", payload)

    def list_contacts(self, userid: str) -> dict:
        return self.get("/cgi-bin/externalcontact/list", {"userid": userid})

    def list_follow_userids(self) -> dict:
        return self.get("/cgi-bin/externalcontact/get_follow_user_list")

    def list_department_users(self, department_id: int = 1, fetch_child: int = 1) -> dict:
        return self.get(
            "/cgi-bin/user/list",
            {"department_id": int(department_id), "fetch_child": int(fetch_child)},
        )

    def get_contact(self, external_userid: str, cursor: str = "") -> dict:
        params = {"external_userid": external_userid}
        if cursor:
            params["cursor"] = cursor
        result = self.get("/cgi-bin/externalcontact/get", params)
        follow_users = list(result.get("follow_user") or [])
        next_cursor = result.get("next_cursor", "")
        while next_cursor:
            page = self.get("/cgi-bin/externalcontact/get", {"external_userid": external_userid, "cursor": next_cursor})
            follow_users.extend(page.get("follow_user") or [])
            next_cursor = page.get("next_cursor", "")
        result["follow_user"] = follow_users
        result.pop("next_cursor", None)
        return result

    def update_contact_description(self, payload: dict) -> dict:
        return self.post("/cgi-bin/externalcontact/remark", payload)

    def create_contact_way(self, payload: dict) -> dict:
        return self.post("/cgi-bin/externalcontact/add_contact_way", payload)

    def list_group_chats(self, payload: dict) -> dict:
        return self.post("/cgi-bin/externalcontact/groupchat/list", payload)

    def get_group_chat(self, chat_id: str, need_name: int = 1) -> dict:
        return self.post("/cgi-bin/externalcontact/groupchat/get", {"chat_id": chat_id, "need_name": need_name})

    def _upload_private_message_image(self, file_name: str, file_bytes: bytes, content_type: str) -> str:
        content_type = validate_wecom_image_upload(
            file_bytes,
            file_name=file_name,
            mime_type=content_type,
        )
        access_token = self._get_access_token()
        try:
            response = requests.post(
                f"{self.api_base}/cgi-bin/media/upload",
                params={"access_token": access_token, "type": "image"},
                files={"media": (file_name, file_bytes, content_type)},
                timeout=self.timeout,
            )
            response.raise_for_status()
            result = response.json()
        except requests.RequestException as exc:
            wecom_logger.exception("wecom media upload failed file=%s", file_name)
            raise WeComClientError(
                f"WeCom image upload failed: {exc}",
                stage="/cgi-bin/media/upload",
                category="wecom_api",
            ) from exc
        if result.get("errcode") not in (0, None):
            wecom_logger.error("wecom media upload nonzero payload=%s", result)
            raise WeComClientError(
                f"WeCom API failed: {result}",
                stage="/cgi-bin/media/upload",
                category=_classify_error(result.get("errcode"), result.get("errmsg", ""), "/cgi-bin/media/upload"),
                payload=result,
            )
        media_id = str(result.get("media_id") or "").strip()
        if not media_id:
            raise WeComClientError(
                f"WeCom image upload failed: {result}",
                stage="/cgi-bin/media/upload",
                category="wecom_api",
                payload=result,
            )
        return media_id

    def _get_ticket(self, ticket_type: str) -> tuple[str, int]:
        access_token = self._get_access_token()
        params = {"access_token": access_token}
        path = "/cgi-bin/get_jsapi_ticket"
        cache_attr = "_corp_jsapi_ticket"
        expires_attr = "_corp_jsapi_ticket_expires_at"
        if ticket_type == "agent_config":
            path = "/cgi-bin/ticket/get"
            params["type"] = "agent_config"
            cache_attr = "_agent_jsapi_ticket"
            expires_attr = "_agent_jsapi_ticket_expires_at"
        cached_ticket = getattr(self, cache_attr)
        cached_expires_at = getattr(self, expires_attr)
        if cached_ticket and cached_expires_at > time.time():
            return cached_ticket, int(max(cached_expires_at - time.time(), 60))

        persisted_ticket_key, persisted_expires_key = self._persistent_ticket_keys(ticket_type)
        persisted_ticket = str(get_setting(persisted_ticket_key) or "").strip()
        persisted_expires_at_raw = str(get_setting(persisted_expires_key) or "").strip()
        try:
            persisted_expires_at = float(persisted_expires_at_raw) if persisted_expires_at_raw else 0.0
        except ValueError:
            persisted_expires_at = 0.0
        if persisted_ticket and persisted_expires_at > time.time():
            setattr(self, cache_attr, persisted_ticket)
            setattr(self, expires_attr, persisted_expires_at)
            return persisted_ticket, int(max(persisted_expires_at - time.time(), 60))

        result = self.get(path, params)
        ticket = str(result.get("ticket") or "").strip()
        if not ticket:
            raise WeComClientError(
                f"ticket request missing ticket: {result}",
                stage=path,
                category="wecom_api",
                payload=result,
            )
        expires_in = int(result.get("expires_in", 7200))
        cache_seconds = max(min(expires_in - 60, current_app.config["ACCESS_TOKEN_CACHE_SECONDS"]), 60)
        expires_at = time.time() + cache_seconds
        setattr(self, cache_attr, ticket)
        setattr(self, expires_attr, expires_at)
        set_settings(
            {
                persisted_ticket_key: ticket,
                persisted_expires_key: str(expires_at),
            }
        )
        return ticket, expires_in

    def get_jsapi_ticket(self) -> dict:
        ticket, expires_in = self._get_ticket("jsapi")
        return {"ticket": ticket, "expires_in": expires_in}

    def get_agent_jsapi_ticket(self) -> dict:
        ticket, expires_in = self._get_ticket("agent_config")
        return {"ticket": ticket, "expires_in": expires_in}

    def build_jsapi_signature(self, url: str, *, ticket_type: str = "jsapi") -> dict:
        normalized_url = str(url or "").strip()
        if not normalized_url:
            raise ValueError("url is required")
        if ticket_type == "agent_config":
            ticket_info = self.get_agent_jsapi_ticket()
        else:
            ticket_info = self.get_jsapi_ticket()
        timestamp = str(int(time.time()))
        nonce_str = secrets.token_hex(8)
        plain = "&".join(
            [
                f"jsapi_ticket={ticket_info['ticket']}",
                f"noncestr={nonce_str}",
                f"timestamp={timestamp}",
                f"url={normalized_url}",
            ]
        )
        signature = hashlib.sha1(plain.encode("utf-8")).hexdigest()
        return {
            "timestamp": timestamp,
            "nonceStr": nonce_str,
            "signature": signature,
            "url": normalized_url,
        }
