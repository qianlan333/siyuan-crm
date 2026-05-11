"""External Cloud Agent — 在 CRM 进程外（cron / UI worker / CLI）跑的 Claude tool-use loop。

CRM 自己不做 LLM 调用，但定时扫描 / UI 流式触发都需要"以外部 Agent 身份"跑一段。
本模块即这个外部 Agent 的核心实现，让 cron 脚本 / 未来 UI SSE worker / 测试能共用
同一段 tool-use loop 逻辑：

    from wecom_ability_service.domains.cloud_orchestrator.external_agent import orchestrate

    summary = orchestrate(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        mcp_url="http://127.0.0.1:5000/mcp",
        mcp_token=os.environ.get("MCP_BEARER_TOKEN", ""),
        user_prompt="扫描沉默用户...",
        operator="cloud_scheduler",
    )
    print(summary["stop_reason"], summary["tool_calls"])

调用方式（设计原则）：

- **可注入**：``client_factory`` / ``mcp_caller`` / ``trace_id`` 都可注入，便于测试
- **稳定**：所有错误都映射到 ``OrchestrateExitCode``；不抛到调用方
- **可扩展**：``allowed_tools`` / ``blocked_tools`` 让上层按场景定制 tool 白名单
- **可观察**：``summary["tool_call_log"]`` 记录每次 call 的 args + 截短结果，
  ``trace_id`` / ``session_id`` 注入到 tool arguments 里贯穿三端
"""
from __future__ import annotations

import enum
import json
import logging
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Callable, Iterable, Sequence


# ---- 常量 --------------------------------------------------------------
DEFAULT_MODEL = "claude-opus-4-7"
DEFAULT_MAX_ITERATIONS = 12
DEFAULT_MAX_TOOLS = 20
DEFAULT_MAX_TOKENS = 4096
DEFAULT_MCP_RETRIES = 3
DEFAULT_MCP_TIMEOUT = 60

# Cloud 自动扫描永远不允许动这几个：commit / start = 真发，request_copy_workorder
# 不是真发但绕过 plan 流程，留给 ``draft_broadcast_plan`` 内部 ``auto_copy_workorder=True`` 触发
DEFAULT_BLOCKED_TOOL_NAMES: frozenset[str] = frozenset(
    {"commit_broadcast_plan", "start_campaign", "request_copy_workorder"}
)

# 兜底：``[WRITE`` 前缀由 mcp_adapter 在 description 里加。哪怕 deny-list 漏了新写工具，
# 描述层一定带 ``[WRITE`` 标记，依然过滤掉。
_BLOCKED_DESCRIPTION_PREFIXES = ("[WRITE",)

logger = logging.getLogger(__name__)


class OrchestrateExitCode(enum.IntEnum):
    """``orchestrate()`` 的标准退出码 — cron 脚本 / 调用方按这个 sys.exit。"""

    OK = 0
    MISSING_API_KEY = 1
    CLAUDE_API_ERROR = 2
    MCP_UNREACHABLE = 3


# ---- 异常 --------------------------------------------------------------
class McpUnreachableError(RuntimeError):
    """连续重试后仍无法连上 MCP HTTP server。"""


class ClaudeApiError(RuntimeError):
    """Claude API 调用失败（鉴权 / 网络 / 模型不可用 / SDK 缺失 / 其他）。"""


