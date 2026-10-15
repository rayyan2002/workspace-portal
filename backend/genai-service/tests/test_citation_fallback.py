"""Day 16: citations recovered from the answer when the model declares no quotes.

THE DEFECT, found by a user in the UI rather than by this suite. Under qa-v2 the model
returns {"answer": ..., "quotes": [...]} and citations are resolved FROM those quotes.
Qwen2.5-0.5B keeps to that envelope on short factual questions and abandons it on
open-ended ones, writing plain prose — so a well-grounded answer shipped with no sources at
all. Measured on the real corpus:

    "what is the refund policy"        parse_path=json           1 citation   overlap 0.90
    "Tell me about admission policy"   parse_path=text_fallback  0 citations  overlap 0.73

The second answer IS made of the document. The evidence existed and went unused because the
model did not label it.

WHAT THESE TESTS PROTECT, in order of how much it would cost to lose:

  1. A declared quote always wins. The fallback must never override the model naming its own
     source, which is strictly better evidence.
  2. Invented text is not cited. The fallback reuses `resolve_quote`, so it inherits the
     4-word floor, the 0.6 overlap threshold and the refusal to resolve a tie — but that
     inheritance is the whole safety argument and is asserted here rather than assumed.
  3. The DOCUMENT's words ship, never the model's. The fallback changes which sentence is
     used as the LOOKUP KEY and nothing about what reaches the screen.
  4. The trace says which mechanism fired, because a silent fallback is one nobody can audit.
"""
from uuid import uuid4

import pytest

from app.answering import answer_question
from app.prompts import QA_V2, cite_from_answer
from app.retrieval import RetrievalOutcome
from app.schemas import RetrievedChunk

CHUNKS = [
    "Refunds follow HEC policy: 100% of tuition up to the 7th day of classes, "
    "50% from the 8th to the 15th day, and none thereafter.",
    "The admission fee is charged once at the time of admission and is not refundable.",
    "Candidates must appear for the admission test and interview on the scheduled dates.",
]


# --- what it recovers -------------------------------------------------------

def test_a_sentence_copied_from_a_chunk_resolves_to_that_chunk():
    cited, matched = cite_from_answer(
        "The admission fee is charged once at the time of admission and is not refundable.",
        CHUNKS)

    assert cited == [2]
    assert "admission fee" in matched[2]


def test_several_sentences_resolve_to_several_chunks_in_order():
    """The real shape of the failing case: a multi-sentence prose answer drawing on more
    than one chunk, which is exactly what an open-ended question produces."""
    answer = ("Refunds follow HEC policy: 100% of tuition up to the 7th day of classes. "
              "The admission fee is charged once and is not refundable. "
              "Candidates must appear for the admission test and interview.")

    cited, _ = cite_from_answer(answer, CHUNKS)

    assert cited == [1, 2, 3]


def test_a_paraphrase_close_enough_to_its_source_still_resolves():
    """The model rewords constantly — Day 7 measured 2 of 3 declared quotes unresolvable for
    this reason. A fallback that only matched verbatim text would recover almost nothing."""
    cited, _ = cite_from_answer(
        "Candidates have to appear for the admission test and the interview on scheduled dates.",
        CHUNKS)

    assert cited == [3]


def test_the_same_chunk_is_cited_once_however_many_sentences_match():
    answer = ("The admission fee is charged once at the time of admission. "
              "The admission fee is not refundable at any point.")

    cited, _ = cite_from_answer(answer, CHUNKS)

    assert cited == [2], "a citation list a person reads must not repeat a source"


# --- what it refuses to cite ------------------------------------------------

def test_text_the_documents_do_not_contain_is_not_cited():
    """THE PROPERTY THE WHOLE FALLBACK RESTS ON. It is weaker evidence than a declared
    quote, so it must be at least as unwilling to invent one."""
    cited, _ = cite_from_answer(
        "The capital of France is Paris and the weather there is generally mild.", CHUNKS)

    assert cited == []


def test_a_short_sentence_is_never_evidence_of_anything():
    """Inherited from resolve_quote's 4-word floor. "Yes." or "It is not." overlaps almost
    any chunk and identifies none."""
    cited, _ = cite_from_answer("Yes. It is not. See above.", CHUNKS)

    assert cited == []


def test_a_sentence_matching_two_chunks_equally_resolves_to_neither():
    """An ambiguous citation is not evidence, and a wrong one is worse than none. Two chunks
    carrying the same sentence cannot identify one."""
    duplicated = ["Fees must be paid by bank challan.", "Fees must be paid by bank challan."]

    cited, _ = cite_from_answer("Fees must be paid by bank challan.", duplicated)

    assert cited == []


def test_an_empty_answer_cites_nothing():
    assert cite_from_answer("", CHUNKS) == ([], {})
    assert cite_from_answer("   ", CHUNKS) == ([], {})


def test_no_chunks_means_no_citations():
    assert cite_from_answer("Anything at all, at some length.", []) == ([], {})


