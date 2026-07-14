from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations/versions/0111_wechat_shop_mobile_projection.py"


def test_wechat_shop_mobile_projection_migration_is_conflict_safe() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision = "0111_wechat_shop_mobile_projection"' in source
    assert 'down_revision = "0110_wechat_pay_mobile_projection"' in source
    assert "FROM wechat_shop_orders o" in source
    assert "o.paid_at IS NOT NULL" in source
    assert "mobile_unionid_count = 1" in source
    assert "other.unionid <> candidate.unionid" in source
    assert "WHERE COALESCE(crm_user_identity.mobile, '') = ''" in source
    assert "'wechat_shop_order'" in source
    assert "deleting verified customer contact data would be destructive" in source
