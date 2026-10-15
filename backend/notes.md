# AI Workplace Knowledge Assistant — Backend Notes (Month 2)

Java + Spring Boot + PostgreSQL. Replacing the Month-1 mock API with real endpoints, persistence, validation, and tests, against the frozen Day-21 contract.

Teaching rule: I write every line of code; AI guides concepts and reviews like a senior. Success target: Spring Boot replaces the mocks with no frontend screen rewrites.

---

# Backend Day 1 — Spring Boot orientation + package map

Scaffold the project, map the product to modules. The Day-21 API contract is the input.

## Environment (from scratch — no Java installed)
- **JDK 21** via Homebrew (`brew install openjdk@21`). Managed/work Mac → not in sudoers, so skipped the system symlink; the PATH export alone is enough: `export PATH="/usr/local/opt/openjdk@21/bin:$PATH"` in `~/.zshrc`. Intel Mac → Homebrew paths are `/usr/local/...` (not `/opt/homebrew/...`).
- **IntelliJ IDEA**, Maven. Registered JDK 21 via Project Structure → SDKs (IntelliJ had auto-downloaded JDK 26 and was defaulting to it — fixed so build + runtime both = 21, matching `pom.xml`).

## Scaffold — Spring Initializr
- Maven, Java 21, Jar. Group `com.bluestone`, Artifact `knowledge-assistant`.
- **Spring Boot 4.0.7** — the timeframe only offered 4.x (3.x is past its window). Chose 4.0.7: settled non-SNAPSHOT (avoid SNAPSHOT = nightly; avoid newest 4.1.0 = least docs). Tax: most tutorials are 3.x, so some artifact names differ (`spring-boot-starter-webmvc` not `-web`; split `-test` starters) and some autoconfig classes moved packages.
- **4 dependencies, chosen deliberately:** Spring Web (REST + embedded Tomcat), Spring Data JPA (persistence), PostgreSQL Driver (JDBC connector), Validation (Bean Validation). Did NOT add Security (demo login only; Security locks every endpoint by default), Lombok (see plain Java first), Flyway (Day 3).
- **Package = `com.bluestone.knowledge_assistant`** — underscore because the hyphen in the artifact is illegal in Java packages. Non-idiomatic but left as-is; not worth renaming mid-setup.

## Spring concepts learned
- **Inversion of control / dependency injection:** you *declare* what you need (`@Service`, `@RestController`, `@Repository`) and Spring instantiates + wires the beans. A controller doesn't `new` its service — it declares the dependency in its constructor; Spring injects it. Big shift from school-Java hand-wiring.
- **Auto-configuration:** Spring wires machinery from what's on the classpath. `spring-boot-starter-webmvc` → embedded Tomcat on 8080, zero config. JPA + Postgres driver → tries to open a DB connection at startup.

## The boot problem + lessons
- First run **failed** (expected + informative): `Failed to configure a DataSource` — JPA/Postgres auto-config tried to connect at startup with no DB. Bean chain `entityManagerFactory → dataSource` collapses; Spring aborts. **All-or-nothing bean wiring** — can't boot halfway.
- Fix for "boot empty today": **the properties exclude (`spring.autoconfigure.exclude`) did NOT work in Boot 4.x**. The **annotation exclude did**: `@SpringBootApplication(exclude = { DataSourceAutoConfiguration.class, HibernateJpaAutoConfiguration.class })` — read earliest, before the auto-config list is built. Had to exclude BOTH (DataSource alone left JPA still building `entityManagerFactory`).
- **4.x moved autoconfig packages** — 3.x import paths didn't resolve. Lesson: don't guess imports — cursor on red symbol → **⌥Return → Import class**, let IntelliJ find the real path.
- `// TODO: remove these excludes on Day 3-4 when PostgreSQL is configured` — temporary scaffolding.
- Clean boot: `Started KnowledgeAssistantApplication in ~2s`, Tomcat on 8080, Java 21.

## Deliverable: feature-first package map
Under `com.bluestone.knowledge_assistant`:
```
auth   document   chat   action   task      (feature domains)
common   config                             (cross-cutting)
```
- **Feature-first over layer-first:** the Day-21 contract is grouped by resource, so packages mirror it. Each feature holds its full vertical slice — `controller`, `service`, `repository`, `entity`, `dto` as sub-packages. Avoids "package explosion" of global layers; keeps a bounded context's code adjacent.
- **`common` vs `config`:** `common` = shared domain types (the `{message, code, timestamp}` error envelope, base exceptions, shared DTOs). `config` = Spring wiring (`@ControllerAdvice`, future CORS/security, DataSource beans). Business-shared vs framework-wiring → clean dependency direction.

## Environment gotchas
- Managed Mac blocks `sudo` — route around it (PATH export, not system symlink); watch for the same on `brew install postgresql` at Day 3.
- Moving the project folder while IntelliJ has it open desyncs `.idea` → close, delete `.idea`, reopen from true path. Home is `~/IdeaProjects/knowledge-assistant` — don't move it again.

## Next (Day 2)
REST fundamentals — health endpoint + base response/error DTOs (the `{message, code, timestamp}` envelope), Bean Validation, consistent HTTP status codes. First real controller.

---

# Backend Day 2 — REST fundamentals (controllers, DTOs, error convention)

First actual Spring code — the top layer of the request flow (Controller → Service → Repository → DB; today just the controller) plus the response/error conventions every future endpoint inherits.

## The health endpoint (first controller)
- `@RestController` = `@Controller` + `@ResponseBody`: marks the class a web handler; return values become the response body. A returned Java object → `HttpMessageConverter` (Jackson) inspects its fields → serializes to JSON. No serialization code, no status code (defaults 200).
- `@GetMapping("/api/health")` maps `GET /api/health` to the method. **`/api` prefix** matches the Day-21 contract (all frontend routes are `/api/*`) → uniform path segment for future gateway/proxy/CORS rules.
- Returns a `record HealthStatus(String status)` → `{"status":"UP"}`. **Verified live in browser.**

## Records for DTOs
- Java **records** (`public record ...`) = immutable data carriers, auto-generate constructor/getters/equals/hashCode/toString. Perfect for DTOs (pure data shuttling). The `Type.ts` `interface`/`type` parallel — data shapes without behavior.
- **`HealthStatus` scoped locally inside the controller** (only that endpoint uses it); **`ApiError` in `common`** (cross-cutting, returned by every endpoint via the advice). State lives at the scope that needs it — same judgment as frontend component state.

## DTO vs Entity (the boundary discipline)
- DTO = shape crossing the HTTP/network boundary. Entity (later) = shape stored in the DB. Distinct boundaries: network shape ≠ storage shape ≠ client's internal shape. Echoes the frontend lesson of excluding client-only fields (`UIMessage.status`) from the API payload.

## The error convention (the day's substance)
Three pieces:
1. **`ErrorCode` enum** (`common`) — transcribed the Day-21 code constants. **Enum over String:** backend *owns* the closed code set (source of truth), so the compiler should enforce it — a `String` lets `"DOCUMENT_NOT_FUND"` compile and silently break the frontend (the stringly-typed / undefined-CSS-token bug class). Jackson serializes the enum to its `.name()` string by default, so **the frontend still receives the plain string** (`"FILE_TOO_LARGE"`) — zero-cost at the HTTP boundary, typo-proof internally.
2. **`ApiError` record** (`common`) — `{ message, code (ErrorCode), timestamp (Instant) }`, matching the contract envelope exactly.
3. **`GlobalExceptionHandler`** (`config`) — `@RestControllerAdvice`: a global choke point that intercepts exceptions from any controller and maps them to the standardized `ApiError` before they reach the client. **This is what makes error responses consistent automatically** — write the mapping once, every endpoint inherits it.

Handlers built:
- **Validation** (`MethodArgumentNotValidException`) → 400 + `VALIDATION_ERROR`. **Concatenates field errors into the flat `message`** ("Validation failed: email must not be blank, ...") rather than adding a `fieldErrors` array — because adding an array would modify the frozen contract schema. Honors the freeze while preserving form-UX context.
- **Malformed JSON** (`HttpMessageNotReadableException`) → 400 + `BAD_REQUEST`. Needs its own handler because it throws *before* Bean Validation runs; without it, a bad payload falls to the 500 catch-all — but a malformed body is a client error, not a server failure.
- **Catch-all** (`Exception.class`) → 500 + `INTERNAL_ERROR`. **Greedy** — intercepts everything without a specific handler, which can mask intentional statuses (a missing-route 404, a future domain 404) as a generic 500. `// TODO: add specific @ExceptionHandler per domain exception as features arrive`, relegating this to a true last-resort net. (Also: log the stack trace before masking, for prod observability.)
- Verified: `/api/boom` test route → thrown exception → `ApiError` JSON with `code:"INTERNAL_ERROR"` and 500. Probe deleted after.

## Placement
- `GlobalExceptionHandler` → `config` (heavy Spring framework annotations, HTTP-lifecycle infrastructure wiring).
- `ApiError` / `ErrorCode` → `common` (pure domain data shapes shared across modules).
- Consistent with the Day-1 `common` (domain) vs `config` (framework wiring) boundary.

## What I built (deliverables)
- `health/HealthController.java` — `/api/health` → `HealthStatus` record.
- `common/ErrorCode.java` — type-safe enum of contract error codes.
- `common/ApiError.java` — standardized `{message, code, timestamp}` envelope record.
- `config/GlobalExceptionHandler.java` — `@RestControllerAdvice`: validation / malformed-JSON / catch-all handlers.

## Next (Day 3)
PostgreSQL — install + configure the datasource (remove the Day-1 excludes), Flyway migrations, first entity + repository. The persistence layer goes live.

---

# Backend Day 3 — PostgreSQL schema + migrations

The app gains a memory. Deliverable: a versioned migration set (V1–V8) creating the full schema + seed data. Success: DB initializes with demo data for frontend integration.

## Environment
- **PostgreSQL 16** via `brew install postgresql@16` — installed clean, NO permission wall (user-space Homebrew install worked despite the managed Mac). `brew services start postgresql@16`, connected via `psql postgres`, `createdb knowledge_assistant`.
- Homebrew Postgres default: superuser = Mac username (`rayyanayub`), no password, trust-auth for local. Fine for dev; prod would use a dedicated app user with a password (note for Day 20).

## Wiring Spring → Postgres
- Added Flyway deps (`flyway-core`, `flyway-database-postgresql`).
- **Removed the Day-1 excludes** — back to plain `@SpringBootApplication`. The JPA/DataSource machinery switched off on Day 1 now runs against a real DB. Boot log confirms: `HikariPool-1 - Start completed`, `Database version: 16.14`, `Initialized JPA EntityManagerFactory` — live connection pool to Postgres.
- `application.properties`: datasource url/username(empty password), **`spring.jpa.hibernate.ddl-auto=validate`** (Flyway owns the schema; Hibernate only validates entities match — never let both fight over schema control), `show-sql=true`, `open-in-view=false` (silences the warning + cleaner default: forces loading in the service layer, not during view render).

## ⚠️ THE FLYWAY SAGA (why migrations are applied manually)
Flyway **never auto-ran** despite everything being correct. Debugged in order:
1. **File-location bug:** the migration file was created directly in `src/main/resources/db/` NOT in `db/migration/` — IntelliJ's tree *displayed* it as nested but on disk it was a sibling. `ls src/main/resources/db/migration/` returning EMPTY was the tell. Lesson: **when a path-dependent tool can't find a file that "looks" right in the IDE tree, verify the actual disk path with `ls`, not the tree.** Moved file into `migration/`, confirmed `find target/classes -name "*.sql"` → `db/migration/V1...`.
2. **Even with the file correct + `spring.flyway.enabled=true` + the dep cached (`flyway-core-11.14.1.jar` present in `~/.m2`), Flyway stayed completely silent** — no log lines at all. Signature of **Spring Boot 4.x not auto-configuring Flyway**. This is the bleeding-edge tax (4.0.7): integrations that "just work" on mainstream 3.x can silently fail on 4.x because the ecosystem hasn't caught up.
- **RESOLUTION — apply migrations manually:** `psql knowledge_assistant < src/main/resources/db/migration/Vn__*.sql`. The migration FILES remain the schema-of-record (versioned, committed, reviewable — the whole value of migrations). Only lost: auto-apply on startup. `ddl-auto=validate` stays, so Day-4 entities get validated against the hand-applied schema.
- **BACKLOG:** "Flyway auto-config silent on Spring Boot 4.0.7 — migrations applied manually via psql; revisit auto-run (may need a 4.x-specific property or workaround)."
- Side note: `./mvnw` can't run (network blocks the wrapper's Maven download) — use IntelliJ's bundled Maven / Build menu instead of the terminal wrapper.

## Schema design decisions (locked, applied to every table)
- **UUID PKs** (`id UUID PRIMARY KEY DEFAULT gen_random_uuid()`) — matches the contract's uuid-string ids, prevents enumeration, PG13+ generates server-side. One PK type across all tables (consistency).
- **Enums as VARCHAR + CHECK** (not native PG ENUM, not plain VARCHAR) — DB enforces the closed set (defense-in-depth with app validation), maps cleanly to Java enums, easy to evolve (drop/re-add constraint) vs native ENUM's `ALTER TYPE` pain. Applied to: document status, message sender, task status/priority, audit type/decision.
- **TIMESTAMPTZ** (not plain TIMESTAMP) — stores the exact instant regardless of server tz; matches the contract's ISO-8601-with-tz.
- **DTO-vs-storage boundary made concrete:** `users.password` exists in the table but NOT the `User` DTO (never returned to client). `chat_sessions.user_id` exists in the table but not the DTO (client knows its user from the token). Column named `created_at` in DB but maps to `timestamp` in the API DTO — `timestamp` is a reserved SQL word; DB follows DB conventions, API follows frontend conventions.
- **TEXT (not VARCHAR) for free-form content** — `messages.content`, `citations.excerpt`. LLM output is unbounded; a VARCHAR ceiling guarantees eventual truncation. Postgres TOAST handles large TEXT efficiently.

