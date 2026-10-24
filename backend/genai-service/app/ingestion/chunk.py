"""Segments in, chunks out.

THREE DECISIONS, EACH WITH A MEASURED REASON.

1. SENTENCE-AWARE PACKING, NOT FIXED-SIZE WINDOWS.
   Day 2 established that citations resolve a QUOTED SENTENCE back to a chunk. A chunk that
   ends mid-sentence produces quotes spanning two chunks, which resolve to neither — or
   ambiguously, and resolve_quote deliberately drops ambiguous matches. Fixed windows would
   silently degrade the citation accuracy Day 2 took from 24% to usable. 512 tokens is a
   CEILING, not a target.

2. ZERO OVERLAP — which is not the conventional answer.
   The usual 10-20% overlap guards against a fact split across a boundary. Here it has a
   specific cost: overlap duplicates sentences across chunks, a duplicated sentence matches
   two chunks, and an ambiguous quote is DROPPED rather than guessed. Overlap would destroy
   citations to protect against something sentence-aware packing already mostly prevents.
   Revisit on Day 13 with the golden set, not by convention.

3. CHUNKS NEVER CROSS A SEGMENT BOUNDARY.
   A segment is one PDF page, one Markdown heading section, one spreadsheet sheet. Packing
   across them would make `page` and `section` approximately true, and a citation card that
   names the wrong page is the same failure as one that names the wrong document.

Token counting is INJECTED, never imported. It must use the EMBEDDING model's tokenizer
(bge), never the generation model's — a chunk is sized for the thing that embeds it. The
injection also keeps the test suite free of a 1GB model load.
"""
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.ingestion.extract import ExtractedDocument, Segment

# Sentence-ish boundaries: terminal punctuation followed by whitespace, or a newline.
# Newlines matter as much as full stops here — CSV rows and spreadsheet rows are the
# natural units in tabular documents and they carry no punctuation at all.
_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass(frozen=True)
class Chunk:
    ordinal: int          # 1-based, document-wide. The number a citation resolves to
    text: str
    token_count: int
    char_start: int       # offsets index into ExtractedDocument.full_text,
    char_end: int         # NOT into the original file — for a PDF those differ entirely
    section: str | None
    page: int | None


def chunk_document(
    document: ExtractedDocument,
    count_tokens: Callable[[str], int],
    max_tokens: int = 512,
    embed_sentences: Callable[[list[str]], "Sequence[Sequence[float]]"] | None = None,
    breakpoint_percentile: float = 70.0,
    window_sentences: int = 5,
    min_distance: float = 0.45,
    min_sentences: int = 4,
) -> list[Chunk]:
    """Segments in, chunks out. Sentence packing by default; semantic when an embedder is given.

    `embed_sentences` is INJECTED exactly as `count_tokens` is, and for the same two
    reasons: this module must not import the model layer, and the tests must not load
    130MB of weights to assert where a boundary lands. Pass None and nothing about the
    old behaviour changes — which is what keeps the two strategies comparable.
    """
    chunks: list[Chunk] = []
    ordinal = 1
    cursor = 0  # running position in full_text

    for segment in document.segments:
        start = document.full_text.find(segment.text, cursor)
        if start < 0:  # defensive: full_text is built from these, so this should not happen
            start = cursor
        cursor = start + len(segment.text)

        pieces = (
            _pack(segment, count_tokens, max_tokens)
            if embed_sentences is None
            else _pack_semantic(segment, count_tokens, max_tokens, embed_sentences,
                                breakpoint_percentile, window_sentences, min_distance,
                                min_sentences)
        )
        for piece_start, piece_text in pieces:
            abs_start = start + piece_start
            chunks.append(Chunk(
                ordinal=ordinal,
                text=piece_text,
                token_count=count_tokens(piece_text),
                char_start=abs_start,
                char_end=abs_start + len(piece_text),
                section=segment.section,
                page=segment.page,
            ))
            ordinal += 1
    return chunks


def _pack(
    segment: Segment,
    count_tokens: Callable[[str], int],
    max_tokens: int,
) -> list[tuple[int, str]]:
    """Greedily fill a chunk with whole sentences. Returns (offset within segment, text)."""
    return _pack_sentences(segment.text, _split_sentences(segment.text),
                           count_tokens, max_tokens)


