"""Day 15: the live trace report. Was **9% covered** — the least-tested file in the service.

WHY IT MATTERS MORE THAN ITS 9% SUGGESTS. This is the report a human reads over someone's
shoulder during a demo. It is the only artefact that answers "which document was cited, what
was the matching score, how many chunks were made, why was I offered that action" in one
place, and it was built precisely because those questions had no answer on screen.

A reporting module that silently drops a section is the project's recurring failure mode
exactly: a confident, complete-looking output about the wrong thing. Nobody double-checks a
report — that is what a report is for.

It also runs on the PRODUCT path (`settings.verbose_trace`), so a crash in here would be a
crash in `/answer`. The last test pins the guard that prevents that.
"""
import uuid
from typing import Any

from app.schemas import (
    AnswerResponse,
    AnswerTrace,
    Citation,
    CreateTaskArguments,
    Outcome,
    RetrievedChunk,
    ToolProposal,
)
from app.verbose import print_answer, print_request

CHUNK = uuid.UUID("11111111-1111-1111-1111-111111111111")
DOC = uuid.UUID("22222222-2222-2222-2222-222222222222")


def _lookup(_chunk_id):
    return ("runway-inspection.pdf", 4, "Runway inspections are carried out quarterly.")


def _response(answer="Runway inspections happen quarterly.", **trace_overrides):
    # Annotated dict[str, Any] deliberately. Without it pyright infers the union of every
    # value type in this literal and then rejects `AnswerTrace(**trace)` against each
    # parameter in turn — 36 errors from one line, all of them noise about a test fixture
    # that is correct. The annotation says "this is a bag of keyword arguments", which it is.
    trace: dict[str, Any] = dict(
        trace_id="t-1",
        retrieved=[RetrievedChunk(rank=1, chunk_id=CHUNK, document_id=DOC, score=0.7231)],
        top_k=5, min_score=0.6, candidates_before_threshold=8, collapsed_duplicates=2,
        allowed_document_count=3, embedding_model="bge-small", embedding_model_revision="rev",
        query_prefix_applied=True, history_turns_received=2, retried_with_history=False,
        embed_ms=40, search_ms=12, generation_backend="local", generation_model="qwen",
        generation_model_revision="rev", prompt_template_version="qa-v2",
        prompt_tokens=900, completion_tokens=120, generate_ms=14000,
        grounding_overlap=0.51, total_ms=14100,
    )
    trace.update(trace_overrides)
    return AnswerResponse(
        outcome=Outcome.GROUNDED,
        answer=answer,
        citations=[Citation(chunk_id=CHUNK, document_id=DOC, score=0.7231,
                            quote="Runway inspections are carried out quarterly.")],
        proposals=[],
        trace=AnswerTrace(**trace),
    )


def _render(response, capsys):
    print_answer(response, _lookup)
    return capsys.readouterr().err


# --- the report is complete -------------------------------------------------

def test_every_section_a_reader_expects_is_present(capsys):
    """Asserted as a SET rather than one at a time: a section quietly disappearing is the
    failure mode, and a per-section test suite still passes when one is dropped."""
    report = _render(_response(), capsys)

    for heading in ("RETRIEVAL", "GENERATION", "IS THE ANSWER MADE OF THE DOCUMENTS?",
                    "CITATIONS", "TOOL ROUTING", "WHAT THE USER SEES"):
        assert heading in report, f"the {heading} section vanished from the report"


def test_retrieval_shows_the_filename_and_score_rather_than_a_uuid(capsys):
    """A chunk id is not something a person can act on. The lookup is INJECTED so this
    module never opens a database — the report is a formatter, not a query."""
    report = _render(_response(), capsys)

    assert "runway-inspection.pdf" in report
    assert "page 4" in report
    assert "0.7231" in report
    assert str(CHUNK) not in report, "a raw chunk uuid reached the human-facing report"


def test_a_score_is_shown_with_a_word_beside_it(capsys):
    """A number alone invites over-reading. The band is what the UI shows the user, and the
    report must agree with the UI or the demo contradicts itself."""
    report = _render(_response(), capsys)

    assert "Close match" in report or "Partial match" in report


def test_the_counts_that_explain_the_retrieval_are_all_reported(capsys):
    report = _render(_response(), capsys)

    assert "8" in report, "candidates before the threshold"
    assert "duplicates collapsed" in report
    assert "0.6" in report, "the floor that was applied"


# --- the conditional sections ----------------------------------------------

def test_the_safety_section_appears_only_when_something_was_quarantined(capsys):
    assert "CHUNKS REMOVED" not in _render(_response(), capsys)

    report = _render(_response(quarantined_chunks=1,
                              quarantine_reasons=["ignore all previous instructions"]), capsys)

    assert "CHUNKS REMOVED BEFORE THE MODEL SAW THEM" in report
    assert "ignore all previous instructions" in report, "a silent defence is one nobody can audit"


