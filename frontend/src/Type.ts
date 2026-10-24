// ==========================================================================
// Base Constants & Enums
// ==========================================================================
export const DOCUMENT_STATUSES = ['pending', 'uploading', 'processing', 'ready', 'failed'] as const
export type DocumentStatus = typeof DOCUMENT_STATUSES[number]

export const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024

export const ALLOWED_MIME_TYPES = [
  'application/pdf',
  'text/plain',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'text/markdown',
  'text/csv',
  'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
]

export type Sender = 'user' | 'assistant'

/**
 * REMOVED on Day 14b: `ActionStatus = 'pending' | 'approved' | 'rejected'` used to be here.
 *
 * It matched NO backend enum. Spring has two and this was neither: `ActionStatus` is
 * `completed | rejected | failed` and `ActionDecision` is `approved | rejected`. The value
 * 'pending' existed nowhere in the system. It survived because it had zero consumers — the
 * `ActionResult` union below declares its own statuses inline — which is exactly how an
 * unchecked hand-written contract rots: the wrong part is the part nobody uses, until
 * somebody uses it.
 *
 * Both vocabularies now come from ACTION_DECISIONS and ACTION_RESULT_STATUSES below, which
 * Type.conformance.test.ts holds to the committed backend snapshot.
 */

// ==========================================================================
// Core Entities
// ==========================================================================
export interface APIError {
  message: string
  code?: string
}

export interface NavLink {
  label: string
  to: string
}

export interface User {
  id: string
  email: string
  name?: string
}

/**
 * A user as `/api/admin/users` returns them — V25.
 *
 * Separate from `User` because the admin list is the only place role information is
 * published. Widening `User` would carry a person's privileges into every auth response
 * that ever mentions them.
 */
export interface AdminUser extends User {
  /** Whether this account currently holds ROLE_ADMIN. */
  admin: boolean
}

export interface LoginRequest {
  email: string
  password: string
}

/**
 * Contract revision (backend Day 16b): login previously returned `{ user, token }`.
 * The single opaque token was replaced by a JWT access token plus a revocable refresh
 * token, which cannot be expressed in the old two-field shape.
 */
export interface AuthResponse {
  accessToken: string
  refreshToken: string
  tokenType: 'Bearer'
  /** Access-token lifetime in SECONDS, so the client can refresh before it expires. */
  expiresIn: number
  user: User
  roles: string[]
}

export interface Document {
  id: string
  filename: string
  sizeBytes: number
  uploadDate: string
  status: DocumentStatus
}

/**
 * What deleting a document would also delete. Mirrors
 * `document/dto/DocumentDeletionImpact.java`.
 *
 * `citations.document_id` is ON DELETE RESTRICT, so a document cited by a conversation
 * cannot be removed without removing that conversation. An empty `chats` array means the
 * document can be deleted outright.
 */
/** A document an affected conversation also cites. It is NOT deleted — only the chat is. */
export interface ReferencedDocument {
  id: string
  filename: string
}

export interface AffectedChat {
  id: string
  title: string
  messageCount: number
  /** The OTHER documents this conversation also draws on. A chat is not necessarily ABOUT
   *  the document being deleted, and the confirmation has to say so — by name, so the user
   *  can go and read them, since those documents survive. */
  otherDocuments: ReferencedDocument[]
}

export interface DocumentDeletionImpact {
  documentId: string
  filename: string
  chats: AffectedChat[]
}

export interface ChatSession {
  id: string
  title: string
  lastMessagePreview: string
  updatedAt: string
  /**
   * The assistant's reply to the opening message, present only on the create response.
   *
   * It carries the action proposal — which, since V23, a history refetch CAN also return,
   * along with whatever was decided about it. Proposals used to be ephemeral and that was
   * the cause of two reported bugs: a decided card vanished on refresh, and nothing linked
   * a task or an audit row back to the prompt that produced it.
   */
  initialResponse?: Message
}

// ==========================================================================
// Chat & Tool Calling Types
// ==========================================================================

/**
 * Which generation backend answers a question.
 *
 * The choice is about WHERE THE DOCUMENT TEXT GOES: 'local' keeps the retrieved chunks on
 * the server's machine, 'gemini' sends them to Google. Retrieval, citations and every
 * guardrail are identical either way — only the step that turns a prompt into text differs.
 *
 * Omitting it uses the backend's configured default, which is 'local': the
 * privacy-preserving option is the one you get by not choosing.
 */
export type GenerationModel = 'local' | 'gemini'

export interface Citation {
  id: string;
  documentId: string;
  documentName: string;
  section?: string;
  /** Page number for paged formats. Complements `section`: PDFs have a page and no heading. */
  page?: number;
  /**
   * A word, never a percentage. It describes how closely the passage matched the QUESTION
   * (retrieval similarity), not how likely the answer is to be correct. The backend derives
   * it from measured score bands so the thresholds live in one place.
   */
  matchQuality?: string;
  excerpt: string;
}

