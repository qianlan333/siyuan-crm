"""``cloud_orchestrator.external_agent`` 的纯单元测试 — 不连 PG / 不依赖 anthropic SDK。

覆盖：

- ``call_mcp`` happy / jsonrpc-error / 网络重试 / unreachable
- ``discover_tools`` 黑名单 + ``[WRITE]`` 描述过滤 + ``inputSchema`` ↔ ``input_schema`` 兼容 + ``allowed`` 白名单
- ``execute_tool`` 注入 ``__trace_id`` / ``__session_id`` / ``__operator``
- ``orchestrate`` 主流程：缺 API key、MCP 不可达、无可用工具、happy path、写工具拦截、tool budget、max iter、tool 异常恢复
- ``call_claude`` cache_control breakpoint
"""
from __future__ import annotations

import io
import json
import urllib.error
from types import SimpleNamespace
from typing import Any

import pytest

from wecom_ability_service.domains.cloud_orchestrator import external_agent as ea


# ---- call_mcp ----------------------------------------------------------
class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._buf = io.BytesIO(payload)

    def read(self) -> bytes:
        return self._buf.getvalue()

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


def _factory_recorder(call_log: list[dict[str, Any]]):
    def factory(url: str, *, data: bytes, headers: dict[str, str], method: str):
        call_log.append({"url": url, "data": data, "headers": dict(headers), "method": method})
        return SimpleNamespace(url=url, data=data, headers=headers, method=method)

    return factory


def test_call_mcp_returns_result_and_sets_bearer() -> None:
    log: list[dict[str, Any]] = []
    response_payload = json.dumps(
        {"jsonrpc": "2.0", "id": "x", "result": {"tools": [{"name": "ping"}]}}
    ).encode("utf-8")

    def opener(req: Any, timeout: int) -> _FakeResponse:
        return _FakeResponse(response_payload)

    out = ea.call_mcp(
        "tools/list",
        {},
        url="http://127.0.0.1:5000/mcp",
        token="abc",
        retries=1,
        timeout=5,
        request_factory=_factory_recorder(log),
        opener=opener,
    )
    assert out == {"tools": [{"name": "ping"}]}
    assert log and log[0]["headers"]["Authorization"] == "Bearer abc"
    body = json.loads(log[0]["data"].decode("utf-8"))
    assert body["jsonrpc"] == "2.0"
    assert body["method"] == "tools/list"


def test_call_mcp_jsonrpc_error_raises_runtimeerror() -> None:
    response_payload = json.dumps(
        {"jsonrpc": "2.0", "id": "x", "error": {"code": -32601, "message": "Method not found"}}
    ).encode("utf-8")

    def opener(req: Any, timeout: int) -> _FakeResponse:
        return _FakeResponse(response_payload)

    with pytest.raises(RuntimeError, match="Method not found"):
        ea.call_mcp(
            "weird",
            {},
            url="http://x",
            retries=1,
            timeout=1,
            opener=opener,
        )


def test_call_mcp_retries_then_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    sleep_calls: list[float] = []
    monkeypatch.setattr(ea.time, "sleep", lambda s: sleep_calls.append(s))

    attempts = {"n": 0}

    def opener(req: Any, timeout: int):
        attempts["n"] += 1
        raise urllib.error.URLError("connection refused")

    with pytest.raises(ea.McpUnreachableError, match="3 attempts"):
        ea.call_mcp(
            "tools/list",
            {},
            url="http://x",
            retries=3,
            timeout=1,
            opener=opener,
        )

    assert attempts["n"] == 3
    # 第 1、2 次失败后分别 sleep 1、3 秒；第 3 次失败后不 sleep（直接抛）
    assert sleep_calls == [1, 3]


