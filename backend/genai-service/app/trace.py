"""Trace ID propagation.

Spring already stamps every request with a trace ID and puts it on every log line
(TraceIdFilter). Propagating the same ID across the boundary is what makes one grep
span both services. If the header is missing, that is a Spring defect: we generate an
ID so the request is still traceable, and log that we had to.
"""
import logging
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

TRACE_HEADER = "X-Trace-Id"
_trace_id: ContextVar[str] = ContextVar("trace_id", default="-")

log = logging.getLogger(__name__)


def current_trace_id() -> str:
    return _trace_id.get()


class TraceIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get(TRACE_HEADER)
        trace_id = incoming or uuid.uuid4().hex
        token = _trace_id.set(trace_id)
        if incoming is None and request.url.path not in ("/health/live", "/health/ready"):
            log.warning("no %s header on %s — caller should propagate it", TRACE_HEADER, request.url.path)
        try:
            response = await call_next(request)
        finally:
            _trace_id.reset(token)
        response.headers[TRACE_HEADER] = trace_id
        return response


class TraceIdLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = current_trace_id()
        return True
