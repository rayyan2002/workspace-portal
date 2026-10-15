"""Correct a misspelled question against the corpus's own vocabulary. Day 19.

WHY THIS EXISTS. Reported from real use: `tell me about ai saftey` answered "I couldn't
find anything in your documents" while AI_safety.pdf sat in the corpus with 81 chunks. The
misspelling scores 0.5355 against a 0.60 floor; the correct spelling scores 0.7120. One
letter costs 0.177, because `bge-small` compares token sequences and has no notion of
spelling — `saftey` does not NEARLY match, it lands somewhere else entirely.

Users type at the speed of thought. This will keep happening.

THE RULE THAT MAKES IT SAFE: this runs ONLY after retrieval has already returned nothing,
and its result is kept ONLY if the corrected question then retrieves something. A question
that worked is never touched, and a correction that does not help is discarded. The failure
reported to the user in that case is the original one, not a confusing report about a word
they did not type.

    "What is the capital of France?"  ->  France->range  ->  still nothing  ->  no harm

That is a real measured case: `France` is absent from this corpus, so it gets "corrected"
to nonsense. It cost nothing because the corrected query failed too, and the original
answer stands.

EDIT DISTANCE, NOT TRIGRAM SIMILARITY, and that was measured rather than assumed. A
transposition destroys trigrams: `safety` and `saftey` share only `saf`, scoring 0.27 —
below any floor that would not also admit junk. The same four typos are all Levenshtein 2:

    saftey/safety  admissoin/admission  positinos/positions  degradatoin/degradation

A trigram pass over the CHUNKS was measured first and rejected: the scores of a true
recovery (0.478) and a wrong-document match (0.467) are 0.011 apart, so no threshold
separates them. Correcting the QUERY and then running the ordinary vector path keeps every
guarantee that path already has — the floor, anchored expansion, the noise profile.
"""
import logging
import re
import time

import psycopg

from app.config import settings

log = logging.getLogger(__name__)

#: Words shorter than this are left alone. "teh" is a typo but so is half the alphabet at
#: three characters, and a wrong correction on a short word changes the question's meaning.
_MIN_WORD = 4

#: The most edits allowed between a typed word and a corpus word. Two covers a single
#: transposition (which is two edits without Damerau) and a doubled or dropped letter.
#: Three starts matching unrelated words of the same length.
_MAX_EDITS = 2

_TOKEN = re.compile(r"[A-Za-z]+|[^A-Za-z]+")

_VOCABULARY: dict[str, int] | None = None
_LOADED_AT = 0.0

#: How long the cached vocabulary is trusted. Documents are added while the service runs,
#: so a vocabulary loaded at startup would slowly stop containing the words users ask about.
_TTL_SECONDS = 600


def _load_vocabulary(dsn: str | None = None) -> dict[str, int]:
    """Every word in the corpus, with how often it appears. One SELECT, cached.

    Frequency is the tie-break: when two corpus words are the same distance from what was
    typed, the one that actually appears more is the better guess.

    SELECT only — rule R1. This reads the chunk table and writes nothing, not even a
    temporary table.
    """
    global _VOCABULARY, _LOADED_AT
    now = time.monotonic()
    if _VOCABULARY is not None and now - _LOADED_AT < _TTL_SECONDS:
        return _VOCABULARY

    with psycopg.connect(dsn or settings.dsn) as conn:
        rows = conn.execute(
            """
            SELECT lower(w) AS word, count(*) AS n
            FROM document_chunks c,
                 LATERAL regexp_split_to_table(c.text, '[^A-Za-z]+') AS w
            WHERE length(w) >= %s
            GROUP BY lower(w)
            """,
            (_MIN_WORD,),
        ).fetchall()

    _VOCABULARY = {word: count for word, count in rows}
    _LOADED_AT = now
    log.info("spelling vocabulary loaded: %d distinct words", len(_VOCABULARY))
    return _VOCABULARY


def _edits_within(a: str, b: str, limit: int) -> int | None:
    """Levenshtein distance, abandoned as soon as it exceeds `limit`.

    Bounded deliberately: the answer "more than 2" is as useful as the exact number and is
    reached far sooner, and this runs against several thousand candidate words.
    """
    if abs(len(a) - len(b)) > limit:
        return None
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(
                previous[j] + 1,
                current[j - 1] + 1,
                previous[j - 1] + (ca != cb),
            ))
        if min(current) > limit:
            return None
        previous = current
    return previous[-1] if previous[-1] <= limit else None


def correct(question: str, dsn: str | None = None) -> tuple[str, list[tuple[str, str]]]:
    """Return the question with unknown words replaced, and what was replaced.

    A word already in the corpus is never touched — if the user typed a word the documents
    contain, it is not a typo however unusual it looks.

    :return: ``(corrected_question, [(typed, replacement), ...])``. An empty list means
             nothing was changed and the caller should not bother retrying.
    """
    try:
        vocabulary = _load_vocabulary(dsn)
    except Exception:  # noqa: BLE001 — a spelling aid must never break a served request
        log.exception("could not load the spelling vocabulary; leaving the question alone")
        return question, []

    if not vocabulary:
        return question, []

    out: list[str] = []
    changed: list[tuple[str, str]] = []
    for token in _TOKEN.findall(question):
        lowered = token.lower()
        if not token.isalpha() or len(token) < _MIN_WORD or lowered in vocabulary:
            out.append(token)
            continue

        best: tuple[int, int, str] | None = None   # (distance, -frequency, word)
        for candidate, frequency in vocabulary.items():
            distance = _edits_within(lowered, candidate, _MAX_EDITS)
            if distance is None:
                continue
            key = (distance, -frequency, candidate)
            if best is None or key < best:
                best = key

        if best is None:
            out.append(token)
        else:
            out.append(best[2])
            changed.append((token, best[2]))

    return "".join(out), changed
