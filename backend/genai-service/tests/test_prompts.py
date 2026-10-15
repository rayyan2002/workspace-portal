"""Day 2 tests.

These do not test whether the model gives good answers — that needs Day 13's golden
questions. They test the RULES that Day 2's experiments paid for, so a later edit cannot
quietly undo them.
"""
import re

import pytest

from app.prompts import QA_V1, parse_answer, parse_proposal, parse_quoted_answer, resolve_quote
from app.prompts.templates import ALL_TEMPLATES, CONTEXT_CLOSE, CONTEXT_OPEN

# Measured with Qwen's own tokenizer on Day 2. Prefill runs at ~205 tok/s here, so these
# budgets are latency budgets: qa-v1 at 93 tokens costs ~0.45s of every single request.
TOKEN_BUDGETS = {"qa-v1": 110, "qa-v2": 120, "summarize-v1": 110, "propose-v1": 180}


# --- the template rules -----------------------------------------------------

@pytest.mark.parametrize("template", ALL_TEMPLATES, ids=lambda t: t.version)
def test_no_concrete_example_value_in_any_instruction(template):
    """The most expensive lesson of Day 2.

    An instruction ending "like [2]" made the model emit exactly [2] in 9 runs out of 10 —
    it copied the specimen instead of choosing a source, and citation accuracy was 0/10.
    A placeholder "like [N]" was worse: silent in 5 of 10. So: describe the shape in words,
    never show a specimen. This test is the mechanism; the memory of why will not survive.
    """
    assert not re.search(r"\[\s*[0-9N]\s*\]", template.system), (
        f"{template.version} contains a specimen citation — the model will copy it verbatim"
    )


@pytest.mark.parametrize("template", ALL_TEMPLATES, ids=lambda t: t.version)
def test_document_text_never_reaches_the_system_message(template):
    """Retrieved chunks are user-uploaded content, i.e. untrusted input.

    They belong in the user message behind a fence, never in the system message where they
    would sit alongside instructions. Day 12 hardens this; today keeps it possible.
    """
    secret = "PARENTAL LEAVE IS TWELVE WEEKS"
    rendered = template.render([secret], "anything?")
    assert secret not in rendered.system
    assert secret in rendered.user
    assert CONTEXT_OPEN in rendered.user and CONTEXT_CLOSE in rendered.user


def test_chunks_are_numbered_from_one():
    """The numbers are request-local ordinals, and the parser validates against 1..n."""
    rendered = QA_V1.render(["alpha", "beta", "gamma"], "q")
    assert "[1] alpha" in rendered.user
    assert "[3] gamma" in rendered.user
    assert rendered.chunk_count == 3


@pytest.mark.parametrize("template", ALL_TEMPLATES, ids=lambda t: t.version)
def test_template_stays_within_its_token_budget(template):
    """A latency test wearing a size test's clothes."""
    transformers = pytest.importorskip("transformers")
    from app.config import settings

    tok = transformers.AutoTokenizer.from_pretrained(
        settings.generation_model, revision=settings.generation_model_revision
    )
    count = len(tok.encode(template.system))
    budget = TOKEN_BUDGETS[template.version]
    assert count <= budget, (
        f"{template.version} is {count} tokens, over its {budget} budget — "
        f"that is {(count - budget) / 205:.2f}s added to every request"
    )


# --- the parser -------------------------------------------------------------

def test_parses_the_shape_the_prompt_actually_asks_for():
    r = parse_answer('{"answer": "12 weeks.", "cites": [1, 2]}', chunk_count=3)
    assert (r.answer, r.cited, r.parse_path) == ("12 weeks.", [1, 2], "json")


def test_parses_the_shape_the_model_actually_returns():
    """Observed in 10 runs out of 10: valid JSON, improvised schema.

    A strict `isinstance(c, int)` filter reads this as zero citations and reports it with
    total confidence — which is exactly what happened during the Day 2 experiment and
    produced a wrong result I nearly acted on.
    """
    raw = '{"answer": "12 weeks.", "cites": [{"number": 1, "context": "[1]"}, {"number": 2, "text": "..."}]}'
    assert parse_answer(raw, chunk_count=3).cited == [1, 2]


