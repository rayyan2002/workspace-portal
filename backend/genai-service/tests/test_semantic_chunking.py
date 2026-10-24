"""Semantic chunking: cut where the meaning turns, not where the punctuation falls.

The embedder is FAKE in every test here, and it embeds BY CONTENT rather than by position.
That matters: the chunker compares the block BEFORE each gap against the block AFTER, so a
fake keyed to sentence index cannot describe what any particular window contains. Keying on
a marker word survives any windowing the implementation chooses, which is the point — these
tests should pin the BEHAVIOUR, not the current arithmetic.

Fake vectors also let a topic change be stated exactly rather than hoped for, and keep
130MB of weights out of a suite that has to stay fast enough to run.
"""
from app.ingestion.chunk import chunk_document
from app.ingestion.extract import ExtractedDocument, Segment


def _doc(*segments: Segment) -> ExtractedDocument:
    return ExtractedDocument(kind="text", segments=list(segments),
                             full_text="\n\n".join(s.text for s in segments))


def _words(text: str) -> int:
    return len(text.split())


def _by_marker(texts):
    """Vector = (how much 'alpha', how much 'beta'). The chunker normalises it.

    PROPORTIONAL, not winner-takes-all. A first attempt returned [1,0] or [0,1] on a
    majority vote, which made a window holding one of each embed as PURE alpha — and that
    invented a boundary one sentence past the real one. A mixed window must land BETWEEN
    the two poles, because that is what a mixed window means.
    """
    out = []
    for text in texts:
        low = text.lower()
        alpha, beta = low.count("alpha"), low.count("beta")
        out.append([1.0, 0.0] if alpha + beta == 0 else [float(alpha), float(beta)])
    return out


def _uniform(texts):
    """Everything identical, so every distance is 0.0 — a document with no seams."""
    return [[1.0, 0.0] for _ in texts]


SEM = dict(embed_sentences=_by_marker, breakpoint_percentile=0.0,
           window_sentences=2, min_distance=0.45, min_sentences=1)


def test_a_topic_change_becomes_a_boundary():
    text = ("Alpha one is here. Alpha two is here. Alpha three is here. "
            "Beta one is here. Beta two is here. Beta three is here.")
    chunks = chunk_document(_doc(Segment(text)), count_tokens=_words, max_tokens=1000, **SEM)

    assert len(chunks) == 2, "one cut, at the one place the subject changes"
    assert "Alpha" in chunks[0].text and "Beta" not in chunks[0].text
    assert "Beta" in chunks[1].text and "Alpha" not in chunks[1].text


def test_a_uniform_document_is_not_cut_at_all():
    # THE FAULT THAT THE ABSOLUTE FLOOR EXISTS TO FIX. A percentile alone can never say "do
    # not cut" — there is always a top 1% — so a document with no seams was being cut at
    # every threshold down to p60. With min_distance, zero distance means zero cuts.
    text = " ".join(f"Alpha sentence number {i} is here." for i in range(12))
    chunks = chunk_document(_doc(Segment(text)), count_tokens=_words, max_tokens=1000,
                            **{**SEM, "embed_sentences": _uniform})

    assert len(chunks) == 1, "nothing diverges, so nothing should be cut"


def test_the_cut_count_follows_the_text_not_the_sentence_count():
    # THE FAULT THAT DEMOTED THE PERCENTILE. At p99 the threshold selects a fixed FRACTION
    # of gaps — 0.55 of them on a 55-gap document — so the number of chunks was decided by
    # sentence count before the embedder was consulted, and three topics could never make
    # three chunks.
    text = ("Alpha one. Alpha two. Alpha three. Alpha four. "
            "Beta one. Beta two. Beta three. Beta four. "
            "Alpha five. Alpha six. Alpha seven. Alpha eight.")
    chunks = chunk_document(_doc(Segment(text)), count_tokens=_words, max_tokens=1000, **SEM)

    assert len(chunks) == 3, "two genuine turns in the text must produce three chunks"


def test_the_token_ceiling_still_wins_over_the_semantics():
    # Semantics choose where a chunk WANTS to end; the encoder decides where it MUST. bge
    # truncates past its limit silently, which is the failure the ceiling exists to prevent.
    text = ". ".join(f"Alpha sentence number {i} about one single topic" for i in range(12)) + "."
    chunks = chunk_document(_doc(Segment(text)), count_tokens=_words, max_tokens=20, **SEM)

    assert len(chunks) > 1, "one topic, but far past the ceiling"
    assert all(c.token_count <= 20 for c in chunks)


