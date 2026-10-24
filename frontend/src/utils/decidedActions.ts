import type { ActionDecision, ActionResult } from '../Type'

/**
 * Which proposals have already been decided in this browser session.
 *
 * THE BUG THIS FIXES. Approve or reject a proposal, navigate to another chat, come back,
 * and the card was offering Approve/Reject again as though nothing had happened. Clicking
 * it a second time hit the server's idempotency branch, so nothing was executed twice — but
 * the card was inviting a decision that had already been made, and the user had no way to
 * know which of the two clicks counted.
 *
 * The cause is that `ActionCard` holds its state in `useState`, and leaving the chat
 * unmounts it. Remounting reset it to 'proposed'.
 *
 * WHY A MODULE-LEVEL MAP AND NOT localStorage, which is what the model preference uses.
 * Action proposals are EPHEMERAL on the server — `ChatSessionService` does not replay them
 * into history, so a real page refresh makes the card disappear entirely. A decision that
 * outlived the proposal would be a record of something no longer on screen, and the map
 * would grow forever with keys nothing can ever read. In-memory matches the proposal's own
 * lifetime exactly: both survive navigation inside the app, both die on refresh.
 *
 * NOT A SOURCE OF TRUTH. The audit trail is. This only stops the UI from asking a question
 * it already has the answer to; every guarantee about deciding once lives in Postgres,
 * where `uq_action_audit_action_id` enforces it.
 */
const decided = new Map<string, { result: ActionResult; decision: ActionDecision }>()

export function rememberDecision(
  actionId: string,
  result: ActionResult,
  decision: ActionDecision,
): void {
  decided.set(actionId, { result, decision })
}

export function recallDecision(
  actionId: string,
): { result: ActionResult; decision: ActionDecision } | undefined {
  return decided.get(actionId)
}

/** Test-only: the map is module state and would otherwise leak between test cases. */
export function forgetAllDecisions(): void {
  decided.clear()
}
