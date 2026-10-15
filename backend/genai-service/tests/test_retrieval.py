"""Day 6: the rules that decide what a user sees.

No database and no model here — `rank_rows` is pure, which is why it was extracted.
The SQL itself is covered by benchmarks/13 and by the live checks in COMMANDS.md.
"""
from uuid import UUID, uuid4

import pytest

from app.config import settings
from app.retrieval import _SEARCH_SQL, rank_rows
from app.schemas import ConversationTurn, RetrievalRequest


def row(text: str, score: float, doc: UUID | None = None):
    return (uuid4(), doc or uuid4(), text, score)


# --- near-duplicate collapsing ----------------------------------------------

def test_byte_identical_chunks_collapse_to_one():
    """The measured failure: top_k=5 returning ONE passage five times.

    "What were the quarterly financial results?" scored [0.700] x 5 against the real
    corpus — five copies of a single chunk, filling the whole context window with one
    fact. Without collapsing, the model sees one passage and calls it five sources.
    """
    rows = [row("identical text", 0.9) for _ in range(5)]
    retrieved, _texts, candidates, duplicates, _e = rank_rows(rows, top_k=5, min_score=0.6)

    assert len(retrieved) == 1
    assert duplicates == 4
    assert candidates == 1


def test_collapsing_keeps_the_highest_scoring_copy():
    rows = [row("same", 0.90), row("same", 0.80), row("other", 0.70)]
    retrieved, _t, _c, _d, _e = rank_rows(rows, top_k=5, min_score=0.0)

    assert [r.score for r in retrieved] == [0.90, 0.70]


def test_collapsing_is_exact_not_fuzzy():
    """Deliberate: a one-character difference is NOT a duplicate.

    Exact hashing cannot merge two genuinely different passages that happen to score
    alike. The seeded stubs that match each other at 0.857 while sharing no text are a
    CORPUS problem for Day 13, not something retrieval should paper over.
    """
    retrieved, _t, _c, duplicates, _e = rank_rows(
        [row("the policy grants 20 days", 0.9), row("the policy grants 21 days", 0.88)],
        top_k=5, min_score=0.0,
    )
    assert len(retrieved) == 2
    assert duplicates == 0


# --- the threshold ----------------------------------------------------------

def test_scores_below_min_score_are_dropped():
    retrieved, _t, _c, _d, _e = rank_rows([row("a", 0.70), row("b", 0.59)], top_k=5, min_score=0.60)
    assert [r.score for r in retrieved] == [0.70]


def test_everything_filtered_out_is_distinguishable_from_nothing_retrieved():
    """The reason `candidates_before_threshold` exists.

    Both cases return zero chunks. Only the trace says which happened, and they have
    different causes: an empty allow-list versus a question the corpus cannot answer.
    """
    _r, _t, candidates_filtered, _d, _e = rank_rows([row("a", 0.10)], top_k=5, min_score=0.60)
    _r2, _t2, candidates_empty, _d2, _e2 = rank_rows([], top_k=5, min_score=0.60)

    assert candidates_filtered == 1     # retrieved something, then filtered it out
    assert candidates_empty == 0        # retrieved nothing at all


def test_default_min_score_rejects_the_measured_noise_floor():
    """0.518 was the best score a question the corpus CANNOT answer achieved.

    The old default of 0.35 sat below it, so `insufficient_context` could never fire.
    """
    noise_floor = 0.518
    assert settings.default_min_score > noise_floor
    retrieved, _t, _c, _d, _e = rank_rows([row("noise", noise_floor)], top_k=5,
                                      min_score=settings.default_min_score)
    assert retrieved == []


# --- ranking and truncation -------------------------------------------------

def test_ranks_are_contiguous_and_one_based_after_collapsing():
    rows = [row("a", 0.9), row("a", 0.89), row("b", 0.8), row("c", 0.7)]
    retrieved, _t, _c, _d, _e = rank_rows(rows, top_k=5, min_score=0.0)
    assert [r.rank for r in retrieved] == [1, 2, 3]


def test_truncates_to_top_k_after_collapsing_not_before():
    """Over-fetching is pointless if truncation happens first."""
    rows = [row("dup", 0.99)] * 3 + [row(f"real{i}", 0.9 - i / 100) for i in range(5)]
    retrieved, _t, _c, _d, _e = rank_rows(rows, top_k=3, min_score=0.0)
    assert len(retrieved) == 3
    assert retrieved[0].score == 0.99
    assert retrieved[1].score != 0.99   # the duplicates did not consume the budget


