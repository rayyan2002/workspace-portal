"""Configuration. Every value is env-overridable; nothing model-related is hardcoded at a call site."""
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GENAI_", env_file=".env", extra="ignore")

    # R4 in INTEGRATION_CONTRACT.md: this service has no authentication and trusts the
    # allowed_document_ids it is handed, so anyone who can reach it can read any document.
    # Binding anything other than a loopback address makes that a data leak, not a config choice.
    host: str = "127.0.0.1"
    port: int = 8000

    # Pinned by revision, not just by name. A model repo is mutable; "BAAI/bge-small-en-v1.5"
    # today and the same string in six months are not guaranteed to be the same weights, and
    # different weights in the same vector space is the silent-corruption case.
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_model_revision: str = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
    embedding_dim: int = Field(default=384, ge=1)
    # bge's hard sequence limit, INCLUDING the [CLS] and [SEP] the encoder adds itself.
    max_sequence_tokens: int = 512
    embedding_special_tokens: int = 2

    @property
    def max_chunk_tokens(self) -> int:
        """The ceiling for chunk CONTENT: 510, not 512.

        Measured, not assumed: the encoder adds 2 special tokens, so a chunk counted at 512
        content tokens arrives as 514 and bge truncates it — silently. The chunk text in the
        database would still show the tail that the embedding does not represent, so a
        passage could be cited and yet be invisible to retrieval.

        The real corpus produced a maximum of 510 tokens per chunk, so nothing was actually
        truncated. That was luck, not design.
        """
        return self.max_sequence_tokens - self.embedding_special_tokens

    # Applied to queries only, never to documents. Defined here so there is exactly one copy.
    query_prefix: str = "Represent this sentence for searching relevant passages: "

    generation_model: str = "Qwen/Qwen2.5-0.5B-Instruct"
    generation_model_revision: str = "7ae557604adf67be50417f59c2c2f167def9a775"
    # qa-v2, NOT qa-v1. This default said "qa-v1" until Day 7, and it would have shipped
    # the template Day 2 measured as broken: cite-by-number put the right chunk in the
    # citation 6/25, with chunk [1] cited 15 times across five unrelated questions.
    # qa-v2 derives citations from quoted sentences in code and took misattribution from
    # 13/25 to 2/25. templates.py calls qa-v1 "kept for comparison" — a comparison
    # baseline, not a product default. Resolved through TEMPLATES_BY_VERSION so an unknown
    # string fails loudly instead of silently falling back.
    prompt_template_version: str = "qa-v2"

    # Decoding. MEASURED greedy against sampled (benchmarks/14) rather than inheriting
    # benchmark 08's sampling settings by habit: qa-v2 resolves citations by matching the
    # model's quote back to chunk text, so anything that perturbs verbatim reproduction is
    # a citation-accuracy choice, not a stylistic one.
    #
    #   greedy   mean 30.8s | JSON 2/3 | >=1 citation 1/3 | hit the 200-token cap 1/3
    #   sampled  mean 30.1s | JSON 1/3 | >=1 citation 0/3 | hit the cap 0/3
    #
    # At n=3 those are INDISTINGUISHABLE and nobody should read 2/3 vs 1/3 as a result.
    # Greedy is the default because it is DETERMINISTIC — the same question gives the same
    # citation, so Day 13's golden set can regress against it at all — not because it
    # measured better. Revisit with the golden set, where n is large enough to mean
    # something.
    # Raised 200 -> 500, then 500 -> 1000 on request. What it buys and what it costs:
    #
    # 200 truncated real answers mid-sentence. The JSON was cut off, so no quote parsed, so
    # NOTHING was cited — "how many parts in project_setup.txt" spent all 200 tokens
    # enumerating Part 1's bullets and produced parse_path=salvaged_json with zero citations.
    #
    # THE COST IS LATENCY, AND IT IS WORSE THAN THIS COMMENT USED TO CLAIM. Decode is the
    # slow half, because each output token needs a full forward pass over every token
    # before it. The old figure here was "4-8 tok/s"; measured over 22 real answers in
    # logs/answers.jsonl it is a MEDIAN OF 2.7 tok/s, range 0.4-4.8. The rate falls as the
    # prompt grows, and the prompt grew when top_k went 5 -> 7.
    #
    #   1000 tokens at 2.7 tok/s = 374s        at 4.8 = 210s
    #    500 tokens at 2.7 tok/s = 187s        at 4.8 = 104s
    #
    # So a 1000-token answer on this hardware is MINUTES, not seconds. app.genai.timeout
    # was raised to 420s in the same change, because raising this without raising that
    # converts a truncated answer into no answer at all — and at 150s it would have done
    # exactly that: the longest answer already measured took 144s at the 500 cap.
    #
    # Most answers are nowhere near the cap — the median completion is 104 tokens — so this
    # raises the CEILING for the rare long answer rather than the cost of a typical one.
    # It is the long ones that pay, and they pay in whole minutes.
    generation_max_new_tokens: int = Field(default=1000, ge=1)
    generation_do_sample: bool = False
    generation_temperature: float = 0.7
    generation_top_p: float = 0.8
    generation_top_k: int = 20

    # RAISED 5 -> 7 ON DAY 18b, and the honest caveat comes first: 7 is the rank at which
    # the chunk answering "WHAT IS THE ADMISSION POLICY" sat, so this number is calibrated
    # against an evaluation set of 13 questions that INCLUDES the case that motivated it.
    # n is small and the fit is partly to one example. 5 was no better founded.
    #
    # What stops it being a free choice in the other direction is cost: every extra chunk
    # is prompt tokens on every request, and BACKLOG 20 measured unrelated chunks already
    # arriving at k=5. Anchored expansion (retrieval.py, decision 5) is what makes the
    # wider k affordable — it spends the extra slots inside the best-matching document
    # instead of on the next unrelated file, which measured 17 noise chunks against 30.
    default_top_k: int = Field(default=7, ge=1, le=50)

    # The floor for chunks from the document the top hit already identified. Only consulted
    # when something cleared `default_min_score` first, so it cannot admit anything on a
    # question that retrieved nothing — see retrieval.py decision 5.
    #
    # 0.55 rather than lower for a measured reason: the three unanswerable golden questions
    # peak at 0.4220, 0.5175 and 0.4894. 0.55 clears the highest of them by 0.032, which is
    # not a comfortable margin and is the number to revisit first if a false answer ever
    # appears on an unanswerable question.
    # MOVED 0.55 -> 0.50 with the floor above it. This band is only consulted for chunks
    # from the document the top hit already identified, and only when something ALREADY
    # cleared default_min_score — so it cannot fire on an unanswerable question, whose best
    # chunk never reaches 0.55 in the first place. Keeping it at 0.55 would have made the
    # band empty and silently disabled anchored expansion.
    anchor_min_score: float = Field(default=0.50, ge=-1.0, le=1.0)

    # HOW MANY DOCUMENTS MAY CONTRIBUTE TO ONE ANSWER. Day 19, and it is what makes the
    # lower floor affordable.
    #
    # Lowering min_score 0.60 -> 0.55 recovered every reported failure and doubled the
    # off-document noise, 14 -> 29 chunks, which is the trade BACKLOG 20 complained about.
    # Measured in benchmarks/27_retrieval_floor.py, restricting the answer to the
    # best-matching document removes ALL of it:
    #
    #     policy                          hits   off-document   tokens/q
    #     0.60, any document              13/14            14       1709   <- before
    #     0.55, any document              14/14            29       2586
    #     0.55, top 1 document            14/14             0       1943   <- this
    #     0.55, top 2 documents           14/14            13       2268
    #
    # WHY IT WORKS, and why it is not arbitrary: this embedder picks the right DOCUMENT
    # reliably — 9/9 on the golden set, measured — and fails at ranking WITHIN one. All the
    # noise was other documents, so gating at the document level plays to the thing it does
    # well. It is the same insight anchored expansion is built on, applied as a hard limit
    # rather than a preference.
    #
    # THE RISK, stated because the evaluation set cannot see it: a question that genuinely
    # needs two documents now sees one. Nothing in the golden set is cross-document, so this
    # is untested rather than measured safe (BACKLOG 29). Set to 2 or 3 if that case appears;
    # 0 disables the limit entirely and restores the old behaviour.
    max_documents: int = Field(default=1, ge=0, le=50)

    # A MARGINAL MATCH MUST HAVE A CLEAR WINNER. Day 19, and it is what makes 0.55 safe.
    #
    # Lowering the floor to 0.55 recovered "what is university policy" (0.5926) and also
    # admitted "Follow up on finance" (0.5925), which retrieves an aviation deck because
    # this user has no finance document at all. THE CHUNK SCORE CANNOT SEPARATE THOSE —
    # they are one ten-thousandth apart, and no floor exists between them.
    #
    # The DOCUMENT margin can. Measured over every question in the band on the real chat
    # history: how far the best document leads the second-best.
    #
    #     what is university policy    0.5926   margin 0.0428   genuine
    #     tell me about university     0.5663   margin 0.0262   genuine
    #     tell me in detail            0.5850   margin 0.0114   a bare follow-up
    #     Follow up on finance         0.5925   margin 0.0047   no finance document exists
    #     tell me your bugs ?          0.5864   margin 0.0017   not about the documents
    #
    # 5 of 5, with 0.015 between the weakest keep and the strongest reject. It works for the
    # reason everything else on this path works: this embedder is reliable about WHICH
    # DOCUMENT and unreliable about which chunk, so a question with no document winner is
    # one the corpus cannot answer — however close the chunk score came.
    #
    # Applied ONLY below `confident_score`. Above it the match is strong enough to stand on
    # its own: "tell me about ai safety" scores 0.7120 with a margin of 0.0148 and must not
    # be rejected for having two documents that both mention AI.
    confident_score: float = Field(default=0.60, ge=-1.0, le=1.0)
    min_document_margin: float = Field(default=0.02, ge=0.0, le=1.0)

    # An answer must be MADE OF the context, not merely accompanied by it.
    #
    # Found in the UI, not in a test. "tell me about how to defend fyp" retrieved one chunk
    # at 0.603 — a table of contents — so `grounded` was declared before the model ran, and
    # the model then answered from parametric memory, inventing "FYP = Flexible Workplace
    # Policy". Confident, fluent, sourceless, and wrong.
    #
    # `grounded` is a RETRIEVAL decision. Nothing checked that the answer used what it was
    # handed. This is that check: the fraction of the answer's content words that appear
    # anywhere in the chunks it was shown (benchmarks/18).
    #
    #   grounded answers  : 1.000, 1.000, 1.000, 0.578   <- min 0.578
    #   the hallucination : 0.057
    #   gap +0.521, midpoint 0.32
    #
    # 0.30 leaves margin on both sides. The first detector tried — "no citations AND no
    # dropped quotes" — would have rejected two of the four good answers above, which is why
    # this one was measured before being trusted.
    #
    # VALIDATED on Day 13, and left unchanged. The golden set added 7 more grounded answers:
    #
    #   grounded, Day 13 golden set : 0.864 - 1.000   (n=7)
    #   grounded, Day 11            : 0.578 - 1.000   (n=4)
    #   the known hallucination     : 0.057
    #
    # Eleven grounded observations, every one at or above 0.578, against a single measured
    # hallucination at 0.057. The floor sits between them with roughly a quarter of margin on
    # each side. Raising it toward the midpoint would buy nothing and would start risking the
    # expensive error — withholding a legitimate answer — so it stays at 0.30 with better
    # evidence rather than a new number.
    #
    # tests/test_golden_set.py now asserts this on every golden question.
    min_grounding_overlap: float = Field(default=0.30, ge=0.0, le=1.0)

    # Conversation history. Spring sends it; this caps what is actually used, so a long
    # conversation cannot grow the prompt without bound — prefill runs at ~280 tok/s, so
    # every extra turn is real latency on every request.
    max_history_turns: int = Field(default=6, ge=0)

    # How many earlier USER turns are prepended to the retrieval query when the question
    # alone matches nothing.
    #
    # Was 1, and 1 was measurably too few — caught in the UI, not by a test. A follow-up TO
    # a follow-up leans on a turn that is itself contentless:
    #
    #   "tell me in detail tell me all formullas in detail"                    -> 0 chunks
    #   "what are the formula of adbms tell me all formullas in detail"        -> 2 chunks
    #   "what are the formula of adbms tell me in detail tell me all ..."      -> 4 chunks
    #
    # The user asked three questions in a row about one document and the third returned
    # "I couldn't find anything in your documents" — while the document sat at rank 1 for
    # the first.
    #
    # The cost of reaching further back is the same stale-topic pollution measured on Day
    # 8b: asked about adbms, then the fleet, then "tell me more", the second turn back puts
    # one ADBMS chunk in five AeroTwin ones. That is acceptable HERE and not in general,
    # because this path only runs when the question matched NOTHING — the alternative is
    # not a cleaner result, it is no result at all.
    history_turns_for_retrieval: int = Field(default=2, ge=0)

    # MEASURED on Day 6, not inherited. The old default was 0.35, which sits BELOW the
    # noise floor of this embedding space: benchmarks/13 scores four questions the corpus
    # provably cannot answer ("What is the capital of France?") and the WORST of them
    # still reaches 0.422. At 0.35 the threshold rejects 0/4 nonsense questions, so
    # `insufficient_context` — decided in code before the model is ever called — could
    # never fire. A branch that exists, passes its tests, and never executes.
    #
    #   answerable   top1: 0.695 - 0.758
    #   unanswerable top1: 0.422 - 0.518   <- the real floor
    #   separation gap: +0.177, midpoint 0.61
    #
    # AND THE CORRECTION, recorded rather than quietly fixed: TWO of those four
    # "answerable" anchors were seeded stubs. `quarterly_financial_report.pdf` and
    # `FastAPI_Proxy_Architecture.md` contain nothing but "Placeholder content for a
    # <filename>", so their 0.700 / 0.758 measured FILENAME ECHO, not retrieval quality —
    # the question repeated words the chunk already contained. The calibration that set
    # this threshold was itself partly flattered by the corpus defect it was meant to
    # survive, which is the same failure shape as benchmarking against your own test data.
    #
    # What survives: the two genuine anchors (AeroTwin 0.752, training tracker 0.695) are
    # still cleanly above the 0.518 unanswerable ceiling, so 0.60 stands — on n=2 real
    # questions, not n=4. Treat the gap as suggestive, not established.
    #
    # PROVISIONAL: on a corpus that is 2.72x duplicated and full of seeded stubs, Day 13's
    # golden set is what should actually set this — and it must exclude the stubs.
    # LOWERED 0.60 -> 0.55 ON DAY 19, measured in benchmarks/27_retrieval_floor.py.
    #
    # Three complaints resolved to this one number, and each was previously answered with a
    # fix in FRONT of it rather than to it:
    #
    #     admission chunk      0.588   missed 0.60 by 0.012
    #     university policy    0.593   missed 0.60 by 0.007
    #
    # THE CONSTRAINT IS NOT RECALL, IT IS THE UNANSWERABLE QUESTIONS. The floor is what
    # produces insufficient_context, so a floor below their top score makes the service
    # answer things the corpus cannot answer — invisibly, since nothing in the output says
    # the passages were irrelevant. Measured ceiling: 0.5175 ("Who won the 1998 FIFA World
    # Cup final?"). At 0.50 and 0.51 that question retrieves; at 0.52 and above it does not.
    #
    #     floor   golden   reported failures   leaked   noise   tokens/q
    #     0.50      9/9                 5/5        2      36       2855   <- answers what it cannot
    #     0.55      9/9                 5/5        0      29       2586
    #     0.59      9/9                 5/5        0      23       2270
    #     0.60      9/9                 4/5        0      14       1709   <- before
    #     0.63      8/9                 3/5        0       2       1033
    #
    # 0.59 is cheaper and was rejected: it clears "university policy" (0.5926) by 0.0026,
    # which is one phrasing away from failing again — and phrasing sensitivity is the whole
    # complaint. 0.55 gives that case 0.043 of headroom and still sits 0.033 above the
    # unanswerable ceiling. The cost is ~880 prompt tokens per question and 15 more
    # off-document chunks across 14 questions, which BACKLOG 20 is about and this does not
    # pretend to fix.
    default_min_score: float = Field(default=0.55, ge=-1.0, le=1.0)

    # Near-duplicate collapsing removes rows AFTER the database has ranked them, so the
    # query must return more than top_k or collapsing would return fewer than asked for.
    # Measured: 170/177 chunks have a byte-identical twin and one text appears 5 times,
    # so "What were the quarterly financial results?" returns top5 = five copies of ONE
    # passage. 4x is sized from that worst case (x5) with headroom.
    overfetch_factor: int = Field(default=4, ge=1)

    # Python holds SELECT on the chunk tables and nothing else — INTEGRATION_CONTRACT R1.
    # Spring owns every write and the schema. These are separate fields rather than one
    # DSN string so a password can arrive from the environment without being pasted into
    # a URL that ends up in a log line.
    db_name: str = "knowledge_assistant_portfolio"
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = ""
    db_password: str = ""

    @property
    def dsn(self) -> str:
        parts = [f"dbname={self.db_name}", f"host={self.db_host}", f"port={self.db_port}"]
        if self.db_user:
            parts.append(f"user={self.db_user}")
        if self.db_password:
            parts.append(f"password={self.db_password}")
        return " ".join(parts)

    # --- Gemini, the hosted alternative ------------------------------------
    #
    # Choosing this sends retrieved chunks — the user's private documents — to Google.
    # Day 1 recorded "no document text leaves the machine" as a CONSEQUENCE of local models
    # rather than a requirement, so this is a trade to make deliberately and per request,
    # not a setting to flip and forget.
    #
    # The key comes from genai-service/.env (GENAI_GEMINI_API_KEY) and is a SecretStr so it
    # cannot be printed by accident — repr() shows '**********'.
    gemini_api_key: SecretStr | None = None

    # Measured against the live API: gemini-2.0-flash and gemini-2.5-flash both answer 404
    # "no longer available to new users". A model name is configuration, not a constant.
    gemini_model: str = "gemini-3.5-flash"

    # Gemini 3.x reasons internally before writing, and thinking counts against the SAME
    # budget as the answer. Measured: a 500-token cap was consumed entirely by thinking —
    # finishReason MAX_TOKENS, empty answer, no error.
    #
    # RAISED 3000 -> 6000 ON DAY 18b, because raising top_k 5 -> 7 moved this. The thinking
    # budget is dynamic (-1 below), so it scales with the prompt, and a bigger prompt buys
    # more reasoning out of the same ceiling. The first 7-chunk request measured:
    #
    #   prompt 3,479 tokens -> thinking 2,876 + completion 120 = 2,996 against a 3,000 cap
    #   finishReason MAX_TOKENS, parse_path salvaged_json
    #
    # The answer survived only because the JSON salvage path caught a truncated object.
    # That is one chunk of prompt away from a blank reply — the exact failure this whole day
    # was spent on — so the ceiling moves with the thing that pushed it.
    gemini_max_output_tokens: int = Field(default=6000, ge=1)

    # -1 lets the model decide, 0 disables thinking. Measured on "how many numbered parts
    # does this document contain": with thinking it answered 5 (correct) in 5.2s; the local
    # model answered 4 in 59.1s.
    gemini_thinking_budget: int = -1

    gemini_timeout_seconds: int = Field(default=120, ge=1)

    # Which backend answers when the request does not say. Local, deliberately: the
    # privacy-preserving option is the one you get by forgetting to choose.
    default_generation_backend: str = "local"

    # Print the full retrieval/generation report to the terminal for EVERY request.
    #
    # OFF BY DEFAULT. Day 12's tests/test_log_redaction.py asserts no document text reaches
    # the log, because every value this service handles is a user's question, their
    # document's contents, or an answer derived from both. This writes exactly that, on
    # purpose, for demonstrations — enabling it knowingly trades the guarantee away.
    #
    # A separate switch rather than a log level: a log level is what someone turns up during
    # a production incident, which is precisely when this must stay off.
    verbose_trace: bool = False

    # --- where the logs go (Day 18) -----------------------------------------
    #
    # They went NOWHERE. Logging was one StreamHandler to stderr, so every diagnostic —
    # including the structured answer trace added today, whose whole purpose is to make a
    # bad answer diagnosable AFTER the fact — lived in terminal scrollback and died with the
    # window. "Where are the logs saved?" had the answer "they are not".
    # RECORDING THE PROMPT TO DISK. Day 19, requested explicitly, and it TRADES AWAY the
    # guarantee the rest of this logging was built around — so it is a setting of its own
    # rather than a side effect of any other.
    #
    # With this on, the full prompt is written twice: `logs/prompts.log` for reading, and a
    # `prompt` object inside each `logs/answers.jsonl` record for grepping by trace id. The
    # prompt CONTAINS THE RETRIEVED CHUNKS, so both files then hold document text and
    # answers.jsonl is no longer the redacted artifact its docstring describes. A rotated
    # log becomes a partial copy of the corpus, readable by anyone who can read logs.
    #
    # DEFAULT FALSE, and the default is the point. Turning this on must be a decision
    # somebody made and can be asked about, not something inherited by a deployment that
    # copied a .env. `tests/test_log_redaction.py` asserts the off state still leaks
    # nothing, which is what keeps the default honest.
    log_prompts: bool = False

    log_dir: str = "logs"
    log_to_file: bool = True
    # Rotation is not optional here. 11,531 orphaned upload files were cleaned out of this
    # project two days ago; an unbounded log file is the same mistake with a different name.
    log_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)
    log_backup_count: int = Field(default=5, ge=0)

    torch_threads: int = 0  # 0 = leave torch's default alone
    load_models: bool = True  # tests set false; nothing else should


    @field_validator("gemini_model", "embedding_model", "generation_model", mode="after")
    @classmethod
    def _strip(cls, value: str) -> str:
        """Whitespace in a model name is invisible and fatal.

        `GENAI_GEMINI_MODEL="gemini-3.1-flash-lite "` — a trailing space inside the quotes —
        was URL-encoded into the request path as `gemini-3.1-flash-lite%20:generateContent`
        and answered 400 Bad Request. The .env file looked right, the setting loaded without
        complaint, and the only evidence was a %20 in a log line.
        """
        return value.strip()

    @field_validator("gemini_api_key", mode="after")
    @classmethod
    def _blank_key_is_no_key(cls, value: SecretStr | None) -> SecretStr | None:
        """An empty or whitespace-only key is ABSENT, not configured.

        Found on Day 18b while testing the new failure records. `GENAI_GEMINI_API_KEY=` in a
        .env file — the natural way to write "I have not set this yet" — parses as
        SecretStr(''), which is not None, so `_select_backend` accepted it as configured and
        the service went on to call Google with an empty key. The user would have got a
        400 from Google relayed as "the cloud model refused the request (HTTP 400)" instead
        of the accurate "Gemini was requested but no API key is configured".

        Same shape as the Day 13 bug where a trailing space inside .env quotes became %20 in
        a request path: the file looked right, the setting loaded without complaint, and the
        only evidence was in the failure.
        """
        if value is not None and not value.get_secret_value().strip():
            return None
        return value

    @field_validator("gemini_model", "embedding_model", "generation_model", "db_name",
                     mode="after")
    @classmethod
    def _must_not_be_blank(cls, value: str, info) -> str:
        """An empty name is never a usable one, and every one of these fails LATE.

        `GENAI_DB_NAME=""` builds a DSN that is rejected at the first query — i.e. at the
        first user's question, not at startup. An empty model name fails when the loader
        thread reaches it, ~40 seconds in, by which point /health/ready says "loading".
        """
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("default_generation_backend", mode="after")
    @classmethod
    def _known_backend(cls, value: str) -> str:
        """MEASURED: `GENAI_DEFAULT_GENERATION_BACKEND=gpt4` was accepted, and then
        `_select_backend` compared it to "gemini", found it different, and served LOCAL.
        The operator asked for a backend that does not exist and got a working service
        answering from a different one — no error, no log line, nothing to notice."""
        allowed = {"local", "gemini"}
        if value.strip() not in allowed:
            raise ValueError(f"must be one of {sorted(allowed)}")
        return value.strip()

    @field_validator("prompt_template_version", mode="after")
    @classmethod
    def _known_template(cls, value: str) -> str:
        """Imported lazily: app.prompts imports nothing from config, and importing it at
        module scope here would make that circular."""
        from app.prompts.templates import ALL_TEMPLATES

        known = {t.version for t in ALL_TEMPLATES}
        if value.strip() not in known:
            raise ValueError(f"must be one of {sorted(known)}")
        return value.strip()


