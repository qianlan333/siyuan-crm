from __future__ import annotations

from typing import Any

from ...db import get_db
from ...db.helpers import fetchall_dicts, fetchone_dict


def get_profile_fields(external_userid: str) -> dict[str, Any] | None:
    return fetchone_dict(
        get_db(),
        """
        SELECT external_userid, source, industry, industry_description,
               needs_blockers_followup, updated_by, updated_at
        FROM sidebar_customer_profile_fields
        WHERE external_userid = ?
        """,
        (str(external_userid or "").strip(),),
    )


def upsert_profile_fields(
    *,
    external_userid: str,
    source: str,
    industry: str,
    industry_description: str,
    needs_blockers_followup: str,
    updated_by: str,
) -> dict[str, Any]:
    db = get_db()
    row = db.execute(
        """
        INSERT INTO sidebar_customer_profile_fields (
            external_userid, source, industry, industry_description,
            needs_blockers_followup, updated_by, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT (external_userid) DO UPDATE SET
            source = EXCLUDED.source,
            industry = EXCLUDED.industry,
            industry_description = EXCLUDED.industry_description,
            needs_blockers_followup = EXCLUDED.needs_blockers_followup,
            updated_by = EXCLUDED.updated_by,
            updated_at = CURRENT_TIMESTAMP
        RETURNING external_userid, source, industry, industry_description,
                  needs_blockers_followup, updated_by, updated_at
        """,
        (
            str(external_userid or "").strip(),
            source,
            industry,
            industry_description,
            needs_blockers_followup,
            updated_by,
        ),
    ).fetchone()
    db.commit()
    return dict(row or {})


def get_workflow_title_for_customer(external_userid: str) -> str:
    row = fetchone_dict(
        get_db(),
        """
        SELECT COALESCE(NULLIF(w.workflow_name, ''), NULLIF(p.program_name, ''), NULLIF(c.channel_name, '')) AS title
        FROM automation_member m
        LEFT JOIN automation_channel c ON c.id = m.source_channel_id
        LEFT JOIN automation_program p ON p.id = c.program_id
        LEFT JOIN wecom_customer_acquisition_links l ON l.automation_channel_id = c.id
        LEFT JOIN automation_workflow w ON w.id = l.workflow_id
        WHERE m.external_contact_id = ?
        ORDER BY m.updated_at DESC, m.id DESC
        LIMIT 1
        """,
        (str(external_userid or "").strip(),),
    )
    return str((row or {}).get("title") or "").strip()


def get_contact_snapshot(external_userid: str) -> dict[str, Any] | None:
    return fetchone_dict(
        get_db(),
        """
        SELECT external_userid, customer_name, owner_userid, remark, description
        FROM contacts
        WHERE external_userid = ?
        """,
        (str(external_userid or "").strip(),),
    )


def get_external_identity_snapshot(external_userid: str) -> dict[str, Any] | None:
    return fetchone_dict(
        get_db(),
        """
        SELECT external_userid, follow_user_userid, name, unionid, openid, status
        FROM wecom_external_contact_identity_map
        WHERE external_userid = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (str(external_userid or "").strip(),),
    )


def get_bindable_wechat_pay_order_mobile(external_userid: str) -> dict[str, Any] | None:
    normalized_external_userid = str(external_userid or "").strip()
    if not normalized_external_userid:
        return None
    rows = fetchall_dicts(
        get_db(),
        """
        WITH target(external_userid) AS (
            VALUES (?)
        ),
        identity_openids AS (
            SELECT m.openid
            FROM wecom_external_contact_identity_map m
            JOIN target t ON m.external_userid = t.external_userid
            WHERE COALESCE(m.openid, '') <> ''
        ),
        identity_unionids AS (
            SELECT m.unionid
            FROM wecom_external_contact_identity_map m
            JOIN target t ON m.external_userid = t.external_userid
            WHERE COALESCE(m.unionid, '') <> ''
        ),
        matching_orders AS (
            SELECT mobile_snapshot, userid_snapshot, paid_at, created_at, id
            FROM wechat_pay_orders
            WHERE COALESCE(mobile_snapshot, '') <> ''
              AND (status = 'paid' OR trade_state = 'SUCCESS')
              AND (
                (
                    COALESCE(external_userid, '') <> ''
                    AND external_userid = (SELECT external_userid FROM target)
                )
                OR (
                    COALESCE(payer_openid, '') <> ''
                    AND payer_openid IN (SELECT openid FROM identity_openids)
                )
                OR (
                    COALESCE(unionid, '') <> ''
                    AND unionid IN (SELECT unionid FROM identity_unionids)
                )
              )
        )
        SELECT
            mobile_snapshot,
            MAX(COALESCE(NULLIF(userid_snapshot, ''), '')) AS userid_snapshot,
            COUNT(*) AS order_count,
            MAX(COALESCE(paid_at, created_at)) AS latest_order_at
        FROM matching_orders
        GROUP BY mobile_snapshot
        ORDER BY latest_order_at DESC, mobile_snapshot ASC
        LIMIT 2
        """,
        (normalized_external_userid,),
    )
    if len(rows) != 1:
        return None
    return rows[0]


def list_customer_wechat_pay_orders(
    *,
    external_userid: str,
    mobile: str = "",
    limit: int = 20,
) -> list[dict[str, Any]]:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_mobile = str(mobile or "").strip()
    if not normalized_external_userid and not normalized_mobile:
        return []
    return fetchall_dicts(
        get_db(),
        """
        WITH target(external_userid, mobile) AS (
            VALUES (?, ?)
        ),
        bound_mobiles AS (
            SELECT p.mobile
            FROM external_contact_bindings b
            JOIN people p ON p.id = b.person_id
            JOIN target t ON b.external_userid = t.external_userid
            WHERE COALESCE(p.mobile, '') <> ''
            UNION
            SELECT mobile
            FROM target
            WHERE COALESCE(mobile, '') <> ''
        ),
        identity_openids AS (
            SELECT m.openid
            FROM wecom_external_contact_identity_map m
            JOIN target t ON m.external_userid = t.external_userid
            WHERE COALESCE(m.openid, '') <> ''
        ),
        identity_unionids AS (
            SELECT m.unionid
            FROM wecom_external_contact_identity_map m
            JOIN target t ON m.external_userid = t.external_userid
            WHERE COALESCE(m.unionid, '') <> ''
        )
        SELECT
            id,
            out_trade_no,
            transaction_id,
            product_code,
            COALESCE(NULLIF(product_name, ''), product_code) AS product_name,
            amount_total,
            currency,
            external_userid AS order_external_userid,
            mobile_snapshot,
            payer_openid,
            unionid,
            status,
            trade_state,
            refunded_amount_total,
            refund_status,
            paid_at,
            created_at
        FROM wechat_pay_orders
        WHERE (
            (
                COALESCE(external_userid, '') <> ''
                AND external_userid = (SELECT external_userid FROM target)
            )
            OR (
                COALESCE(mobile_snapshot, '') <> ''
                AND mobile_snapshot IN (SELECT mobile FROM bound_mobiles)
            )
            OR (
                COALESCE(payer_openid, '') <> ''
                AND payer_openid IN (SELECT openid FROM identity_openids)
            )
            OR (
                COALESCE(unionid, '') <> ''
                AND unionid IN (SELECT unionid FROM identity_unionids)
            )
        )
        ORDER BY COALESCE(paid_at, created_at) DESC, id DESC
        LIMIT ?
        """,
        (normalized_external_userid, normalized_mobile, max(1, min(int(limit or 20), 100))),
    )
