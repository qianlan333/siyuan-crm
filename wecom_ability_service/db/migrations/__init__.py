from __future__ import annotations


def _ensure_automation_sop_v1_seed_data() -> None:
    from ...domains.automation_conversion import service as _svc

    _svc.ensure_sop_v1_defaults()


def _ensure_automation_agent_prompt_defaults() -> None:
    from ...domains.automation_conversion import service as _svc

    _svc.ensure_agent_prompt_defaults()
