"""Turn whatever the model said into something the contract can hold.

PARSE LENIENTLY, VALIDATE STRICTLY. Those are two separate jobs and conflating them is how
the Day 2 experiments went wrong four times.

Leniently, because the model does not obey the schema it is given. Asked for
`"cites": [1, 2]` it returned `[{"number": 1, "context": "[1]"}]` in 10 runs out of 10 —
valid JSON, improvised shape, every time. A strict parser reads that as "no citations" and
says so with total confidence. That is worse than a crash: it is a silent, confident zero.

Strictly, because a recovered number is still only a claim. Every number is checked against
the chunks that were actually shown, and anything else is dropped and recorded — never
guessed, never passed through. Same rule as Day 1: correctness is decided in code, not by a
0.5B model behaving well.
"""
import json
import re
from dataclasses import dataclass, field, replace

# Keys the model has actually used for a chunk number, plus the obvious synonyms. Text-
# bearing keys ("value", "text", "excerpt") are deliberately NOT here: they contain chunk
# prose, and prose contains numbers like "12 weeks" that would be read as citations.
_NUMBER_KEYS = {"number", "num", "n", "chunk", "chunk_number", "index", "idx", "id", "context", "ref"}

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)
_FIRST_OBJECT = re.compile(r"\{.*\}", re.S)
_BRACKET_NUMBER = re.compile(r"\[(\d+)\]")

# The value of "answer" in an object that never closed. Deliberately does NOT require a
# closing quote: the whole point is that generation stopped mid-string.
_TRUNCATED_ANSWER = re.compile(r'"answer"\s*:\s*"((?:[^"\\]|\\.)*)', re.S)


@dataclass(frozen=True)
class ParsedAnswer:
    answer: str
    cited: list[int]                       # 1-based ordinals, validated in range, order preserved
    dropped: list[str] = field(default_factory=list)
    parse_path: str = "json"               # json | text_fallback | unparsed
    quote_for: dict[int, str] = field(default_factory=dict)
    """Which of the model's quotes resolved to which chunk, 1-based.

    Kept so a citation can show the SOURCE sentence the quote matched rather than the whole
    510-token chunk. The model's own words never leave this dict — they are the lookup key,
    not the thing displayed."""

    @property
    def is_empty(self) -> bool:
        """The model declined to answer.

        Advisory only. `insufficient_context` is decided in code from retrieval scores
        BEFORE the model is called (Day 1); this is a second, weaker signal, never the
        authority.
        """
        return not self.answer.strip()


@dataclass(frozen=True)
class ParsedProposal:
    tool: str | None                       # create_task | summarize_document | lookup_knowledge | None
    title: str | None = None
    chunk: int | None = None
    query: str | None = None
    dropped: list[str] = field(default_factory=list)


def _load_json(raw: str) -> dict | None:
    """Four attempts, cheapest first. Models wrap JSON in prose and markdown fences.

    The fourth exists because of a measured failure: 3 runs in 25 emitted a fenced fragment
    with the braces missing entirely —

        ```json
        "answer": "12"
        ```

    — which fails all three earlier attempts, so the whole raw string became the answer and
    the user would have been shown markdown fences. Re-wrapping costs one more parse
    attempt and recovers it.
    """
    container = _json_container(raw)
    return container if isinstance(container, dict) else None


def _json_container(raw: str) -> dict | list | None:
    """The same four attempts, but an ARRAY counts as a result. Day 18b.

    `_load_json` discards a top-level list, and that discard was a user-visible bug. Asked
    to "list the formulas for binary search and B+ tree cost", Qwen2.5-0.5B replied:

        ```json
        [{"formula": "binary search (sorted file)",
          "quote": "Binary search (sorted file): cost = \u2308 log\u2082(b) \u2309"}]
        ```

    That is valid JSON, it parses on the first attempt, and `isinstance(obj, dict)` threw it
    away — so the prose fallback kept the WHOLE string, fences and brackets included, and
    rendered it to the user as the answer. Exactly the failure this function's docstring
    above already describes for a different shape, in a branch that could not see it.

    The content was good: both quotes are verbatim document text and the grounding guard
    scored 0.882. Only the envelope was unexpected, and the envelope is what the user reads.
    """
    for candidate in (raw, _fenced(raw), _first_object(raw), _rewrapped(raw)):
        if not candidate:
            continue
        try:
            obj = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict | list):
            return obj
    return None


