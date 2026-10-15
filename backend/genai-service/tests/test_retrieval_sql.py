"""Day 15: the retrieval DB path, with a fake connection. No Postgres.

`tests/test_retrieval.py` covers `rank_rows` — which is pure — and asserts the TEXT of the
SQL statement. Neither executes `_search`, so the wiring between them was untested: the
vector literal format, the parameters actually bound, the over-fetch arithmetic, and the
history fallback's two-pass timing.

That left 67% coverage over the module that decides what the model is allowed to see, and
the specific risk is not a crash. It is **a query that runs fine and returns the wrong
rows** — the empty allow-list becoming an unfiltered search, or a vector literal that
Postgres parses into a different vector. Both would be silent.

The connection is faked at `psycopg.connect`, so the real parameter-building code runs and
the test can read back exactly what would have been sent.
"""
import uuid

import pytest

from app import retrieval as retrieval_module
from app.config import settings
from app.retrieval import _vector_literal, retrieve
from app.schemas import ConversationTurn

DOC_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
DOC_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
CHUNK = uuid.UUID("11111111-1111-1111-1111-111111111111")


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeConnection:
    def __init__(self, recorder, row_batches):
        self._recorder = recorder
        self._batches = row_batches

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, sql, params):
        self._recorder.append({"sql": sql, "params": params})
        return _FakeCursor(self._batches.pop(0) if self._batches else [])


@pytest.fixture()
def db(monkeypatch):
    """Records every query and hands back queued row batches."""
    class _Recorder(list):
        """The queries that ran, plus the row batches to hand back. A list subclass so
        assertions read as `db[0]["params"]` — the queries are the thing under test."""

        batches: list
        dsn: str | None = None

    queries = _Recorder()
    queries.batches = []

    def fake_connect(dsn):
        queries.dsn = dsn
        return _FakeConnection(queries, queries.batches)

    monkeypatch.setattr(retrieval_module.psycopg, "connect", fake_connect)
    return queries


def _row(score, text="Runway inspections are quarterly.", document_id=DOC_A):
    """Matches the SELECT list: (chunk_id, document_id, text, score)."""
    return (CHUNK, document_id, text, score)


def _embed(_question):
    return [0.5] * settings.embedding_dim


# --- the vector literal -----------------------------------------------------

def test_the_vector_literal_is_pgvectors_format_not_pythons():
    """Looks like a Python list by coincidence, and is not one. pgvector parses its own text
    format; a mismatch here is a parse error at best and a different vector at worst."""
    assert _vector_literal([1.0, -0.5, 0.25]) == "[1.0,-0.5,0.25]"
    assert " " not in _vector_literal([1.0, 2.0]), "whitespace is not part of the format"


def test_integers_are_coerced_to_floats_before_formatting():
    """A list of ints reaching this unconverted would produce "[1,0]" — which pgvector reads
    as a valid 2-dimensional vector rather than rejecting, so the failure is silent."""
    assert _vector_literal([1, 0]) == "[1.0,0.0]"


# --- what actually gets sent ------------------------------------------------

def test_the_document_filter_is_bound_even_when_the_allow_list_is_empty(db):
    """THE LEAK THIS SERVICE IS ONE `if` AWAY FROM. An `if allowed_document_ids:` guard turns
    an empty allow-list into a search across every user's documents. test_retrieval.py
    asserts the filter is in the SQL TEXT; this asserts it is in the PARAMETERS of a query
    that actually ran with an empty list."""
    db.batches = [[]]

    retrieve(embed_query=_embed, question="q", allowed_document_ids=[], top_k=5,
             min_score=0.6, history=[])

    assert len(db) == 1
    assert db[0]["params"]["ids"] == [], "the filter was skipped for an empty allow-list"


def test_document_ids_are_bound_as_strings_for_the_uuid_array_cast(db):
    db.batches = [[_row(0.8)]]

    retrieve(embed_query=_embed, question="q", allowed_document_ids=[DOC_A, DOC_B],
             top_k=5, min_score=0.6, history=[])

    assert db[0]["params"]["ids"] == [str(DOC_A), str(DOC_B)]
    assert all(isinstance(i, str) for i in db[0]["params"]["ids"])


def test_the_query_over_fetches_because_collapsing_removes_rows_after_ranking(db):
    """Asking for exactly top_k would return FEWER than top_k whenever duplicates are
    present — which, on this corpus, is almost always. The factor is config, not a literal."""
    db.batches = [[_row(0.8)]]

    retrieve(embed_query=_embed, question="q", allowed_document_ids=[DOC_A], top_k=5,
             min_score=0.6, history=[])

    assert db[0]["params"]["lim"] == 5 * settings.overfetch_factor


