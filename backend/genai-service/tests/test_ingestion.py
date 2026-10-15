"""Day 3 tests.

Formats that can be built in memory are tested here (markdown, text, csv, xlsx, docx).
PDF is verified against the real corpus in a separate script — generating a PDF with a text
layer needs another dependency, and a fabricated one would not prove anything about the
files actually in the database.
"""
import io

import pytest

from app.ingestion import Segment, UnsupportedDocument, chunk_document, extract
from app.ingestion.extract import ExtractedDocument


def count_words(text: str) -> int:
    """Stand-in for bge's tokenizer. Injected so the suite never loads a 1GB model."""
    return len(text.split())


# --- extraction --------------------------------------------------------------

def test_markdown_headings_become_sections():
    """CitationDto.section already exists and CitationCard.tsx renders it — today it shows
    the literal "Placeholder section". These headings are what replaces it."""
    doc = extract(b"# Leave\nBody one.\n\n## Approval\nBody two.", "policy.md")
    assert doc.kind == "markdown"
    assert [s.section for s in doc.segments] == ["Leave", "Approval"]


def test_markdown_without_headings_is_one_segment():
    doc = extract(b"Just some prose with no headings at all.", "notes.md")
    assert len(doc.segments) == 1 and doc.segments[0].section is None


def test_dispatch_is_on_content_and_extension_never_on_mime():
    """Three documents in the live database are stored as application/octet-stream and are
    actually a .md and .xlsx. The recorded MIME type cannot be trusted."""
    doc = extract(b"# Real markdown\nbody", "FastAPI_Proxy_Architecture.md")
    assert doc.kind == "markdown"


def test_csv_rows_are_readable_and_citable():
    doc = extract(b"name,score\nZohaib,88\nAli,91\n", "scores.csv")
    assert doc.kind == "csv"
    assert "Zohaib | 88" in doc.full_text


def test_xlsx_sheet_names_become_sections():
    """Loaded from bytes, never a path: openpyxl picks its parser from the file EXTENSION,
    and stored files are uploads/<uuid> with none. That is the whole reason every
    spreadsheet in the corpus looked unreadable."""
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    wb.active.title = "Dashboard"
    wb.active.append(["Metric", "Value"])
    wb.create_sheet("Backlog").append(["Story", "Priority"])
    buf = io.BytesIO()
    wb.save(buf)

    doc = extract(buf.getvalue(), "tracker.xlsx")
    assert doc.kind == "xlsx"
    assert [s.section for s in doc.segments] == ["Dashboard", "Backlog"]


def test_docx_is_supported_even_though_the_corpus_has_none():
    """DocumentService ACCEPTS .docx. Building extraction from the corpus rather than the
    allow-list would have left a hole the first upload fell into."""
    docx = pytest.importorskip("docx")
    d = docx.Document()
    d.add_heading("Overview", level=1)
    d.add_paragraph("Some body text.")
    buf = io.BytesIO()
    d.save(buf)

    doc = extract(buf.getvalue(), "spec.docx")
    assert doc.kind == "docx"
    assert doc.segments[0].section == "Overview"
    assert "Some body text." in doc.full_text


def test_unsupported_type_raises_rather_than_returning_nothing():
    """It must not become a `ready` document with no chunks: ready promises retrievable,
    and a chunkless document silently never appears in an answer."""
    with pytest.raises(UnsupportedDocument):
        extract(b"\x00\x01binary", "archive.zip")


def test_empty_document_is_detectable():
    assert extract(b"   \n  ", "blank.txt").is_empty


# --- chunking ----------------------------------------------------------------

def _doc(*segments: Segment) -> ExtractedDocument:
    return ExtractedDocument(kind="text", segments=list(segments),
                             full_text="\n\n".join(s.text for s in segments))


