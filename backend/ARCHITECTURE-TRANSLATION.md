# Backend Framework Translation

**Day 18 — Architecture.** Which of my decisions were Spring decisions, and which were architecture decisions?

I can only tell by asking what survives a change of stack. That question is the whole document. A table mapping `@RestController` to `app.get()` would be accurate and worthless — I can look that up in ten minutes, and it has no opinion about which of my choices were actually mine.

The test I apply to every decision below: **if I rebuilt this API in Express tomorrow, does the decision come with me?** The answers sort into four groups, and the sorting is the point.

---

## A. Architecture — travels unchanged

These I'd make again in any stack. Nothing about them is Spring; Spring just happened to be where I met them.

**Cross-user access returns 404, never 403.** A 403 confirms the resource exists and leaks the id space. This is a statement about HTTP semantics and information disclosure — no framework has an opinion on it.

**Ownership belongs in the WHERE clause, not in a check after loading.** `findByIdAndOwner_Id` rather than `findById` followed by comparing owners — so the leak-free 404 falls out of the query instead of having to be remembered at every call site. In Django that's `Model.objects.filter(id=pk, owner=request.user).first()`; in SQLAlchemy a `.where()` clause.

Only half of my original justification belongs in this section, though. I gave two reasons, and they are not the same kind of reason. *"The 404 falls out for free"* is architecture and travels. *"There is no window in which I hold a row I'm not entitled to"* is largely an **ORM artifact**: `findById` returning a fully-formed object is what makes load-then-check tempting in the first place. Writing SQL directly, you are already composing a WHERE clause, so the antipattern barely suggests itself. The decision is the same everywhere; the **risk of getting it wrong is highest in exactly the stacks that hand you an object** — which properly makes that half a group-D item, not a group-A one.

**The refresh token is deliberately not a JWT.** A JWT you cannot revoke needs a blocklist, and a blocklist is the server-side lookup you adopted JWTs to avoid. So: short-lived signed access token, opaque revocable refresh token stored as a SHA-256 digest. This is a reasoning chain about credential lifetime, not about Java.

**`forgot-password` always returns 202.** Reporting "no such user" turns the endpoint into an account-existence oracle. Framework-independent.

**A password reset revokes every existing session.** Resetting is what someone does when they believe they're compromised; leaving sessions alive means the attacker keeps access.

**Passwords capped at 72 bytes.** Bcrypt silently truncates beyond that, so anything longer *looks* stronger while doing nothing. That's a property of bcrypt, and bcrypt is in every stack.

**Migrations are forward-only and an applied one is never edited.** Editing V8 breaks its checksum and corrupts the history. Flyway, Alembic, Django migrations, Knex — all identical on this point.

**Single-flight refresh on the client.** Rotation is single-use, so concurrent refreshes present a spent token, which the server correctly reads as reuse and answers by revoking the family. The client must dedupe. This is imposed by *my server's security design*, not by any framework on either side — the most stack-independent thing I learned all month.

---

## B. Spring mechanisms with direct equivalents elsewhere

The pattern is universal; only the mechanism is Spring's.

| What I built | Spring | Express | NestJS | Django/DRF | FastAPI |
|---|---|---|---|---|---|
| One place renders the error envelope | `@RestControllerAdvice` | error middleware `(err, req, res, next)` | Exception Filters | `EXCEPTION_HANDLER` | `@app.exception_handler` |
| Declarative atomicity | `@Transactional` | manual `BEGIN`/`COMMIT` or ORM wrapper | `@Transaction` / manual | `@transaction.atomic` | manual session `begin()` |
| Request validation | Bean Validation (`@NotBlank`, `@Size`) | `express-validator`, Zod | `class-validator` pipes | serializer fields | Pydantic |
| Typed config from env | `@ConfigurationProperties` | `process.env` + Zod | `ConfigModule` | `settings.py` | `pydantic-settings` |
| Cross-cutting request work | servlet filters | `app.use()` middleware | Middleware/Guards/Interceptors | middleware | dependencies + middleware |
| Dependency injection | constructor injection | none (manual wiring) | Angular-style DI | none (module imports) | `Depends()` |

**NestJS is the closest relative by a distance.** Controllers, providers, modules, DI, decorator-driven — my code would translate almost structurally. Express is the furthest: no DI, no declarative anything, everything explicit.

The `@RestControllerAdvice` → error-middleware translation is worth dwelling on because the *pattern* I'd keep is: a domain exception carrying a code and an HTTP status, and exactly one place that turns it into a response body. My `DomainException(message, ErrorCode, HttpStatus)` is a plain data-carrying class. It works identically as a JS class extending `Error`, or a Python exception subclass. **Yesterday's bug proves the pattern matters more than the mechanism**: `DocumentValidationException` extended `RuntimeException` instead of `DomainException`, so the handler never saw it and every rejected upload returned 500. That's not a Spring bug — it's an exception-hierarchy bug, and I could write it in any language.