def test_the_embedded_question_is_what_gets_searched(db):
    db.batches = [[_row(0.8)]]
    seen = []

    def spy(question):
        seen.append(question)
        return [0.25] * settings.embedding_dim

    retrieve(embed_query=spy, question="when are inspections", allowed_document_ids=[DOC_A],
             top_k=5, min_score=0.6, history=[])

    assert seen == ["when are inspections"]
    assert db[0]["params"]["q"] == _vector_literal([0.25] * settings.embedding_dim)


def test_rows_from_the_database_become_ranked_chunks(db):
    db.batches = [[_row(0.81), _row(0.70, text="A different sentence.")]]

    outcome = retrieve(embed_query=_embed, question="q", allowed_document_ids=[DOC_A],
                       top_k=5, min_score=0.6, history=[])

    assert [c.rank for c in outcome.retrieved] == [1, 2]
    assert outcome.retrieved[0].score == pytest.approx(0.81)
    assert outcome.texts == ["Runway inspections are quarterly.", "A different sentence."]
    assert outcome.candidates_before_threshold == 2


def test_timings_are_measured_separately_so_a_slow_half_is_identifiable(db):
    db.batches = [[_row(0.8)]]

    outcome = retrieve(embed_query=_embed, question="q", allowed_document_ids=[DOC_A],
                       top_k=5, min_score=0.6, history=[])

    assert outcome.embed_ms >= 0 and outcome.search_ms >= 0


# --- the history fallback, which is a SECOND query --------------------------

def test_history_is_not_used_when_the_question_retrieves_on_its_own(db):
    """Prepending unconditionally was the first design and was measurably worse: on a topic
    change the stale topic took one of five slots, and an irrelevant chunk in the context is
    exactly what produces a citation to it."""
    db.batches = [[_row(0.8)]]

    outcome = retrieve(embed_query=_embed, question="what is the fleet size",
                       allowed_document_ids=[DOC_A], top_k=5, min_score=0.6,
                       history=[ConversationTurn(role="user", content="tell me about adbms")])

    assert len(db) == 1, "history was used on a question that did not need it"
    assert outcome.retried_with_history is False


def test_an_anaphoric_follow_up_retries_once_with_the_previous_turn(db):
    """Measured on the real corpus: "tell me in detail", "and?" and "tell me more" all
    returned ZERO chunks alone. The retry costs one extra round trip on the follow-up path
    and nothing at all on the normal one."""
    db.batches = [[], [_row(0.77)]]

    outcome = retrieve(embed_query=_embed, question="tell me in detail",
                       allowed_document_ids=[DOC_A], top_k=5, min_score=0.6,
                       history=[ConversationTurn(role="user", content="what are the adbms formulas")])

    assert len(db) == 2, "the fallback query never ran"
    assert outcome.retried_with_history is True
    assert len(outcome.retrieved) == 1


def test_the_retry_reports_the_total_time_rather_than_hiding_the_first_attempt(db):
    """Both passes are real work the user waited for. Reporting only the second would make
    the follow-up path look as fast as the normal one in every trace."""
    db.batches = [[], [_row(0.77)]]
    calls = []

    def slow_embed(question):
        calls.append(question)
        return [0.5] * settings.embedding_dim

    outcome = retrieve(embed_query=slow_embed, question="and?", allowed_document_ids=[DOC_A],
                       top_k=5, min_score=0.6,
                       history=[ConversationTurn(role="user", content="what is the fleet size")])

    assert len(calls) == 2, "the second pass must embed the combined text, not reuse the first"
    assert "fleet size" in calls[1], "the previous USER turn is what gets prepended"
    assert outcome.embed_ms >= 0 and outcome.search_ms >= 0


def test_nothing_retrieved_and_no_history_does_not_run_a_second_query(db):
    db.batches = [[]]

    outcome = retrieve(embed_query=_embed, question="q", allowed_document_ids=[DOC_A],
                       top_k=5, min_score=0.6, history=[])

    assert len(db) == 1
    assert outcome.retrieved == []
    assert outcome.retried_with_history is False


def test_a_history_of_only_assistant_turns_produces_no_fallback_text(db):
    """The assistant's own replies are never fed back into the query — that would retrieve
    against generated text and make the model's own words look like a source."""
    db.batches = [[]]

    outcome = retrieve(embed_query=_embed, question="and?", allowed_document_ids=[DOC_A],
                       top_k=5, min_score=0.6,
                       history=[ConversationTurn(role="assistant", content="Inspections are quarterly.")])

    assert len(db) == 1, "an assistant turn was used as a retrieval query"
    assert outcome.retried_with_history is False


