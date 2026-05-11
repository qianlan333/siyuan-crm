"""问卷探索 service — 给 Agent 自助"读问卷 → 选维度 → 出 SQL"的工具集。

设计原则（核心架构）：
- **不写一次性脚本**。每次新需求都通过同一组接口完成。
- **AI 在外部组合调用**：先 list 找到目标问卷，再 inspect 看题目结构，再
  query 验证人数，最后 compose 出 SQL 给 propose_segment。
- **稳定的 read-only 接口**，永远幂等、永远可重入。

典型对话流（在 Claude Code 里，运营说"按问卷答案分层"）：
    1. list_questionnaires(keyword=...) — 找目标问卷
    2. inspect_questionnaire(questionnaire_id=N) — 看题目 + 选项 + 命中分布
    3. preview_questionnaire_population(filters=[...]) — 验证某几个选项组合的命中人数
    4. compose_segment_sql_from_questionnaire(filters=[...], extras=...) — 拼 SQL
    5. propose_segment(sql_query=<上一步的 SQL>, ...) — 落地命名分层
"""
from __future__ import annotations

import json
import logging
from typing import Any, Iterable

from ...db import get_db


logger = logging.getLogger(__name__)


def _conn():
    return get_db()


# ---------- 1. 列问卷 ------------------------------------------------------

