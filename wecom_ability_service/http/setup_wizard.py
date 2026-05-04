from __future__ import annotations

from flask import current_app, redirect, render_template, request, url_for

from ..infra.config_schema import CONFIG_SCHEMA, build_config_checklist, validate_config
from ..infra.settings import get_setting, mask_value, set_settings, SENSITIVE_KEYS


def _current_setting_values() -> dict[str, str]:
    config = current_app.config
    values: dict[str, str] = {}
    for group in CONFIG_SCHEMA.values():
        for field_key, field in group["fields"].items():
            db_val = get_setting(field_key)
            if db_val is not None:
                values[field_key] = db_val
            else:
                env_val = str(config.get(field_key, "") or "").strip()
                if env_val:
                    values[field_key] = env_val
    return values


def _masked_setting_values() -> dict[str, str]:
    raw = _current_setting_values()
    return {k: mask_value(k, v) for k, v in raw.items()}


def setup_wizard():
    schema_groups = [
        {"label": group["label"], "required": group.get("required", False), "fields": group["fields"]}
        for group in CONFIG_SCHEMA.values()
    ]
    return render_template(
        "admin_console/setup_wizard.html",
        schema_groups=schema_groups,
        current_values=_masked_setting_values(),
        validation_errors=[],
        save_success=False,
        admin_action_token="",
    )


def setup_wizard_save():
    form = request.form
    operator = form.get("operator", "").strip() or "unknown"

    settings_to_save: dict[str, str] = {}
    for key in form:
        if not key.startswith("setting__"):
            continue
        field_key = key[len("setting__"):]
        value = form[key].strip()
        if field_key in SENSITIVE_KEYS and not value:
            continue
        settings_to_save[field_key] = value

    merged = _current_setting_values()
    merged.update(settings_to_save)
    errors = validate_config(merged)

    if errors:
        schema_groups = [
            {"label": group["label"], "required": group.get("required", False), "fields": group["fields"]}
            for group in CONFIG_SCHEMA.values()
        ]
        return render_template(
            "admin_console/setup_wizard.html",
            schema_groups=schema_groups,
            current_values=_masked_setting_values(),
            validation_errors=errors,
            save_success=False,
            admin_action_token="",
        )

    if settings_to_save:
        set_settings(settings_to_save)

    schema_groups = [
        {"label": group["label"], "required": group.get("required", False), "fields": group["fields"]}
        for group in CONFIG_SCHEMA.values()
    ]
    return render_template(
        "admin_console/setup_wizard.html",
        schema_groups=schema_groups,
        current_values=_masked_setting_values(),
        validation_errors=[],
        save_success=True,
        admin_action_token="",
    )


def config_checklist_page():
    from .admin_config import _render_config_template

    settings = _current_setting_values()
    checklist = build_config_checklist(settings)
    return _render_config_template(
        "config_checklist.html",
        active_tab="checklist",
        page_title="配置检查清单",
        page_summary="新客户接入时按照此清单逐项配置，必填项标红星，绿色表示已配置。",
        breadcrumbs=[
            {"label": "客户管理后台", "href": url_for("api.admin_console_home")},
            {"label": "配置中心", "href": url_for("api.admin_config_home")},
            {"label": "配置检查清单", "href": ""},
        ],
        checklist=checklist,
    )


def register_routes(bp):
    bp.route('/setup/wizard', methods=['GET'])(setup_wizard)
    bp.route('/setup/wizard/save', methods=['POST'])(setup_wizard_save)
    bp.route('/admin/config/checklist', methods=['GET'])(config_checklist_page)
