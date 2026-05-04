from __future__ import annotations

from flask import redirect, url_for


def admin_console_mcp():
    # Legacy console page is retired; keep route as compatibility redirect only.
    return redirect(url_for("api.admin_console_api_docs"), code=302)


def register_routes(bp):
    bp.route("/admin/mcp", methods=["GET"])(admin_console_mcp)
    bp.route("/admin/mcp/preflight", methods=["POST"])(admin_console_mcp)
    bp.route("/admin/mcp/sample-call", methods=["POST"])(admin_console_mcp)
