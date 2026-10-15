"""One error envelope for every failure, including FastAPI's own validation errors.

Spring parses one shape. The 422 body is normalised into the same envelope as everything
else (code MALFORMED_REQUEST) rather than left in FastAPI's default shape — a second
error format on one boundary is exactly the kind of thing that gets handled in one
place and forgotten in another.

Note what a 422 MEANS here: the frontend never reaches this service, and Spring validated
the user's input before calling. A 422 therefore means SPRING sent something malformed.
Spring logs it as its own defect and returns a server error — it must never be relayed to
the user as "your input was invalid".
"""
import logging
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas import ErrorCode
from app.trace import current_trace_id

log = logging.getLogger(__name__)


def _envelope(code: ErrorCode, message: str, errors: list | None = None) -> dict[str, Any]:
    # Annotated, not inferred: from the literal alone this is dict[str, str], and the
    # errors list below would be a type error.
    body: dict[str, Any] = {"code": code.value, "message": message, "trace_id": current_trace_id()}
    if errors is not None:
        body["errors"] = errors
    return {"detail": body}


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Typed as `Exception`, then narrowed.

    Starlette declares handlers as Callable[[Request, Exception], Response]. Annotating the
    parameter as RequestValidationError narrows an input position, which breaks contravariance
    — the reason the editor red-underlines the add_exception_handler calls in main.py even
    though the code runs perfectly. Widening the annotation and narrowing at runtime is the
    honest fix; a `# type: ignore` would only hide it.
    """
    if not isinstance(exc, RequestValidationError):  # registered for this type only
        raise exc
    # Log the field paths, never the values — a rejected body can contain document text.
    log.warning(
        "malformed request from caller on %s: %s",
        request.url.path,
        [".".join(str(p) for p in e.get("loc", ())) for e in exc.errors()],
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_envelope(
            ErrorCode.MALFORMED_REQUEST,
            "Request does not match the published contract — this is a caller defect",
            [{"field": ".".join(str(p) for p in e.get("loc", ())), "error": e.get("msg", "")}
             for e in exc.errors()],
        ),
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):  # registered for this type only
        raise exc
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(ErrorCode.INTERNAL_ERROR, str(exc.detail)),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error on %s", request.url.path)
    # No exception text in the body: a stack trace from a chunking or embedding failure can
    # contain document content (R5).
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_envelope(ErrorCode.INTERNAL_ERROR, "Internal error — see logs for trace_id"),
    )


def not_implemented(endpoint: str) -> HTTPException:
    """Day 1: the shape is real, the behaviour is not.

    A stub returning plausible fake data would look finished and prove nothing. 501 is
    honest, and the request is still validated against the real model before reaching here,
    so the contract is testable today.
    """
    # FastAPI's HTTPException, not Starlette's: we pass a dict as `detail`, and Starlette
    # types that parameter as `str | None`. FastAPI's subclass widens it to Any, and since it
    # IS a subclass, the handler registered for StarletteHTTPException still catches it.
    return HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "code": ErrorCode.NOT_IMPLEMENTED.value,
            "message": f"{endpoint} is declared but not implemented (Month 3 Day 1)",
            "trace_id": current_trace_id(),
        },
    )
