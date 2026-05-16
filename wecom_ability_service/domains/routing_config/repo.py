from __future__ import annotations

from ...db import get_db
from ...infra.helpers import db_bool


def get_owner_role(userid: str):
    return get_db().execute(
        """
        SELECT userid, display_name, role, active, updated_at
        FROM owner_role_map
        WHERE userid = ?
        """,
        (userid,),
    ).fetchone()


def list_owner_role_map(active_only: bool = False):
    sql = """
        SELECT userid, display_name, role, active, updated_at
        FROM owner_role_map
    """
    params: list[object] = []
    if active_only:
        sql += " WHERE active = ?"
        params.append(db_bool(True))
    sql += " ORDER BY active DESC, display_name ASC, userid ASC"
    return get_db().execute(sql, tuple(params)).fetchall()


def get_routing_rule(rule_key: str):
    return get_db().execute(
        """
        SELECT
            rule_key,
            routing_alias,
            route_owner_userid,
            route_owner_role,
            routing_target,
            fallback_target,
            when_owner_role_sales,
            when_owner_role_delivery,
            active,
            updated_at
        FROM routing_rule_config
        WHERE rule_key = ?
        """,
        (str(rule_key or "").strip(),),
    ).fetchone()


def list_routing_rules(active_only: bool = False):
    sql = """
        SELECT
            rule_key,
            routing_alias,
            route_owner_userid,
            route_owner_role,
            routing_target,
            fallback_target,
            when_owner_role_sales,
            when_owner_role_delivery,
            active,
            updated_at
        FROM routing_rule_config
    """
    params: list[object] = []
    if active_only:
        sql += " WHERE active = ?"
        params.append(db_bool(True))
    sql += " ORDER BY active DESC, rule_key ASC"
    return get_db().execute(sql, tuple(params)).fetchall()


def upsert_routing_rule(
    *,
    rule_key: str,
    routing_alias: str,
    route_owner_userid: str,
    route_owner_role: str,
    routing_target: str,
    fallback_target: str,
    when_owner_role_sales: str,
    when_owner_role_delivery: str,
    active: bool,
) -> None:
    get_db().execute(
        """
        INSERT INTO routing_rule_config (
            rule_key,
            routing_alias,
            route_owner_userid,
            route_owner_role,
            routing_target,
            fallback_target,
            when_owner_role_sales,
            when_owner_role_delivery,
            active,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(rule_key) DO UPDATE SET
            routing_alias = excluded.routing_alias,
            route_owner_userid = excluded.route_owner_userid,
            route_owner_role = excluded.route_owner_role,
            routing_target = excluded.routing_target,
            fallback_target = excluded.fallback_target,
            when_owner_role_sales = excluded.when_owner_role_sales,
            when_owner_role_delivery = excluded.when_owner_role_delivery,
            active = excluded.active,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            str(rule_key or "").strip(),
            str(routing_alias or "").strip(),
            str(route_owner_userid or "").strip(),
            str(route_owner_role or "").strip(),
            str(routing_target or "").strip(),
            str(fallback_target or "").strip(),
            str(when_owner_role_sales or "").strip(),
            str(when_owner_role_delivery or "").strip(),
            db_bool(active),
        ),
    )
    get_db().commit()