def test_prose_bearing_keys_are_not_scanned_for_numbers():
    """The model echoes chunk text under keys like "value" — and chunk text has numbers in
    it. Reading those as citations would invent sources out of the prose itself."""
    raw = '{"answer": "ok", "cites": [{"number": 1, "value": "12 weeks of leave, 30 days notice"}]}'
    assert parse_answer(raw, chunk_count=3).cited == [1]


def test_markdown_fenced_json_is_recovered():
    raw = '```json\n{"answer": "12 weeks.", "cites": [2]}\n```'
    assert parse_answer(raw, chunk_count=3).cited == [2]


def test_json_buried_in_prose_is_recovered():
    raw = 'Sure! Here is the result:\n{"answer": "12 weeks.", "cites": [1]}\nHope that helps.'
    assert parse_answer(raw, chunk_count=3).cited == [1]


def test_out_of_range_citations_are_dropped_and_recorded():
    """The model cited a chunk that was never shown. Drop it, keep the answer, record it —
    the same rule as Day 1's dropped_citations. Fail one piece, not the whole response."""
    r = parse_answer('{"answer": "a", "cites": [1, 9, 0, -2]}', chunk_count=3)
    assert r.cited == [1]
    assert r.dropped == ["9", "0", "-2"]


def test_repeated_citations_are_deduplicated_in_order():
    r = parse_answer('{"answer": "a", "cites": [2, 1, 2, 2]}', chunk_count=3)
    assert r.cited == [2, 1]


def test_falls_back_to_bracket_markers_when_there_is_no_json():
    """Format B kept as a safety net. Without it a parse failure loses the whole answer
    after a 25-second wait; with it, only the citations degrade."""
    r = parse_answer("Employees get 12 weeks [1]. Managers approve it [2].", chunk_count=3)
    assert r.cited == [1, 2]
    assert r.parse_path == "text_fallback"
    assert "[1]" not in r.answer and "12 weeks" in r.answer


def test_total_garbage_is_reported_as_unparsed_not_as_an_empty_answer():
    r = parse_answer("   ", chunk_count=3)
    assert r.parse_path == "unparsed"
    assert r.is_empty


def test_empty_cites_is_normal_not_an_error():
    r = parse_answer('{"answer": "", "cites": []}', chunk_count=3)
    assert r.cited == [] and r.is_empty and r.parse_path == "json"


# --- tool proposals: fail closed -------------------------------------------

def test_valid_create_task_proposal():
    p = parse_proposal('{"tool": "create-task", "title": "Draft leave summary"}', chunk_count=3)
    assert (p.tool, p.title) == ("create-task", "Draft leave summary")


def test_none_is_a_clean_no_proposal():
    p = parse_proposal('{"tool": "none"}', chunk_count=3)
    assert p.tool is None and p.dropped == []


def test_unknown_tool_is_refused():
    p = parse_proposal('{"tool": "delete_everything", "title": "x"}', chunk_count=3)
    assert p.tool is None and p.dropped == ["delete_everything"]


def test_missing_required_argument_means_no_proposal_not_a_half_built_one():
    """A wrongly-raised proposal puts a decision in front of a human that should never have
    been raised. Day 14 measures that false-positive rate directly."""
    assert parse_proposal('{"tool": "create-task"}', chunk_count=3).tool is None
    assert parse_proposal('{"tool": "lookup-knowledge", "query": "  "}', chunk_count=3).tool is None


def test_summarize_document_must_point_at_a_chunk_that_was_shown():
    assert parse_proposal('{"tool": "summarize-document", "chunk": 9}', chunk_count=3).tool is None
    assert parse_proposal('{"tool": "summarize-document", "chunk": 2}', chunk_count=3).chunk == 2


