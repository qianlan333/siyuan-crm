from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import secrets
from typing import Any, Protocol

from aicrm_next.shared.repository_provider import RepositoryProviderError, assert_repository_allowed
from aicrm_next.shared.runtime import production_data_ready, raw_database_url


def _psycopg_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    return url


class RadarLinksRepository(Protocol):
    def list_links(self, *, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]: ...
    def get_link(self, link_id: int) -> dict[str, Any] | None: ...
    def get_link_by_code(self, code: str) -> dict[str, Any] | None: ...
    def save_link(self, payload: dict[str, Any], link_id: int | None = None) -> dict[str, Any]: ...
    def set_enabled(self, link_id: int, enabled: bool) -> dict[str, Any] | None: ...
    def record_click_event(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def list_click_events(
        self,
        link_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
        stage: str = "",
        start_at: str = "",
        end_at: str = "",
    ) -> tuple[list[dict[str, Any]], int]: ...
    def stats(self, link_id: int) -> dict[str, Any] | None: ...
    def set_pdf_processing_status(
        self,
        link_id: int,
        *,
        status: str,
        page_count: int = 0,
        error_code: str = "",
        error_message: str = "",
    ) -> dict[str, Any] | None: ...
    def replace_pdf_preview_assets(self, link_id: int, media_item_id: str, assets: list[dict[str, Any]]) -> None: ...
    def list_pdf_preview_assets(self, link_id: int, media_item_id: str) -> list[dict[str, Any]]: ...
    def get_pdf_preview_asset(self, link_id: int, media_item_id: str, page_no: int) -> dict[str, Any] | None: ...


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _today_prefix() -> str:
    return datetime.now(timezone.utc).date().isoformat()


class InMemoryRadarLinksRepository:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._links: list[dict[str, Any]] = []
        self._events: list[dict[str, Any]] = []
        self._pdf_assets: list[dict[str, Any]] = []
        self._next_id = 1
        self._next_event_id = 1
        self._next_pdf_asset_id = 1

    def _new_code(self) -> str:
        while True:
            code = secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:8]
            if code and not self.get_link_by_code(code):
                return code

    def list_links(self, *, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        rows = deepcopy(sorted(self._links, key=lambda item: int(item["id"]), reverse=True))
        return rows[offset : offset + limit], len(rows)

    def get_link(self, link_id: int) -> dict[str, Any] | None:
        for item in self._links:
            if int(item["id"]) == int(link_id):
                return deepcopy(item)
        return None

    def get_link_by_code(self, code: str) -> dict[str, Any] | None:
        normalized = str(code or "").strip()
        for item in self._links:
            if item.get("code") == normalized:
                return deepcopy(item)
        return None

    def save_link(self, payload: dict[str, Any], link_id: int | None = None) -> dict[str, Any]:
        now = _now()
        if link_id is None:
            item = {
                "id": self._next_id,
                "code": self._new_code(),
                "created_at": now,
            }
            self._next_id += 1
            self._links.append(item)
        else:
            item = next((entry for entry in self._links if int(entry["id"]) == int(link_id)), None)
            if item is None:
                return {}
        item.update(
            {
                "title": str(payload.get("title", item.get("title", "")) or "").strip(),
                "target_type": str(payload.get("target_type", item.get("target_type", "link")) or "link").strip() or "link",
                "original_url": str(payload.get("original_url", item.get("original_url", "")) or "").strip(),
                "media_item_id": str(payload.get("media_item_id", item.get("media_item_id", "")) or "").strip(),
                "preview_mode": str(payload.get("preview_mode", item.get("preview_mode", "")) or "").strip(),
                "file_name_snapshot": str(payload.get("file_name_snapshot", item.get("file_name_snapshot", "")) or "").strip(),
                "mime_type_snapshot": str(payload.get("mime_type_snapshot", item.get("mime_type_snapshot", "")) or "").strip(),
                "file_size_snapshot": int(payload.get("file_size_snapshot", item.get("file_size_snapshot", 0)) or 0),
                "pdf_processing_status": str(payload.get("pdf_processing_status", item.get("pdf_processing_status", "")) or "").strip(),
                "pdf_page_count": int(payload.get("pdf_page_count", item.get("pdf_page_count", 0)) or 0),
                "pdf_preview_error_code": str(payload.get("pdf_preview_error_code", item.get("pdf_preview_error_code", "")) or "").strip(),
                "pdf_preview_error_message": str(payload.get("pdf_preview_error_message", item.get("pdf_preview_error_message", "")) or "").strip(),
                "enabled": bool(payload.get("enabled", item.get("enabled", True))),
                "auth_required": bool(payload.get("auth_required", item.get("auth_required", True))),
                "source_channel": str(payload.get("source_channel", item.get("source_channel", "")) or "").strip(),
                "campaign_id": str(payload.get("campaign_id", item.get("campaign_id", "")) or "").strip(),
                "staff_id": str(payload.get("staff_id", item.get("staff_id", "")) or "").strip(),
                "created_by": str(payload.get("created_by", item.get("created_by", "")) or "").strip(),
                "updated_at": now,
            }
        )
        return deepcopy(item)

    def set_enabled(self, link_id: int, enabled: bool) -> dict[str, Any] | None:
        item = next((entry for entry in self._links if int(entry["id"]) == int(link_id)), None)
        if item is None:
            return None
        item["enabled"] = bool(enabled)
        item["updated_at"] = _now()
        return deepcopy(item)

    def record_click_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        event = deepcopy(payload)
        event["id"] = self._next_event_id
        event["event_id"] = self._next_event_id
        event.setdefault("target_type_snapshot", "")
        event.setdefault("person_id", "")
        event.setdefault("ip_hash", "")
        event.setdefault("referer", "")
        event.setdefault("query_params_json", {})
        event.setdefault("source_channel_snapshot", event.get("source_channel", ""))
        event.setdefault("campaign_id_snapshot", event.get("campaign_id", ""))
        event.setdefault("staff_id_snapshot", event.get("staff_id", ""))
        event.setdefault("error_code", "")
        event["created_at"] = event.get("created_at") or _now()
        self._next_event_id += 1
        self._events.append(event)
        return deepcopy(event)

    def list_click_events(
        self,
        link_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
        stage: str = "",
        start_at: str = "",
        end_at: str = "",
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [
            deepcopy(item)
            for item in reversed(self._events)
            if int(item.get("link_id") or 0) == int(link_id)
        ]
        stage_filter = str(stage or "").strip()
        if stage_filter:
            rows = [item for item in rows if str(item.get("stage") or "") == stage_filter]
        start_filter = str(start_at or "").strip()
        if start_filter:
            rows = [item for item in rows if str(item.get("created_at") or "") >= start_filter]
        end_filter = str(end_at or "").strip()
        if end_filter:
            rows = [item for item in rows if str(item.get("created_at") or "") <= end_filter]
        return rows[offset : offset + limit], len(rows)

    def stats(self, link_id: int) -> dict[str, Any] | None:
        if not self.get_link(link_id):
            return None
        events = [item for item in self._events if int(item.get("link_id") or 0) == int(link_id)]
        landing_events = [item for item in events if item.get("stage") == "landing"]
        authorized_events = [item for item in events if item.get("stage") in {"authorized", "authorized_click"}]
        redirect_events = [item for item in events if item.get("stage") == "redirect"]
        viewer_events = [item for item in events if item.get("stage") == "viewer_open"]
        image_loaded_events = [item for item in events if item.get("stage") == "image_loaded"]
        pdf_opened_events = [item for item in events if item.get("stage") == "pdf_opened"]
        unique_users = {
            str(item.get("unionid") or item.get("openid") or item.get("external_userid") or "").strip()
            for item in authorized_events
            if str(item.get("unionid") or item.get("openid") or item.get("external_userid") or "").strip()
        }
        today = _today_prefix()
        last_clicked_at = ""
        if landing_events:
            last_clicked_at = max(str(item.get("created_at") or "") for item in landing_events)
        last_event_at = max([str(item.get("created_at") or "") for item in events] or [""])
        last_viewed_at = max([str(item.get("created_at") or "") for item in viewer_events + image_loaded_events + pdf_opened_events] or [""])
        return {
            "total_clicks": len(landing_events),
            "total_landings": len(landing_events),
            "authorized_clicks": len(authorized_events),
            "unique_users": len(unique_users),
            "authorized_users": len(unique_users),
            "redirects": len(redirect_events),
            "viewer_opens": len(viewer_events),
            "view_opens": len(viewer_events),
            "image_loaded": len(image_loaded_events),
            "pdf_opened": len(pdf_opened_events),
            "today_clicks": len([item for item in landing_events if str(item.get("created_at") or "").startswith(today)]),
            "today_landings": len([item for item in landing_events if str(item.get("created_at") or "").startswith(today)]),
            "last_clicked_at": last_clicked_at,
            "last_event_at": last_event_at,
            "last_viewed_at": last_viewed_at,
        }

    def set_pdf_processing_status(
        self,
        link_id: int,
        *,
        status: str,
        page_count: int = 0,
        error_code: str = "",
        error_message: str = "",
    ) -> dict[str, Any] | None:
        item = next((entry for entry in self._links if int(entry["id"]) == int(link_id)), None)
        if item is None:
            return None
        item["pdf_processing_status"] = str(status or "").strip()
        item["pdf_page_count"] = int(page_count or 0)
        item["pdf_preview_error_code"] = str(error_code or "").strip()
        item["pdf_preview_error_message"] = str(error_message or "").strip()
        item["updated_at"] = _now()
        return deepcopy(item)

    def replace_pdf_preview_assets(self, link_id: int, media_item_id: str, assets: list[dict[str, Any]]) -> None:
        normalized_media_id = str(media_item_id or "").strip()
        self._pdf_assets = [
            item
            for item in self._pdf_assets
            if not (int(item.get("link_id") or 0) == int(link_id) and str(item.get("media_item_id") or "") == normalized_media_id)
        ]
        for asset in assets:
            row = deepcopy(asset)
            row["id"] = self._next_pdf_asset_id
            self._next_pdf_asset_id += 1
            row["link_id"] = int(link_id)
            row["media_item_id"] = normalized_media_id
            row["created_at"] = row.get("created_at") or _now()
            row["updated_at"] = row.get("updated_at") or _now()
            self._pdf_assets.append(row)

    def list_pdf_preview_assets(self, link_id: int, media_item_id: str) -> list[dict[str, Any]]:
        normalized_media_id = str(media_item_id or "").strip()
        rows = [
            deepcopy(item)
            for item in self._pdf_assets
            if int(item.get("link_id") or 0) == int(link_id) and str(item.get("media_item_id") or "") == normalized_media_id
        ]
        rows.sort(key=lambda item: int(item.get("page_no") or 0))
        return rows

    def get_pdf_preview_asset(self, link_id: int, media_item_id: str, page_no: int) -> dict[str, Any] | None:
        for item in self.list_pdf_preview_assets(link_id, media_item_id):
            if int(item.get("page_no") or 0) == int(page_no):
                return item
        return None


class PostgresRadarLinksRepository:
    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = _psycopg_url(str(database_url or raw_database_url()).strip())
        if not self._database_url:
            raise RepositoryProviderError("radar_links production repository unavailable: DATABASE_URL is required")

    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row

            return psycopg.connect(self._database_url, row_factory=dict_row)
        except Exception as exc:
            raise RepositoryProviderError(f"radar_links production repository unavailable: {exc}") from exc

    @staticmethod
    def _row(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return dict(row)

    @staticmethod
    def _link_select_columns() -> str:
        return """
            id, code, title, target_type, original_url, media_item_id, preview_mode,
            file_name_snapshot, mime_type_snapshot, file_size_snapshot,
            pdf_processing_status, pdf_page_count, pdf_preview_error_code, pdf_preview_error_message,
            enabled, auth_required, source_channel, campaign_id, staff_id, created_by,
            created_at, updated_at, deleted_at
        """

    def _new_code(self, conn) -> str:
        while True:
            code = secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:8]
            exists = conn.execute("SELECT 1 FROM radar_links WHERE code = %s", (code,)).fetchone()
            if code and not exists:
                return code

    def list_links(self, *, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        limit = max(1, min(int(limit or 50), 200))
        offset = max(0, int(offset or 0))
        with self._connect() as conn:
            total = int((conn.execute("SELECT COUNT(*) AS total FROM radar_links WHERE deleted_at IS NULL").fetchone() or {}).get("total") or 0)
            rows = conn.execute(
                f"""
                SELECT {self._link_select_columns()}
                FROM radar_links
                WHERE deleted_at IS NULL
                ORDER BY id DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            ).fetchall()
        return [dict(row) for row in rows], total

    def get_link(self, link_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT {self._link_select_columns()}
                FROM radar_links
                WHERE id = %s AND deleted_at IS NULL
                """,
                (int(link_id),),
            ).fetchone()
        return self._row(row)

    def get_link_by_code(self, code: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT {self._link_select_columns()}
                FROM radar_links
                WHERE code = %s AND deleted_at IS NULL
                """,
                (str(code or "").strip(),),
            ).fetchone()
        return self._row(row)

    def save_link(self, payload: dict[str, Any], link_id: int | None = None) -> dict[str, Any]:
        with self._connect() as conn:
            if link_id is None:
                row = conn.execute(
                    """
                    INSERT INTO radar_links (
                        code, title, target_type, original_url, media_item_id, preview_mode,
                        file_name_snapshot, mime_type_snapshot, file_size_snapshot,
                        pdf_processing_status, pdf_page_count, pdf_preview_error_code, pdf_preview_error_message,
                        enabled, auth_required, source_channel, campaign_id, staff_id, created_by
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        self._new_code(conn),
                        str(payload.get("title") or "").strip(),
                        str(payload.get("target_type") or "link").strip() or "link",
                        str(payload.get("original_url") or "").strip(),
                        str(payload.get("media_item_id") or "").strip(),
                        str(payload.get("preview_mode") or "").strip(),
                        str(payload.get("file_name_snapshot") or "").strip(),
                        str(payload.get("mime_type_snapshot") or "").strip(),
                        int(payload.get("file_size_snapshot") or 0),
                        str(payload.get("pdf_processing_status") or "").strip(),
                        int(payload.get("pdf_page_count") or 0),
                        str(payload.get("pdf_preview_error_code") or "").strip(),
                        str(payload.get("pdf_preview_error_message") or "").strip(),
                        bool(payload.get("enabled", True)),
                        bool(payload.get("auth_required", True)),
                        str(payload.get("source_channel") or "").strip(),
                        str(payload.get("campaign_id") or "").strip(),
                        str(payload.get("staff_id") or "").strip(),
                        str(payload.get("created_by") or "").strip(),
                    ),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    UPDATE radar_links
                    SET title = %s,
                        target_type = %s,
                        original_url = %s,
                        media_item_id = %s,
                        preview_mode = %s,
                        file_name_snapshot = %s,
                        mime_type_snapshot = %s,
                        file_size_snapshot = %s,
                        pdf_processing_status = %s,
                        pdf_page_count = %s,
                        pdf_preview_error_code = %s,
                        pdf_preview_error_message = %s,
                        enabled = %s,
                        auth_required = %s,
                        source_channel = %s,
                        campaign_id = %s,
                        staff_id = %s,
                        created_by = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    RETURNING id
                    """,
                    (
                        str(payload.get("title") or "").strip(),
                        str(payload.get("target_type") or "link").strip() or "link",
                        str(payload.get("original_url") or "").strip(),
                        str(payload.get("media_item_id") or "").strip(),
                        str(payload.get("preview_mode") or "").strip(),
                        str(payload.get("file_name_snapshot") or "").strip(),
                        str(payload.get("mime_type_snapshot") or "").strip(),
                        int(payload.get("file_size_snapshot") or 0),
                        str(payload.get("pdf_processing_status") or "").strip(),
                        int(payload.get("pdf_page_count") or 0),
                        str(payload.get("pdf_preview_error_code") or "").strip(),
                        str(payload.get("pdf_preview_error_message") or "").strip(),
                        bool(payload.get("enabled", True)),
                        bool(payload.get("auth_required", True)),
                        str(payload.get("source_channel") or "").strip(),
                        str(payload.get("campaign_id") or "").strip(),
                        str(payload.get("staff_id") or "").strip(),
                        str(payload.get("created_by") or "").strip(),
                        int(link_id),
                    ),
                ).fetchone()
        return self.get_link(int((row or {}).get("id") or link_id or 0)) or {}

    def set_enabled(self, link_id: int, enabled: bool) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                f"""
                UPDATE radar_links
                SET enabled = %s, updated_at = NOW()
                WHERE id = %s
                RETURNING {self._link_select_columns()}
                """,
                (bool(enabled), int(link_id)),
            ).fetchone()
        return self._row(row)

    def record_click_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO radar_click_events (
                    link_id, code, stage, openid, unionid, external_userid,
                    target_type_snapshot, person_id, ip_hash, user_agent, referer, query_params_json,
                    source_channel, campaign_id, staff_id, source_channel_snapshot, campaign_id_snapshot, staff_id_snapshot, error_code, ip
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, id AS event_id, link_id, code, stage, openid, unionid, external_userid,
                    target_type_snapshot, person_id, ip_hash, user_agent, referer, query_params_json,
                    source_channel, campaign_id, staff_id, source_channel_snapshot, campaign_id_snapshot, staff_id_snapshot, error_code, created_at
                """,
                (
                    int(payload.get("link_id") or 0),
                    str(payload.get("code") or ""),
                    str(payload.get("stage") or ""),
                    str(payload.get("openid") or ""),
                    str(payload.get("unionid") or ""),
                    str(payload.get("external_userid") or ""),
                    str(payload.get("target_type_snapshot") or ""),
                    str(payload.get("person_id") or ""),
                    str(payload.get("ip_hash") or ""),
                    str(payload.get("user_agent") or ""),
                    str(payload.get("referer") or ""),
                    json.dumps(payload.get("query_params_json") or {}, ensure_ascii=False),
                    str(payload.get("source_channel") or ""),
                    str(payload.get("campaign_id") or ""),
                    str(payload.get("staff_id") or ""),
                    str(payload.get("source_channel_snapshot") or payload.get("source_channel") or ""),
                    str(payload.get("campaign_id_snapshot") or payload.get("campaign_id") or ""),
                    str(payload.get("staff_id_snapshot") or payload.get("staff_id") or ""),
                    str(payload.get("error_code") or ""),
                    "",
                ),
            ).fetchone()
        return dict(row or {})

    def list_click_events(
        self,
        link_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
        stage: str = "",
        start_at: str = "",
        end_at: str = "",
    ) -> tuple[list[dict[str, Any]], int]:
        limit = max(1, min(int(limit or 100), 500))
        offset = max(0, int(offset or 0))
        conditions = ["link_id = %s"]
        params: list[Any] = [int(link_id)]
        stage_filter = str(stage or "").strip()
        if stage_filter:
            conditions.append("stage = %s")
            params.append(stage_filter)
        start_filter = str(start_at or "").strip()
        if start_filter:
            conditions.append("created_at >= %s")
            params.append(start_filter)
        end_filter = str(end_at or "").strip()
        if end_filter:
            conditions.append("created_at <= %s")
            params.append(end_filter)
        where_sql = " AND ".join(conditions)
        with self._connect() as conn:
            total = int(
                (conn.execute(f"SELECT COUNT(*) AS total FROM radar_click_events WHERE {where_sql}", tuple(params)).fetchone() or {}).get("total") or 0
            )
            rows = conn.execute(
                f"""
                SELECT id, id AS event_id, link_id, code, stage, openid, unionid, external_userid,
                    target_type_snapshot, person_id, ip_hash, user_agent, referer, query_params_json,
                    source_channel, campaign_id, staff_id, source_channel_snapshot, campaign_id_snapshot, staff_id_snapshot, error_code, created_at
                FROM radar_click_events
                WHERE {where_sql}
                ORDER BY id DESC
                LIMIT %s OFFSET %s
                """,
                tuple(params + [limit, offset]),
            ).fetchall()
        return [dict(row) for row in rows], total

    def stats(self, link_id: int) -> dict[str, Any] | None:
        if not self.get_link(link_id):
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE stage = 'landing') AS total_landings,
                    COUNT(*) FILTER (WHERE stage IN ('authorized', 'authorized_click')) AS authorized_clicks,
                    COUNT(DISTINCT NULLIF(COALESCE(NULLIF(unionid, ''), NULLIF(openid, ''), NULLIF(external_userid, '')), ''))
                        FILTER (WHERE stage IN ('authorized', 'authorized_click')) AS unique_users,
                    COUNT(*) FILTER (WHERE stage = 'redirect') AS redirects,
                    COUNT(*) FILTER (WHERE stage = 'viewer_open') AS viewer_opens,
                    COUNT(*) FILTER (WHERE stage = 'image_loaded') AS image_loaded,
                    COUNT(*) FILTER (WHERE stage = 'pdf_opened') AS pdf_opened,
                    COUNT(*) FILTER (WHERE stage = 'landing' AND created_at::date = CURRENT_DATE) AS today_clicks,
                    MAX(created_at) FILTER (WHERE stage = 'landing') AS last_clicked_at,
                    MAX(created_at) AS last_event_at,
                    MAX(created_at) FILTER (WHERE stage IN ('viewer_open', 'image_loaded', 'pdf_opened')) AS last_viewed_at
                FROM radar_click_events
                WHERE link_id = %s
                """,
                (int(link_id),),
            ).fetchone()
            total_landings = int((row or {}).get("total_landings") or 0)
            unique_users = int((row or {}).get("unique_users") or 0)
        return {
            "total_clicks": total_landings,
            "total_landings": total_landings,
            "authorized_clicks": int((row or {}).get("authorized_clicks") or 0),
            "unique_users": unique_users,
            "authorized_users": unique_users,
            "redirects": int((row or {}).get("redirects") or 0),
            "viewer_opens": int((row or {}).get("viewer_opens") or 0),
            "view_opens": int((row or {}).get("viewer_opens") or 0),
            "image_loaded": int((row or {}).get("image_loaded") or 0),
            "pdf_opened": int((row or {}).get("pdf_opened") or 0),
            "today_clicks": int((row or {}).get("today_clicks") or 0),
            "today_landings": int((row or {}).get("today_clicks") or 0),
            "last_clicked_at": str((row or {}).get("last_clicked_at") or ""),
            "last_event_at": str((row or {}).get("last_event_at") or ""),
            "last_viewed_at": str((row or {}).get("last_viewed_at") or ""),
        }

    def set_pdf_processing_status(
        self,
        link_id: int,
        *,
        status: str,
        page_count: int = 0,
        error_code: str = "",
        error_message: str = "",
    ) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                f"""
                UPDATE radar_links
                SET pdf_processing_status = %s,
                    pdf_page_count = %s,
                    pdf_preview_error_code = %s,
                    pdf_preview_error_message = %s,
                    updated_at = NOW()
                WHERE id = %s AND deleted_at IS NULL
                RETURNING {self._link_select_columns()}
                """,
                (str(status or ""), int(page_count or 0), str(error_code or ""), str(error_message or ""), int(link_id)),
            ).fetchone()
        return self._row(row)

    def replace_pdf_preview_assets(self, link_id: int, media_item_id: str, assets: list[dict[str, Any]]) -> None:
        normalized_media_id = str(media_item_id or "").strip()
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM radar_pdf_preview_assets WHERE link_id = %s AND media_item_id = %s",
                (int(link_id), normalized_media_id),
            )
            for asset in assets:
                conn.execute(
                    """
                    INSERT INTO radar_pdf_preview_assets (
                        media_item_id, radar_link_id, link_id, source_file_hash, page_no, page_count,
                        preview_mime_type, preview_storage_key, preview_data_base64, preview_public_url,
                        width, height, file_size, render_dpi, render_quality,
                        status, error_code, error_message
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        normalized_media_id,
                        int(link_id),
                        int(link_id),
                        str(asset.get("source_file_hash") or ""),
                        int(asset.get("page_no") or 0),
                        int(asset.get("page_count") or 0),
                        str(asset.get("preview_mime_type") or "image/jpeg"),
                        str(asset.get("preview_storage_key") or ""),
                        str(asset.get("preview_data_base64") or ""),
                        str(asset.get("preview_public_url") or ""),
                        int(asset.get("width") or 0),
                        int(asset.get("height") or 0),
                        int(asset.get("file_size") or 0),
                        int(asset.get("render_dpi") or 144),
                        int(asset.get("render_quality") or 82),
                        str(asset.get("status") or "ready"),
                        str(asset.get("error_code") or ""),
                        str(asset.get("error_message") or ""),
                    ),
                )

    def list_pdf_preview_assets(self, link_id: int, media_item_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, media_item_id, link_id, radar_link_id, source_file_hash, page_no, page_count,
                    preview_mime_type, preview_storage_key, preview_data_base64, preview_public_url,
                    width, height, file_size, render_dpi, render_quality,
                    status, error_code, error_message, created_at, updated_at
                FROM radar_pdf_preview_assets
                WHERE link_id = %s AND media_item_id = %s
                ORDER BY page_no ASC
                """,
                (int(link_id), str(media_item_id or "").strip()),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_pdf_preview_asset(self, link_id: int, media_item_id: str, page_no: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, media_item_id, link_id, radar_link_id, source_file_hash, page_no, page_count,
                    preview_mime_type, preview_storage_key, preview_data_base64, preview_public_url,
                    width, height, file_size, render_dpi, render_quality,
                    status, error_code, error_message, created_at, updated_at
                FROM radar_pdf_preview_assets
                WHERE link_id = %s AND media_item_id = %s AND page_no = %s
                """,
                (int(link_id), str(media_item_id or "").strip(), int(page_no)),
            ).fetchone()
        return self._row(row)


_DEFAULT_REPO = InMemoryRadarLinksRepository()


def build_radar_links_repository() -> RadarLinksRepository:
    if production_data_ready():
        return PostgresRadarLinksRepository()
    return assert_repository_allowed(_DEFAULT_REPO, capability_owner="radar_links")


def reset_radar_links_fixture_state() -> None:
    _DEFAULT_REPO.reset()