# ---- discover_tools ----------------------------------------------------
def _fake_tool_payload() -> dict[str, Any]:
    return {
        "tools": [
            {
                "name": "search_segment_members",
                "description": "[DRAFT - 不发送] 多维筛选",
                "inputSchema": {"type": "object", "properties": {"keyword": {"type": "string"}}},
            },
            {
                "name": "draft_broadcast_plan",
                "description": "[DRAFT] 草稿群发",
                "input_schema": {"type": "object"},
            },
            {
                "name": "commit_broadcast_plan",
                "description": "[WRITE - 需要 approval_token] 真发",
                "inputSchema": {"type": "object"},
            },
            {
                "name": "request_copy_workorder",
                "description": "[ASYNC] 工单",
                "inputSchema": {"type": "object"},
            },
            {
                "name": "start_campaign",
                "description": "[WRITE - 需要 approval_token] 启动",
                "inputSchema": {"type": "object"},
            },
            {
                "name": "no_schema_tool",
                "description": "[DRAFT] 无 schema",
            },
        ]
    }


def test_discover_tools_filters_blocked_and_write_descriptions() -> None:
    captured: dict[str, Any] = {}

    def fake_caller(method: str, params: dict[str, Any] | None = None, **kw: Any) -> Any:
        captured["method"] = method
        captured["params"] = params
        captured["kw"] = kw
        return _fake_tool_payload()

    tools = ea.discover_tools(
        url="http://x",
        token="t",
        blocked=ea.DEFAULT_BLOCKED_TOOL_NAMES,
        retries=1,
        timeout=5,
        mcp_caller=fake_caller,
    )
    names = [t["name"] for t in tools]
    # 三个 blocked: commit_broadcast_plan / start_campaign / request_copy_workorder
    assert "commit_broadcast_plan" not in names
    assert "start_campaign" not in names
    assert "request_copy_workorder" not in names
    # draft 与 read-like 工具留下来
    assert "search_segment_members" in names
    assert "draft_broadcast_plan" in names
    assert "no_schema_tool" in names
    assert captured["method"] == "tools/list"
    # 强制 input_schema 字段（Anthropic 命名）
    for t in tools:
        assert "input_schema" in t
        assert isinstance(t["input_schema"], dict)


def test_discover_tools_handles_empty_payload() -> None:
    def fake_caller(method: str, params: dict[str, Any] | None = None, **kw: Any) -> Any:
        return {}

    tools = ea.discover_tools(url="http://x", token="", mcp_caller=fake_caller)
    assert tools == []


def test_discover_tools_allowed_whitelist_limits_to_subset() -> None:
    """``allowed`` 非空时只保留这些 tool — 给场景化定制用。"""
    def fake_caller(method: str, params: dict[str, Any] | None = None, **kw: Any) -> Any:
        return _fake_tool_payload()

    tools = ea.discover_tools(
        url="http://x",
        token="",
        allowed=["search_segment_members"],
        mcp_caller=fake_caller,
    )
    names = [t["name"] for t in tools]
    assert names == ["search_segment_members"]


# ---- execute_tool ------------------------------------------------------
def test_execute_tool_injects_trace_session_operator() -> None:
    captured: dict[str, Any] = {}

    def fake_caller(method: str, params: dict[str, Any] | None = None, **kw: Any) -> Any:
        captured["method"] = method
        captured["params"] = params
        return {"ok": True}

    out = ea.execute_tool(
        "search_segment_members",
        {"keyword": "vip"},
        url="http://x",
        token="t",
        trace_id="trc-123",
        session_id="sess-456",
        operator="alice",
        mcp_caller=fake_caller,
    )
    assert out == {"ok": True}
    assert captured["method"] == "tools/call"
    args = captured["params"]["arguments"]
    assert args["__trace_id"] == "trc-123"
    assert args["__session_id"] == "sess-456"
    assert args["__operator"] == "alice"
    assert args["keyword"] == "vip"


# ---- orchestrate() — 整段流程 ----------------------------------------
class _FakeBlock:
    """模拟 anthropic SDK 的 content block — 用对象属性形式（不是 dict）。"""

    def __init__(self, **fields: Any) -> None:
        for k, v in fields.items():
            setattr(self, k, v)


