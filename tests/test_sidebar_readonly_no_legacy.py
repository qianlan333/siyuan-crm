from __future__ import annotations

import inspect
from pathlib import Path

from aicrm_next.customer_read_model import api as customer_api


ROOT = Path(__file__).resolve().parents[1]


TARGET_FUNCTIONS = [
    customer_api.get_sidebar_customer_context,
    customer_api.get_sidebar_profile,
    customer_api.get_sidebar_tags,
    customer_api.get_sidebar_lead_pool_status,
    customer_api.get_sidebar_signup_tag_status,
    customer_api.get_sidebar_marketing_status,
    customer_api.get_sidebar_v2_workbench,
    customer_api.get_sidebar_v2_questionnaires,
    customer_api.get_sidebar_v2_materials,
    customer_api.get_sidebar_v2_image_thumbnail,
    customer_api.get_sidebar_v2_other_staff_messages,
    customer_api.get_sidebar_v2_products,
    customer_api.get_sidebar_v2_orders,
]


def test_sidebar_readonly_target_routes_do_not_call_legacy_sidebar_facade() -> None:
    combined = "\n".join(inspect.getsource(func) for func in TARGET_FUNCTIONS)

    assert "legacy_sidebar_read_facade" not in combined
    assert "forward_to_legacy_flask" not in combined
    assert "wecom_ability_service" not in combined


def test_sidebar_readonly_routes_are_not_production_compat_forwards() -> None:
    assert not (ROOT / "aicrm_next/production_compat/api.py").exists()
