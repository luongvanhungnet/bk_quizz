import base64
import json
from types import SimpleNamespace

import pytest

from app.core.exceptions import ServiceError
from app.services.gcp_job_transport import (
    CloudTasksEnqueuer,
    PubSubJobDispatcher,
    decode_pubsub_indexing_event,
)


class CompletedFuture:
    def result(self, timeout: int) -> str:
        assert timeout == 10
        return "message-1"


class Publisher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes, dict[str, str]]] = []

    def topic_path(self, project: str, topic: str) -> str:
        return f"projects/{project}/topics/{topic}"

    def publish(self, topic: str, data: bytes, **attributes: str) -> CompletedFuture:
        self.calls.append((topic, data, attributes))
        return CompletedFuture()


class TasksClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def queue_path(self, project: str, region: str, queue: str) -> str:
        return f"projects/{project}/locations/{region}/queues/{queue}"

    def create_task(self, *, parent: str, task: dict) -> None:
        self.calls.append({"parent": parent, "task": task})


def cloud_settings() -> SimpleNamespace:
    return SimpleNamespace(
        gcp_project_id="project-1",
        gcp_region="asia-southeast1",
        pubsub_indexing_topic="rag-indexing",
        cloud_tasks_queue="rag-indexing",
        cloud_tasks_worker_url="https://rag.example.run.app",
        cloud_tasks_oidc_audience="https://rag.example.run.app",
        cloud_tasks_service_account_email="rag-events@example.iam.gserviceaccount.com",
        cloud_tasks_dispatch_deadline_seconds=900,
    )


def test_pubsub_dispatcher_publishes_versioned_indexing_event() -> None:
    publisher = Publisher()
    dispatcher = PubSubJobDispatcher(cloud_settings(), publisher)

    dispatcher.dispatch("job-123")

    topic, raw, attributes = publisher.calls[0]
    assert topic == "projects/project-1/topics/rag-indexing"
    assert json.loads(raw) == {
        "version": "1",
        "eventType": "INDEXING_REQUESTED",
        "jobId": "job-123",
    }
    assert attributes["eventType"] == "INDEXING_REQUESTED"


def test_pubsub_envelope_is_validated_and_decoded() -> None:
    data = base64.b64encode(json.dumps({
        "version": "1", "eventType": "INDEXING_REQUESTED", "jobId": "job-123"
    }).encode()).decode()

    event = decode_pubsub_indexing_event({
        "message": {"messageId": "message-1", "data": data}
    })

    assert event.job_id == "job-123"
    assert event.message_id == "message-1"


def test_invalid_pubsub_message_is_rejected() -> None:
    with pytest.raises(ServiceError, match="Pub/Sub") as captured:
        decode_pubsub_indexing_event({"message": {"messageId": "message-1", "data": "!"}})
    assert captured.value.code == "PUBSUB_MESSAGE_INVALID"


def test_cloud_task_has_idempotent_name_oidc_and_deadline() -> None:
    client = TasksClient()
    enqueuer = CloudTasksEnqueuer(cloud_settings(), client)

    assert enqueuer.enqueue("job-123", dedupe_key="message-1") is True
    assert enqueuer.enqueue("job-123", dedupe_key="message-1") is True

    first = client.calls[0]
    second = client.calls[1]
    assert first["task"]["name"] == second["task"]["name"]
    request = first["task"]["http_request"]
    assert request["url"].endswith("/internal/tasks/indexing-jobs/job-123")
    assert request["oidc_token"]["audience"] == "https://rag.example.run.app"
    assert first["task"]["dispatch_deadline"] == {"seconds": 900}
