from typing import Protocol


class JobDispatcher(Protocol):
    def dispatch(self, job_id: str) -> None: ...


class JobProcessor(Protocol):
    def process(self, job_id: str) -> None: ...


class CeleryJobDispatcher:
    def dispatch(self, job_id: str) -> None:
        from app.worker.tasks import process_indexing_job

        process_indexing_job.delay(job_id)


class InlineJobDispatcher:
    """Deterministic dispatcher used only by tests."""

    def __init__(self, processor: JobProcessor) -> None:
        self._processor = processor

    def dispatch(self, job_id: str) -> None:
        self._processor.process(job_id)
