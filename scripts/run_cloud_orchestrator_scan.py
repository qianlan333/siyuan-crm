"""定时扫描脚本 — 让 Cloud 编排端"自己醒过来"。

(2026-05-09 重写) 脚本本身即"外部 Cloud Agent"。
直接调 Anthropic Messages API + tool-use loop（实现在
``wecom_ability_service.domains.cloud_orchestrator.external_agent``），
工具调用走本地 MCP HTTP（POST /mcp）。不再依赖任何 CRM 后端的 sessions / SSE 端点。

cron 每天 N 点跑一次，无人值守地：

1. 默认 prompt：扫描沉默重点池用户、按 segment 归纳、对每组 ``draft_broadcast_plan``
2. ``tools/list`` 拉 cloud orchestrator 工具集 → 转 Anthropic ``input_schema`` 格式
3. 屏蔽 write 类工具：``commit_broadcast_plan`` / ``start_campaign`` / ``request_copy_workorder``
4. tool-use 循环 → 让 Claude 自助调 read / draft 工具，落地多份 plan 草稿
5. 真发动作均等运营在 UI 上 confirm 后才能触发

环境变量：

- ``ANTHROPIC_API_KEY`` (必填)
- ``ANTHROPIC_BASE_URL`` (可选自定义 endpoint)
- ``APP_HOST`` / ``APP_PORT`` (默认 127.0.0.1:5000，本地 ``/mcp`` 入口)
- ``MCP_BEARER_TOKEN`` (与 mcp_adapter 约定的 token；兼容老名 ``AUTOMATION_INTERNAL_API_TOKEN``)
- ``CLOUD_ORCH_SCAN_OPERATOR`` (默认 ``cloud_scheduler``)
- ``CLOUD_ORCH_SCAN_PROMPT`` (覆盖默认 prompt)
- ``CLOUD_ORCH_SCAN_SYSTEM`` (覆盖默认 system prompt)
- ``CLOUD_ORCH_SCAN_MODEL`` (默认 ``claude-opus-4-7``)
- ``CLOUD_ORCH_SCAN_MAX_ITER`` (默认 12)
- ``CLOUD_ORCH_SCAN_MAX_TOOLS`` (默认 20)
- ``CLOUD_ORCH_SCAN_MAX_TOKENS`` (默认 4096)
- ``CLOUD_ORCH_SCAN_MCP_RETRIES`` (默认 3，1s/3s/9s 退避)
- ``CLOUD_ORCH_SCAN_MCP_TIMEOUT`` (默认 60s)
- ``CLOUD_ORCH_SCAN_ALLOWED_TOOLS`` (可选 CSV 白名单，仅暴露这些工具给 Agent)

退出码（由 ``OrchestrateExitCode`` 决定）：

- ``0`` 正常完成（含主动 budget 截断）
- ``1`` 缺少 ``ANTHROPIC_API_KEY``
- ``2`` Claude API 调用失败（鉴权 / 网络 / 模型不可用）
- ``3`` 本地 MCP 不可达 / 无可用工具
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

# 让脚本在没安装 wecom_ability_service 包的环境下也能拿到 domain 模块
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from wecom_ability_service.domains.cloud_orchestrator import (  # noqa: E402
    external_agent,
)

# 默认 prompt / system prompt — 后续可走 DB 配置驱动（automation_agent_config.scenario_code）
DEFAULT_OPERATOR = "cloud_scheduler"
DEFAULT_PROMPT = (
    "扫描近 14 天没有任何回复但近 60 天有过触达的活跃-重点（active_focus）"
    "和不活跃-重点（inactive_focus）池用户，按 profile_segment_key 分组归纳，"
    "对每组提出一份激活方案 draft：使用 draft_broadcast_plan 工具创建草稿，"
    "scenario_code 用 silent_wake，等运营审核后再发。"
    "完成后用结构化结论回复：总沉默人数、按 segment 的草稿 plan_id 列表、跳过原因汇总。"
)
DEFAULT_SYSTEM_PROMPT = (
    "你是 CRM 系统的 Cloud 编排 Agent，由定时任务唤起，无人值守。"
    "你拥有一组 read / draft 工具，可以查询用户分层、互动统计、最近触达，"
    "并创建草稿型群发计划（draft_broadcast_plan / propose_campaign / propose_segment）。"
    "硬规则："
    "1. 你**没有权限**调任何 [WRITE] 标记的工具；不要尝试，会被拒绝。"
    "2. 所有真发都需要运营在 UI 上 confirm，不要假装能 commit。"
    "3. 完成任务后用结构化结论回答（segment / draft plan_id / 跳过原因）。"
    "4. 工具失败时，先调 query_recent_audit_logs 看 error_message 再换策略，最多重试 3 次。"
    "5. 单次任务总工具调用 ≤ 20。"
)

logger = logging.getLogger("cloud_orchestrator_scan")


def _resolve_env(env: dict[str, str] | None = None) -> dict[str, Any]:
    """从环境变量解析 ``orchestrate()`` 的 kwargs。

    抽出来是为了让单元测试不用 monkey-patch ``os.environ`` 也能跑。
    """
    e = dict(os.environ if env is None else env)
    host = (e.get("APP_HOST") or "").strip() or "127.0.0.1"
    port = (e.get("APP_PORT") or "").strip() or "5000"
    mcp_token = (e.get("MCP_BEARER_TOKEN") or "").strip() or (
        e.get("AUTOMATION_INTERNAL_API_TOKEN") or ""
    ).strip()
    allowed_csv = (e.get("CLOUD_ORCH_SCAN_ALLOWED_TOOLS") or "").strip()
    allowed = [s.strip() for s in allowed_csv.split(",") if s.strip()] or None
    return {
        "api_key": (e.get("ANTHROPIC_API_KEY") or "").strip(),
        "base_url": (e.get("ANTHROPIC_BASE_URL") or "").strip(),
        "mcp_url": f"http://{host}:{port}/mcp",
        "mcp_token": mcp_token,
        "user_prompt": (e.get("CLOUD_ORCH_SCAN_PROMPT") or "").strip() or DEFAULT_PROMPT,
        "system_prompt": (e.get("CLOUD_ORCH_SCAN_SYSTEM") or "").strip()
        or DEFAULT_SYSTEM_PROMPT,
        "operator": (e.get("CLOUD_ORCH_SCAN_OPERATOR") or "").strip() or DEFAULT_OPERATOR,
        "model": (e.get("CLOUD_ORCH_SCAN_MODEL") or "").strip()
        or external_agent.DEFAULT_MODEL,
        "max_iterations": int(
            e.get("CLOUD_ORCH_SCAN_MAX_ITER") or external_agent.DEFAULT_MAX_ITERATIONS
        ),
        "max_tools": int(
            e.get("CLOUD_ORCH_SCAN_MAX_TOOLS") or external_agent.DEFAULT_MAX_TOOLS
        ),
        "max_tokens": int(
            e.get("CLOUD_ORCH_SCAN_MAX_TOKENS") or external_agent.DEFAULT_MAX_TOKENS
        ),
        "mcp_retries": int(
            e.get("CLOUD_ORCH_SCAN_MCP_RETRIES") or external_agent.DEFAULT_MCP_RETRIES
        ),
        "mcp_timeout": int(
            e.get("CLOUD_ORCH_SCAN_MCP_TIMEOUT") or external_agent.DEFAULT_MCP_TIMEOUT
        ),
        "allowed_tools": allowed,
    }


def run(env: dict[str, str] | None = None) -> dict[str, Any]:
    """薄壳：从 env 解析 kwargs 后调 ``external_agent.orchestrate()``。"""
    kwargs = _resolve_env(env)
    return external_agent.orchestrate(**kwargs)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    summary = run()
    print(json.dumps(summary, ensure_ascii=False, default=str))
    return int(summary.get("exit_code", 0))


if __name__ == "__main__":
    sys.exit(main())