def test_chunks_still_do_not_cross_a_segment_boundary():
    # page and section stay honest: a chunk spanning two pages makes both approximate, and
    # a citation naming the wrong page is the same failure as naming the wrong document.
    doc = _doc(Segment("Alpha one. Alpha two.", page=1),
               Segment("Alpha three. Alpha four.", page=2))
    chunks = chunk_document(doc, count_tokens=_words, max_tokens=1000, **SEM)

    assert {c.page for c in chunks} == {1, 2}


def test_offsets_still_index_into_full_text():
    # The offset bookkeeping is shared with sentence packing rather than reimplemented, and
    # this proves the sharing holds. A wrong offset is invisible until a citation points at
    # the wrong place.
    doc = _doc(Segment("Alpha one is here. Alpha two is here. "
                       "Beta one is here. Beta two is here."))
    for chunk in chunk_document(doc, count_tokens=_words, max_tokens=1000, **SEM):
        assert doc.full_text[chunk.char_start:chunk.char_end] == chunk.text


def test_min_sentences_prevents_one_sentence_chunks():
    # Every sentence a different topic. Without a floor this is one chunk per sentence, and
    # a chunk that short carries no context to answer from.
    text = "Alpha one. Beta one. Alpha two. Beta two. Alpha three. Beta three."
    chunks = chunk_document(_doc(Segment(text)), count_tokens=_words, max_tokens=1000,
                            **{**SEM, "min_sentences": 3})

    assert all(len(c.text.split(".")) > 3 for c in chunks), \
        "a cut must never leave a group shorter than min_sentences"


def test_the_cut_count_is_not_capped_by_a_percentile():
    # THE SECOND HALF OF FAULT 1, and it survived the first fix. Demoting the percentile
    # from 99 to 70 was not enough: the rule takes max(floor, percentile), so on a UNIFORM
    # page the floor wins and the percentile is harmless, but on a DIVERSE page the
    # percentile is higher and overrules the floor. Ten unrelated sentences measured seven
    # gaps above the floor and produced two chunks, because p70 raised the bar to 0.516.
    #
    # Every sentence here turns the subject, so every gap clears the floor. The number of
    # chunks must follow the TEXT, not a fraction of the sentence count.
    # window_sentences=1 here ON PURPOSE. With a wider window both blocks either side of
    # an alternating boundary contain both markers, so nothing clears the floor and the
    # fixture cannot show the cap at all — which is itself worth knowing: the window size
    # bounds how fine a topic alternation the method can resolve.
    text = ("Alpha one. Beta one. Alpha two. Beta two. "
            "Alpha three. Beta three. Alpha four. Beta four.")
    doc = _doc(Segment(text))
    narrow = {**SEM, "window_sentences": 1}

    free = chunk_document(doc, count_tokens=_words, max_tokens=1000, **narrow)
    capped = chunk_document(doc, count_tokens=_words, max_tokens=1000,
                            **{**narrow, "breakpoint_percentile": 70.0})

    assert len(free) > len(capped), (
        "with the percentile disabled the text decides the cut count; a percentile caps it")


def test_a_short_tail_is_merged_rather_than_left_as_its_own_chunk():
    # Found on a stress document: the last chunk was the single word "consumed." — 2 tokens,
    # no meaning, and still able to occupy one of the top_k retrieval slots. The grouping
    # loop refuses a cut that would leave a short group, but the LEFTOVER at the end was
    # appended unconditionally.
    #
    # PDF text is hard-wrapped and every line break is treated as a sentence boundary, so a
    # trailing fragment is the normal case rather than a strange one.
    text = ("Alpha one. Alpha two. Alpha three. Alpha four. Alpha five. "
            "Beta one. Beta two. Beta three. Beta four. Beta five. Beta six.")
    chunks = chunk_document(_doc(Segment(text)), count_tokens=_words, max_tokens=1000,
                            **{**SEM, "min_sentences": 4})

    assert all(len(c.text.split(".")) > 4 for c in chunks), \
        "no chunk may be shorter than min_sentences, including the last one"


def test_without_an_embedder_nothing_changes():
    # The parity guarantee. Both strategies must stay comparable, which they cannot be if
    # adding the semantic path quietly altered the old one.
    doc = _doc(Segment("First sentence here. Second sentence here. Third sentence here."))
    default = chunk_document(doc, count_tokens=_words, max_tokens=1000)
    explicit = chunk_document(doc, count_tokens=_words, max_tokens=1000, embed_sentences=None)

    assert [c.text for c in default] == [c.text for c in explicit]
    assert len(default) == 1