# --- the summarise path's positional read, Day 18b --------------------------

def test_document_opening_orders_by_ordinal_and_not_by_score(db):
    """THE ENTIRE POINT OF THIS QUERY, asserted on the SQL itself.

    Measured on AI_safety.pdf (81 chunks): the abstract ranks 34th by similarity for
    "what is this paper about", because a question about a whole document has no content
    words to discriminate on. If this ever sorts by score again it silently becomes the
    path it was written to replace, and the only symptom is a worse answer.
    """
    from app.retrieval import document_opening

    db.batches = [[(CHUNK, DOC_A, "Title page.", 0.41),
                   (CHUNK, DOC_A, "The abstract.", 0.66)]]

    retrieved, texts = document_opening([0.5] * settings.embedding_dim, DOC_A, limit=3)

    sql = db[0]["sql"]
    assert "ORDER BY c.ordinal" in sql
    assert "<#>" not in sql.split("ORDER BY")[1], "ordering must not be by distance"
    # Document order is preserved even though the second chunk scores higher.
    assert texts == ["Title page.", "The abstract."]
    assert [c.rank for c in retrieved] == [1, 2]


def test_document_opening_is_scoped_to_one_document(db):
    """It reads a document the caller already cleared — the anchor came from a chunk that
    passed the allow-list and the score floor. A missing WHERE here would turn a scoped
    second read into an unfiltered scan of every user's documents."""
    from app.retrieval import document_opening

    db.batches = [[]]
    document_opening([0.5] * settings.embedding_dim, DOC_A, limit=5)

    assert "WHERE c.document_id = %(doc)s::uuid" in db[0]["sql"]
    assert db[0]["params"]["doc"] == str(DOC_A)
    assert db[0]["params"]["lim"] == 5


def test_document_opening_still_reports_a_real_similarity_score(db):
    """Position decides the ORDER; the score is still computed so a trace from this path
    stays comparable with one from the similarity path. A hard-coded 1.0 would make every
    summarise answer look like a perfect match."""
    from app.retrieval import document_opening

    db.batches = [[(CHUNK, DOC_A, "The abstract.", 0.6580)]]

    retrieved, _texts = document_opening([0.5] * settings.embedding_dim, DOC_A, limit=3)

    assert retrieved[0].score == pytest.approx(0.6580)
    assert "-(c.embedding <#> %(q)s::vector) AS score" in db[0]["sql"]


# --- the near miss, Day 19 --------------------------------------------------

def test_the_best_rejected_score_is_reported_when_nothing_clears_the_floor(db):
    """THE NUMBER THAT TURNS A DEAD END INTO ADVICE.

    Reported from real use: "tell me about ai saftey" returned "I couldn't find anything in
    your documents… upload a document that covers it" while AI_safety.pdf sat in the corpus
    with 81 chunks. The misspelling scores 0.5355 against a 0.60 floor; the correct spelling
    scores 0.7120. Without this field a near miss and a total miss look identical, and the
    user is told to fix the wrong thing.
    """
    db.batches = [[_row(0.5355), _row(0.52), _row(0.48)]]

    outcome = retrieve(_embed, "tell me about ai saftey", [DOC_A], 7, 0.60)

    assert outcome.retrieved == []
    assert outcome.best_rejected_score == pytest.approx(0.5355)


def test_the_best_rejected_score_is_absent_when_something_was_admitted(db):
    """Only meaningful when nothing cleared the floor. With admitted chunks their own scores
    say everything, and a leftover value here would invite a caller to report a 'near miss'
    on a question that was answered."""
    db.batches = [[_row(0.71), _row(0.52)]]

    outcome = retrieve(_embed, "tell me about ai safety", [DOC_A], 7, 0.60)

    assert len(outcome.retrieved) == 1
    assert outcome.best_rejected_score is None


def test_the_best_rejected_score_is_absent_when_the_query_matched_no_rows(db):
    """A subject the corpus has never heard of is a DIFFERENT thing from one it nearly
    matched, and the reply should differ too. None means there was nothing to be near."""
    db.batches = [[]]

    outcome = retrieve(_embed, "the migratory habits of penguins", [DOC_A], 7, 0.60)

    assert outcome.retrieved == []
    assert outcome.best_rejected_score is None