def test_an_unsupported_request_is_called_out(capsys):
    report = _render(_response(unsupported_request="send email"), capsys)

    assert "CANNOT SERVE" in report
    assert "send email" in report


def test_a_withheld_answer_says_so_in_capitals(capsys):
    """The one verdict that must not be missed on a screen someone is glancing at: the
    answer shown to the user was SUPPRESSED because it was not made of the documents.

    The wording moved from WITHHELD to UNGROUNDED on Day 18b when the verdict started
    coming from `attribute_answer`, so the terminal and the JSON trace cannot disagree.
    What must hold is unchanged: it is in capitals and the overlap is on screen.
    """
    report = _render(_response(rejected_as_ungrounded=True, grounding_overlap=0.04), capsys)

    assert "UNGROUNDED" in report
    assert "0.040" in report
    assert "generation" in report, "the report must name the stage to look at"


def test_a_grounded_answer_gets_the_opposite_verdict(capsys):
    report = _render(_response(), capsys)

    assert "UNGROUNDED" not in report
    assert "GROUNDED" in report
    assert "LOOK AT" not in report, "a clean answer must not point a finger at any stage"


def test_the_report_never_claims_the_answer_is_CORRECT(capsys):
    """THE CAVEAT IS PART OF THE OUTPUT, not just of the docstring. `grounded` means the
    words came from the documents; a model that reads the right passage and states the
    opposite of it scores perfectly here, and Qwen-0.5B has done that on the refund rules.
    A reader glancing at "GROUNDED" must see the limit in the same glance."""
    report = _render(_response(), capsys)

    assert "provenance, not correctness" in report


def test_an_empty_answer_is_not_reported_as_grounded(capsys):
    """THE BUG THIS REPLACES. The old line printed "built from the retrieved text" whenever
    the guard had not fired — including over an EMPTY answer at overlap 0.000. That is how
    a declining cloud model read as a success for two sessions."""
    report = _render(_response(answer="", grounding_overlap=0.0), capsys)

    assert "DECLINED" in report
    assert "generation" in report
    assert "GROUNDED" not in report.replace("UNGROUNDED", "")


def test_quotes_that_resolved_to_nothing_are_counted(capsys):
    report = _render(_response(dropped_quotes=["a sentence that matched no chunk"]), capsys)

    assert "quotes that matched nothing : 1" in report


# --- tool routing, added with the router ------------------------------------

def test_the_routing_section_says_which_half_decided_and_in_words(capsys):
    """"Why was I offered this?" is the question a person actually asks when a proposal
    appears, and it had no answer anywhere in this report while routing lived in a keyword
    list in another service."""
    report = _render(_response(routed_tool="create-task", routed_by="keywords",
                               routing_confidence=1.0), capsys)

    assert "create-task" in report
    assert "keywords" in report
    assert "auditable rule, not a model" in report, "the half is a jargon word without a gloss"


def test_a_classifier_decision_explains_itself_differently_from_a_keyword_hit(capsys):
    report = _render(_response(routed_tool="summarize-document", routed_by="classifier",
                               routing_confidence=0.53), capsys)

    assert "embedding space" in report
    assert "+0.530" in report
    assert "0.10 is the floor" in report, "a margin is meaningless without the threshold"


def test_silence_is_reported_as_a_decision_rather_than_as_an_absence(capsys):
    report = _render(_response(routed_by="silent", routing_confidence=-0.25), capsys)

    assert "(nothing)" in report
    assert "neither half was confident enough to interrupt" in report


def test_suppressed_routing_is_distinguishable_from_silent_routing(capsys):
    report = _render(_response(routed_by="suppressed", unsupported_request="send email"), capsys)

    assert "not consulted" in report


def test_a_proposal_is_printed_with_the_reminder_that_nothing_ran(capsys):
    """The governance boundary, restated where a demo audience can see it. A proposal on
    screen looks like an action taken unless the report says otherwise."""
    response = _response(routed_tool="create-task", routed_by="keywords", routing_confidence=1.0)
    response = response.model_copy(update={"proposals": [ToolProposal(
        arguments=CreateTaskArguments(title="Rehearse the demo", priority="medium"),
        label="Create a task: Rehearse the demo")]})

    report = _render(response, capsys)

    assert "OFFERED: Create a task: Rehearse the demo" in report
    assert "NOTHING HAS RUN" in report
    assert "including a rejection" in report


# --- the request header and the crash guard ---------------------------------

def test_the_incoming_question_is_printed_before_the_work_starts(capsys):
    """A request that takes a minute must show something immediately rather than appearing
    hung — the reason this is a separate function and not part of the final report."""
    print_request("how many parts are in the setup document", 3, "local")
    printed = capsys.readouterr().err

    assert "INCOMING QUESTION" in printed
    assert "how many parts" in printed
    assert "local" in printed