// ==========================================================================
// Action vocabulary — RUNTIME CONSTANTS, so the types can actually be tested
// ==========================================================================
//
// These were three inline string unions repeated across ActionProposal, ActionRequest,
// ActionResult and ActionAudit below — the same literals written out four times in one
// file, hand-matched to Spring's enums and checked by nobody. TypeScript types erase at
// runtime, so no test could reach them.
//
// `as const` arrays survive compilation, which is what makes src/Type.conformance.test.ts
// possible: it compares these to src/test/action-contract.json, the snapshot the backend's
// ActionContractSnapshotTest holds Spring's own enums and records to. The derived
// `typeof X[number]` types then keep every union below spelled from one place.
//
// The pattern is not new here — DOCUMENT_STATUSES at the top of this file has always
// worked this way. It simply never reached the action types.

export const ACTION_TYPES = ['create-task', 'summarize-document', 'lookup-knowledge'] as const
export type ActionType = typeof ACTION_TYPES[number]

/** What a human may decide about a proposal. Spring's ActionDecision. */
export const ACTION_DECISIONS = ['approved', 'rejected'] as const
export type ActionDecision = typeof ACTION_DECISIONS[number]

/**
 * How an action turned out. Spring's ActionStatus — NOT the decision.
 *
 * `running` arrived with V22: a decision is acknowledged the moment it is recorded, and
 * slow work (summarise, lookup — both call a language model, measured at 78-135s) finishes
 * in the background. Without it the request held the connection open for two minutes and
 * people navigated away from a working system.
 */
export const ACTION_RESULT_STATUSES = ['completed', 'rejected', 'failed', 'running'] as const
export type ActionResultStatus = typeof ACTION_RESULT_STATUSES[number]

export const TASK_PRIORITIES = ['low', 'medium', 'high'] as const
export type TaskPriority = typeof TASK_PRIORITIES[number]

/** `in-progress` with a hyphen: Spring's TaskStatus.in_progress serialises via @JsonValue. */
export const TASK_STATUSES = ['todo', 'in-progress', 'done'] as const
export type TaskStatus = typeof TASK_STATUSES[number]

/**
 * The payload each action carries, keyed by discriminator.
 *
 * Spelled in SPRING's camelCase, which is what the browser actually exchanges.
 * `GET /tools` publishes Python's snake_case for the same tools and that is not a
 * contradiction: Python's schema describes what a MODEL may produce, this describes what a
 * BROWSER sends, and Spring's ActionProposer is the translation between them. The backend's
 * ToolRegistryConformanceTest asserts that bridge exists — it did not, for five days.
 */
export interface CreateTaskPayload { title: string; priority: TaskPriority }
export interface SummarizePayload { documentId: string; documentName: string }
export interface LookupPayload { query: string }

export interface ActionPayloads {
  'create-task': CreateTaskPayload
  'summarize-document': SummarizePayload
  'lookup-knowledge': LookupPayload
}

/**
 * The same key lists at RUNTIME. The compile-time assertions below tie these to the
 * interfaces above in both directions, so this map cannot describe a shape the interfaces
 * do not have, and the conformance test compares it to the backend snapshot. Between the
 * two, a field renamed on either side of the wire fails something.
 */
export const ACTION_PAYLOAD_KEYS = {
  'create-task': ['title', 'priority'],
  'summarize-document': ['documentId', 'documentName'],
  'lookup-knowledge': ['query'],
} as const satisfies { [K in ActionType]: readonly (keyof ActionPayloads[K])[] }

// Compile-time proof that no KEY IS MISSING from the map above. `satisfies` already stops
// it naming a key the interface lacks; this is the other direction, which `satisfies`
// cannot express on its own. `npm run build` runs tsc, so this is enforced on every build.
type _Exhaustive<K extends ActionType> =
  Exclude<keyof ActionPayloads[K], typeof ACTION_PAYLOAD_KEYS[K][number]> extends never
    ? true : ['payload key missing from ACTION_PAYLOAD_KEYS', K]
type _CheckCreateTask = _Exhaustive<'create-task'>
type _CheckSummarize = _Exhaustive<'summarize-document'>
type _CheckLookup = _Exhaustive<'lookup-knowledge'>
const _payloadKeysAreComplete: [_CheckCreateTask, _CheckSummarize, _CheckLookup] =
  [true, true, true]
void _payloadKeysAreComplete

// Discriminated Union for Action Proposals (Used by UI to render proposals)
/**
 * What a decided proposal carries when history replays it — V23.
 *
 * Proposals used to be ephemeral: sent once, never stored, so a refresh removed the card
 * and a decision a human made left no trace in the conversation where they made it.
 */
export interface ProposalDecision {
  /** What the human chose. */
  decision: ActionDecision
  /** What execution did. Null for rows decided before the outcome was stored. */
  status: ActionResultStatus | null
  result: { summary?: string; title?: string; snippets?: string[] } | null
  failureReason: string | null
}

export type ActionProposal = {
  [K in ActionType]: {
    id: string; type: K; label: string; payload: ActionPayloads[K]
    /** The message this proposal belongs to, for linking to the exact prompt. */
    messageId?: string | null
    /** Absent while undecided. Present once somebody has approved or rejected it. */
    decision?: ProposalDecision | null
  }
}[ActionType]

