from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, Request

from app.core.exceptions import ServiceError
from app.services.gcp_job_transport import decode_pubsub_indexing_event

router = APIRouter(prefix="/internal", tags=["cloud-jobs"], include_in_schema=False)


def _require_gcp_identity(request: Request, authorization: str | None) -> None:
    if request.app.state.settings.job_dispatch_backend != "gcp":
        raise ServiceError(404, "CLOUD_JOB_TRANSPORT_DISABLED", "Cloud job transport chưa được bật.")
    request.app.state.gcp_oidc_verifier.verify(authorization)


@router.post("/events/indexing")
def receive_indexing_event(
    request: Request,
    envelope: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_gcp_identity(request, authorization)
    event = decode_pubsub_indexing_event(envelope)
    created = request.app.state.cloud_tasks_enqueuer.enqueue(
        event.job_id, dedupe_key=f"pubsub-{event.message_id}"
    )
    return {"accepted": True, "taskCreated": created}


@router.post("/tasks/indexing-jobs/{job_id}")
def process_indexing_task(
    job_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
    queue_name: str | None = Header(default=None, alias="X-CloudTasks-QueueName"),
) -> dict[str, Any]:
    _require_gcp_identity(request, authorization)
    settings = request.app.state.settings
    if queue_name != settings.cloud_tasks_queue:
        raise ServiceError(403, "CLOUD_TASK_QUEUE_FORBIDDEN", "Cloud Task không thuộc queue được phép.")

    processor = request.app.state.async_document_processor
    jobs = request.app.state.indexing_job_service
    try:
        processor.process(job_id)
        return {"jobId": job_id, "status": "ACKNOWLEDGED"}
    except ServiceError as error:
        if error.status_code < 500 and not error.retryable:
            return {"jobId": job_id, "status": "TERMINAL", "code": error.code}
        raw = jobs.raw(job_id)
        if raw is None:
            return {"jobId": job_id, "status": "MISSING"}
        owner_id, _, _ = raw
        try:
            jobs.retry(owner_id, job_id)
        except ServiceError:
            return {"jobId": job_id, "status": "RETRIES_EXHAUSTED", "code": error.code}
        raise ServiceError(
            503,
            "INDEXING_RETRY_REQUESTED",
            "Cloud Tasks sẽ thử lại job lập chỉ mục.",
            retryable=True,
            retry_after_seconds=5,
        ) from error


@router.post("/schedules/reconcile-indexing-jobs")
def reconcile_indexing_jobs(
    request: Request,
    authorization: str | None = Header(default=None),
    scheduler: str | None = Header(default=None, alias="X-CloudScheduler"),
) -> dict[str, Any]:
    _require_gcp_identity(request, authorization)
    if scheduler != "true":
        raise ServiceError(403, "CLOUD_SCHEDULER_REQUIRED", "Endpoint chỉ nhận yêu cầu từ Cloud Scheduler.")
    settings = request.app.state.settings
    jobs = request.app.state.indexing_job_service
    recovered = jobs.recover_stale(settings.indexing_job_stale_seconds)
    pending = jobs.pending_for_reconciliation(settings.pending_job_reconcile_seconds)
    job_ids = list(dict.fromkeys([*recovered, *pending]))
    window = int(datetime.now(timezone.utc).timestamp() // 60)
    created = 0
    for job_id in job_ids:
        if request.app.state.cloud_tasks_enqueuer.enqueue(
            job_id, dedupe_key=f"reconcile-{window}"
        ):
            created += 1
    return {
        "recovered": len(recovered),
        "pending": len(pending),
        "tasksCreated": created,
    }
