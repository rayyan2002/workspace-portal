"""Day 6: question in, ranked chunks out.

FOUR DECISIONS, EACH MEASURED OR MANDATED.

1. THE FILTER IS APPLIED UNCONDITIONALLY.
   `document_id = ANY(%s::uuid[])` runs on every request, including when the allow-list
   is empty — `ANY('{}')` matches zero rows, verified against the live table. There is
   deliberately no `if allowed_document_ids:` short-circuit, not even a safe one that
   returns early: that branch is how an empty list becomes a search across every user's
   documents, and the cheapest way to never write it is to have no place it could go.

2. SCORE DIRECTION IS CONVERTED ONCE, AT THE SQL BOUNDARY.
   pgvector's `<#>` returns NEGATIVE inner product (lower = more similar); the contract
   publishes `score` as cosine SIMILARITY (higher = better). `-(embedding <#> q)` does
   both jobs in one place: ORDER BY uses the raw operator so the index (when one exists)
   can be used, and the SELECT list negates it. Converting anywhere else would mean two
   conventions in one process.

3. NEAR-DUPLICATE COLLAPSING, ON EXACT TEXT HASH.
   Mandatory, not an optimisation. Measured: 170/177 chunks have a byte-identical twin,
   and "What were the quarterly financial results?" returns top5 = [0.700 x 5] — ONE
   passage, five times, filling the entire context window with a single fact. Collapsing
   keeps the highest-ranked row per distinct text and drops the rest.
   Exact hash is the deliberate choice over score-similarity clustering: it cannot merge
   two genuinely different passages that happen to score alike. It therefore does NOT
   catch the seeded stubs that match each other at 0.857 while sharing no text — that is
   a corpus problem for Day 13, not a retrieval trick.

4. THE THRESHOLD IS APPLIED IN CODE, BEFORE ANY MODEL IS CALLED.
   `insufficient_context` is a retrieval decision. Day 6 raised the default from 0.35 to
   0.60 because 0.35 sat below the noise floor — see config.default_min_score.

6. ONE DOCUMENT ANSWERS ONE QUESTION, by default.
   `max_documents` caps how many documents may contribute. Measured on Day 19 while
   lowering the floor from 0.60 to 0.55: the lower floor recovered every reported failure
   and doubled off-document noise, 14 -> 29 chunks. Capping at the best-matching document
   removed ALL of it — 14/14 hits, 0 off-document chunks, and fewer prompt tokens than the
   0.60 setting it replaced.

   It works for the same reason decision 5 does: this embedder picks the right DOCUMENT
   reliably (9/9 measured) and fails at ranking WITHIN one. The noise was never the
   threshold; it was other documents. See config.max_documents for the risk.

5. ANCHORED EXPANSION: THE TOP HIT NAMES A DOCUMENT, AND THE REST OF THE BUDGET IS SPENT
   THERE FIRST. Day 18b, and the reason is a bug rather than a theory.

   "WHAT IS THE ADMISSION POLICY" put the one chunk describing the admission process at
   rank 7 with 0.588, under a 0.60 floor and outside a top_k of 5. The model was handed a
   refunds table and two page headers and correctly reported that they did not answer the
   question — a retrieval failure that looked exactly like a model failure.

   FOUR FIXES WERE MEASURED AND THREE WERE REJECTED, which is why this one is here:

     - Moving the floor CANNOT work. The same floor was measured as too LOW two days
       earlier (BACKLOG 20: noise at 0.6144 under a top of 0.6238) and is too HIGH here by
       0.012. One global number cannot do both jobs.
     - A relative floor (ratio to the top score) cannot either: the noise sits at 0.985 of
       its top hit and the wanted chunk at 0.862 of its own. Any ratio admitting one admits
       the other.
     - A cross-encoder reranker (ms-marco-MiniLM-L-6-v2 over 20 candidates) made it WORSE,
       moving the wanted chunk from rank 7 to rank 8, and cost 2.1s per question.
     - Smaller chunks made it worse too: re-chunking the whole corpus at 256/192/128 tokens
       and re-calibrating the floor for each scored 8/10, 7/10 and 7/10 against 9/10 today.

   What works is cheap and specific: the highest-scoring chunk identifies a document, and
   chunks from THAT document are admitted down to a lower floor. Measured over 13
   questions, against simply dropping the floor and widening top_k to reach the same 10/10:

                                    targets   noise chunks   tokens/question
       today        0.60 / k=5         9/10             14              1180
       flat         0.58 / k=7        10/10             30              1940
       anchored     0.60 / k=7        10/10             17              1661

   IT CANNOT MANUFACTURE AN ANSWER OUT OF NOTHING, which is the property that makes it safe
   rather than merely effective: expansion only runs when something ALREADY cleared the
   real floor. All three unanswerable golden questions top out at 0.52, nothing is
   admitted, and `insufficient_context` is reached exactly as before. Held by a test.
"""
import hashlib
import logging
import time
from dataclasses import dataclass, field, replace
from uuid import UUID