def test_a_broken_report_never_breaks_the_request(capsys, monkeypatch):
    """A DEMONSTRATION AID MUST NEVER COST A USER THEIR ANSWER. verbose_trace runs on the
    product path, so an exception in here would surface as a 500 from /answer — the
    formatter taking down the thing it was formatting."""
    from app.routers import answer as answer_router

    def exploding_lookup(_chunk_id):
        raise RuntimeError("the database went away mid-demo")

    monkeypatch.setattr(answer_router, "_chunk_lookup", exploding_lookup)

    answer_router._print_verbose(_response())   # must not raise

    assert True


def test_no_section_is_printed_to_stdout(capsys):
    """stderr on purpose: stdout is where a piped command's real output goes, and a report
    interleaved into it would corrupt anything consuming the service's output."""
    _render(_response(), capsys)
    out, _err = capsys.readouterr()

    assert out == ""


# --- the prompt itself, Day 19 ----------------------------------------------

def _prompt_report(capsys, template=None, chunks=None, question="What is the refund policy?",
                   earlier=None):
    from app.prompts.templates import QA_V2
    from app.verbose import print_prompt

    template = template or QA_V2
    chunks = chunks or ["Refunds follow HEC policy: 100% of tuition up to the 7th day."]
    rendered = template.render(chunks, question, earlier)
    print_prompt(rendered, template)
    return capsys.readouterr().err


def test_the_report_shows_the_prompt_actually_sent_not_a_reconstruction(capsys):
    """The point of the section. Every other part of this report describes what came back;
    this is the only record of what went in, and it must be the real string."""
    report = _prompt_report(capsys)

    assert "You answer questions about workplace documents." in report, "the system message"
    assert "<context>" in report and "</context>" in report, "the fence, byte for byte"
    assert "Refunds follow HEC policy" in report, "the substituted chunk"
    assert "What is the refund policy?" in report, "the question"


def test_earlier_questions_appear_as_their_own_block(capsys):
    """A follow-up carries the user's OWN earlier questions and never the assistant's
    replies — showing its own output back would teach it the terse format Day 8 measured as
    a problem. If that ever regresses, it regresses visibly here."""
    report = _prompt_report(capsys, earlier=["what are the fees", "when is the deadline"])

    assert "Earlier questions in this conversation:" in report
    assert "- what are the fees" in report
    assert "- when is the deadline" in report


def test_nothing_is_elided_however_long_the_chunks_are(capsys):
    """CHANGED ON REQUEST, and the earlier version was the wrong call. It trimmed chunk
    bodies to 300 characters because RETRIEVAL prints them above — true, and beside the
    point: this section exists to be the prompt AS SENT, and a reader comparing it against
    what the model did cannot use a copy with holes in it."""
    long_chunk = "Admission requirements. " * 60
    report = _prompt_report(capsys, chunks=[long_chunk])

    assert "elided" not in report
    assert long_chunk.strip() in " ".join(
        line.partition("| ")[2] for line in report.splitlines() if "| " in line), (
        "the chunk must appear in full")
    assert "<context>" in report and "</context>" in report
    assert "What is the refund policy?" in report


def test_the_numbering_flag_is_reported_because_it_changes_the_substitution(capsys):
    """`numbered` decides whether chunks are rendered as "[1] ..." or separated by a rule,
    and it is the difference Day 2 measured at 13/25 misattributions against 2/25. Reading
    the prompt without knowing which one produced it is reading half the evidence."""
    from app.prompts.templates import QA_V1, QA_V2

    numbered = _prompt_report(capsys, template=QA_V1)
    assert "chunks rendered as   : [1] ... [2] ...  (numbered)" in numbered
    assert "[1] Refunds follow HEC policy" in numbered

    plain = _prompt_report(capsys, template=QA_V2)
    assert "chunks rendered as   : separated by ---  (no [n] labels)" in plain
    assert "[1] Refunds follow HEC policy" not in plain


def test_no_identifier_is_ever_substituted_into_the_prompt(capsys):
    """The rule the whole citation design rests on: the model is never shown a chunk id, a
    document id, a filename or a page, so it cannot state a wrong one. A future template
    that interpolated any of them would break citation accuracy silently — this fails first.
    """
    import re

    from app.prompts.templates import QA_V2
    from app.verbose import print_prompt

    chunks = ["Refunds follow HEC policy: 100% of tuition up to the 7th day."]
    rendered = QA_V2.render(chunks, "What is the refund policy?")
    print_prompt(rendered, QA_V2)
    report = capsys.readouterr().err

    prompt_only = report.split("NOT substituted")[0]
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", prompt_only), "a UUID reached the prompt"
    assert ".pdf" not in prompt_only and ".xlsx" not in prompt_only, "a filename reached it"
