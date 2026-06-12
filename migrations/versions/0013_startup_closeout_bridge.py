"""startup closeout bridge revision.

Revision ID: 0013
Revises: 0012_wechat_pay_products

This no-op migration restores the historical revision id referenced by
0014_alipay_pay. The schema work for this point in the chain had already been
materialized by surrounding migrations; keeping 0014's parent intact is safer
for production deployments than rewriting an already-merged revision.
"""
from __future__ import annotations


revision = "0013"
down_revision = "0012_wechat_pay_products"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