---

## C. Spring/JVM artifacts — these do not travel

The most valuable section, because these are the things I learned as "how backends work" that are really "how *this* backend works."

**Dirty checking.** Day 9: mutate a managed entity inside a transaction and Hibernate persists it with no `save()` call. I filed this as "how persistence works". It is not. Django's ORM requires an explicit `.save()` — forget it and nothing happens, silently. SQLAlchemy's unit-of-work with autoflush is close to Hibernate; Django is not. Prisma and TypeORM's active-record mode need explicit saves too. **So the single most surprising thing I learned about persistence is a Hibernate feature, not a database concept.**

**Lazy loading and `LazyInitializationException`.** A JPA proxy artifact. The reason `UserRepository` uses `@EntityGraph` to fetch roles eagerly is that authentication happens outside an open persistence context. Django has no equivalent exception — it re-queries transparently, which trades a loud failure for a silent N+1. **Same underlying hazard, opposite failure mode**: Hibernate throws, Django quietly does 50 queries. I'd rather have the exception.

**Servlet filter ordering.** `TraceIdFilter` → CORS → security → request logging, expressed through `@Order` values and Spring Security's chain sitting at −100. I spent real time on this and hit a genuine bug: `JwtAuthenticationFilter` removed `userId` from MDC in a `finally` while `TraceIdFilter` already ended every request with `MDC.clear()`, so the inner cleanup wiped the value before the outer request-logging filter wrote its line — every authenticated request logged as `anonymous`. **In Express this ordering confusion largely evaporates**: middleware runs in the order you call `app.use()`, visibly, in one file. The bug I hit needed two filters with numeric orders and an implicit nesting relationship to exist at all.