## The tables (V1–V7)
- **users** — id, email (NOT NULL UNIQUE — login identity), password (NOT NULL, bcrypt hash), name (nullable), created_at.
- **documents** — id, filename, size_bytes (BIGINT — future-proof past INT's 2GB), upload_date, status (CHECK, DEFAULT 'pending').
- **chat_sessions** — id, **user_id FK→users ON DELETE CASCADE** (delete account → purge their chats = privacy compliance at the DB level), title, created_at, updated_at (bumped by the service layer on new message, NOT a DB trigger — keep business logic visible in Java), last_message_preview (nullable).
- **messages** — id, **session_id FK→chat_sessions CASCADE**, content (TEXT), sender (CHECK), created_at. **Composite index `(session_id, created_at)`** — the dominant query is "messages for session X ordered by time"; not premature, it serves the one real access pattern.
- **tasks** — id, title, priority (CHECK), status (CHECK, DEFAULT 'todo'), created_at, completed_at (nullable, no default — set on →done / cleared on →not-done by the bidirectional PATCH logic), **source_session_id FK→chat_sessions CASCADE**.
- **action_audit** — id, action_id (VARCHAR — proposal ids are formatted strings like `act-...`, not UUIDs), **session_id FK→chat_sessions CASCADE**, type (CHECK), decision (CHECK), created_at.
- **citations** — the two-FK table, opposite delete behaviors:
    - **message_id FK→messages ON DELETE CASCADE** — a citation is owned child data, meaningless without its message.
    - **document_id FK→documents ON DELETE RESTRICT** — a document is a shared global resource; RESTRICT throws a hard DB error if you try to delete a cited document. **This structurally enforces the Day-12 dangling-citation fix** — the orphan is now IMPOSSIBLE by construction, not by defensive app code.

## Seed data (V8)
- Hardcoded predictable UUIDs (`1111.../2222...`) so relationships are visually traceable in the file and the script is perfectly reproducible.
- Seeded: demo user, 4 documents (matching the frontend catalog), 1 session, 2 messages (user+assistant), 1 task, 1 citation, 1 audit entry — exercises every table including the two-FK citation.
- **Password:** seeded a bcrypt hash (so Day-5 login "just works" — a plaintext seed would make `BCryptPasswordEncoder.matches()` fail). **⚠️ TODO: the seeded hash must be verified to decode to the actual demo password on Day 5 — a copied example hash won't match.**

## Verification (all passed)
- All 7 tables in `\dt`. SELECTs confirm user, documents (correct statuses), messages.
- **RESTRICT proven live:** `DELETE FROM documents WHERE id=<cited doc>` → `ERROR: ... violates foreign key constraint "citations_document_id_fkey" ... still referenced from table "citations"`. The DB refused to orphan the citation. The dangling-reference bug is structurally impossible.

## Next (Day 4)
Persistence — JPA entities + repositories + service layer. Map each table to a `@Entity`, create `JpaRepository` interfaces, write service methods to create/retrieve. `ddl-auto=validate` will check the entities match the hand-applied schema.

---

# Backend Day 4 — Persistence (entities, repositories, service layer)

The seven tables become Java objects. Completes the layered stack: Controller → **Service → Repository → Entity → DB**. Success: services can create and retrieve.

## The three new layers
- **Entity** (`@Entity` + `@Table(name=...)`) — maps a class to a table, fields to columns. JPA/Hibernate ORM translates Java objects ↔ SQL.
- **Repository** — an *interface* extending `JpaRepository<Entity, IdType>`. Spring Data generates the impl at runtime: `save()`, `findById()`, `findAll()`, `delete()` for free. Near-zero-code CRUD.
- **Service** (`@Service`) — business logic + transaction boundaries. Constructor-injects the repository (the DI from Day 1: service declares the need, Spring provides).

## `ddl-auto=validate` earns its keep
Entities must map EXACTLY to the hand-built schema (right table, column names, types). A mismatch → Hibernate aborts startup with a clear "missing column" error. Clean boot + `Found N JPA repository interfaces` = the mapping is correct. This is the payoff of Day 3's `validate` choice — entity/schema drift caught immediately.

## Mapping decisions (locked, applied to every entity)
- **Explicit `@Column(name = "snake_case")`** over Hibernate's implicit CamelCase→snake_case strategy — the schema is the hand-rolled source of truth; explicit annotations make the entity self-documenting and immune to a framework-version change in the implicit rule.
- **`@Id @GeneratedValue(strategy = GenerationType.UUID)`** — Hibernate generates the UUID *app-side* before INSERT, so JPA holds the id in its first-level cache immediately (vital for cascading relationships before commit). The DB's `DEFAULT gen_random_uuid()` becomes a safety net for raw-SQL inserts (the seed data) but is dead code for JPA inserts.
- **Java `enum` + `@Enumerated(EnumType.STRING)`** for CHECK-constrained columns — consistency with Day-2 `ErrorCode`, compile-time safety (can't write `setStatus("reedy")`). **STRING is critical** — the default ORDINAL stores integers (`0,1,2`), which breaks the CHECK constraint and shatters if you reorder the enum. Enum constants left lowercase (`pending`) to match the DB's lowercase CHECK values — pragmatism over Java UPPERCASE convention (avoids writing a custom `@Converter`).
- **Strict Entity ↔ DTO separation** — returning entities directly leaks DB columns (`password`, `Message.status`) to the client unless littered with `@JsonIgnore`, which couples HTTP serialization into the mapping layer. API contract (DTO) and storage contract (Entity) stay distinct; mapping happens in the service.
- **Immutability discipline** — protected no-args constructor (JPA requires it), public constructor for real creation, getters for all, setters ONLY on mutable fields (e.g. `Document.status`).

## `@Transactional` placement
Class-level `@Transactional(readOnly = true)` as the default (reads bypass Hibernate dirty-checking — a real optimization), method-level `@Transactional` override on writes (`createDocument`) for a full read-write atomic transaction. Idiomatic pattern.

## Proven end-to-end (Document slice)
A throwaway `CommandLineRunner` exercised the full chain: `getAllDocuments()` → repo → Hibernate SQL (`select ... from documents`) → Postgres returned the 4 seeded rows → mapped back to entities (enum read back correctly as `ready`/`processing`). Then `createDocument(...)` → `insert into documents ...` with app-generated UUID + `status=pending`, confirmed the row landed via psql. Both create + retrieve proven. Runner + test row deleted after (scaffolding, doesn't ship — same discipline as the Day-2 `/api/boom` probe).

## The @ManyToOne relationship (the genuinely-new concept)
Built `User` (standalone) + `ChatSession` (FK → users) to learn relationship mapping:
```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "user_id", nullable = false)
private User user;
```
- **Object reference (`private User user`) vs raw `UUID userId`** — chose the object (standard JPA, enables navigation `session.getUser().getEmail()` for future auth/audit). Raw-UUID is simpler and dodges proxy overhead; kept in back pocket if complexity demands. (Many teams prefer raw FK ids precisely to avoid lazy-loading headaches — a real trade, not a wrong choice either way.)
- **`FetchType.LAZY`** — loading a session does NOT fetch its User; Hibernate puts a proxy in the field and hits the DB only if `getUser()` is called. Right default (don't fetch what you might not need), BUT the famous failure mode: **`LazyInitializationException`** — if the txn closes and *then* something calls `getUser()` (e.g. during JSON serialization in the controller), the DB session is gone → throws.
- **The architecture makes this fail SAFELY:** `open-in-view=false` (Day 3) + entity/DTO separation (today) structurally force mapping entities→DTOs *inside* the `@Transactional` service boundary. A forgotten proxy fails fast/loud in the service, not mysteriously during serialization. Three days of decisions compounding into the #1 JPA gotcha being debuggable-by-design. (Implication for Day 8: load everything you need inside the service; never lazily navigate after the service returns.)

## Scope decision (YAGNI)
Built `Document` (full slice: entity+repo+service, proven) + `User`/`ChatSession` (entity+repo, to learn FK mapping). **Deferred** `Message`/`Task`/`ActionAudit`/`Citation` to their feature days — building them now = unexercised code sitting until Day 8-10. Every persistence piece should be immediately wired to a controller and tested end-to-end. Services for User/ChatSession also deferred (come with auth Day 5 / chat Day 8).

## Cleanup owed
- Confirm `spring.jpa.open-in-view=false` is actually saved in `application.properties` — the boot log still shows the "enabled by default" warning, meaning it may not be applied. This setting is load-bearing: the whole lazy-loading safety argument depends on it being OFF.

## Next (Day 5)
Auth — `POST /auth/login` matching the Month-1 contract. FIRST TASK: generate the real bcrypt hash of `securepassword123` via the actual `BCryptPasswordEncoder` and UPDATE the seeded user (the current seeded hash is a well-known hash of `"password"`, won't match). Then the login endpoint, user context, the auth boundary.

---

# Backend Day 5 — Authentication (POST /auth/login)

First fully-realized endpoint with a request body, validation, and business logic. Success: frontend demo login works against Spring Boot. Converged several deferred pieces: the `UserRepository` finder + `UserService`-equivalent (Day 4), and the bcrypt hash (Day 3).

## Scope decisions (both YAGNI, both correct)
- **BCrypt-only, NOT full Spring Security** (Option A). Added just `spring-security-crypto` for the encoder; did NOT add `spring-boot-starter-security`. Reason: the full starter enables default security that 401s EVERY endpoint (including `/api/health`) until a `SecurityFilterChain` bypass is written — a big detour for a demo login. Route protection is Day 16's job ("security-basics"). Today just needs secure hash comparison.
- **Simple token, NOT JWT.** Returned `"demo-token-" + UUID`. A real JWT (signing keys, claims, expiration) provides zero value now because nothing validates it (the frontend doesn't even send the `Authorization` header yet — deferred Month-2 frontend task). A UUID string satisfies the contract's shape; keeps complexity flat.

## The bcrypt hash (deferred from Day 3, done first)
- Generated via a throwaway `CommandLineRunner` using the ACTUAL `BCryptPasswordEncoder`, and **self-verified**: printed `matches("securepassword123", hash) == true`. This eliminates the silent-failure trap (the old seed hash was a well-known hash of `"password"`, would never have matched).
- `UPDATE users SET password = '<hash>'` — run INSIDE `psql` (not `psql -c "..."`) to avoid shell `$`-escaping mangling the `$2a$10$...` hash. Verified the full 60 chars landed intact. Updated `V8__seed_data.sql` too (the migration is schema-of-record). Runner deleted after.

## The login flow (all pieces)
- **`UserRepository.findByEmail(String) : Optional<User>`** — a Spring Data *derived query*: the method name generates `SELECT ... WHERE email = ?`, zero implementation written. `Optional` (missing email → empty, not null).
- **DTOs** (`auth.dto`): `LoginRequest(@NotBlank email, @NotBlank password)` — the `@Valid` finally exercises the Day-2 validation handler. `UserDto(id, email, name)` — **no password** (the exclusion boundary made concrete). `LoginResponse(UserDto user, String token)`.
- **`PasswordConfig`** (renamed from `SecurityConfig` — the class only holds a `PasswordEncoder` bean, no filter chain; honest naming + `// full Spring Security deferred to Day 16` comment) — `@Bean PasswordEncoder` = injectable Spring-managed singleton.
- **`AuthService.login()`** (`@Transactional(readOnly=true)`): findByEmail → verify with `passwordEncoder.matches()` → generate token → map entity→DTO **inside the transaction** (lazy-safe boundary from Day 4) → return.
- **`UnauthorizedException`** (`common`) + `@ExceptionHandler` → 401 `UNAUTHORIZED`, extending the Day-2 error convention.
- **`AuthController`** — `@PostMapping("/api/auth/login")`, `@Valid @RequestBody`.

## The security detail: anti-enumeration
**Identical `"Invalid email or password"` 401 for BOTH "email not found" AND "wrong password".** If the API said "email not found" vs "wrong password", an attacker could script random emails to harvest which are registered (account enumeration). Identical responses deny any signal about account existence. Easy to miss when writing "helpful" error messages.

## Verified end-to-end (4 curls, all correct)
1. Correct creds → **200**, user object with **NO password field**, a token. (Real bcrypt verify + exclusion boundary.)
2. Wrong password → **401** `UNAUTHORIZED`.
3. Nonexistent email → **byte-identical 401** to #2. (Anti-enumeration proven.)
4. Blank email → **400** `VALIDATION_ERROR` "email must not be blank". (Day-2 validation handler fires.)

Full stack behaved: controller → service → repository → DB → bcrypt → DTO. First complete endpoint.

## Next (Day 6)
Documents — `GET /api/documents` with seeded data, DTO mapping, filtering, pagination basics. The `DocumentService` (built Day 4) gets its controller; the frontend document library reads from Spring Boot. Entity→DTO mapping pattern repeats.

---

# Backend Day 6 — Documents (GET /api/documents)

The Day-4 `DocumentService` gets its controller; the frontend document library reads real rows. Success: frontend reads from Spring Boot. Adds two concepts: filtering + pagination basics.

## Pagination decision (the Day-21 contract choice comes home)
- **Returned a bare `List<DocumentDto>`, NOT the `{items,total,page,size}` envelope.** The frontend does `documents.map(...)` on an array; returning the envelope would instantly break it. This honors the exact v1/v2 split frozen in the Day-21 contract: bare array secures the immediate integration win; the Spring `Pageable` upgrade is the flagged Month-2 transition requiring a *synchronized* frontend+backend change. Deferred by contract, not by laziness.
- (When pagination does come: Spring Data's `findAll(Pageable)` → `Page<T>` gives items+total+page+size almost free, and combines with filtering: `findByStatus(status, pageable)`.)

## Filtering — optional ?status=
- **Controller:** `@RequestParam(required = false) DocumentStatus status` — omitted → Spring passes `null`.
- **Service:** ternary branch `status != null ? findByStatus(status) : findAll()` — handles null deliberately before hitting the DB.
- **Repository:** `findByStatus(DocumentStatus)` — a Spring Data *derived query*, method name → `SELECT ... WHERE status = ?`.
- Verified: `?status=ready` returned 3 docs, correctly excluding the one `processing` doc.

## DTO mapping — static from() factory
`DocumentDto.from(Document)` static factory over MapStruct. YAGNI: a mapping framework for one flat 5-field DTO is build complexity + learning overhead for no gain. Static factory = zero-dependency, encapsulates the transform, keeps the boundary explicit.
- **Entity/DTO separation even when shapes match:** API shape (network) and schema (storage) evolve independently. If a future internal column (`s3_bucket_path`) is added to the entity, a direct entity return would silently leak it. The DTO is a deliberate boundary.

## The 500→400 bug (greedy catch-all, again)
`?status=bogus` returned **500** at first. Chain: `@RequestParam DocumentStatus` → Spring tries to convert `"bogus"` → no matching enum constant → `MethodArgumentTypeMismatchException` → no specific handler → fell through to the catch-all `Exception` handler → 500. **But a bad query param is a client error (400), not a server panic (500).**
- Fix: added `@ExceptionHandler(MethodArgumentTypeMismatchException.class)` → 400 `BAD_REQUEST`, extracting the bad value + param name (`Invalid value 'bogus' for parameter 'status'`). Placed above the catch-all so it intercepts first.
- This is exactly the Day-2 "greedy catch-all" TODO playing out: the catch-all masks intent by treating every unforeseen exception as a server panic; specific handlers get added as features surface the need, relegating the catch-all to a true last-resort net.
- Note: two distinct 400 codes now — payload field errors → `VALIDATION_ERROR` (Day 5), query-param type errors → `BAD_REQUEST` (today). Intentional: a malformed body field is a validation failure; a wrong-typed param is a bad request.

## Verified (all correct)
- `GET /api/documents` → 200, bare array, all 4 seeded docs, enum serialized as strings. Frontend-compatible.
- `?status=ready` → 200, 3 docs (filtered).
- `?status=bogus` → 400 `BAD_REQUEST` (clean envelope, was 500 before the handler).

## What I built (deliverables)
- `document/dto/DocumentDto.java` — API shape + static `from()` mapper.
- `document/DocumentRepository.java` — added `findByStatus` derived query.
- `document/DocumentService.java` — `getDocuments(status)` with ternary branch + entity→DTO map.
- `document/DocumentController.java` — `GET /api/documents` with optional `?status=`.
- `config/GlobalExceptionHandler.java` — added `MethodArgumentTypeMismatchException` → 400 handler.

## Note (expected, not a bug)
Seeded `uploadDate` shows today's date (seed used `DEFAULT now()`), not the frontend mock's historical "Jul 12" dates. Harmless for integration (frontend displays whatever comes back); set explicit dates in the seed only if the demo needs specific ones.

## Next (Day 7)
Document upload — `POST /api/documents/upload`, multipart/form-data (the only multipart endpoint), metadata storage, the size/MIME validation the backend must enforce independently, upload failure handling. `createDocument` (built Day 4) gets its controller.

---

# Backend Day 7 — Document upload (POST /api/documents/upload)

The one endpoint with a genuinely new HTTP concept: multipart/form-data. `createDocument` (Day 4) gets its real controller + input. Success: frontend upload flow works against real backend validation and errors.

## Multipart basics
- A file arrives as binary chunks in a `multipart/form-data` request, split by boundary markers. Received via `@RequestParam("file") MultipartFile` — gives `getOriginalFilename/getSize/getContentType/isEmpty/getInputStream`. Contrast `@RequestBody` (single text payload → Jackson deserializes to an object). This is the ONLY multipart endpoint in the API (flagged in the Day-21 contract); field name is `file`.
- Set `spring.servlet.multipart.max-file-size=10MB` (+ max-request-size) in properties. Spring's DEFAULT is ~1MB — without the override, a valid 5MB PDF is rejected by Tomcat *before* reaching the controller.

## Storage decision (forward-looking to Month 3)
Save physical bytes to a local `uploads/` dir **and** store metadata. Metadata-only satisfies the frontend, but the Month-3 RAG ingestion service (Python/FastAPI) needs physical file access to parse/chunk/vectorize. Storing now = staging ground + clean Java-API→Python-processing handoff, avoids an endpoint rewrite later.

## Validation — independent, in the service, unified exception
- **Why backend validates even though the frontend does:** client validation is UX only, zero security — an attacker bypasses the frontend and hits the API directly (curl/Postman). Backend is the final gatekeeper.
- **Order: missing → size → type.** Fail fast: existence first (avoids NPEs on later checks), size next (don't waste CPU parsing a massive payload), type last (only once proven to exist and be manageable).
- **MIME check WITH extension fallback.** `getContentType()` is client-claimed and inconsistent — browsers send `application/octet-stream` or null for `.md`/`.csv`. If the MIME isn't in the allowed set, fall back to checking the file extension against an allowed-extensions set before rejecting. **Proven necessary:** a plain `.md` upload (no forced type) hit the fallback — strict-MIME-only would have falsely rejected it.
- All failures throw one `DocumentValidationException(message, ErrorCode)` → a single `@ExceptionHandler` maps it to the right envelope (`MISSING_FILE`/`FILE_TOO_LARGE`/`INVALID_FILE_TYPE`, all 400). Validation lives in the service (business logic); the controller stays a thin router.

## Storage safety + transaction ordering
- **Store under the generated UUID, not the original filename.** (1) Security: eliminates path traversal — `../../etc/passwd` just becomes a file named `<uuid>` on disk. (2) Collisions: two users uploading `Q3_Report.pdf` don't overwrite each other. Original filename kept only as DB metadata, never as a path.
- **Metadata-first ordering (DB row BEFORE file write).** File I/O is NOT transactional. If you wrote the file first and the DB insert failed, the DB rolls back but the file stays → orphan on disk. Saving metadata first means an `IOException` during the write triggers `@Transactional` rollback → the row is erased, state stays consistent.
- **`IOException` → `RuntimeException` to force rollback.** `@Transactional` rolls back on *unchecked* exceptions by default; `IOException` is checked, so wrapping it in a `RuntimeException` is what *triggers* the rollback (not just propagation). Load-bearing detail.
- **`Files.copy(file.getInputStream(), path)` + `.toAbsolutePath()`, NOT `transferTo` with a relative path.** `transferTo` with a relative path has a known embedded-Tomcat quirk: it resolves against a temp working dir, not the project root → mysterious failures. This was the actual Day-7 500 bug — fixed by absolute path + `Files.copy`.

## The recurring 500→400 pattern (showed up TWICE today)
Framework-level strictness preempts business logic → the framework throws *before* your service validation runs → falls to the catch-all as an opaque 500. Fixes: relax the HTTP binding OR add a specific handler.
- **Missing-file 500:** absent `@RequestParam("file")` → `MissingServletRequestPartException` before the controller ran. Fix: `required = false` → arrives as `null` → the service's `MISSING_FILE` check catches it → clean 400. (Same shape as Day-6 `?status=bogus` type-mismatch.)
- **Catch-all now LOGS `ex`** (`logger.error(..., ex)` via SLF4J). Its earlier absence made the storage-failure 500 un-debuggable — the response was sanitized and the stack trace was swallowed. The whole day is "upload failure handling," so opaque errors defeat the purpose. Now: generic message to the client, full stack trace to the server console.

## Verified matrix (all through the ApiError envelope)
- Valid `.md` → **201** + document row + file on disk named by UUID (`ls uploads/` confirmed `9bb832ea-...`, 7 bytes).
- Wrong type `.exe` → **400** `INVALID_FILE_TYPE`.
- Missing file → **400** `MISSING_FILE` (after the `required=false` fix).
- Oversized 11MB → **400**.
- `.md` no forced type → **201** (extension fallback proven).

## What I built (deliverables)
- `application.properties` — multipart size limits (10MB).
- `common/DocumentValidationException.java` — carries a domain `ErrorCode` from service to handler.
- `config/GlobalExceptionHandler.java` — added `DocumentValidationException` + `MaxUploadSizeExceededException` handlers; wired SLF4J logging into the catch-all.
- `document/DocumentService.java` — `uploadDocument`: validate (missing→size→type w/ extension fallback) → metadata-first → UUID-named storage via `Files.copy`+absolute path.
- `document/DocumentController.java` — `POST /api/documents/upload`, `@RequestParam(required=false)` for clean missing-file handling, returns 201.

## Next (Day 8)
Chat session APIs — `GET /api/chat/sessions`, session persistence. One-to-many (session→messages), user scoping, ordering. `ChatSession`/`Message` get their services + controllers. This is where the LAZY `@ManyToOne` from Day 4 gets exercised — must map entities→DTOs inside the transaction (the LazyInitializationException boundary).

---

# Backend Day 8 — Chat session APIs (GET /api/chat/sessions)

First genuinely *relational* endpoint. Exercises the Day-4 `@ManyToOne` + the LazyInitializationException boundary. Success: frontend chat session list backed by PostgreSQL.

## The lazy-loading trap — avoided BY DESIGN
`ChatSession` has a LAZY `@ManyToOne` to `User`. The trap: navigating `session.getUser()` after the txn closes → `LazyInitializationException`. **Avoided because the `ChatSessionDto` excludes user data** — the contract DTO is `{id, title, createdAt, updatedAt, lastMessagePreview}`, NO `userId` (client knows its user from the token). So `ChatSessionDto.from()` only touches already-loaded fields, never calls `getUser()`, so the Hibernate proxy is never triggered. The three-day setup (LAZY fetch + open-in-view=false + entity/DTO separation) routes around the trap by design, not luck. (It WOULD bite if the DTO needed user fields — then you'd map inside the txn.)

## User scoping (Option B — scoped query, seeded user id)
- Wrote the real scoped+ordered derived query but hardcoded `DEMO_USER_ID` in the controller with `// TODO Day 16: derive from authenticated principal`. Middle ground: learn the one-to-many scoping *mechanics* now (the tracker's concept), defer the auth-context extraction (`@AuthenticationPrincipal` from the token) to Day 16 where it belongs. Endpoints are still open (no auth enforced yet).
- **Why scope:** privacy — a user sees only their own chat history. **Proven:** inserted a session owned by a *different* user → it did NOT appear in the response (query filters by user 1111, the other session belonged to 9999).

## Ordering (baked into the derived query)
- `findByUser_IdOrderByUpdatedAtDesc(UUID)` → SQL `... WHERE user_id = ? ORDER BY updated_at DESC`. Most-recently-active session floats to top (standard chat-sidebar UX).
- **The `User_Id` underscore** explicitly tells Spring Data to traverse the nested `user` object's `id` property (vs looking for a literal `userId` field on ChatSession). Best practice for relationship traversal in derived queries — interacts with the Day-4 object-reference mapping (`private User user`, not raw UUID).
- Connects to the Day-3 denormalized `updated_at`: sorting happens at the DB level with no expensive JOIN to the messages table to find the latest message time. The denormalization was designed for exactly this.
- **Proven:** inserted a session with `updated_at = now+1hr` → it came back FIRST, ahead of the older seeded session.

## Verification discipline (the Day-18 lesson, backend edition)
A single seeded session passes "ordering" and "scoping" trivially while exercising neither. Built the conditions where each COULD fail (a second session at a different timestamp; a session owned by a different user) and confirmed they don't. A test that can't fail proves nothing. Cleaned up all test rows after.

## Scope decision: GET only
Session creation deferred to Day 9. A chat session isn't created in a vacuum — it's created atomically with the user's first prompt + the AI's initial response (the atomic `POST /chat/sessions` from the Day-21 contract). A bare `POST /chat/sessions` today → empty orphaned UI states. Creation is a messaging concern.

## What I built (deliverables)
- `chat/dto/ChatSessionDto.java` — API shape, excludes the user relationship (lazy-safe), `from()` factory.
- `chat/ChatSessionRepository.java` — `findByUser_IdOrderByUpdatedAtDesc` derived query (scoping + ordering).
- `chat/ChatSessionService.java` — read-only txn, fetch scoped sessions, map entity→DTO inside the boundary.
- `chat/ChatController.java` — `GET /api/chat/sessions`, hardcoded `DEMO_USER_ID` + Day-16 TODO.
- `chat/ChatSession.java` — added getters for the DTO factory.

## Next (Day 9)
Message APIs — `GET /api/chat/:id/messages` (route params, the messages one-to-many, chronological ordering via the Day-3 composite index) and `POST /api/chat/message` (the atomic create: persist user msg + AI response + bump session's denormalized `updatedAt`/`lastMessagePreview`). Message/session creation lands here. `Message` entity + repo get built (deferred from Day 4 per YAGNI).

---

# Backend Day 9 — Message APIs (GET messages + atomic POST message)

The meatiest chat day. First endpoint with a transactional side-effect on a parent row. Success: frontend can send and retrieve messages through Spring Boot. `Message` entity + repo built (deferred from Day 4 per YAGNI).

## Message entity — raw UUID FK (not @ManyToOne)
Mapped `session_id` as a raw `UUID sessionId`, NOT a `@ManyToOne ChatSession`. Access pattern is only "messages WHERE session_id = ?" — never navigate from a message up to its session object. Raw UUID = lightweight entity, immune to LazyInitializationException on the message side. Contrast ChatSession→User where the object ref was chosen (might load user details). Same Day-4 trade, opposite call — because the access pattern differs. `sender` → `MessageSender` enum + `@Enumerated(STRING)` lowercase (the DocumentStatus pattern).

## GET /api/chat/{sessionId}/messages
- **`@PathVariable` vs `@RequestParam`:** path variable extracts from the URI path (`/chat/{id}/messages`) — the REST standard for identifying a specific resource. Query param is for optional filtering/sorting. `sessionId` defines *which* resource, so it's a path variable. Path matches the Day-21 contract exactly (`/api/chat/:sessionId/messages`, NOT `/sessions/:id/messages`).
- **Ordering ASC** (oldest-first, reads top-to-bottom), served by the Day-3 composite index `(session_id, created_at)` — `WHERE session_id = ? ORDER BY created_at ASC` reads straight from the B-tree in order.
- **404 on nonexistent session** (`existsById` check → `ChatNotFoundException`), NOT an empty array. Empty array implies "exists but no messages"; 404 correctly signals the parent resource is invalid (masking a malformed/unauthorized id as empty would hide a client error).
- `MessageDto {id, content, sender, timestamp}` — maps `getCreatedAt()` → `timestamp` (the Day-3 reserved-word boundary: DB `created_at`, API `timestamp`). **Citations/actions deferred** (YAGNI — citations = Month-3 RAG, actions = Day 10; frontend renders text messages without them).

## POST /api/chat/message — the atomic multi-step mutation (the day's substance)
Four DB operations in ONE `@Transactional`:
1. Insert user message.
2. Insert AI message (placeholder — no LLM until Month 3; dynamic echo: "I am a placeholder AI. You said: '<content>'..." — echoing proves the data flow request→service→response, testable vs a static string).
3. Bump parent session `updatedAt = now()`.
4. Set session `lastMessagePreview` (truncated to fit VARCHAR(255)).
- **Atomicity:** all-or-nothing. Prevents partial state like "user prompt saved but AI response failed" → a broken half-exchange. First endpoint where the transaction boundary genuinely protects a multi-step mutation (prior writes were single inserts).
- **`findById` (not `existsById`) for the session lookup** — serves the 404 check AND loads the managed entity into the persistence context, so mutating its fields later auto-persists via **Hibernate dirty checking** at flush (the explicit `save(session)` is redundant — dirty checking already tracks the change; kept only for readability).
- **Denormalized side-effect in the service layer**, not a DB trigger — business logic (truncation rule, preview format) belongs in version-controlled, testable, visible app code, not opaque triggers. (The Day-3 design decision, now implemented.)
- **Returns only the assistant message** per the Day-21 contract — the client added the user message optimistically on Send; returning both would duplicate in the UI. Minimizes payload.
- `MessageRequest(@NotNull sessionId, @NotBlank content)` — `@Valid` runs the Day-2 validation handler.

## Verified end-to-end (proven in the DB, not just the 201)
- GET messages → 200, chronological. After the POST: **4 messages** (2 seeded + new user + AI), timestamps ascending.
- POST → 201, echo placeholder returned. **Atomicity + side-effect confirmed via psql:** the session row showed bumped `updated_at` AND the new `last_message_preview` = the AI text. All three effects present and consistent — the multi-step mutation committed atomically.
- GET nonexistent → 404 `CHAT_NOT_FOUND` (after a restart — an earlier run showed `VALIDATION_ERROR` from before the handler was added; stale, not a real bug).
- GET malformed UUID → 400 `BAD_REQUEST` — **the Day-6 `MethodArgumentTypeMismatchException` handler (built for `?status=bogus`) generalized to bad path variables for free.** Both trigger the same Spring exception → the global envelope is DRY and resilient.

## What I built (deliverables)
- `chat/MessageSender.java` — enum (user/assistant).
- `chat/Message.java` — entity, raw `sessionId` UUID mapping.
- `chat/MessageRepository.java` — `findBySessionIdOrderByCreatedAtAsc`.
- `chat/dto/MessageDto.java` — response shape (citations/actions deferred).
- `chat/dto/MessageRequest.java` — validated POST payload.
- `common/ChatNotFoundException.java` + `common/ErrorCode.java` (added CHAT_NOT_FOUND) + `config/GlobalExceptionHandler.java` (404 handler).
- `chat/ChatSession.java` — setters for the denormalized mutations.
- `chat/ChatSessionService.java` — read path + the atomic transactional POST.
- `chat/ChatController.java` — GET + POST, path variables + `@Valid`.

## Next (Day 10)
Actions + tasks — `POST /ai/actions` (the governance flow: log both approve/reject to audit, execute only approvals) and `GET /tasks`, using non-AI placeholder logic. The discriminated-union DTOs (ActionRequest/Result), the audit trail, task projection. `Task`/`ActionAudit` entities built. The RESTRICT/CASCADE FK behaviors from Day 3 come into play.

---

# Backend Day 10 — Actions + Tasks (POST /ai/actions governance flow + GET /tasks)

The most conceptually rich day: discriminated unions (Jackson polymorphic), the governance audit (log-both-decisions-execute-only-approvals), and the RESTRICT/CASCADE FKs at runtime. Built the last two deferred entities (`Task`, `ActionAudit`). Success: frontend action confirmation + task history work with backend data. Non-AI placeholder logic (only `create-task` does real work).

## Entities (raw UUID FKs, like Message)
`Task` (source_session_id) + `ActionAudit` (session_id) — raw UUID FKs, not object refs (queried by / written, never navigated up to session). `actionId` is **String not UUID** — proposal ids are formatted strings (`act-123`), the DB column is VARCHAR.

## The TaskStatus hyphen bug (trickiest enum of the month)
`GET /tasks` passed with the seeded `todo` task — but the enum DRIFTED from the schema. Enum had 5 values (`todo, pending, in_progress, completed, cancelled`); DB CHECK allows only 3 (`todo, in-progress, done`). Two mismatches: `pending`/`completed`/`cancelled` aren't valid DB values, and `in_progress` (underscore) ≠ `in-progress` (hyphen). `ddl-auto=validate` does NOT catch this — it validates columns/types, not CHECK values vs enum constants.
- **The hyphen is the hard part:** `in-progress` is illegal as a Java identifier, so `@Enumerated(STRING)` (which uses `.name()`) can't produce it. Fixed with a **JPA `@Converter(autoApply=true)`** (`AttributeConverter<TaskStatus,String>`) mapping `in_progress` ↔ `'in-progress'` for the DB. **Must REMOVE `@Enumerated`** — converter and `@Enumerated` conflict on the same field.
- **Two sides, one source of truth:** the enum holds its canonical string in a `value` field. `@Converter` reads it for the DB; `@JsonValue getValue()` reads the SAME value for JSON output. So `value="in-progress"` serves both DB and frontend; the Java constant stays `in_progress`. (`@JsonValue` = output; the converter = DB; enum name = Java.)
- **Proven on the value that matters:** `todo` passes trivially (no hyphen). Inserted an `in-progress` task → round-tripped DB→converter→enum→`@JsonValue`→JSON as `"in-progress"`. Test the value that can actually fail (Day-8 discipline).

## Discriminated unions — Jackson polymorphic (the crux)
- **Option A chosen: nested payload + EXTERNAL_PROPERTY discriminator.** The frozen Day-21 wire format is `{type, payload:{...}}` — `type` is a SIBLING of the polymorphic `payload`, not inside it. Contract fidelity is non-negotiable; flattening (Option B) would break the frontend.
- `ActionPayload` = **sealed interface** permitting `CreateTaskPayload`/`SummarizePayload`/`LookupPayload`. The `@JsonTypeInfo(use=NAME, include=As.EXTERNAL_PROPERTY, property="type")` + `@JsonSubTypes` go on the **`payload` field** (not the interface) — because the discriminator points at a sibling field. Advanced but correct.
- **Tested the hard part in isolation FIRST** (echo controller before any logic): `type=CREATE_TASK payloadClass=CreateTaskPayload` — proved (1) the nested payload routes to the right subtype, (2) top-level `type` isn't consumed by the discriminator (no `visible=true` needed), (3) the enums deserialize from kebab (`@JsonValue` handles INPUT too in this Jackson version — no `@JsonCreator` needed). Build-on-proven-plumbing so later failures are logic not wiring.
- Gotcha en route: a stale running process → `NoResourceFoundException: No static resource api/ai/actions` (Spring couldn't match the endpoint, fell back to static-resource handler → 500). New controllers need Rebuild + restart. `NoResourceFoundException` = "endpoint not matched", distinct from a Jackson body-parse error.

## The governance flow (POST /ai/actions)
`@Transactional`, in order:
1. **Validate session first** — `findById(sessionId)` → 404 `CHAT_NOT_FOUND` if absent. Pre-empts the FK `DataIntegrityViolationException` that would otherwise be an opaque 500 (the recurring framework-failure-masked-as-500 pattern).
2. **Always write an ActionAudit** — BOTH approved and rejected. The immutable governance log.
3. **Execute ONLY if approved** — `if (decision==approved && payload instanceof CreateTaskPayload p)` (Java 21 pattern matching on the sealed interface — type-safe extraction of `p.title()`/`p.priority()`, no cast). `create-task` inserts a real Task; summarize/lookup return canned placeholders (no LLM till Month 3); rejected → audit only.
4. **Return `ActionResult {actionId, status, type, result}`** — **flat `Object result`, NOT a polymorphic response.** Key insight: `@JsonTypeInfo` is needed for *deserialization* (Jackson must pick a class from JSON) but *serialization* just introspects whatever object you hand it — so `Object result` serializes a `TaskDto`, a String, or null correctly with zero polymorphic boilerplate. Polymorphic-in, flat-out.

## Governance proven in the DB (the day's real substance)
The approve-vs-reject asymmetry — provable ONLY in the database, not from the 200s:
- **Approve create-task:** 1 task (`todo`) + 1 audit row (`approved`). Both written.
- **Reject create-task:** response `{status:rejected, result:null}`, **0 tasks**, **1 audit row (`rejected`)**. Audited but NOT executed.
- **Bad session:** 404 `CHAT_NOT_FOUND` (validate-first works, no raw FK 500).
  Result: every decision is auditable, only approvals act — human-in-the-loop with an immutable trail, enforced server-side.

## GET /tasks
`findAll()` today + `// TODO Day 16` for user scoping (task→session→user needs a JOIN; one seeded user means all-tasks ≈ user's-tasks for now). Task projection = entity→`TaskDto` via `from()`.

## What I built (deliverables)
- `task/` — `Task` entity, `TaskPriority`/`TaskStatus` enums, `TaskStatusConverter` (hyphen mapping), `TaskRepository`, `TaskDto`, `TaskController` (GET /api/tasks).
- `action/` — `ActionAudit` entity, `ActionType` (@JsonValue kebab)/`ActionDecision` enums, `ActionAuditRepository`, `ActionService` (governance), `ActionController` (POST /api/ai/actions).
- `action/dto/` — `ActionPayload` sealed interface + 3 payload records, `ActionRequest` (EXTERNAL_PROPERTY polymorphic), `ActionResult` (flat).

## Next (Day 11 — MONTH 3 week per tracker, but backend error-handling day)
Global exception handling — centralize errors, match the frontend error contract, add trace IDs. Consolidate/review the GlobalExceptionHandler built incrementally across Days 2/5/6/7/9/10. Ensure predictable validation/not-found/unauthorized/server errors. (Largely a hardening + review day — the handler already exists; this makes it comprehensive + adds trace IDs for debuggability.)

---

# Backend Day 11 — Global exception handling (consolidation + trace IDs)

Not a new subsystem — the `GlobalExceptionHandler` was built incrementally since Day 2. Today: consolidate domain errors, seal framework leaks, add trace IDs. Success: frontend receives predictable validation/not-found/unauthorized/server errors.

## Domain error refactor — base DomainException
Four 1:1 exception→handler mappings (ChatNotFound, Unauthorized, DocumentValidation, + new DocumentNotFound) was the right inflection point to consolidate (not premature at 4; the pattern only becomes clear once it repeats).
- Abstract `DomainException(message, ErrorCode code, HttpStatus status)`. Each domain exc extends it trivially: `super(msg, ErrorCode.CHAT_NOT_FOUND, HttpStatus.NOT_FOUND)`.
- ONE `@ExceptionHandler(DomainException.class)` replaces all the per-exception handlers — reads `ex.getCode()` + `ex.getStatus()`. Adding a new domain error next month = one class, zero handler changes (the DRY test).
- **Critical:** DELETE the now-redundant per-exception handlers or they shadow the base (most-specific-handler wins). Framework-exception handlers STAY separate (they're not ours to make extend DomainException).

## Sealed the framework leaks (JSON boundary stays JSON)
- `NoResourceFoundException` (unmapped path) → 404 `NOT_FOUND` — this was the 500 from Day 10! An unmatched route fell to the static-resource handler → 500. Now a clean envelope.
- `HttpRequestMethodNotSupportedException` (wrong verb) → 405 `METHOD_NOT_ALLOWED`.
- Added generic `NOT_FOUND` + `METHOD_NOT_ALLOWED` to the ErrorCode enum (the specific DOCUMENT_NOT_FOUND/CHAT_NOT_FOUND weren't right for "route doesn't exist"/"wrong verb").

## Filled the contract gap: GET /documents/{id}
The Day-21 contract had `GET /documents/:id` → 404 DOCUMENT_NOT_FOUND, never built. Wired it: `@GetMapping("/{documentId}")` → `getDocumentById(id).orElseThrow(DocumentNotFoundException)` → DTO. (Building the exception class alone did nothing — the *endpoint* has to exist and throw it, else the request 404s at routing with the wrong code.)

## Trace IDs — full MDC-in-a-filter
- `TraceIdFilter extends OncePerRequestFilter`: generate a UUID → `MDC.put("traceId", id)` → every log line for that thread is auto-tagged. Generating the id only in the handler would miss warn logs deep in the service before the throw — the filter tags ALL events for the request.
- **CRITICAL: `finally { MDC.clear() }`** — MDC is thread-local and Tomcat reuses threads; without the clear, a stale id leaks into the next request on that thread. The #1 MDC bug.
- Added `traceId` to the `ApiError` record, sourced from `MDC.get("traceId")` in every handler. **Adding a field to a JSON response is backward-compatible** (clients ignore unknown keys) — safe contract evolution; renaming/removing would not be.
- Also return `X-Trace-Id` response header (visible in the network tab even for non-error responses).
- Log pattern `%X{traceId}` so the id actually PRINTS in the console (MDC holds it, but the pattern must reference it) — closes the correlation loop: id in the response AND the logs, grep-matchable.

## The regression lesson (the real takeaway)
The refactor compiled and MOSTLY worked (trace ids flowed, most errors correct) — but silently broke bad-credentials login: **500 instead of 401**. Caught by RE-RUNNING the existing error tests to verify behavior-preservation, not by testing the new stuff. A refactor isn't done when it compiles — it's done when the old behavior is PROVEN unchanged. "Behavior-preserving" is a claim you verify, not assume.

## Verified matrix (all clean envelopes + traceId)
- 400 validation / malformed JSON (unchanged), 401 UNAUTHORIZED login (regression fixed), 404 CHAT_NOT_FOUND, 404 DOCUMENT_NOT_FOUND (new endpoint), 404 NOT_FOUND (unmapped path, was 500), 405 METHOD_NOT_ALLOWED (wrong verb), 500 catch-all. Every response carries traceId in body + X-Trace-Id header.

## What I built (deliverables)
- `common/DomainException.java` — abstract base (code + status).
- Refactored `ChatNotFoundException`/`UnauthorizedException`/`DocumentValidationException` to extend it; new `DocumentNotFoundException`.
- `common/ErrorCode.java` — added NOT_FOUND, METHOD_NOT_ALLOWED.
- `common/ApiError.java` — added traceId field.
- `config/TraceIdFilter.java` — OncePerRequestFilter, UUID→MDC, finally-clear, X-Trace-Id header.
- `config/GlobalExceptionHandler.java` — consolidated DomainException handler; added NoResourceFoundException (404) + HttpRequestMethodNotSupportedException (405); all handlers source traceId.
- `document/DocumentController.java` — GET /{documentId}.
- `application.properties` — `%X{traceId}` log pattern.

## Next (Day 12)
OpenAPI/Swagger docs — springdoc-openapi, annotate endpoints/DTOs, example payloads for all Month-1 contract endpoints. Success: mentor can inspect + test the APIs from documented examples. Interactive Swagger UI over the whole surface built Days 2-11.

---

# Backend Day 12 — OpenAPI/Swagger documentation

Expose the whole Days 2-11 API surface as a live, browsable, testable Swagger UI. Success: mentor can inspect AND test the APIs from documented examples. A lighter, satisfying day.

## springdoc + the Boot 4.x version risk
`springdoc-openapi-starter-webmvc-ui` (webmvc, not webflux — matches the stack). **The version was the real risk:** springdoc versions map to Spring generations (1.x→Boot2, 2.0-2.6→Boot3), and Boot 4.x (Spring 7) is bleeding-edge — a Boot-3-era springdoc would fail autoconfiguration or render nothing. Same "verify library compat on Boot 4.x" caution as the early scaffold days. Found a compatible version; app booted; `/swagger-ui.html` rendered.

## What's free vs. annotated
- **Free (zero annotations):** springdoc scans `@RestController`s → auto-lists every endpoint, infers request/response schemas from DTOs (even inferred the enum example `status:"pending"`), renders the UI. Multipart `POST /upload` correctly rendered a FILE PICKER (`file: string($binary)`), not a JSON body.
- **Annotated (targeted approach):** `@Operation(summary=...)` on all endpoints (cheap, makes the nav read like docs) + explicit `@ExampleObject` payloads only on the complex POSTs. Skipped per-field `@Schema` (auto-gen infers types/enums/required-via-@NotNull; annotating every field clutters the clean records for little gain).

## The polymorphic ActionRequest — why it needed an explicit example
Swagger UI can't build a working input form for Jackson `EXTERNAL_PROPERTY` polymorphism — auto-gen produces a confusing nested object that FAILS on Execute. The schema list showed the sealed family (`ActionPayload`, `ActionRequest`, 3 variants as `any & object`) but not a runnable payload. Fix: a hardcoded `@ExampleObject` JSON on the action endpoint (`{type:"create-task", payload:{...}}`) bypasses the UI's confusion — paste-and-run. This is the one endpoint where the explicit example is essential, not just nice.

## Examples seeded with REAL values (the usability insight)
The examples aren't just docs — Swagger executes against the LIVE backend, so examples are EXECUTABLE. Seeded them with real working values: login example uses the real seeded creds (`user@bluestone.com`/`securepassword123`), action/message examples use the real seeded session id (`3333...`). So "Try it out" actually succeeds (200 + token, 200 + created task) instead of 401/404-ing on placeholder values. The mentor drives the whole API from the browser, no terminal.
- Caveat: Execute has REAL side effects (the action example created a real task row) — Swagger is not a dry-run.

## Verified interactively (from the browser)
- `POST /login` "Try it out" → real 200, user + `demo-token-...`, x-trace-id header.
- `POST /ai/actions` "Try it out" with the polymorphic example → real 200, `ActionResult` with a created `TaskDto` (status todo). The hardest endpoint, mentor-testable.
- All 7 controllers (auth/document/chat/action/task/health) + ~15 endpoints listed; all DTOs in the Schemas section.

## Error docs — kept global for now
Skipped per-endpoint `@ApiResponse(400/401/...)` copy-paste across 15 endpoints. The `ApiError` schema is registered; the mentor can trigger errors organically. A global OpenAPI config bean listing all error codes can come later if wanted. (Day-16 note: when security lands, the Swagger paths must be whitelisted or auth will block the UI.)

## What I built (deliverables)
- `pom.xml` — springdoc-openapi-starter-webmvc-ui (Boot-4-compatible version).
- `@Operation(summary=...)` on all ~15 endpoints across the 5 feature controllers.
- `@ExampleObject` payloads on `POST /ai/actions` (polymorphic, essential), `POST /login`, `POST /message` — seeded with real working values.

## Next (Day 13)
Unit tests — JUnit + Mockito. Test the document/chat/action services (happy path, edge path, validation cases) WITHOUT full app startup (mock the repositories). Core service behavior covered in isolation — fast, no DB, no Spring context.

---

# Backend Day 13 — Unit tests (JUnit + Mockito)

A shift in KIND: everything before was manual/integration (run app, curl, check DB). Today = isolated, automated, repeatable unit tests. Mock the repositories, test the service logic, NO Spring, NO PostgreSQL. Success: core service behavior covered without full app startup.

## The mocking mindset
`@ExtendWith(MockitoExtension.class)`, `@Mock` (fake repo), `@InjectMocks` (real service, mock wired in), `when(mock.x()).thenReturn(...)` (stub responses), assert/verify on the outcome. No DB, no context.
- **Two assertion flavors:** state/return (`assertEquals`, `assertThrows` — for logic that transforms/validates) vs. interaction/behavior (`verify(mock).save(...)`, `verify(mock, never()).save(...)` — for logic whose effect is a side-effect).

## Proof it's a true unit test
`DocumentServiceTest` alone ran in <1s (935ms) with NO Hikari/Hibernate/DB in the log. Compare: the scaffold `@SpringBootTest` (`KnowledgeAssistantApplicationTests`) booted the full context + connected to Postgres = 5.5s. That contrast IS the day's point — "without full app startup" made concrete.

## DocumentService — validation branches (pure logic, pre-write)
Focused unit tests ONLY on validation (MISSING_FILE / FILE_TOO_LARGE / INVALID_FILE_TYPE) — these throw BEFORE `Files.copy`/`save`, so they're pure isolated logic. The physical-file happy path is deferred to Day-14 integration ("an integration test wearing a unit test's clothes" if it writes real bytes). Null-file test implicitly proves the `file==null` short-circuit ordering (else NPE). Ordering edge: oversized AND wrong-type → FILE_TOO_LARGE proves size-before-type.

## ActionService — the governance asymmetry as a millisecond assertion (crown jewel)
The single most valuable unit test in the app. Day 10 proved audit-but-no-task by querying Postgres after a curl; today the SAME rule runs in ms with mocks, on every build:
- **Reject:** `verify(actionAuditRepository).save(...)` + `verify(taskRepository, never()).save(...)`.
- **Approve create-task:** both saved once.
- **Session-not-found:** `assertThrows(ChatNotFoundException)` + `never()` on BOTH repos (encodes validate-FIRST ordering — audit must not fire before the session check).
- Stub the precondition (`existsById → true`) to isolate the branch under test. (Green result confirmed the service calls `existsById`, not `findById` — stubs matched, no UnnecessaryStubbingException.)

## ChatSessionService
- `getSessionMessages` not-found → `ChatNotFoundException` + `verify(messageRepository, never())...` (guard short-circuits before the query).
- `sendMessage` → `verify(messageRepository, times(2)).save(...)` (atomic two-message insert, proven by interaction, no DB) + `verify(chatSessionRepository).save(session)`.
- **Unit-testing insight — dirty checking is NOT mock-observable.** In the real app, mutating a managed entity from `findById` persists via Hibernate dirty checking with no explicit `save()`. But a MOCK repo has no persistence context — so if the service relied on dirty checking alone, `verify(...save(session))` would fail. It PASSED → the service makes an explicit `save(session)`. The Day-9 "redundant" explicit save turns out to aid testability: it makes the session update an observable interaction, not an invisible Hibernate side-effect.
- `new ChatSession()` works in-test only because the test shares the entity's package (protected no-arg ctor = same-package accessible).

## Mockito strict stubbing
`MockitoExtension` defaults to strict: an unused stub → `UnnecessaryStubbingException`. Stub minimally per test (it's a feature — catches dead stubs). `lenient()` sparingly if needed.

## Housekeeping decisions
- **Scaffold `@SpringBootTest` → relocate to Day 14** (it boots the full context = integration, not unit; it's why `mvn test` is slow + DB-dependent).
- **Mockito self-attach warning → backlog.** JDK 21 noise about dynamic agent loading (ByteBuddy); doesn't fail the build (exit 0). Not worth polluting pom.xml with a `-javaagent` while focused on logic. (Production fix: declare Mockito as an explicit test `-javaagent`.)

## What I built (deliverables)
- `document/DocumentServiceTest.java` — 4 validation-branch tests (null, empty, oversized, wrong-type + ordering).
- `chat/ChatSessionServiceTest.java` — sendMessage interaction (times(2) + session save), getMessages not-found.
- `action/ActionServiceTest.java` — reject (audit-only), approve (both), session-not-found (neither). The governance crown jewel.
- All pass; unit classes run DB-free in <1s.

## Next (Day 14)
Integration tests — `@SpringBootTest`, a test database, HTTP assertions, seeded data. Test auth/documents/chat/tasks/actions end-to-end through the real stack (relocate the scaffold context test here; add the physical-file upload happy path deferred from today). Success: the backend contract is protected against regressions.

---

# Backend Day 14 — Integration tests (@SpringBootTest + MockMvc + test DB)

The complement to Day 13's units: boot the REAL context, hit a REAL test DB, assert on ACTUAL HTTP through the full stack (filters → controllers → exception handler → service → repo → DB). Success: backend contract protected against regressions. (A marathon — many environmental fights + real bugs flushed out.)

## Test-DB strategy (given the environment)
- **No Docker** (company policy on managed Macs) → no Testcontainers. **H2 rejected** (Postgres-specific schema: UUID, gen_random_uuid, TIMESTAMPTZ, CHECK constraints — H2 would lie). → **Dedicated local `knowledge_assistant_test` Postgres DB**, isolated from dev.
- **Seeding: `@Sql` was the plan, but the real answer is pre-load-once.** CRITICAL catch: **Flyway has been dead on Boot 4.x since Day 3** — "let Flyway auto-migrate the test DB" would crash every test with "relation does not exist." Also `ddl-auto=validate` runs at BOOT (before `@Sql` runs after boot) → ordering conflict. Resolution: `CREATE DATABASE knowledge_assistant_test`, load V1-V8 manually ONCE (same muscle as dev), keep `validate`, let each test's `@Transactional` roll back its own mutations on top of the stable seed. No `@Sql` needed.
- **DB separation non-negotiable:** `@Transactional` rollback protects WITHIN a test; a crash / `@Commit` / manual insert / stray curl pollutes. Test DB should be touched ONLY by the seed load + rolled-back tests. (Learned live: pgAdmin/curls leaked extra rows into the test DB → count assertions broke.)

## Harness: @SpringBootTest + @AutoConfigureMockMvc + @ActiveProfiles("test") + @Transactional
- `MockMvc` (not TestRestTemplate) — exercises the full pipeline (TraceIdFilter, controllers, GlobalExceptionHandler, Jackson) without binding Tomcat. Fast, less flaky.
- `application-test.properties` in `src/test/resources/` → test DB URL, `validate`. `@ActiveProfiles("test")` activates it.
- `@Transactional` on the class → each test method's DB mutations roll back after → seed stays pristine, tests repeatable.

## Environmental fights (the slog)
- **Boot 4.x test-starter rename.** `AutoConfigureMockMvc` wouldn't resolve. Root cause: on Boot 4.x the class MOVED packages (`org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc`, NOT the old `...boot.test.autoconfigure.web.servlet...`) and the artifact is `spring-boot-webmvc-test`. Not in any older doc — found by working the compat. (`spring-boot-starter-test` also pulls the chain; the granular per-slice `-test` starters were the confusion.)
- **IntelliJ caching wall** — new dep in pom didn't resolve until **Invalidate Caches → Restart** (no terminal `mvn` — bundled Maven only; must wait for FULL re-index before checking).

## Real bugs the fresh clean-load flushed out (the payoff)
1. **Duplicate user INSERT in V8** — a trailing second user block (leftover from the Day-5 hash edit: appended instead of replaced). Only surfaced on a clean load (dev loaded piecemeal). Duplicate-key error on `users_pkey`.
2. **9-day-wrong bcrypt hash in version-controlled V8.** The surviving first insert had the WELL-KNOWN hash of `"password"` (`N9qo...`), NOT `securepassword123` (`jeE4...`). Day-5 fixed the DEV DB via manual UPDATE but the FILE stayed wrong → any fresh clone/deploy would've had broken login. Fixed the canonical V8 (one insert, correct hash).
3. **CONTRACT-BREAKING route regression (the headline).** `ChatController` routes had drifted (likely during the Day-12 Swagger annotation pass) to `GET /api/chat/sessions/{id}/messages` and `POST /api/chat/sessions/{id}/messages` — OFF the frozen Day-21 contract (`GET /api/chat/{id}/messages`, `POST /api/chat/message` with sessionId in BODY, 201). The integration test hit the contract paths → 404 `NoResourceFoundException`. Fixed: restored `/{sessionId}/messages`, `/message` (body not path), 201. **Nothing else would have caught this** — units don't hit routes, Swagger documents whatever exists, the Day-9 curls were from when the code was still right. Caught ONE DAY before Day-15 FE-BE integration where the frontend calls these exact paths.

## Assertion lesson: presence, not exact count
`$.length()==4` docs / `==2` messages broke because upload/message tests (and stray manual ops) legitimately add rows. Robust: assert a seeded item EXISTS (`$[?(@.filename == 'maintenance_log_Q2.md')]).exists()`) — survives added rows. A contract test shouldn't break because someone adds data.

## Verified (full suite green, repeatable)
Auth (200/401), Documents (list, 404 DOCUMENT_NOT_FOUND, upload 201), Chat (sessions, messages, CHAT_NOT_FOUND, sendMessage 201), Actions (tasks, approve+task, reject+no-task). Exit code 0. The suite already EARNED ITS KEEP — it caught the route regression + the seed/hash bugs. "Contract protected against regressions" isn't hypothetical: it found real ones.

## Housekeeping
- Scaffold `@SpringBootTest` context test relocated here (integration home). Mockito self-attach warning still backlogged.
- Upload integration test writes a real file to `uploads/` (file I/O isn't transactional — no rollback). Leaves a stray UUID file per run. Noted, harmless.
- pgAdmin installed for visual DB inspection — but keep it pointed at DEV, not the test DB (open connections block DROP + risk polluting the pristine seed).

## What I built (deliverables)
- `application-test.properties` (test DB profile).
- `AuthIntegrationTest`, `DocumentIntegrationTest`, `ChatIntegrationTest`, `ActionIntegrationTest` — full-stack HTTP assertions per feature.
- Fixes forced by the tests: corrected V8 (dedup + right hash), corrected ChatController routes (contract fidelity), robust presence-based assertions.
- pom: `spring-boot-webmvc-test` (Boot-4.x test artifact).

## Next (Day 15 — THE MONTH'S PAYOFF)
FE-BE integration — swap the frontend's mock API layer for the real Spring Boot backend. Environment configs, base URL, request adapter, CORS, auth headers. Keep mock mode toggleable. Success: frontend runs against the real backend WITHOUT major screen rewrites. The contract-first discipline of Months 1-2 gets its final exam. (The route-regression catch today means the contract paths are now actually correct for this swap.)

---

# Backend Day 15 (backend slice) — CORS for FE-BE integration

The month's payoff day: the Month-1 React frontend swapped from its MSW mock onto the real Spring Boot backend. Most of the work is frontend (recorded in notes.md); the permanent BACKEND addition is CORS.

## CORS — the new backend concern
Frontend runs on `localhost:5173`, backend on `localhost:8080` → different origins → the BROWSER blocks cross-origin requests unless the backend sends `Access-Control-Allow-Origin`. Never came up before (MSW intercepted in-browser; curl/Swagger don't enforce CORS — only browsers do). So this is a browser-only gate, fixed backend-side.
- `config/WebConfig implements WebMvcConfigurer`, `addCorsMappings`: `addMapping("/**")`, `allowedOrigins("http://localhost:5173")`, methods GET/POST/PUT/DELETE/OPTIONS, `allowedHeaders("*")`.
- **Dropped `allowCredentials(true)`** — that flag is for cookies. Auth here is a bearer token in the `Authorization` header, NOT a cookie, so credentials aren't needed — and `allowCredentials(true)` triggers CORS strictness rules (can't combine with wildcards) that would cause footguns. Header tokens ≠ CORS credentials.
- OPTIONS is in the allowed methods so the browser's preflight (sent before a JSON POST) is answered.
- Result: the frontend's `POST http://localhost:8080/api/auth/login` returned 200 first try — no CORS wall.

## Day-16 note
CORS allows the dev origin only. Real deploy will need the prod frontend origin. And when route protection lands (Day 16), the token the frontend now sends (`Authorization: Bearer demo-token-...`) can start being enforced — today the backend receives but ignores it (endpoints still open).

## What I built (deliverables — backend slice)
- `config/WebConfig.java` — global CORS mapping for the Vite dev origin.

## Next (Day 16)
Security basics — authorization boundaries + safe inputs. User scoping (replace the hardcoded `DEMO_USER_ID` markers across chat/tasks with real per-user scoping), tighten validation on uploads/messages/actions, least privilege, secrets handling. Success: obvious invalid or cross-user requests are rejected. All the `// TODO Day 16` markers left through Month 2 come due.

---

# Backend Day 15 (cont.) — endpoints the frontend needed that were never built + the agentic loop

FE-BE integration surfaced missing backend endpoints (the MSW mock had faked them). All backend work below; the frontend slice is in notes.md.

## Missing endpoints, built
- **`GET /api/actions/audit`** — audit rows were WRITTEN since Day 10 but never READABLE (no GET endpoint existed). Built `ActionAuditDto` + `ActionService.getAuditTrail()` (findAll, sorted newest-first) + the controller mapping.
- **`PATCH /api/tasks/{id}`** — `TaskController` had ONLY GET; the frontend's status dropdown had nothing to call. Symptom was diagnostic: `0 B transferred`, no status code = the browser blocked it at CORS, because **PATCH wasn't in `allowedMethods`** (WebConfig listed GET/POST/PUT/DELETE/OPTIONS). Built:
    - `TaskNotFoundException` + `TASK_NOT_FOUND` ErrorCode — **the Day-11 DRY payoff: one new class extending `DomainException`, ZERO handler changes.** Exactly the test that justified the refactor.
    - `Task.setStatus` / `setCompletedAt` (status is genuinely mutable now; Day-10 immutability discipline said setters only on mutable fields).
    - `TaskService.updateStatus` — transactional, `findById().orElseThrow()`, mutate + dirty-checking persists (Day-9 managed-entity pattern), conditional `completedAt` (stamped on `done`, cleared otherwise). Marked `// TODO Day 16: scope to owner`.
    - `@PatchMapping("/{taskId}")` + PATCH added to CORS.
    - Removed a DUPLICATE `updateTaskStatus` in `ActionController` — two mappings on `/api/tasks/{id}` = ambiguous-handler startup crash.
- **The hyphen boundary, THIRD appearance:** `TaskDto` serialized raw enum names (`in_progress`) but the frontend expects `in-progress` → the dropdown's "silent revert". Fixed at the DTO. **Debt:** the hyphen rule now lives in 3 places (DB `@Converter`, `@JsonValue` on the enum, this DTO mapping). One source of truth would be better.
- **DTO naming after a misdiagnosis:** an earlier `@JsonProperty("sourceSessionId")` on `ActionAuditDto` was a fix for the wrong cause (the real bug was a hardcoded frontend link) — reverted. Names now follow their DB columns: `session_id`→`sessionId` (audit), `source_session_id`→`sourceSessionId` (tasks). Coherent vertical slices per domain (DB↔Entity↔DTO speak one language each), NOT an artificial unified convention across distinct tables.

## The agentic loop — governance was unreachable from the product
The human-in-the-loop flow had NEVER been exercised through the UI — only curl/Swagger/tests. Why: the placeholder AI returned only a canned string, and `MessageDto` deferred `actions` (Day-9 YAGNI), so `msg.actions` was always undefined → `MessageActions` never rendered → `POST /ai/actions` was never called from the product. The most architecturally interesting work (discriminated unions, audit-both-execute-approvals) was undemonstrable.
- **Fix — rule-based proposer** (non-AI placeholder logic, matching the tracker's Day-10 language): `ActionProposalDto`; `MessageDto` extended with `List<ActionProposalDto> actions`; a keyword scanner in `ChatSessionService.sendMessage` ("create a task"/"todo"...) attaches a `create-task` proposal to the AI response.
- **Clean seam for Month 3:** real LLM tool-calling replaces the PROPOSER only — the `POST /ai/actions` governance contract is untouched.
- **Verified through the real UI:** trigger → card renders → Approve → audit row + Task created → appears in Actions tab. **Asymmetry holds through the UI path: 9 approvals → 9 audit rows → 9 tasks; 2 rejections → 2 audit rows → 0 tasks.** (Proven in DB Day 10, unit tests Day 13, now the product path.)

## ActionStatus — a modeling gap, not frontend accommodation
Frontend expected `completed` where the backend sent `approved`. Resolved by adding an **`ActionStatus` enum (`completed, rejected, failed`)** and typing `ActionResult.status` to it (NOT a raw String — type safety kept).
- **Decisive argument:** `approved` = what the human DECIDED; `completed` = what the system DID. **Approved-but-execution-failed is a REACHABLE state that `ActionDecision` cannot express — a type that can't represent a reachable state is the wrong type for that field.**
- Two different FACTS about one event, recorded where each belongs: `action_audit.decision` stays `approved` forever (it records authorization — saying `completed` there would corrupt the audit's meaning); the API response reports OUTCOME, which is what the caller renders.
- The discriminator vs. bending-to-the-frontend: *would I keep `ActionStatus` if the frontend vanished tomorrow?* Yes. Renaming a field to match a client's spelling of the same concept = slippery slope. Adding a concept the backend was MISSING = a real gap the client's vocabulary happened to reveal.

## Debt logged (Day-16 list)
- **No route protection AT ALL** — `POST /api/ai/actions` accepts any session id from anyone; no Spring Security on the backend (deferred since Day 5). The single biggest Day-16 item.
- `failed` in `ActionStatus` is never produced — exceptions propagate to the error handler and the client sets its own failed state. Wire it when execution can fail partway.
- **Proposal payload uses `Map<String,Object>` with hardcoded `"title"`/`"priority"` keys** that must match `CreateTaskPayload`'s component names. A rename breaks it SILENTLY at deserialization on a LATER request, not at compile time. Constructing proposals from the sealed `ActionPayload` would make it a compile error. (Serialization is forgiving — the polymorphic-in/flat-out asymmetry from Day 10 — but this is a correctness hazard, not style.)
- **Proposals are ephemeral** — confirmed in code: `sendMessage` returns `MessageDto.from(aiMessage, proposals)` while `getMessages` uses the single-arg `from`. A refresh before deciding drops a pending proposal permanently. Month 3 governance wants pending decisions to survive a refresh.
- Missing integration test for create-session-persists-first-message-and-derives-title (the Day-14 suite had no test for that path, which is why the bug shipped).
- Orphaned empty sessions in dev from the pre-fix flow — clean up.

## What I built (deliverables — backend, Day 15 cont.)
- `action/dto/ActionAuditDto.java`, `ActionProposalDto.java`, `TaskStatusUpdateRequest.java`; `action/ActionStatus.java`.
- `ActionService`: `getAuditTrail()`, `ActionStatus` mapping in `processAction`.
- `task/TaskService.java` (new), `TaskController` `@PatchMapping`, `Task` setters, `TaskNotFoundException` + `TASK_NOT_FOUND`.
- `chat/ChatSessionService`: keyword action-proposer; `MessageDto` extended with `actions`.
- `config/WebConfig`: PATCH added to CORS.

---

# Backend Day 16 — Security basics (authorization boundaries + safe inputs)

Success criterion: obvious invalid or cross-user requests are rejected. Delivered on both halves, verified live. This became the largest day of the month — the starting position was worse than the tracker described, and the requirement grew mid-day.

## Starting position (found by reading, before writing)
- **No route protection at all.** Every endpoint accepted anything from anyone; the frontend sent `Authorization: Bearer demo-token-<uuid>` and the backend ignored it entirely.
- **The token carried no identity** — `"demo-token-" + UUID.randomUUID()`, no server-side record. The backend could not derive a user even in principle. Nothing could be scoped until that was solved.
- `documents` had no `owner_id` — ownership was a schema change, not a check.
- `tasks` had no `user_id` — ownership runs `tasks.source_session_id → chat_sessions.user_id`, so scoping needs a JOIN.
- **The unmarked holes were worse than the marked ones.** `getMessages`/`addMessage` had no ownership concept at all, and `processAction` only checked `existsById(sessionId)` — anyone could post an approved action into anyone else's session. The `// TODO Day 16` constants were at least visible.

## The load-bearing decision: how the backend identifies the user
Chose the server-side token store first, and BUILT it (`TokenStore` ConcurrentHashMap issue/resolve/revoke, `OncePerRequestFilter`, `@CurrentUserId` backed by a **request attribute, not a ThreadLocal** — Tomcat reuses request threads, so a ThreadLocal without a guaranteed clear lets request N+1 inherit request N's user, the MDC bug from Day 11 in a far worse place).
Reasoning at the time: the day's objective is authorization, not authentication — token→user resolution is the precondition, not the lesson. JWT without revocation is strictly worse than a map with one process and one issuer. Spring Security's value is what it gives free (CSRF, session fixation, method security, OAuth), almost none of which applies to an opaque-token REST API.
**Then the requirement changed** (refresh + expiry + roles) and it was replaced with Spring Security + JWT. Why the change was right:
1. "Refresh + expiry + roles" is a different problem from "resolve a user id". Hand-building all three = writing a worse JWT.
2. **The anti-JWT argument was half right, and the right half saved the design.** "A JWT you can't revoke is worse than a map" is still true — the resolution wasn't to abandon JWT, it was to **stop making the refresh token a JWT**. The revocable credential went back into the database (which is what `TokenStore` always was); the unrevocable one got a 15-minute fuse. The argument didn't lose, it relocated.
3. The framework gave something Day-5 reasoning couldn't anticipate: **`DaoAuthenticationProvider` dummy-hashes unknown accounts** so wrong-email and wrong-password take the same time. The hand-rolled `passwordEncoder.matches` leaked that timing difference.
- The cost was real (a working, verified implementation deleted). **What made it survivable is that the seam held** — `issue`/`resolve`/`revoke` was the right shape, and `RefreshTokenService` has those same three methods against a different store. A substitution, not a redesign. That was the actual payoff of "the seam is the lesson, not the storage."

## Auth architecture
- `spring-boot-starter-security` + JJWT (`jjwt-api` compile; `impl`/`jackson` runtime-only so app code can only touch the stable API).
- `SecurityConfig`: stateless, CSRF off (credentials travel in a header; a cross-site form cannot set one), `@EnableMethodSecurity`, **closed by default — an allowlist, not a blocklist**, so an endpoint added next month is protected the day it's written.
- **`JwtAuthenticationFilter` never rejects** — it populates the SecurityContext or leaves it empty; the 401 decision belongs to `RestAuthenticationEntryPoint`. That's what keeps permitted endpoints reachable.
- `RestAuthenticationEntryPoint` (401) + `RestAccessDeniedHandler` (403) write the `ApiError` envelope **by hand**, because `@RestControllerAdvice` only sees exceptions thrown inside the DispatcherServlet. Without them, auth failures would be the one response shape in the API that didn't match.
- `TraceIdFilter` at `HIGHEST_PRECEDENCE` (Security's chain is −100) so 401s/403s carry a traceId. CORS moved into the security chain via `http.cors()` — a filter-level rejection otherwise carries no `Access-Control-Allow-Origin`, the browser hides the body, and the frontend sees an opaque network error instead of an actionable 401.
- `@CurrentUserId` survived as a meta-annotation over `@AuthenticationPrincipal(expression="id")` — controller signatures byte-identical, custom resolver deleted.

## Access / refresh split (the design decision that shaped everything)
| | Access | Refresh |
|---|---|---|
| Form | Signed JWT (HS512) | Opaque 256-bit random, SHA-256 digest in DB |
| TTL | 15 min | 7 days |
| Revocable | No — TTL is the blast radius | Yes |
| Lookup | None; principal rebuilt from claims | By digest |
Rotation is single-use, so a stolen token is a race the attacker must win, and replaying a spent one is detectable → revoke the user's whole token family.

## Scoping — the actual objective
Every read/write/download/delete resolves through a query with ownership in the WHERE clause (`findByIdAndUser_Id`, `findByIdAndOwner_Id`, JOINs for tasks and audit).
- **Cross-user access returns 404, never 403.** A 403 confirms the resource exists and leaks the id space. Folding ownership INTO the query means an unowned id simply doesn't resolve — "not yours" and "not there" collapse into one answer and the leak-free response falls out for free instead of having to be remembered. **There is no `findById()` followed by an owner comparison anywhere**, so there is never a moment where an unentitled resource is loaded in memory.
- 403 is for role failures, where the caller is known and admitting the endpoint exists leaks nothing.
- Roles: normalised `roles` + `user_roles` (V10) rather than a column — adding a role is an INSERT, not a migration. Names carry the `ROLE_` prefix because `hasRole()` prepends it; storing bare `ADMIN` would silently never match. `/api/admin/**` guarded twice (URL rule + `@PreAuthorize`) so it survives a remapping.
- **Verified with a control row**: A→B's messages 404, A→B's task 404, A→B's session delete 404, **B→own messages 200** ← without this control, a filter that broke everything would produce identical 404s and look like perfect security.

## Everything else built
- **Document ownership (V13)** — `owner_id NOT NULL` + FK + index. Seeded documents **split between the two users** rather than all to one: with an empty library on one side the boundary is invisible in the browser. One constraint forced part of the split — V8's citation links A's message to document …2224, so that one had to stay with A or A's own chat would cite a file A can't open.
- **Document storage + download** — added `storage_path` + `content_type`. **The bytes were always written to `uploads/<uuid>` but the location was never recorded** — the metadata knew a document existed and not where it lived, which is why nothing could serve it. `GET /{id}/download` streams with `Content-Disposition: inline`, `Cache-Control: private, no-store`, and re-checks the resolved path against the upload root (the stored value is ours, not user input, but reading a file whose location came from a DB row is exactly the shape of a path-traversal bug).
- `DELETE /api/documents/{id}` — **didn't exist; the UI button had been getting 405 the whole time.** Added, ownership-checked, file removed after the row.
- `DELETE /api/chat/sessions/{id}` — ownership-checked; messages/tasks/audit follow via the Day-3 cascades.
- **Citations** — the table existed since V7 and the frontend had rendered citation cards since Month 1, and **no Java code had ever touched the table**. Built `Citation`/`CitationRepository`/`CitationDto` matching the shape the cards were already written against (no frontend change needed), persisted on assistant replies, loaded in one query keyed by message rather than N+1.
- **Document status** — upload set `pending` and nothing ever called `setStatus`, so every document sat `pending` forever while being fully readable. Now marked `ready` once bytes are on disk (the truth); `processing`/`failed` remain for the real Month-3 pipeline. V15 backfilled.
- **Sign-up** (`POST /api/auth/register`) — returns the profile, not tokens (sign-up and sign-in stay separate so there's one place credentials become a session). `ROLE_USER` only; nothing self-service grants admin. Email lower-cased. Duplicate → 409, and **the pre-check is best-effort** — two simultaneous sign-ups both pass it, so the unique constraint is the real arbiter and `DataIntegrityViolationException` maps to the same 409. Password 8–72 chars **because bcrypt silently truncates past 72 bytes** — anything longer would look like it strengthens the password while doing nothing.
- **Password reset** — 256-bit token, digest-only, single-use, 30-min expiry. `forgot-password` **always returns 202** whether or not the account exists, else it's an account-existence oracle that undoes the login anti-enumeration. A second request invalidates the first. **A successful reset revokes every refresh token** — resetting is what someone does when they believe they're compromised; leaving sessions alive means the attacker keeps access.
- **Mail** — `EmailService` over `JavaMailSender`, self-enabling once SMTP credentials exist (a separate flag would mean configuring it correctly and still getting no mail). SMTP failures logged, never rethrown: a loud failure would leak that the address exists AND strand the user on an error they can't fix.
- **Validation** — `CreateTaskPayload` had zero constraints against `VARCHAR(255) NOT NULL`; blank/300-char titles were 500s from Postgres instead of 400s. Added, plus `@Size` caps on message/session content (`messages.content` is TEXT/unbounded, so the cap must come from the DTO) and filename length. Verified live: 300-char title → 400 with a specific message; valid title → 200 (control).
- **Secrets** — DB creds, CORS origins, JWT settings, mail all `${ENV:default}`. **`JwtSecretValidator` refuses to boot** if the checked-in dev signing key is in use outside dev/test/local, and enforces the 32-byte HS256 minimum. A misconfiguration that silently runs with a public key is strictly worse than a crash — the crash is loud at deploy time, the silent version is loud six months later. Proved the placeholders are live by booting with `DB_USERNAME=wrong-user-on-purpose` → `FATAL: role does not exist`.

## Bugs introduced and found (diagnoses > fixes)
- **Refresh storm vs. rotation.** Concurrent requests each started their own refresh; rotation is single-use, so the first succeeded and the rest presented a spent token — which the backend correctly read as reuse and answered by revoking the whole family, **logging the user out precisely because the client tried harder**. Single-flight refresh is a *correctness requirement imposed by the server's security design*, not an optimisation. Verified with `JWT_ACCESS_TTL=5s`: two concurrent 401s → exactly one refresh → both retried 200.
- **Revoke-then-throw in one transaction is a silent no-op.** The rollback undoes the revocation, so reuse detection *appears* to work (the replay 401s) while doing nothing. Any security side effect that must survive a rejection needs its own committed transaction (`REQUIRES_NEW`). **Live HTTP caught it; the test didn't.**
- **The test for it then deadlocked.** `AuthIntegrationTest` was `@Transactional`; the `REQUIRES_NEW` transaction runs on a second connection and waits on row locks the test's own transaction holds until the method returns. **A test asserting on what commits cannot run inside a rollback-only transaction.**
- `window.open(url, name, 'noopener,noreferrer')` **returns null by specification** — those flags sever the handle. The browser opened a tab, the code got null, concluded pop-ups were blocked, and ran a download fallback: a blank `about:blank` tab AND an unwanted download from one line.
- **Browsers only render a narrow set of MIME types.** PDFs/images render in an iframe; text/markdown, csv and Office are "save this", so an iframe silently downloads them. Now: iframe for PDFs/images, in-app `<pre>` for text (no blob URL and no anchor click on that path, so a download is *impossible*, not merely avoided), honest "no preview" for Office. **The markdown check had passed only because this sandbox's browser renders text/markdown and Chrome doesn't** — verified on a browser that wasn't the one being used.
- **Action proposals vanished on the first message.** Backend: `createSession` and `sendMessage` each built their own reply and only the latter had the proposal branch (the same duplication had already forced citations to be added twice) → unified into one `respondTo()`. Frontend: proposals are never persisted, so any refetch erases them; two failed attempts first (skipping the refetch failed because React dev double-invokes effects; a `useRef` failed because `/chat/new → /chat/{id}` remounts and resets the ref microseconds after it's written). A console diagnostic showing the response carrying actions while the ref read empty identified it.
- **Deleted user B's seeded demo data while testing the delete button, and Flyway won't re-run V9.** Did NOT fix by editing V9 — **editing an applied migration breaks its checksum.** Added V12 with `ON CONFLICT DO NOTHING`: restores rows on an existing DB, no-op on a fresh one. **Demo data the demo can destroy needs a repeatable way back.**

## Pre-existing problems found (not mine)
Two tests already red on main (`ActionIntegrationTest` expected `"approved"` where the contract returns execution status `"completed"`; a chat test asserted on array position against a mutable shared DB). Seven CSS tokens referenced but never defined. `--color-white` used as text on blue buttons — a surface token that correctly inverts to near-black in dark mode, which would have put dark text on a blue button; added `--on-accent`, which never inverts.

## The recurring pattern, named
**Five times this month a backend capability existed, was correct, and had no path to it from the product:** the audit trail was written for six days before it was readable; the governance loop worked in curl for six days before a proposal card could trigger it; `DELETE /chat/sessions/{id}` shipped with an ownership check and no UI; `DELETE /documents/{id}` never existed while the UI button called it and got a 405; the citations table and the citation cards both existed for two months with nothing joining them. Each time the backend work was complete, correct, and invisible.

## Principle worth carrying forward
> When a server responds to an ambiguous signal by assuming attack, every client behaviour that can produce that signal innocently becomes a bug — and the server can never tell you which one it's looking at.

Rotation is one instance. Same family: idempotency keys (a naive retry looks like a duplicate submission), optimistic locking (a double-submit looks like a lost update), rate limiting (a retry storm looks like abuse). **Wherever a server chooses safety under ambiguity, the client's concurrency model becomes part of the security model.** Ask of any such mechanism: *what innocent client behaviour is indistinguishable from the attack this defends against?*
And on verification: **make the slow failure fast, then assert on the mechanism, not the symptom** (`JWT_ACCESS_TTL=5s`; the network log, not the UI looking fine).

## Contract revision #1 — the first deliberate break
`POST /api/auth/login`: `{user, token}` → `{accessToken, refreshToken, tokenType, expiresIn, user, roles}`. Unavoidable: **a session is no longer one credential** — two tokens with different lifetimes and revocation semantics don't fit `token: string`, and overloading it would hide the distinction the design rests on. Blast radius: that endpoint only; new routes are additive. `ChatSessionDto` also gained an additive `initialResponse`.
**Rule going forward: a contract change gets a notes entry with before/after and a reason, in the same commit as the change. A break that's justified is fine; a break that's undocumented is drift.**

## Status
Backend branch `day-16-security-basics`, 11 commits ahead of main, **75/75 green**, migrations V9–V16. Frontend branch `jwt-auth-client`, 11 commits ahead, typecheck clean. Neither merged; both clean fast-forwards.

## Outstanding
1. 8 failing frontend tests — pre-existing. **Cause wasn't neglect: `package.json` had no `test` script**; vitest was installed and three test files existed but `npm test` errored, so the only way in was `npx vitest run`, which nobody types by habit. **Never reachable by the conventional command → never in any loop, while still looking like coverage from the file tree.** Script added; the 8 failures are now visible. Fixing them is its own pass.
2. `.idea/launch.json` committed by a `git add -A`; hardcodes an absolute path, shouldn't be tracked.
3. Password-reset links point at `http://localhost:5173` — set `FRONTEND_BASE_URL` before a mentor opens one elsewhere.
4. Every document is now `ready`, so the status badge has no variety left to demo.
5. Month 3 replaces the deterministic citation picker with real retrieval — the row, API shape and card all stay; only "which document?" gets a better answer.

---

# Backend Day 16 — Security: authorization boundaries and safe inputs

Success criterion: obvious invalid or cross-user requests are rejected. MET, verified live. Scope grew well past the tracker (see "Scope discipline lapsed" below — an honest finding, not a boast).

## Starting position was worse than the tracker described
- **No route protection at all.** Every endpoint accepted anything from anyone; the frontend sent `Authorization: Bearer demo-token-<uuid>` and the backend ignored it completely.
- **The token carried no identity** — `"demo-token-"+UUID` with no server-side record, so the backend could not derive a user *even in principle*. Nothing could be scoped until that was solved.
- **`documents` had no `owner_id`**; **`tasks` had no `user_id`** (ownership runs `tasks.source_session_id → chat_sessions.user_id` = a JOIN, not a column compare).
- **The unmarked holes were worse than the marked ones.** `getMessages`/`addMessage` had no ownership concept at all, and `processAction` only checked `existsById(sessionId)` — anyone could post an approved action into anyone else's session. The hardcoded `DEMO_USER_ID` constants were at least *visible*.

## The load-bearing decision: how the backend identifies the user
Initially chose a **server-side token store** (ConcurrentHashMap, `issue`/`resolve`/`revoke`, a `OncePerRequestFilter`, `@CurrentUserId` backed by a **request attribute not a ThreadLocal** — Tomcat reuses request threads, so a ThreadLocal without a guaranteed clear lets request N+1 inherit request N's user, the Day-11 MDC trap again). Reasoning: the day's objective is *authorization*; token→user resolution is the precondition, not the lesson.

Then the requirement changed (refresh + expiry + roles) and it was **replaced with Spring Security + JWT**. Why the mind changed:
1. **The ask changed.** "Refresh + expiry + roles" is a different problem from "resolve a user id" — hand-building all three would have produced a worse JWT.
2. **The anti-JWT argument was half right, and the right half saved the design.** "A JWT you can't revoke is worse than a map" is still true. The resolution wasn't to abandon JWT — it was to **stop making the refresh token a JWT**. The revocable credential went into the DB (which is what `TokenStore` always was); the unrevocable one got a 15-minute fuse. The argument didn't lose, it relocated.
3. **The framework gave something Day-5 reasoning couldn't anticipate:** `DaoAuthenticationProvider` dummy-hashes unknown accounts so wrong-email and wrong-password take the same time. The hand-rolled `passwordEncoder.matches` leaked that timing difference.
- Cost was real (a working, verified impl deleted). **What made it survivable is that the seam held** — `issue`/`resolve`/`revoke` was the right shape, and `RefreshTokenService` has essentially those three methods against a different store. A substitution, not a redesign. (The Day-16 plan said "the seam is the real lesson, not the storage choice." It was.)

## Auth architecture
| | Access | Refresh |
|---|---|---|
| Form | Signed JWT (HS512) | Opaque 256-bit random, SHA-256 digest in DB |
| TTL | 15 min | 7 days |
| Revocable | No — TTL *is* the blast radius | Yes |
| Lookup | None; principal rebuilt from claims | By digest |
Single-use rotation, so a stolen token is a race the attacker must win, and replaying a spent one is *detectable* → revoke the user's whole token family.
- `SecurityConfig`: stateless, **closed by default (allowlist not blocklist** — an endpoint added next month is protected the day it's written), CSRF off (credentials travel in a header; a cross-site form can't set one), `@EnableMethodSecurity`.
- **`JwtAuthenticationFilter` never rejects** — it populates the SecurityContext or leaves it empty; the 401 decision belongs to `RestAuthenticationEntryPoint`. That's what keeps permitted endpoints reachable.
- **`RestAuthenticationEntryPoint` (401) / `RestAccessDeniedHandler` (403) write the `ApiError` envelope by hand** — `@RestControllerAdvice` only sees exceptions thrown *inside* the DispatcherServlet. Without these, auth failures would be the one response shape in the API that didn't match.
- `TraceIdFilter` at `HIGHEST_PRECEDENCE` (Security's chain is −100) so 401s/403s carry a traceId. CORS moved into the security chain via `http.cors()`.
- `@CurrentUserId` survived as a **meta-annotation over `@AuthenticationPrincipal(expression="id")`** — controller signatures byte-identical, custom resolver deleted.
- Roles: normalised `roles` + `user_roles` (V10) so adding a role is an INSERT not a migration. Names carry the `ROLE_` prefix because `hasRole()` prepends it — storing bare `ADMIN` would silently never match. `/api/admin/**` guarded twice (URL rule + `@PreAuthorize`) so it survives a remapping.

## Scoping — the actual objective
Every read/write/download/delete resolves through a query with ownership **in the WHERE clause**: `findByIdAndUser_Id`, `findByIdAndOwner_Id`, JOINs for tasks and audit.
- **Cross-user access returns 404, never 403.** A 403 confirms the resource exists and leaks the id space. Folding ownership into the query means an unowned id simply doesn't resolve — "not yours" and "not there" collapse into one answer and the leak-free response falls out **for free instead of having to be remembered**. There is no `findById()`-then-compare anywhere, so there is never a moment where an unentitled resource is loaded in memory.
- **403 is for role failures** — the caller is known, and admitting the endpoint exists leaks nothing.
- Verified live: A→B's task 404 · A→B's messages 404 · A→B's session DELETE 404 · **B→own messages 200 (the control — proves the 404s aren't "everything 404s")** · admin 200 · non-admin 403 · anonymous 401.

## Everything else built (backend)
- **Document ownership (V13):** `owner_id NOT NULL` + FK + index. **Split the four seeded docs between both users** rather than giving all to one — with an empty library on one side the boundary is invisible in the browser. (Constraint: V8's citation links A's message to doc …2224, so that one had to stay with A or A's own chat would cite a file A can't open.)
- **Document storage + download:** added `storage_path` and `content_type`. The bytes were always written to `uploads/<uuid>` but **the location was never recorded** — metadata knew a document existed and not where it lived, which is why nothing could serve it. `GET /{id}/download` streams with `Content-Disposition: inline`, `Cache-Control: private, no-store`, and re-checks the resolved path against the upload root (the stored value is ours, not user input, but reading a file whose location came from a DB row is exactly the shape of a traversal bug).
- **`DELETE /api/documents/{id}`** — didn't exist; the Documents page delete button had been returning **405 the whole time**. Added, ownership-checked, file removed after the row.
- **`DELETE /api/chat/sessions/{id}`** — ownership-checked; messages/tasks/audit follow the Day-3 cascades.
- **Citations:** the table existed since V7 and the frontend had rendered citation cards since Month 1 — **and no Java code had ever touched the table.** Built `Citation`/`CitationRepository`/`CitationDto` matching the shape the cards were already written against (no frontend change needed), persisted on assistant replies, loaded in one query keyed by message (not N+1).
- **Document status:** upload set `pending` and nothing ever called `setStatus` — every document sat `pending` forever while being fully readable. Now `ready` once bytes are on disk (the truth); `processing`/`failed` remain for the Month-3 pipeline. V15 backfilled.
- **Sign-up** (`POST /api/auth/register`): returns the profile, **not tokens** — sign-up and sign-in stay separate so there's one place credentials become a session. `ROLE_USER` only; nothing self-service grants admin. Email lower-cased. Duplicate → 409, and **the pre-check is best-effort** — two simultaneous sign-ups both pass it, so the unique constraint is the real arbiter and `DataIntegrityViolationException` maps to the same 409. Password 8–72 chars **because bcrypt silently truncates past 72 bytes** — longer would look like it strengthens the password while doing nothing.
- **Password reset:** 256-bit token, digest only, single-use, 30-min expiry. `forgot-password` **always returns 202** whether or not the account exists — otherwise it's an account-existence oracle undoing the login anti-enumeration. A second request invalidates the first. **A successful reset revokes every refresh token** — resetting is what someone does when they believe they're compromised; leaving sessions alive would mean the attacker keeps access.
- **Mail:** `EmailService` over `JavaMailSender`, **turns itself on as soon as SMTP credentials exist** — a separate flag would mean configuring it correctly and still getting no mail, with a deliberate 202 and a silent log line as the only evidence. SMTP failures logged, never rethrown (a loud failure would leak that the address exists *and* strand the user).
- **Validation:** `CreateTaskPayload` had **zero constraints** against `VARCHAR(255) NOT NULL` — a blank or 300-char title was a 500 from Postgres instead of a 400. Added, plus `@Size` caps on message/session content (`messages.content` is TEXT = unbounded, so the cap must come from the DTO) and filename length. Verified live: 300-char title → 400 with a specific message; valid title → 200.
- **Secrets:** DB creds, CORS origins, JWT settings, mail all `${ENV:default}`. **`JwtSecretValidator` refuses to boot** if the checked-in dev signing key is in use outside dev/test/local, and enforces the 32-byte HS256 minimum. A misconfiguration that silently runs with a public key is strictly worse than a crash — the crash is loud at deploy time; the silent version is loud six months later. Proved the placeholders are live, not decorative, by booting with `DB_USERNAME=wrong-user-on-purpose` → `FATAL: role does not exist`.
- Cleanup: deleted the dead duplicate `ActionService.updateTaskStatus` (bare `RuntimeException`, `valueOf` on raw input); moved `User`/`UserRepository` into a `user` package.

## Bugs introduced and found (the diagnoses matter more than the fixes)
- **Revoke-then-throw in one transaction is a silent no-op.** Reuse detection revoked the family then threw — the rollback undid the revocation. It *appeared* to work (the replay 401'd) while doing nothing (the rotated replacement still worked). Live HTTP caught it; the test didn't. Fixed with `REQUIRES_NEW`. **Generalizable: any security side effect that must survive a rejection needs its own committed transaction.**
- **The test for it then deadlocked.** `AuthIntegrationTest` was `@Transactional`; the `REQUIRES_NEW` transaction runs on a second connection and waits on row locks the test's own transaction holds until the method returns. **A test asserting on what COMMITS cannot run inside a rollback-only transaction.**
- **`createSession` and `sendMessage` each built their own reply** and only the latter had the proposal branch (the same duplication had already forced citations to be added twice) — unified into one `respondTo()`.

## Clean-load verification (the finding worth repeating)
`createdb` → V1–V16 from scratch → full suite: 75/75 green, zero demo accounts (V16's fresh-DB behaviour sound). **But it left ten stray `user-<uuid>@test.local` rows** — invisible on a populated DB, which is why every *incremental* green run missed it. Same structural property as the V8 hash bug (different mechanism: that was a file disagreeing with a DB; this is test residue only visible when nothing else is in the table to hide it). **"The suite is green" was true and insufficient every single time.**
- Fixed both halves: transactional tests keep rolling back; `TestFixtures` tracks what it created with `cleanUp()` for the tests that can't be transactional. Re-verified on a third throwaway DB: 75/75, every table empty.
- **The clean-load check is now a repeatable handoff step whenever migrations change** — the practice that catches the family, not the instance.

## Scope discipline lapsed (honest finding)
In the morning, document download was deferred with a good argument (it couldn't express ownership yet). By evening the day had absorbed sign-up, password reset, mail, a theme system, document preview strategies, citations, and work explicitly labelled Day 19. **Nothing forced it** — each addition came from a direct request, which makes it easy to justify one at a time and hard to see in aggregate. The discipline shown in the morning is the thing that lapsed.

## Contract revision #1 — the first deliberate break
`POST /api/auth/login`: `{user, token}` → `{accessToken, refreshToken, tokenType, expiresIn, user, roles}`.
**Why unavoidable:** a session is no longer one credential. Two tokens with different lifetimes and revocation semantics don't fit `token: string`, and overloading it would hide the distinction the design rests on. **Blast radius:** that endpoint only; new routes are additive. `ChatSessionDto` also gained an additive `initialResponse`.
**Rule going forward:** a contract change gets a notes entry with before/after and a reason, **in the same commit as the change**. A break that's justified is fine; a break that's undocumented is drift.

## Migrations V9–V16
V9 user B + session + task · V10 roles/user_roles · V12 re-seed with `ON CONFLICT DO NOTHING` (V9's rows were deleted while testing the delete button, and **editing an applied migration breaks its checksum** — demo data the demo can destroy needs a repeatable way back) · V13 document `owner_id` · V15 status backfill · V16 retire demo accounts.

## Next (Day 17)
Observability — structured logs, request IDs (traceId exists since Day 11), error logs, operational debugging. Success: failures can be diagnosed from backend logs. Carry-ins: document `owner_id` is done so #3 shipped; 8 failing frontend tests still open; `FRONTEND_BASE_URL` for reset links.

---

# Backend Day 17 — Observability: logging and diagnostics

Success criterion: failures can be diagnosed from backend logs. **Demonstrated rather than asserted** — the request log found a real ten-day-old bug within minutes of existing (below). 81/81 green.

## Starting position: the constraint was a LIVE LEAK, not a design consideration
One login, before touching anything:
```
{"email":"...","password":"reset-password-worked"}
"accessToken":"eyJhbGciOiJIUzUxMiJ9…
"refreshToken":"n3VC62cWcIajf3oK_n08…
```
`logbook=TRACE` logs request/response bodies. **This was true since Logbook was added — but Day 16 changed its severity.** The logged token used to be `demo-token-<uuid>`, a meaningless string. It's now a working credential with a seven-day life. Same log line, noise → account takeover. A pre-existing setting became a vulnerability because the thing it printed changed underneath it.

## Secrets: mechanism over configuration, three paths closed
`toString()` overrides alone would NOT have caught this — **Logbook never calls `toString()`; it reads the raw HTTP body before Jackson has produced an object at all.**
1. **Logbook removed, not configured.** Its default behaviour is the exact thing that must never happen. A misconfigured Logbook leaks; a filter with no body access *can't*. **Configuration is a fact about a file, and facts about files drift; capability is a fact about the code's shape.** Not choosing a safer setting — removing the setting from existence.
2. **`toString()` overridden** on `LoginRequest`, `RegisterRequest`, `ResetPasswordRequest`, `RefreshTokenRequest` — closes the path where an exception message interpolates a DTO. (Records generate a `toString()` containing every component, so any log line interpolating one leaks its secrets.)
3. **`hibernate.orm.jdbc.bind=TRACE` off** — it was printing token digests and would print a bcrypt hash on registration.
4. **A test that survives a future re-enablement:** performs a login, asserts the password never appears in captured output, **captured at the ROOT logger** (a named-logger capture would pass while a different appender leaked). **Written first and watched fail — 4/4 red against unfixed code.** A leak-detection test you've never seen fail is one you don't know works. Same role as the control row in the Day-16 scoping matrix.

## Format: readable now, JSON deferred to Day 20 (deliberate)
JSON-per-line optimises for an aggregator that doesn't exist, at the cost of the one reader who does (the IntelliJ console). **The stronger argument: writing an output format that can't be verified because no environment exists to run it in is the same mistake as checking markdown rendering on a browser nobody uses.** Day 20 is deploy prep — that's when JSON becomes checkable.
- **What DID happen today: the log CONTENT is structured** (`key=value` everywhere, context in MDC). That makes the later switch a formatting change, not a rewrite of every call site — the same seam argument that made the `TokenStore`→JWT swap survivable.

## Request logging
`method`, `path`, `status`, `durationMs` (+ traceId, userId from MDC). Duration earns its place; the rest are the minimum to correlate.
- **Outside the security chain** so rejected requests are logged too — *a 401 you can't see is the request you most want to see.* Verified a 401 actually produces a line (an ordering mistake would silently drop exactly that case).
- **Explicitly NOT logged:** bodies, headers, query strings. Query strings matter because a reset token can arrive in one; path-only kills that whole class.

## Bug found while testing the filter: MDC double-ownership
Authenticated requests logged as `[anonymous]`. `JwtAuthenticationFilter` removed `userId` from MDC in a `finally`, while `TraceIdFilter` already ends every request with `MDC.clear()` — **the inner cleanup wiped it before the outer filter wrote its line. Two owners of one lifecycle.** Now one owner.
Worth noting the failure mode: this produces *wrong data*, not a crash — and the missing field is exactly the one needed to diagnose a user-specific issue, missing in a way that looks like the user wasn't authenticated.

## THE find: rejected uploads had been returning 500 for ten days
Minutes after the request log existed:
```
WARN  document.upload_rejected reason=unsupported_type filename=blocked.exe
ERROR http method=POST path=/api/documents/upload status=500
```
A deliberate rejection sitting next to a 500. One grep on the traceId found it: **`DocumentValidationException extends RuntimeException`, not `DomainException`** — so `GlobalExceptionHandler` never mapped it and every rejected upload fell to the catch-all as a 500 instead of a 400.
- **It's a Day-11 regression.** Consolidating four per-exception handlers into one `@ExceptionHandler(DomainException.class)` and deleting the redundant ones left this exception with no handler. **The same refactor produced two identical regressions: the login 401→500 was caught that day by re-running the existing error tests; this one lived ten days because no test existed for a rejected upload — the suite only ever uploaded a valid file.**
- **What test coverage actually buys:** not "the code works" but "a behaviour is pinned against future edits." Every unpinned behaviour is one refactor away from silently changing.
- Also the fifth instance of correct-logic-broken-wiring: upload validation was described as "in decent shape" on Day 16, and the *logic* was fine. The wiring wasn't.
- Fixed, with the two regression tests that were missing. Verified `400 INVALID_FILE_TYPE`.

## Service-level logs — only what the database can't tell you
Governance actions and approvals are reconstructable from `action_audit`; duplicating them in logs is noise. The three that the DB genuinely cannot answer:
- **Download of a file missing from disk** — the row says the document exists, the disk disagrees. **Logged at ERROR, not WARN: it means the system's state is internally inconsistent, a different severity from "a user sent a bad request."** Nothing recorded that divergence before.
- **Refresh-token reuse firing** — kept, as the security event it is.
- **Upload rejected by validation** — previously a 400 to the client and silence server-side, so "why do this user's uploads keep failing" was unanswerable.

## Next (Day 18)
Architecture — backend framework translation. Write notes mapping Spring controllers/services/repositories onto Express, NestJS, Django, FastAPI. Success: can explain how the same API would be built in another stack. A writing day, no code.

---

# Backend Day 18 — Backend framework translation

A writing day, no code. Deliverable is a standalone tracked file: **`ARCHITECTURE-TRANSLATION.md` at the repo root** (deliberately not buried in these notes — it's the most interview-usable artifact of the month). This entry records only the framing and the conclusions.

## The framing that made it worth doing
The failure mode was a syntax table (`@RestController` ↔ `app.get()` ↔ `@app.get()`) — accurate, lookup-able in ten minutes, teaches nothing. The question actually asked instead: **which of my decisions were Spring decisions and which were architecture decisions?** The only way to tell is to ask what survives a change of stack. Everything sorts into four groups, and the sorting IS the document.

- **A — Architecture, travels unchanged.** 404-not-403 on cross-user access; refresh token deliberately not a JWT; `forgot-password` always 202 (else it's an account-existence oracle); reset revokes all sessions; 72-byte password cap (bcrypt truncates silently); migrations forward-only, never edit an applied one; **single-flight refresh on the client — imposed by the server's security design, not by any framework on either side; the most stack-independent thing learned all month.**
- **B — Spring mechanisms with direct equivalents.** Error envelope (`@RestControllerAdvice` / error middleware / Exception Filters / `EXCEPTION_HANDLER` / `@app.exception_handler`), declarative atomicity, validation, typed config, cross-cutting request work, DI. NestJS is the closest relative by a distance; Express the furthest.
- **C — Spring/JVM artifacts that do NOT travel.** The most valuable section: things learned as "how backends work" that are really "how *this* backend works." **Dirty checking** (filed on Day 9 as a persistence concept — it's a Hibernate feature; Django needs an explicit `.save()`); **lazy loading / `LazyInitializationException`** (Django re-queries transparently — *same hazard, opposite failure mode: Hibernate throws, Django quietly does 50 queries*); **servlet filter ordering** (the MDC double-ownership bug needed two filters with numeric orders and implicit nesting to exist at all — in Express, middleware order is visibly the order you call `app.use()`); **MDC thread-locals** (Node has no request threads; `AsyncLocalStorage` is the analogue — the thread-reuse leak can't happen, but async-context loss across `await` boundaries can: *not fewer bugs, different bugs*); **Jackson polymorphism** (`visible=true` exists only because Jackson otherwise consumes the discriminator — Pydantic's `Field(discriminator='type')` is one line).
- **D — Same decision, different risk of getting it wrong.** Where the framework's value actually shows. `@Transactional` vs a manual commit; closed-by-default security in one line vs per-route middleware; ownership across a join (JPQL vs Django's `source_session__user` traversal — a point *against* Spring).

## The two conclusions worth keeping
1. **Spring's convenience is exactly what hid the revoke-then-throw bug.** Never wrote a commit → never thought about when it happened. *A framework that does something for you is a framework that stops you noticing it — fine until the day you need to reason about exactly that thing.*
2. **The debugging tax is stack-specific; the domain problem is portable.** Roughly even split this month between API-logic bugs (duplicated reply path, documents stuck `pending`, citations never wired, exception hierarchy turning rejections into 500s) and stack artifacts (MDC ownership, Jackson `visible`, record `toString()`, Logbook's TRACE default, Jackson 2v3, `noopener` returning null, StrictMode double-invoke, remount clearing a `useRef`, CSS specificity). Note the two columns have different *characters*: the logic bugs are all **wiring** (caught by "what does a user click to reach this?"); the artifacts are all **mechanism surprises** (caught only by reading what the framework does rather than assuming). **The design goes about as fast in an unfamiliar stack; the debugging does not.**

## A reasoning hazard found while writing it
"Ownership belongs in the WHERE clause" was filed under A with two justifications — and only one travels. *"The 404 falls out for free"* is architecture; *"no window holding an unentitled row"* is largely an ORM artifact (`findById` handing back a formed object is what makes load-then-check tempting; writing SQL you're already composing the WHERE clause). **A conclusion supported by two arguments looks stronger, but if the arguments belong to different categories the bundle silently inherits the weaker one's scope.** Split across A and D.

## Next (Day 19)
Performance basics — N+1 queries, pagination, indexing, response shape, payload size. Success: document/chat/task APIs stay practical with larger demo data. (Note: the Day-6 pagination decision — bare array now, `{items,total,page,size}` envelope as a synchronized FE+BE change — comes due here. And the frontend responsive work labelled Day 19 was already pulled forward into Day 16.)

---

# Backend Day 19 — Performance basics

Success criterion: document/chat/task APIs stay practical with larger demo data. 92/92 green, clean-load verified.

## Headline: there were NO N+1s — a negative result worth pinning
Expected some; five list endpoints, all **O(1) in query count**. Proven by a test that runs each against **one row, then ten, and asserts the query count is unchanged**.
- **Asserting on a COUNT, not a timing, is the point.** An N+1 is invisible in a timing at demo scale and only becomes latency long after the code was written. A timing test would have passed regardless.
- **What prevented them: the DTO discipline of never touching a lazy relation inside `from()`.** That decision was made on **Day 4 for a different reason** (avoiding `LazyInitializationException`) and turns out to have prevented a class of performance bug nobody was thinking about at the time. *A constraint adopted for one reason often pays out somewhere unrelated* — the same discipline that made Day 8's sessions lazy-safe made these list endpoints query-flat. Now pinned by a test, so the accidental benefit becomes a guaranteed one.

## Wrong about the indexes — and measured it rather than asserting it
Predicted the missing FK indexes would speed up cascade deletes:
| | Before | After |
|---|---|---|
| Demo volume (400 audit rows) | 4.08ms | 3.91ms — **noise** |
| 120,000 audit rows | 21.89ms | 11.83ms |
Reasoning sound, **scale prediction wrong**. The migration comment now says exactly that instead of claiming an unobserved speedup. *"No measurable effect at demo volume, ~2x at 120k rows" is worth more than "adds indexes for performance" — it tells the next person when to care.*

## Pagination (contract revision #2) — the envelope was the easy part
Three things had to change or **the feature would have been actively worse**:
- **Search moved server-side.** A client-side filter over a paged list only searches the *loaded page* — the search box would have silently ignored 230 of 250 documents. A search that appears to work and covers 8% of the corpus is worse than no pagination.
- **The Dashboard got cheaper.** It renders three documents and three counts and was fetching **all 250** to compute them. Now three rows plus three size-1 queries read for their `total`.
- **Page size clamped at 100.** `?size=1000000` is a one-request denial of service. **Size is proposed by the client and decided by the server** — generalizes well past pagination.
- **Deliberately NOT paginated: the message transcript.** That needs a load-older pattern, not an envelope; a numbered pager on a chat would be worse than leaving it. Recorded as a deferral, not an oversight.
- (This is the Day-6 decision coming due — bare array then, envelope now, as a synchronized FE+BE change exactly as the contract flagged.)

## Broke my own rule immediately
**Edited V17's comment after it had been applied**; Flyway refused to start on the checksum mismatch — *the exact mistake written about three times this month.* Comment-only and local-only, so the honest repair was to un-apply and let it land fresh.
**Knowing a rule and following it under momentum are different things** — and a comment-only change is precisely when the rule feels least like it applies. Note that **Flyway WAS the mechanism**: it refused to start. The system worked; the memory didn't.

## Yesterday's traceId paid for itself twice more
- A **null String parameter reaching Postgres as `bytea`** — every unfiltered document list was a 500.
- The paged hook **decrementing `total` on uploads**.
  Both found by grepping one id; both now regression-tested.

## Open decision
`perf@test.local` (60 sessions, 2,400 messages, 250 documents, 300 tasks, ~390 audit rows) is resident in the dev database. Useful for demonstrating pagination; also makes every future clean-load and manual DB inspection noisier. **Should be a choice, not residue** — keep and document, delete now the measurements are taken, or move behind a `perf` profile generated on demand. Day 22 is a demo, which argues for keeping it.

## Next (Day 20)
Deploy prep. Also where the **JSON log format deferred on Day 17** becomes checkable — there'll finally be an environment to verify it in, and the log content is already `key=value` so it's a formatting change, not a rewrite.

---

# Backend Day 20 — Deployment prep: environment config and local runbook

Success criterion: **another engineer can start the app from documented steps.** Deliverable is `README.md` at the backend repo root, written as a runbook and **verified by walking it on a fresh database without using anything not written down**.

## The day's real work: the Flyway baseline config was a trap
Tested both branches rather than reasoning about them:
| Database state | What Flyway does | Result |
|---|---|---|
| Genuinely empty | runs V1–V17 | 12 tables, correct |
| **Any pre-existing table, no history** | **baselines at V8, skips V1–V8** | `relation "users" does not exist` |
- **`baseline-version=8` was an artifact of MY database's history, not a project requirement.** It existed only because V1–V8 were hand-applied before Flyway was wired (the thirteen-day no-op). My dev DB has the `V8 BASELINE` row recorded permanently, so **the setting can never fire for me again — it fires only where there's no history table, which now means only on someone else's machine.** Zero remaining benefit, pure hazard. **Deleted, not documented.**
- It fails *loudly* (the tolerable half), but **the error names what is MISSING, not what was SKIPPED.** Nothing in `relation "users" does not exist` hints that a baseline setting skipped schema creation. General property: *a config that changes what RUNS produces errors that describe what's ABSENT, and the distance between those two is where debugging time goes.*

## The measurement I had to throw away — and why it matters most
The first run of the broken case reported `health: 200`. **That was a process from the previous case still holding 8080** — a stale listener answering for the *wrong application*.
**A false negative on a "does this break?" test is uniquely dangerous because it ENDS the investigation.** A false positive sends you looking and you find nothing; a false negative tells you the trap is harmless and you ship it. Had it stood, nothing would have been deleted or documented and the config would have sat waiting for the next person's laptop.
Same shape as several things this month: the suite green and insufficient, the timing test that passes at demo scale, markdown rendering checked in the wrong browser. **Every one is a check that answers a question adjacent to the one asked.**

## JSON logging landed — the Day-17 deferral didn't survive scrutiny
A **locally runnable `prod` profile is a real environment**, so "I can't verify the format" no longer held. Verified rather than assumed: 30 log lines parsed as JSON, zero malformed, `traceId`/`userId` as **top-level fields** rather than buried in the message — which is the entire point of the format. Bonus: the prod profile exercises `JwtSecretValidator` for real (weak secret → refuses to boot) and Swagger 404s under prod.

## Docker: omitted deliberately, with the reason stated
Not installed here (company policy), so any `docker-compose.yml` would be **untested**. The README says so plainly and gives the three facts a Docker user needs instead (`postgres:16`, db name, `DB_URL`). **A documented path that fails costs a reader more than an absent one, because they will trust it and debug it before doubting it.** Stating the reasoning also stops the next person helpfully adding an untested compose file.

## Verified in the walk (each claim checked, not asserted)
Empty DB → 12 tables, **zero users** (V8/V9 create demo accounts, V16 retires them — so first run is *sign up*) · new account → empty workspace (not a broken install) · cross-user → 404 · no token → 401 · `size=99999` → clamped to 100 · `X-Trace-Id` correlates to the log · **password appears 0 times in the log** · `./mvnw test` → 92/92 on a clean database.

## Two carried assumptions that expired
- **`./mvnw --version` works now** (Maven 3.9.16, wrapper-downloaded). The Day-1 network block is gone. **Constraints get recorded once and then stop being re-checked — and some of them expire.** Nineteen days of using IntelliJ's bundled Maven rested on a fact that had stopped being true.
- Deleting `perf@test.local` hit the `citations.document_id` **RESTRICT** constraint — the one designed on Day 3 and proven then. Doing exactly its job, three weeks later. Cleared citations first.

## Notes on the README itself
- §9's common-failures table is written **from scars, not imagination** — six of seven rows are things that actually cost time this month (`postmaster.pid`, port 8080, the JWT guard, the baseline error).
- Limit worth naming: the whole §2 path assumes **macOS/Homebrew Postgres** behaving as this machine's does. Can't be tested without another laptop — a limit, not a gap.
- Starting state is now defined: `perf@test.local` and its ~3,400 rows deleted so the documented state matches reality.

## Next (Day 21)
Contract review — review every frontend flow against the real backend APIs; produce a milestone bug list and fixes. Success: **all Month-1 mock APIs have real Spring Boot equivalents.** Given this month's recurring finding (five instances of correct-backend-no-path-from-product), this is the day that pattern gets systematically hunted rather than stumbled into.

---

# Backend Day 21 — Contract review: the milestone audit

Success criterion: **all Month-1 mock APIs have real Spring Boot equivalents.** Met (14/14). But the criterion was the least interesting part of the day.

## The contract never existed
`API_CONTRACT.md` was not in either repo and never had been. **For two months the contract lived in three places that could disagree — the frontend's `Type.ts`, the MSW handlers, and prose in `notes.md` — with nothing reconciling them.**
Worth sitting with: *"the frozen Day-21 contract"* was invoked as an authority repeatedly this month, in reasoning that held up, and it named a fiction. **The discipline was real and did constrain decisions; the artifact was not.** Written today **from the running service, not transcribed from source** — the only honest option once that was discovered.

## Three diffs, three directions
| Direction | Finds | Result |
|---|---|---|
| mock → real | *missing* endpoints (the literal criterion) | 14/14 |
| UI → endpoint | frontend controls calling nothing (the 405 class) | zero orphans |
| endpoint → UI | *unreachable* capability (the month's pattern) | 3 unreached |
Unreached: `/api/health` (correct — it's a probe), `/api/admin/users`, `/api/auth/logout-all`. The last two were **the sixth and seventh instances** of the pattern. Both wired: an Admin page behind a role-gated nav link, and "Sign out everywhere" in Settings — *which matters precisely when someone believes another device is compromised, and ordinary logout does nothing about that.*
Making direction 3 mechanical: grep every `apiFetch(` call site for distinct paths, diff against controller mappings. Both orphan classes fall out automatically.

## The fourth direction — correct by URL, wrong by shape
Wiring the admin UI broke instantly on `undefined.map`. **`/api/admin/users` returned a bare array while every other list returns the paged envelope** — missed by Day 19 because *nothing called it, so no consumer noticed.* Recorded as contract revision #3.
**All three diffs operate on identity — does this path exist on both sides. The admin endpoint passed every one and was wrong in the only dimension none could see.** A path-level diff is structurally blind to shape.
**The compounding finding: an unreached endpoint doesn't sit unused — it DRIFTS.** It misses the refactors that touch its siblings, because the thing that normally catches a missed refactor is *a consumer breaking*, and an endpoint with no consumer has none. That's an argument for reaching endpoints promptly **independent of "users can't use it"** — even a capability nobody needs yet should have a consumer, if only a test, because the consumer is what keeps it honest through refactors.

## The eight frontend tests: a deferral wearing a verdict's clothes
"Fix or delete, and deleting is legitimate" was two decisions posing as one, resting on an **unchecked claim** — that they asserted a two-month-old UI. They didn't. **All nine assert behaviour that still exists, including the governance approval flow, the single most valuable test in either suite.** One step from deleting the best coverage on the strength of a plausible assumption. *Same failure mode as the branch position, the shipped-vs-open items, and the stale listener: a confident claim about state, from a mental model rather than a look.*
**The actual cause was two independent disconnections stacked:**
1. **Mechanical.** MSW registers handlers on *relative* paths; `apiFetch` (Day 15) prefixes `VITE_API_BASE_URL` unless `VITE_USE_MOCK` is set. Every request went to an absolute URL and matched no handler. **The suite broke the day `apiFetch` landed.**
2. **Invisibility.** No `npm test` script until Day 16, so nobody could see it.
   **Neither failure is durable alone** — a broken suite with a working command gets noticed on the next run; an unreachable suite stays honest until something breaks it. **Two independent gaps composed into an invisibility that neither produces on its own** — the second instance of that shape this month (Day 17: a harmless Logbook setting plus a change in what it printed). Neither was a bug when introduced.
   Fixed: `mocks/handlers.ts` got 5/9; the remaining 4 were `DocumentsPage.test.tsx`'s own inline handler overrides, drifted separately. **9/9 green for the first time since Month 1.**

## The real diagnosis: copy count, not missing tests
**The contract has four hand-maintained copies — backend DTOs, `Type.ts`, `mocks/handlers.ts`, per-test overrides — and all four drifted independently this month, each found by a different accident.**
That's a normalization problem, not a testing gap. The naive fix (a test hitting the real backend from the frontend suite) reintroduces every Day-14 isolation problem. **The tractable fix: generate `Type.ts` from the OpenAPI spec springdoc already publishes**, and type the mocks against the generated types — collapsing four copies to one source plus derivations, and turning drift from a *discovery* into a *compile error*.
Caveat worth recording: **`API_CONTRACT.md` is now a fifth copy.** Accurate today, hand-maintained, so it can drift tomorrow. It's the right artifact — it documents the two client obligations no generated type can express (rotation semantics, ephemeral proposals) — but it should state that **the generated spec is authoritative for shapes and this document for behaviour**, or revision #4 will be someone trusting the wrong one.

## Deliverables
- **`API_CONTRACT.md`** — written from the running service. All three revisions recorded with before/after/reason, plus the rule that future changes land with their entry in the same commit.
- **`BACKLOG.md`** — every deferral with a **verdict, not a place on a list**: 3 DEBT, 4 MONTH 3, 6 BY DESIGN, 10 DONE.
- Admin page + "Sign out everywhere" wired; the eight failing tests fixed.

## Next (Day 22)
Milestone demo — API walkthrough, database walkthrough, test walkthrough, self-assessment. Success: React frontend connected to Spring Boot with PostgreSQL persistence, demoed end to end.

---

**Month 3 continues in a separate journal:** `genai-service/NOTES.md`. The GenAI service is
its own codebase, so its journal lives beside it rather than extending this file.