import psycopg

from app.config import settings
from app.schemas import ConversationTurn, RetrievedChunk
from app.spelling import correct as correct_spelling

log = logging.getLogger(__name__)

# ORDER BY uses the bare operator (index-usable); the SELECT list negates it into the
# similarity the contract publishes. Same expression, one conversion.
_OPENING_SQL = """
SELECT c.id, c.document_id, c.text, -(c.embedding <#> %(q)s::vector) AS score
FROM document_chunks c
WHERE c.document_id = %(doc)s::uuid
ORDER BY c.ordinal
LIMIT %(lim)s
"""
"""ORDER BY ORDINAL, NOT BY SCORE — the whole point of the summarise path.

Measured on AI_safety.pdf, 81 chunks. Asked "what is this paper about", the ABSTRACT ranks
34th by similarity; asked "summarise abstract of ai-safety research paper" it ranks 7th and
what outranks it is the bibliography, because a reference list is the densest concentration
of a paper's own subject words anywhere in the document.

That is not a threshold that needs moving. A question about a document AS A WHOLE has no
content words to discriminate on — every chunk is equally "about" the paper — so similarity
has nothing to rank by. Position does: chunk 1 is the title, chunk 2 the abstract.

The score is still computed and reported so the trace stays comparable with the similarity
path, but it does not decide the order and it does not gate admission.
"""

_SEARCH_SQL = """
SELECT c.id, c.document_id, c.text, -(c.embedding <#> %(q)s::vector) AS score
FROM document_chunks c
WHERE c.document_id = ANY(%(ids)s::uuid[])
ORDER BY c.embedding <#> %(q)s::vector
LIMIT %(lim)s
"""


@dataclass(frozen=True)
class RetrievalOutcome:
    """Everything the trace needs, computed once."""

    retrieved: list[RetrievedChunk]
    texts: list[str]                    # parallel to `retrieved`; Day 7 prompts need these
    candidates_before_threshold: int
    collapsed_duplicates: int
    embed_ms: int
    search_ms: int
    retried_with_history: bool = False
    spelling_corrections: list[tuple[str, str]] = field(default_factory=list)
    """Words replaced before the search that produced this result, as (typed, used).

    Non-empty ONLY when the original question retrieved nothing AND the corrected one
    retrieved something. The UI shows it so a user is told what was assumed rather than
    silently answered about a different word."""

    best_rejected_score: float | None = None
    """The highest score that did NOT clear the floor, when nothing cleared it.

    THE NUMBER THAT TURNS A DEAD END INTO ADVICE. With no candidates admitted the trace
    said only "0 retrieved", so a question that missed by 0.065 and one about a subject the
    corpus has never heard of were indistinguishable — and the user was told, identically,
    that their documents do not cover it and they should upload one.

    Measured on the real corpus: "tell me about ai saftey" scores 0.5355 against a 0.60
    floor while "tell me about ai safety" scores 0.7120. One letter. The document was there
    the whole time, and the only honest reply names the near miss.

    None when the query matched no rows at all, which is a different thing from matching
    badly."""

    query_vector: list[float] | None = None
    """Kept so a second pass over the same question does not re-embed it. Internal to
    this service — it never reaches a schema or a log."""
    anchor_expanded: int = 0
    """How many chunks were admitted ONLY by anchored expansion. Zero means the gate
    behaved exactly as a plain threshold, which is the common case — so a non-zero value
    marks the requests where this rule actually changed what the model saw."""


