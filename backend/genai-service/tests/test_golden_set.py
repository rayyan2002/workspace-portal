"""Day 13: the golden set as a regression test.

`benchmarks/21_golden_set.py` compares backends and prints a table. This asserts. The
difference matters: a benchmark tells you what happened when someone ran it, and nothing
tells you when a question that used to work stops working.

RUNS AGAINST THE LOCAL BACKEND ONLY, and that is the whole reason it can be a test:

  deterministic   greedy decoding, so the same question gives the same answer
  no network      no 503, no 429, no quota that empties overnight
  no cost         Gemini's free tier is capped per day per model, and a 10-question run
                  is 10 requests against it

Gemini is measured in the benchmark, where a flaky upstream is an observation rather than
a failing build.

DESELECTED BY DEFAULT — `addopts = -m 'not golden'`. It loads both models and queries
Postgres, so it takes about two minutes and cannot run where the corpus does not exist:

    PYTHONPATH=$PWD ./.venv/bin/python -m pytest -m golden
"""
import json
from pathlib import Path

import numpy as np
import psycopg
import pytest

from app.answering import answer_question
from app.config import settings
from app.generation import local_generator
from app.ingestion import Embedder
from app.prompts import template_for
from app.retrieval import retrieve
from app.schemas import Outcome

OWNER_EMAIL = "mayub@nisum.com"
GOLDEN = Path(__file__).resolve().parents[1] / "evaluation" / "golden_questions.json"

pytestmark = pytest.mark.golden


@pytest.fixture(scope="module")
def corpus():
    """The allow-list and a chunk-id -> filename map, from the real database."""
    with psycopg.connect(settings.dsn) as conn:
        owner = conn.execute("select id from users where email=%s", (OWNER_EMAIL,)).fetchone()
        assert owner is not None, f"the golden set expects documents owned by {OWNER_EMAIL}"
        allowed = [r[0] for r in conn.execute(
            "select id from documents where owner_id=%s", (owner[0],)).fetchall()]
        names = {str(i): f for i, f in conn.execute(
            "select c.id, d.filename from document_chunks c join documents d on d.id=c.document_id "
            "where c.document_id = ANY(%s::uuid[])", ([str(a) for a in allowed],)).fetchall()}
    assert allowed, "no ready documents — the golden set has nothing to retrieve from"
    return allowed, names


@pytest.fixture(scope="module")
def pipeline():
    """Both models, loaded once for the module. Local only — see the module docstring."""
    import torch
    from sentence_transformers import SentenceTransformer
    from transformers import AutoModelForCausalLM, AutoTokenizer

    emb = SentenceTransformer(settings.embedding_model,
                              revision=settings.embedding_model_revision, device="cpu")
    tok = AutoTokenizer.from_pretrained(settings.generation_model,
                                        revision=settings.generation_model_revision)
    gen = AutoModelForCausalLM.from_pretrained(settings.generation_model,
                                               revision=settings.generation_model_revision,
                                               torch_dtype=torch.float32)
    gen.eval()
    embedder = Embedder(
        encode=lambda texts, bs: np.asarray(
            emb.encode(list(texts), batch_size=bs, normalize_embeddings=True,
                       show_progress_bar=False)).tolist(),
        dim=settings.embedding_dim, model=settings.embedding_model,
        revision=settings.embedding_model_revision)
    return embedder, local_generator(tok, gen)


def _questions():
    return json.loads(GOLDEN.read_text())["questions"]


def _answer(pipeline, corpus, question: str):
    embedder, generate = pipeline
    allowed, _ = corpus
    outcome = retrieve(embedder.embed_query, question, allowed,
                       settings.default_top_k, settings.default_min_score)
    return outcome, answer_question(outcome, question, template_for(settings.prompt_template_version),
                                    generate)


@pytest.mark.parametrize("q", [q for q in _questions() if q["answerable"]],
                         ids=lambda q: q["id"])
def test_retrieval_finds_the_expected_document(pipeline, corpus, q):
    """The tracker's done-when: known questions verify RETRIEVAL correctness.

    Measured 7/7 on Day 13 — retrieval has been the reliable half all month while generation
    was not, so this is the assertion most worth protecting.
    """
    _allowed, names = corpus
    outcome, _ = _answer(pipeline, corpus, q["question"])
    retrieved = {names.get(str(c.chunk_id)) for c in outcome.retrieved}

    assert q["expect_document"] in retrieved, (
        f"{q['expect_document']} was not retrieved for {q['question']!r}; got {sorted(retrieved)}")


@pytest.mark.parametrize("q", [q for q in _questions() if not q["answerable"]],
                         ids=lambda q: q["id"])
def test_unanswerable_questions_are_refused(pipeline, corpus, q):
    """min_score decides insufficient_context in code, before the model is called. These
    three are what make that measurable — a system that answers everything scores perfectly
    on answerable questions alone."""
    _outcome, result = _answer(pipeline, corpus, q["question"])

    assert result.outcome is Outcome.INSUFFICIENT_CONTEXT, (
        f"{q['question']!r} should not have been answerable, got {result.answer[:60]!r}")


@pytest.mark.parametrize("q", [q for q in _questions() if q["answerable"]],
                         ids=lambda q: q["id"])
def test_answers_stay_grounded_in_the_documents(pipeline, corpus, q):
    """The grounding floor, now on real evidence rather than n=4.

    Measured across 11 grounded answers (7 here, 4 on Day 11): every one scored >= 0.578,
    and the known hallucination — "FYP = Flexible Workplace Policy", invented from a table of
    contents — scored 0.057. The floor at 0.30 sits between them with margin on both sides.
    """
    _outcome, result = _answer(pipeline, corpus, q["question"])

    assert not result.rejected_as_ungrounded, (
        f"a legitimate answer was withheld: overlap {result.grounding_overlap:.3f}")
    if result.answer.strip():
        assert result.grounding_overlap >= settings.min_grounding_overlap


def test_every_cited_document_is_one_the_user_owns(pipeline, corpus):
    """Not a quality check — a containment one. A citation naming a document outside the
    allow-list would be the leak the unconditional filter exists to prevent."""
    allowed, names = corpus
    allowed_names = {names.get(str(c)) for c in names}

    for q in _questions():
        _outcome, result = _answer(pipeline, corpus, q["question"])
        for citation in result.citations:
            assert names.get(str(citation.chunk_id)) in allowed_names


@pytest.mark.parametrize("q", [q for q in _questions() if q.get("expect_chunk_contains")],
                         ids=lambda q: q["id"])
def test_retrieval_finds_the_chunk_that_actually_answers(pipeline, corpus, q):
    """DOCUMENT-LEVEL IS NOT ENOUGH, and Day 18b is the proof.

    `test_retrieval_finds_the_expected_document` passed for the whole life of the bug. Asked
    "WHAT IS THE ADMISSION POLICY", retrieval returned three chunks from the prospectus — the
    right document — and every one of them was a refunds table or a repeated page header.
    The chunk describing the admission process ranked 7th at 0.588, under the floor and
    outside top_k, so the model was given the right FILE and none of the right TEXT.

    A document-level assertion cannot see that, and on an 8-chunk document it is close to
    vacuous. This one names the passage.
    """
    _allowed, _names = corpus
    outcome, _ = _answer(pipeline, corpus, q["question"])

    assert any(q["expect_chunk_contains"] in text for text in outcome.texts), (
        f"the chunk answering {q['question']!r} was not retrieved. Expected a chunk "
        f"containing {q['expect_chunk_contains']!r}; got "
        f"{[t[:60] for t in outcome.texts]}")