# --- the boundary rules -----------------------------------------------------

def test_sql_applies_the_document_filter_unconditionally():
    """The leak this service is one `if` away from.

    An `if allowed_document_ids:` guard turns an empty allow-list into a search across
    every user's documents. The filter must be IN the statement, always.
    """
    assert "document_id = ANY(" in _SEARCH_SQL
    assert "WHERE" in _SEARCH_SQL


def test_sql_converts_negative_inner_product_into_similarity():
    """pgvector's <#> is NEGATIVE inner product; the contract publishes similarity.

    ORDER BY must use the raw operator so an index can serve it, while the SELECT list
    negates it. Both, in one statement, converted once.
    """
    assert "-(c.embedding <#> %(q)s::vector) AS score" in _SEARCH_SQL
    assert "ORDER BY c.embedding <#> %(q)s::vector" in _SEARCH_SQL


def test_contract_defaults_are_not_a_second_copy_of_config():
    """min_score drifted exactly this way: config said one thing, the contract another."""
    request = RetrievalRequest(question="q", allowed_document_ids=[])
    assert request.min_score == settings.default_min_score
    assert request.top_k == settings.default_top_k


def test_overfetch_is_large_enough_for_the_measured_worst_case():
    """One text appears 5 times in the real corpus."""
    assert settings.overfetch_factor >= 5 - 1


@pytest.mark.parametrize("bad", [-1.1, 1.1])
def test_min_score_outside_cosine_range_is_rejected(bad):
    with pytest.raises(ValueError):
        RetrievalRequest(question="q", allowed_document_ids=[], min_score=bad)


# --- conversation history, Day 8b ------------------------------------------

def test_history_is_a_fallback_not_a_default():
    """Measured on the real corpus, and the reason this is not applied unconditionally.

    Standalone questions retrieve fine alone (1-5 chunks). Prepending the previous turn to
    them cost one of five slots to the stale topic on a topic change — and an irrelevant
    chunk in the context is exactly what produces a citation to it.
    """
    from app.retrieval import search_text_with_history

    history = [
        ConversationTurn(role="user", content="what are the formulas of adbms"),
        ConversationTurn(role="assistant", content="b = records / records_per_block"),
    ]
    assert search_text_with_history("tell me in detail", history, 1) == (
        "what are the formulas of adbms tell me in detail"
    )


def test_the_assistants_own_replies_are_never_fed_back_into_the_query():
    """An earlier assistant turn is this system's OUTPUT. Embedding it searches for whatever
    the model happened to say last — on this corpus, often a single terse formula."""
    from app.retrieval import search_text_with_history

    history = [ConversationTurn(role="assistant", content="b = records / records_per_block")]
    assert search_text_with_history("tell me in detail", history, 1) is None


def test_only_the_most_recent_user_turns_are_used():
    from app.retrieval import search_text_with_history

    history = [
        ConversationTurn(role="user", content="first"),
        ConversationTurn(role="user", content="second"),
    ]
    assert search_text_with_history("now", history, 1) == "second now"
    assert search_text_with_history("now", history, 2) == "first second now"


def test_history_defaults_to_empty_unlike_the_allow_list():
    """allowed_document_ids omitted is a 422 because Spring always knows the answer.
    History omitted is a FIRST TURN, which is a normal state, not a caller defect."""
    request = RetrievalRequest(question="q", allowed_document_ids=[])
    assert request.history == []


def test_history_has_a_sanity_bound():
    with pytest.raises(ValueError):
        RetrievalRequest(
            question="q",
            allowed_document_ids=[],
            history=[ConversationTurn(role="user", content="x")] * 51,
        )


def test_the_fallback_reaches_past_a_contentless_previous_turn():
    """Found in the UI: three questions in a row about one document, and the third returned
    "I couldn't find anything in your documents".

    "tell me all formulas in detail" followed "tell me in detail", which followed the only
    turn that named the subject. Reaching one turn back built
    "tell me in detail tell me all formullas in detail" — no subject, 0 chunks. Reaching two
    picks up "what are the formula of adbms" and retrieves 4.
    """
    from app.retrieval import search_text_with_history

    history = [
        ConversationTurn(role="user", content="what are the formula of adbms"),
        ConversationTurn(role="assistant", content="b = records / records_per_block"),
        ConversationTurn(role="user", content="tell me in detail"),
    ]
    built = search_text_with_history("tell me all formulas in detail", history,
                                     settings.history_turns_for_retrieval)

    # Not None: there IS a user turn to lean on, and the assertion below would pass
    # vacuously against None without saying so.
    assert built is not None
    assert "adbms" in built, "the fallback must reach past a contentless turn to the subject"