# ---- MCP 客户端 --------------------------------------------------------
def call_mcp(
    method: str,
    params: dict[str, Any] | None = None,
    *,
    url: str,
    token: str = "",
    retries: int = DEFAULT_MCP_RETRIES,
    timeout: int = DEFAULT_MCP_TIMEOUT,
    request_factory: Callable[..., urllib.request.Request] | None = None,
    opener: Callable[[urllib.request.Request, int], Any] | None = None,
) -> Any:
    """JSON-RPC 2.0 调用本地 MCP HTTP server。

    重试 1s / 3s / 9s 指数退避（前两次失败后等待）。
    成功返回 ``result`` 字段；JSON-RPC 错误抛 ``RuntimeError``；
    网络 / 解析失败抛 ``McpUnreachableError``。

    ``request_factory`` 与 ``opener`` 仅给单元测试注入用。
    """
    body = {
        "jsonrpc": "2.0",
        "id": uuid.uuid4().hex[:12],
        "method": method,
        "params": params or {},
    }
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    factory = request_factory or urllib.request.Request
    open_url = opener or (lambda req, t: urllib.request.urlopen(req, timeout=t))

    last_exc: Exception | None = None
    attempts = max(1, retries)
    for attempt in range(attempts):
        try:
            req = factory(
                url,
                data=json.dumps(body).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with open_url(req, timeout) as resp:
                payload = json.loads(
                    resp.read().decode("utf-8", errors="replace") or "{}"
                )
            if isinstance(payload, dict) and payload.get("error"):
                err = payload["error"]
                raise RuntimeError(
                    f"jsonrpc error: code={err.get('code')} message={err.get('message')}"
                )
            return payload.get("result") if isinstance(payload, dict) else payload
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            last_exc = exc
            if attempt + 1 >= attempts:
                break
            sleep_for = 3 ** attempt  # 1, 3, 9
            logger.warning(
                "[mcp] %s attempt %d failed: %s; retry in %ds",
                method,
                attempt + 1,
                exc,
                sleep_for,
            )
            time.sleep(sleep_for)
    raise McpUnreachableError(
        f"mcp call failed after {attempts} attempts: {last_exc}"
    ) from last_exc


def discover_tools(
    *,
    url: str,
    token: str,
    blocked: Iterable[str] = (),
    allowed: Iterable[str] | None = None,
    retries: int = DEFAULT_MCP_RETRIES,
    timeout: int = DEFAULT_MCP_TIMEOUT,
    mcp_caller: Callable[..., Any] | None = None,
) -> list[dict[str, Any]]:
    """拉取 MCP ``tools/list``，过滤黑名单 + ``[WRITE]`` 描述，转 Anthropic ``input_schema`` 格式。

    ``allowed`` 为白名单：传非空则只保留这些名字（与 blocked 双向过滤）。
    """
    caller = mcp_caller or call_mcp
    payload = caller(
        "tools/list",
        {},
        url=url,
        token=token,
        retries=retries,
        timeout=timeout,
    )
    raw_tools: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        raw_tools = list(payload.get("tools") or [])
    blocked_set = set(blocked)
    allowed_set = set(allowed) if allowed else None
    out: list[dict[str, Any]] = []
    for tool in raw_tools:
        name = str(tool.get("name") or "")
        if not name or name in blocked_set:
            continue
        if allowed_set is not None and name not in allowed_set:
            continue
        description = str(tool.get("description") or "")
        if any(description.startswith(p) for p in _BLOCKED_DESCRIPTION_PREFIXES):
            continue
        schema = (
            tool.get("input_schema")
            or tool.get("inputSchema")
            or {"type": "object", "properties": {}}
        )
        out.append(
            {
                "name": name,
                "description": description,
                "input_schema": schema,
            }
        )
    return out


def execute_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    url: str,
    token: str,
    trace_id: str,
    session_id: str,
    operator: str,
    retries: int = DEFAULT_MCP_RETRIES,
    timeout: int = DEFAULT_MCP_TIMEOUT,
    mcp_caller: Callable[..., Any] | None = None,
) -> Any:
    """对单个 tool 注入 ``__trace_id`` / ``__session_id`` / ``__operator`` 后 ``tools/call``。

    mcp_adapter 一侧会 pop 这三个 key 并路由给 ``dispatch_cloud_tool``，
    自动写 ``cloud_agent_audit_log`` 让审计三端贯穿。
    """
    caller = mcp_caller or call_mcp
    augmented = dict(arguments or {})
    augmented["__trace_id"] = trace_id
    augmented["__session_id"] = session_id
    augmented["__operator"] = operator
    return caller(
        "tools/call",
        {"name": name, "arguments": augmented},
        url=url,
        token=token,
        retries=retries,
        timeout=timeout,
    )