def test_unparseable_proposal_fails_closed():
    p = parse_proposal("I think you should create a task!", chunk_count=3)
    assert p.tool is None and p.dropped == ["unparseable"]


# --- qa-v2: citations derived from quotes, never taken from the model -------

CHUNKS = [
    "Employees are entitled to 12 weeks of paid parental leave following the birth of a child.",
    "The company observes 14 public holidays per year.",
    "Final approval of leave longer than four weeks rests with the employee's line manager.",
]


def test_verbatim_quote_resolves_to_its_chunk():
    assert resolve_quote("rests with the employee's line manager", CHUNKS) == 3


def test_paraphrase_still_resolves_when_the_overlap_is_clear():
    """Under sampling the model truncates and reworks. A near-miss that plainly came from
    one chunk is still a usable citation; the alternative is throwing away good evidence."""
    assert resolve_quote("final approval of leave longer than four weeks rests with the manager", CHUNKS) == 3


def test_a_quote_matching_nothing_is_dropped_not_guessed():
    """The property qa-v1 could not have. A wrong NUMBER is indistinguishable from a right
    one; a wrong QUOTE matches no chunk and is therefore detectable."""
    r = parse_quoted_answer('{"answer": "x", "quotes": ["the sky is famously green in winter"]}', CHUNKS)
    assert r.cited == [] and len(r.dropped) == 1


def test_short_fragments_are_not_evidence():
    assert resolve_quote("approval", CHUNKS) is None
    assert resolve_quote("12 weeks", CHUNKS) is None


def test_an_ambiguous_quote_cites_nothing():
    """A sentence present in two chunks cannot identify one of them, and a wrong citation is
    worse than a missing one."""
    duplicated = ["Leave must be approved in advance.", "Leave must be approved in advance."]
    assert resolve_quote("Leave must be approved in advance", duplicated) is None


def test_quotes_wrapped_in_objects_are_still_read():
    raw = '{"answer": "x", "quotes": [{"text": "rests with the employee\'s line manager"}]}'
    assert parse_quoted_answer(raw, CHUNKS).cited == [3]


def test_qa_v2_falls_back_to_marker_parsing_when_there_is_no_json():
    r = parse_quoted_answer("The line manager approves it [3].", CHUNKS)
    assert r.cited == [3] and r.parse_path == "text_fallback"


def test_qa_v2_context_carries_no_number_labels():
    """The specimen was in the DATA, not the instruction.

    qa-v1 renders chunks as "[1] text ...". Asked for a verbatim quote with those labels
    visible, the model returned "[5]" as its quote in 8 of 25 runs — copying the labels
    directly above the question rather than quoting. qa-v2 resolves citations from text, so
    the labels serve no purpose and must not be shown: with nothing to copy, quoting is the
    only way to cite.
    """
    from app.prompts import QA_V2

    rendered = QA_V2.render(["alpha text here", "beta text here"], "q?")
    assert not re.search(r"\[\d+\]", rendered.user), "qa-v2 must not show citation-shaped labels"
    assert "alpha text here" in rendered.user and "beta text here" in rendered.user
    assert rendered.chunk_count == 2


def test_recovers_json_whose_braces_the_model_forgot():
    """Measured: 3 runs in 25 produced a fenced fragment with no braces at all. Without
    this the raw markdown became the answer and the user saw ```json in their chat."""
    raw = '```json\n"answer": "12 weeks", "quotes": ["Employees are entitled to 12 weeks of paid leave"]\n```'
    chunks = ["Employees are entitled to 12 weeks of paid leave.", "Something else entirely."]
    r = parse_quoted_answer(raw, chunks)
    assert r.answer == "12 weeks"
    assert r.cited == [1]


def test_summarize_document_resolves_its_source_by_quote():
    """propose-v1 had the same defect qa-v1 did: it asked the model which NUMBERED chunk to
    summarise. Measured across the day, model-supplied numbers are right ~24% of the time.
    The quote is resolved against real text instead."""
    p = parse_proposal(
        '{"tool": "summarize-document", "quote": "rests with the employee\'s line manager"}',
        chunk_texts=CHUNKS,
    )
    assert (p.tool, p.chunk) == ("summarize-document", 3)


