"""Day 14: the validation half of tool-calling evaluation.

Driven from the same `evaluation/tool_cases.json` the Spring routing tests read. Restating
the cases inline in two languages would be a sixth copy of a contract, which is the failure
this project keeps finding.

ROUTING is tested in Spring, because Spring routes. Day 10 measured the generation model on
that decision and found constant functions — "none" to all nine cases under one prompt,
"create-task" to all nine under another, including "what is the fleet size". Neither was
deciding; the prompt was the entire signal.

VALIDATION is tested here, because this is where a model's output becomes a proposal or
becomes nothing. `parse_proposal` FAILS CLOSED: unknown tool, missing argument, out-of-range
chunk all produce no proposal rather than a half-built one. A wrongly-proposed action puts a
decision in front of a human that should never have been raised.
"""
import json
from pathlib import Path

import pytest

from app.prompts import parse_proposal

CASES = json.loads((Path(__file__).resolve().parents[1] / "evaluation" / "tool_cases.json").read_text())
VALIDATION = CASES["validation"]

# Three chunks, so "chunk": 99 is demonstrably out of range rather than merely unlucky.
CHUNKS = ["Runway inspections are quarterly.", "The line manager approves.", "Costs are logged."]


@pytest.mark.parametrize("case", VALIDATION, ids=[c["why"] for c in VALIDATION])
def test_every_validation_case(case):
    parsed = parse_proposal(case["raw"], chunk_texts=CHUNKS)

    assert parsed.tool == case["expect_tool"], (
        f"{case['why']}: expected {case['expect_tool']!r}, got {parsed.tool!r} "
        f"from {case['raw'][:60]!r}"
    )


def test_an_unknown_tool_is_never_rounded_to_a_known_one():
    """The dangerous failure mode would be helpfulness: "delete-everything" is not a typo for
    "create-task", and nothing here tries to guess what the model meant."""
    parsed = parse_proposal('{"tool": "delete-everything", "title": "x"}', chunk_texts=CHUNKS)

    assert parsed.tool is None
    assert parsed.dropped, "an unknown tool should be RECORDED, not silently ignored"


def test_underscores_are_rejected_because_the_running_system_uses_hyphens():
    """create_task is a rejected discriminator tag.

    These literals go to Postgres (action_audit.type), to Jackson's @JsonSubTypes and to the
    frontend's union. The training tracker writes them with underscores; the running system
    does not, and the running system wins. Accepting both would be a translation layer whose
    only job is to undo a naming choice.
    """
    assert parse_proposal('{"tool": "create_task", "title": "x"}', chunk_texts=CHUNKS).tool is None
    assert parse_proposal('{"tool": "create-task", "title": "x"}', chunk_texts=CHUNKS).tool == "create-task"


def test_a_chunk_ordinal_outside_what_was_shown_does_not_resolve():
    """summarize-document carries a 1-based index into the chunks sent FOR THIS REQUEST.
    An ordinal beyond that range is the model inventing a source."""
    assert parse_proposal('{"tool": "summarize-document", "chunk": 99}',
                          chunk_texts=CHUNKS).tool is None
    assert parse_proposal('{"tool": "summarize-document", "chunk": 2}',
                          chunk_texts=CHUNKS).tool == "summarize-document"


def test_the_evaluation_set_still_tests_failure_more_than_success():
    """A validation set that drifted toward happy paths would pass while proving little.
    Failing closed is the property worth protecting, so most cases must be failures."""
    failures = sum(1 for c in VALIDATION if c["expect_tool"] is None)

    assert failures >= len(VALIDATION) * 0.6, (
        f"only {failures}/{len(VALIDATION)} validation cases exercise a failure path")