def _fenced(raw: str) -> str | None:
    m = _FENCE.search(raw)
    return m.group(1) if m else None


def _first_object(raw: str) -> str | None:
    m = _FIRST_OBJECT.search(raw)
    return m.group(0) if m else None


def _rewrapped(raw: str) -> str | None:
    """Last resort: brace-less key/value pairs that are otherwise valid JSON body."""
    body = (_fenced(raw) or raw).strip()
    if body.startswith("{") or '"' not in body:
        return None
    return "{" + body.rstrip(",") + "}"


def _numbers_from(node: object, out: list[int]) -> None:
    """Pull chunk numbers out of whatever shape `cites` arrived in.

    Handles every shape observed on Day 2: [1, 2] · [{"number": 1, "context": "[1]"}] ·
    [{"context": "[1]", "number": 2, "value": "<chunk prose>"}] · ["1", "2"].
    """
    if isinstance(node, bool):
        return  # bool is an int subclass in Python; a True here is not chunk 1
    if isinstance(node, int):
        out.append(node)
    elif isinstance(node, str):
        # A bare "[1]" or "1" is a reference; free prose is not, so require the whole
        # string to be a number or a bracketed number.
        s = node.strip()
        m = _BRACKET_NUMBER.fullmatch(s) or re.fullmatch(r"\d+", s)
        if m:
            out.append(int(m.group(1) if m.lastindex else s))
    elif isinstance(node, list):
        for item in node:
            _numbers_from(item, out)
    elif isinstance(node, dict):
        for key, value in node.items():
            if key.lower() in _NUMBER_KEYS:
                _numbers_from(value, out)


def _validate(raw_numbers: list[int], chunk_count: int) -> tuple[list[int], list[str]]:
    """Keep what points at a real chunk, drop and record the rest.

    Deduplicated with order preserved, because the model repeats itself and the citation
    list is shown to a person.
    """
    kept: list[int] = []
    dropped: list[str] = []
    for n in raw_numbers:
        if 1 <= n <= chunk_count:
            if n not in kept:
                kept.append(n)
        else:
            dropped.append(str(n))
    return kept, dropped


def _salvage_truncated_answer(raw: str) -> str | None:
    """Recover the answer text from a JSON object that generation cut off."""
    match = _TRUNCATED_ANSWER.search(raw)
    if match is None:
        return None
    body = match.group(1).rstrip("\\")  # a dangling escape would break the decode below
    try:
        text = json.loads(f'"{body}"')
    except ValueError:
        text = body.replace("\\n", "\n").replace('\\"', '"')
    text = text.strip()
    return text or None


def parse_answer(raw: str, chunk_count: int) -> ParsedAnswer:
    """Stage 1: the JSON envelope. Stage 2: bracketed numbers in raw text.

    The fallback is Format B's trick kept as a safety net. Format C parsed 10/10 in
    testing, but ten samples of one question is not proof; without the fallback a future
    parse failure costs the whole answer after a 25-second wait, and with it the answer
    survives and only the citations degrade.
    """
    obj = _load_json(raw)
    if obj is not None:
        answer = obj.get("answer")
        if not isinstance(answer, str):
            answer = ""
        numbers: list[int] = []
        _numbers_from(obj.get("cites"), numbers)
        kept, dropped = _validate(numbers, chunk_count)
        return ParsedAnswer(answer=answer.strip(), cited=kept, dropped=dropped, parse_path="json")

    # JSON that never finished. Measured on the real corpus: a detailed answer runs to
    # max_new_tokens, so the object is cut off mid-string and _load_json rightly rejects it.
    # The prose fallback below then treats the BROKEN JSON as the answer, and the user is
    # shown ```json {"answer": "... in the chat bubble — the salvage being worse than the
    # failure. The answer text itself is intact up to the cut, so take it and drop the
    # scaffolding. No citations: the quotes array is what got truncated away, and a
    # half-parsed quote is exactly the guess this service refuses to make.
    salvaged = _salvage_truncated_answer(raw)
    if salvaged:
        return ParsedAnswer(answer=salvaged, cited=[], dropped=[], parse_path="salvaged_json")

    # No JSON at all: keep the prose as the answer and scavenge any [n] markers.
    numbers = [int(x) for x in _BRACKET_NUMBER.findall(raw)]
    kept, dropped = _validate(numbers, chunk_count)
    answer = _BRACKET_NUMBER.sub("", raw).strip()
    return ParsedAnswer(
        answer=answer,
        cited=kept,
        dropped=dropped,
        parse_path="text_fallback" if (answer or kept) else "unparsed",
    )