# --- how it behaves inside answer_question ----------------------------------

def _answered(reply, chunk_texts):
    chunks = [RetrievedChunk(rank=i, chunk_id=uuid4(), document_id=uuid4(), score=0.9 - i / 100)
              for i, _ in enumerate(chunk_texts, start=1)]
    retrieval = RetrievalOutcome(retrieved=chunks, texts=list(chunk_texts),
                                 candidates_before_threshold=len(chunk_texts),
                                 collapsed_duplicates=0, embed_ms=1, search_ms=1)
    return answer_question(retrieval, "q", QA_V2, lambda _s, _u: (reply, 10, 10))


def test_a_declared_quote_always_wins_over_the_fallback():
    """THE ORDERING THAT MUST NOT INVERT. A declared quote is the model naming the sentence
    it used; the fallback is this service inferring it afterwards. If the fallback ever ran
    first, every citation would silently become the weaker kind."""
    import json

    reply = json.dumps({
        "answer": "The admission fee is charged once and is not refundable.",
        "quotes": ["Refunds follow HEC policy: 100% of tuition up to the 7th day of classes"],
    })

    result = _answered(reply, CHUNKS)

    assert result.citation_source == "quotes"
    assert len(result.citations) == 1
    # The QUOTE points at chunk 1; the ANSWER text points at chunk 2. Asserting the shipped
    # citation carries chunk 1's sentence is what proves the quote won — comparing counts
    # alone would pass whichever mechanism had run.
    assert result.citations[0].quote == CHUNKS[0]


def test_prose_with_no_json_envelope_still_gets_citations():
    """The exact production failure: the model ignores the envelope entirely."""
    result = _answered(
        "The admission fee is charged once at the time of admission and is not refundable.",
        CHUNKS)

    assert result.parse_path == "text_fallback"
    assert len(result.citations) == 1
    assert result.citation_source == "answer_fallback"


def test_a_truncated_json_answer_also_recovers():
    """Not the headline case but the same hole. A long answer hits the 500-token cap, the
    object never closes, and the quotes array is what got cut off — so the salvaged answer
    arrived with no citations despite scoring 1.00 on the grounding guard."""
    truncated = ('{"answer": "The admission fee is charged once at the time of '
                 'admission and is not refundable.')

    result = _answered(truncated, CHUNKS)

    assert result.parse_path == "salvaged_json"
    assert result.citation_source == "answer_fallback"
    assert len(result.citations) == 1


def test_an_answer_the_documents_do_not_support_is_withheld_before_the_fallback_matters():
    """The grounding guard runs regardless. The fallback cannot rescue an ungrounded answer
    into looking sourced, because the answer itself never ships.

    The example is deliberately made of CONTENT words. "Paris is the capital of France and
    the weather there is generally mild" scores 0.364 against these chunks — above the 0.30
    floor — purely on "is", "the", "of", "and", "there". That is a real property of the
    guard worth knowing about and is not what this test is for; picking a sentence that
    shares no vocabulary keeps the test measuring the thing it names.
    """
    result = _answered("Volcanic basalt weathers into fertile tropical soils.", CHUNKS)

    assert result.rejected_as_ungrounded is True
    assert result.citations == []


def test_the_citation_shows_the_documents_sentence_not_the_models():
    """Unchanged by the fallback, and the reason it is safe to display at all. The model's
    sentence is the LOOKUP KEY; `source_sentence` returns the chunk's own words. Storing the
    model's paraphrase would put generated text on screen under a filename — the
    misattribution quote-resolved citations exist to prevent."""
    result = _answered(
        "Candidates have to appear for the admission test and the interview on scheduled dates.",
        CHUNKS)

    assert len(result.citations) == 1
    assert result.citations[0].quote == CHUNKS[2], "the model's paraphrase reached the card"


def test_the_trace_names_the_mechanism_that_produced_the_citations():
    """A silent fallback is one nobody can audit. `answer_fallback` is weaker evidence than
    a declared quote, so a surprising citation has to be traceable to it."""
    import json

    quoted = _answered(json.dumps({"answer": "The admission fee is not refundable.",
                                   "quotes": [CHUNKS[1]]}), CHUNKS)
    inferred = _answered(CHUNKS[1], CHUNKS)
    nothing = _answered("Yes.", CHUNKS)

    assert quoted.citation_source == "quotes"
    assert inferred.citation_source == "answer_fallback"
    assert nothing.citation_source == "none"


@pytest.mark.parametrize("source", ["quotes", "answer_fallback", "none"])
def test_every_citation_source_value_is_one_the_contract_publishes(source):
    """The three values are published in AnswerTrace.citation_source's description and read
    by whoever debugs a citation. A fourth added in code and not there would be undocumented
    the moment it appeared."""
    from app.schemas import AnswerTrace

    described = AnswerTrace.model_fields["citation_source"].description

    assert f"`{source}`" in (described or "")