def test_char_offsets_index_into_full_text():
    """If these lie, every excerpt in the UI is wrong."""
    doc = extract(b"# A\nOne sentence here. Another one follows.\n\n# B\nThird sentence.", "d.md")
    for chunk in chunk_document(doc, count_words, max_tokens=5):
        assert doc.full_text[chunk.char_start:chunk.char_end] == chunk.text


def test_chunks_never_cross_a_segment_boundary():
    """Otherwise `page` and `section` become approximately true, and a card naming the
    wrong page is the same failure as one naming the wrong document."""
    doc = _doc(Segment("Page one text.", page=1), Segment("Page two text.", page=2))
    chunks = chunk_document(doc, count_words, max_tokens=500)
    assert len(chunks) == 2
    assert [c.page for c in chunks] == [1, 2]


def test_a_chunk_does_not_end_mid_sentence():
    """The dependency Day 2 created: quotes resolve against chunk text, and a half sentence
    matches nothing."""
    doc = _doc(Segment("First sentence here. Second sentence here. Third sentence here."))
    for chunk in chunk_document(doc, count_words, max_tokens=6):
        assert chunk.text.endswith(".")


def test_nothing_is_duplicated_across_chunks():
    """Zero overlap, verified rather than assumed. A duplicated sentence matches two chunks,
    and resolve_quote drops ambiguous matches — overlap would destroy citations."""
    doc = _doc(Segment("Alpha one. Beta two. Gamma three. Delta four."))
    chunks = chunk_document(doc, count_words, max_tokens=4)
    joined = " ".join(c.text for c in chunks)
    for word in ("Alpha", "Beta", "Gamma", "Delta"):
        assert joined.count(word) == 1


def test_ordinals_are_sequential_from_one():
    doc = _doc(Segment("One. Two. Three."))
    chunks = chunk_document(doc, count_words, max_tokens=1)
    assert [c.ordinal for c in chunks] == list(range(1, len(chunks) + 1))


def test_an_oversized_sentence_is_hard_split_rather_than_silently_truncated():
    """Routine in spreadsheets, where one row is one very long 'sentence'. The encoder would
    truncate past its limit without saying so, which is worse than an ugly boundary."""
    doc = _doc(Segment(" ".join(f"word{i}" for i in range(30))))
    chunks = chunk_document(doc, count_words, max_tokens=8)
    assert len(chunks) > 1
    assert all(c.token_count <= 8 for c in chunks)


def test_no_chunk_exceeds_the_ceiling():
    doc = extract(b"# H\n" + b"A sentence of several words here. " * 40, "big.md")
    for chunk in chunk_document(doc, count_words, max_tokens=20):
        assert chunk.token_count <= 20


def test_empty_document_produces_zero_chunks():
    assert chunk_document(extract(b"   ", "blank.txt"), count_words) == []


def test_offsets_survive_leading_and_trailing_whitespace():
    """Regression. Chunk text is stripped, and the offset must move with it.

    Found by chunking a real 16-page PDF, not by the unit tests — hand-written fixtures do
    not have ragged whitespace, and extracted PDF text is full of it. Every excerpt shown in
    the UI is a slice at these offsets, so an offset that is off by two characters is a
    quote that starts mid-word.
    """
    doc = _doc(Segment("   \n  Leading space here. And a second sentence.   \n  "))
    chunks = chunk_document(doc, count_words, max_tokens=4)
    assert chunks
    for chunk in chunks:
        assert doc.full_text[chunk.char_start:chunk.char_end] == chunk.text
        assert chunk.text == chunk.text.strip()


def test_the_chunk_ceiling_leaves_room_for_the_encoders_special_tokens():
    """510, not 512.

    bge adds [CLS] and [SEP] itself, so a chunk counted at 512 content tokens arrives as
    514 and is truncated without any error. The chunk text in the database would still
    contain the tail that its embedding does not represent — a passage that can be cited
    but can never be retrieved.
    """
    from app.config import settings

    assert settings.max_chunk_tokens == settings.max_sequence_tokens - settings.embedding_special_tokens
    assert settings.max_chunk_tokens == 510