def test_summarize_document_with_an_unresolvable_quote_fails_closed():
    p = parse_proposal(
        '{"tool": "summarize-document", "quote": "a sentence from no document at all"}',
        chunk_texts=CHUNKS,
    )
    assert p.tool is None and p.dropped


def test_propose_context_carries_no_number_labels():
    """Measured: with labels visible the model wrote chunk numbers into the TITLE field —
    '"title": 1' — and a create_task proposal was rejected 4/4 as a result. Third instance
    of the same anchoring failure in one day."""
    from app.prompts import PROPOSE_V1, SUMMARIZE_V1

    for template in (PROPOSE_V1, SUMMARIZE_V1):
        rendered = template.render(["alpha text here", "beta text here"], "do something")
        assert not re.search(r"\[\d+\]", rendered.user), f"{template.version} must not show labels"


# --- truncated JSON, Day 8b -------------------------------------------------

def test_a_truncated_json_answer_does_not_leak_scaffolding_to_the_user():
    """Measured on the real corpus, in the exact flow a user runs.

    A detailed answer runs to max_new_tokens, so the object is cut off mid-string and
    _load_json rightly rejects it. The prose fallback then treated the BROKEN JSON as the
    answer and the chat bubble showed ```json {"answer": "... — a salvage worse than the
    failure it was rescuing.
    """
    from app.prompts.parsing import parse_quoted_answer

    truncated = (
        '```json\n{\n  "answer": "Blocks in file: b = records / records_per_block",\n'
        '  "quotes": [\n    {\n      "text": "File / Sear'
    )
    parsed = parse_quoted_answer(truncated, ["File / Search Costs"])

    assert parsed.parse_path == "salvaged_json"
    assert parsed.answer == "Blocks in file: b = records / records_per_block"
    assert "```" not in parsed.answer
    assert '"answer"' not in parsed.answer
    # No citations: the quotes array is what got truncated away, and half a quote is
    # exactly the guess this service refuses to make.
    assert parsed.cited == []


def test_genuine_prose_still_reaches_the_prose_fallback():
    """The salvage must not swallow the case it was added beside: a model that ignored the
    JSON instruction entirely and answered in prose."""
    from app.prompts.parsing import parse_quoted_answer

    parsed = parse_quoted_answer("The leave policy grants twenty days.", ["x"])

    assert parsed.parse_path in {"text_fallback", "unparsed"}
    assert parsed.answer == "The leave policy grants twenty days."


# --- replies that are structured but unlabelled, Day 18b ---------------------
#
# REPORTED FROM THE UI as "the local model replies in latex format". It was not LaTeX. The
# model abandoned qa-v2's {"answer", "quotes"} envelope and invented its own shape, and the
# parser rendered the raw reply — code fence, brackets, quoted keys — as the answer. The
# documents contain no LaTeX at all (checked: zero ADBMS chunks carry a backslash or a
# dollar sign), so the markup was always the envelope rather than the content.

_FORMULA_CHUNK = (
    "ADBMS Numericals — Formula Sheet 1. File / Search Costs "
    "Sequential (linear) scan: cost = b (worst case); average = b / 2 "
    "Binary search (sorted file): cost = ⌈ log₂(b) ⌉ "
    "B+ Tree search: cost = height + 1"
)

_REAL_ARRAY_REPLY = """```json
[
    {
        "formula": "sequential (linear) scan",
        "quote": "Sequential (linear) scan: cost = b (worst case); average = b / 2"
    },
    {
        "formula": "binary search (sorted file)",
        "quote": "Binary search (sorted file): cost = ⌈ log₂(b) ⌉"
    }
]
```"""


