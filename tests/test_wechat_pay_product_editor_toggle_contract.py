from __future__ import annotations

from pathlib import Path


TEMPLATE = Path("aicrm_next/commerce/templates/wechat_products.html")


def test_product_editor_toggles_are_persisted_business_enablement_controls() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")

    assert "展开配置" not in text
    assert "let afterActionEnabled = Boolean(product.completion_redirect_enabled || product.lead_channel_id);" in text
    assert "setAfterActionEnabled(Boolean(product.completion_redirect_enabled || product.lead_channel_id));" in text
    assert 'lead_channel_id: afterActionEnabled && afterActionMode === "lead"' in text
    assert 'const enabled = afterActionEnabled && afterActionMode === "redirect";' in text
    assert "setExternalPushActive(Boolean(externalPush.enabled));" in text
    assert "enabled: Boolean(externalPush.enabled)," in text
    assert "externalPushEnabled" not in text
    assert "支付成功外推" not in text
