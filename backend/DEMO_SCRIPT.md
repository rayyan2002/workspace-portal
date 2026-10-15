# Milestone Demo — Running Order

**15 minutes.** Month 2 backend: Spring Boot + PostgreSQL behind the existing React frontend.

Every step below was executed end to end on 2026-09-02 and the stated output is what it produced. Nothing here is untested.

---

## Before they arrive (10 minutes ahead — not live)

| | |
|---|---|
| 1 | `brew services start postgresql@16` → `pg_isready` |
| 2 | `./mvnw spring-boot:run` — **start early.** Startup has ranged 7–29 seconds and a slow one is dead air |
| 3 | `npm run dev` in the frontend |
| 4 | Open: two browser windows (one normal, one incognito), a terminal at the backend log, a `psql -d knowledge_assistant`, and Swagger at `/swagger-ui/index.html` |
| 5 | Log the normal window in as yourself. **Leave incognito at the login page** — signing up is step 1 |

> **Do not do the refresh-rotation demo on this instance.** It needs `JWT_ACCESS_TTL=5s`, which is a separate start. Either run a second backend for it or move it to the end and restart. Decide beforehand.

---

## 1 · Sign-up, and the empty workspace  (90 seconds)

In **incognito**, sign up as `reviewer@demo.local`.

Three things at once: registration works, the account gets `ROLE_USER` only, and it lands on a completely empty workspace.

> "Everything is scoped per user, so a new account starts with nothing. No documents, no conversations, no tasks. That's not a broken install — it's the authorization model showing through."

**Verified:** `register → 201`, and `/documents`, `/chat/sessions`, `/tasks` all `total=0`.

---

## 2 · Ownership scoping — the ten-second version  (2 minutes)

Put the windows side by side. **Different sidebars, different documents, different tasks.**

Then the part that matters. Copy a session id from your own URL and paste it into the incognito address bar:

```
/chat/9cb0469a-a7ef-4442-9984-b61469851994
```

**Verified:** `404`.

> "Not 403. A 403 would confirm the resource exists and leak the id space. Ownership is part of the WHERE clause, not a check after loading — so another user's id simply doesn't resolve, and 'not yours' and 'not there' are the same answer. The leak-free response falls out of the query rather than having to be remembered at every call site."

If asked *"couldn't you just check the owner after loading?"* — that's the point. Loading first means holding a row you aren't entitled to, even briefly, and it puts the check somewhere a future edit can forget.

---

## 3 · Governance asymmetry — reject, don't approve  (2 minutes)

In chat: *"Please follow up on the runway inspection."* A proposal card appears.

**Click Reject.**

**Verified:** tasks `total=0`, audit `total=1`, `decision=rejected`.

> "The rejection is the interesting half. The AI proposed, a human declined, and the system recorded that it was declined. An assistant that can't be told no — and can't prove it was told no — isn't governable. Approving is the boring case."

Then approve one, and show the task appear alongside a second audit row.

---

## 4 · Trace correlation  (2 minutes)

Upload a `.exe`. It's rejected. Show the response:

```json
{"message":"Unsupported file type.","code":"INVALID_FILE_TYPE","traceId":"5f660a99-…"}
```

Copy the `traceId`, grep the log:

```
upload_rejected reason=unsupported_type owner=711dc90e-… contentType=application/octet-stream
http method=POST path=/api/documents/upload status=400 durationMs=63
```

> "One id from the response finds every log line for that request — the service-level reason, the HTTP result, and a stack trace if there was one. This is how the 500-instead-of-400 bug was found: a deliberate rejection sitting next to a `status=500` in the same trace, which is a contradiction you can see."

**No bodies are logged** — no password, token, or document content. A test fails if that regresses.

---

## 5 · Refresh rotation  (2 minutes — needs the 5s-TTL instance)

Log in, wait seven seconds, reload. **Still logged in.** Network tab shows a `POST /api/auth/refresh` between two 401s.

**Verified:** `200` → (expiry) → `401` → (refresh) → `200`, and replaying the spent refresh token → `401`.

> "Access tokens last 15 minutes and can't be revoked, so their lifetime is their blast radius. The refresh token is deliberately *not* a JWT — it's opaque, stored as a hash, single-use, and revocable. Replaying a spent one is treated as theft and revokes the whole family."

The consequence worth naming, because it's counter-intuitive:

> "That forces something on the client. Concurrent refreshes are indistinguishable from a stolen token being replayed, so a client that fires several logs the user out — by trying too hard. Single-flight refresh isn't an optimisation, it's a correctness requirement the server's security design imposes."

---