def _vector_literal(values: list[float]) -> str:
    """pgvector's text input format. Not a Python list literal by coincidence."""
    return "[" + ",".join(repr(float(v)) for v in values) + "]"


def rank_rows(
    rows: list[tuple[UUID, UUID, str, float]],
    top_k: int,
    min_score: float,
    anchor_min_score: float | None = None,
    max_documents: int = 0,
    confident_score: float | None = None,
    min_document_margin: float = 0.0,
) -> tuple[list[RetrievedChunk], list[str], int, int, int]:
    """Collapse, threshold, truncate, rank. PURE — no database, no model.

    Separated from `retrieve` so the rules that decide what a user sees are testable
    without Postgres running and without loading 130MB of weights. `rows` must already be
    in descending score order, which is what the SQL guarantees.
    """
    # Keep the highest-ranked occurrence of each distinct text. Rows arrive in score
    # order, so "first seen" IS "best scoring" and no re-sort is needed.
    seen: set[str] = set()
    collapsed: list[tuple[UUID, UUID, str, float]] = []
    duplicates = 0
    for chunk_id, document_id, text, score in rows:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest in seen:
            duplicates += 1
            continue
        seen.add(digest)
        collapsed.append((chunk_id, document_id, text, score))

    # Counted AFTER collapsing and BEFORE the threshold, which is the only position that
    # distinguishes the three outcomes the trace exists to tell apart: nothing matched the
    # filter, everything was a duplicate, or everything scored too low.
    candidates_before_threshold = len(collapsed)

    admitted = [c for c in collapsed if c[3] >= min_score]

    # THE MARGIN GUARD — decision 7, and what makes a 0.55 floor SAFE rather than merely
    # generous. A top score in the marginal band must be backed by a clear document winner;
    # without one the question is one the corpus cannot answer, however close it came.
    #
    # The comparison uses `collapsed` rather than `admitted` on purpose: the second-best
    # document's score is the thing being measured, and it is usually below the floor.
    if admitted and confident_score is not None and admitted[0][3] < confident_score:
        best_per_document: dict[UUID, float] = {}
        for _chunk_id, document_id, _text, score in collapsed:
            if document_id not in best_per_document:   # score-ordered, so first IS best
                best_per_document[document_id] = score
        ranked_documents = sorted(best_per_document.values(), reverse=True)
        runner_up = ranked_documents[1] if len(ranked_documents) > 1 else 0.0
        if ranked_documents[0] - runner_up < min_document_margin:
            admitted = []

    # THE DOCUMENT LIMIT — decision 6, and what makes a 0.55 floor affordable.
    #
    # Applied BEFORE anchored expansion and before top_k, because it changes which chunks
    # are candidates rather than how many survive. `collapsed` is score-ordered, so the
    # documents are taken in the order their best chunk appeared: the top hit's document
    # first, which is the one the embedder is reliable about.
    if max_documents and admitted:
        allowed: list[UUID] = []
        for _chunk_id, document_id, _text, _score in admitted:
            if document_id not in allowed:
                if len(allowed) >= max_documents:
                    continue
                allowed.append(document_id)
        admitted = [c for c in admitted if c[1] in allowed]

    # ANCHORED EXPANSION — decision 5 in the module docstring.
    #
    # The guard is `if admitted`, and it is the whole safety argument: with nothing over
    # the real floor there is no anchor, no expansion, and `insufficient_context` is
    # reached exactly as it was before. A rule that can only widen an already-good result
    # cannot invent one.
    expanded = 0
    if admitted and anchor_min_score is not None and anchor_min_score < min_score:
        # The best-scoring chunk names the document. `collapsed` is score-ordered, so
        # admitted[0] IS the global best — the anchor is never a second-choice document.
        anchor_document = admitted[0][1]
        near_misses = [
            c for c in collapsed
            if c[1] == anchor_document and anchor_min_score <= c[3] < min_score
        ]
        if near_misses:
            admitted = sorted(admitted + near_misses, key=lambda c: -c[3])
            # Counted AFTER truncation: a near-miss that top_k cuts anyway did not change
            # what the model saw, and reporting it would overstate what this rule did.
            expanded = sum(1 for c in admitted[:top_k] if c in near_misses)

    kept = admitted[:top_k]
    retrieved = [
        RetrievedChunk(rank=i, chunk_id=chunk_id, document_id=document_id, score=float(score))
        for i, (chunk_id, document_id, _text, score) in enumerate(kept, start=1)
    ]
    return retrieved, [c[2] for c in kept], candidates_before_threshold, duplicates, expanded


