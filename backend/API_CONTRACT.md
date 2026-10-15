# API Contract

**Status:** written on Day 21 of Month 2, from the running application.

This document did not exist before. For two months the contract lived in three places that could disagree with each other — the frontend's `Type.ts`, the MSW mock handlers, and prose in `notes.md` — and it drifted, because nothing reconciled them. Two revisions had already happened and were recorded only as notes entries.

Every endpoint below was verified against the running service, not transcribed from the source.

---

## Conventions

**Auth.** Everything except `/api/auth/**` and `/api/health` requires `Authorization: Bearer <accessToken>`. Missing or invalid → `401`. Authenticated but insufficient role → `403`.

**Ownership.** Every resource is scoped to its owner. Another user's resource returns **`404`, never `403`** — a 403 would confirm it exists.

**Errors.** One envelope everywhere:

```json
{ "message": "...", "code": "VALIDATION_ERROR", "timestamp": "2026-09-01T…Z", "traceId": "…" }
```

`traceId` also appears in the `X-Trace-Id` response header and on every server log line for that request.

**Paged lists.** All list endpoints return:

```json
{ "items": [ … ], "total": 250, "page": 0, "size": 20 }
```

`?page=` is zero-based, `?size=` defaults to 20 and is **clamped to 100**. Negative or nonsensical values fall back to defaults rather than erroring.

---

## Authentication — `/api/auth`

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/login` | none | → `AuthResponse` |
| POST | `/register` | none | `201` → `UserDto`. Duplicate email → `409`. Grants `ROLE_USER` only |
| POST | `/refresh` | none | Refresh token is the credential. Rotates single-use |
| POST | `/logout` | bearer | Revokes one refresh token |
| POST | `/logout-all` | bearer | Revokes every refresh token for the account |
| POST | `/forgot-password` | none | **Always `202`**, whether or not the account exists |
| POST | `/reset-password` | none | Token single-use, 30-min expiry. Revokes all sessions |

```jsonc
// AuthResponse — login and refresh
{
  "accessToken": "eyJ…",     // JWT, 15 minutes, not revocable
  "refreshToken": "n3VC…",   // opaque, 7 days, single-use, revocable
  "tokenType": "Bearer",
  "expiresIn": 900,          // SECONDS
  "user": { "id": "…", "email": "…", "name": "…" },
  "roles": ["ROLE_USER"]
}
```

> **Refresh tokens rotate, single-use.** Concurrent refreshes are indistinguishable from token theft and revoke the whole family. A client **must** dedupe refreshes behind one in-flight request. This is a requirement the server imposes on the client, not an optimisation.

Password rules: 8–72 characters. The upper bound is real — bcrypt silently truncates beyond 72 bytes.

---

## Documents — `/api/documents`

| Method | Path | Notes |
|---|---|---|
| GET | `/` | Paged. `?status=`, `?search=` (filename, case-insensitive, applied in the database) |
| POST | `/upload` | multipart `file`. `201` → `DocumentDto` |
| GET | `/{id}` | Metadata |
| GET | `/{id}/download` | Bytes. `Content-Disposition: inline`, `Cache-Control: private, no-store` |
| GET | `/{id}/deletion-impact` | What deleting it would also delete. `{ documentId, filename, chats[] }` |
| DELETE | `/{id}` | Removes the row and the stored file. **`409 DOCUMENT_IN_USE`** if conversations cite it; `?deleteLinkedChats=true` deletes them too |

```jsonc
{ "id": "…", "filename": "report.pdf", "sizeBytes": 2048576,
  "uploadDate": "2026-08-11T…Z", "status": "ready" }
```

`status` ∈ `pending | uploading | processing | ready | failed`. **Today only `ready` is ever set** — a document is marked ready once its bytes are stored. `processing` and `failed` describe the Month-3 ingestion pipeline and nothing produces them yet.

### Deleting a document that conversations cite

`citations.document_id` is `ON DELETE RESTRICT`, so a document used by a conversation cannot
be removed without removing that conversation. Call `deletion-impact` first and show the user
what they would lose:

```jsonc
{ "documentId": "…", "filename": "Q3_Financials.pdf",
  "chats": [
    { "id": "…", "title": "tell me about finance",
      "messageCount": 10,
      "otherDocuments": [                       // NAMED, and NOT deleted
        { "id": "…", "filename": "Budget_2026.xlsx" }
      ] }
  ] }