def _pack_sentences(
    text: str,
    sentences: list[tuple[int, str]],
    count_tokens: Callable[[str], int],
    max_tokens: int,
) -> list[tuple[int, str]]:
    """The packing loop, over a sentence list somebody else chose.

    Split out so semantic chunking can decide WHERE the groups are and still reuse the
    token ceiling, the offset bookkeeping and the oversized-sentence escape hatch. Those
    three are not strategy choices — they are correctness, and duplicating them for a
    second strategy is how the two quietly drift apart.
    """
    packed: list[tuple[int, str]] = []
    current: list[tuple[int, str]] = []
    current_tokens = 0

    def flush() -> None:
        nonlocal current, current_tokens
        if current:
            offset = current[0][0]
            end = current[-1][0] + len(current[-1][1])
            raw = text[offset:end]
            # Stripping shortens the text, so the OFFSET has to move with it. Without this,
            # char_start still pointed at the discarded leading whitespace and every offset
            # after it was wrong by that many characters. The unit tests missed it because
            # hand-written fixtures have no leading whitespace; a real 16-page PDF does.
            lead = len(raw) - len(raw.lstrip())
            packed.append((offset + lead, raw.strip()))
            current = []
            current_tokens = 0

    for offset, sentence in sentences:
        tokens = count_tokens(sentence)

        if tokens > max_tokens:
            # A single sentence over the ceiling. Rare in prose, routine in a spreadsheet
            # row. Flush what is held, then hard-split — the only case where a chunk
            # boundary can land mid-sentence, and it is unavoidable: the encoder would
            # truncate it silently otherwise, which is worse.
            flush()
            for sub_offset, sub_text in _hard_split(sentence, count_tokens, max_tokens):
                packed.append((offset + sub_offset, sub_text))
            continue

        if current and current_tokens + tokens > max_tokens:
            flush()
        current.append((offset, sentence))
        current_tokens += tokens

    flush()
    return [(o, t) for o, t in packed if t.strip()]


