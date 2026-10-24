"""Find the document a rare query term names, when the vector search did not. Day 20.

WHY THIS EXISTS. Reported: `summarize features of swift` proposed summarising
`AI_Assessment_Nisum_Alpha_A_Zohaib_Ali_graded (1).csv`, while the one document in the
corpus containing the word "swift" — a Suzuki Swift guide, 26 occurrences — was not
retrieved at all. The service's own trace already said something was wrong: verdict
`weak_evidence`, suspect `retrieval`, best chunk 0.544 against a 0.55 floor, six of seven
chunks admitted only by anchored expansion after the wrong document had anchored.

IT IS NOT THE FLOOR, AND NOT THE WORD "summarize". Measured in benchmarks/29:

    swift                                       Suzuki  0.6123  rank 1
    summarize features of swift                 CSV     0.6179  Suzuki rank 10 (0.5146)
    features of swift        (no "summarize")   AI_safety       Suzuki rank  8
    summarize features of the training tracker  AI_safety 0.7139  tracker not even top

Dropping "summarize" does not fix it, and naming the training tracker outright still loses
to AI_safety.pdf. Generic scaffolding ("features of ...") dominates a short query's
embedding and outvotes the single token that identifies the document. bge-small compares
token sequences; it has no notion that "swift" is a name here.

WHAT MAKES A TERM IDENTIFYING: it appears in exactly ONE document, and appears there
REPEATEDLY. Document frequency alone was tried first and is not enough — on a 15-document
corpus ordinary English words reach df 1 by accident, and promoting on them BROKE the
project-setup golden question via the word `contain`. Occurrence count separates accident
from signal:

    swift 26    suzuki 21    aerotwin 42    admission 13   <- identify a document
    contain 2   adbms 1                                    <- do not

RESULT at a rescue floor of 0.50, over the golden set and every previously reported
failure: 3 fixed, 0 broken, 0 leaked onto unanswerable questions, 14 already correct and
left alone.

THE SAFETY PROPERTY is that this is a NO-OP unless the query contains such a term AND the
vector search picked a document that does not contain it. A question that already works is
never touched. Admission is still gated on a floor of its own, because reaching past what
the vector search surfaced is exactly where a rescue could start answering questions the
corpus cannot.

SELECT only — rule R1. This reads the chunk table and writes nothing.
"""
import logging
import re
import time
from uuid import UUID

import psycopg

from app.config import settings

log = logging.getLogger(__name__)

#: Shorter tokens identify nothing. "ai" alone would match half this corpus.
_MIN_TERM = 4

_TOKEN = re.compile(rf"[a-z]{{{_MIN_TERM},}}")

#: term -> (document ids containing it, total occurrences). Cached; see _TTL_SECONDS.
_INDEX: dict[str, tuple[frozenset[UUID], int]] | None = None
_LOADED_AT = 0.0

#: Documents are added while the service runs, so an index built at startup would slowly
#: stop knowing about the words users ask about. Same reasoning as spelling.py.
_TTL_SECONDS = 600


def _load_index(dsn: str | None = None) -> dict[str, tuple[frozenset[UUID], int]]:
    """Every corpus term with the documents holding it and how often it occurs.

    One SELECT, grouped in Postgres rather than in Python: the corpus is small today and
    this still beats pulling every chunk's text across the wire on each rebuild.
    """
    global _INDEX, _LOADED_AT
    now = time.monotonic()
    if _INDEX is not None and now - _LOADED_AT < _TTL_SECONDS:
        return _INDEX

    with psycopg.connect(dsn or settings.dsn) as conn:
        rows = conn.execute(
            """
            SELECT lower(w) AS term,
                   array_agg(DISTINCT c.document_id) AS documents,
                   count(*) AS occurrences
            FROM document_chunks c,
                 LATERAL regexp_split_to_table(c.text, '[^A-Za-z]+') AS w
            WHERE length(w) >= %s
            GROUP BY lower(w)
            """,
            (_MIN_TERM,),
        ).fetchall()

    _INDEX = {term: (frozenset(documents), int(occurrences))
              for term, documents, occurrences in rows}
    _LOADED_AT = now
    log.info("selectivity index loaded: %d distinct terms", len(_INDEX))
    return _INDEX


