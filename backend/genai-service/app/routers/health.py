from fastapi import APIRouter, HTTPException, status

from app.config import settings
from app.models_registry import registry
from app.schemas import ErrorCode, ErrorResponse, LiveResponse, ReadyResponse
from app.trace import current_trace_id

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=LiveResponse, summary="The process is up")
def live() -> LiveResponse:
    """Never touches the models.

    Liveness answers "is this process alive", not "is it useful yet". Checking the models
    here would report a still-loading service as dead and get it killed mid-startup.
    """
    return LiveResponse()


@router.get(
    "/ready",
    response_model=ReadyResponse,
    responses={503: {"model": ErrorResponse, "description": "A model is still loading or failed to load"}},
    summary="Both models are loaded and usable",
)
def ready() -> ReadyResponse:
    if not registry.is_ready:
        # Raised, not returned. A returned body is validated against response_model
        # (ReadyResponse) and a 503 error envelope does not match it — which is how the
        # Day 1 test caught this: the endpoint answered 500, not 503.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": ErrorCode.MODEL_NOT_READY.value,
                "message": registry.status_message(),
                "trace_id": current_trace_id(),
            },
        )
    return ReadyResponse(
        embedding_model=settings.embedding_model,
        embedding_model_revision=settings.embedding_model_revision,
        embedding_dim=settings.embedding_dim,
        generation_model=settings.generation_model,
        generation_model_revision=settings.generation_model_revision,
    )