def _pack_semantic(
    segment: Segment,
    count_tokens: Callable[[str], int],
    max_tokens: int,
    embed_sentences,
    breakpoint_percentile: float,
    window_sentences: int,
    min_distance: float,
    min_sentences: int,
) -> list[tuple[int, str]]:
    """Cut where the MEANING changes, then pack each group under the token ceiling.

    HOW IT DECIDES. At every gap between sentences, the BLOCK BEFORE is compared with the
    BLOCK AFTER — `window_sentences` on each side, with NO OVERLAP between them. A gap
    where those two blocks are far apart is a topic change.

    WHY NOT COMPARE SINGLE SENTENCES, which is the obvious implementation and was the first
    one here: it does not work with this encoder. Measured on two stress documents, one with
    four unrelated topics and one uniformly about coffee:

        single sentences   A max 0.631   B max 0.573   separation 0.059
        5-sentence blocks  A max 0.566   B max 0.344   separation 0.222

    Sentence-to-sentence distance is dominated by ordinary sentence variation, so a document
    with four unrelated topics looks almost exactly like one with none. Blocks average that
    noise out and leave the topic signal standing.

    WHY NOT OVERLAPPING WINDOWS, which is what this did before: at a boundary BOTH windows
    contain BOTH topics, so they resemble each other and the spike disappears. The real
    aviation-to-baking boundary measured 0.4902 with no window and 0.0955 with an
    overlapping one — the smoothing erased the only thing worth detecting, and the cuts
    landed on noise instead.

    TWO GATES, AND BOTH MUST PASS:

      min_distance          ABSOLUTE. A percentile alone can never say "do not cut" —
                            there is always a top 1% — so a uniform document was cut at
                            every threshold down to p60. This is the gate that lets a
                            document with no seams produce no cuts.
      breakpoint_percentile RELATIVE, and now a safety valve rather than the main rule. It
                            was 99, which on 55 gaps selects 0.55 of them: the CUT COUNT
                            was fixed by sentence count before the text was read, so four
                            topics could never yield four chunks.

    THE TOKEN CEILING STILL WINS. A semantic group of any length goes through the ordinary
    packer, because the encoder truncates past its limit silently. Semantics choose where
    chunks WANT to end; the ceiling decides where they MUST.

    SEGMENT BOUNDARIES STILL WIN TOO: called per segment, so a chunk cannot span two PDF
    pages and `page`/`section` on a citation stay honest.
    """
    sentences = _split_sentences(segment.text)
    if len(sentences) <= min_sentences:
        return _pack_sentences(segment.text, sentences, count_tokens, max_tokens)

    # The two blocks meeting at each gap. `before` ends at i, `after` starts at i+1, so they
    # never share a sentence — that disjointness is the whole point.
    before, after = [], []
    for i in range(len(sentences) - 1):
        lo = max(0, i - window_sentences + 1)
        hi = min(len(sentences), i + 1 + window_sentences)
        before.append(" ".join(text for _offset, text in sentences[lo:i + 1]))
        after.append(" ".join(text for _offset, text in sentences[i + 1:hi]))

    vectors = [_unit(v) for v in embed_sentences(before + after)]
    half = len(before)
    distances = [1.0 - _dot(vectors[i], vectors[half + i]) for i in range(half)]

    # percentile <= 0 means NO relative gate, and it has to be special-cased: a percentile
    # of 0 is the MINIMUM distance, not zero. On a page where every gap is large that
    # minimum is itself large, so "disabled" would have set a high threshold and cut
    # nothing — the exact opposite of disabling it. Found by the test that pins this.
    relative = _percentile(distances, breakpoint_percentile) if breakpoint_percentile > 0 else 0.0
    threshold = max(min_distance, relative)
    # STRICTLY GREATER, so a segment whose distances are all identical produces no cuts
    # rather than cutting at every gap.
    cuts = {i + 1 for i, d in enumerate(distances) if d > threshold}

    groups: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    for i, sentence in enumerate(sentences):
        if i in cuts and len(current) >= min_sentences:
            groups.append(current)
            current = []
        current.append(sentence)
    if current:
        # THE TAIL IS NOT EXEMPT FROM min_sentences. The loop above refuses a cut that would
        # leave a group too short, but whatever is left over at the end was appended
        # unconditionally — so a final cut followed by one fragment produced a chunk of the
        # single word "consumed.", which carries no meaning and still occupies a retrieval
        # slot. PDF text is hard-wrapped and `_split_sentences` treats every line break as a
        # boundary, so these fragments are common rather than exotic.
        if groups and len(current) < min_sentences:
            groups[-1].extend(current)
        else:
            groups.append(current)

    packed: list[tuple[int, str]] = []
    for group in groups:
        packed.extend(_pack_sentences(segment.text, group, count_tokens, max_tokens))
    return packed


def _unit(vector) -> list[float]:
    """Normalise, so a dot product IS the cosine similarity.

    Done here rather than trusted from the caller: the injected embedder is whatever the
    caller passed, and an un-normalised vector would make every distance meaningless in a
    way no test would notice — the numbers would still look like numbers.
    """
    values = [float(x) for x in vector]
    norm = sum(x * x for x in values) ** 0.5
    return values if norm == 0.0 else [x / norm for x in values]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))


def _percentile(values: list[float], percentile: float) -> float:
    """Linear-interpolated percentile. Pure Python on purpose — this module imports no numpy."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * (percentile / 100.0)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _split_sentences(text: str) -> list[tuple[int, str]]:
    """Sentences with their offsets. Offsets are what make char_start/char_end honest."""
    out: list[tuple[int, str]] = []
    position = 0
    for match in _BOUNDARY.finditer(text):
        piece = text[position:match.start()]
        if piece.strip():
            out.append((position, piece))
        position = match.end()
    tail = text[position:]
    if tail.strip():
        out.append((position, tail))
    return out


def _hard_split(
    sentence: str,
    count_tokens: Callable[[str], int],
    max_tokens: int,
) -> list[tuple[int, str]]:
    """Split on whitespace until each piece fits. Last resort only."""
    words = list(re.finditer(r"\S+", sentence))
    pieces: list[tuple[int, str]] = []
    start_idx = 0
    while start_idx < len(words):
        end_idx = start_idx + 1
        while end_idx <= len(words):
            candidate = sentence[words[start_idx].start():words[end_idx - 1].end()]
            if count_tokens(candidate) > max_tokens and end_idx - start_idx > 1:
                end_idx -= 1
                break
            if end_idx == len(words):
                break
            end_idx += 1
        offset = words[start_idx].start()
        pieces.append((offset, sentence[offset:words[end_idx - 1].end()]))
        start_idx = end_idx
    return pieces
