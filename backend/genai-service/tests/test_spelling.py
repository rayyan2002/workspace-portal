"""Day 19: a typo must not lose a document the corpus plainly contains.

THE REPORTED CASE. `tell me about ai saftey` answered "I couldn't find anything in your
documents" while AI_safety.pdf sat there with 81 chunks. The misspelling scores 0.5355
against a 0.60 floor; the correct spelling scores 0.7120. One letter costs 0.177, because
`bge-small` compares token sequences and has no notion of spelling.

These tests never touch Postgres. The vocabulary is injected by setting the module cache,
which is also what keeps them honest about WHICH words can be corrected: a word is only
ever replaced by one the corpus actually contains.
"""
import time

import pytest

from app import spelling


@pytest.fixture(autouse=True)
def vocabulary(monkeypatch):
    """A small corpus vocabulary, with frequencies, standing in for the real query."""
    monkeypatch.setattr(spelling, "_VOCABULARY", {
        "safety": 40, "satiety": 1, "admission": 25, "admin": 30, "position": 12,
        "positions": 9, "degradation": 7, "document": 50, "documents": 44, "range": 15,
    })
    monkeypatch.setattr(spelling, "_LOADED_AT", time.monotonic())


# --- the reported case ------------------------------------------------------

def test_the_reported_typo_is_corrected():
    corrected, changes = spelling.correct("tell me about ai saftey")

    assert corrected == "tell me about ai safety"
    assert changes == [("saftey", "safety")]


def test_a_transposition_beats_a_rarer_word_at_the_same_distance():
    """`saftey` is 2 edits from `safety` and 2 from `satiety`. Frequency is the tie-break,
    because the word the documents actually use is the better guess."""
    _corrected, changes = spelling.correct("saftey")

    assert changes == [("saftey", "safety")]


# --- what must NOT be touched -----------------------------------------------

def test_a_word_the_corpus_contains_is_never_corrected():
    """If the documents contain the word the user typed, it is not a typo however unusual
    it looks."""
    corrected, changes = spelling.correct("admin position")

    assert corrected == "admin position"
    assert changes == []


def test_short_words_are_left_alone():
    """At three characters too many real words are one edit apart, and a wrong correction
    changes the question's meaning rather than its spelling."""
    corrected, changes = spelling.correct("who ran the job")

    assert corrected == "who ran the job"
    assert changes == []


def test_a_word_too_far_from_anything_is_left_alone():
    """Three edits starts matching unrelated words of the same length. Leaving it alone
    produces a clean failure, which is better than a confident wrong answer."""
    corrected, changes = spelling.correct("xylophone")

    assert corrected == "xylophone"
    assert changes == []


def test_punctuation_and_spacing_survive_exactly():
    """The corrected question is re-embedded, so anything that changes its shape changes
    the vector for reasons unrelated to the typo."""
    corrected, _ = spelling.correct("WHAT IS THE ADMISSOIN POLICY?")

    assert corrected == "WHAT IS THE admission POLICY?"


# --- the safety properties --------------------------------------------------

def test_an_empty_vocabulary_changes_nothing(monkeypatch):
    """A corpus with no documents yet. Correcting against nothing would be inventing."""
    monkeypatch.setattr(spelling, "_VOCABULARY", {})
    monkeypatch.setattr(spelling, "_LOADED_AT", time.monotonic())

    assert spelling.correct("saftey") == ("saftey", [])


def test_a_vocabulary_that_cannot_load_does_not_break_the_request(monkeypatch):
    """A spelling aid must never be able to fail a question. The caller then retrieves
    nothing, which is exactly what it would have done without this module."""
    monkeypatch.setattr(spelling, "_VOCABULARY", None)
    monkeypatch.setattr(spelling, "_load_vocabulary",
                        lambda dsn=None: (_ for _ in ()).throw(RuntimeError("no database")))

    assert spelling.correct("saftey") == ("saftey", [])


def test_the_edit_bound_abandons_early_rather_than_scoring_everything():
    """The distance is computed against several thousand words on a failed request. The
    answer 'more than 2' is as useful as the exact number and is reached far sooner."""
    assert spelling._edits_within("safety", "saftey", 2) == 2
    assert spelling._edits_within("safety", "xylophone", 2) is None
    assert spelling._edits_within("safety", "safety", 2) == 0


def test_every_replacement_comes_from_the_corpus():
    """The property the whole design rests on: a word is only ever replaced by one the
    documents actually contain, so a correction can never introduce a term the corpus has
    never seen."""
    vocab = dict(spelling._VOCABULARY or {})
    _corrected, changes = spelling.correct("tell me about ai saftey and admissoin")

    assert changes, "expected at least one correction to exercise this"
    for _typed, replacement in changes:
        assert replacement in vocab
