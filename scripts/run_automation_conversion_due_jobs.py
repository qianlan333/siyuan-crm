from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request


DEFAULT_OPERATOR = "automation_conversion_due_runner"
DEFAULT_RETRY_COUNT = 6
DEFAULT_RETRY_INTERVAL_SECONDS = 10
JOB_DEFINITIONS = {
    "conversion_workflow": {
        "label": "自动化转化任务流",
        "path": "/api/admin/automation-conversion/jobs/run-due",
        "payload": {"jobs": ["conversion_workflow"]},
    }
}


def build_request(*, host: str, port: str, token: str, operator: str, path: str, payload: dict[str, object] | None = None) -> urllib.request.Request:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(
        f"http://{host}:{port}{path}",
        data=json.dumps({"operator": operator, **dict(payload or {})}).encode("utf-8"),
        headers=headers,
        method="POST",
    )


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
    request = build_request(host=host, port=port, token=token, operator=operator, path=path, payload=payload)
    attempts = max(1, int(retry_count))
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            print(body)
            raise
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt >= attempts:
                raise
            time.sleep(max(0, int(retry_interval_seconds)))
    assert last_error is not None
    raise last_error


def run(*, jobs: list[str] | None = None) -> str:
    host = os.getenv("APP_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = os.getenv("APP_PORT", "5000").strip() or "5000"
    token = os.getenv("AUTOMATION_INTERNAL_API_TOKEN", "").strip()
    operator = os.getenv("AUTOMATION_CONVERSION_DUE_OPERATOR", DEFAULT_OPERATOR).strip() or DEFAULT_OPERATOR
    retry_count = int((os.getenv("AUTOMATION_CONVERSION_DUE_RETRY_COUNT") or DEFAULT_RETRY_COUNT))
    retry_interval_seconds = int((os.getenv("AUTOMATION_CONVERSION_DUE_RETRY_INTERVAL_SECONDS") or DEFAULT_RETRY_INTERVAL_SECONDS))

    selected_jobs = jobs or list(JOB_DEFINITIONS.keys())
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
    body = json.dumps(response_payload, ensure_ascii=False)
    print(body)
    return body


def main() -> None:
    raw_jobs = os.getenv("AUTOMATION_CONVERSION_DUE_JOBS", "").strip()
    jobs = [item.strip() for item in raw_jobs.split(",") if item.strip()] if raw_jobs else []
    run(jobs=jobs or None)


if __name__ == "__main__":
    main()
