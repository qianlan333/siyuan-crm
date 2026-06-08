from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


Json = dict[str, Any]


class WeComTagLiveGateway:
    def __init__(self, *, client: Any | None = None, api_base: str | None = None, timeout: int | None = None) -> None:
        self._client = client
        self._api_base = (api_base or os.getenv("AICRM_WECOM_TAG_API_BASE", "https://qyapi.weixin.qq.com")).rstrip("/")
        self._timeout = timeout or int(os.getenv("AICRM_WECOM_TAG_TIMEOUT_SECONDS", "15") or "15")

    def _build_client(self) -> Any:
        if self._client is not None:
            return self._client
        return self

    def _access_token(self) -> str:
        corp_id = os.getenv("AICRM_WECOM_TAG_CORP_ID") or os.getenv("WECOM_CORP_ID") or ""
        secret = os.getenv("AICRM_WECOM_TAG_AGENT_SECRET") or os.getenv("WECOM_CONTACT_SECRET") or os.getenv("WECOM_SECRET") or ""
        if not corp_id.strip() or not secret.strip():
            raise RuntimeError("WECOM_CORP_ID and WECOM_CONTACT_SECRET are required for WeCom tag sync")
        query = urlencode(
            {
                "corpid": corp_id,
                "corpsecret": secret,
            }
        )
        with urlopen(f"{self._api_base}/cgi-bin/gettoken?{query}", timeout=self._timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("errcode") != 0:
            raise RuntimeError(f"wecom token request failed: errcode={payload.get('errcode')}")
        return str(payload.get("access_token") or "")

    def _post(self, path: str, payload: Json) -> Json:
        token = self._access_token()
        query = urlencode({"access_token": token})
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            f"{self._api_base}{path}?{query}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=self._timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
        if result.get("errcode") not in (0, None):
            raise RuntimeError(f"wecom tag request failed: errcode={result.get('errcode')}")
        return dict(result or {})

    def list_wecom_tags_live(self) -> Json:
        client = self._build_client()
        if client is self:
            return self._post("/cgi-bin/externalcontact/get_corp_tag_list", {})
        return dict(client.list_wecom_tags_live() if hasattr(client, "list_wecom_tags_live") else client.list_tags({}) or {})

    def mark_tags_live(self, *, external_userid: str, tag_ids: list[str], operator: str) -> Json:
        client = self._build_client()
        payload = {"userid": operator, "external_userid": external_userid, "add_tag": list(tag_ids)}
        if client is self:
            return self._post("/cgi-bin/externalcontact/mark_tag", payload)
        return dict(client.mark_tags_live(external_userid=external_userid, tag_ids=tag_ids, operator=operator) if hasattr(client, "mark_tags_live") else client.mark_tag(payload) or {})

    def unmark_tags_live(self, *, external_userid: str, tag_ids: list[str], operator: str) -> Json:
        client = self._build_client()
        payload = {"userid": operator, "external_userid": external_userid, "remove_tag": list(tag_ids)}
        if client is self:
            return self._post("/cgi-bin/externalcontact/mark_tag", payload)
        return dict(client.unmark_tags_live(external_userid=external_userid, tag_ids=tag_ids, operator=operator) if hasattr(client, "unmark_tags_live") else client.mark_tag(payload) or {})


def build_wecom_tag_live_gateway() -> WeComTagLiveGateway:
    return WeComTagLiveGateway()