```

An empty `chats` array means the document deletes outright. `otherDocuments` is what makes
the confirmation honest — a conversation is not necessarily *about* the document being
deleted, and one citing four documents would be destroyed by deleting any one of them.

**The documents in `otherDocuments` are not deleted.** Only the document named in the path
and the conversations citing it are removed; the other material survives and only the
*discussion* of it is lost. They are returned with ids so a client can link to them.

`deleteLinkedChats` defaults to **false**, so a client that has not been updated keeps the
safe behaviour and gets a `409` explaining itself rather than silently destroying
conversations. Deleting a session cascades in the database to its messages, their citations,
its action audit rows and any task created from it.

Upload limits: 10MB, filename ≤ 255 chars, types `.pdf .txt .md .markdown .csv .docx .xlsx`. Rejections are `400` with a specific code, not `500`.

---

## Chat — `/api/chat`

| Method | Path | Notes |
|---|---|---|
| GET | `/sessions` | Paged |
| POST | `/sessions` | `201` → `ChatSessionDto` **including `initialResponse`** |
| DELETE | `/sessions/{id}` | Cascades to messages, tasks, audit rows |
| GET | `/{sessionId}/messages` | **Not paged** — see below |
| POST | `/message` | `201` → `MessageDto` |

```jsonc
// MessageDto
{ "id": "…", "content": "…", "sender": "assistant", "timestamp": "…",
  "citations": [ { "id": "…", "documentId": "…", "documentName": "notes.md",
                   "section": "…", "excerpt": "…" } ],
  "actions":   [ { "id": "act-…", "type": "create-task",
                   "label": "Create a tracking task for this request",
                   "payload": { "title": "…", "priority": "medium" } } ] }
```

Two properties a client must know:

- **`actions` are ephemeral and never persisted.** They arrive with the live response only; refetching history returns the message *without* them. A client that re-renders from history will lose the proposal card unless it retains them itself.
- **`initialResponse` on session creation exists for that reason.** The opening reply must travel with the create response, because there is no later request that can return its proposal.

`GET /{sessionId}/messages` is deliberately **not paged**. Paging a transcript needs a load-older interaction, not an envelope, and a numbered pager on a conversation would be worse than none. Recorded as a deferral, not an oversight.

---

## Tasks — `/api/tasks`

| Method | Path | Notes |
|---|---|---|
| GET | `/` | Paged. `?status=` |
| PATCH | `/{id}` | `{ "status": "done" }`. Sets/clears `completedAt` |

Tasks have no owner column — ownership resolves by joining through the originating chat session.

---

## Actions — `/api/ai/actions`, `/api/actions/audit`

| Method | Path | Notes |
|---|---|---|
| POST | `/api/ai/actions` | Governance decision |
| GET | `/api/actions/audit` | Paged |

```jsonc
// request
{ "actionId": "act-123", "sessionId": "…", "decision": "approved",
  "type": "create-task", "payload": { "title": "…", "priority": "high" } }

// response — status is the EXECUTION result, not the decision echoed back
{ "actionId": "act-123", "status": "completed", "type": "create-task",
  "result": { /* TaskDto when a task was created */ } }
```

`decision` ∈ `approved | rejected`. `status` ∈ `completed | rejected | failed` — **`failed` is never produced today**; it exists for real tool execution in Month 3.

**An audit row is written for every decision, including rejections.** That is the point of the flow: the record shows what was proposed and what a human decided, whether or not it executed.

`payload` is discriminated by `type`: `create-task` → `{title, priority}`, `summarize-document` → `{documentId}`, `lookup-knowledge` → `{query}`.

---

## Administration — `/api/admin`

| Method | Path | Notes |
|---|---|---|
| GET | `/users` | Paged. **`ROLE_ADMIN` only** — otherwise `403` |

No self-service path grants `ROLE_ADMIN`; it must be assigned in the database.

---

## Health — `/api/health`

Unauthenticated. `{ "status": "UP" }`.

---

## Revision history

**Revision 1 — Day 16 — `POST /api/auth/login`**
`{ user, token }` → the six-field `AuthResponse`. A session stopped being one credential: two tokens with different lifetimes and revocation semantics cannot be expressed as `token: string`.

**Revision 2 — Day 19 — all list endpoints**
Bare array → `{ items, total, page, size }`, plus `?page=`/`?size=`. Every list returned its whole table; at demo volume that was 39KB of documents and 83KB of audit rows per page load, growing without bound.

**Revision 3 — Day 21 — `GET /api/admin/users`**
Bare array → the paged envelope. It was missed by revision 2 because **nothing called it**, so no consumer noticed the divergence. Found by wiring a UI to it during this audit, when the page failed on `undefined.map`. A path-level diff cannot catch this class: the endpoint existed and was correct by URL, and wrong only by shape.

**Rule going forward:** a contract change gets an entry here, with before, after, and a reason, in the same commit as the change.