# ---- Anthropic 客户端 --------------------------------------------------
def build_claude_client(api_key: str, base_url: str = "") -> Any:
    """实例化 ``anthropic.Anthropic``，缺包时抛 ``ClaudeApiError``。"""
    try:
        import anthropic  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - 运行时缺包
        raise ClaudeApiError(
            "anthropic SDK not installed; run `pip install anthropic`"
        ) from exc
    kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return anthropic.Anthropic(**kwargs)


def call_claude(
    client: Any,
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    system: str,
    max_tokens: int,
) -> Any:
    """单次 Anthropic Messages API 调用。

    - ``system`` 走一个 ``cache_control`` breakpoint
    - 最后一个 tool 走一个 ``cache_control`` breakpoint，覆盖整个 tools 数组
    - 两个 breakpoint 都用 ``ephemeral`` 类型（5 分钟 TTL）
    - 把 SDK 错误统一转 ``ClaudeApiError``
    """
    cached_tools = list(tools)
    if cached_tools:
        last = dict(cached_tools[-1])
        last["cache_control"] = {"type": "ephemeral"}
        cached_tools[-1] = last
    cached_system = [
        {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
    ]
    try:
        return client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=cached_system,
            tools=cached_tools,
            messages=messages,
        )
    except Exception as exc:  # pragma: no cover - SDK 错误透传
        raise ClaudeApiError(f"messages.create failed: {exc}") from exc


# ---- 辅助 --------------------------------------------------------------
def _content_blocks_to_dict(blocks: Sequence[Any]) -> list[dict[str, Any]]:
    """把 SDK 返回的 content blocks 序列化成 dict（assistant 历史回放用）。"""
    out: list[dict[str, Any]] = []
    for block in blocks or []:
        block_type = getattr(block, "type", None) or (
            block.get("type") if isinstance(block, dict) else None
        )
        if block_type == "text":
            text = (
                getattr(block, "text", None)
                if not isinstance(block, dict)
                else block.get("text")
            ) or ""
            out.append({"type": "text", "text": text})
        elif block_type == "tool_use":
            out.append(
                {
                    "type": "tool_use",
                    "id": (
                        getattr(block, "id", None)
                        if not isinstance(block, dict)
                        else block.get("id")
                    ),
                    "name": (
                        getattr(block, "name", None)
                        if not isinstance(block, dict)
                        else block.get("name")
                    ),
                    "input": (
                        getattr(block, "input", None)
                        if not isinstance(block, dict)
                        else block.get("input")
                    )
                    or {},
                }
            )
        else:
            # 透传未知类型（thinking 等）
            if hasattr(block, "model_dump"):
                out.append(block.model_dump())
            elif isinstance(block, dict):
                out.append(dict(block))
    return out


def _summarize(value: Any, *, limit: int = 240) -> str:
    """日志里截短结果，避免噪音。"""
    try:
        s = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        s = repr(value)
    return s if len(s) <= limit else s[: limit - 3] + "..."