def test_configured_lookback_is_more_than_one_turn():
    """1 was the original value and was measurably too few. Guarding it so the reason does
    not get lost in a future tidy-up."""
    assert settings.history_turns_for_retrieval >= 2


# --- anchored expansion, Day 18b --------------------------------------------
#
# THE BUG THESE EXIST FOR. "WHAT IS THE ADMISSION POLICY" put the one chunk describing the
# admission process at rank 7 with a score of 0.588 — under the floor and outside top_k.
# Gemini was handed a refunds table and two page headers, correctly reported that they did
# not answer the question, and the whole thing was reported to the user as the cloud model
# being broken. See retrieval.py decision 5 for the three fixes that were measured and
# rejected before this one.

ANCHOR = uuid4()
OTHER = uuid4()
THIRD = uuid4()


def test_a_near_miss_from_the_top_hits_document_is_admitted():
    """The exact shape of the live failure, in miniature: a strong hit and a slightly weak
    one in the SAME document, with the weak one carrying the actual answer."""
    rows = [
        row("refund rules", 0.68, ANCHOR),
        row("the admission process", 0.588, ANCHOR),
    ]
    retrieved, texts, _c, _d, expanded = rank_rows(
        rows, top_k=5, min_score=0.60, anchor_min_score=0.55)

    assert len(retrieved) == 2
    assert "the admission process" in texts
    assert expanded == 1


def test_a_near_miss_from_a_DIFFERENT_document_is_still_rejected():
    """The half that keeps this from being "lower the floor" with extra steps.

    Measured over 13 questions, admitting every near miss scored 30 unrelated chunks
    against anchored expansion's 17. A chunk from another document that cannot clear the
    real floor is exactly the noise BACKLOG 20 is about.
    """
    rows = [
        row("refund rules", 0.68, ANCHOR),
        row("an unrelated marking spreadsheet", 0.588, OTHER),
    ]
    retrieved, texts, _c, _d, expanded = rank_rows(
        rows, top_k=5, min_score=0.60, anchor_min_score=0.55)

    assert len(retrieved) == 1
    assert "an unrelated marking spreadsheet" not in texts
    assert expanded == 0


def test_expansion_cannot_fire_when_nothing_cleared_the_real_floor():
    """THE SAFETY PROPERTY, and the reason this rule cannot cause a false answer.

    An unanswerable question retrieves nothing above min_score, so there is no anchor and
    no expansion — `insufficient_context` is reached exactly as before. The three
    unanswerable golden questions peak at 0.4220, 0.5175 and 0.4894, all under the 0.55
    anchor floor as well, but this test does not rely on that: it asserts the mechanism,
    which holds whatever the scores are.
    """
    rows = [row("almost relevant", 0.59, ANCHOR), row("also almost", 0.57, ANCHOR)]

    retrieved, texts, _c, _d, expanded = rank_rows(
        rows, top_k=5, min_score=0.60, anchor_min_score=0.55)

    assert retrieved == [] and texts == [] and expanded == 0


def test_the_anchor_is_the_best_scoring_document_not_any_admitted_one():
    """Two documents clear the floor. The expansion must follow the TOP one — following
    the other would spend the budget inside whichever document happened to sort second."""
    rows = [
        row("best hit", 0.70, ANCHOR),
        row("second document", 0.62, OTHER),
        row("near miss in the runner-up", 0.57, OTHER),
        row("near miss in the anchor", 0.56, ANCHOR),
    ]
    _r, texts, _c, _d, expanded = rank_rows(
        rows, top_k=5, min_score=0.60, anchor_min_score=0.55)

    assert "near miss in the anchor" in texts
    assert "near miss in the runner-up" not in texts
    assert expanded == 1


def test_expansion_never_pushes_out_a_chunk_that_cleared_the_floor():
    """Ordering, asserted because it is silent when wrong. Expanded chunks score BELOW the
    floor by definition, so they must sort after everything that cleared it — if top_k
    truncates, it must truncate the weakest, never a legitimate hit."""
    rows = [row(f"real hit {i}", 0.70 - i / 100, ANCHOR) for i in range(3)]
    rows.append(row("near miss", 0.56, ANCHOR))

    retrieved, texts, _c, _d, expanded = rank_rows(
        rows, top_k=3, min_score=0.60, anchor_min_score=0.55)

    assert texts == ["real hit 0", "real hit 1", "real hit 2"]
    assert len(retrieved) == 3
    assert expanded == 0, "a near miss cut by top_k did not change what the model saw"


