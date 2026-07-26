from contextvars import ContextVar

REQUEST_TRACE_ID: ContextVar[str] = ContextVar("request_trace_id", default="unknown")