def search_text_with_history(
    question: str,
    history: list[ConversationTurn],
    turns: int,
) -> str | None:
    """The retrieval query for a follow-up that cannot stand on its own.

    Returns None when there is no earlier USER turn to lean on.

    Only user turns are used. An earlier ASSISTANT turn is this system's own output, and
    feeding it back into the query embeds whatever the model happened to say last —
    including, on this corpus, a single terse formula. The question is what the user is
    asking about; the answer is what we already got wrong.
    """
    earlier = [t.content for t in history if t.role == "user"][-turns:]
    if not earlier:
        return None
    return " ".join([*earlier, question])


def retrieve(
    embed_query,
    question: str,
    allowed_document_ids: list[UUID],
    top_k: int,
    min_score: float,
    dsn: str | None = None,
    history: list[ConversationTurn] | None = None,
) -> RetrievalOutcome:
    """`embed_query` is injected so tests never load a 130MB model to check SQL wiring.

    History is a FALLBACK, not a default. Measured on the real corpus: standalone questions
    retrieve fine alone (1-5 chunks) and anaphoric follow-ups score exactly nothing —
    "tell me in detail", "and?" and "tell me more" all returned 0. So the previous user turn
    is prepended only when the question alone clears the threshold with nothing, which costs
    one extra ~32ms round trip on the follow-up path and nothing at all on the normal one.

    Prepending unconditionally was the first design and was measurably worse: on a topic
    change ("...adbms ... what is the fleet size") the stale topic took one of five slots,
    and an irrelevant chunk in the context is exactly what produces a citation to it.
    """
    outcome = _search(embed_query, question, allowed_document_ids, top_k, min_score, dsn)
    if outcome.retrieved:
        return outcome

    # SPELLING, BEFORE HISTORY. A typo is the likelier explanation for retrieving nothing
    # than a follow-up needing its topic restored, and it is the cheaper thing to rule out:
    # the vocabulary is cached in memory, so this costs one re-embed and one search only
    # when the first attempt already failed.
    #
    # The result is kept ONLY if it actually retrieves something. A correction that does not
    # help is discarded and the ORIGINAL failure is reported, so a user is never told about
    # a word they did not type. See app/spelling.py.
    # `candidates_before_threshold` is the guard: zero means the allow-list matched no rows
    # at all, so no spelling of the question could have helped and the vocabulary load would
    # be pure waste. A typo shows up as candidates that exist but score too low.
    corrected, changes = (
        correct_spelling(question, dsn)
        if outcome.candidates_before_threshold else (question, [])
    )
    if changes:
        respelled = _search(embed_query, corrected, allowed_document_ids, top_k, min_score, dsn)
        if respelled.retrieved:
            log.info("nothing cleared min_score; retrying with %d word(s) corrected",
                     len(changes))
            return replace(
                respelled,
                spelling_corrections=changes,
                embed_ms=outcome.embed_ms + respelled.embed_ms,
                search_ms=outcome.search_ms + respelled.search_ms,
            )

    if not history:
        return outcome

    fallback_text = search_text_with_history(question, history, settings.history_turns_for_retrieval)
    if fallback_text is None:
        return outcome

    log.info("nothing cleared min_score; retrying with the previous user turn prepended")
    retried = _search(embed_query, fallback_text, allowed_document_ids, top_k, min_score, dsn)
    return replace(
        retried,
        retried_with_history=True,
        # Both passes are real work the user waited for, so the trace reports the total
        # rather than quietly hiding the first attempt.
        embed_ms=outcome.embed_ms + retried.embed_ms,
        search_ms=outcome.search_ms + retried.search_ms,
    )