# Hyphens, matching Spring's ActionType. See schemas.ToolName.
_TOOLS = {"create-task", "summarize-document", "lookup-knowledge"}


def parse_proposal(
    raw: str,
    chunk_texts: list[str] | None = None,
    chunk_count: int | None = None,
) -> ParsedProposal:
    """Fails closed: anything unrecognised becomes "no proposal".

    A wrongly-proposed action is worse than a missed one — it puts a decision in front of a
    human that should never have been raised, and Day 14 measures exactly that false
    positive rate. Unknown tool name, missing argument, out-of-range chunk: all become None.
    """
    if chunk_texts is None and chunk_count is None:
        raise TypeError("parse_proposal needs chunk_texts (preferred) or chunk_count")
    n_chunks = len(chunk_texts) if chunk_texts is not None else (chunk_count or 0)

    obj = _load_json(raw)
    if obj is None:
        return ParsedProposal(tool=None, dropped=["unparseable"])

    tool = obj.get("tool")
    if not isinstance(tool, str) or tool.strip().lower() not in _TOOLS:
        reason = str(tool) if tool not in (None, "none") else None
        return ParsedProposal(tool=None, dropped=[reason] if reason else [])
    tool = tool.strip().lower()

    dropped: list[str] = []
    title = obj.get("title") if isinstance(obj.get("title"), str) else None
    query = obj.get("query") if isinstance(obj.get("query"), str) else None

    # Prefer a QUOTE resolved against real text over a number the model invented — the
    # same correction qa-v2 made. A number is kept only as a fallback for callers that
    # still pass chunk_count.
    chunk = None
    quote = obj.get("quote")
    if chunk_texts is not None and isinstance(quote, str) and quote.strip():
        chunk = resolve_quote(quote, chunk_texts)
        if chunk is None:
            dropped.append(quote[:60])
    if chunk is None:
        numbers: list[int] = []
        _numbers_from(obj.get("chunk"), numbers)
        if numbers:
            kept, bad = _validate(numbers, n_chunks)
            dropped.extend(bad)
            chunk = kept[0] if kept else None

    # Required argument missing -> no proposal at all, rather than a half-built one.
    if tool == "create-task" and not (title and title.strip()):
        return ParsedProposal(tool=None, dropped=dropped + ["create-task without title"])
    if tool == "summarize-document" and chunk is None:
        return ParsedProposal(tool=None, dropped=dropped + ["summarize-document without a resolvable source"])
    if tool == "lookup-knowledge" and not (query and query.strip()):
        return ParsedProposal(tool=None, dropped=dropped + ["lookup-knowledge without query"])

    return ParsedProposal(tool=tool, title=title, chunk=chunk, query=query, dropped=dropped)


# --- quote-based citations (qa-v2) ------------------------------------------

_WORD = re.compile(r"[a-z0-9]+")
_MIN_OVERLAP = 0.6   # of the quote's words that must appear in the chunk
_MIN_WORDS = 4       # shorter "quotes" match too many chunks to be evidence of anything


# Sentence-ish boundaries, matching how chunking split them in the first place.
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")