def load_settings() -> Settings:
    """Build the settings, or fail at STARTUP with the environment variable named.

    DAY 17. Pydantic already reported which FIELD was wrong; it could not know the variable
    an operator actually sets, because `env_prefix` turns `default_min_score` into
    `GENAI_DEFAULT_MIN_SCORE`. Being told to fix `default_min_score` when nothing by that
    name exists in your shell or your .env is a small cruelty at exactly the wrong moment.

    WHY STARTUP AND NOT FIRST USE. Measured before this existed: of eleven deliberately bad
    values, TEN were accepted silently. `GENAI_OVERFETCH_FACTOR=0` made every query retrieve
    nothing, with no error anywhere. `GENAI_DEFAULT_MIN_SCORE=5.0` put the floor above the
    maximum possible cosine similarity, so every question came back insufficient_context and
    the service looked healthy. A process that starts and then quietly does the wrong thing
    is the failure mode this project keeps finding; refusing to start is the cheap version.
    """
    from pydantic import ValidationError

    try:
        return Settings()
    except ValidationError as invalid:
        lines = []
        for error in invalid.errors():
            field = str(error["loc"][0]) if error["loc"] else "?"
            # .get with a default: model_config is a TypedDict and env_prefix is optional
            # on it, so indexing is a type error even though this class always sets one.
            prefix = Settings.model_config.get("env_prefix", "")
            variable = f"{prefix}{field.upper()}"
            lines.append(f"  {variable}: {error['msg']}")
        raise SystemExit(
            "Refusing to start — the GenAI service configuration is invalid:\n"
            + "\n".join(lines)
            + "\n\nThese are environment variables, and may also be set in genai-service/.env"
        ) from None


settings = load_settings()
