from __future__ import annotations

import json
import re
import subprocess


def build_feishu_session_id(chat_id: str) -> str:
    normalized = str(chat_id or "").strip()
    if not normalized:
        return "feishu_default"
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", normalized).strip("_")
    return f"feishu_{safe or 'default'}"


def run_openclaw_agent_text(
    text: str,
    *,
    chat_id: str = "",
    timeout_seconds: int = 90,
) -> str:
    session_id = build_feishu_session_id(chat_id)
    command = [
        "openclaw",
        "agent",
        "--session-id",
        session_id,
        "--message",
        text,
        "--json",
        "--timeout",
        str(timeout_seconds),
    ]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds + 5,
            check=False,
        )
    except FileNotFoundError:
        return "OpenClaw CLI 不可用，请稍后重试。"
    except subprocess.TimeoutExpired:
        return "OpenClaw 处理超时了，请稍后再试。"
    except Exception as exc:  # pragma: no cover - defensive fallback
        return f"OpenClaw 处理失败：{exc}"

    payload = _parse_agent_payload(completed.stdout)
    reply_text = _extract_reply_text(payload)
    if reply_text:
        return reply_text

    stderr = (completed.stderr or "").strip()
    if stderr:
        return f"OpenClaw 处理失败：{stderr[:500]}"

    if completed.returncode != 0:
        return f"OpenClaw 处理失败，exit code={completed.returncode}"

    return "OpenClaw 暂时没有返回内容，请稍后再试。"


def _parse_agent_payload(stdout: str) -> dict:
    raw = str(stdout or "").strip()
    if not raw:
        return {}

    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        return {}

    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return {}


def _extract_reply_text(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""

    payloads = _extract_payloads(payload)
    if not payloads:
        return ""

    texts: list[str] = []
    for item in payloads:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if text:
            texts.append(text)
    return "\n\n".join(texts).strip()


def _extract_payloads(payload: dict) -> list[dict]:
    result = payload.get("result")
    if isinstance(result, dict):
        nested_payloads = result.get("payloads")
        if isinstance(nested_payloads, list):
            payloads = [item for item in nested_payloads if isinstance(item, dict)]
            if payloads:
                return payloads
        nested_payload = result.get("payload")
        if isinstance(nested_payload, dict):
            return [nested_payload]

    top_level_payloads = payload.get("payloads")
    if isinstance(top_level_payloads, list):
        payloads = [item for item in top_level_payloads if isinstance(item, dict)]
        if payloads:
            return payloads

    top_level_payload = payload.get("payload")
    if isinstance(top_level_payload, dict):
        return [top_level_payload]

    return []
