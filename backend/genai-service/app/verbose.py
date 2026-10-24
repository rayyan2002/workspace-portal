"""The explainer report, printed for every request as it happens.

`benchmarks/19_explain_query.py` prints this by RE-RUNNING a question. That answers "why did
that answer happen?" only if you ask again — and a second run of a sampled model is not the
same run. This prints the real one, from the request a user actually made in the browser.

OFF BY DEFAULT, AND THAT IS NOT TIMIDITY. Day 12 shipped `tests/test_log_redaction.py`,
which asserts no document text reaches the log: every value here is a user's question, their
document's contents, or an answer derived from both, so a log line that helpfully includes
"the chunk we retrieved" turns the log into a copy of the corpus — rotated, shipped, and
read by people never granted access to it.

This writes exactly that, on purpose, for demonstrations. Enabling it knowingly trades the
guarantee away. It is a separate switch rather than a log level because a log level is
something someone turns up while debugging a production incident, which is precisely when
this must stay off.

    GENAI_VERBOSE_TRACE=true ./.venv/bin/python -m uvicorn app.main:app --port 8000
"""
import sys
import textwrap

RULE = "=" * 100


def _h(title: str) -> None:
    print(f"\n{RULE}\n  {title}\n{RULE}", file=sys.stderr)


def _wrap(text: str, indent: str = "      ") -> str:
    return textwrap.fill(" ".join(text.split()), width=96,
                         initial_indent=indent, subsequent_indent=indent)


def print_request(question: str, allowed_count: int, backend: str) -> None:
    """Printed before the work starts, so a slow request shows something immediately."""
    _h("INCOMING QUESTION")
    print(f"  question   : {question!r}", file=sys.stderr)
    print(f"  documents  : {allowed_count} in scope", file=sys.stderr)
    print(f"  backend    : {backend}", file=sys.stderr)


def print_prompt(rendered, template) -> None:
    """The template, with its placeholders filled. Printed BEFORE generation starts.

    WHY THIS EXISTS. Every other section of this report describes what came back. This one
    shows what went in — the one thing missing whenever the question was "why did the model
    answer like that?". Three bugs this month turned out to be decided by the prompt rather
    than by the model, and each time the prompt was reconstructed by hand from source code
    afterwards. This prints the real string, from the real request.

    IT PRINTS BEFORE THE MODEL RUNS, deliberately. A local answer takes a median of 55
    seconds; seeing the prompt at the start of that wait is worth more than seeing it at the
    end, and if generation hangs or dies this is the only record of what was sent.

    NOTHING IS ELIDED. An earlier version trimmed chunk bodies to 300 characters on the
    grounds that RETRIEVAL prints them above — which is true, and still the wrong call: the
    whole point of this section is that it is the prompt AS SENT, and a reader comparing it
    against what the model did cannot use a version with holes in it. A 7-chunk prompt runs
    to about 14,000 characters. That is the real size of the thing, and seeing it is part of
    understanding why a local answer takes 55 seconds.
    """
    _h(f"THE PROMPT — WHAT {template.version.upper()} BECAME")

    print(f"  template             : {template.version}", file=sys.stderr)
    # How the chunks are rendered is the single biggest difference between two templates
    # given the same chunks, so it is stated as what you will SEE below rather than as a
    # flag name you would have to look up.
    if template.numbered:
        print("  chunks rendered as   : [1] ... [2] ...  (numbered)", file=sys.stderr)
    else:
        print("  chunks rendered as   : separated by ---  (no [n] labels)", file=sys.stderr)
    print(f"  chunks substituted   : {rendered.chunk_count}", file=sys.stderr)
    print(f"  system message       : {len(rendered.system)} chars", file=sys.stderr)
    print(f"  user message         : {len(rendered.user)} chars   "
          f"(the measured token count is under GENERATION, below)", file=sys.stderr)

    print("", file=sys.stderr)
    print("  -- SYSTEM MESSAGE. The template's fixed text; nothing is substituted into it,",
          file=sys.stderr)
    print("     and no document text may ever appear here (Day 12, prompt injection).",
          file=sys.stderr)
    for line in rendered.system.splitlines():
        print(f"      | {line}", file=sys.stderr)

    print("", file=sys.stderr)
    print("  -- USER MESSAGE. The context block, then any earlier questions, then the",
          file=sys.stderr)
    print("     question. Document text lives HERE, inside the fence.", file=sys.stderr)
    for line in rendered.user.splitlines():
        print(f"      | {line}", file=sys.stderr)

    print("", file=sys.stderr)
    print("  NOT substituted, on purpose: no chunk id, no document id, no filename and no",
          file=sys.stderr)
    print("  page number reaches the model. It is never asked for an identifier, so it",
          file=sys.stderr)
    print("  cannot state a wrong one — citations are resolved in code from the sentence",
          file=sys.stderr)
    print("  it quotes.", file=sys.stderr)


