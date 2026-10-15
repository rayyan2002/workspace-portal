import logging
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.errors import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.models_registry import registry
from app.routers import answer, health, ingest, tools
from app.trace import TraceIdLogFilter, TraceIdMiddleware


def _configure_logging() -> None:
    """Console always; files when configured. Day 18 added the files.

    Until then this was one StreamHandler to stderr and nothing else, so every log line this
    service produced lived in terminal scrollback and vanished with the window. That is
    tolerable for INFO chatter and not tolerable for the answer trace, which exists so a
    question asked this morning can be diagnosed this afternoon.

    TWO FILES, because they have two readers:

      app.log      the human-readable stream, same format as the console
      answers.jsonl one JSON object per answer, nothing else, so it can be read with
                   `jq` or loaded into a dataframe without parsing log preamble

    Both ROTATE. An unbounded log file is the same mistake as the 11,531 orphaned upload
    files cleaned out of this project two days ago, wearing a different hat.

    The answer trace still propagates to the console as well, so a live demo is unchanged.
    """
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-5s [%(trace_id)s] %(name)s — %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.addFilter(TraceIdLogFilter())

    root = logging.getLogger()
    root.handlers = [console]
    root.setLevel(logging.INFO)

    if not settings.log_to_file:
        return

    directory = Path(settings.log_dir)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as unwritable:
        # A log directory that cannot be created must not stop the service from serving.
        # Console logging still works, and the failure is visible on the console.
        root.warning("could not create log directory %s (%s); logging to console only",
                     directory, unwritable)
        return

    app_log = RotatingFileHandler(
        directory / "app.log", maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count, encoding="utf-8")
    app_log.setFormatter(formatter)
    app_log.addFilter(TraceIdLogFilter())
    root.addHandler(app_log)

    # The answer trace gets its own file and a BARE formatter: the file is JSON Lines, so a
    # timestamp prefix would make every line unparseable by the tools that make it useful.
    # The record already carries its own trace_id and timings.
    answers = RotatingFileHandler(
        directory / "answers.jsonl", maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count, encoding="utf-8")
    answers.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger("app.trace.answer").addHandler(answers)

    if settings.log_prompts:
        # A THIRD FILE, and only when asked for. The prompt runs to ~14,000 characters and
        # contains the retrieved chunks; escaped into a JSON string it is machine-readable
        # and humanly useless, so it also gets a plain file laid out for reading. Its own
        # handler, so turning the setting off stops the writing rather than merely hiding
        # it. Bare formatter for the same reason as above: the block carries its own
        # trace id and its own separators.
        prompt_log = RotatingFileHandler(
            directory / "prompts.log", maxBytes=settings.log_max_bytes,
            backupCount=settings.log_backup_count, encoding="utf-8")
        prompt_log.setFormatter(logging.Formatter("%(message)s"))
        logging.getLogger("app.trace.prompt").addHandler(prompt_log)
        root.warning(
            "GENAI_LOG_PROMPTS=true — full prompts, INCLUDING RETRIEVED DOCUMENT TEXT, are "
            "being written to %s and into answers.jsonl", directory / "prompts.log")


_configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Kick off model loading, then return immediately.

    Loading is NOT awaited here: the socket must open before the models are in memory, or
    /health/live is connection-refused for the whole startup and looks identical to a dead
    process. Readiness carries the "not usable yet" signal instead.
    """
    if settings.load_models:
        registry.start_loading()
    else:
        logging.getLogger(__name__).warning("GENAI_LOAD_MODELS=false — readiness will never report ready")
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Knowledge Assistant GenAI Service",
    version="0.1.0",
    summary="RAG, citations and tool proposals for the AI Workplace Knowledge Assistant",
    description=(
        "Called only by the Spring Boot backend, never by a browser. See "
        "INTEGRATION_CONTRACT.md. Every endpoint below is declared with its real request "
        "and response shape and returns 501 until it is implemented."
    ),
)

app.add_middleware(TraceIdMiddleware)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(health.router)
app.include_router(ingest.router)
app.include_router(answer.router)
app.include_router(tools.router)

