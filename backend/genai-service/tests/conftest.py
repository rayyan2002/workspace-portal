import os

# Must be set before app.config is imported: these tests exercise the CONTRACT, not the
# models. Loading ~1.5GB of weights to assert that an omitted field is a 422 would make
# the suite slow enough that nobody runs it.
os.environ["GENAI_LOAD_MODELS"] = "false"

# And no FILES. Without this the suite wrote into genai-service/logs/ — the directory the
# running service uses — so a deliberate "the trace blew up" case in test_log_redaction.py
# put a traceback into the real answers.jsonl and corrupted 16 of its 54 lines.
#
# This is the same mistake as Day 16's 11,531 orphaned upload files: a test writing into the
# application's own operational data because nothing told it not to. Found that one in
# uploads/, fixed it, and reintroduced it in logs/ two days later.
os.environ["GENAI_LOG_TO_FILE"] = "false"

# And the suite must not inherit a developer's prompt logging. `GENAI_LOG_PROMPTS=true` in
# a local .env turned SEVEN redaction tests red the moment it was set — correctly, since
# the prompt really was in the log, but for a reason that has nothing to do with the code
# under test. A guarantee whose tests depend on whoever's .env happens to be on disk is a
# guarantee nobody can trust; `test_log_redaction.py` turns it on explicitly where it means
# to test the on state.
os.environ["GENAI_LOG_PROMPTS"] = "false"

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c
