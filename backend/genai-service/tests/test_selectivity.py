"""Day 20: the proposal pointed at the wrong document, and the floor was not the reason.

THE REPORTED CASE. `summarize features of swift` proposed summarising an AI assessment CSV,
while the only document in the corpus containing "swift" — a Suzuki Swift guide, 26
occurrences — was not retrieved at all. Generic scaffolding ("features of ...") dominates a
short query's embedding and outvotes the one token that identifies the document.

These tests never touch Postgres. The index is injected by setting the module cache, which
is also what keeps them honest about the rule being measured rather than asserted: a term
identifies a document only if it names exactly ONE and RECURS there.
"""
import time
from uuid import UUID

import pytest

from app import selectivity
from app.config import settings

SUZUKI = UUID("11111111-1111-1111-1111-111111111111")
ASSESSMENT = UUID("22222222-2222-2222-2222-222222222222")
SAFETY = UUID("33333333-3333-3333-3333-333333333333")


@pytest.fixture(autouse=True)
def index(monkeypatch):
    """term -> (documents containing it, total occurrences), from the real corpus counts."""
    monkeypatch.setattr(selectivity, "_INDEX", {
        "swift": (frozenset({SUZUKI}), 26),
        "suzuki": (frozenset({SUZUKI}), 21),
        "admission": (frozenset({ASSESSMENT}), 13),
        # df 1 BY ACCIDENT. An ordinary English word that happens to appear in one
        # document of a small corpus, twice. Promoting on this broke a golden question
        # before occurrence count was added, which is the whole reason that rule exists.
        "contain": (frozenset({SAFETY}), 2),
        # Identifying but too rare to trust by this rule; the vector search already
        # handles it, so the rescue declining to fire costs nothing.
        "adbms": (frozenset({SAFETY}), 1),
        # Spread across the corpus: identifies nothing.
        "safety": (frozenset({SUZUKI, ASSESSMENT, SAFETY}), 37),
        "features": (frozenset({SUZUKI, ASSESSMENT, SAFETY}), 61),
    })
    monkeypatch.setattr(selectivity, "_LOADED_AT", time.monotonic())


# --- the reported case ------------------------------------------------------

def test_the_reported_question_names_the_document_the_search_missed():
    found = selectivity.selective_documents("summarize features of swift")
    assert found == {"swift": frozenset({SUZUKI})}, (
        "'swift' must identify the Suzuki guide; 'features' and 'summarize' must not")


def test_the_phrasings_that_bracket_it_agree():
    # Measured: all three picked the wrong document before the rescue, and the bare word
    # 'swift' picked the right one without it. All four must agree on the named document.
    for question in ("features of swift", "summarize swift", "swift",
                     "SUMMARIZE FEATURES OF SWIFT"):
        assert selectivity.selective_documents(question) == {"swift": frozenset({SUZUKI})}


# --- what must NOT be treated as identifying --------------------------------

def test_a_word_that_is_rare_by_accident_is_not_identifying():
    """`contain` appears in one document, twice. Document frequency alone called that
    identifying and broke `How many numbered parts does the project setup contain`."""
    assert selectivity.selective_documents("what does this contain") == {}


def test_a_term_spread_across_the_corpus_identifies_nothing():
    assert selectivity.selective_documents("tell me about safety features") == {}


def test_short_tokens_are_ignored():
    """'ai' would match half this corpus, and a two-letter token names nothing."""
    assert selectivity.selective_documents("ai") == {}


def test_a_question_with_nothing_rare_in_it_finds_nothing():
    """The ordinary case, and the one that matters most: no selective term means every
    caller leaves the vector search exactly as it was."""
    assert selectivity.selective_documents("what is this document about") == {}


# --- the rule itself --------------------------------------------------------

def test_occurrences_below_the_setting_are_rejected(monkeypatch):
    monkeypatch.setattr(settings, "rare_term_min_occurrences", 27)
    assert selectivity.selective_documents("swift") == {}, (
        "26 occurrences must not qualify when the floor is 27")


def test_two_documents_are_rejected_at_the_default_setting(monkeypatch):
    monkeypatch.setattr(selectivity, "_INDEX",
                        {"shared": (frozenset({SUZUKI, SAFETY}), 99)})
    monkeypatch.setattr(selectivity, "_LOADED_AT", time.monotonic())
    assert selectivity.selective_documents("shared") == {}, (
        "df 2 is where ordinary words start landing; the default is 1")


def test_several_rare_terms_are_all_reported():
    found = selectivity.selective_documents("suzuki swift")
    assert found == {"swift": frozenset({SUZUKI}), "suzuki": frozenset({SUZUKI})}