def test_without_an_anchor_floor_the_gate_is_exactly_the_old_threshold():
    """The feature is opt-in at the call site. Passing nothing must reproduce Day 6
    behaviour byte for byte, so the only thing that can change behaviour is configuration.
    """
    rows = [row("over", 0.70, ANCHOR), row("under", 0.58, ANCHOR)]

    retrieved, texts, _c, _d, expanded = rank_rows(rows, top_k=5, min_score=0.60)

    assert texts == ["over"] and len(retrieved) == 1 and expanded == 0


def test_an_anchor_floor_above_min_score_is_ignored_rather_than_inverting_the_gate():
    """A misconfiguration that would otherwise be interesting: anchor_min_score ABOVE
    min_score describes an empty band. It must be a no-op, not a stricter filter on the
    anchor document, because "chunks from the best document are held to a HIGHER standard"
    is the opposite of the intent and nobody would read it in a config file."""
    rows = [row("over", 0.70, ANCHOR), row("mid", 0.62, ANCHOR)]

    _r, texts, _c, _d, expanded = rank_rows(
        rows, top_k=5, min_score=0.60, anchor_min_score=0.65)

    assert texts == ["over", "mid"] and expanded == 0


def test_the_floor_clears_the_measured_unanswerable_ceiling():
    """THE CALIBRATION GUARD, and it moved on Day 19.

    `min_score` is what produces insufficient_context, so it is the number that decides
    whether the service answers questions the corpus cannot answer. Measured ceiling across
    the unanswerable golden questions: 0.5175 ("Who won the 1998 FIFA World Cup final?").
    benchmarks/27_retrieval_floor.py shows that question retrieving at 0.50 and 0.51, and
    not at 0.52 or above.

    This used to assert the ANCHOR floor cleared that ceiling, which was belt-and-braces
    from when anchored expansion was new. It is no longer true — the anchor floor is 0.50,
    below the ceiling — and it no longer needs to be: expansion cannot run at all unless
    something already cleared `min_score`, which an unanswerable question never does. That
    mechanism is asserted by
    `test_expansion_cannot_fire_when_nothing_cleared_the_real_floor`, which is a statement
    about behaviour rather than about two numbers happening to be ordered.
    """
    unanswerable_ceiling = 0.5175

    assert settings.default_min_score > unanswerable_ceiling, (
        "the floor must stay above the best score an unanswerable question reaches, or "
        "insufficient_context stops being reachable")
    assert settings.anchor_min_score < settings.default_min_score, (
        "an anchor floor at or above min_score describes an empty band and silently "
        "disables anchored expansion")


# --- the document limit, Day 19 ---------------------------------------------
#
# Lowering the floor 0.60 -> 0.55 recovered every reported failure and DOUBLED the
# off-document noise, 14 -> 29 chunks. Capping the answer to the best-matching document
# removed all of it: 14/14 hits, 0 off-document chunks, fewer tokens than the 0.60 setting
# it replaced. The embedder picks the right DOCUMENT reliably and fails at ranking WITHIN
# one, so the limit plays to the half that works.

def test_only_the_best_matching_document_contributes():
    rows = [
        row("the right passage", 0.70, ANCHOR),
        row("an unrelated bibliography entry", 0.68, OTHER),
        row("more of the right document", 0.62, ANCHOR),
    ]

    _r, texts, _c, _d, _e = rank_rows(rows, top_k=7, min_score=0.55, max_documents=1)

    assert texts == ["the right passage", "more of the right document"]


def test_the_document_is_chosen_by_the_best_chunk_not_by_chunk_count():
    """A document with many mediocre chunks must not outvote the one holding the single
    best passage. `collapsed` is score-ordered, so the first document seen IS the top hit's."""
    rows = [row("the single best passage", 0.72, ANCHOR)]
    rows += [row(f"mediocre {i}", 0.60 - i / 1000, OTHER) for i in range(5)]

    _r, texts, _c, _d, _e = rank_rows(rows, top_k=7, min_score=0.55, max_documents=1)

    assert texts == ["the single best passage"]


def test_raising_the_limit_admits_that_many_documents():
    """Configurable rather than hard-coded: a cross-document question is a real shape this
    corpus does not happen to contain, and the setting is how that case is served."""
    rows = [row("first", 0.70, ANCHOR), row("second", 0.68, OTHER),
            row("third", 0.66, THIRD)]

    _r, texts, _c, _d, _e = rank_rows(rows, top_k=7, min_score=0.55, max_documents=2)

    assert texts == ["first", "second"]


