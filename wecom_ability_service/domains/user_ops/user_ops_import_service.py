from __future__ import annotations

import json
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Callable
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from ...db import get_db


@dataclass(frozen=True)
class ImportRuntime:
    """Internal-only dependency bag for user-ops import flows."""

    db_bool: Callable[[Any], bool | int]
    normalize_mobile: Callable[[str], str]
    current_operator_resolver: Callable[[], str]
    normalize_lead_pool_activation_state: Callable[..., str]
    apply_activation_source_to_existing_member: Callable[..., dict[str, Any]]
    upsert_user_ops_lead_pool_member: Callable[..., dict[str, Any]]


def _is_experience_lead_header(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized in {"手机号", "手机", "mobile", "phone", "手机号列表"}


def _is_activation_status_header(value: str) -> bool:
    normalized = str(value or "").strip().lower().replace(" ", "")
    return normalized in {
        "手机号,状态",
        "手机号,状态,备注",
        "mobile,status",
        "mobile,status,remark",
    }


def _collect_experience_lead_mobiles(
    raw_values: list[str],
    *,
    runtime: ImportRuntime,
) -> dict[str, Any]:
    valid_rows: list[str] = []
    invalid_rows: list[str] = []
    seen: set[str] = set()
    unique_mobiles: list[str] = []
    total_rows = 0
    for raw_value in raw_values:
        candidate = str(raw_value or "").strip()
        if not candidate or _is_experience_lead_header(candidate):
            continue
        total_rows += 1
        try:
            mobile = runtime.normalize_mobile(candidate)
        except ValueError:
            invalid_rows.append(candidate)
            continue
        valid_rows.append(mobile)
        if mobile not in seen:
            seen.add(mobile)
            unique_mobiles.append(mobile)
    return {
        "total_rows": total_rows,
        "valid_rows": valid_rows,
        "unique_mobiles": unique_mobiles,
        "invalid_rows": invalid_rows,
        "duplicate_count": max(0, len(valid_rows) - len(unique_mobiles)),
    }


def _extract_xlsx_shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    namespace = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    values: list[str] = []
    for item in root.findall("a:si", namespace):
        values.append("".join(item.itertext()).strip())
    return values


def _parse_xlsx_rows(file_bytes: bytes) -> list[list[str]]:
    with ZipFile(BytesIO(file_bytes)) as archive:
        shared_strings = _extract_xlsx_shared_strings(archive)
        worksheet_name = "xl/worksheets/sheet1.xml"
        if worksheet_name not in archive.namelist():
            worksheet_candidates = sorted(
                name
                for name in archive.namelist()
                if name.startswith("xl/worksheets/") and name.endswith(".xml")
            )
            if not worksheet_candidates:
                return []
            worksheet_name = worksheet_candidates[0]
        root = ET.fromstring(archive.read(worksheet_name))
        namespace = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        rows: list[list[str]] = []
        for row in root.findall(".//a:sheetData/a:row", namespace):
            cell_values: list[str] = []
            for cell in row.findall("a:c", namespace):
                cell_type = str(cell.attrib.get("t") or "").strip()
                if cell_type == "inlineStr":
                    text_value = "".join(cell.itertext()).strip()
                else:
                    value_node = cell.find("a:v", namespace)
                    text_value = str(value_node.text or "").strip() if value_node is not None else ""
                    if cell_type == "s" and text_value.isdigit():
                        index = int(text_value)
                        text_value = shared_strings[index] if 0 <= index < len(shared_strings) else ""
                cell_values.append(text_value)
            if any(value.strip() for value in cell_values):
                rows.append(cell_values)
        return rows


def _decode_utf8_text_file(file_bytes: bytes) -> str:
    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("only .xlsx or utf-8 text files are supported") from exc


def _split_text_values(text: str) -> list[str]:
    return [item for item in re.split(r"[\s,，;；]+", str(text or "").strip()) if item.strip()]


def _nonempty_text_lines(text: str) -> list[str]:
    return [line.strip() for line in str(text or "").splitlines() if line.strip()]


def _parse_column_lines_from_file(
    *,
    file_name: str,
    file_bytes: bytes,
    column_count: int,
) -> list[str]:
    normalized_name = str(file_name or "").strip().lower()
    if normalized_name.endswith(".xlsx"):
        lines: list[str] = []
        for row in _parse_xlsx_rows(file_bytes):
            normalized_row = [str(item or "").strip() for item in row[:column_count]]
            if any(normalized_row):
                lines.append(",".join(normalized_row))
        return lines
    return _nonempty_text_lines(_decode_utf8_text_file(file_bytes))


def _resolve_import_operator(created_by: str, *, runtime: ImportRuntime) -> str:
    return str(created_by or runtime.current_operator_resolver()).strip() or "admin_user_ops"


def _build_import_error_summary(invalid_rows: list[str], duplicate_count: int) -> str:
    error_summary_parts: list[str] = []
    if invalid_rows:
        preview = " / ".join(invalid_rows[:5])
        suffix = " ..." if len(invalid_rows) > 5 else ""
        error_summary_parts.append(f"invalid: {preview}{suffix}")
    if duplicate_count:
        error_summary_parts.append(f"duplicates: {duplicate_count}")
    return "; ".join(error_summary_parts)


def _parse_experience_leads_from_text(
    pasted_text: str,
    *,
    runtime: ImportRuntime,
) -> dict[str, Any]:
    raw_values = _split_text_values(pasted_text)
    result = _collect_experience_lead_mobiles(raw_values, runtime=runtime)
    result["input_mode"] = "pasted_text"
    return result


def _parse_experience_leads_from_file(
    *,
    file_name: str,
    file_bytes: bytes,
    runtime: ImportRuntime,
) -> dict[str, Any]:
    normalized_name = str(file_name or "").strip().lower()
    if normalized_name.endswith(".xlsx"):
        raw_values = [row[0] for row in _parse_xlsx_rows(file_bytes) if row]
    else:
        raw_values = _split_text_values(_decode_utf8_text_file(file_bytes))
    result = _collect_experience_lead_mobiles(raw_values, runtime=runtime)
    result["input_mode"] = "file"
    result["file_name"] = str(file_name or "").strip()
    return result


def _is_class_term_header(value: str) -> bool:
    normalized = str(value or "").strip().lower().replace(" ", "")
    return normalized in {
        "手机号,班期",
        "mobile,classterm",
        "mobile,class_term",
        "phone,classterm",
    }


def _normalize_class_term_value(value: str) -> str:
    class_term_label = str(value or "").strip()
    if not class_term_label:
        raise ValueError("class_term is required")
    return class_term_label


def _extract_class_term_no(class_term_label: str) -> int | None:
    matched = re.fullmatch(r"(\d+)\s*期?", str(class_term_label or "").strip())
    if not matched:
        return None
    return int(matched.group(1))


def _parse_class_term_import_line(
    line: str,
    *,
    runtime: ImportRuntime,
) -> tuple[str, str, int | None]:
    parts = [item.strip() for item in re.split(r"[,\t，]+", str(line or "").strip())]
    parts = [item for item in parts if item]
    if not parts:
        raise ValueError("class term row is empty")
    mobile = runtime.normalize_mobile(parts[0])
    if len(parts) < 2:
        raise ValueError("class_term is required")
    class_term_label = _normalize_class_term_value(parts[1])
    return mobile, class_term_label, _extract_class_term_no(class_term_label)


def _parse_class_term_source_from_text(
    pasted_text: str,
    *,
    runtime: ImportRuntime,
) -> dict[str, Any]:
    lines = _nonempty_text_lines(pasted_text)
    rows: list[dict[str, Any]] = []
    invalid_rows: list[str] = []
    total_rows = 0
    for line in lines:
        if _is_class_term_header(line):
            continue
        total_rows += 1
        try:
            mobile, class_term_label, class_term_no = _parse_class_term_import_line(
                line,
                runtime=runtime,
            )
        except ValueError:
            invalid_rows.append(line)
            continue
        rows.append(
            {
                "mobile": mobile,
                "class_term_label": class_term_label,
                "class_term_no": class_term_no,
            }
        )
    return {
        "input_mode": "pasted_text",
        "total_rows": total_rows,
        "rows": rows,
        "invalid_rows": invalid_rows,
    }


def _parse_class_term_source_from_file(
    *,
    file_name: str,
    file_bytes: bytes,
    runtime: ImportRuntime,
) -> dict[str, Any]:
    lines = _parse_column_lines_from_file(file_name=file_name, file_bytes=file_bytes, column_count=2)
    result = _parse_class_term_source_from_text("\n".join(lines), runtime=runtime)
    result["input_mode"] = "file"
    result["file_name"] = str(file_name or "").strip()
    return result


def _normalize_activation_status_value(value: str) -> str:
    normalized = str(value or "").strip()
    mapping = {
        "未激活": "not_activated",
        "已激活": "activated",
        "激活": "activated",
    }
    result = mapping.get(normalized)
    if not result:
        raise ValueError(f"activation_status is invalid: {normalized} (allowed: 已激活, 未激活)")
    return result


def _normalize_legacy_user_ops_activation_for_lead_pool(value: str) -> str:
    normalized = str(value or "").strip()
    if normalized == "activated":
        return "activated"
    if normalized == "not_activated":
        return "not_activated"
    return "unknown"


def _resolve_lead_pool_binding_by_mobile(
    mobile: str,
    *,
    runtime: ImportRuntime,
) -> dict[str, Any]:
    normalized_mobile = runtime.normalize_mobile(mobile)
    row = get_db().execute(
        """
        SELECT
            p.mobile,
            COALESCE(bindings.external_userid, '') AS external_userid,
            COALESCE(c.customer_name, status.customer_name_snapshot, '') AS customer_name,
            COALESCE(c.owner_userid, status.owner_userid_snapshot, '') AS owner_userid,
            bindings.person_id
        FROM people p
        LEFT JOIN external_contact_bindings bindings
          ON bindings.person_id = p.id
        LEFT JOIN contacts c
          ON c.external_userid = bindings.external_userid
        LEFT JOIN class_user_status_current status
          ON status.external_userid = bindings.external_userid
        WHERE p.mobile = ?
        ORDER BY COALESCE(bindings.updated_at, bindings.created_at) DESC, bindings.external_userid ASC
        LIMIT 1
        """,
        (normalized_mobile,),
    ).fetchone()
    external_userid = str((row or {}).get("external_userid") or "").strip()
    is_mobile_bound = bool(row and row.get("person_id") is not None and external_userid)
    return {
        "mobile": normalized_mobile,
        "external_userid": external_userid,
        "customer_name": str((row or {}).get("customer_name") or "").strip(),
        "owner_userid": str((row or {}).get("owner_userid") or "").strip(),
        "is_mobile_bound": is_mobile_bound,
        "is_wecom_added": bool(external_userid),
    }


def _get_user_ops_pool_current_member_by_identity(
    *,
    mobile: str = "",
    external_userid: str = "",
) -> dict[str, Any] | None:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_mobile = str(mobile or "").strip()
    if normalized_external_userid:
        row = get_db().execute(
            """
            SELECT
                id,
                mobile,
                external_userid,
                customer_name,
                owner_userid,
                current_status,
                is_wecom_bound,
                activation_status,
                activation_remark,
                class_term_no,
                class_term_label,
                source_type
            FROM user_ops_pool_current
            WHERE external_userid = ?
            LIMIT 1
            """,
            (normalized_external_userid,),
        ).fetchone()
        if row:
            return dict(row)
    if normalized_mobile:
        row = get_db().execute(
            """
            SELECT
                id,
                mobile,
                external_userid,
                customer_name,
                owner_userid,
                current_status,
                is_wecom_bound,
                activation_status,
                activation_remark,
                class_term_no,
                class_term_label,
                source_type
            FROM user_ops_pool_current
            WHERE mobile = ?
            LIMIT 1
            """,
            (normalized_mobile,),
        ).fetchone()
        if row:
            return dict(row)
    return None


def _upsert_user_ops_pool_current_import_member(
    *,
    mobile: str,
    external_userid: str = "",
    customer_name: str = "",
    owner_userid: str = "",
    is_wecom_bound: bool = False,
    class_term_no: int | None = None,
    class_term_label: str = "",
    source_type: str = "student_import",
    runtime: ImportRuntime,
) -> None:
    normalized_mobile = runtime.normalize_mobile(mobile)
    normalized_external_userid = str(external_userid or "").strip()
    existing = _get_user_ops_pool_current_member_by_identity(
        mobile=normalized_mobile,
        external_userid=normalized_external_userid,
    )
    final_external_userid = normalized_external_userid or str((existing or {}).get("external_userid") or "").strip()
    final_customer_name = str(customer_name or "").strip() or str((existing or {}).get("customer_name") or "").strip()
    final_owner_userid = str(owner_userid or "").strip() or str((existing or {}).get("owner_userid") or "").strip()
    final_class_term_no = (
        class_term_no if class_term_no not in (None, "") else (existing or {}).get("class_term_no")
    )
    final_class_term_label = str(class_term_label or "").strip() or str((existing or {}).get("class_term_label") or "").strip()
    final_source_type = (
        str(source_type or "").strip()
        or str((existing or {}).get("source_type") or "").strip()
        or "student_import"
    )
    activation_status = str((existing or {}).get("activation_status") or "").strip() or "not_activated"
    activation_remark = str((existing or {}).get("activation_remark") or "").strip()
    current_status = str((existing or {}).get("current_status") or "").strip() or "lead_trial"
    db = get_db()
    if existing:
        db.execute(
            """
            UPDATE user_ops_pool_current
            SET mobile = ?,
                external_userid = ?,
                customer_name = ?,
                owner_userid = ?,
                current_status = ?,
                is_wecom_bound = ?,
                activation_status = ?,
                activation_remark = ?,
                class_term_no = ?,
                class_term_label = ?,
                source_type = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                normalized_mobile,
                final_external_userid,
                final_customer_name,
                final_owner_userid,
                current_status,
                runtime.db_bool(bool(is_wecom_bound)),
                activation_status,
                activation_remark,
                final_class_term_no,
                final_class_term_label,
                final_source_type,
                int(existing["id"]),
            ),
        )
        return
    db.execute(
        """
        INSERT INTO user_ops_pool_current (
            mobile, external_userid, customer_name, owner_userid, current_status, is_wecom_bound,
            activation_status, activation_remark, class_term_no, class_term_label, source_type, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (
            normalized_mobile,
            final_external_userid,
            final_customer_name,
            final_owner_userid,
            current_status,
            runtime.db_bool(bool(is_wecom_bound)),
            activation_status,
            activation_remark,
            final_class_term_no,
            final_class_term_label,
            final_source_type,
        ),
    )


def _apply_activation_status_to_user_ops_pool_current_member(
    *,
    mobile: str,
    activation_status: str,
    activation_remark: str = "",
    runtime: ImportRuntime,
) -> dict[str, Any]:
    normalized_mobile = runtime.normalize_mobile(mobile)
    normalized_status = str(activation_status or "").strip() or "not_activated"
    normalized_remark = str(activation_remark or "").strip()
    existing = _get_user_ops_pool_current_member_by_identity(mobile=normalized_mobile)
    if not existing:
        return {"matched_member": False}
    get_db().execute(
        """
        UPDATE user_ops_pool_current
        SET activation_status = ?, activation_remark = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            normalized_status,
            normalized_remark or ("已激活" if normalized_status == "activated" else "未激活"),
            int(existing["id"]),
        ),
    )
    return {"matched_member": True, "id": int(existing["id"])}


def _parse_activation_status_line(
    line: str,
    *,
    runtime: ImportRuntime,
) -> tuple[str, str, str]:
    parts = [item.strip() for item in re.split(r"[,\t，]+", str(line or "").strip())]
    parts = [item for item in parts if item]
    if not parts:
        raise ValueError("activation row is empty")
    mobile = runtime.normalize_mobile(parts[0])
    if len(parts) < 2:
        raise ValueError("activation_status is required")
    if len(parts) > 3:
        raise ValueError("activation_status rows must contain mobile, activation_status and optional remark")
    activation_status = _normalize_activation_status_value(parts[1])
    return mobile, activation_status, str(parts[2] if len(parts) > 2 else "").strip()


def _parse_activation_status_from_text(
    pasted_text: str,
    *,
    runtime: ImportRuntime,
) -> dict[str, Any]:
    lines = _nonempty_text_lines(pasted_text)
    rows: list[dict[str, str]] = []
    invalid_rows: list[str] = []
    total_rows = 0
    for line in lines:
        if _is_activation_status_header(line):
            continue
        total_rows += 1
        try:
            mobile, activation_status, activation_remark = _parse_activation_status_line(
                line,
                runtime=runtime,
            )
        except ValueError as exc:
            invalid_rows.append(f"{line} -> {exc}")
            continue
        rows.append(
            {
                "mobile": mobile,
                "activation_status": activation_status,
                "activation_remark": activation_remark,
            }
        )
    return {
        "input_mode": "pasted_text",
        "total_rows": total_rows,
        "rows": rows,
        "invalid_rows": invalid_rows,
    }


def _parse_activation_status_from_file(
    *,
    file_name: str,
    file_bytes: bytes,
    runtime: ImportRuntime,
) -> dict[str, Any]:
    lines = _parse_column_lines_from_file(file_name=file_name, file_bytes=file_bytes, column_count=3)
    result = _parse_activation_status_from_text("\n".join(lines), runtime=runtime)
    result["input_mode"] = "file"
    result["file_name"] = str(file_name or "").strip()
    return result


def _create_user_ops_import_batch(
    *,
    import_type: str,
    file_name: str,
    total_rows: int,
    success_rows: int,
    failed_rows: int,
    error_summary: str,
    created_by: str,
) -> int:
    row = get_db().execute(
        """
        INSERT INTO user_ops_import_batches (
            import_type, file_name, total_rows, success_rows, failed_rows, error_summary, created_by, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        RETURNING id
        """,
        (
            import_type,
            file_name,
            int(total_rows),
            int(success_rows),
            int(failed_rows),
            error_summary,
            created_by,
        ),
    ).fetchone()
    return int(row["id"])


def _dedupe_user_ops_import_rows_by_mobile(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    deduped_by_mobile: dict[str, dict[str, Any]] = {}
    for row in rows:
        deduped_by_mobile[str(row["mobile"])] = row
    unique_rows = list(deduped_by_mobile.values())
    duplicate_count = max(0, len(rows) - len(unique_rows))
    return unique_rows, duplicate_count


def upsert_user_ops_huangxiaocan_activation_source(
    *,
    mobile: str,
    activation_state: str,
    activation_remark: str = "",
    import_batch_id: str = "",
    created_by: str = "",
    is_active: bool = True,
    runtime: ImportRuntime,
) -> dict[str, Any]:
    """Internal stable owner for activation-source upserts; legacy service facade may call this."""

    normalized_mobile = runtime.normalize_mobile(mobile)
    normalized_state = runtime.normalize_lead_pool_activation_state(
        activation_state,
        allow_unknown=False,
    )
    normalized_remark = str(activation_remark or "").strip()
    operator = _resolve_import_operator(created_by, runtime=runtime)
    db = get_db()
    existing = db.execute(
        """
        SELECT id, mobile, activation_state, import_batch_id, created_by, is_active
        FROM user_ops_huangxiaocan_activation_source
        WHERE mobile = ?
        LIMIT 1
        """,
        (normalized_mobile,),
    ).fetchone()
    db.execute(
        """
        INSERT INTO user_ops_huangxiaocan_activation_source (
            mobile, activation_state, import_batch_id, created_by, is_active, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(mobile) DO UPDATE SET
            activation_state = excluded.activation_state,
            import_batch_id = excluded.import_batch_id,
            created_by = excluded.created_by,
            is_active = excluded.is_active,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            normalized_mobile,
            normalized_state,
            str(import_batch_id or "").strip(),
            operator,
            runtime.db_bool(bool(is_active)),
        ),
    )
    apply_payload = runtime.apply_activation_source_to_existing_member(
        mobile=normalized_mobile,
        activation_state=normalized_state,
        operator=operator,
        source_type="huangxiaocan_activation_import",
        remark=normalized_remark or "patched existing lead member from activation source",
    )
    current_pool_apply_payload = _apply_activation_status_to_user_ops_pool_current_member(
        mobile=normalized_mobile,
        activation_status=normalized_state,
        activation_remark=normalized_remark,
        runtime=runtime,
    )
    source_row = db.execute(
        """
        SELECT mobile, activation_state, import_batch_id, created_by, is_active, created_at, updated_at
        FROM user_ops_huangxiaocan_activation_source
        WHERE mobile = ?
        LIMIT 1
        """,
        (normalized_mobile,),
    ).fetchone()
    db.commit()
    return {
        "ok": True,
        "action_type": "activation_source_insert" if existing is None else "activation_source_update",
        "matched_member": bool(
            apply_payload.get("matched_member") or current_pool_apply_payload.get("matched_member")
        ),
        "created_member": False,
        "source": {
            "mobile": normalized_mobile,
            "activation_state": normalized_state,
            "import_batch_id": str((source_row or {}).get("import_batch_id") or "").strip(),
            "created_by": str((source_row or {}).get("created_by") or "").strip(),
            "is_active": bool((source_row or {}).get("is_active")),
        },
        "member": apply_payload.get("member"),
    }


def import_experience_leads(
    *,
    pasted_text: str = "",
    file_name: str = "",
    file_bytes: bytes | None = None,
    created_by: str = "",
    runtime: ImportRuntime,
) -> dict[str, Any]:
    """Internal stable owner for experience-lead imports; legacy service facade may call this."""

    operator = _resolve_import_operator(created_by, runtime=runtime)
    if file_bytes is not None:
        parsed = _parse_experience_leads_from_file(
            file_name=file_name,
            file_bytes=file_bytes,
            runtime=runtime,
        )
    else:
        parsed = _parse_experience_leads_from_text(pasted_text, runtime=runtime)

    unique_mobiles = list(parsed["unique_mobiles"])
    invalid_rows = list(parsed["invalid_rows"])
    total_rows = int(parsed["total_rows"])
    success_rows = len(parsed["valid_rows"])
    failed_rows = len(invalid_rows)
    duplicate_count = int(parsed["duplicate_count"])

    if not unique_mobiles:
        raise ValueError("no valid mobile numbers found")

    error_summary = _build_import_error_summary(invalid_rows, duplicate_count)

    db = get_db()
    batch_id = _create_user_ops_import_batch(
        import_type="experience_leads",
        file_name=str(parsed.get("file_name") or file_name or parsed.get("input_mode") or "").strip(),
        total_rows=total_rows,
        success_rows=success_rows,
        failed_rows=failed_rows,
        error_summary=error_summary,
        created_by=operator,
    )

    for mobile in unique_mobiles:
        existing = db.execute(
            """
            SELECT id, mobile, source_type, import_batch_id, created_by, is_active
            FROM user_ops_experience_leads
            WHERE mobile = ?
            LIMIT 1
            """,
            (mobile,),
        ).fetchone()
        db.execute(
            """
            INSERT INTO user_ops_experience_leads (
                mobile, source_type, import_batch_id, created_by, is_active, created_at, updated_at
            )
            VALUES (?, 'experience_import', ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(mobile) DO UPDATE SET
                source_type = excluded.source_type,
                import_batch_id = excluded.import_batch_id,
                created_by = excluded.created_by,
                is_active = excluded.is_active,
                updated_at = CURRENT_TIMESTAMP
            """,
            (mobile, batch_id, operator, runtime.db_bool(True)),
        )
        db.execute(
            """
            INSERT INTO user_ops_pool_history (
                pool_id, mobile, external_userid, action_type, old_payload_json, new_payload_json, operator, source_type, created_at
            )
            VALUES (?, ?, '', ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                None,
                mobile,
                "experience_import_source_upsert",
                json.dumps(dict(existing or {}), ensure_ascii=False),
                json.dumps(
                    {
                        "mobile": mobile,
                        "source_type": "experience_import",
                        "import_batch_id": batch_id,
                        "created_by": operator,
                        "is_active": True,
                    },
                    ensure_ascii=False,
                ),
                operator,
                "experience_import",
            ),
        )
    db.commit()

    return {
        "ok": True,
        "import_type": "experience_leads",
        "input_mode": str(parsed.get("input_mode") or "").strip(),
        "batch_id": batch_id,
        "total_rows": total_rows,
        "success_rows": success_rows,
        "failed_rows": failed_rows,
        "duplicate_count": duplicate_count,
        "unique_mobile_count": len(unique_mobiles),
        "invalid_rows": invalid_rows,
        "reload": {"mode": "legacy_pool_disabled", "triggered": False},
    }


def import_mobile_class_term_source(
    *,
    pasted_text: str = "",
    file_name: str = "",
    file_bytes: bytes | None = None,
    created_by: str = "",
    runtime: ImportRuntime,
) -> dict[str, Any]:
    """Internal stable owner for class-term import pipeline; legacy service facade may call this."""

    operator = _resolve_import_operator(created_by, runtime=runtime)
    if file_bytes is not None:
        parsed = _parse_class_term_source_from_file(
            file_name=file_name,
            file_bytes=file_bytes,
            runtime=runtime,
        )
    else:
        parsed = _parse_class_term_source_from_text(pasted_text, runtime=runtime)

    rows = list(parsed["rows"])
    invalid_rows = list(parsed["invalid_rows"])
    total_rows = int(parsed["total_rows"])
    failed_rows = len(invalid_rows)

    if not rows:
        raise ValueError("no valid class term rows found")

    unique_rows, duplicate_count = _dedupe_user_ops_import_rows_by_mobile(rows)

    error_summary = _build_import_error_summary(invalid_rows, duplicate_count)

    db = get_db()
    batch_id = _create_user_ops_import_batch(
        import_type="class_term_source",
        file_name=str(parsed.get("file_name") or file_name or parsed.get("input_mode") or "").strip(),
        total_rows=total_rows,
        success_rows=len(rows),
        failed_rows=failed_rows,
        error_summary=error_summary,
        created_by=operator,
    )

    applied_count = 0
    bound_count = 0
    members: list[dict[str, Any]] = []
    for row in unique_rows:
        mobile = str(row["mobile"] or "").strip()
        resolved = _resolve_lead_pool_binding_by_mobile(mobile, runtime=runtime)
        result = runtime.upsert_user_ops_lead_pool_member(
            mobile=mobile,
            external_userid=resolved["external_userid"],
            customer_name=resolved["customer_name"],
            owner_userid=resolved["owner_userid"],
            is_wecom_added=resolved["is_wecom_added"],
            is_mobile_bound=resolved["is_mobile_bound"],
            class_term_no=row["class_term_no"],
            class_term_label=row["class_term_label"],
            entry_source="student_import",
            operator=operator,
            remark=f"class term import batch={batch_id}",
        )
        _upsert_user_ops_pool_current_import_member(
            mobile=mobile,
            external_userid=resolved["external_userid"],
            customer_name=resolved["customer_name"],
            owner_userid=resolved["owner_userid"],
            is_wecom_bound=resolved["is_mobile_bound"],
            class_term_no=row["class_term_no"],
            class_term_label=row["class_term_label"],
            source_type="student_import",
            runtime=runtime,
        )
        members.append(dict(result.get("member") or {}))
        applied_count += 1
        if bool((result.get("member") or {}).get("is_wecom_added")):
            bound_count += 1

    db.commit()
    return {
        "ok": True,
        "import_type": "class_term_source",
        "input_mode": str(parsed.get("input_mode") or "").strip(),
        "batch_id": batch_id,
        "total_rows": total_rows,
        "success_rows": len(rows),
        "failed_rows": failed_rows,
        "duplicate_count": duplicate_count,
        "unique_mobile_count": len(unique_rows),
        "invalid_rows": invalid_rows,
        "applied_count": applied_count,
        "bound_count": bound_count,
        "members": members,
        "reload": {"mode": "incremental", "triggered": False},
    }


def import_activation_status_source(
    *,
    pasted_text: str = "",
    file_name: str = "",
    file_bytes: bytes | None = None,
    created_by: str = "",
    runtime: ImportRuntime,
) -> dict[str, Any]:
    """Internal stable owner for activation-status imports; legacy service facade may call this."""

    operator = _resolve_import_operator(created_by, runtime=runtime)
    if file_bytes is not None:
        parsed = _parse_activation_status_from_file(
            file_name=file_name,
            file_bytes=file_bytes,
            runtime=runtime,
        )
    else:
        parsed = _parse_activation_status_from_text(pasted_text, runtime=runtime)

    rows = list(parsed["rows"])
    invalid_rows = list(parsed["invalid_rows"])
    total_rows = int(parsed["total_rows"])
    failed_rows = len(invalid_rows)

    if invalid_rows:
        preview = " / ".join(invalid_rows[:5])
        suffix = " ..." if len(invalid_rows) > 5 else ""
        raise ValueError(f"invalid activation rows: {preview}{suffix}")
    if not rows:
        raise ValueError("no valid activation rows found")

    unique_rows, duplicate_count = _dedupe_user_ops_import_rows_by_mobile(rows)
    error_summary = _build_import_error_summary(invalid_rows, duplicate_count)

    batch_id = _create_user_ops_import_batch(
        import_type="activation_status",
        file_name=str(parsed.get("file_name") or file_name or parsed.get("input_mode") or "").strip(),
        total_rows=total_rows,
        success_rows=len(rows),
        failed_rows=failed_rows,
        error_summary=error_summary,
        created_by=operator,
    )

    matched_member_count = 0
    members: list[dict[str, Any]] = []
    for row in unique_rows:
        result = upsert_user_ops_huangxiaocan_activation_source(
            mobile=str(row["mobile"]),
            activation_state=str(row["activation_status"]),
            activation_remark=str(row.get("activation_remark") or ""),
            import_batch_id=str(batch_id),
            created_by=operator,
            is_active=True,
            runtime=runtime,
        )
        if result["matched_member"]:
            matched_member_count += 1
            if result.get("member"):
                members.append(dict(result["member"]))
    return {
        "ok": True,
        "import_type": "activation_status",
        "input_mode": str(parsed.get("input_mode") or "").strip(),
        "batch_id": batch_id,
        "total_rows": total_rows,
        "success_rows": len(rows),
        "failed_rows": failed_rows,
        "duplicate_count": duplicate_count,
        "unique_mobile_count": len(unique_rows),
        "invalid_rows": invalid_rows,
        "matched_member_count": matched_member_count,
        "created_member_count": 0,
        "members": members,
        "reload": {"mode": "incremental", "triggered": False},
    }


def migrate_legacy_user_ops_pool_to_lead_pool(
    *,
    operator: str = "",
    runtime: ImportRuntime,
) -> dict[str, Any]:
    """Internal stable owner for legacy pool migration; legacy service facade may call this."""

    rows = get_db().execute(
        """
        SELECT
            mobile,
            external_userid,
            customer_name,
            owner_userid,
            is_wecom_bound,
            activation_status,
            class_term_no,
            class_term_label,
            source_type
        FROM user_ops_pool_current
        WHERE class_term_no IS NOT NULL
           OR (
                COALESCE(mobile, '') <> ''
                AND COALESCE(source_type, '') = 'experience_import'
                AND COALESCE(is_wecom_bound, false) = ?
           )
        ORDER BY id ASC
        """,
        (runtime.db_bool(False),),
    ).fetchall()
    normalized_operator = str(operator or runtime.current_operator_resolver()).strip() or "admin_user_ops"
    migrated_count = 0
    for row in rows:
        runtime.upsert_user_ops_lead_pool_member(
            mobile=str(row.get("mobile") or "").strip(),
            external_userid=str(row.get("external_userid") or "").strip(),
            customer_name=str(row.get("customer_name") or "").strip(),
            owner_userid=str(row.get("owner_userid") or "").strip(),
            is_wecom_added=bool(str(row.get("external_userid") or "").strip()),
            is_mobile_bound=bool(row.get("is_wecom_bound")),
            huangxiaocan_activation_state=_normalize_legacy_user_ops_activation_for_lead_pool(
                str(row.get("activation_status") or "").strip()
            ),
            class_term_no=int(row["class_term_no"]) if row.get("class_term_no") not in (None, "") else None,
            class_term_label=str(row.get("class_term_label") or "").strip(),
            entry_source="legacy_pool_migration",
            operator=normalized_operator,
            remark=f"migrated from legacy source_type={str(row.get('source_type') or '').strip()}",
        )
        migrated_count += 1
    return {"ok": True, "migrated_count": migrated_count}
