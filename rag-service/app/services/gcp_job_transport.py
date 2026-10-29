import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from app.core.exceptions import ServiceError

EVENT_VERSION = "1"
INDEXING_REQUESTED = "INDEXING_REQUESTED"


class PubSubJobDispatcher:
    def __init__(self, settings: Any, publisher: Any | None = None) -> None:
        if publisher is None:
            from google.cloud import pubsub_v1

            publisher = pubsub_v1.PublisherClient()
        self._publisher = publisher
        self._topic_path = publisher.topic_path(
            settings.gcp_project_id, settings.pubsub_indexing_topic
        )

    def dispatch(self, job_id: str) -> None:
        payload = json.dumps(
            {
                "version": EVENT_VERSION,
                "eventType": INDEXING_REQUESTED,
                "jobId": job_id,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        self._publisher.publish(
            self._topic_path,
            payload,
            eventType=INDEXING_REQUESTED,
            schemaVersion=EVENT_VERSION,
        ).result(timeout=10)

    def close(self) -> None:
        stop = getattr(self._publisher, "stop", None)
        if callable(stop):
            stop()


class CloudTasksEnqueuer:
    def __init__(self, settings: Any, client: Any | None = None) -> None:
        if client is None:
            from google.cloud import tasks_v2

            client = tasks_v2.CloudTasksClient()
        self._client = client
        self._parent = client.queue_path(
            settings.gcp_project_id,
            settings.gcp_region,
            settings.cloud_tasks_queue,
        )
        self._worker_url = settings.cloud_tasks_worker_url.rstrip("/")
        self._audience = settings.cloud_tasks_oidc_audience
        self._service_account_email = settings.cloud_tasks_service_account_email
        self._dispatch_deadline_seconds = settings.cloud_tasks_dispatch_deadline_seconds

    def enqueue(self, job_id: str, *, dedupe_key: str) -> bool:
        digest = hashlib.sha256(f"{job_id}:{dedupe_key}".encode("utf-8")).hexdigest()[:32]
        task_name = f"{self._parent}/tasks/index-{digest}"
        task = {
            "name": task_name,
            "http_request": {
                "http_method": "POST",
                "url": f"{self._worker_url}/internal/tasks/indexing-jobs/{job_id}",
                "headers": {"Content-Type": "application/json"},
                "body": b"{}",
                "oidc_token": {
                    "service_account_email": self._service_account_email,
                    "audience": self._audience,
                },
            },
            "dispatch_deadline": {"seconds": self._dispatch_deadline_seconds},
        }
        try:
            self._client.create_task(parent=self._parent, task=task)
            return True
        except Exception as error:
            if type(error).__name__ == "AlreadyExists":
                return False
            raise


@dataclass(frozen=True)
class PubSubIndexingEvent:
    job_id: str
    message_id: str


def decode_pubsub_indexing_event(envelope: dict[str, Any]) -> PubSubIndexingEvent:
    message = envelope.get("message")
    if not isinstance(message, dict):
        raise ServiceError(400, "PUBSUB_MESSAGE_INVALID", "Pub/Sub message không hợp lệ.")
    encoded = message.get("data")
    message_id = str(message.get("messageId") or message.get("message_id") or "").strip()
    if not isinstance(encoded, str) or not message_id:
        raise ServiceError(400, "PUBSUB_MESSAGE_INVALID", "Pub/Sub message thiếu data hoặc messageId.")
    try:
        payload = json.loads(base64.b64decode(encoded, validate=True).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ServiceError(400, "PUBSUB_MESSAGE_INVALID", "Pub/Sub message không thể giải mã.") from error
    if (
        payload.get("version") != EVENT_VERSION
        or payload.get("eventType") != INDEXING_REQUESTED
        or not isinstance(payload.get("jobId"), str)
        or not payload["jobId"].strip()
    ):
        raise ServiceError(400, "PUBSUB_EVENT_INVALID", "Sự kiện lập chỉ mục không hợp lệ.")
    return PubSubIndexingEvent(payload["jobId"].strip(), message_id)


class GoogleOidcVerifier:
    def __init__(self, *, audience: str, allowed_service_account: str) -> None:
        self._audience = audience
        self._allowed_service_account = allowed_service_account.casefold()

    def verify(self, authorization: str | None) -> dict[str, Any]:
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.casefold() != "bearer" or not token:
            raise ServiceError(401, "GCP_ID_TOKEN_REQUIRED", "Thiếu Google ID token.")
        try:
            from google.auth.transport.requests import Request as GoogleRequest
            from google.oauth2 import id_token

            claims = id_token.verify_oauth2_token(
                token, GoogleRequest(), audience=self._audience
            )
        except Exception as error:
            raise ServiceError(401, "GCP_ID_TOKEN_INVALID", "Google ID token không hợp lệ.") from error
        issuer = str(claims.get("iss") or "")
        email = str(claims.get("email") or "").casefold()
        if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
            raise ServiceError(401, "GCP_ID_TOKEN_INVALID", "Google ID token có issuer không hợp lệ.")
        if email != self._allowed_service_account or claims.get("email_verified") is not True:
            raise ServiceError(403, "GCP_SERVICE_ACCOUNT_FORBIDDEN", "Service account không được phép gọi endpoint này.")
        return claims