def _search(
    embed_query,
    question: str,
    allowed_document_ids: list[UUID],
    top_k: int,
    min_score: float,
    dsn: str | None,
) -> RetrievalOutcome:
    t0 = time.perf_counter()
    query_vector = embed_query(question)
    embed_ms = int((time.perf_counter() - t0) * 1000)

    # Over-fetch: collapsing removes rows AFTER ranking, so asking for exactly top_k
    # would return fewer than top_k whenever duplicates are present — which, on this
    # corpus, is almost always.
    limit = top_k * settings.overfetch_factor

    t1 = time.perf_counter()
    with psycopg.connect(dsn or settings.dsn) as conn:
        rows = conn.execute(
            _SEARCH_SQL,
            {
                "q": _vector_literal(query_vector),
                # Unconditional. Empty list -> ANY('{}') -> zero rows, no branch.
                "ids": [str(d) for d in allowed_document_ids],
                "lim": limit,
            },
        ).fetchall()
    search_ms = int((time.perf_counter() - t1) * 1000)

    retrieved, texts, candidates_before_threshold, duplicates, expanded = rank_rows(
        rows, top_k, min_score, settings.anchor_min_score, settings.max_documents,
        settings.confident_score, settings.min_document_margin,
    )

    log.info(
        "retrieved %d/%d candidates (%d duplicates collapsed, min_score=%.2f%s) in %dms",
        len(retrieved), candidates_before_threshold, duplicates, min_score,
        f", {expanded} by anchored expansion" if expanded else "",
        embed_ms + search_ms,
    )
    # `rows` is score-ordered by the SQL, so the first is the best the corpus could do.
    # Only meaningful when nothing was admitted; otherwise the admitted scores say it.
    best_rejected = float(rows[0][3]) if rows and not retrieved else None

    return RetrievalOutcome(
        retrieved=retrieved,
        texts=texts,
        best_rejected_score=best_rejected,
        candidates_before_threshold=candidates_before_threshold,
        collapsed_duplicates=duplicates,
        embed_ms=embed_ms,
        search_ms=search_ms,
        query_vector=query_vector,
        anchor_expanded=expanded,
    )


def document_opening(
    query_vector: list[float],
    document_id: UUID,
    limit: int,
    dsn: str | None = None,
) -> tuple[list[RetrievedChunk], list[str]]:
    """The first `limit` chunks of one document, in document order. Day 18b.

    THE OTHER HALF OF THE SUMMARISE PATH. `_search` answers "which passages match this
    question"; this answers "how does this document begin", which is the question a
    request to summarise is actually asking. See `_OPENING_SQL` for the measurement.

    THE DOCUMENT IS CHOSEN BY SIMILARITY AND ONLY ITS CONTENTS BY POSITION. Picking the
    file is exactly the job similarity does well — measured across four phrasings of the
    same request, including "what is this paper about", the top-scoring chunk named the
    right document every time (0.632 to 0.726). It was never the file that was wrong.

    Nothing here can admit a document the caller has not already cleared: `document_id`
    comes from a chunk that passed the allow-list filter and the score floor in `_search`,
    so this is a second read of material already authorised rather than a new search.
    """
    with psycopg.connect(dsn or settings.dsn) as conn:
        rows = conn.execute(
            _OPENING_SQL,
            {
                "q": _vector_literal(query_vector),
                "doc": str(document_id),
                "lim": limit,
            },
        ).fetchall()

    retrieved = [
        RetrievedChunk(rank=i, chunk_id=chunk_id, document_id=doc_id, score=float(score))
        for i, (chunk_id, doc_id, _text, score) in enumerate(rows, start=1)
    ]
    return retrieved, [r[2] for r in rows]
