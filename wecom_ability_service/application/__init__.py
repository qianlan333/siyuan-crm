"""Wave 1 application namespace skeleton.

This package defines the formal application entrypoints that will be adopted by
HTTP/MCP callers in later PRs. In PR 2 the modules stay as thin delegates to
legacy implementations and must not introduce new business logic.
"""

__all__ = [
    "ai_assist",
    "automation_engine",
    "questionnaire",
    "customer_read_model",
    "integration_gateway",
    "platform_foundation",
]