def source_sentence(quote: str, chunk_text: str) -> str:
    """The sentence FROM THE CHUNK that the model's quote best matches.

    This is what a citation card should show, and the distinction is the whole point: it
    returns the DOCUMENT's words, never the model's. Storing the model's quote string would
    put generated text on screen under a filename — the misattribution that quote-resolved
    citations exist to prevent — and Day 7 measured the model paraphrasing often enough
    (2 of 3 quotes unresolvable) that this is a live risk, not a theoretical one.

    Falls back to the whole chunk when no single sentence stands out, which is honest:
    better a long excerpt than a confidently wrong short one.
    """
    sentences = [s.strip() for s in _SENTENCE.split(chunk_text) if s.strip()]
    if len(sentences) <= 1:
        return chunk_text.strip()

    q_set = set(_words(quote))
    if not q_set:
        return chunk_text.strip()

    best_score, best = 0.0, None
    for sentence in sentences:
        s_set = set(_words(sentence))
        if not s_set:
            continue
        overlap = len(q_set & s_set) / len(q_set)
        if overlap > best_score:
            best_score, best = overlap, sentence

    return best if best is not None else chunk_text.strip()


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def resolve_quote(quote: str, chunk_texts: list[str]) -> int | None:
    """Map a quoted sentence back to the chunk it came from. 1-based, or None.

    Exact containment first, because the model usually copies verbatim. Then word overlap,
    because under sampling it sometimes paraphrases or truncates — and a paraphrase that
    clearly came from one chunk is still a usable citation.

    Returns None when nothing matches well enough, AND when two chunks tie: an ambiguous
    citation is not evidence, and a wrong one is worse than none.
    """
    q_words = _words(quote)
    if len(q_words) < _MIN_WORDS:
        return None

    normalised = " ".join(q_words)
    exact = [i for i, c in enumerate(chunk_texts, start=1) if normalised in " ".join(_words(c))]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None  # the same sentence in two chunks cannot identify one

    if not chunk_texts:
        # Nothing to resolve against. Previously unreachable — every caller passed the
        # chunks it had just retrieved — and made reachable by cite_from_answer, which runs
        # on the answer rather than on a quote. An IndexError here would have surfaced as a
        # 500 from the product path.
        return None

    scored: list[tuple[float, int]] = []
    q_set = set(q_words)
    for i, chunk in enumerate(chunk_texts, start=1):
        c_set = set(_words(chunk))
        scored.append((len(q_set & c_set) / len(q_set), i))
    scored.sort(reverse=True)
    best, runner_up = scored[0], (scored[1] if len(scored) > 1 else (0.0, 0))
    if best[0] < _MIN_OVERLAP or best[0] == runner_up[0]:
        return None
    return best[1]


# The `quotes` array as TEXT, recovered from an object json.loads refused. Non-greedy to
# the first `]`, which is correct because a quote containing a bracket is not a sentence
# from a document.
_QUOTES_BLOCK = re.compile(r'"quotes"\s*:\s*\[(.*?)\]', re.S)

#: Element boundaries inside that array. A comma between a closing and an opening quote is
#: a separator; a comma INSIDE a sentence is not, which is why the quotes are required.
_QUOTE_SEPARATOR = re.compile(r'"\s*,\s*"')


def salvage_quotes(raw: str) -> list[str]:
    """Pull the quotes out of a `quotes` array that is not valid JSON.

    MEASURED, on the real corpus, and not the failure I expected to find. Asked "how much of
    the tuition is refunded in the first week", Qwen2.5-0.5B replied:

        {"answer": "50%", "quotes": ["50%" from the 8th to the 15th day", ...]}

    Those inner quotes are UNESCAPED, so the object is malformed and `json.loads` rejects
    all of it. The answer regex then recovered `50%` — a single token, which correctly
    resolves to no chunk — and a 1.00-overlap answer shipped with no source. The citation
    the model offered was sitting in the raw text the whole time.

    This is the same PARSE LENIENTLY, VALIDATE STRICTLY rule the rest of this module runs
    on. Nothing here decides a citation is real: every recovered string still goes through
    `resolve_quote` against text this service already holds, so a mangled fragment that
    matches nothing is dropped exactly like a cleanly-parsed one would be.
    """
    match = _QUOTES_BLOCK.search(raw)
    if match is None:
        return []
    recovered = []
    for part in _QUOTE_SEPARATOR.split(match.group(1)):
        # Strip the outer quoting the split left behind. Inner stray quotes are left alone:
        # `_words` discards punctuation anyway, so they cost nothing and removing them would
        # risk joining two words into one.
        cleaned = part.strip().strip('"').strip()
        if cleaned:
            recovered.append(cleaned)
    return recovered


