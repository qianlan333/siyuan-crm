from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import re
from typing import Any, Protocol
from uuid import uuid4

from aicrm_next.navigation_target.service import normalize_completion_target_for_storage
from aicrm_next.shared.repository_provider import RepositoryProviderError, assert_repository_allowed
from aicrm_next.shared.runtime import production_data_ready, raw_database_url
from aicrm_next.shared.runtime_settings import runtime_setting
from .domain import CHOICE_QUESTION_TYPES, selected_choice_options


class QuestionnaireRepository(Protocol):
    source_status: str
    read_model_status: str

    def list_questionnaires(self, *, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]: ...
    def get_questionnaire(self, questionnaire_id: int) -> dict[str, Any] | None: ...
    def get_questionnaire_by_slug(self, slug: str) -> dict[str, Any] | None: ...
    def list_questions(self, questionnaire_id: int) -> list[dict[str, Any]] | None: ...
    def get_results_summary(self, questionnaire_id: int) -> dict[str, Any] | None: ...
    def list_submissions(self, questionnaire_id: int, *, limit: int = 20, offset: int = 0) -> tuple[list[dict[str, Any]], int] | None: ...
    def list_external_submissions(
        self,
        *,
        filters: dict[str, Any],
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]: ...
    def save_questionnaire(self, payload: dict[str, Any], questionnaire_id: int | None = None) -> dict[str, Any]: ...
    def set_enabled(self, questionnaire_id: int, enabled: bool) -> dict[str, Any] | None: ...
    def delete_questionnaire(self, questionnaire_id: int) -> bool: ...
    def create_submission(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def get_submission(self, submission_id: str) -> dict[str, Any] | None: ...
    def find_submission_for_identity(self, questionnaire_id: int, identity: dict[str, Any]) -> dict[str, Any] | None: ...
    def latest_submission(self, questionnaire_id: int) -> dict[str, Any] | None: ...
    def export_submissions(self, questionnaire_id: int) -> dict[str, Any] | None: ...
    def get_app_setting(self, key: str) -> str | None: ...
    def create_external_push_log(self, **kwargs: Any) -> dict[str, Any]: ...
    def list_external_push_log_threads(
        self,
        questionnaire_id: int | None = None,
        *,
        questionnaire_title: str = "",
        user_id: str = "",
        target_url: str = "",
        status: str = "",
        limit: int | None = 50,
    ) -> list[dict[str, Any]]: ...
    def count_external_push_logs(
        self,
        *,
        questionnaire_id: int | None = None,
        questionnaire_title: str = "",
        user_id: str = "",
        target_url: str = "",
        status: str = "",
        created_at_gte: str = "",
    ) -> int: ...
    def summarize_external_push_logs(self, questionnaire_id: int) -> dict[str, Any]: ...
    def get_external_push_log(self, log_id: int) -> dict[str, Any] | None: ...
    def count_external_push_retry_logs(self, root_log_id: int) -> int: ...


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _identity_lookup_values(identity: dict[str, Any] | None) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for field in ("external_userid", "unionid", "openid", "respondent_key", "mobile"):
        value = _text((identity or {}).get(field)).strip()
        if not value:
            continue
        pair = (field, value)
        if pair in seen:
            continue
        seen.add(pair)
        values.append(pair)
    return values


def _timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return _text(value)


def _json_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _json_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _json_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _jsonb(value: Any) -> Any:
    from psycopg.types.json import Jsonb

    return Jsonb(value, dumps=_json_dumps)


def _normalized_external_push_log(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    payload["id"] = int(payload.get("id") or 0)
    payload["questionnaire_id"] = int(payload.get("questionnaire_id") or 0)
    payload["submission_record_id"] = int(payload.get("submission_record_id") or 0)
    payload["retry_from_log_id"] = int(payload.get("retry_from_log_id") or 0) or None
    payload["retry_attempt"] = int(payload.get("retry_attempt") or 0)
    payload["request_payload"] = _json_payload(payload.get("request_payload"))
    payload["response_status_code"] = payload.get("response_status_code")
    payload["questionnaire_title_snapshot"] = _text(payload.get("questionnaire_title_snapshot"))
    payload["user_id"] = _text(payload.get("user_id"))
    payload["target_url"] = _text(payload.get("target_url"))
    payload["response_body"] = _text(payload.get("response_body"))
    payload["status"] = _text(payload.get("status"))
    payload["failure_reason"] = _text(payload.get("failure_reason"))
    payload["created_at"] = _timestamp(payload.get("created_at"))
    payload["updated_at"] = _timestamp(payload.get("updated_at"))
    return payload


def _external_push_log_threads(
    rows: list[dict[str, Any]],
    *,
    status: str = "",
    limit: int | None = 50,
) -> list[dict[str, Any]]:
    normalized = [_normalized_external_push_log(row) for row in rows]
    roots = [row for row in normalized if not row.get("retry_from_log_id")]
    retries_by_root: dict[int, list[dict[str, Any]]] = {int(row["id"]): [] for row in roots}
    for row in normalized:
        root_id = int(row.get("retry_from_log_id") or 0)
        if root_id:
            retries_by_root.setdefault(root_id, []).append(row)
    threads: list[dict[str, Any]] = []
    normalized_status = _text(status).strip()
    for root in roots:
        retries = sorted(
            retries_by_root.get(int(root["id"]), []),
            key=lambda item: (_text(item.get("created_at")), int(item.get("id") or 0)),
            reverse=True,
        )
        latest = retries[0] if retries else root
        latest_status = _text(latest.get("status")).strip()
        if normalized_status and latest_status != normalized_status:
            continue
        threads.append(
            {
                **root,
                "is_retry": False,
                "retry_count": len(retries),
                "retries": retries,
                "latest_log": latest,
                "latest_status": latest_status,
                "latest_response_status_code": latest.get("response_status_code"),
                "latest_response_body": latest.get("response_body"),
                "latest_failure_reason": latest.get("failure_reason"),
                "latest_updated_at": latest.get("updated_at") or latest.get("created_at"),
                "has_retry": bool(retries),
                "can_retry": latest_status == "failed",
            }
        )
    threads.sort(
        key=lambda item: (_text(item.get("latest_updated_at")), int((item.get("latest_log") or {}).get("id") or 0)),
        reverse=True,
    )
    if limit is None:
        return threads
    return threads[: max(1, min(int(limit or 50), 200))]


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _slugify_questionnaire(value: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    if not base:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        base = f"q-{timestamp}-{uuid4().hex[:6]}"
    return base[:120]


def _external_push_payload(payload: dict[str, Any]) -> dict[str, Any]:
    config = dict(payload.get("external_push_config") or {})
    return {
        "enabled": _as_bool(payload.get("external_push_enabled", config.get("enabled"))),
        "url": _text(payload.get("external_push_url") or config.get("webhook_url")),
        "type": _text(payload.get("external_push_type") or config.get("type")),
        "expires_at_ts": _optional_int(payload.get("external_push_expires_at_ts", config.get("expires_at_ts"))),
        "day": _optional_int(payload.get("external_push_day", config.get("day"))),
        "frequency": _optional_int(payload.get("external_push_frequency", config.get("frequency"))),
        "remark": _text(payload.get("external_push_remark") or config.get("remark")),
        "custom_params": _json_list(payload.get("external_push_custom_params", config.get("custom_params"))),
    }


def _questionnaire_payload(payload: dict[str, Any], *, slug: str) -> dict[str, Any]:
    external_push = _external_push_payload(payload)
    assessment_config = _json_dict(payload.get("assessment_config") or payload.get("result_config"))
    title = _text(payload.get("title") or payload.get("name")).strip()
    completion_target = normalize_completion_target_for_storage(payload, legacy_url_key="redirect_url")
    return {
        "slug": slug,
        "name": _text(payload.get("name") or title).strip(),
        "title": title,
        "description": _text(payload.get("description")),
        "is_disabled": _as_bool(payload.get("is_disabled"), default=not _as_bool(payload.get("enabled"), default=True)),
        "redirect_url": _text(payload.get("redirect_url")),
        "completion_target_json": completion_target,
        "answer_display_mode": _text(payload.get("answer_display_mode") or "all_in_one") or "all_in_one",
        "assessment_enabled": _as_bool(payload.get("assessment_enabled")),
        "assessment_config": assessment_config,
        "external_push": external_push,
    }


def _answer_value_list(raw_value: Any) -> list[str]:
    if raw_value is None:
        return []
    if isinstance(raw_value, list):
        return [str(item) for item in raw_value if item not in (None, "")]
    if raw_value == "":
        return []
    return [str(raw_value)]


def _text_answer(raw_value: Any) -> str:
    values = _answer_value_list(raw_value)
    return "、".join(values)


def _answer_snapshots(questions: list[dict[str, Any]], answers: dict[str, Any]) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for question in questions:
        question_id = question.get("id")
        question_key = str(question_id)
        if question_key not in answers:
            continue
        question_type = _text(question.get("type") or "single_choice")
        raw_value = answers.get(question_key)
        selected_options: list[dict[str, Any]] = []
        other_text = ""
        if question_type in CHOICE_QUESTION_TYPES:
            selected_options, other_text = selected_choice_options(question, raw_value)
        selected_option_scores = [float(option.get("score") or 0) for option in selected_options]
        selected_option_tags: list[str] = []
        for option in selected_options:
            for tag_code in option.get("tag_codes") or []:
                tag_text = str(tag_code or "").strip()
                if tag_text and tag_text not in selected_option_tags:
                    selected_option_tags.append(tag_text)
        selected_other_text = other_text.strip() if any(bool(option.get("is_other")) for option in selected_options) else ""
        snapshots.append(
            {
                "question_id": question_id,
                "question_type": question_type,
                "question_title_snapshot": _text(question.get("title")),
                "selected_option_ids": [option.get("id") for option in selected_options],
                "selected_option_texts_snapshot": [_text(option.get("label") or option.get("option_text")) for option in selected_options],
                "selected_option_scores_snapshot": selected_option_scores,
                "selected_option_tags_snapshot": selected_option_tags,
                "text_value": _text_answer(raw_value) if question_type in {"textarea", "mobile"} else selected_other_text,
                "score_contribution": sum(selected_option_scores) if question_type not in {"textarea", "mobile"} else 0.0,
            }
        )
    return snapshots


def _answers_from_snapshots(answer_snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    answers: dict[str, Any] = {}
    for snapshot in answer_snapshots:
        key = str(snapshot.get("question_id"))
        question_type = _text(snapshot.get("question_type") or "single_choice")
        if question_type in {"textarea", "mobile"}:
            answers[key] = _text(snapshot.get("text_value"))
            continue
        selected = _json_list(snapshot.get("selected_option_ids"))
        other_text = _text(snapshot.get("text_value")).strip()
        if other_text:
            answers[key] = {"selected_option_ids": selected, "other_text": other_text}
        else:
            answers[key] = selected[0] if len(selected) == 1 else selected
    return answers


def _external_answer_projection(answer: dict[str, Any]) -> dict[str, Any]:
    return {
        "question_title_snapshot": _text(answer.get("question_title_snapshot")),
        "selected_option_texts_snapshot": _json_list(answer.get("selected_option_texts_snapshot")),
        "text_value": _text(answer.get("text_value")),
        "score_contribution": float(answer.get("score_contribution") or 0),
    }


def _external_submission_projection(row: dict[str, Any], answers: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "mobile": _text(row.get("mobile") or row.get("mobile_snapshot")),
        "unionid": _text(row.get("unionid")),
        "external_userid": _text(row.get("external_userid")),
        "submitted_at": _timestamp(row.get("submitted_at") or row.get("created_at")),
        "questionnaire_id": int(row.get("questionnaire_id") or 0),
        "questionnaire_title": _text(row.get("questionnaire_title") or row.get("title") or row.get("name")),
        "final_tags": _json_list(row.get("final_tags")),
        "assessment_result_snapshot": _json_dict(row.get("assessment_result_snapshot")),
        "answers": [_external_answer_projection(dict(answer)) for answer in answers or []],
    }


def _parse_comparable_timestamp(value: Any) -> datetime | None:
    text = _text(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
        return datetime.fromisoformat(text.replace(" ", "T")).replace(tzinfo=None)
    except ValueError:
        return None


def _matches_external_submission_filters(row: dict[str, Any], filters: dict[str, Any]) -> bool:
    if _text(filters.get("mobile")) and _text(row.get("mobile") or row.get("mobile_snapshot")) != _text(filters.get("mobile")):
        return False
    if _text(filters.get("unionid")) and _text(row.get("unionid")) != _text(filters.get("unionid")):
        return False
    if _text(filters.get("external_userid")) and _text(row.get("external_userid")) != _text(filters.get("external_userid")):
        return False
    if filters.get("questionnaire_id") not in (None, "") and int(row.get("questionnaire_id") or 0) != int(filters.get("questionnaire_id") or 0):
        return False
    submitted_at = _parse_comparable_timestamp(row.get("submitted_at") or row.get("created_at"))
    submitted_from = _parse_comparable_timestamp(filters.get("submitted_from"))
    submitted_to = _parse_comparable_timestamp(filters.get("submitted_to"))
    if submitted_from and (not submitted_at or submitted_at < submitted_from):
        return False
    if submitted_to and (not submitted_at or submitted_at > submitted_to):
        return False
    return True


def _mobile_answer(questions: list[dict[str, Any]], answers: dict[str, Any]) -> str:
    for question in questions:
        if _text(question.get("type")) != "mobile":
            continue
        value = _text_answer(answers.get(str(question.get("id")))).strip()
        if value:
            return value
    return ""


def _psycopg_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    return url


def _initial_questionnaires() -> list[dict[str, Any]]:
    return [
        {
            "id": 1,
            "slug": "hxc-activation-v1",
            "title": "黄小璨激活问卷",
            "name": "黄小璨激活问卷",
            "description": "用于收集用户激活状态和后续运营标签。",
            "enabled": True,
            "redirect_url": "/s/hxc-activation-v1/submitted",
            "submit_button_text": "提交问卷",
            "created_at": "2026-05-01T10:00:00Z",
            "updated_at": "2026-05-20T10:00:00Z",
            "submission_count": 1,
            "assessment_enabled": False,
            "external_push_config": {
                "enabled": False,
                "status": "stubbed",
                "note": "第一阶段不真实外发 webhook。",
            },
            "questions": [
                {
                    "id": "q_activation",
                    "type": "single_choice",
                    "title": "黄小璨是否已激活？",
                    "required": True,
                    "options": [
                        {
                            "id": "activated",
                            "label": "已激活",
                            "value": "activated",
                            "tag_codes": ["tag_hxc_activated"],
                            "score": 10,
                        },
                        {
                            "id": "not_activated",
                            "label": "未激活",
                            "value": "not_activated",
                            "tag_codes": ["tag_hxc_not_activated"],
                            "score": 0,
                        },
                    ],
                },
                {
                    "id": "q_interest",
                    "type": "multi_choice",
                    "title": "你关注哪些能力？",
                    "required": False,
                    "options": [
                        {"id": "private_domain", "label": "私域运营", "value": "private_domain", "tag_codes": ["tag_interest_private_domain"], "score": 3},
                        {"id": "ai_tools", "label": "AI 工具", "value": "ai_tools", "tag_codes": ["tag_interest_ai_tools"], "score": 3},
                    ],
                },
                {
                    "id": "q_note",
                    "type": "textarea",
                    "title": "还有什么想补充？",
                    "required": False,
                    "options": [],
                    "placeholder_text": "可填写你最想解决的问题",
                },
            ],
        },
        {
            "id": 2,
            "slug": "disabled-demo",
            "title": "停用问卷样例",
            "name": "停用问卷样例",
            "description": "用于验证 disabled questionnaire contract。",
            "enabled": False,
            "redirect_url": "",
            "submit_button_text": "提交",
            "created_at": "2026-05-02T10:00:00Z",
            "updated_at": "2026-05-20T10:00:00Z",
            "submission_count": 0,
            "assessment_enabled": False,
            "external_push_config": {"enabled": False, "status": "stubbed"},
            "questions": [
                {
                    "id": "q_disabled",
                    "type": "single_choice",
                    "title": "停用问卷问题",
                    "required": True,
                    "options": [{"id": "yes", "label": "是", "value": "yes", "tag_codes": [], "score": 0}],
                }
            ],
        },
    ]


class InMemoryQuestionnaireRepository:
    source_status = "local_contract_probe"
    read_model_status = "fixture"

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._questionnaires = _initial_questionnaires()
        self._submissions: list[dict[str, Any]] = [
            {
                "submission_id": "sub_fixture_001",
                "result_token": "result_fixture_001_grant_7e3a9c5b2d8f4a61",
                "questionnaire_id": 1,
                "slug": "hxc-activation-v1",
                "answers": {"q_activation": "activated"},
                "respondent_identity": {"mobile": "mobile_masked_fixture"},
                "person_id": "person_fixture",
                "external_userid": "external_user_masked_fixture",
                "mobile": "mobile_masked_fixture",
                "score": 10,
                "final_tags": ["tag_hxc_activated"],
                "created_at": "2026-05-20T10:10:00Z",
            }
        ]
        self._external_push_logs: list[dict[str, Any]] = []
        self._next_id = max(item["id"] for item in self._questionnaires) + 1
        self._next_submission = len(self._submissions) + 1
        self._next_external_push_log = 1

    def list_questionnaires(self, *, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        rows = deepcopy(self._questionnaires)
        return rows[offset : offset + limit], len(rows)

    def _raw_questionnaire(self, questionnaire_id: int) -> dict[str, Any] | None:
        for item in self._questionnaires:
            if int(item["id"]) == int(questionnaire_id):
                return item
        return None

    def get_questionnaire(self, questionnaire_id: int) -> dict[str, Any] | None:
        item = self._raw_questionnaire(questionnaire_id)
        if item is None:
            return None
        payload = deepcopy(item)
        payload["submissions_summary"] = self.get_results_summary(questionnaire_id) or {}
        payload["submissions"] = (self.list_submissions(questionnaire_id, limit=10, offset=0) or ([], 0))[0]
        return payload

    def get_questionnaire_by_slug(self, slug: str) -> dict[str, Any] | None:
        slug = str(slug or "").strip()
        for item in self._questionnaires:
            if item.get("slug") == slug:
                return deepcopy(item)
        return None

    def list_questions(self, questionnaire_id: int) -> list[dict[str, Any]] | None:
        item = self._raw_questionnaire(questionnaire_id)
        if not item:
            return None
        return deepcopy(item.get("questions") or [])

    def get_results_summary(self, questionnaire_id: int) -> dict[str, Any] | None:
        item = self._raw_questionnaire(questionnaire_id)
        if not item:
            return None
        rows = [submission for submission in self._submissions if int(submission.get("questionnaire_id") or 0) == int(questionnaire_id)]
        return {
            "questionnaire_id": int(questionnaire_id),
            "submission_count": len(rows),
            "latest_submitted_at": rows[-1].get("created_at") if rows else "",
            "average_score": sum(float(row.get("score") or 0) for row in rows) / len(rows) if rows else 0,
            "result_config": deepcopy(item.get("result_config") or {}),
            "rules": deepcopy(item.get("rules") or []),
        }

    def list_submissions(self, questionnaire_id: int, *, limit: int = 20, offset: int = 0) -> tuple[list[dict[str, Any]], int] | None:
        questionnaire = self._raw_questionnaire(questionnaire_id)
        if not questionnaire:
            return None
        rows = []
        for item in self._submissions:
            if int(item.get("questionnaire_id") or 0) != int(questionnaire_id):
                continue
            row = deepcopy(item)
            row.setdefault("unionid", _text((row.get("respondent_identity") or {}).get("unionid")))
            if "answer_snapshots" not in row:
                row["answer_snapshots"] = _answer_snapshots(questionnaire.get("questions") or [], dict(row.get("answers") or {}))
            rows.append(row)
        return rows[int(offset) : int(offset) + int(limit)], len(rows)

    def list_external_submissions(
        self,
        *,
        filters: dict[str, Any],
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        questionnaire_by_id = {int(item["id"]): item for item in self._questionnaires}
        rows: list[dict[str, Any]] = []
        for item in self._submissions:
            questionnaire = questionnaire_by_id.get(int(item.get("questionnaire_id") or 0))
            if not questionnaire:
                continue
            row = deepcopy(item)
            row.setdefault("submitted_at", row.get("created_at"))
            row.setdefault("mobile", row.get("mobile_snapshot") or row.get("mobile"))
            row.setdefault("assessment_result_snapshot", (row.get("result_json") or {}).get("assessment_result") if isinstance(row.get("result_json"), dict) else {})
            row["questionnaire_title"] = _text(questionnaire.get("title") or questionnaire.get("name"))
            if "answer_snapshots" not in row:
                row["answer_snapshots"] = _answer_snapshots(questionnaire.get("questions") or [], dict(row.get("answers") or {}))
            if _matches_external_submission_filters(row, filters):
                rows.append(row)
        rows.sort(key=lambda item: (_text(item.get("submitted_at") or item.get("created_at")), _text(item.get("submission_id"))), reverse=True)
        page = rows[int(offset) : int(offset) + int(limit)]
        return [_external_submission_projection(row, row.get("answer_snapshots") or []) for row in page], len(rows)

    def save_questionnaire(self, payload: dict[str, Any], questionnaire_id: int | None = None) -> dict[str, Any]:
        now = _now()
        if questionnaire_id is None:
            item = {
                "id": self._next_id,
                "slug": str(payload.get("slug") or f"questionnaire-{self._next_id}").strip(),
                "created_at": now,
                "submission_count": 0,
                "assessment_enabled": False,
            }
            self._next_id += 1
            self._questionnaires.append(item)
        else:
            item = next((entry for entry in self._questionnaires if int(entry["id"]) == int(questionnaire_id)), None)
            if item is None:
                return {}
        item.update(
            {
                "title": str(payload.get("title") or item.get("title") or "").strip(),
                "name": str(payload.get("title") or item.get("name") or "").strip(),
                "description": str(payload.get("description") or ""),
                "enabled": bool(payload.get("enabled", item.get("enabled", True))),
                "redirect_url": str(payload.get("redirect_url") or ""),
                "completion_target_json": deepcopy(
                    payload.get("completion_target_json")
                    or normalize_completion_target_for_storage(payload, legacy_url_key="redirect_url")
                ),
                "submit_button_text": str(payload.get("submit_button_text") or "提交"),
                "answer_display_mode": str(payload.get("answer_display_mode") or item.get("answer_display_mode") or "all_in_one"),
                "assessment_enabled": bool(payload.get("assessment_enabled", item.get("assessment_enabled", False))),
                "assessment_config": deepcopy(payload.get("assessment_config") or payload.get("result_config") or item.get("assessment_config") or {}),
                "result_config": deepcopy(payload.get("result_config") or payload.get("assessment_config") or item.get("result_config") or {}),
                "updated_at": now,
                "questions": deepcopy(payload.get("questions") or item.get("questions") or []),
                "score_rules": deepcopy(payload.get("score_rules") or payload.get("rules") or item.get("score_rules") or []),
                "rules": deepcopy(payload.get("rules") or payload.get("score_rules") or item.get("rules") or []),
                "external_push_config": deepcopy(payload.get("external_push_config") or item.get("external_push_config") or {}),
            }
        )
        return deepcopy(item)

    def set_enabled(self, questionnaire_id: int, enabled: bool) -> dict[str, Any] | None:
        item = next((entry for entry in self._questionnaires if int(entry["id"]) == int(questionnaire_id)), None)
        if item is None:
            return None
        item["enabled"] = bool(enabled)
        item["updated_at"] = _now()
        return deepcopy(item)

    def delete_questionnaire(self, questionnaire_id: int) -> bool:
        before = len(self._questionnaires)
        self._questionnaires = [item for item in self._questionnaires if int(item["id"]) != int(questionnaire_id)]
        return len(self._questionnaires) < before

    def create_submission(self, payload: dict[str, Any]) -> dict[str, Any]:
        submission = deepcopy(payload)
        submission["submission_id"] = submission.get("submission_id") or f"sub_next_{self._next_submission:03d}"
        submission["created_at"] = submission.get("created_at") or _now()
        questionnaire = self._raw_questionnaire(int(submission["questionnaire_id"]))
        if questionnaire and "answer_snapshots" not in submission:
            submission["answer_snapshots"] = _answer_snapshots(questionnaire.get("questions") or [], dict(submission.get("answers") or {}))
        self._next_submission += 1
        self._submissions.append(submission)
        for item in self._questionnaires:
            if int(item["id"]) == int(submission["questionnaire_id"]):
                item["submission_count"] = int(item.get("submission_count") or 0) + 1
                item["updated_at"] = _now()
        return deepcopy(submission)

    def get_submission(self, submission_id: str) -> dict[str, Any] | None:
        for item in self._submissions:
            if item.get("result_token") == submission_id:
                payload = deepcopy(item)
                if isinstance(payload.get("answer_snapshots"), list):
                    payload["answers"] = _answers_from_snapshots(payload["answer_snapshots"])
                    payload["answers_json"] = payload["answers"]
                return payload
        return None

    def find_submission_for_identity(self, questionnaire_id: int, identity: dict[str, Any]) -> dict[str, Any] | None:
        candidates = _identity_lookup_values(identity)
        if not candidates:
            return None
        for item in reversed(self._submissions):
            if int(item.get("questionnaire_id") or 0) != int(questionnaire_id):
                continue
            respondent_identity = item.get("respondent_identity") if isinstance(item.get("respondent_identity"), dict) else {}
            if any(
                _text(item.get(field) or respondent_identity.get(field) or (item.get("mobile_snapshot") if field == "mobile" else "")) == value
                for field, value in candidates
            ):
                return deepcopy(item)
        return None

    def latest_submission(self, questionnaire_id: int) -> dict[str, Any] | None:
        for item in reversed(self._submissions):
            if int(item.get("questionnaire_id") or 0) == int(questionnaire_id):
                return deepcopy(item)
        return None

    def export_submissions(self, questionnaire_id: int) -> dict[str, Any] | None:
        if not self.get_questionnaire(questionnaire_id):
            return None
        rows = [item for item in self._submissions if int(item.get("questionnaire_id") or 0) == int(questionnaire_id)]
        return {
            "filename": f"questionnaire_{questionnaire_id}_submissions.json",
            "items": deepcopy(rows),
            "total": len(rows),
            "format": "json",
        }

    def get_app_setting(self, key: str) -> str | None:
        return None

    def create_external_push_log(self, **kwargs: Any) -> dict[str, Any]:
        row = dict(kwargs)
        row["id"] = self._next_external_push_log
        row["created_at"] = _now()
        row["updated_at"] = row["created_at"]
        self._next_external_push_log += 1
        self._external_push_logs.append(row)
        return deepcopy(row)

    def list_external_push_log_threads(
        self,
        questionnaire_id: int | None = None,
        *,
        questionnaire_title: str = "",
        user_id: str = "",
        target_url: str = "",
        status: str = "",
        limit: int | None = 50,
    ) -> list[dict[str, Any]]:
        title_filter = _text(questionnaire_title).strip()
        user_filter = _text(user_id).strip()
        target_filter = _text(target_url).strip()
        rows = []
        for row in self._external_push_logs:
            if questionnaire_id is not None and int(row.get("questionnaire_id") or 0) != int(questionnaire_id):
                continue
            if title_filter and title_filter not in _text(row.get("questionnaire_title_snapshot")):
                continue
            if user_filter and user_filter not in _text(row.get("user_id")):
                continue
            if target_filter and target_filter not in _text(row.get("target_url")):
                continue
            rows.append(deepcopy(row))
        return _external_push_log_threads(rows, status=status, limit=limit)

    def count_external_push_logs(
        self,
        *,
        questionnaire_id: int | None = None,
        questionnaire_title: str = "",
        user_id: str = "",
        target_url: str = "",
        status: str = "",
        created_at_gte: str = "",
    ) -> int:
        title_filter = _text(questionnaire_title).strip()
        user_filter = _text(user_id).strip()
        target_filter = _text(target_url).strip()
        status_filter = _text(status).strip()
        since_filter = _text(created_at_gte).strip()
        total = 0
        for row in self._external_push_logs:
            normalized = _normalized_external_push_log(deepcopy(row))
            if questionnaire_id is not None and int(normalized.get("questionnaire_id") or 0) != int(questionnaire_id):
                continue
            if title_filter and title_filter not in _text(normalized.get("questionnaire_title_snapshot")):
                continue
            if user_filter and user_filter not in _text(normalized.get("user_id")):
                continue
            if target_filter and target_filter not in _text(normalized.get("target_url")):
                continue
            if status_filter and _text(normalized.get("status")) != status_filter:
                continue
            if since_filter and _text(normalized.get("created_at")) < since_filter:
                continue
            total += 1
        return total

    def summarize_external_push_logs(self, questionnaire_id: int) -> dict[str, Any]:
        rows = [
            _normalized_external_push_log(deepcopy(row))
            for row in self._external_push_logs
            if int(row.get("questionnaire_id") or 0) == int(questionnaire_id)
        ]
        return {
            "total_count": len(rows),
            "success_count": sum(1 for row in rows if row.get("status") == "success"),
            "failed_count": sum(1 for row in rows if row.get("status") == "failed"),
            "last_created_at": max((_text(row.get("created_at")) for row in rows), default=""),
        }

    def get_external_push_log(self, log_id: int) -> dict[str, Any] | None:
        for row in self._external_push_logs:
            if int(row.get("id") or 0) == int(log_id):
                return _normalized_external_push_log(deepcopy(row))
        return None

    def count_external_push_retry_logs(self, root_log_id: int) -> int:
        return sum(1 for row in self._external_push_logs if int(row.get("retry_from_log_id") or 0) == int(root_log_id))


class PostgresQuestionnaireReadRepository:
    source_status = "next_read_model"
    read_model_status = "primary"

    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = _psycopg_url(str(database_url or raw_database_url()).strip())
        if not self._database_url:
            raise RepositoryProviderError("questionnaire production read repository unavailable: DATABASE_URL is required")

    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except Exception as exc:  # pragma: no cover - dependency failure varies by runtime
            raise RepositoryProviderError("psycopg is required for questionnaire production read repository") from exc
        return psycopg.connect(self._database_url, row_factory=dict_row)

    def _questionnaire_from_row(self, row: dict[str, Any]) -> dict[str, Any]:
        enabled = not bool(row.get("is_disabled"))
        external_push_config = {
            "enabled": bool(row.get("external_push_enabled")),
            "webhook_url": _text(row.get("external_push_url")),
            "type": _text(row.get("external_push_type")),
            "expires_at_ts": row.get("external_push_expires_at_ts"),
            "day": row.get("external_push_day"),
            "frequency": row.get("external_push_frequency"),
            "remark": _text(row.get("external_push_remark")),
            "custom_params": _json_list(row.get("external_push_custom_params")),
        }
        return {
            "id": int(row["id"]),
            "slug": _text(row.get("slug")),
            "name": _text(row.get("name")),
            "title": _text(row.get("title") or row.get("name")),
            "description": _text(row.get("description")),
            "enabled": enabled,
            "is_disabled": not enabled,
            "status": "disabled" if not enabled else "published",
            "version": int(row.get("version") or 1),
            "redirect_url": _text(row.get("redirect_url")),
            "completion_target_json": _json_dict(row.get("completion_target_json")),
            "answer_display_mode": _text(row.get("answer_display_mode") or "all_in_one"),
            "assessment_enabled": bool(row.get("assessment_enabled")),
            "assessment_config": _json_dict(row.get("assessment_config")),
            "result_config": _json_dict(row.get("assessment_config")),
            "external_push_config": external_push_config,
            "external_push_enabled": external_push_config["enabled"],
            "external_push_url": external_push_config["webhook_url"],
            "external_push_type": external_push_config["type"],
            "external_push_expires_at_ts": external_push_config["expires_at_ts"],
            "external_push_day": external_push_config["day"],
            "external_push_frequency": external_push_config["frequency"],
            "external_push_remark": external_push_config["remark"],
            "external_push_custom_params": external_push_config["custom_params"],
            "created_at": _timestamp(row.get("created_at")),
            "updated_at": _timestamp(row.get("updated_at")),
            "question_count": int(row.get("question_count") or 0),
            "submission_count": int(row.get("submission_count") or 0),
            "last_submitted_at": _timestamp(row.get("last_submitted_at")),
            "questions": [],
            "rules": [],
            "score_rules": [],
            "submissions_summary": {},
            "submissions": [],
        }

    def _base_select(self) -> str:
        return """
            SELECT
                q.*,
                1 AS version,
                COALESCE(question_counts.question_count, 0) AS question_count,
                COALESCE(submission_counts.submission_count, 0) AS submission_count,
                submission_counts.last_submitted_at AS last_submitted_at
            FROM questionnaires q
            LEFT JOIN (
                SELECT questionnaire_id, COUNT(*) AS question_count
                FROM questionnaire_questions
                GROUP BY questionnaire_id
            ) question_counts ON question_counts.questionnaire_id = q.id
            LEFT JOIN (
                SELECT questionnaire_id, COUNT(*) AS submission_count, MAX(submitted_at) AS last_submitted_at
                FROM questionnaire_submissions
                GROUP BY questionnaire_id
            ) submission_counts ON submission_counts.questionnaire_id = q.id
        """

    def list_questionnaires(self, *, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        with self._connect() as conn:
            total = int((conn.execute("SELECT COUNT(*) AS total FROM questionnaires").fetchone() or {}).get("total") or 0)
            rows = conn.execute(
                self._base_select() + " ORDER BY q.updated_at DESC, q.id DESC LIMIT %s OFFSET %s",
                (int(limit), int(offset)),
            ).fetchall()
        return [self._questionnaire_from_row(dict(row)) for row in rows], total

    def get_questionnaire(self, questionnaire_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(self._base_select() + " WHERE q.id = %s", (int(questionnaire_id),)).fetchone()
        if not row:
            return None
        item = self._questionnaire_from_row(dict(row))
        item["questions"] = self.list_questions(questionnaire_id) or []
        item["rules"] = self._list_score_rules(questionnaire_id)
        item["score_rules"] = deepcopy(item["rules"])
        item["submissions_summary"] = self.get_results_summary(questionnaire_id) or {}
        submissions = self.list_submissions(questionnaire_id, limit=10, offset=0)
        item["submissions"] = submissions[0] if submissions else []
        return item

    def get_questionnaire_by_slug(self, slug: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(self._base_select() + " WHERE q.slug = %s", (str(slug or "").strip(),)).fetchone()
        if not row:
            return None
        return self.get_questionnaire(int(row["id"]))

    def list_questions(self, questionnaire_id: int) -> list[dict[str, Any]] | None:
        if not self._exists(questionnaire_id):
            return None
        with self._connect() as conn:
            question_rows = conn.execute(
                """
                SELECT *
                FROM questionnaire_questions
                WHERE questionnaire_id = %s
                ORDER BY sort_order ASC, id ASC
                """,
                (int(questionnaire_id),),
            ).fetchall()
            option_rows = conn.execute(
                """
                SELECT qo.*
                FROM questionnaire_options qo
                JOIN questionnaire_questions qq ON qq.id = qo.question_id
                WHERE qq.questionnaire_id = %s
                ORDER BY qo.sort_order ASC, qo.id ASC
                """,
                (int(questionnaire_id),),
            ).fetchall()
        options_by_question: dict[int, list[dict[str, Any]]] = {}
        for row in option_rows:
            payload = dict(row)
            question_id = int(payload.get("question_id") or 0)
            options_by_question.setdefault(question_id, []).append(
                {
                    "id": int(payload["id"]),
                    "label": _text(payload.get("option_text")),
                    "value": _text(payload.get("id")),
                    "option_text": _text(payload.get("option_text")),
                    "score": int(float(payload.get("score") or 0)),
                    "tag_codes": _json_list(payload.get("tag_codes")),
                    "is_other": bool(payload.get("is_other")),
                    "other_placeholder": _text(payload.get("other_placeholder")),
                    "other_max_length": int(payload.get("other_max_length") or 80),
                    "sort_order": int(payload.get("sort_order") or 0),
                }
            )
        questions: list[dict[str, Any]] = []
        for row in question_rows:
            payload = dict(row)
            question_id = int(payload["id"])
            questions.append(
                {
                    "id": question_id,
                    "type": _text(payload.get("type") or "single_choice"),
                    "title": _text(payload.get("title")),
                    "required": bool(payload.get("required")),
                    "placeholder_text": _text(payload.get("placeholder_text")),
                    "assessment_dimension_key": _text(payload.get("assessment_dimension_key")),
                    "sidebar_profile_field": _text(payload.get("sidebar_profile_field")),
                    "sort_order": int(payload.get("sort_order") or 0),
                    "created_at": _timestamp(payload.get("created_at")),
                    "updated_at": _timestamp(payload.get("updated_at")),
                    "options": options_by_question.get(question_id, []),
                }
            )
        return questions

    def get_results_summary(self, questionnaire_id: int) -> dict[str, Any] | None:
        if not self._exists(questionnaire_id):
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS submission_count,
                    MAX(submitted_at) AS latest_submitted_at,
                    COALESCE(AVG(total_score), 0) AS average_score
                FROM questionnaire_submissions
                WHERE questionnaire_id = %s
                """,
                (int(questionnaire_id),),
            ).fetchone()
        return {
            "questionnaire_id": int(questionnaire_id),
            "submission_count": int((row or {}).get("submission_count") or 0),
            "latest_submitted_at": _timestamp((row or {}).get("latest_submitted_at")),
            "average_score": float((row or {}).get("average_score") or 0),
            "rules": self._list_score_rules(questionnaire_id),
        }

    def list_submissions(self, questionnaire_id: int, *, limit: int = 20, offset: int = 0) -> tuple[list[dict[str, Any]], int] | None:
        if not self._exists(questionnaire_id):
            return None
        with self._connect() as conn:
            total = int(
                (conn.execute("SELECT COUNT(*) AS total FROM questionnaire_submissions WHERE questionnaire_id = %s", (int(questionnaire_id),)).fetchone() or {}).get("total")
                or 0
            )
            rows = conn.execute(
                """
                SELECT qs.id, qs.questionnaire_id, '' AS respondent_key,
                       COALESCE(identity.primary_openid, '') AS openid,
                       qs.unionid,
                       COALESCE(identity.primary_external_userid, '') AS external_userid,
                       qs.follow_user_userid, qs.matched_by,
                       COALESCE(identity.mobile, '') AS mobile_snapshot,
                       qs.source_channel, qs.campaign_id,
                       qs.staff_id, qs.total_score, qs.final_tags, qs.result_token, qs.redirect_url_snapshot,
                       qs.submitted_at
                FROM questionnaire_submissions qs
                LEFT JOIN crm_user_identity identity ON identity.unionid = qs.unionid
                WHERE qs.questionnaire_id = %s
                ORDER BY qs.submitted_at DESC, qs.id DESC
                LIMIT %s OFFSET %s
                """,
                (int(questionnaire_id), int(limit), int(offset)),
            ).fetchall()
            row_ids = [int(row["id"]) for row in rows]
            answer_rows = []
            if row_ids:
                answer_rows = conn.execute(
                    """
                    SELECT submission_id, question_id, question_type, question_title_snapshot,
                           selected_option_ids, selected_option_texts_snapshot, text_value
                    FROM questionnaire_submission_answers
                    WHERE submission_id = ANY(%s)
                    ORDER BY submission_id ASC, id ASC
                    """,
                    (row_ids,),
                ).fetchall()
        answers_by_submission: dict[int, dict[str, Any]] = {}
        answer_snapshots_by_submission: dict[int, list[dict[str, Any]]] = {}
        for answer in answer_rows:
            submission_id = int(answer.get("submission_id") or 0)
            answer_payload = dict(answer)
            answer_snapshots_by_submission.setdefault(submission_id, []).append(answer_payload)
            key = str(answer_payload.get("question_id"))
            answers = answers_by_submission.setdefault(submission_id, {})
            if answer_payload.get("question_type") in {"textarea", "mobile"}:
                answers[key] = _text(answer_payload.get("text_value"))
                continue
            selected = _json_list(answer_payload.get("selected_option_ids"))
            other_text = _text(answer_payload.get("text_value")).strip()
            if other_text:
                answers[key] = {"selected_option_ids": selected, "other_text": other_text}
            else:
                answers[key] = selected[0] if len(selected) == 1 else selected
        items = [
            {
                **dict(row),
                "submission_id": str(row.get("id")),
                "submitted_at": _timestamp(row.get("submitted_at")),
                "final_tags": _json_list(row.get("final_tags")),
                "score": float(row.get("total_score") or 0),
                "mobile": _text(row.get("mobile_snapshot")),
                "answers": answers_by_submission.get(int(row.get("id") or 0), {}),
                "answer_snapshots": answer_snapshots_by_submission.get(int(row.get("id") or 0), []),
            }
            for row in rows
        ]
        return items, total

    def list_external_submissions(
        self,
        *,
        filters: dict[str, Any],
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        clauses = ["1 = 1"]
        params: list[Any] = []
        if _text(filters.get("mobile")).strip():
            clauses.append("(identity.mobile = %s OR identity.mobile_normalized = %s)")
            mobile = _text(filters.get("mobile")).strip()
            params.extend([mobile, mobile])
        if _text(filters.get("unionid")).strip():
            clauses.append("qs.unionid = %s")
            params.append(_text(filters.get("unionid")).strip())
        if _text(filters.get("external_userid")).strip():
            clauses.append("(identity.primary_external_userid = %s OR jsonb_exists(identity.external_userids_json, %s))")
            external_userid = _text(filters.get("external_userid")).strip()
            params.extend([external_userid, external_userid])
        if filters.get("questionnaire_id") not in (None, ""):
            clauses.append("qs.questionnaire_id = %s")
            params.append(int(filters.get("questionnaire_id") or 0))
        if _text(filters.get("submitted_from")).strip():
            clauses.append("qs.submitted_at >= %s")
            params.append(_text(filters.get("submitted_from")).strip())
        if _text(filters.get("submitted_to")).strip():
            clauses.append("qs.submitted_at <= %s")
            params.append(_text(filters.get("submitted_to")).strip())

        where_sql = " AND ".join(clauses)
        with self._connect() as conn:
            total = int(
                (
                    conn.execute(
                        f"""
                        SELECT COUNT(*) AS total
                        FROM questionnaire_submissions qs
                        LEFT JOIN crm_user_identity identity ON identity.unionid = qs.unionid
                        WHERE {where_sql}
                        """,
                        tuple(params),
                    ).fetchone()
                    or {}
                ).get("total")
                or 0
            )
            rows = conn.execute(
                f"""
                SELECT
                    qs.id,
                    qs.questionnaire_id,
                    qs.unionid,
                    COALESCE(identity.primary_external_userid, '') AS external_userid,
                    COALESCE(identity.mobile, '') AS mobile_snapshot,
                    qs.submitted_at,
                    qs.final_tags,
                    qs.assessment_result_snapshot,
                    COALESCE(NULLIF(q.title, ''), NULLIF(q.name, ''), '') AS questionnaire_title
                FROM questionnaire_submissions qs
                LEFT JOIN crm_user_identity identity ON identity.unionid = qs.unionid
                LEFT JOIN questionnaires q ON q.id = qs.questionnaire_id
                WHERE {where_sql}
                ORDER BY qs.submitted_at DESC, qs.id DESC
                LIMIT %s OFFSET %s
                """,
                tuple(params + [int(limit), int(offset)]),
            ).fetchall()
            row_ids = [int(row["id"]) for row in rows]
            answer_rows = []
            if row_ids:
                answer_rows = conn.execute(
                    """
                    SELECT submission_id, question_title_snapshot, selected_option_texts_snapshot,
                           text_value, score_contribution
                    FROM questionnaire_submission_answers
                    WHERE submission_id = ANY(%s)
                    ORDER BY submission_id ASC, id ASC
                    """,
                    (row_ids,),
                ).fetchall()

        answers_by_submission: dict[int, list[dict[str, Any]]] = {}
        for answer in answer_rows:
            answers_by_submission.setdefault(int(answer.get("submission_id") or 0), []).append(dict(answer))
        items = [
            _external_submission_projection(dict(row), answers_by_submission.get(int(row.get("id") or 0), []))
            for row in rows
        ]
        return items, total

    def _exists(self, questionnaire_id: int) -> bool:
        with self._connect() as conn:
            return bool(conn.execute("SELECT 1 FROM questionnaires WHERE id = %s", (int(questionnaire_id),)).fetchone())

    def _list_score_rules(self, questionnaire_id: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, questionnaire_id, min_score, max_score, tag_codes, sort_order, created_at, updated_at
                FROM questionnaire_score_rules
                WHERE questionnaire_id = %s
                ORDER BY sort_order ASC, id ASC
                """,
                (int(questionnaire_id),),
            ).fetchall()
        return [
            {
                **dict(row),
                "tag_codes": _json_list(row.get("tag_codes")),
                "created_at": _timestamp(row.get("created_at")),
                "updated_at": _timestamp(row.get("updated_at")),
            }
            for row in rows
        ]

    def save_questionnaire(self, payload: dict[str, Any], questionnaire_id: int | None = None) -> dict[str, Any]:
        with self._connect() as conn:
            with conn.transaction():
                existing = None
                if questionnaire_id is not None:
                    existing = conn.execute(
                        "SELECT id, slug, name, title FROM questionnaires WHERE id = %s FOR UPDATE",
                        (int(questionnaire_id),),
                    ).fetchone()
                    if not existing:
                        return {}
                requested_slug = _text(payload.get("slug")).strip()
                slug_source = requested_slug or _text((existing or {}).get("slug")) or _text(payload.get("name")) or _text(payload.get("title"))
                slug = _slugify_questionnaire(slug_source)
                if self._slug_exists(conn, slug, exclude_id=int(questionnaire_id) if questionnaire_id is not None else None):
                    if requested_slug:
                        raise RepositoryProviderError("slug already exists")
                    slug = self._dedupe_slug(conn, slug_source, exclude_id=int(questionnaire_id) if questionnaire_id is not None else None)
                normalized = _questionnaire_payload(payload, slug=slug)
                if not normalized["name"]:
                    raise RepositoryProviderError("name is required")
                if not normalized["title"]:
                    raise RepositoryProviderError("title is required")
                external_push = normalized["external_push"]

                if questionnaire_id is None:
                    row = conn.execute(
                        """
                        INSERT INTO questionnaires (
                            slug, name, title, description, is_disabled, redirect_url, completion_target_json,
                            answer_display_mode, assessment_enabled, assessment_config,
                            external_push_enabled, external_push_url, external_push_type, external_push_expires_at_ts,
                            external_push_day, external_push_frequency, external_push_remark, external_push_custom_params,
                            created_at, updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                        RETURNING id
                        """,
                        (
                            normalized["slug"],
                            normalized["name"],
                            normalized["title"],
                            normalized["description"],
                            normalized["is_disabled"],
                            normalized["redirect_url"],
                            _jsonb(normalized["completion_target_json"]),
                            normalized["answer_display_mode"],
                            normalized["assessment_enabled"],
                            _jsonb(normalized["assessment_config"]),
                            external_push["enabled"],
                            external_push["url"],
                            external_push["type"],
                            external_push["expires_at_ts"],
                            external_push["day"],
                            external_push["frequency"],
                            external_push["remark"],
                            _jsonb(external_push["custom_params"]),
                        ),
                    ).fetchone()
                    questionnaire_id = int(row["id"])
                else:
                    conn.execute(
                        """
                        UPDATE questionnaires
                        SET slug = %s, name = %s, title = %s, description = %s, is_disabled = %s,
                            redirect_url = %s, completion_target_json = %s, answer_display_mode = %s, assessment_enabled = %s,
                            assessment_config = %s, external_push_enabled = %s, external_push_url = %s,
                            external_push_type = %s, external_push_expires_at_ts = %s, external_push_day = %s,
                            external_push_frequency = %s, external_push_remark = %s,
                            external_push_custom_params = %s, updated_at = NOW()
                        WHERE id = %s
                        """,
                        (
                            normalized["slug"],
                            normalized["name"],
                            normalized["title"],
                            normalized["description"],
                            normalized["is_disabled"],
                            normalized["redirect_url"],
                            _jsonb(normalized["completion_target_json"]),
                            normalized["answer_display_mode"],
                            normalized["assessment_enabled"],
                            _jsonb(normalized["assessment_config"]),
                            external_push["enabled"],
                            external_push["url"],
                            external_push["type"],
                            external_push["expires_at_ts"],
                            external_push["day"],
                            external_push["frequency"],
                            external_push["remark"],
                            _jsonb(external_push["custom_params"]),
                            int(questionnaire_id),
                        ),
                    )
                self._sync_questions(conn, int(questionnaire_id), _json_list(payload.get("questions")))
                self._sync_score_rules(conn, int(questionnaire_id), _json_list(payload.get("score_rules") or payload.get("rules")))
        item = self.get_questionnaire(int(questionnaire_id))
        if not item:
            raise RepositoryProviderError("questionnaire write failed")
        return item

    def set_enabled(self, questionnaire_id: int, enabled: bool) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.transaction():
                row = conn.execute(
                    """
                    UPDATE questionnaires
                    SET is_disabled = %s, updated_at = NOW()
                    WHERE id = %s
                    RETURNING id
                    """,
                    (not bool(enabled), int(questionnaire_id)),
                ).fetchone()
        if not row:
            return None
        return self.get_questionnaire(int(questionnaire_id))

    def delete_questionnaire(self, questionnaire_id: int) -> bool:
        with self._connect() as conn:
            with conn.transaction():
                row = conn.execute(
                    """
                    DELETE FROM questionnaires
                    WHERE id = %s
                    RETURNING id
                    """,
                    (int(questionnaire_id),),
                ).fetchone()
        return bool(row)

    def _slug_exists(self, conn: Any, slug: str, *, exclude_id: int | None = None) -> bool:
        params: list[Any] = [slug]
        sql = "SELECT 1 FROM questionnaires WHERE slug = %s"
        if exclude_id is not None:
            sql += " AND id <> %s"
            params.append(int(exclude_id))
        return bool(conn.execute(sql, tuple(params)).fetchone())

    def _dedupe_slug(self, conn: Any, slug_source: str, *, exclude_id: int | None = None) -> str:
        candidate = _slugify_questionnaire(slug_source)
        if not self._slug_exists(conn, candidate, exclude_id=exclude_id):
            return candidate
        while True:
            suffix = uuid4().hex[:6]
            prefix = candidate[: max(120 - len(suffix) - 1, 1)].rstrip("-")
            fallback_prefix = datetime.now(timezone.utc).strftime("q-%Y%m%d%H%M%S")
            deduped = f"{prefix or fallback_prefix}-{suffix}"[:120]
            if not self._slug_exists(conn, deduped, exclude_id=exclude_id):
                return deduped

    def _sync_questions(self, conn: Any, questionnaire_id: int, questions: list[Any]) -> None:
        conn.execute("DELETE FROM questionnaire_questions WHERE questionnaire_id = %s", (int(questionnaire_id),))
        for index, raw_question in enumerate(questions, start=1):
            question = dict(raw_question or {})
            question_type = _text(question.get("type") or "single_choice")
            title = _text(question.get("title"))
            if not title:
                raise RepositoryProviderError("question title is required")
            row = conn.execute(
                """
                INSERT INTO questionnaire_questions (
                    questionnaire_id, type, title, placeholder_text, assessment_dimension_key,
                    sidebar_profile_field, required, sort_order, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                RETURNING id
                """,
                (
                    int(questionnaire_id),
                    question_type,
                    title,
                    _text(question.get("placeholder_text")),
                    _text(question.get("assessment_dimension_key")),
                    _text(question.get("sidebar_profile_field")),
                    _as_bool(question.get("required")),
                    int(question.get("sort_order") or index),
                ),
            ).fetchone()
            question_id = int(row["id"])
            if question_type not in {"textarea", "mobile"}:
                self._insert_options(conn, question_id, _json_list(question.get("options")))

    def _insert_options(self, conn: Any, question_id: int, options: list[Any]) -> None:
        for index, raw_option in enumerate(options, start=1):
            option = dict(raw_option or {})
            option_text = _text(option.get("option_text") or option.get("label") or option.get("value"))
            if not option_text:
                raise RepositoryProviderError("option_text is required")
            conn.execute(
                """
                INSERT INTO questionnaire_options (
                    question_id, option_text, score, assessment_type_key, tag_codes,
                    is_other, other_placeholder, other_max_length, sort_order, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                """,
                (
                    int(question_id),
                    option_text,
                    float(option.get("score") or 0),
                    _text(option.get("assessment_type_key")),
                    _jsonb(_json_list(option.get("tag_codes"))),
                    _as_bool(option.get("is_other")),
                    _text(option.get("other_placeholder")),
                    int(option.get("other_max_length") or 80),
                    int(option.get("sort_order") or index),
                ),
            )

    def _sync_score_rules(self, conn: Any, questionnaire_id: int, score_rules: list[Any]) -> None:
        conn.execute("DELETE FROM questionnaire_score_rules WHERE questionnaire_id = %s", (int(questionnaire_id),))
        for index, raw_rule in enumerate(score_rules, start=1):
            rule = dict(raw_rule or {})
            conn.execute(
                """
                INSERT INTO questionnaire_score_rules (
                    questionnaire_id, min_score, max_score, tag_codes, sort_order, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                """,
                (
                    int(questionnaire_id),
                    _optional_float(rule.get("min_score")),
                    _optional_float(rule.get("max_score")),
                    _jsonb(_json_list(rule.get("tag_codes"))),
                    int(rule.get("sort_order") or index),
                ),
            )

    def create_submission(self, payload: dict[str, Any]) -> dict[str, Any]:
        questionnaire_id = int(payload.get("questionnaire_id") or 0)
        if not questionnaire_id:
            raise RepositoryProviderError("questionnaire_id is required for questionnaire submit")
        answers = _json_dict(payload.get("answers") or payload.get("answers_json"))
        questions = self.list_questions(questionnaire_id) or []
        answer_snapshots = _answer_snapshots(questions, answers)
        source = _json_dict(payload.get("source_json"))
        respondent_identity = _json_dict(payload.get("respondent_identity"))
        mobile_snapshot = _text(payload.get("mobile") or respondent_identity.get("mobile") or _mobile_answer(questions, answers)).strip()
        final_tags = _json_list(payload.get("final_tags"))
        score = float(payload.get("score") or (payload.get("result_json") or {}).get("score") or 0)
        assessment_result = _json_dict((payload.get("result_json") or {}).get("assessment_result"))
        redirect_url = _text(payload.get("redirect_url") or "")
        unionid = _text(payload.get("unionid") or respondent_identity.get("unionid"))
        if not unionid:
            self._enqueue_identity_resolution(
                {
                    "source_type": "questionnaire_submission",
                    "questionnaire_id": questionnaire_id,
                    "respondent_key": _text(payload.get("respondent_key") or respondent_identity.get("respondent_key")),
                    "openid": _text(payload.get("openid") or respondent_identity.get("openid")),
                    "external_userid": _text(payload.get("external_userid") or respondent_identity.get("external_userid")),
                    "mobile": mobile_snapshot,
                    "slug": _text(payload.get("slug")),
                },
                reason="missing_unionid",
            )
            raise RepositoryProviderError("identity_pending_unionid")

        with self._connect() as conn:
            with conn.transaction():
                row = conn.execute(
                    """
                    INSERT INTO questionnaire_submissions (
                        questionnaire_id, unionid, follow_user_userid, matched_by, source_channel, campaign_id,
                        staff_id, total_score, final_tags, assessment_result_snapshot, result_token,
                        redirect_url_snapshot, submitted_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    RETURNING id, submitted_at
                    """,
                    (
                        questionnaire_id,
                        unionid,
                        _text(payload.get("follow_user_userid")),
                        _text(payload.get("matched_by")),
                        _text(source.get("source_channel")),
                        _text(source.get("campaign_id")),
                        _text(source.get("staff_id")),
                        score,
                        _jsonb(final_tags),
                        _jsonb(assessment_result),
                        _text(payload.get("result_token")),
                        redirect_url,
                    ),
                ).fetchone()
                submission_id = int(row["id"])
                for item in answer_snapshots:
                    conn.execute(
                        """
                        INSERT INTO questionnaire_submission_answers (
                            submission_id, question_id, question_type, question_title_snapshot,
                            selected_option_ids, selected_option_texts_snapshot, selected_option_scores_snapshot,
                            selected_option_tags_snapshot, text_value, score_contribution, created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        """,
                        (
                            submission_id,
                            int(item["question_id"]),
                            item["question_type"],
                            item["question_title_snapshot"],
                            _jsonb(item.get("selected_option_ids") or []),
                            _jsonb(item.get("selected_option_texts_snapshot") or []),
                            _jsonb(item.get("selected_option_scores_snapshot") or []),
                            _jsonb(item.get("selected_option_tags_snapshot") or []),
                            item.get("text_value", "") or "",
                            float(item.get("score_contribution") or 0),
                        ),
                    )
        submitted_at = _timestamp(row.get("submitted_at"))
        return {
            "id": submission_id,
            "submission_id": str(submission_id),
            "result_token": _text(payload.get("result_token")),
            "questionnaire_id": questionnaire_id,
            "slug": _text(payload.get("slug")),
            "answers": answers,
            "answers_json": answers,
            "result_json": _json_dict(payload.get("result_json")),
            "source_json": source,
            "diagnostics_json": _json_dict(payload.get("diagnostics_json")),
            "respondent_identity": respondent_identity,
            "person_id": payload.get("person_id"),
            "identity_map_id": payload.get("identity_map_id"),
            "external_userid": _text(payload.get("external_userid") or respondent_identity.get("external_userid")),
            "follow_user_userid": _text(payload.get("follow_user_userid")),
            "matched_by": _text(payload.get("matched_by")),
            "openid": _text(payload.get("openid") or respondent_identity.get("openid")),
            "unionid": unionid,
            "mobile": mobile_snapshot,
            "mobile_snapshot": mobile_snapshot,
            "source_channel": _text(source.get("source_channel")),
            "campaign_id": _text(source.get("campaign_id")),
            "staff_id": _text(source.get("staff_id")),
            "binding_status": _text(payload.get("binding_status") or "unresolved"),
            "score": score,
            "total_score": score,
            "final_tags": final_tags,
            "status": _text(payload.get("status") or "submitted"),
            "created_at": submitted_at,
            "submitted_at": submitted_at,
            "updated_at": _text(payload.get("updated_at") or submitted_at),
            "answer_snapshots": answer_snapshots,
        }

    def _enqueue_identity_resolution(self, payload: dict[str, Any], *, reason: str) -> None:
        source_key = (
            _text(payload.get("respondent_key"))
            or _text(payload.get("openid"))
            or _text(payload.get("external_userid"))
            or _text(payload.get("mobile"))
            or f"questionnaire:{int(payload.get('questionnaire_id') or 0)}"
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO crm_user_identity_resolution_queue (
                    source_type,
                    source_key,
                    external_userid,
                    openid,
                    mobile,
                    payload_json,
                    reason,
                    status,
                    first_seen_at,
                    last_seen_at,
                    created_at,
                    updated_at
                ) VALUES (
                    'questionnaire_submission',
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    'pending',
                    NOW(),
                    NOW(),
                    NOW(),
                    NOW()
                )
                ON CONFLICT (source_type, source_key) WHERE status = 'pending' AND source_type <> '' AND source_key <> ''
                DO UPDATE SET
                    external_userid = COALESCE(NULLIF(EXCLUDED.external_userid, ''), crm_user_identity_resolution_queue.external_userid),
                    openid = COALESCE(NULLIF(EXCLUDED.openid, ''), crm_user_identity_resolution_queue.openid),
                    mobile = COALESCE(NULLIF(EXCLUDED.mobile, ''), crm_user_identity_resolution_queue.mobile),
                    payload_json = crm_user_identity_resolution_queue.payload_json || EXCLUDED.payload_json,
                    reason = EXCLUDED.reason,
                    last_seen_at = NOW(),
                    updated_at = NOW()
                """,
                (
                    source_key,
                    _text(payload.get("external_userid")),
                    _text(payload.get("openid")),
                    _text(payload.get("mobile")),
                    _jsonb(payload),
                    _text(reason) or "identity_unresolved",
                ),
            )
            conn.commit()

    def get_submission(self, submission_id: str) -> dict[str, Any] | None:
        normalized_id = str(submission_id or "").strip()
        if not normalized_id:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT qs.*, q.slug
                FROM questionnaire_submissions qs
                JOIN questionnaires q ON q.id = qs.questionnaire_id
                WHERE qs.result_token = %s LIMIT 1
                """,
                (normalized_id,),
            ).fetchone()
            if not row:
                return None
            answer_rows = conn.execute(
                """
                SELECT question_id, question_type, question_title_snapshot,
                       selected_option_ids, selected_option_texts_snapshot, text_value
                FROM questionnaire_submission_answers
                WHERE submission_id = %s
                ORDER BY id ASC
                """,
                (int(row["id"]),),
            ).fetchall()
        answers: dict[str, Any] = {}
        answer_snapshots: list[dict[str, Any]] = []
        for answer in answer_rows:
            answer_payload = dict(answer)
            answer_snapshots.append(answer_payload)
            key = str(answer_payload.get("question_id"))
            if answer_payload.get("question_type") in {"textarea", "mobile"}:
                answers[key] = _text(answer_payload.get("text_value"))
            else:
                selected = _json_list(answer_payload.get("selected_option_ids"))
                other_text = _text(answer_payload.get("text_value")).strip()
                if other_text:
                    answers[key] = {"selected_option_ids": selected, "other_text": other_text}
                else:
                    answers[key] = selected[0] if len(selected) == 1 else selected
        return {
            **dict(row),
            "submission_id": str(row.get("id")),
            "slug": _text(row.get("slug")),
            "answers": answers,
            "score": float(row.get("total_score") or 0),
            "final_tags": _json_list(row.get("final_tags")),
            "mobile": _text(row.get("mobile_snapshot")),
            "created_at": _timestamp(row.get("submitted_at")),
            "submitted_at": _timestamp(row.get("submitted_at")),
            "answer_snapshots": answer_snapshots,
        }

    def find_submission_for_identity(self, questionnaire_id: int, identity: dict[str, Any]) -> dict[str, Any] | None:
        candidates = _identity_lookup_values(identity)
        if not candidates:
            return None
        clauses: list[str] = []
        params: list[Any] = [int(questionnaire_id)]
        for field, value in candidates:
            if field == "unionid":
                clauses.append("qs.unionid = %s")
                params.append(value)
            elif field == "mobile":
                clauses.append("(identity.mobile = %s OR identity.mobile_normalized = %s)")
                params.extend([value, value])
            elif field == "external_userid":
                clauses.append("(identity.primary_external_userid = %s OR jsonb_exists(identity.external_userids_json, %s))")
                params.extend([value, value])
            elif field == "openid":
                clauses.append("(identity.primary_openid = %s OR jsonb_exists(identity.openids_json, %s))")
                params.extend([value, value])
            elif field == "respondent_key":
                continue
        if not clauses:
            return None
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT qs.id, qs.questionnaire_id, '' AS respondent_key,
                       COALESCE(identity.primary_openid, '') AS openid,
                       qs.unionid,
                       COALESCE(identity.primary_external_userid, '') AS external_userid,
                       COALESCE(identity.mobile, '') AS mobile_snapshot,
                       qs.total_score, qs.final_tags, qs.result_token, qs.redirect_url_snapshot,
                       qs.submitted_at
                FROM questionnaire_submissions qs
                LEFT JOIN crm_user_identity identity ON identity.unionid = qs.unionid
                WHERE qs.questionnaire_id = %s AND ({" OR ".join(clauses)})
                ORDER BY qs.submitted_at DESC, qs.id DESC
                LIMIT 1
                """,
                tuple(params),
            ).fetchone()
        if not row:
            return None
        return {
            **dict(row),
            "submission_id": str(row.get("id")),
            "mobile": _text(row.get("mobile_snapshot")),
            "score": float(row.get("total_score") or 0),
            "final_tags": _json_list(row.get("final_tags")),
            "submitted_at": _timestamp(row.get("submitted_at")),
        }

    def latest_submission(self, questionnaire_id: int) -> dict[str, Any] | None:
        submissions = self.list_submissions(questionnaire_id, limit=1, offset=0)
        if not submissions or not submissions[0]:
            return None
        return submissions[0][0]

    def export_submissions(self, questionnaire_id: int) -> dict[str, Any] | None:
        raise RepositoryProviderError("questionnaire export remains out of scope for the admin read replacement")

    def get_app_setting(self, key: str) -> str | None:
        return runtime_setting(key, "") or None

    def create_external_push_log(self, **kwargs: Any) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO questionnaire_external_push_logs (
                    questionnaire_id, questionnaire_title_snapshot, submission_record_id, retry_from_log_id,
                    retry_attempt, user_id, target_url, request_payload, response_status_code, response_body,
                    status, failure_reason, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                RETURNING id, questionnaire_id, questionnaire_title_snapshot, submission_record_id,
                          retry_from_log_id, retry_attempt, user_id, target_url, request_payload,
                          response_status_code, response_body, status, failure_reason, created_at, updated_at
                """,
                (
                    int(kwargs["questionnaire_id"]),
                    _text(kwargs.get("questionnaire_title_snapshot")),
                    int(kwargs["submission_record_id"]),
                    int(kwargs["retry_from_log_id"]) if kwargs.get("retry_from_log_id") else None,
                    max(0, int(kwargs.get("retry_attempt") or 0)),
                    _text(kwargs.get("user_id")),
                    _text(kwargs.get("target_url")),
                    _jsonb(_json_dict(kwargs.get("request_payload"))),
                    kwargs.get("response_status_code"),
                    _text(kwargs.get("response_body")),
                    _text(kwargs.get("status")),
                    _text(kwargs.get("failure_reason")),
                ),
            ).fetchone()
            conn.commit()
        return dict(row)

    def list_external_push_log_threads(
        self,
        questionnaire_id: int | None = None,
        *,
        questionnaire_title: str = "",
        user_id: str = "",
        target_url: str = "",
        status: str = "",
        limit: int | None = 50,
    ) -> list[dict[str, Any]]:
        sql = """
            SELECT id, questionnaire_id, questionnaire_title_snapshot, submission_record_id,
                   retry_from_log_id, retry_attempt, user_id, target_url, request_payload,
                   response_status_code, response_body, status, failure_reason, created_at, updated_at
            FROM questionnaire_external_push_logs
            WHERE 1 = 1
        """
        params: list[Any] = []
        if questionnaire_id is not None:
            sql += " AND questionnaire_id = %s"
            params.append(int(questionnaire_id))
        if _text(questionnaire_title).strip():
            sql += " AND questionnaire_title_snapshot ILIKE %s"
            params.append(f"%{_text(questionnaire_title).strip()}%")
        if _text(user_id).strip():
            sql += " AND user_id ILIKE %s"
            params.append(f"%{_text(user_id).strip()}%")
        if _text(target_url).strip():
            sql += " AND target_url ILIKE %s"
            params.append(f"%{_text(target_url).strip()}%")
        sql += " ORDER BY created_at DESC, id DESC"
        with self._connect() as conn:
            rows = [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]
        return _external_push_log_threads(rows, status=status, limit=limit)

    def count_external_push_logs(
        self,
        *,
        questionnaire_id: int | None = None,
        questionnaire_title: str = "",
        user_id: str = "",
        target_url: str = "",
        status: str = "",
        created_at_gte: str = "",
    ) -> int:
        sql = "SELECT COUNT(*) AS total FROM questionnaire_external_push_logs WHERE 1 = 1"
        params: list[Any] = []
        if questionnaire_id is not None:
            sql += " AND questionnaire_id = %s"
            params.append(int(questionnaire_id))
        if _text(questionnaire_title).strip():
            sql += " AND questionnaire_title_snapshot ILIKE %s"
            params.append(f"%{_text(questionnaire_title).strip()}%")
        if _text(user_id).strip():
            sql += " AND user_id ILIKE %s"
            params.append(f"%{_text(user_id).strip()}%")
        if _text(target_url).strip():
            sql += " AND target_url ILIKE %s"
            params.append(f"%{_text(target_url).strip()}%")
        if _text(status).strip():
            sql += " AND status = %s"
            params.append(_text(status).strip())
        if _text(created_at_gte).strip():
            sql += " AND created_at >= %s"
            params.append(_text(created_at_gte).strip())
        with self._connect() as conn:
            row = conn.execute(sql, tuple(params)).fetchone() or {}
        return int(row.get("total") or 0)

    def summarize_external_push_logs(self, questionnaire_id: int) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total_count,
                       SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_count,
                       SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count,
                       MAX(created_at) AS last_created_at
                FROM questionnaire_external_push_logs
                WHERE questionnaire_id = %s
                """,
                (int(questionnaire_id),),
            ).fetchone() or {}
        return {
            "total_count": int(row.get("total_count") or 0),
            "success_count": int(row.get("success_count") or 0),
            "failed_count": int(row.get("failed_count") or 0),
            "last_created_at": _timestamp(row.get("last_created_at")),
        }

    def get_external_push_log(self, log_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, questionnaire_id, questionnaire_title_snapshot, submission_record_id,
                       retry_from_log_id, retry_attempt, user_id, target_url, request_payload,
                       response_status_code, response_body, status, failure_reason, created_at, updated_at
                FROM questionnaire_external_push_logs
                WHERE id = %s
                LIMIT 1
                """,
                (int(log_id),),
            ).fetchone()
        return _normalized_external_push_log(dict(row)) if row else None

    def count_external_push_retry_logs(self, root_log_id: int) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total FROM questionnaire_external_push_logs WHERE retry_from_log_id = %s",
                (int(root_log_id),),
            ).fetchone() or {}
        return int(row.get("total") or 0)


_DEFAULT_REPO = InMemoryQuestionnaireRepository()


def build_questionnaire_repository() -> QuestionnaireRepository:
    if production_data_ready():
        return assert_repository_allowed(PostgresQuestionnaireReadRepository(), capability_owner="questionnaire")
    return assert_repository_allowed(_DEFAULT_REPO, capability_owner="questionnaire")


def reset_questionnaire_fixture_state() -> None:
    _DEFAULT_REPO.reset()