def test_a_json_array_reply_is_not_rendered_to_the_user_as_markup():
    """The captured reply, verbatim, from a live local-model request.

    A top-level ARRAY is valid JSON and parses on the first attempt — and `_load_json`
    discarded it for not being a dict, so the prose fallback kept the whole string.
    """
    parsed = parse_quoted_answer(_REAL_ARRAY_REPLY, [_FORMULA_CHUNK])

    assert "```" not in parsed.answer, "a code fence reached the answer the user reads"
    assert '"formula"' not in parsed.answer, "JSON keys reached the answer"
    assert "[" not in parsed.answer and "{" not in parsed.answer
    assert "cost = ⌈ log₂(b) ⌉" in parsed.answer, "the content itself must survive"


def test_the_array_reply_still_resolves_its_citations():
    """The content was never the problem — both quotes are verbatim document text and the
    grounding guard scored 0.882 on this reply. Only the envelope was unexpected."""
    parsed = parse_quoted_answer(_REAL_ARRAY_REPLY, [_FORMULA_CHUNK])

    assert parsed.cited == [1]
    assert parsed.parse_path == "unlabelled_json", (
        "the trace must name this path, not report it as a clean parse")


def test_a_label_is_not_printed_twice_alongside_the_line_it_labels():
    """These replies pair a label with its content, and the label is long enough to resolve
    against a chunk by itself. Without subsumption filtering the answer read
    "binary search (sorted file)" on its own line directly above the formula."""
    parsed = parse_quoted_answer(_REAL_ARRAY_REPLY, [_FORMULA_CHUNK])

    assert parsed.answer.lower().count("binary search (sorted file)") == 1


def test_an_object_with_none_of_the_expected_keys_is_not_a_silent_empty_answer():
    """The quieter half of the same defect. An object improvising its own keys produced
    answer="" and no citations — the user told nothing could be put together while the
    content sat unread in the reply. The array case at least showed something."""
    reply = '{"formulas": ["Binary search (sorted file): cost = ⌈ log₂(b) ⌉"]}'

    parsed = parse_quoted_answer(reply, [_FORMULA_CHUNK])

    assert parsed.answer, "an empty answer here discards content that was present"
    assert parsed.cited == [1]


def test_an_unlabelled_reply_matching_nothing_is_still_readable_prose():
    """Nothing resolves, so there is no document text to build from. The strings are still
    shown — prose the model wrote is a better thing to render than the JSON around it — and
    the path is recorded with no citations so a trace shows exactly what happened."""
    reply = '["The quick brown fox jumped over the lazy dog entirely."]'

    parsed = parse_quoted_answer(reply, [_FORMULA_CHUNK])

    assert "[" not in parsed.answer and '"' not in parsed.answer
    assert parsed.cited == []
    assert parsed.parse_path == "unlabelled_json"


def test_a_well_formed_qa_v2_reply_is_untouched_by_any_of_this():
    """The regression guard. Everything above runs only when the expected shape is absent,
    so the ordinary path must still report parse_path=json and resolve from `quotes`."""
    reply = ('{"answer": "Binary search costs the ceiling of log base 2 of b.", '
             '"quotes": ["Binary search (sorted file): cost = ⌈ log₂(b) ⌉"]}')

    parsed = parse_quoted_answer(reply, [_FORMULA_CHUNK])

    assert parsed.parse_path == "json"
    assert parsed.answer == "Binary search costs the ceiling of log base 2 of b."
    assert parsed.cited == [1]


def test_the_dict_only_contract_of_load_json_is_unchanged():
    """`parse_answer` and `parse_proposal` both call `_load_json` and both assume a dict.
    Widening it in place would have changed qa-v1 and the tool router as a side effect, so
    the array-aware loader is a separate function and this pins that apart."""
    from app.prompts.parsing import _json_container, _load_json

    assert _load_json("[1, 2]") is None, "a list must not escape as a dict"
    assert _json_container("[1, 2]") == [1, 2]
    assert _load_json('{"answer": "x"}') == {"answer": "x"}
