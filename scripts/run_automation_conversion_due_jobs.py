from __future__ import annotations

import os
import urllib.request

from scripts import internal_http
from scripts.script_runtime import emit_json, read_app_host, read_app_port, read_int_env, read_internal_api_token


DEFAULT_OPERATOR = "automation_conversion_due_runner"
DEFAULT_RETRY_COUNT = 6
DEFAULT_RETRY_INTERVAL_SECONDS = 10
JOB_DEFINITIONS = {
    "sop": {
        "label": "自动化转化 SOP",
        "path": "/api/admin/automation-conversion/jobs/run-due",
        "payload": {"jobs": ["sop"]},
    },
    "conversion_workflow": {
        "label": "自动化转化任务流",
        "path": "/api/admin/automation-conversion/jobs/run-due",
        "payload": {"jobs": ["conversion_workflow"]},
    },
    "operation_task": {
        "label": "自动化运营任务",
        "path": "/api/admin/automation-conversion/jobs/run-due",
        "payload": {"jobs": ["operation_task"]},
    },
}
DEFAULT_JOB_CODES = ["sop", "conversion_workflow"]


def _post_json(
    *,
    host: str,
    port: str,
    token: str,
    operator: str,
    path: str,
    payload: dict[str, object] | None,
    retry_count: int,
    retry_interval_seconds: int,
) -> dict[str, object]:
    return internal_http.post_json(
        host=host,
        port=port,
        token=token,
        path=path,
        payload={"operator": operator, **dict(payload or {})},
        retry_count=retry_count,
        retry_interval_seconds=retry_interval_seconds,
        urlopen=urllib.request.urlopen,
    )


def run(*, jobs: list[str] | None = None) -> str:
    host = read_app_host()
    port = read_app_port()
    token = read_internal_api_token()
    operator = os.getenv("AUTOMATION_CONVERSION_DUE_OPERATOR", DEFAULT_OPERATOR).strip() or DEFAULT_OPERATOR
    retry_count = read_int_env("AUTOMATION_CONVERSION_DUE_RETRY_COUNT", DEFAULT_RETRY_COUNT)
    retry_interval_seconds = read_int_env(
        "AUTOMATION_CONVERSION_DUE_RETRY_INTERVAL_SECONDS",
        DEFAULT_RETRY_INTERVAL_SECONDS,
    )

    selected_jobs = jobs or list(DEFAULT_JOB_CODES)
    invalid_jobs = [job_code for job_code in selected_jobs if job_code not in JOB_DEFINITIONS]
    if invalid_jobs:
        raise ValueError(f"unsupported due jobs: {', '.join(sorted(dict.fromkeys(invalid_jobs)))}")

    jobs_payload: list[dict[str, object]] = []
    executed_job_count = 0
    failed_job_count = 0
    total_success_count = 0
    total_skipped_count = 0
    total_failed_count = 0
    batch_ids: list[int] = []

    for job_code in selected_jobs:
        definition = JOB_DEFINITIONS[job_code]
        try:
            payload = _post_json(
                host=host,
                port=port,
                token=token,
                operator=operator,
                path=str(definition["path"]),
                payload=dict(definition.get("payload") or {}),
                retry_count=retry_count,
                retry_interval_seconds=retry_interval_seconds,
            )
            executed_job_count += 1
            total_success_count += int(payload.get("total_success_count") or 0)
            total_skipped_count += int(payload.get("total_skipped_count") or 0)
            total_failed_count += int(payload.get("total_failed_count") or 0)
            batch_ids.extend(int(item) for item in (payload.get("batch_ids") or []) if str(item).strip())
            jobs_payload.append(
                {
                    "job_code": job_code,
                    "label": definition["label"],
                    "ok": True,
                    "result": payload,
                }
            )
        except Exception as exc:
            failed_job_count += 1
            jobs_payload.append(
                {
                    "job_code": job_code,
                    "label": definition["label"],
                    "ok": False,
                    "error": str(exc),
                }
            )

    response_payload = {
        "ok": failed_job_count == 0,
        "requested_job_codes": selected_jobs,
        "executed_job_count": executed_job_count,
        "failed_job_count": failed_job_count,
        "total_success_count": total_success_count,
        "total_skipped_count": total_skipped_count,
        "total_failed_count": total_failed_count,
        "batch_ids": sorted(dict.fromkeys(batch_ids)),
        "jobs": jobs_payload,
    }
    return emit_json(response_payload)


def main() -> None:
    raw_jobs = os.getenv("AUTOMATION_CONVERSION_DUE_JOBS", "").strip()
    jobs = [item.strip() for item in raw_jobs.split(",") if item.strip()] if raw_jobs else []
    run(jobs=jobs or None)


if __name__ == "__main__":
    main()
