from __future__ import annotations

from flask import url_for

from ..domains.admin_api_docs.service import _api_endpoint_groups, build_api_docs_view_model
from .admin_console import _breadcrumb_items, _render_admin_template


def admin_console_api_docs():
    view_model = build_api_docs_view_model()
    return _render_admin_template(
        "api_docs.html",
        active_nav="api_docs",
        page_title="API 文档",
        page_summary="后台全量 API 参考文档。适用于开发者集成和 AI Agent 直接调用。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("API 文档", None)),
        **view_model,
    )


def register_routes(bp):
    bp.route("/admin/api-docs", methods=["GET"])(admin_console_api_docs)


__all__ = [
    "_api_endpoint_groups",
    "admin_console_api_docs",
    "register_routes",
]