def test_zero_disables_the_limit_entirely():
    """The escape hatch, and the behaviour every test written before Day 19 assumes."""
    rows = [row("first", 0.70, ANCHOR), row("second", 0.68, OTHER)]

    _r, texts, _c, _d, _e = rank_rows(rows, top_k=7, min_score=0.55, max_documents=0)

    assert texts == ["first", "second"]


def test_the_limit_cannot_resurrect_a_chunk_below_the_floor():
    """It narrows what is admitted; it never widens it. A document surviving the cap does
    not get its sub-floor chunks admitted as a side effect."""
    rows = [row("over the floor", 0.70, ANCHOR), row("under the floor", 0.40, ANCHOR)]

    _r, texts, _c, _d, _e = rank_rows(rows, top_k=7, min_score=0.55, max_documents=1)

    assert texts == ["over the floor"]


def test_the_limit_leaves_an_empty_result_empty():
    """An unanswerable question admits nothing, and the cap must not change that — it is
    applied to what already cleared the floor, not to the candidates."""
    rows = [row("almost", 0.52, ANCHOR), row("also almost", 0.51, OTHER)]

    retrieved, texts, _c, _d, _e = rank_rows(rows, top_k=7, min_score=0.55, max_documents=1)

    assert retrieved == [] and texts == []


# --- the margin guard, Day 19 -----------------------------------------------
#
# Lowering the floor to 0.55 admitted "what is university policy" (0.5926, genuine) and
# "Follow up on finance" (0.5925, an aviation deck for a user with no finance document).
# ONE TEN-THOUSANDTH APART — no floor separates them. What does is how far the best
# document leads the second: 0.0428 against 0.0047.

def test_a_marginal_match_with_no_clear_document_winner_is_refused():
    """The "Follow up on finance" shape: several documents equally close, none of them the
    answer. Before the margin guard this returned seven chunks of an unrelated deck and the
    model wrote something from them."""
    rows = [row("aviation", 0.5925, ANCHOR), row("maintenance", 0.5878, OTHER),
            row("more aviation", 0.5830, ANCHOR)]

    retrieved, texts, _c, _d, _e = rank_rows(
        rows, top_k=7, min_score=0.55, confident_score=0.60, min_document_margin=0.02)

    assert retrieved == [] and texts == []


def test_a_marginal_match_with_a_clear_winner_is_kept():
    """The "what is university policy" shape: a weak score, but one document plainly ahead.
    This is the case the lower floor exists for."""
    rows = [row("the prospectus", 0.5926, ANCHOR), row("something else", 0.5498, OTHER)]

    _r, texts, _c, _d, _e = rank_rows(
        rows, top_k=7, min_score=0.55, confident_score=0.60, min_document_margin=0.02)

    assert texts == ["the prospectus"]


def test_a_confident_match_is_never_refused_for_a_narrow_margin():
    """Above `confident_score` the match stands on its own. "tell me about ai safety"
    scores 0.7120 with a margin of 0.0148 — two documents that both mention AI is not a
    reason to answer nothing."""
    rows = [row("the right passage", 0.7120, ANCHOR), row("also mentions it", 0.6972, OTHER)]

    _r, texts, _c, _d, _e = rank_rows(
        rows, top_k=7, min_score=0.55, confident_score=0.60, min_document_margin=0.02)

    assert "the right passage" in texts


def test_the_margin_is_measured_against_documents_below_the_floor_too():
    """The runner-up is usually BELOW the floor — that is what makes it a runner-up. Using
    only admitted chunks would see one document, compute an enormous margin, and admit
    everything."""
    rows = [row("marginal", 0.5600, ANCHOR), row("just under", 0.5550, OTHER)]

    retrieved, _t, _c, _d, _e = rank_rows(
        rows, top_k=7, min_score=0.55, confident_score=0.60, min_document_margin=0.02)

    assert retrieved == [], "the sub-floor document still counts as the runner-up"


def test_the_guard_is_off_when_no_confident_score_is_configured():
    """Opt-in at the call site, so every test written before Day 19 still describes the
    behaviour it was written for."""
    rows = [row("marginal", 0.5600, ANCHOR), row("close behind", 0.5590, OTHER)]

    _r, texts, _c, _d, _e = rank_rows(rows, top_k=7, min_score=0.55)

    assert texts == ["marginal", "close behind"]