def list_questionnaires(
    *,
    keyword: str = "",
    only_with_submissions: bool = True,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """列出问卷 + 提交数。Agent 用来定位目标问卷。

    Returns:
        [{
          "questionnaire_id": int,
          "title": str,
          "status": str,
          "submission_count": int,
          "last_submitted_at": str,
        }]
    """
    db = _conn()
    cur = db.cursor()
    where = ["1=1"]
    args: list[Any] = []
    kw = (keyword or "").strip()
    if kw:
        where.append("q.title LIKE ?")
        args.append(f"%{kw}%")
    args.append(int(limit))
    # PG 上 submitted_at 是 TIMESTAMPTZ，SQLite 是 TEXT —— 用 CAST AS TEXT 跨库通用
    # 先 CAST 再 COALESCE，避免 timestamp 和 '' 类型不匹配
    cur.execute(
        f"""
        SELECT q.id AS questionnaire_id,
               q.title,
               q.is_disabled,
               COALESCE(s.submission_count, 0) AS submission_count,
               COALESCE(CAST(s.last_submitted_at AS TEXT), '') AS last_submitted_at
        FROM questionnaires q
        LEFT JOIN (
            SELECT questionnaire_id,
                   COUNT(*) AS submission_count,
                   MAX(submitted_at) AS last_submitted_at
            FROM questionnaire_submissions
            GROUP BY questionnaire_id
        ) s ON s.questionnaire_id = q.id
        WHERE {' AND '.join(where)}
        ORDER BY COALESCE(s.submission_count, 0) DESC, q.id DESC
        LIMIT ?
        """,
        tuple(args),
    )
    rows = [dict(r) for r in (cur.fetchall() or [])]
    if only_with_submissions:
        rows = [r for r in rows if int(r.get("submission_count") or 0) > 0]
    return rows


# ---------- 2. 看问卷结构 + 选项分布 ---------------------------------------

def inspect_questionnaire(
    *,
    questionnaire_id: int = 0,
    title_keyword: str = "",
) -> dict[str, Any]:
    """单个问卷的题目树 + 每题每选项的命中人数。

    Args:
        questionnaire_id: 直接给 id
        title_keyword: 模糊匹配标题（取第一个匹配的）

    Returns:
        {
          "questionnaire": {"id": int, "title": str, "submission_count": int},
          "questions": [
            {
              "question_id": int,
              "title": str,
              "type": str,
              "options": [
                {"option_id": int, "text": str, "selected_count": int}
              ]
            }
          ]
        }
    """
    db = _conn()
    cur = db.cursor()
    qid = int(questionnaire_id or 0)
    if not qid and title_keyword:
        cur.execute(
            "SELECT id FROM questionnaires WHERE title LIKE ? ORDER BY id DESC LIMIT 1",
            (f"%{title_keyword}%",),
        )
        row = cur.fetchone()
        if row:
            qid = int(row["id"])
    if not qid:
        raise ValueError("questionnaire_id or title_keyword required")

    cur.execute(
        "SELECT id, title, is_disabled FROM questionnaires WHERE id = ?",
        (qid,),
    )
    qn_row = cur.fetchone()
    if not qn_row:
        raise LookupError(f"questionnaire not found id={qid}")
    qn = dict(qn_row)

    cur.execute(
        "SELECT COUNT(*) AS c FROM questionnaire_submissions WHERE questionnaire_id = ?",
        (qid,),
    )
    submission_count = int((cur.fetchone() or {}).get("c") or 0)

    cur.execute(
        """
        SELECT id AS question_id, title, type, sort_order
        FROM questionnaire_questions
        WHERE questionnaire_id = ?
        ORDER BY sort_order ASC, id ASC
        """,
        (qid,),
    )
    questions = [dict(r) for r in (cur.fetchall() or [])]

    for q in questions:
        question_id = int(q["question_id"])
        cur.execute(
            """
            SELECT id AS option_id, option_text AS text, sort_order
            FROM questionnaire_options
            WHERE question_id = ?
            ORDER BY sort_order ASC, id ASC
            """,
            (question_id,),
        )
        options = [dict(r) for r in (cur.fetchall() or [])]
        # 算每个选项被选过几次（基于 selected_option_ids 字段，是 JSON 数组）
        cur.execute(
            """
            SELECT selected_option_ids
            FROM questionnaire_submission_answers
            WHERE question_id = ?
            """,
            (question_id,),
        )
        ans_rows = cur.fetchall() or []
        counts: dict[int, int] = {}
        for ar in ans_rows:
            raw = ar["selected_option_ids"]
            # PG JSONB 字段 psycopg3 自动反序列化成 Python list；SQLite 是 TEXT
            if isinstance(raw, list):
                ids = raw
            elif isinstance(raw, str):
                try:
                    ids = json.loads(raw or "[]")
                except (TypeError, ValueError):
                    ids = []
            else:
                ids = []
            for oid in ids:
                try:
                    oid_int = int(oid)
                    counts[oid_int] = counts.get(oid_int, 0) + 1
                except (TypeError, ValueError):
                    continue
        for opt in options:
            opt["selected_count"] = int(counts.get(int(opt["option_id"]), 0))
        q["options"] = options
        q.pop("sort_order", None)

    return {
        "questionnaire": {
            "id": qn["id"],
            "title": qn["title"],
            "is_disabled": int(qn.get("is_disabled") or 0),
            "submission_count": submission_count,
        },
        "questions": questions,
    }


# ---------- 3. 验证：某组条件命中多少人 ------------------------------------

def preview_questionnaire_population(
    *,
    filters: list[dict[str, Any]],
    audience_code: str = "operating",
    limit: int = 50,
) -> dict[str, Any]:
    """一组 question/option filter 的"AND"交集 — 这群人到底是谁、多少。

    Args:
        filters: [{"question_id": int, "option_ids": [int,...] OR
                  "option_text_keywords": ["100万", "50万"]}]
                每条 filter 内是 OR 关系；filter 之间是 AND。
        audience_code: 默认 'operating'，限制只看运营中的；空字符串=不限
        limit: 样本最多返回多少条 external_userid

    Returns:
        {
          "headcount": int,
          "sample_external_userids": [...],
          "filters_resolved": [{question_title, option_texts_in_use}, ...]
        }
    """
    if not filters:
        raise ValueError("filters is required")

    db = _conn()
    cur = db.cursor()
    filters_resolved: list[dict[str, Any]] = []
    where_parts = []
    args: list[Any] = []

    for f in filters:
        question_id = int(f.get("question_id") or 0)
        if not question_id:
            raise ValueError("each filter must have question_id")
        # 如果给 option_text_keywords，先翻译成 option_ids
        option_ids = list(f.get("option_ids") or [])
        keywords = list(f.get("option_text_keywords") or [])
        if not option_ids and keywords:
            ph = ",".join(["?"] * len(keywords))
            cur.execute(
                f"SELECT id FROM questionnaire_options WHERE question_id = ? AND ("
                + " OR ".join(["option_text LIKE ?"] * len(keywords))
                + ")",
                (question_id, *[f"%{k}%" for k in keywords]),
            )
            option_ids = [int(r["id"]) for r in (cur.fetchall() or [])]
        if not option_ids:
            raise ValueError(
                f"filter on question_id={question_id} resolved to 0 options "
                "(option_ids empty and option_text_keywords matched nothing)"
            )
        # 拼一个 EXISTS 子句：该用户在该问题上选了 option_ids 中任意一个
        # 注意 selected_option_ids 是 JSON 数组（TEXT 存的）— 用 LIKE 匹配
        ored = " OR ".join(["CAST(qa.selected_option_ids AS TEXT) LIKE ?" for _ in option_ids])
        where_parts.append(
            f"EXISTS (SELECT 1 FROM questionnaire_submission_answers qa "
            f"JOIN questionnaire_submissions qs ON qs.id = qa.submission_id "
            f"WHERE qs.external_userid = m.external_contact_id "
            f"AND qa.question_id = ? AND ({ored}))"
        )
        args.append(question_id)
        for oid in option_ids:
            # JSON 数组 LIKE：匹配 [1,2,3] 中的某个 id
            args.append(f"%{int(oid)}%")
        # 回填 resolved 给前端展示
        ph = ",".join(["?"] * len(option_ids))
        cur.execute(
            f"SELECT title FROM questionnaire_questions WHERE id = ?",
            (question_id,),
        )
        qrow = cur.fetchone()
        cur.execute(
            f"SELECT option_text AS label FROM questionnaire_options WHERE id IN ({ph})",
            tuple(option_ids),
        )
        labels = [r["label"] for r in (cur.fetchall() or [])]
        filters_resolved.append({
            "question_id": question_id,
            "question_title": str((qrow or {}).get("title", "")),
            "option_ids_in_use": [int(x) for x in option_ids],
            "option_texts_in_use": labels,
        })

    audience_clause = ""
    if audience_code:
        audience_clause = "AND m.current_audience_code = ?"
    where_sql = " AND ".join(where_parts)
    head_sql = (
        "SELECT COUNT(*) AS c FROM automation_member m "
        f"WHERE m.external_contact_id <> '' {audience_clause} AND {where_sql}"
    )
    sample_sql = (
        "SELECT m.external_contact_id, m.id AS member_id, m.current_pool, "
        "m.profile_segment_key, m.behavior_tier_key "
        "FROM automation_member m "
        f"WHERE m.external_contact_id <> '' {audience_clause} AND {where_sql} "
        "LIMIT ?"
    )
    head_args = ((audience_code,) if audience_code else ()) + tuple(args)
    sample_args = ((audience_code,) if audience_code else ()) + tuple(args) + (int(limit),)

    cur.execute(head_sql, head_args)
    headcount = int((cur.fetchone() or {}).get("c") or 0)
    cur.execute(sample_sql, sample_args)
    sample = [dict(r) for r in (cur.fetchall() or [])]

    return {
        "headcount": headcount,
        "sample": sample,
        "filters_resolved": filters_resolved,
        "audience_code": audience_code or "(any)",
    }


# ---------- 4. 拼 segment SQL（不真写库） ----------------------------------

def compose_segment_sql_from_questionnaire(
    *,
    filters: list[dict[str, Any]],
    audience_code: str = "operating",
    extra_member_constraints: list[str] | None = None,
) -> dict[str, Any]:
    """把 filters 拼成 propose_segment 直接可用的 SQL。

    Returns:
        {
          "sql_query": "SELECT m.id AS member_id, m.external_contact_id FROM ...",
          "headcount": int,
          "sample": [...],
          "filters_resolved": [...],
        }

    Agent 拿到 sql_query 之后调 propose_segment(sql_query=...) 即可创建命名分层。
    """
    if not filters:
        raise ValueError("filters is required")
    db = _conn()
    cur = db.cursor()
    where_parts: list[str] = []
    filters_resolved: list[dict[str, Any]] = []
    if audience_code:
        where_parts.append(f"m.current_audience_code = '{audience_code}'")
    for f in filters:
        question_id = int(f.get("question_id") or 0)
        if not question_id:
            raise ValueError("filter.question_id required")
        option_ids = list(f.get("option_ids") or [])
        keywords = list(f.get("option_text_keywords") or [])
        if not option_ids and keywords:
            ph = ",".join(["?"] * len(keywords))
            cur.execute(
                f"SELECT id FROM questionnaire_options WHERE question_id = ? AND ("
                + " OR ".join(["option_text LIKE ?"] * len(keywords))
                + ")",
                (question_id, *[f"%{k}%" for k in keywords]),
            )
            option_ids = [int(r["id"]) for r in (cur.fetchall() or [])]
        if not option_ids:
            raise ValueError(
                f"filter on question_id={question_id} resolved to 0 options"
            )
        ored = " OR ".join([
            f"CAST(qa.selected_option_ids AS TEXT) LIKE '%{int(oid)}%'" for oid in option_ids
        ])
        where_parts.append(
            f"EXISTS (SELECT 1 FROM questionnaire_submission_answers qa "
            f"JOIN questionnaire_submissions qs ON qs.id = qa.submission_id "
            f"WHERE qs.external_userid = m.external_contact_id "
            f"AND qa.question_id = {question_id} AND ({ored}))"
        )
        cur.execute("SELECT title FROM questionnaire_questions WHERE id = ?", (question_id,))
        qrow = cur.fetchone()
        ph = ",".join(["?"] * len(option_ids))
        cur.execute(
            f"SELECT option_text AS label FROM questionnaire_options WHERE id IN ({ph})",
            tuple(option_ids),
        )
        labels = [r["label"] for r in (cur.fetchall() or [])]
        filters_resolved.append({
            "question_id": question_id,
            "question_title": str((qrow or {}).get("title", "")),
            "option_ids_in_use": [int(x) for x in option_ids],
            "option_texts_in_use": labels,
        })
    for extra in (extra_member_constraints or []):
        where_parts.append(str(extra).strip())
    where_sql = " AND ".join(where_parts) or "1=1"
    sql = (
        "SELECT m.id AS member_id, m.external_contact_id "
        "FROM automation_member m "
        f"WHERE {where_sql}"
    )

    # 试跑（沙箱）拿人数 + 样本
    from .sql_sandbox import run_segment_query

    try:
        run = run_segment_query(sql=sql, params={})
        headcount = int(run.get("row_count") or 0)
        sample = list(run.get("rows") or [])[:20]
    except Exception as exc:  # pragma: no cover
        headcount = 0
        sample = []
        logger.warning("compose preview run failed: %s", exc)
    return {
        "sql_query": sql,
        "headcount": headcount,
        "sample": sample,
        "filters_resolved": filters_resolved,
    }


__all__ = [
    "list_questionnaires",
    "inspect_questionnaire",
    "preview_questionnaire_population",
    "compose_segment_sql_from_questionnaire",
]
