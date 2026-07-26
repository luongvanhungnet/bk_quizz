import os

from celery.signals import worker_process_init
from prometheus_client import start_http_server


@worker_process_init.connect
def start_worker_metrics(**_: object) -> None:
    port = int(os.getenv("WORKER_METRICS_PORT", "9101"))
    start_http_server(port)