def print_answer(response, chunk_lookup) -> None:
    """The full report. `chunk_lookup` maps a chunk id to (filename, page, text) so UUIDs
    become something a person can read; it is injected so this module never opens a database."""
    trace = response.trace

    _h("RETRIEVAL — WHAT MATCHED, AND HOW WELL")
    print(f"  candidates after collapsing : {trace.candidates_before_threshold}", file=sys.stderr)
    print(f"  duplicates collapsed        : {trace.collapsed_duplicates}", file=sys.stderr)
    print(f"  cleared the {trace.min_score} floor        : {len(trace.retrieved)}", file=sys.stderr)
    if trace.anchor_expanded:
        # Only printed when it fired. A line reading "0" on every request trains the eye to
        # skip it, and this one matters exactly when it is not zero.
        print(f"  admitted by anchored expand : {trace.anchor_expanded}"
              f"  (below the floor, from the top hit's document)", file=sys.stderr)
    print(f"  retried with history        : {trace.retried_with_history}", file=sys.stderr)
    print(f"  embedding {trace.embed_ms}ms + search {trace.search_ms}ms\n", file=sys.stderr)

    for chunk in trace.retrieved:
        filename, page, text = chunk_lookup(str(chunk.chunk_id))
        label = "Close match" if chunk.score >= 0.68 else "Partial match"
        where = f"page {page}" if page else "no page"
        print(f"    rank {chunk.rank}   score {chunk.score:.4f}   {label}", file=sys.stderr)
        print(f"           {filename}  ({where})", file=sys.stderr)
        print(_wrap(text[:220] + ("..." if len(text) > 220 else "")), file=sys.stderr)
        print(file=sys.stderr)

    if trace.quarantined_chunks:
        _h("SAFETY — CHUNKS REMOVED BEFORE THE MODEL SAW THEM")
        print(f"  quarantined : {trace.quarantined_chunks}", file=sys.stderr)
        for reason in trace.quarantine_reasons:
            print(f"      instruction-like phrase: {reason!r}", file=sys.stderr)

    if trace.unsupported_request:
        _h("SAFETY — REQUEST THIS SERVICE CANNOT SERVE")
        print(f"  cannot: {trace.unsupported_request}", file=sys.stderr)

    _h("GENERATION")
    print(f"  backend              : {trace.generation_backend}", file=sys.stderr)
    print(f"  model                : {trace.generation_model}", file=sys.stderr)
    print(f"  template             : {trace.prompt_template_version}", file=sys.stderr)
    print(f"  history turns sent   : {trace.history_turns_received}", file=sys.stderr)
    print(f"  prompt tokens        : {trace.prompt_tokens}", file=sys.stderr)
    print(f"  completion tokens    : {trace.completion_tokens}", file=sys.stderr)
    print(f"  generation           : {trace.generate_ms / 1000:.1f}s   TOTAL {trace.total_ms / 1000:.1f}s",
          file=sys.stderr)
    print(f"  parse path           : {trace.parse_path}", file=sys.stderr)

    _h("IS THE ANSWER MADE OF THE DOCUMENTS?")
    print(f"  grounding overlap    : {trace.grounding_overlap:.3f}", file=sys.stderr)
    # The old line here printed "built from the retrieved text" whenever the guard had not
    # fired — including over an EMPTY answer at overlap 0.000, which is how a declining
    # cloud model read as a success for two sessions. The verdict now comes from the same
    # attribution the JSON trace records, so the terminal and the log cannot disagree.
    from app.observability import attribute_answer

    verdict, suspect, reason = attribute_answer(
        retrieved=len(trace.retrieved),
        top_score=trace.retrieved[0].score if trace.retrieved else None,
        min_score=trace.min_score,
        answer_chars=len(response.answer.strip()),
        overlap=trace.grounding_overlap,
        rejected=trace.rejected_as_ungrounded,
        citations=len(response.citations),
        dropped_quotes=len(trace.dropped_quotes),
        parse_path=trace.parse_path,
    )
    print(f"  VERDICT              : {verdict.upper()}", file=sys.stderr)
    # The plain-English consequence, which the verdict word alone does not carry. The Day
    # 18b rewrite dropped these sentences and kept only the enum, and "UNGROUNDED" does not
    # tell a reader that the answer in front of them was SUPPRESSED and never shown.
    meaning = {
        "grounded": "built from the retrieved text, and shown to the user",
        "weak_evidence": "shown, but the passages behind it barely cleared the floor",
        "unverified": "shown WITHOUT a source — nothing in it could be traced to a chunk",
        "ungrounded": "WITHHELD — not made of the documents, so it was suppressed rather "
                      "than shown without a source",
        "declined": "the model was given documents and chose not to answer from them",
        "no_evidence": "no documents reached the model; this is insufficient_context",
    }.get(verdict)
    if meaning:
        print(f"                         {meaning}", file=sys.stderr)
    if suspect != "none":
        print(f"  LOOK AT              : {suspect}", file=sys.stderr)
        print(f"                         {reason}", file=sys.stderr)
    print("                         (provenance, not correctness — a wrong answer copied",
          file=sys.stderr)
    print("                          from the document still reads as grounded)", file=sys.stderr)

    _h("CITATIONS")
    print(f"  quotes that matched nothing : {len(trace.dropped_quotes)}\n", file=sys.stderr)
    if not response.citations:
        print("      no citations resolved for this answer", file=sys.stderr)
    for citation in response.citations:
        filename, page, _text = chunk_lookup(str(citation.chunk_id))
        label = "Close match" if citation.score >= 0.68 else "Partial match"
        print(f"      {filename}" + (f"   page {page}" if page else ""), file=sys.stderr)
        print(f"      similarity {citation.score:.4f}  -> shown as: {label}", file=sys.stderr)
        print(_wrap(f'"{citation.quote}"'), file=sys.stderr)
        print(file=sys.stderr)

    _h("TOOL ROUTING — WAS AN ACTION OFFERED, AND WHO DECIDED")
    # Added Day 14b. Until then routing lived in a keyword list in Spring, so "why was I
    # offered this?" had no answer anywhere in this report — the one question a person
    # watching a proposal appear actually asks.
    decided = {
        "keywords": "a trigger phrase matched — an auditable rule, not a model",
        "classifier": "no trigger matched; the classifier decided from the message's position"
                      " in the embedding space",
        "silent": "neither half was confident enough to interrupt a human",
        "suppressed": "the request itself was unsupported, so routing was not consulted",
        "failed": "the router errored; this turn proposes nothing",
    }.get(trace.routed_by) or trace.routed_by
    print(f"  routed to            : {trace.routed_tool or '(nothing)'}", file=sys.stderr)
    print(f"  decided by           : {trace.routed_by}", file=sys.stderr)
    print(_wrap(decided, indent=" " * 25), file=sys.stderr)
    if trace.routing_confidence is not None:
        margin = trace.routing_confidence
        print(f"  margin over 'none'   : {margin:+.3f}" +
              ("   (1.0 = an exact keyword hit)" if margin == 1.0
               else "   (0.10 is the floor to propose anything)"), file=sys.stderr)
    for proposal in response.proposals:
        print(f"\n      OFFERED: {proposal.label}", file=sys.stderr)
        print(f"      arguments: {proposal.arguments.model_dump(mode='json')}", file=sys.stderr)
        print("      NOTHING HAS RUN. Spring records the human's decision either way,", file=sys.stderr)
        print("      including a rejection, and only an approval has an effect.", file=sys.stderr)

    _h("WHAT THE USER SEES")
    print(f"  outcome : {response.outcome.value}\n", file=sys.stderr)
    print(_wrap(response.answer or "(empty)"), file=sys.stderr)
    print(file=sys.stderr)