/**
 * A word corrected before retrieval ran. Mirrors `MessageDto.SpellingCorrectionDto`.
 *
 * Present only when the question AS TYPED retrieved nothing and the corrected one
 * retrieved something — so almost always absent. The UI must say so when it is there:
 * answering "ai saftey" as "ai safety" without mentioning it substitutes the user's
 * question for a different one.
 */
export interface SpellingCorrection {
  typed: string;
  used: string;
}

export interface Message {
  id: string;
  content: string;
  sender: Sender;
  timestamp: string;
  citations?: Citation[];
  actions?: ActionProposal[];
  /** Ephemeral, like `actions` — describes this turn's retrieval, not the message. */
  corrections?: SpellingCorrection[];
}

export interface Chat {
  id: string
  title?: string
  messages: Message[]
}

export interface SendMessageRequest {
  sessionId: string;
  content: string;
}

// Reconciled Task Shape
export interface Task {
  id: string;
  title: string;
  priority: TaskPriority;
  status: TaskStatus;
  createdAt: string;
  completedAt?: string;
  sourceSessionId: string; // NEW: The referential link back to the chat
  /** The prompt that proposed this task. Null for tasks created before V23. */
  sourceMessageId?: string | null;
}

// ==========================================================================
// DAY 13: Action & Audit Trail Contracts (Strictly Typed)
// ==========================================================================

// Request shape for POST /api/ai/actions
export type ActionRequest = {
  [K in ActionType]: {
    actionId: string
    sessionId: string
    decision: ActionDecision
    type: K
    payload: ActionPayloads[K]
  }
}[ActionType]

/**
 * What each action returns once approved. Keyed by discriminator so the `result` field
 * narrows on `type`.
 *
 * `summarize-document` returns `{ summary }` and NOT a bare string — Spring returned a bare
 * string until Day 14b while ActionCard.tsx has always rendered `result.summary`, so an
 * approved summary rendered as an empty card with no error anywhere. The backend was
 * corrected to match what was already published here rather than the other way round; see
 * SummarizeResult.java.
 */
export interface ActionResults {
  'create-task': Task
  'summarize-document': { summary: string }
  'lookup-knowledge': { snippets: string[] }
}

// Response shape for POST /api/ai/actions
export type ActionResult =
  | {
      actionId: string
      status: Exclude<ActionResultStatus, 'completed'>
      result: null
      /** Why it did not complete. Present on `failed`, absent on `rejected` — a rejection
       *  has no reason beyond the user's, and inventing one would be wrong. */
      failureReason?: string | null
      /** See the `completed` branch below. */
      replayedDecision?: ActionDecision | null
    }
  | {
      [K in ActionType]: {
        actionId: string; status: 'completed'; type: K
        /** NULL ON A REPLAYED DECISION, and this type used to deny it. ActionService
         *  returns `completed` with no result when the proposal was already decided: the
         *  original side effect is not re-run and its output was never stored, so there is
         *  nothing truthful to send. Declaring it non-null let `result.summary` compile and
         *  crash the page with "Cannot read properties of null (reading 'summary')" the
         *  second time a user pressed a button. */
        result: ActionResults[K] | null
        failureReason?: null
        /**
         * The decision that ACTUALLY STANDS, when this click did not make it. Null when
         * this click is the one that decided the proposal.
         *
         * A user approved a create-task proposal, then pressed Reject on the same card, and
         * the card answered "Task created: University admission policy." The server was
         * right — a proposal is decided once and rejecting afterwards must not delete a
         * task that exists — but the UI reported a creation as though Reject had caused it.
         */
        replayedDecision?: ActionDecision | null
      }
    }[ActionType]

// Audit Trail shape
export interface ActionAudit {
  id: string;
  actionId: string;
  sessionId: string;
  type: ActionType;
  decision: ActionDecision;
  timestamp: string;
  /** What execution did, as opposed to what was decided. Null for rows predating V21. */
  status: ActionResultStatus | null;
  /** The stored result, replayed verbatim. Null unless status is `completed`. */
  result: { summary?: string; title?: string; snippets?: string[] } | null;
  /** Operator-facing text. Null unless status is `failed`. */
  failureReason: string | null;
  /** The prompt that carried this proposal. Null for actions decided before V23. */
  messageId?: string | null;
}
/**
 * Contract revision #2 (backend Day 19). List endpoints previously returned a bare
 * array and now return this envelope: `/api/documents`, `/api/tasks`,
 * `/api/chat/sessions`, `/api/actions/audit`.
 *
 * Reserved on Day 6 and deferred because adopting it required a synchronised change
 * on both sides. It came due because every list endpoint returned its entire table —
 * 250 documents and 400 audit rows in one response at demo volume, growing without
 * bound.
 */
export interface PageResponse<T> {
  items: T[]
  /** Total matching rows across all pages, so a pager can be sized. */
  total: number
  /** Zero-based page index. */
  page: number
  /** Page size actually applied — the server clamps anything above 100. */
  size: number
}
