from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations/versions/0110_wechat_pay_mobile_projection.py"


def test_wechat_pay_mobile_projection_migration_is_chained_to_current_head() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision = "0110_wechat_pay_mobile_projection"' in source
    assert 'down_revision = "0109_questionnaire_auto_execute"' in source


def test_wechat_pay_mobile_projection_backfill_is_paid_valid_and_conflict_safe() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "o.status = 'paid' OR o.trade_state = 'SUCCESS'" in source
    assert "mobile ~ '^1[0-9]{10}$'" in source
    assert "mobile_unionid_count = 1" in source
    assert "other.unionid <> candidate.unionid" in source
    assert "ON CONFLICT (unionid) DO UPDATE SET" in source
    assert "WHERE COALESCE(crm_user_identity.mobile, '') = ''" in source
    assert "def downgrade()" in source
    assert "pass" in source.split("def downgrade()", 1)[1]
