"""Which tool a message is asking for, if any. Day 14b.

This file replaces a keyword list that lived in Java. ONE router now exists, in the
language that holds the encoder, and both of the other two languages are tested against
what it publishes rather than reimplementing it.

WHY NOT A GENERATIVE MODEL — measured on Day 10 and the measurement still stands.
propose-v1 asked Qwen2.5-0.5B-Instruct to name a tool and it answered "none" to all nine
labelled cases, including four explicit task requests. Removing the none-anchoring from
the same prompt flipped it to "create-task" for all nine, including "what is the fleet
size". Both are CONSTANT FUNCTIONS: the prompt was the entire signal and the message
contributed nothing. It also cost ~7 seconds per turn to achieve that.

WHY A CLASSIFIER IS A DIFFERENT THING. "A language model generates the tool name" was
never the only alternative to keywords, and it is the worst one — it asks a model to
produce text and then hopes the text is a decision. A classifier asks a much smaller
question: the message is already a point in the 384-dimensional space this service uses
for retrieval, so put it there and see which labelled group it lands nearest. No prompt,
no sampling, no generation. It is a matrix multiply, measured at well under a
millisecond, against the keyword router's ~0ms and the generative pass's 7,000ms.

WHY BOTH, AND NOT JUST THE CLASSIFIER. benchmarks/23 on a held-out set of 27 cases:

    keyword router (what shipped)        25/27   0 false positives   2 missed
    classifier alone                     24/27   0 false positives   3 missed
    BOTH, keywords first                 26/27   0 false positives   1 missed

Neither dominates, and they fail on different cases, which is the whole reason to keep
both. The division is by STRUCTURE, not by whichever pairing scored best:

  * The trigger list is an exact-match rule, auditable by a person, with measured zero
    false positives on create-task. Where a readable rule applies it should decide,
    because this product asks a human to approve every action and "why was I asked
    this?" deserves an answer better than a dot product.
  * No trigger list can express summarize-document or lookup-knowledge without colliding
    with ordinary questions. "summarise the runway efficiency figures" wants an answer
    and "summarise the AeroTwin document for me" wants the tool; they share every word a
    keyword could match. That distinction is geometric, not lexical.

So keywords are asked first and the classifier is consulted only when they stay silent.

A FALSE POSITIVE IS THE EXPENSIVE ERROR. A wrongly-raised proposal puts a decision in
front of a human that should never have been asked, and a user cannot tell a guardrail
from a broken product. A miss merely does nothing. Hence `_MARGIN`: the classifier always
has a favourite, and "create-task by 0.001" is not grounds to interrupt anyone.
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from app.schemas import (
    CreateTaskArguments,
    LookupKnowledgeArguments,
    RetrievedChunk,
    SummarizeDocumentArguments,
    ToolName,
    ToolProposal,
)

log = logging.getLogger(__name__)

TRAINING_SET = Path(__file__).resolve().parent.parent / "evaluation" / "intent_train.json"

# Order is fixed because the probability columns are read positionally below.
LABELS: tuple[str, ...] = (
    ToolName.CREATE_TASK.value,
    ToolName.SUMMARIZE_DOCUMENT.value,
    ToolName.LOOKUP_KNOWLEDGE.value,
    "none",
)

# How far the best TOOL must beat `none` before a human is interrupted. 0.10 and 0.00 both
# scored 26/27 with zero false positives on the held-out set; 0.10 is the one that requires
# the classifier to actually lead rather than merely tie, so unseen phrasings that land
# between classes resolve to silence. Ties go to doing nothing, on purpose.
_MARGIN = 0.10

# ---------------------------------------------------------------------------
# The keyword half. MOVED here from ChatSessionService.java, not copied: Java's copy is
# deleted in the same change. Two lists in two languages that have to agree is the failure
# this project keeps finding — "note down" was in Java's title-prefix list and NOT in its
# trigger list, so the system knew how to extract a title from a phrasing it would never
# route, and nothing noticed for four days.

#: Interrogative openers. A message starting with one of these, or ending in "?", is a
#: QUESTION even when it contains a trigger word. Measured on Day 10 removing both false
#: positives from the trigger list: "is there a todo list in the quarterly report" and
#: "what does the document say about follow up procedures" ask ABOUT tracking.
QUESTION_OPENERS: tuple[str, ...] = (
    "what", "who", "when", "where", "why", "how",
    "is ", "are ", "does ", "do ", "did ", "which", "can you tell",
)

#: Phrases that make the assistant offer to create a task.
TASK_TRIGGERS: tuple[str, ...] = (
    "create a task", "create task", "add a task", "make a task",
    "remind me", "reminder", "todo", "to-do", "to do",
    "note down", "follow up", "follow-up", "action item", "track this", "assign",
)

#: Politeness and framing that sits in front of a request. Never the work itself.
REQUEST_OPENERS: tuple[str, ...] = (
    "please", "can you", "could you", "would you", "can we", "could we", "would you mind",
    "i need to", "i need", "i want to", "we need to", "we should", "i should", "we must",
    "someone needs to", "someone should", "somebody needs to",
    "don't let me forget to", "dont let me forget to", "don't forget to", "dont forget to",
    "make sure to", "make sure", "let's", "lets", "remember to",
)

#: Phrases that mean "record this as a task". These say HOW the user asked, not WHAT they
#: want done, so they are scaffolding and come off.
#:
#: NOTE WHAT IS DELIBERATELY ABSENT: "follow up", "chase up", "review", "schedule". Those
#: are the WORK. The old fixed list contained "please follow up on" and "follow up on", so
#: "please follow up on the runway inspection" became "The runway inspection" — a topic
#: rather than a task. Over-stripping is as wrong as under-stripping and is harder to see,
#: because the result still reads like English.
TASK_WRAPPERS: tuple[str, ...] = (
    "create a task", "create task", "add a task", "add task", "make a task",
    "open a ticket", "open a bug", "raise a ticket",
    "log a todo", "log a task", "add a todo",
    "set a reminder", "set reminder", "remind me", "reminder",
    "keep a note", "make a note", "take a note", "leave a note",
    "jot down", "note down", "write down", "note that",
    # Gerunds of the three note-verbs above. Added after "would you mind noting that the
    # lift is out of service" produced "Noting that the lift is out of service" in an
    # out-of-sample probe. Completing an inflection of a verb already chosen is different
    # from adding a new verb because a case failed — the former closes a hole in the
    # vocabulary, the latter is the reflex this rewrite exists to stop. Said out loud
    # because the distinction is easy to abuse.
    "jotting down", "noting down", "writing down", "noting that",
    "put this on my list", "put it on my list", "add to my list", "on my list",
    "track this", "action item", "action point", "todo", "to-do",
    "assign someone", "assign",
)

#: Joining words that are left dangling once a wrapper in front of them is removed.
#: Stripped ONLY immediately after a wrapper came off, never from a bare message — "About
#: the sprint retro" is a bad title, but a message that genuinely begins with "about" is
#: not one this router would have routed.
_CONNECTIVES: tuple[str, ...] = ("to", "that", "for", "about", "on", "with", "of")

#: Punctuation between a wrapper and its subject: "action item: migrate the legacy rows".
_SEPARATORS = ":-–—,;"


def _strip_phrase(text: str, phrase: str) -> str | None:
    """Remove `phrase` from the front of `text`, but only on a WORD BOUNDARY.

    Without the boundary check "assign" would match "assignment review" and leave
    "ment review" — a title that is not merely wrong but unreadable, from a message that
    was never about assigning anything.
    """
    lowered = text.lower()
    if not lowered.startswith(phrase):
        return None
    rest = text[len(phrase):]
    if rest and rest[0].isalnum():
        return None          # matched mid-word
    return rest.lstrip()


TASK_TITLE_MAX = 255   # tasks.title is VARCHAR(255); the published schema advertises the same
QUERY_MAX = 500        # LookupKnowledgeArguments.query


def looks_like_a_question(message: str) -> bool:
    text = message.strip().lower()
    return text.endswith("?") or text.startswith(QUESTION_OPENERS)


def keyword_route(message: str) -> str | None:
    """create-task, or None. The only tool a readable rule can express safely."""
    if looks_like_a_question(message):
        return None
    text = message.strip().lower()
    return ToolName.CREATE_TASK.value if any(t in text for t in TASK_TRIGGERS) else None


def task_title_from(message: str) -> str:
    """The task title, taken from the message rather than generated.

    A task list is read at a glance, so the title must name the WORK rather than the
    request: "could you jot down that the hangar light is broken" belongs in a list as
    "The hangar light is broken". The wrapper is how the user asked; it is not what they
    want done.

    PEELED COMPOSITIONALLY, not matched as a whole prefix — and that is the fix, not a
    longer list. Day 14b replaced the keyword router with a classifier, so phrasings nobody
    wrote down started reaching this function while it was still matching against a fixed
    list of complete prefixes. Measured on the 32 create-task messages in
    evaluation/title_cases.json: **11/32 correct, and 16 of them became their own title
    verbatim.** The classifier generalised the routing and left the naming behind.

    A fixed list cannot win here, because the wrappers COMPOSE. "can you" + "write down" +
    "that" is three independent pieces, and enumerating their combinations is the
    combinatorial version of the problem the classifier was brought in to solve. So each
    layer is removed in turn until nothing more comes off:

        can you write down that the backup job failed overnight
        -> write down that the backup job failed overnight     (opener)
        -> that the backup job failed overnight                (wrapper)
        -> the backup job failed overnight                     (connective)

    Still NOT a model call. benchmarks/17 measured the generation model against a free
    heuristic and the heuristic matched it; what changed on Day 14b was the set of messages
    that arrive, not the economics. ~7 seconds and a non-deterministic title is a poor
    trade for a string that a human reads once and can edit.
    """
    title = message.strip()

    # Peel one layer per pass. A connective only comes off in a pass where a wrapper came
    # off first, so a message that merely begins with "to" keeps its first word.
    while True:
        peeled = None
        # Longest first: "make sure" must win over nothing, and "assign someone" over
        # "assign", or the leftover is a fragment rather than a subject.
        for phrase in sorted(REQUEST_OPENERS + TASK_WRAPPERS, key=len, reverse=True):
            peeled = _strip_phrase(title, phrase)
            if peeled is not None:
                break
        if peeled is None:
            break

        title = peeled.lstrip(_SEPARATORS).lstrip()
        for connective in sorted(_CONNECTIVES, key=len, reverse=True):
            shortened = _strip_phrase(title, connective)
            if shortened is not None:
                title = shortened.lstrip(_SEPARATORS).lstrip()
                break
        if not title:
            break

    # Drop a trailing clause: "review the findings, it is overdue" -> "review the findings".
    comma = title.find(",")
    if comma > 0:
        title = title[:comma]
    title = title.strip().lstrip(_SEPARATORS).strip()

    if not title:
        # Everything was wrapper — "remind me", "note down". The schema forbids an empty
        # title, and the original message is the only honest thing left to say.
        title = message.strip()

    title = title[0].upper() + title[1:]
    return title[:TASK_TITLE_MAX]


# ---------------------------------------------------------------------------
# The classifier half.

EncodeFn = Callable[[Sequence[str]], object]
"""Texts -> an (n, dim) array of UNIT-NORMALISED vectors.