class _FakeResponseObj:
    def __init__(
        self,
        *,
        content: list[Any],
        stop_reason: str = "end_turn",
    ) -> None:
        self.content = content
        self.stop_reason = stop_reason


class _FakeAnthropicClient:
    """根据预设脚本依次返回 response，记录 messages.create 的调用参数。"""

    def __init__(self, responses: list[_FakeResponseObj]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.messages = self  # 让 client.messages.create 也能调到这

    def create(self, **kw: Any) -> _FakeResponseObj:
        # 深拷一份 messages — orchestrate() 会持续 append，避免 calls[i] 都指向同一引用
        snapshot = dict(kw)
        if "messages" in snapshot:
            snapshot["messages"] = [dict(m) for m in snapshot["messages"]]
        self.calls.append(snapshot)
        if not self._responses:
            raise AssertionError("no more fake responses")
        return self._responses.pop(0)


def _orchestrate(
    *,
    user_prompt: str = "测试 prompt",
    system_prompt: str = "测试 system",
    mcp_caller: Any = None,
    client: Any = None,
    **overrides: Any,
) -> dict[str, Any]:
    """简化 orchestrate() 调用 — 测试公用 wrapper。"""
    kwargs: dict[str, Any] = {
        "api_key": "sk-test",
        "mcp_url": "http://test/mcp",
        "mcp_token": "",
        "user_prompt": user_prompt,
        "system_prompt": system_prompt,
        "operator": "tester",
        "model": "claude-test",
        "max_iterations": overrides.pop("max_iterations", 12),
        "max_tools": overrides.pop("max_tools", 20),
        "max_tokens": 2048,
        "mcp_retries": 1,
        "mcp_timeout": 5,
    }
    kwargs.update(overrides)
    if mcp_caller is not None:
        kwargs["mcp_caller"] = mcp_caller
    if client is not None:
        kwargs["client_factory"] = lambda *a, **kw: client
    return ea.orchestrate(**kwargs)


def _tools_only_caller(
    tools: list[dict[str, Any]],
    *,
    on_call: Any = None,
) -> Any:
    """构造一个 mcp_caller — tools/list 返回 ``tools``；tools/call 走 ``on_call``。"""
    def _caller(method: str, params: dict[str, Any] | None = None, **kw: Any) -> Any:
        if method == "tools/list":
            return {"tools": tools}
        if method == "tools/call":
            if on_call is None:
                return {"ok": True}
            return on_call(params or {})
        raise AssertionError(f"unexpected mcp method: {method}")

    return _caller


def test_orchestrate_missing_api_key_returns_exit_1() -> None:
    out = ea.orchestrate(
        api_key="",
        mcp_url="http://x",
        user_prompt="x",
    )
    assert out["exit_code"] == int(ea.OrchestrateExitCode.MISSING_API_KEY)
    assert "ANTHROPIC_API_KEY" in (out["error"] or "")


def test_orchestrate_mcp_unreachable_returns_exit_3(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(method: str, params: dict[str, Any] | None = None, **kw: Any) -> Any:
        raise ea.McpUnreachableError("connection refused")

    out = _orchestrate(mcp_caller=_raise)
    assert out["exit_code"] == int(ea.OrchestrateExitCode.MCP_UNREACHABLE)
    assert "mcp unreachable" in (out["error"] or "")


def test_orchestrate_no_usable_tools_returns_exit_3() -> None:
    def _empty(method: str, params: dict[str, Any] | None = None, **kw: Any) -> Any:
        return {"tools": []}

    out = _orchestrate(mcp_caller=_empty)
    assert out["exit_code"] == int(ea.OrchestrateExitCode.MCP_UNREACHABLE)
    assert "no usable tools" in (out["error"] or "")


def test_orchestrate_happy_path_one_tool_then_done() -> None:
    """模型先调一次工具，再返回 end_turn 文本结论。"""
    tools_raw = [
        {
            "name": "search_segment_members",
            "description": "[DRAFT] 选人",
            "input_schema": {"type": "object"},
        }
    ]
    fake_client = _FakeAnthropicClient(
        responses=[
            _FakeResponseObj(
                content=[
                    _FakeBlock(type="text", text="先找人"),
                    _FakeBlock(
                        type="tool_use",
                        id="tu-1",
                        name="search_segment_members",
                        input={"keyword": "vip"},
                    ),
                ],
                stop_reason="tool_use",
            ),
            _FakeResponseObj(
                content=[
                    _FakeBlock(
                        type="text",
                        text="共 12 人；plan_id=draft-001",
                    )
                ],
                stop_reason="end_turn",
            ),
        ]
    )
    tool_calls: list[dict[str, Any]] = []

    def _on_call(params: dict[str, Any]) -> Any:
        tool_calls.append(params)
        return {"items": [{"id": 1}], "total": 12}

    out = _orchestrate(
        mcp_caller=_tools_only_caller(tools_raw, on_call=_on_call),
        client=fake_client,
    )
    assert out["exit_code"] == 0
    assert out["iterations"] == 2
    assert out["tool_calls"] == 1
    assert out["stop_reason"] == "end_turn"
    assert "plan_id" in out["final_text"]
    # trace_id / session_id 注入到 tools/call.arguments
    assert tool_calls[0]["arguments"]["__trace_id"] == out["trace_id"]
    assert tool_calls[0]["arguments"]["__session_id"] == out["session_id"]
    assert tool_calls[0]["arguments"]["__operator"] == "tester"


def test_orchestrate_blocks_blocked_tool_call_and_continues() -> None:
    """模型尝试调 commit_broadcast_plan → 应被 orchestrate() 拦截并通过 tool_result is_error=True 回传。"""
    tools_raw = [
        {
            "name": "draft_broadcast_plan",
            "description": "[DRAFT]",
            "input_schema": {"type": "object"},
        }
    ]
    fake_client = _FakeAnthropicClient(
        responses=[
            _FakeResponseObj(
                content=[
                    _FakeBlock(
                        type="tool_use",
                        id="tu-bad",
                        name="commit_broadcast_plan",
                        input={"plan_id": "x"},
                    )
                ],
                stop_reason="tool_use",
            ),
            _FakeResponseObj(
                content=[_FakeBlock(type="text", text="OK 我不 commit 了")],
                stop_reason="end_turn",
            ),
        ]
    )
    tool_calls: list[dict[str, Any]] = []

    def _on_call(params: dict[str, Any]) -> Any:
        tool_calls.append(params)
        return {"never": True}

    out = _orchestrate(
        mcp_caller=_tools_only_caller(tools_raw, on_call=_on_call),
        client=fake_client,
    )
    assert out["exit_code"] == 0
    # tools/call 不应被实际调用（BLOCKED 在 orchestrate 内部拦下）
    assert tool_calls == []
    log = out["tool_call_log"]
    assert any(item.get("blocked") for item in log)
    second_call_messages = fake_client.calls[1]["messages"]
    tool_result_block = second_call_messages[-1]["content"][0]
    assert tool_result_block["type"] == "tool_result"
    assert tool_result_block["is_error"] is True


def test_orchestrate_tool_budget_stops_loop() -> None:
    tools_raw = [
        {
            "name": "search_segment_members",
            "description": "[DRAFT]",
            "input_schema": {"type": "object"},
        }
    ]
    fake_client = _FakeAnthropicClient(
        responses=[
            _FakeResponseObj(
                content=[
                    _FakeBlock(
                        type="tool_use",
                        id=f"tu-{i}",
                        name="search_segment_members",
                        input={"page": i},
                    )
                    for i in range(3)
                ],
                stop_reason="tool_use",
            )
        ]
    )
    out = _orchestrate(
        mcp_caller=_tools_only_caller(tools_raw),
        client=fake_client,
        max_tools=2,
    )
    assert out["stop_reason"] == "tool_budget_exceeded"
    assert out["tool_calls"] == 2
    assert out["exit_code"] == 0


def test_orchestrate_max_iterations_stops_loop() -> None:
    tools_raw = [
        {
            "name": "search_segment_members",
            "description": "[DRAFT]",
            "input_schema": {"type": "object"},
        }
    ]

    def _new_resp() -> _FakeResponseObj:
        return _FakeResponseObj(
            content=[
                _FakeBlock(
                    type="tool_use",
                    id="tu-x",
                    name="search_segment_members",
                    input={},
                )
            ],
            stop_reason="tool_use",
        )

    fake_client = _FakeAnthropicClient(responses=[_new_resp(), _new_resp()])
    out = _orchestrate(
        mcp_caller=_tools_only_caller(tools_raw),
        client=fake_client,
        max_iterations=2,
        max_tools=100,
    )
    assert out["iterations"] == 2
    assert out["stop_reason"] == "max_iterations_reached"
    assert out["exit_code"] == 0


def test_orchestrate_tool_failure_recorded_but_loop_continues() -> None:
    """工具异常 → 转成 ``tool_result`` 报错回传，循环不中断。"""
    tools_raw = [
        {
            "name": "search_segment_members",
            "description": "[DRAFT]",
            "input_schema": {"type": "object"},
        }
    ]
    fake_client = _FakeAnthropicClient(
        responses=[
            _FakeResponseObj(
                content=[
                    _FakeBlock(
                        type="tool_use",
                        id="tu-1",
                        name="search_segment_members",
                        input={},
                    )
                ],
                stop_reason="tool_use",
            ),
            _FakeResponseObj(
                content=[_FakeBlock(type="text", text="收尾")],
                stop_reason="end_turn",
            ),
        ]
    )

    def _boom(params: dict[str, Any]) -> Any:
        raise RuntimeError("boom")

    out = _orchestrate(
        mcp_caller=_tools_only_caller(tools_raw, on_call=_boom),
        client=fake_client,
    )
    assert out["exit_code"] == 0
    assert any("error" in entry for entry in out["tool_call_log"])
    second_call_messages = fake_client.calls[1]["messages"]
    tool_result_block = second_call_messages[-1]["content"][0]
    assert tool_result_block["type"] == "tool_result"
    assert tool_result_block["is_error"] is True


def test_call_claude_applies_cache_control() -> None:
    """system + 最后一个 tool 都打 ``cache_control=ephemeral``。"""
    tools = [
        {"name": "a", "description": "...", "input_schema": {}},
        {"name": "b", "description": "...", "input_schema": {}},
    ]
    captured: dict[str, Any] = {}

    class _C:
        class messages:
            @staticmethod
            def create(**kw: Any) -> Any:
                captured.update(kw)
                return _FakeResponseObj(content=[], stop_reason="end_turn")

    ea.call_claude(
        _C,
        model="claude-test",
        messages=[{"role": "user", "content": "hi"}],
        tools=tools,
        system="sys",
        max_tokens=512,
    )
    sent_tools = captured["tools"]
    assert "cache_control" not in sent_tools[0]
    assert sent_tools[-1]["cache_control"] == {"type": "ephemeral"}
    sent_system = captured["system"]
    assert isinstance(sent_system, list)
    assert sent_system[0]["cache_control"] == {"type": "ephemeral"}


def test_orchestrate_passes_explicit_trace_and_session_ids() -> None:
    """允许调用方注入 trace_id/session_id（observability 链路对齐）。"""
    tools_raw = [
        {
            "name": "search_segment_members",
            "description": "[DRAFT]",
            "input_schema": {"type": "object"},
        }
    ]
    fake_client = _FakeAnthropicClient(
        responses=[
            _FakeResponseObj(
                content=[_FakeBlock(type="text", text="done")],
                stop_reason="end_turn",
            )
        ]
    )
    out = _orchestrate(
        mcp_caller=_tools_only_caller(tools_raw),
        client=fake_client,
        trace_id="trc-fixed",
        session_id="sess-fixed",
    )
    assert out["trace_id"] == "trc-fixed"
    assert out["session_id"] == "sess-fixed"