def selective_documents(question: str,
                        dsn: str | None = None) -> dict[str, frozenset[UUID]]:
    """Query terms that name exactly one document and recur inside it.

    Empty — the common case — means this question has nothing rare in it and every caller
    should leave the vector search alone.
    """
    index = _load_index(dsn)
    found: dict[str, frozenset[UUID]] = {}
    for term in set(_TOKEN.findall(question.lower())):
        entry = index.get(term)
        if entry is None:
            continue
        documents, occurrences = entry
        if (len(documents) <= settings.rare_term_max_documents
                and occurrences >= settings.rare_term_min_occurrences):
            found[term] = documents
    return found


#: Words that appear in questions as scaffolding, never as the name of a thing. Unlike the
#: corpus-term rules above this IS a hand-written list, because it is about the shape of a
#: QUESTION rather than about this corpus — "summarize" is scaffolding on any corpus, and
#: document frequency cannot see that.
_SCAFFOLDING = frozenset({
    "summarize", "summarise", "document", "documents", "abstract", "features", "feature",
    "what", "about", "tell", "give", "show", "this", "that", "from", "main", "points",
    "does", "your", "with", "used", "which", "into", "the", "and", "for", "are", "how",
})

_NAME_TOKEN = re.compile(r"[a-z]{3,}")

_FILENAMES: dict[UUID, frozenset[str]] | None = None
_FILENAMES_AT = 0.0


def _name_tokens(text: str) -> frozenset[str]:
    cleaned = text.replace("_", " ").replace("-", " ").replace(".", " ")
    return frozenset(w for w in _NAME_TOKEN.findall(cleaned.lower())
                     if w not in _SCAFFOLDING)


def _load_filenames(dsn: str | None = None) -> dict[UUID, frozenset[str]]:
    global _FILENAMES, _FILENAMES_AT
    now = time.monotonic()
    if _FILENAMES is not None and now - _FILENAMES_AT < _TTL_SECONDS:
        return _FILENAMES
    with psycopg.connect(dsn or settings.dsn) as conn:
        rows = conn.execute("SELECT id, filename FROM documents").fetchall()
    _FILENAMES = {document_id: _name_tokens(filename) for document_id, filename in rows}
    _FILENAMES_AT = now
    return _FILENAMES


def question_names_a_document(question: str, dsn: str | None = None) -> bool:
    """Cheap pre-check: does any question word appear in ANY document's filename?

    Lets the caller skip the extra per-document score query on the common question that
    names nothing. Filenames are cached, so this touches the database at most once per TTL.
    """
    asked = _name_tokens(question)
    return any(asked & tokens for tokens in _load_filenames(dsn).values())


def best_named_document(question: str, candidates, dsn: str | None = None):
    """Of `candidates`, the one whose FILENAME the question names best. None if no overlap.

    USED ONLY TO BREAK A TIE, and that restriction is the entire safety argument. Applied
    to all documents it picks the wrong one: "What technology stack is the final project
    built on?" matches `project_setup.txt` on the word "project" and overrides a correct
    answer. Restricted to documents already within `min_document_margin` of the top — where
    the vector score has, by definition, failed to decide — it fixed the reported case and
    broke nothing. Measured over the golden set: 1 fixed, 0 broken, 11 unchanged, and it
    never fired on an unanswerable question.
    """
    asked = _name_tokens(question)
    if not asked:
        return None
    filenames = _load_filenames(dsn)
    scored = [(len(asked & filenames.get(d, frozenset())), d) for d in candidates]
    best = max(scored, default=(0, None))
    return best[1] if best[0] > 0 else None