# ---- 主 orchestrate ---------------------------------------------------
def orchestrate(
    *,
    api_key: str,
    mcp_url: str,
    mcp_token: str = "",
    user_prompt: str,
    system_prompt: str = "",
    operator: str = "cloud_scheduler",
    model: str = DEFAULT_MODEL,
    base_url: str = "",
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    max_tools: int = DEFAULT_MAX_TOOLS,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    mcp_retries: int = DEFAULT_MCP_RETRIES,
    mcp_timeout: int = DEFAULT_MCP_TIMEOUT,
    blocked_tools: Iterable[str] = DEFAULT_BLOCKED_TOOL_NAMES,
    allowed_tools: Iterable[str] | None = None,
    trace_id: str | None = None,
    session_id: str | None = None,
    client_factory: Callable[[str, str], Any] | None = None,
    mcp_caller: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """跑一次 Claude tool-use loop，返回结构化 summary。

    返回 dict 字段：

    - ``exit_code``: ``OrchestrateExitCode`` 数值
    - ``iterations``: 实际迭代轮次
    - ``tool_calls``: 实际工具调用次数
    - ``tool_call_log``: ``[{tool, args, result_summary | error | blocked}]``
    - ``trace_id`` / ``session_id``: 16-hex，注入到所有工具调用、贯穿三端审计
    - ``stop_reason``: ``end_turn`` / ``tool_budget_exceeded`` / ``max_iterations_reached`` / ...
    - ``final_text``: Agent 最后一段文本输出
    - ``error``: 失败时的 error message

    所有错误都映射到 ``exit_code``，不抛到调用方 — 让 cron / UI worker 行为一致。
    """
    blocked_set = frozenset(blocked_tools)
    summary: dict[str, Any] = {
        "exit_code": int(OrchestrateExitCode.OK),
        "iterations": 0,
        "tool_calls": 0,
        "tool_call_log": [],
        "trace_id": trace_id or uuid.uuid4().hex[:16],
        "session_id": session_id or uuid.uuid4().hex[:16],
        "stop_reason": None,
        "final_text": "",
        "error": None,
    }

    if not (api_key or "").strip():
        logger.error("[exit] missing ANTHROPIC_API_KEY")
        summary["exit_code"] = int(OrchestrateExitCode.MISSING_API_KEY)
        summary["error"] = "missing ANTHROPIC_API_KEY"
        return summary

    # 1. 拉工具
    try:
        tools = discover_tools(
            url=mcp_url,
            token=mcp_token,
            blocked=blocked_set,
            allowed=allowed_tools,
            retries=mcp_retries,
            timeout=mcp_timeout,
            mcp_caller=mcp_caller,
        )
    except McpUnreachableError as exc:
        logger.error("[exit] mcp unreachable: %s", exc)
        summary["exit_code"] = int(OrchestrateExitCode.MCP_UNREACHABLE)
        summary["error"] = f"mcp unreachable: {exc}"
        return summary
    except Exception as exc:
        logger.exception("[exit] discover tools failed")
        summary["exit_code"] = int(OrchestrateExitCode.MCP_UNREACHABLE)
        summary["error"] = f"discover tools failed: {exc}"
        return summary

    if not tools:
        logger.error("[exit] no usable tools after filtering")
        summary["exit_code"] = int(OrchestrateExitCode.MCP_UNREACHABLE)
        summary["error"] = "no usable tools"
        return summary

    logger.info(
        "[init] %d tools available (blocked: %s)",
        len(tools),
        sorted(blocked_set),
    )

    # 2. 建 Anthropic client
    try:
        factory = client_factory or build_claude_client
        client = factory(api_key, base_url)
    except ClaudeApiError as exc:
        logger.error("[exit] %s", exc)
        summary["exit_code"] = int(OrchestrateExitCode.CLAUDE_API_ERROR)
        summary["error"] = str(exc)
        return summary

    # 3. tool-use 循环
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_prompt}]
    iterations = 0
    while iterations < max_iterations:
        iterations += 1
        try:
            response = call_claude(
                client,
                model=model,
                messages=messages,
                tools=tools,
                system=system_prompt,
                max_tokens=max_tokens,
            )
        except ClaudeApiError as exc:
            logger.error("[exit] claude api failed at iter %d: %s", iterations, exc)
            summary["exit_code"] = int(OrchestrateExitCode.CLAUDE_API_ERROR)
            summary["error"] = str(exc)
            summary["iterations"] = iterations
            return summary

        content_blocks = list(getattr(response, "content", []) or [])
        stop_reason = getattr(response, "stop_reason", None)

        # 把 assistant 回复加入历史
        messages.append(
            {"role": "assistant", "content": _content_blocks_to_dict(content_blocks)}
        )

        tool_uses = [
            block
            for block in content_blocks
            if getattr(block, "type", None) == "tool_use"
            or (isinstance(block, dict) and block.get("type") == "tool_use")
        ]
        text_blocks = [
            block
            for block in content_blocks
            if getattr(block, "type", None) == "text"
            or (isinstance(block, dict) and block.get("type") == "text")
        ]

        if not tool_uses:
            # 模型不再调工具 → 收尾
            summary["stop_reason"] = stop_reason or "end_turn"
            summary["final_text"] = "\n".join(
                (
                    getattr(b, "text", None)
                    if not isinstance(b, dict)
                    else b.get("text")
                )
                or ""
                for b in text_blocks
            ).strip()
            break

        # 执行工具，构造 tool_result
        tool_results: list[dict[str, Any]] = []
        budget_hit = False
        for tu in tool_uses:
            tool_name = (
                getattr(tu, "name", None)
                if not isinstance(tu, dict)
                else tu.get("name")
            ) or ""
            tool_input = (
                getattr(tu, "input", None)
                if not isinstance(tu, dict)
                else tu.get("input")
            ) or {}
            tool_use_id = (
                getattr(tu, "id", None) if not isinstance(tu, dict) else tu.get("id")
            ) or ""

            summary["tool_calls"] += 1

            if tool_name in blocked_set:
                msg = f"tool {tool_name} is blocked in unattended scan"
                logger.warning(
                    "[tool] %s BLOCKED args=%s", tool_name, _summarize(tool_input)
                )
                summary["tool_call_log"].append(
                    {"tool": tool_name, "blocked": True, "args": tool_input}
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": json.dumps(
                            {"ok": False, "error": msg}, ensure_ascii=False
                        ),
                        "is_error": True,
                    }
                )
                continue

            try:
                result = execute_tool(
                    tool_name,
                    tool_input,
                    url=mcp_url,
                    token=mcp_token,
                    trace_id=summary["trace_id"],
                    session_id=summary["session_id"],
                    operator=operator,
                    retries=mcp_retries,
                    timeout=mcp_timeout,
                    mcp_caller=mcp_caller,
                )
                logger.info(
                    "[tool] %s args=%s -> %s",
                    tool_name,
                    _summarize(tool_input),
                    _summarize(result),
                )
                summary["tool_call_log"].append(
                    {
                        "tool": tool_name,
                        "args": tool_input,
                        "result_summary": _summarize(result, limit=400),
                    }
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )
            except Exception as exc:  # noqa: BLE001 — 把任何工具失败转成 tool_result
                logger.exception("[tool] %s FAILED", tool_name)
                summary["tool_call_log"].append(
                    {"tool": tool_name, "args": tool_input, "error": str(exc)}
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": json.dumps(
                            {"ok": False, "error": str(exc)}, ensure_ascii=False
                        ),
                        "is_error": True,
                    }
                )

            if summary["tool_calls"] >= max_tools:
                logger.warning(
                    "[budget] tool budget %d exceeded, ending loop", max_tools
                )
                summary["stop_reason"] = "tool_budget_exceeded"
                budget_hit = True
                break

        messages.append({"role": "user", "content": tool_results})

        if budget_hit:
            break

    if summary["stop_reason"] is None:
        summary["stop_reason"] = "max_iterations_reached"
        logger.warning("[budget] max_iterations %d reached", max_iterations)

    summary["iterations"] = iterations
    logger.info(
        "[done] iterations=%d tool_calls=%d stop=%s",
        iterations,
        summary["tool_calls"],
        summary["stop_reason"],
    )
    return summary


__all__ = [
    "DEFAULT_MODEL",
    "DEFAULT_MAX_ITERATIONS",
    "DEFAULT_MAX_TOOLS",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_MCP_RETRIES",
    "DEFAULT_MCP_TIMEOUT",
    "DEFAULT_BLOCKED_TOOL_NAMES",
    "OrchestrateExitCode",
    "McpUnreachableError",
    "ClaudeApiError",
    "call_mcp",
    "discover_tools",
    "execute_tool",
    "build_claude_client",
    "call_claude",
    "orchestrate",
]