def parse_quoted_answer(raw: str, chunk_texts: list[str]) -> ParsedAnswer:
    """qa-v2's parser: citations are derived from quotes, never taken from the model.

    The model never states a chunk number, so it cannot state a wrong one. Every citation
    here was resolved by matching text this service already holds.
    """
    obj = _load_json(raw)
    if obj is None:
        # A TOP-LEVEL ARRAY parses cleanly and is not a dict, so `_load_json` returns None
        # for it. Caught here rather than in the prose fallback, which would render the
        # brackets to the user. See `_json_container`.
        listed = _json_container(raw)
        if isinstance(listed, list):
            return _from_unlabelled_json(listed, chunk_texts)

        salvaged = parse_answer(raw, len(chunk_texts))  # fall back to qa-v1 behaviour
        if salvaged.cited or not salvaged.answer:
            return salvaged
        # The object was malformed rather than absent, so the model may still have declared
        # quotes that json.loads could not reach. Recover them and resolve them normally.
        cited: list[int] = []
        dropped: list[str] = []
        quote_for: dict[int, str] = {}
        for quote in salvage_quotes(raw):
            ordinal = resolve_quote(quote, chunk_texts)
            if ordinal is None:
                dropped.append(quote[:60])
            elif ordinal not in cited:
                cited.append(ordinal)
                quote_for[ordinal] = quote
        if cited:
            return replace(salvaged, cited=cited, dropped=salvaged.dropped + dropped,
                           quote_for=quote_for)
        return salvaged

    answer = obj.get("answer")
    if not isinstance(answer, str):
        answer = ""

    quotes: list[str] = []
    _strings_from(obj.get("quotes"), quotes)

    if not answer.strip() and not quotes:
        # A JSON OBJECT WITH NONE OF THE KEYS WE ASKED FOR — {"formulas": [...]}, and the
        # same improvisation as the array above. Returning here would be an empty answer
        # and no citations: the user is told nothing could be put together while the
        # content sits in the reply, unread. The array case was visible because it showed
        # markup; this one failed silently, which is worse.
        return _from_unlabelled_json(obj, chunk_texts)

    cited: list[int] = []
    dropped: list[str] = []
    quote_for: dict[int, str] = {}
    for quote in quotes:
        ordinal = resolve_quote(quote, chunk_texts)
        if ordinal is None:
            dropped.append(quote[:60])
        elif ordinal not in cited:
            cited.append(ordinal)
            quote_for[ordinal] = quote
    return ParsedAnswer(answer=answer.strip(), cited=cited, dropped=dropped,
                        parse_path="json", quote_for=quote_for)


def _every_string(node: object, out: list[str]) -> None:
    """Every string leaf, whatever key it sits under.

    Deliberately NOT `_strings_from`, which only follows a known set of keys. This runs on
    a reply whose keys are the model's own invention — "formula", "step", "item" — so there
    is no key list to match. The protection is not the key; it is that every string
    harvested is then resolved against chunk text before it is used.
    """
    if isinstance(node, str):
        text = node.strip()
        if text:
            out.append(text)
    elif isinstance(node, list):
        for item in node:
            _every_string(item, out)
    elif isinstance(node, dict):
        for value in node.values():
            _every_string(value, out)


def _drop_subsumed(strings: list[str]) -> list[str]:
    """Remove any string wholly contained in another. Order preserved.

    These replies pair a LABEL with the thing it labels — {"formula": "binary search
    (sorted file)", "quote": "Binary search (sorted file): cost = \u2308 log\u2082(b)
    \u2309"} — and the label is long enough to resolve against a chunk on its own. Keeping
    both printed the heading twice, once bare and once as part of the line it introduces.

    Case-insensitive, because the label is usually the same words in a different case,
    which is precisely why a plain equality check does not catch it.
    """
    ordered = sorted(strings, key=len, reverse=True)
    kept: list[str] = []
    for text in ordered:
        lowered = text.lower()
        if not any(lowered in k.lower() for k in kept):
            kept.append(text)
    return [t for t in strings if t in kept]


