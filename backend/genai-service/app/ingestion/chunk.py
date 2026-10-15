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
from collections.abc import Callable
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
) -> list[Chunk]:
    chunks: list[Chunk] = []
    ordinal = 1
    cursor = 0  # running position in full_text

    for segment in document.segments:
        start = document.full_text.find(segment.text, cursor)
        if start < 0:  # defensive: full_text is built from these, so this should not happen
            start = cursor
        cursor = start + len(segment.text)

        for piece_start, piece_text in _pack(segment, count_tokens, max_tokens):
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
    sentences = _split_sentences(segment.text)
    packed: list[tuple[int, str]] = []
    current: list[tuple[int, str]] = []
    current_tokens = 0

    def flush() -> None:
        nonlocal current, current_tokens
        if current:
            offset = current[0][0]
            end = current[-1][0] + len(current[-1][1])
            raw = segment.text[offset:end]
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