## 6 · The four walkthroughs  (4 minutes)

**API — Swagger.** 23 endpoints. Authorize with a real token and run one live. Point at `/api/admin/**` requiring `ROLE_ADMIN`.

**Database — psql.**
```sql
\dt
SELECT decision, count(*) FROM action_audit GROUP BY decision;
```
12 tables. Note `citations.document_id` is `ON DELETE RESTRICT` while everything else cascades — a document with a citation pointing at it can't silently vanish.

**Tests.** `./mvnw test` → **92 passing**. `npm test` → **9 passing**. Three worth naming:
- **Query-count test** — runs each list endpoint against 1 row and then 10 and asserts the query count is *unchanged*. Asserting on a count rather than a timing, because an N+1 is invisible in a timing at demo scale.
- **Log-redaction test** — captures at the *root* logger and asserts no password or token appears. Written before the fix and watched to fail, because a leak-detection test you've never seen fail is one you don't know works.
- **Cross-user 404s** — two users built per test, because with one user every scoping assertion passes whether or not scoping exists.

**Self-assessment.** Section below.

---

## 7 · Self-assessment  (2 minutes)

Lead with this, not with the feature list. The features are visible; this isn't.

### Judgment errors

**Scope discipline lapsed.** On Day 16 I deferred document download for a good reason — the schema couldn't express ownership yet, so the endpoint would have shipped with a check it couldn't make. By that evening I'd folded in sign-up, password reset, mail, a theme system, and work labelled for a different day. Each addition was individually justifiable, which is exactly how scope goes. The discipline I showed in the morning is what lapsed by evening.

**The contract was a fiction.** I cited "the frozen contract" as an authority for two months. It named three files that could disagree — and did. The discipline was real, which is why nobody noticed the artifact wasn't. Written properly on Day 21, from the running service rather than from source.

### Process gaps

**Six capabilities were complete, correct, and unreachable** — the audit trail, the governance loop, both deletes, citations, the admin endpoint. One was the mirror image: a delete button calling an endpoint that never existed, returning 405 for ten days. Cause: work sequenced by layer, so "the endpoint works" and "a user can do it" were never the same milestone.

The compounding version is worse. **An unreached endpoint doesn't just sit unused — it drifts.** `/api/admin/users` was skipped by the pagination sweep for exactly one reason: nothing called it, so nothing broke. It stayed wrong until someone finally connected it.

**Four hand-maintained copies of one contract** — backend DTOs, `Type.ts`, mock handlers, per-test overrides. All four drifted independently. The fix isn't another test category; it's generating the frontend's types from the OpenAPI spec so drift becomes a compile error.

### Predictions I got wrong and measured

The category I'd most want judged on.

- I predicted FK indexes would speed up cascade deletes. Measured: **4.08ms → 3.91ms — nothing.** At 120,000 rows: 21.9ms → 11.8ms. Right reasoning, wrong scale, and the migration comment says so rather than claiming a speedup I didn't observe.
- I claimed eight failing frontend tests asserted a UI that no longer existed. Looked properly: **every one was still valid.** They broke on a URL-base change the day `apiFetch` landed.
- I edited a migration comment after it was applied and Flyway refused to boot — the exact mistake I'd been writing about all month. Knowing a rule and following it under momentum are different.

> "Those are the ones I'd lead with. The first two categories a reviewer can reconstruct from the git log. The third is the only evidence about how I work — not that I'm right, but that I check, and write down the answer when it contradicts me."

---

## If something breaks live

| Symptom | Say this, then |
|---|---|
| Backend won't start | "This is the startup-order thing in the runbook." → `pg_isready`, then check 8080 |
| Port 8080 in use | `lsof -ti :8080 \| xargs kill` |
| Blank page after login | Token expired mid-demo. Reload — it refreshes silently. **This is demo 5 happening for real** |
| A request 500s | **Use it.** Take the traceId and find it live. That's demo 4, unrehearsed |

The last row is genuine: an unplanned failure is the strongest version of the observability demo, because nobody can suspect you set it up.

---

## Closing

> "Month 1 was a React app against mocks. Month 2 replaced every mock with a real Spring Boot endpoint on PostgreSQL — 23 endpoints, 12 tables, 101 tests. The part I'd point at isn't the feature count, it's that the security properties are structural rather than remembered: cross-user access is 404 because ownership is in the query, rejections are audited because the audit write precedes the branch, and credentials can't reach the logs because a test fails if they do.
>
> Month 3 makes the assistant real. The citation pipeline, the tool-calling flow and the governance loop are already built and wired — retrieval replaces a placeholder document picker, and nothing downstream changes."