def _from_unlabelled_json(node: dict | list, chunk_texts: list[str]) -> ParsedAnswer:
    """A reply that is structured, parseable, and in none of the shapes qa-v2 asked for.

    WHAT THIS REPLACES. The old path showed the user raw markup — code fence, brackets,
    quoted keys — because the final fallback keeps its input verbatim as the answer, and
    its input was JSON. A reader got scaffolding instead of a sentence.

    THE ANSWER IS BUILT FROM THE DOCUMENT, NOT FROM THE MODEL. Each harvested string is put
    through `resolve_quote` against the retrieved chunks. The ones that resolve are the
    document's own sentences, and those are what the answer is made of — so this cannot
    promote invented text into an answer that previously showed as mangled markup.

    When NOTHING resolves there is no document text to show, so the strings are joined
    anyway: they are still the model's content, and prose it wrote is a better thing to
    render than the JSON it wrapped around it. That case gets `parse_path=unlabelled_json`
    with no citations, which is exactly how it should read in a trace.
    """
    harvested: list[str] = []
    _every_string(node, harvested)
    harvested = _drop_subsumed(harvested)

    cited: list[int] = []
    dropped: list[str] = []
    quote_for: dict[int, str] = {}
    grounded: list[str] = []
    for text in harvested:
        ordinal = resolve_quote(text, chunk_texts)
        if ordinal is None:
            dropped.append(text[:60])
            continue
        if ordinal not in cited:
            cited.append(ordinal)
            quote_for[ordinal] = text
        # Kept even when the ordinal repeats: two formulas can live in one chunk, and
        # dropping the second would silently delete half the answer.
        if text not in grounded:
            grounded.append(text)

    # Short fragments are labels, not content — "binary search (sorted file)" next to the
    # formula it names. The same 4-word floor resolve_quote uses, for the same reason.
    body = grounded or [t for t in harvested if len(_words(t)) >= _MIN_WORDS]
    return ParsedAnswer(
        answer="\n".join(body).strip(),
        cited=cited,
        dropped=[] if grounded else dropped,
        parse_path="unlabelled_json",
        quote_for=quote_for,
    )


def _strings_from(node: object, out: list[str]) -> None:
    """Quotes arrive as a list of strings, or wrapped in objects — same improvisation the
    numbers came in. Accept either."""
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, list):
        for item in node:
            _strings_from(item, out)
    elif isinstance(node, dict):
        for key, value in node.items():
            if key.lower() in {"text", "quote", "sentence", "source", "value", "excerpt"}:
                _strings_from(value, out)


# --- answer-derived citations (Day 16) --------------------------------------

def cite_from_answer(answer: str, chunk_texts: list[str]) -> tuple[list[int], dict[int, str]]:
    """Locate the ANSWER's own sentences in the chunks, when the model declared no quotes.

    WHY THIS EXISTS. Under qa-v2 the model returns {"answer": ..., "quotes": [...]} and
    citations are resolved from those quotes. Qwen2.5-0.5B keeps to that envelope on short
    factual questions and ABANDONS IT on open-ended ones, answering in plain prose — so a
    well-grounded answer shipped with zero sources. Measured: "what is the refund policy"
    parsed as json with 1 citation; "Tell me about admission policy" fell to text_fallback
    with 0, while scoring 0.73 on the grounding guard. The evidence was there and unused.

    THIS IS A FALLBACK AND NEVER A REPLACEMENT. Declared quotes are the model telling us
    which sentence it used, which is strictly better evidence than us inferring it
    afterwards. This runs only when that produced nothing.

    IT IS STILL CODE DECIDING, NOT THE MODEL. Every sentence is matched against text this
    service already holds, by the same `resolve_quote` that handles declared quotes — same
    4-word floor, same 0.6 overlap threshold, same refusal to resolve a tie. A sentence the
    model invented will not match, and an ambiguous one is dropped rather than guessed.

    THE HONEST RISK, written down rather than discovered later: a sentence the model wrote
    from its own training could coincidentally overlap a chunk enough to resolve, and would
    then be cited as if the document said it. The thresholds make that unlikely, not
    impossible — which is why the trace records WHICH source produced a citation, so a
    surprising one can be traced to the weaker mechanism.

    :return: ``(ordinals, sentence_for_ordinal)`` — 1-based, order preserved, deduplicated.
    """
    cited: list[int] = []
    matched: dict[int, str] = {}
    for sentence in _SENTENCE.split(answer):
        sentence = sentence.strip()
        if len(_words(sentence)) < _MIN_WORDS:
            continue
        ordinal = resolve_quote(sentence, chunk_texts)
        if ordinal is not None and ordinal not in cited:
            cited.append(ordinal)
            matched[ordinal] = sentence
    return cited, matched