def print_chunking(document, chunks, strategy: str, knobs: dict, chunk_ms: int,
                   ceiling: int) -> None:
    """How this document was cut, printed at ingestion.

    ADDITIVE: the `ingest.done` log line is unchanged and still carries the same fields it
    always has. This is the readable version, for showing someone what semantic chunking
    actually did rather than asking them to trust that it ran.

    Prints SIZES AND BOUNDARIES, never chunk text — the whole-document text is what
    test_log_redaction.py exists to keep out of the log, and a chunking report does not need
    it to be convincing.
    """
    _h("HOW THIS DOCUMENT WAS CUT")
    print(f"  strategy   : {strategy}", file=sys.stderr)
    for name, value in knobs.items():
        print(f"  {name:<11}: {value}", file=sys.stderr)
    print(f"  kind       : {document.kind}  "
          f"({len(document.segments)} segment(s) — pages, headings or sheets)",
          file=sys.stderr)
    print(f"  chunks     : {len(chunks)} in {chunk_ms}ms", file=sys.stderr)

    if not chunks:
        return

    sizes = sorted(c.token_count for c in chunks)
    def at(fraction: float) -> int:
        return sizes[min(len(sizes) - 1, int(len(sizes) * fraction))]
    print(f"  tokens     : min {sizes[0]}  p25 {at(.25)}  median {at(.5)}  "
          f"p75 {at(.75)}  max {sizes[-1]}  (ceiling {ceiling})", file=sys.stderr)

    # WHERE THE CUTS LANDED, as a map. A chunk ending well under the ceiling was ended by
    # MEANING; one at the ceiling was ended by the token limit. Showing the difference is
    # the point — it is the only way to see that semantic chunking did anything at all.
    # AGAINST THE CONFIGURED CEILING, not the largest chunk that happened to occur. Using
    # max(sizes) made every document report chunks "at the ceiling" even when none came
    # close to 510 — a report that flatters the strategy it is meant to evidence.
    by_meaning = sum(1 for c in chunks if c.token_count < ceiling * 0.9)
    print(f"  ended by   : {by_meaning} at a meaning boundary, "
          f"{len(chunks) - by_meaning} at the token ceiling", file=sys.stderr)

    print("  layout     :", file=sys.stderr)
    for chunk in chunks[:12]:
        bar = "#" * max(1, round(chunk.token_count / ceiling * 40))
        where = f"page {chunk.page}" if chunk.page else (chunk.section or "-")
        print(f"    {chunk.ordinal:>3}. {chunk.token_count:>4} tok  "
              f"{bar:<40}  {where[:28]}", file=sys.stderr)
    if len(chunks) > 12:
        print(f"    ... {len(chunks) - 12} more", file=sys.stderr)
