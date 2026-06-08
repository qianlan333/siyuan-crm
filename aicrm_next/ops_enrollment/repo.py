from __future__ import annotations

import os
from copy import deepcopy
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from aicrm_next.shared.config import Settings, get_settings
from aicrm_next.shared.db_session import get_session_factory
from aicrm_next.shared.repository_provider import assert_repository_allowed
from aicrm_next.shared.typing import JsonDict

from .models import (
    user_ops_do_not_disturb_next,
    user_ops_pool_current_next,
    user_ops_send_records_next,
)

AUTO_DND_REASON = {
    "source_type": "auto",
    "source": "auto",
    "reason_code": "signed_paid_course",
    "reason_text": "已报名正价课",
    "reason_label": "已报名正价课",
}

ACTIVATION_LABELS = {
    "activated": "黄小璨已激活",
    "not_activated": "黄小璨未激活",
    "pending_input": "激活待录入",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _iso(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "")


def _default_pool_rows() -> list[JsonDict]:
    return [
        {
            "id": 1,
            "person_id": "person_001",
            "mobile": "13800138000",
            "external_userid": "wx_ext_001",
            "customer_name": "张小蓝",
            "owner_userid": "ZhaoYanFang",
            "owner_display_name": "赵燕芳",
            "class_term_no": "2026-05-A",
            "class_term_label": "2026 五月 A 班",
            "source_type": "lead_pool",
            "created_at": "2026-05-01T09:00:00+08:00",
            "updated_at": "2026-05-18T10:00:00+08:00",
            "activation_bucket": "activated",
            "tags": ["黄小璨", "已激活"],
            "manual_dnd_reasons": [],
            "auto_dnd_reasons": [],
        },
        {
            "id": 2,
            "person_id": "person_002",
            "mobile": "",
            "external_userid": "wx_ext_002",
            "customer_name": "李未绑",
            "owner_userid": "LiuXiao",
            "owner_display_name": "刘潇",
            "class_term_no": "2026-05-A",
            "class_term_label": "2026 五月 A 班",
            "source_type": "lead_pool",
            "created_at": "2026-05-02T09:00:00+08:00",
            "updated_at": "2026-05-18T10:20:00+08:00",
            "activation_bucket": "pending_input",
            "tags": ["黄小璨", "待录入"],
            "manual_dnd_reasons": [],
            "auto_dnd_reasons": [dict(AUTO_DND_REASON)],
        },
        {
            "id": 3,
            "person_id": "person_003",
            "mobile": "13900139000",
            "external_userid": "",
            "customer_name": "王缺外部联系人",
            "owner_userid": "ZhaoYanFang",
            "owner_display_name": "赵燕芳",
            "class_term_no": "2026-05-B",
            "class_term_label": "2026 五月 B 班",
            "source_type": "questionnaire",
            "created_at": "2026-05-03T09:00:00+08:00",
            "updated_at": "2026-05-18T10:40:00+08:00",
            "activation_bucket": "not_activated",
            "tags": ["未激活"],
            "manual_dnd_reasons": [],
            "auto_dnd_reasons": [],
        },
        {
            "id": 4,
            "person_id": "person_004",
            "mobile": "13700137000",
            "external_userid": "wx_ext_004",
            "customer_name": "陈缺负责人",
            "owner_userid": "",
            "owner_display_name": "",
            "class_term_no": "2026-05-B",
            "class_term_label": "2026 五月 B 班",
            "source_type": "lead_pool",
            "created_at": "2026-05-04T09:00:00+08:00",
            "updated_at": "2026-05-18T11:00:00+08:00",
            "activation_bucket": "not_activated",
            "tags": ["黄小璨", "未激活"],
            "manual_dnd_reasons": [],
            "auto_dnd_reasons": [],
        },
    ]


def _manual_reason(reason_code: str, reason_text: str) -> JsonDict:
    return {
        "source_type": "manual",
        "source": "manual",
        "reason_code": reason_code,
        "reason_text": reason_text,
        "reason_label": reason_text,
    }


def _project_row(row: JsonDict) -> JsonDict:
    projected = deepcopy(row)
    external_userid = str(projected.get("external_userid") or "").strip()
    mobile = str(projected.get("mobile") or "").strip()
    activation_bucket = str(projected.get("activation_bucket") or "pending_input").strip() or "pending_input"
    reasons = list(projected.pop("auto_dnd_reasons", [])) + list(projected.pop("manual_dnd_reasons", []))
    projected.update(
        {
            "mobile": mobile,
            "external_userid": external_userid,
            "is_added_wecom": bool(external_userid),
            "is_wecom_added": bool(external_userid),
            "is_mobile_bound": bool(mobile),
            "activation_bucket": activation_bucket,
            "activation_bucket_label": ACTIVATION_LABELS.get(activation_bucket, activation_bucket),
            "huangxiaocan_activation_state": activation_bucket,
            "huangxiaocan_activation_state_label": ACTIVATION_LABELS.get(activation_bucket, activation_bucket),
            "do_not_disturb": bool(reasons),
            "do_not_disturb_reasons": reasons,
            "can_open_customer_detail": bool(external_userid),
            "can_batch_send": bool(external_userid),
            "tags": list(projected.get("tags") or []),
        }
    )
    return projected


class UserOpsRepository(Protocol):
    def reset(self) -> None: ...

    def list_rows(self) -> list[JsonDict]: ...

    def find_row(self, *, external_userid: str = "", mobile: str = "") -> JsonDict | None: ...

    def set_do_not_disturb(
        self,
        *,
        external_userid: str = "",
        mobile: str = "",
        reason_code: str,
        reason_text: str,
        is_active: bool,
        operator: str = "fixture-admin",
    ) -> JsonDict | None: ...

    def create_send_record(self, payload: JsonDict) -> JsonDict: ...

    def list_send_records(self) -> list[JsonDict]: ...

    def get_send_record(self, record_id: str) -> JsonDict | None: ...


class InMemoryUserOpsRepository:
    """Default fixture repository; it mirrors the SQL repository contract."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._rows = _default_pool_rows()
        self._send_records: list[JsonDict] = []
        self._next_send_record_id = 1

    def list_rows(self) -> list[JsonDict]:
        return [_project_row(row) for row in self._rows]

    list_pool = list_rows

    def find_row(self, *, external_userid: str = "", mobile: str = "") -> JsonDict | None:
        for row in self._rows:
            if external_userid and row.get("external_userid") == external_userid:
                return row
            if mobile and row.get("mobile") == mobile:
                return row
        return None

    def set_do_not_disturb(
        self,
        *,
        external_userid: str = "",
        mobile: str = "",
        reason_code: str,
        reason_text: str,
        is_active: bool,
        operator: str = "fixture-admin",
    ) -> JsonDict | None:
        row = self.find_row(external_userid=external_userid, mobile=mobile)
        if row is None:
            return None

        manual_reasons = [
            reason
            for reason in list(row.get("manual_dnd_reasons") or [])
            if reason.get("reason_code") != reason_code
        ]
        if is_active:
            manual_reasons.append(_manual_reason(reason_code, reason_text))
        row["manual_dnd_reasons"] = manual_reasons
        row["updated_at"] = _now_iso()
        return _project_row(row)

    def create_send_record(self, payload: JsonDict) -> JsonDict:
        record_id = self._next_send_record_id
        self._next_send_record_id += 1
        created_at = _now_iso()
        record = {
            "id": record_id,
            "record_id": f"user_ops_send_{record_id:04d}",
            "task_type": "user_ops_batch_send",
            "created_at": created_at,
            "updated_at": created_at,
            **payload,
        }
        self._send_records.insert(0, record)
        return deepcopy(record)

    def list_send_records(self) -> list[JsonDict]:
        if not self._send_records:
            return [
                {
                    "id": 0,
                    "record_id": "fixture_record_001",
                    "task_type": "user_ops_batch_send",
                    "selected_count": 1,
                    "eligible_count": 1,
                    "sent_count": 1,
                    "skipped_count": 0,
                    "skipped_reasons": {},
                    "include_do_not_disturb": False,
                    "content_preview": "欢迎继续了解黄小璨课程",
                    "image_count": 0,
                    "sender_userids": ["ZhaoYanFang"],
                    "filter_snapshot": {},
                    "operator": "fixture-admin",
                    "status": "created",
                    "status_label": "已创建任务",
                    "created_at": "2026-05-18T10:30:00+08:00",
                    "task_results": [],
                }
            ]
        return [deepcopy(record) for record in self._send_records]

    def get_send_record(self, record_id: str) -> JsonDict | None:
        for record in self.list_send_records():
            if str(record.get("record_id")) == record_id or str(record.get("id")) == record_id:
                return record
        return None


class SqlAlchemyUserOpsRepository:
    """PostgreSQL-ready User Ops repository backed by SQLAlchemy Core tables."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def close(self) -> None:
        try:
            self._session.rollback()
        finally:
            self._session.close()

    def reset(self) -> None:
        self._session.execute(delete(user_ops_send_records_next))
        self._session.execute(delete(user_ops_do_not_disturb_next))
        self._session.execute(delete(user_ops_pool_current_next))
        self.seed_pool_rows(_default_pool_rows())
        self._session.commit()

    def seed_pool_rows(self, rows: list[JsonDict]) -> None:
        for row in rows:
            created_at = _coerce_datetime(row.get("created_at"))
            updated_at = _coerce_datetime(row.get("updated_at"))
            self._session.execute(
                insert(user_ops_pool_current_next).values(
                    id=row["id"],
                    person_id=row.get("person_id") or f"person_{int(row['id']):03d}",
                    mobile=row.get("mobile") or "",
                    external_userid=row.get("external_userid") or "",
                    customer_name=row.get("customer_name") or "",
                    owner_userid=row.get("owner_userid") or "",
                    owner_display_name=row.get("owner_display_name") or "",
                    class_term_no=row.get("class_term_no") or "",
                    class_term_label=row.get("class_term_label") or "",
                    source_type=row.get("source_type") or "lead_pool",
                    activation_bucket=row.get("activation_bucket") or "pending_input",
                    activation_bucket_label=ACTIVATION_LABELS.get(
                        str(row.get("activation_bucket") or "pending_input"),
                        str(row.get("activation_bucket") or "pending_input"),
                    ),
                    is_mobile_bound=bool(row.get("mobile")),
                    auto_do_not_disturb_reasons_json=list(row.get("auto_dnd_reasons") or []),
                    created_at=created_at,
                    updated_at=updated_at,
                )
            )

    def list_rows(self) -> list[JsonDict]:
        rows = self._session.execute(
            select(user_ops_pool_current_next).order_by(user_ops_pool_current_next.c.id.asc())
        ).mappings()
        return [_project_row(self._row_to_dict(row)) for row in rows]

    list_pool = list_rows

    def find_row(self, *, external_userid: str = "", mobile: str = "") -> JsonDict | None:
        stmt = select(user_ops_pool_current_next)
        if external_userid:
            stmt = stmt.where(user_ops_pool_current_next.c.external_userid == external_userid)
        elif mobile:
            stmt = stmt.where(user_ops_pool_current_next.c.mobile == mobile)
        else:
            return None
        row = self._session.execute(stmt.limit(1)).mappings().first()
        return self._row_to_dict(row) if row else None

    def set_do_not_disturb(
        self,
        *,
        external_userid: str = "",
        mobile: str = "",
        reason_code: str,
        reason_text: str,
        is_active: bool,
        operator: str = "fixture-admin",
    ) -> JsonDict | None:
        target = self.find_row(external_userid=external_userid, mobile=mobile)
        if target is None:
            return None

        now = _now()
        match = self._dnd_match_stmt(target, reason_code=reason_code)
        existing = self._session.execute(match.limit(1)).mappings().first()
        values = {
            "external_userid": target.get("external_userid") or "",
            "mobile": target.get("mobile") or "",
            "source_type": "manual",
            "reason_code": reason_code,
            "reason_text": reason_text,
            "is_active": bool(is_active),
            "created_by": operator,
            "updated_at": now,
        }
        if existing:
            self._session.execute(
                update(user_ops_do_not_disturb_next)
                .where(user_ops_do_not_disturb_next.c.id == existing["id"])
                .values(**values)
            )
        else:
            self._session.execute(
                insert(user_ops_do_not_disturb_next).values(
                    **values,
                    created_at=now,
                )
            )
        self._session.execute(
            update(user_ops_pool_current_next)
            .where(user_ops_pool_current_next.c.id == target["id"])
            .values(updated_at=now)
        )
        self._session.commit()
        return _project_row(self._row_to_dict(self._fetch_pool_row_by_id(int(target["id"]))))

    def create_send_record(self, payload: JsonDict) -> JsonDict:
        next_id = int(self._session.execute(select(func.coalesce(func.max(user_ops_send_records_next.c.id), 0))).scalar_one()) + 1
        record_key = f"user_ops_send_{next_id:04d}"
        now = _now()
        task_results = list(payload.get("task_results") or [])
        outbound_task_ids = [result.get("task_id") for result in task_results if result.get("task_id")]
        self._session.execute(
            insert(user_ops_send_records_next).values(
                id=next_id,
                record_key=record_key,
                task_type="user_ops_batch_send",
                outbound_task_ids_json=outbound_task_ids,
                task_results_json=task_results,
                selected_count=int(payload.get("selected_count") or 0),
                eligible_count=int(payload.get("eligible_count") or 0),
                sent_count=int(payload.get("sent_count") or 0),
                skipped_count=int(payload.get("skipped_count") or 0),
                skipped_reasons_json=dict(payload.get("skipped_reasons") or payload.get("skipped_by_reason") or {}),
                include_do_not_disturb=bool(payload.get("include_do_not_disturb")),
                content_preview=str(payload.get("content_preview") or ""),
                image_count=int(payload.get("image_count") or 0),
                sender_userids_json=list(payload.get("sender_userids") or []),
                filter_snapshot_json=dict(payload.get("filter_snapshot") or {}),
                operator=str(payload.get("operator") or "fixture-admin"),
                status=str(payload.get("status") or "created"),
                status_label=str(payload.get("status_label") or "已创建任务"),
                created_at=now,
            )
        )
        self._session.commit()
        return self.get_send_record(record_key) or {}

    def list_send_records(self) -> list[JsonDict]:
        rows = self._session.execute(
            select(user_ops_send_records_next).order_by(user_ops_send_records_next.c.created_at.desc())
        ).mappings()
        return [self._record_to_dict(row) for row in rows]

    def get_send_record(self, record_id: str) -> JsonDict | None:
        stmt = select(user_ops_send_records_next).where(user_ops_send_records_next.c.record_key == record_id)
        if str(record_id).isdigit():
            stmt = select(user_ops_send_records_next).where(user_ops_send_records_next.c.id == int(record_id))
        row = self._session.execute(stmt.limit(1)).mappings().first()
        return self._record_to_dict(row) if row else None

    def _dnd_match_stmt(self, target: JsonDict, *, reason_code: str):
        stmt = select(user_ops_do_not_disturb_next).where(
            user_ops_do_not_disturb_next.c.source_type == "manual",
            user_ops_do_not_disturb_next.c.reason_code == reason_code,
        )
        if target.get("external_userid"):
            stmt = stmt.where(user_ops_do_not_disturb_next.c.external_userid == target["external_userid"])
        else:
            stmt = stmt.where(user_ops_do_not_disturb_next.c.mobile == target.get("mobile", ""))
        return stmt

    def _fetch_pool_row_by_id(self, row_id: int):
        return self._session.execute(
            select(user_ops_pool_current_next).where(user_ops_pool_current_next.c.id == row_id)
        ).mappings().one()

    def _row_to_dict(self, row) -> JsonDict:
        data = dict(row)
        data["created_at"] = _iso(data.get("created_at"))
        data["updated_at"] = _iso(data.get("updated_at"))
        data["auto_dnd_reasons"] = list(data.pop("auto_do_not_disturb_reasons_json") or [])
        data["manual_dnd_reasons"] = self._manual_reasons_for_row(data)
        data["mobile"] = data.get("mobile") or ""
        data["external_userid"] = data.get("external_userid") or ""
        data["owner_userid"] = data.get("owner_userid") or ""
        data["class_term_no"] = data.get("class_term_no") or ""
        return data

    def _manual_reasons_for_row(self, row: JsonDict) -> list[JsonDict]:
        stmt = select(user_ops_do_not_disturb_next).where(
            user_ops_do_not_disturb_next.c.source_type == "manual",
            user_ops_do_not_disturb_next.c.is_active.is_(True),
        )
        external_userid = str(row.get("external_userid") or "")
        mobile = str(row.get("mobile") or "")
        if external_userid:
            stmt = stmt.where(user_ops_do_not_disturb_next.c.external_userid == external_userid)
        elif mobile:
            stmt = stmt.where(user_ops_do_not_disturb_next.c.mobile == mobile)
        else:
            return []
        reasons = []
        for item in self._session.execute(stmt.order_by(user_ops_do_not_disturb_next.c.id.asc())).mappings():
            reasons.append(_manual_reason(str(item["reason_code"]), str(item["reason_text"])))
        return reasons

    def _record_to_dict(self, row) -> JsonDict:
        data = dict(row)
        return {
            "id": data["id"],
            "record_id": data["record_key"],
            "task_type": data["task_type"],
            "selected_count": data["selected_count"],
            "eligible_count": data["eligible_count"],
            "sent_count": data["sent_count"],
            "skipped_count": data["skipped_count"],
            "skipped_reasons": data.get("skipped_reasons_json") or {},
            "include_do_not_disturb": data["include_do_not_disturb"],
            "content_preview": data["content_preview"],
            "image_count": data["image_count"],
            "sender_userids": data.get("sender_userids_json") or [],
            "filter_snapshot": data.get("filter_snapshot_json") or {},
            "operator": data["operator"],
            "status": data["status"],
            "status_label": data["status_label"],
            "created_at": _iso(data["created_at"]),
            "task_results": data.get("task_results_json") or [],
        }


def _coerce_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if value:
        return datetime.fromisoformat(str(value))
    return _now()


def build_user_ops_repository(
    settings: Settings | None = None,
    *,
    session: Session | None = None,
    engine: Engine | None = None,
) -> UserOpsRepository:
    settings = settings or get_settings()
    backend = os.getenv("USER_OPS_REPO_BACKEND", settings.user_ops_repo_backend).strip().lower()
    if backend in {"sql", "sqlalchemy", "postgres", "postgresql"}:
        if session is not None:
            return assert_repository_allowed(SqlAlchemyUserOpsRepository(session), capability_owner="ops_enrollment")
        owned_session = get_session_factory(settings=settings)() if engine is None else Session(bind=engine, future=True)
        return assert_repository_allowed(SqlAlchemyUserOpsRepository(owned_session), capability_owner="ops_enrollment")
    return assert_repository_allowed(InMemoryUserOpsRepository(), capability_owner="ops_enrollment")


FixtureUserOpsRepository = InMemoryUserOpsRepository