**MDC and thread-locals.** MDC is a thread-local, which works because a servlet container gives each request a thread. Node is a single-threaded event loop — there are no request threads to hang context on, so `AsyncLocalStorage` is the analogue. The thread-reuse leak I designed around (Tomcat reuses threads, so a `ThreadLocal` without a guaranteed clear lets request N+1 inherit request N's user) **cannot happen in Node** — but a new class can: async context is lost across improperly propagated `await` boundaries. Not fewer bugs. Different bugs.

**Jackson polymorphic deserialization.** `ActionRequest` uses `@JsonTypeInfo(use = NAME, include = EXTERNAL_PROPERTY, property = "type", visible = true)` plus `@JsonSubTypes` to pick a payload class from a sibling `type` field. The `visible = true` is there because Jackson otherwise *consumes* the discriminator and leaves the field null. That is a Jackson quirk, and knowing it is worth nothing elsewhere. **Pydantic does this far better**: a discriminated union with `Field(discriminator='type')` is one line and the discriminator stays visible by default. In Express there is no mechanism at all — you `switch` on `body.type` and validate manually.

**Records stringifying their secrets — the hazard travels, the fix differs.** I overrode `toString()` on `LoginRequest` and friends because a Java record's generated `toString()` prints every component, so any log line interpolating it leaks the password. Python dataclasses have exactly the same problem via `__repr__`, and `console.log(obj)` in Node prints everything. **But Pydantic ships `SecretStr`, whose `__repr__` is `**********` by default** — a first-class solution to a problem Spring makes me solve by hand, per class, and remember to keep solving. That's a point *against* Spring.

---

## D. Same decision, different risk — where the framework's value shows

Translation that preserves the guarantee but changes how easy it is to lose.

**`@Transactional` → manual commit.** My Day-9 multi-step mutation writes a user message, an AI message, and updates the session's denormalised preview. In Spring the annotation makes partial failure impossible without my thinking about it. In Express I'd open a transaction, pass the client through every call, and commit — and a forgotten `await tx.commit()` or an early `return` inside the `try` is a silent correctness bug.

Worse than silent: **non-local**. A transaction opened and never committed or rolled back holds its pooled connection. Leak enough of them and the pool starves, at which point the symptom is *unrelated* requests hanging — nothing points at the endpoint that actually did it. So the failure is not just invisible at the site of the mistake, it surfaces somewhere else entirely, under load, as a availability problem rather than a correctness one. **Same guarantee, and Spring removes an entire category of way to lose it.** Django's `@transaction.atomic` is as good; FastAPI with SQLAlchemy sits in between.

There's a sharper version of this from yesterday: **revoke-then-throw in one transaction is a silent no-op**, because the rollback undoes the revocation while the 401 still returns. That trap exists in *every* stack with transactions — but the declarative annotation is what made it invisible, because I never wrote the commit and so never thought about when it happened. **Spring's convenience is exactly what hid the bug.**

**Closed-by-default security.** `.anyRequest().authenticated()` is one line and covers every endpoint written from now on. In Express, auth is middleware you apply per-route or per-router, so "closed by default" takes deliberate structuring (a catch-all `app.use(requireAuth)` before route registration) and a new route mounted in the wrong place is silently public. My allowlist-over-blocklist decision is architecture — but Spring makes the safe version the easy one, and Express does not.

**Ownership scoping across a join.** `tasks` has no `user_id`; ownership runs `tasks.source_session_id → chat_sessions.user_id`. In Spring Data that's an explicit `@Query` with a JOIN. Django's ORM expresses it more naturally as `Task.objects.filter(source_session__user=request.user)` — traversing relations with `__` is genuinely nicer than writing JPQL. **A point against Spring**, and one I wouldn't have noticed without asking the question.

---

## E. The anchor: `POST /api/ai/actions` in four stacks

One endpoint that touches everything — routing, polymorphic body parsing, validation, ownership, transactions, audit, error mapping. What it does: validate the body, confirm the session belongs to the caller (404 if not), **always** write an audit row, execute the side effect **only** if approved, return the execution status.

**Spring (what exists).** `@PostMapping` + `@Valid @RequestBody ActionRequest` + `@CurrentUserId UUID`. Jackson resolves the payload subtype; Bean Validation rejects a bad one as 400 via the advice. `@Transactional` on the service makes audit-plus-task atomic. `existsByIdAndUser_Id` is the ownership check; `ChatNotFoundException` maps to 404.

**NestJS.** Nearly one-to-one. `@Post()`, a `ValidationPipe` with `class-validator`, a `@UseGuards(JwtAuthGuard)`, a custom `@CurrentUser()` param decorator, an Exception Filter for the envelope. Polymorphic payload is the weak spot — `class-transformer`'s `@Type` with a discriminator is clumsier than Jackson.

**FastAPI.** The most elegant of the four for this endpoint. The polymorphic payload is a `Union[CreateTaskPayload, SummarizePayload, LookupPayload]` with `Field(discriminator='type')` — cleaner than my Jackson annotations and it returns a 422 with per-field detail automatically. `current_user: User = Depends(get_current_user)` replaces `@CurrentUserId`. The cost: the transaction is a `with session.begin():` I must not forget.

**Django/DRF.** A serializer validates and a `@transaction.atomic` view does the work. The polymorphic payload is the awkward part — DRF has no native discriminated union, so it's a custom `to_internal_value` that switches on `type`. But `ChatSession.objects.filter(id=..., user=request.user).exists()` is the nicest ownership check of the four.

**Express.** Everything explicit. `router.post('/ai/actions', requireAuth, async (req, res, next) => ...)`, Zod for validation (Zod's `discriminatedUnion` is genuinely good), a manual `pg` transaction with try/commit/rollback, and `next(err)` into error middleware. Most code, least magic — and the only one where I could forget the commit.

---

## F. What I'd actually conclude

**Spring gave me three things I'd miss:** declarative transactions (an entire class of bug removed), a security filter chain that is closed by default in one line, and constructor DI that makes services testable without ceremony.

**Three things I'd rather have elsewhere:** Pydantic's discriminated unions over Jackson's annotations, Pydantic's `SecretStr` over hand-written `toString()` overrides, and Django's relation traversal over hand-written JPQL joins.

**And the honest one:** the convenience that makes Spring pleasant is the same convenience that hid the revoke-then-throw bug from me. I never wrote a commit, so I never thought about when it happened. A framework that does something for you is a framework that stops you noticing it — which is fine until the day you need to reason about exactly that thing.

**The debugging tax is stack-specific, and it is not small.** Setting the four groups aside, it is worth counting what I actually spent debugging time on this month. Bugs in my API's own logic: the duplicated reply path that stopped the first chat message proposing an action; documents stuck at `pending` because nothing advanced the status; citations never wired between a table and a UI that both already existed; the exception hierarchy that turned every rejected upload into a 500.

Bugs that were pure artifacts of the stack: MDC double-ownership between two filters; Jackson's `visible = true` consuming the discriminator; a Java record's `toString()` printing a password; Logbook's TRACE default logging request bodies; Jackson 2 versus Jackson 3 under Boot 4. And on the frontend: `window.open` returning null under `noopener`, React StrictMode's double-invoke defeating a transition guard, a remount resetting a `useRef`, and a CSS block that did nothing because a bare element selector loses to a class.

That is close to an even split, and the second list is the one that does not transfer. **The domain problem — scoping, token lifetimes, audit, error envelopes — is portable. The debugging tax is rent paid to a specific stack.** Worth remembering when estimating work in an unfamiliar one: the design will go about as fast as it did here, and the debugging will not.

**The success criterion — can I explain how this API would be built in another stack?** Yes, and the useful form of that answer isn't a translation table. It's this: about two thirds of what I built is architecture and comes with me unchanged, most of the remaining third has a direct equivalent, and the genuinely Spring-specific parts are dirty checking, lazy-loading semantics, filter ordering, MDC thread-locals, and Jackson's polymorphism. **Those five are the list of things I should be careful not to describe as "how backends work" in an interview.**
