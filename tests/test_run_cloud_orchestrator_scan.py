"""``scripts/run_cloud_orchestrator_scan.py`` 薄壳测试 — 只测环境变量解析 + 透传。

核心 tool-use loop 的覆盖在 ``test_cloud_orchestrator_external_agent.py``。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest


# 让 import 拿到 scripts/run_cloud_orchestrator_scan.py
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import run_cloud_orchestrator_scan as scan  # type: ignore[import-not-found]
from wecom_ability_service.domains.cloud_orchestrator import external_agent as ea


# ---- _resolve_env ------------------------------------------------------
def test_resolve_env_defaults_apply_when_env_empty() -> None:
    out = scan._resolve_env(env={"ANTHROPIC_API_KEY": "sk-test"})
    assert out["api_key"] == "sk-test"
    assert out["mcp_url"] == "http://127.0.0.1:5000/mcp"
    assert out["mcp_token"] == ""
    assert out["operator"] == scan.DEFAULT_OPERATOR
    assert out["model"] == ea.DEFAULT_MODEL
    assert out["max_iterations"] == ea.DEFAULT_MAX_ITERATIONS
    assert out["max_tools"] == ea.DEFAULT_MAX_TOOLS
    assert out["max_tokens"] == ea.DEFAULT_MAX_TOKENS
    assert out["mcp_retries"] == ea.DEFAULT_MCP_RETRIES
    assert out["mcp_timeout"] == ea.DEFAULT_MCP_TIMEOUT
    assert out["user_prompt"] == scan.DEFAULT_PROMPT
    assert out["system_prompt"] == scan.DEFAULT_SYSTEM_PROMPT
    assert out["allowed_tools"] is None


def test_resolve_env_overrides_take_effect() -> None:
    env = {
        "ANTHROPIC_API_KEY": "sk-test",
        "ANTHROPIC_BASE_URL": "https://example.invalid",
        "APP_HOST": "10.0.0.1",
        "APP_PORT": "8080",
        "MCP_BEARER_TOKEN": "tok-1",
        "CLOUD_ORCH_SCAN_OPERATOR": "alice",
        "CLOUD_ORCH_SCAN_PROMPT": "custom prompt",
        "CLOUD_ORCH_SCAN_SYSTEM": "custom system",
        "CLOUD_ORCH_SCAN_MODEL": "claude-sonnet-4-6",
        "CLOUD_ORCH_SCAN_MAX_ITER": "5",
        "CLOUD_ORCH_SCAN_MAX_TOOLS": "8",
        "CLOUD_ORCH_SCAN_MAX_TOKENS": "1024",
        "CLOUD_ORCH_SCAN_MCP_RETRIES": "1",
        "CLOUD_ORCH_SCAN_MCP_TIMEOUT": "10",
        "CLOUD_ORCH_SCAN_ALLOWED_TOOLS": "search_segment_members, draft_broadcast_plan",
    }
    out = scan._resolve_env(env=env)
    assert out["base_url"] == "https://example.invalid"
    assert out["mcp_url"] == "http://10.0.0.1:8080/mcp"
    assert out["mcp_token"] == "tok-1"
    assert out["operator"] == "alice"
    assert out["user_prompt"] == "custom prompt"
    assert out["system_prompt"] == "custom system"
    assert out["model"] == "claude-sonnet-4-6"
    assert out["max_iterations"] == 5
    assert out["max_tools"] == 8
    assert out["max_tokens"] == 1024
    assert out["mcp_retries"] == 1
    assert out["mcp_timeout"] == 10
    assert out["allowed_tools"] == ["search_segment_members", "draft_broadcast_plan"]


def test_resolve_env_legacy_token_env_works() -> None:
    out = scan._resolve_env(
        env={
            "ANTHROPIC_API_KEY": "sk-x",
            "AUTOMATION_INTERNAL_API_TOKEN": "legacy",
        }
    )
    assert out["mcp_token"] == "legacy"


# ---- run() 透传 -------------------------------------------------------
def test_run_passes_env_kwargs_to_orchestrate(monkeypatch: pytest.MonkeyPatch) -> None:
    """``run()`` 应把 ``_resolve_env`` 的全部 kwargs 透给 ``external_agent.orchestrate()``。"""
    captured: dict[str, Any] = {}
    sentinel = {"exit_code": 0, "iterations": 0}

    def _fake_orchestrate(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(scan.external_agent, "orchestrate", _fake_orchestrate)
    out = scan.run(env={"ANTHROPIC_API_KEY": "sk-test"})
    assert out is sentinel
    # 关键 kwargs 全都被传过去
    assert captured["api_key"] == "sk-test"
    assert captured["mcp_url"] == "http://127.0.0.1:5000/mcp"
    assert captured["user_prompt"] == scan.DEFAULT_PROMPT
    assert captured["system_prompt"] == scan.DEFAULT_SYSTEM_PROMPT
    assert captured["operator"] == scan.DEFAULT_OPERATOR


def test_run_missing_api_key_returns_exit_1_via_orchestrate() -> None:
    """没 patch orchestrate — 走真链路，但因为 api_key 为空，orchestrate 在第一步就退。"""
    out = scan.run(env={})
    assert out["exit_code"] == int(ea.OrchestrateExitCode.MISSING_API_KEY)


def test_main_returns_exit_code_from_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """``main()`` 把 summary 的 ``exit_code`` 作为进程退出码。"""
    captured_print: list[str] = []

    def _fake_run(env: Any = None) -> dict[str, Any]:
        return {"exit_code": 2, "error": "fake claude api"}

    monkeypatch.setattr(scan, "run", _fake_run)
    monkeypatch.setattr("builtins.print", lambda s: captured_print.append(s))

    rc = scan.main()
    assert rc == 2
    # 打印的 summary 是 JSON
    assert captured_print
    assert '"exit_code": 2' in captured_print[0]