No bge query prefix. That prefix is trained for query-to-PASSAGE asymmetry, and this is a
sentence-to-sentence comparison, so applying it here would be cargo-culting a convention
from a different task. Measured either way in benchmarks/23: 24/27 both, i.e. no
difference, so the choice is made on what the prefix MEANS rather than on noise.
"""


@dataclass(frozen=True)
class Intent:
    """What the router decided, and enough to say why in a trace."""

    tool: str | None
    decided_by: str          # "keywords" | "classifier" | "silent"
    confidence: float        # the classifier's margin over `none`; 1.0 for a keyword hit
    scores: dict[str, float]


class IntentRouter:
    """Keyword rules plus a classifier fitted at startup from the committed training set.

    Fitting here rather than committing a model file: the vectors depend on the exact
    encoder revision, and a pickled classifier would be a second artefact that can silently
    disagree with the model actually loaded. Refitting costs one encode of 84 short
    sentences and removes a whole class of version-skew bug.
    """

    def __init__(self, classifier=None, encode: EncodeFn | None = None,
                 labels: Sequence[str] = LABELS, margin: float = _MARGIN):
        self._clf = classifier
        self._encode = encode
        self._labels = tuple(labels)
        self._margin = margin

    @property
    def classifier_ready(self) -> bool:
        return self._clf is not None

    @classmethod
    def fit(cls, encode: EncodeFn, training_set: Path = TRAINING_SET) -> IntentRouter:
        import numpy as np
        from sklearn.linear_model import LogisticRegression

        examples = json.loads(training_set.read_text())["examples"]
        messages = [e["message"] for e in examples]
        labels = [e["label"] for e in examples]

        t0 = time.perf_counter()
        vectors = np.asarray(encode(messages))
        # lbfgs on a convex objective from a fixed seed: the same training file and the same
        # encoder produce the same coefficients every time. Nothing here samples.
        clf = LogisticRegression(max_iter=2000, C=4.0, random_state=0).fit(vectors, labels)
        log.info("intent classifier fitted on %d examples in %.1fs (classes=%s)",
                 len(examples), time.perf_counter() - t0, list(clf.classes_))
        return cls(classifier=clf, encode=encode)

    def route(self, message: str) -> Intent:
        """Keywords first; the classifier only where no readable rule applies."""
        hit = keyword_route(message)
        if hit is not None:
            return Intent(tool=hit, decided_by="keywords", confidence=1.0, scores={})

        if self._clf is None:
            # The classifier failed to fit, or was never fitted. Degrading to
            # keywords-only is the correct failure: it loses the two tools keywords
            # cannot express and keeps the one they can, with its measured zero false
            # positives. The alternative — proposing nothing at all — would also disable
            # create-task, which works perfectly well without a model.
            return Intent(tool=None, decided_by="silent", confidence=0.0, scores={})

        import numpy as np

        proba = self._clf.predict_proba(np.asarray(self._encode_one(message)))[0]
        scores = {label: 0.0 for label in self._labels}
        # strict=True is not cosmetic here: a length mismatch between the fitted classes
        # and the probability row would otherwise truncate silently, and the dropped class
        # would read as probability 0.0 — a confident wrong answer from a shape bug.
        for label, p in zip(self._clf.classes_, proba, strict=True):
            scores[label] = float(p)

        none_score = scores["none"]
        tool, best = max(
            ((t, s) for t, s in scores.items() if t != "none"),
            key=lambda pair: pair[1],
        )
        margin = best - none_score
        if margin < self._margin:
            return Intent(tool=None, decided_by="silent", confidence=margin, scores=scores)
        return Intent(tool=tool, decided_by="classifier", confidence=margin, scores=scores)

    def _encode_one(self, message: str):
        if self._encode is None:
            raise RuntimeError("IntentRouter has a classifier but no encoder")
        return self._encode([message])


# ---------------------------------------------------------------------------
# Turning a decision into the contracted shape.

def proposals_for(
    message: str,
    intent: Intent,
    retrieved: Sequence[RetrievedChunk],
) -> list[ToolProposal]:
    """One proposal at most, or none. Builds the wire shape Spring's governance flow reads.

    PROPOSALS COME FROM THE USER'S MESSAGE, NEVER FROM RETRIEVED TEXT. That is a security
    property, not an implementation detail: a poisoned document cannot forge a tool call
    here, because no part of a chunk reaches this function. Day 12 quarantines chunks that
    try; this path never consults them in the first place.

    NOTHING IS EXECUTED AND NOTHING IS WRITTEN. A proposal is a suggestion addressed to a
    human. Spring records a row for every decision including rejections, and only an
    approval has an effect.
    """
    if intent.tool is None:
        return []

    if intent.tool == ToolName.CREATE_TASK.value:
        title = task_title_from(message)
        return [ToolProposal(
            arguments=CreateTaskArguments(
                title=title,
                # STILL "medium", and still a measured decision rather than a leftover.
                # benchmarks/17 asked the generation model to infer priority from
                # deliberately unambiguous phrasing ("urgent", "when you get a chance") and
                # it answered "high" to all nine cases — 3/9, exactly what this constant
                # scores, while costing ~7 seconds and making every task look urgent.
                # A classifier could do this properly and there is no labelled priority
                # data to fit one on; inventing the labels myself would measure my own
                # guesses. Unmeasured, therefore unchanged, and said out loud.
                priority="medium",
            ),
            label=f"Create a task: {title}"[:120],
        )]

    if intent.tool == ToolName.SUMMARIZE_DOCUMENT.value:
        # The TOP-RANKED chunk decides which document, because that is the one the question
        # actually matched. Resolution happens here, in code, over this service's own
        # retrieval result — the model never names a document.
        if not retrieved:
            # Nothing was retrieved, so there is no document to point at. Proposing a
            # summary of an unidentified document is the half-built proposal that
            # parse_proposal refuses to emit, and this refuses it for the same reason.
            return []
        top = retrieved[0]
        return [ToolProposal(
            arguments=SummarizeDocumentArguments(
                # Typed access, no getattr. The parameter was Sequence[object] to keep this
                # module from importing the retrieval package — but RetrievedChunk lives in
                # app.schemas, which this file already imports and which imports nothing from
                # here, so there was never a cycle to avoid. `object` forced getattr, and
                # getattr hides a typo in an attribute name until runtime.
                chunk_ordinal=top.rank,
                document_id=top.document_id,
            ),
            label="Summarise this document",
        )]

    if intent.tool == ToolName.LOOKUP_KNOWLEDGE.value:
        return [ToolProposal(
            arguments=LookupKnowledgeArguments(query=message.strip()[:QUERY_MAX]),
            label=f"Search your documents for: {message.strip()}"[:120],
        )]

    # An unreachable branch kept loud rather than returning []. LABELS and this function
    # have to agree, and a new tool added to one and not the other should fail here where
    # a reader can see why, not go silently unproposed like summarize-document did for
    # five days.
    raise ValueError(f"routed to {intent.tool!r}, which proposals_for cannot build")
