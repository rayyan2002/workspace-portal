import { useState } from 'react'
import { Link } from 'react-router'
import { AlertCircle, Check, X, Loader2 } from 'lucide-react'
import type { ActionProposal, ActionResult, ActionRequest } from '../Type'
import { apiFetch } from '../api/client'
import { recallDecision, rememberDecision } from '../utils/decidedActions'

interface ActionCardProps {
  proposal: ActionProposal
  sessionId: string
}

// A proposal already decided in this session must not be offered again. Leaving the chat
// unmounts this component, and a plain useState('proposed') meant coming back re-opened a
// question that had already been answered. See src/utils/decidedActions.ts.
function statusOf(result: ActionResult) {
  switch (result.status) {
    case 'completed': return 'completed' as const
    case 'rejected': return 'rejected' as const
    case 'running': return 'running' as const
    default: return 'failed' as const
  }
}

// What history replayed about this proposal, as the shape the render path already reads.
// THIS IS WHAT MAKES A DECIDED CARD PERMANENT. The in-memory map below only survives
// navigation inside the app; this survives a refresh, a new device, and next week, because
// it comes from action_proposals joined to action_audit.
function fromServer(proposal: ActionProposal): ActionResult | null {
  const decided = proposal.decision
  if (!decided) return null
  return {
    actionId: proposal.id,
    // A decision with no recorded status predates V21: it was decided, but what execution
    // did was never stored. `completed` for an approval is the same inference the server
    // makes for those rows, and the card falls through to "already done".
    status: decided.status ?? (decided.decision === 'approved' ? 'completed' : 'rejected'),
    type: proposal.type,
    result: decided.result,
    failureReason: decided.failureReason,
  } as ActionResult
}

function ActionCard({ proposal, sessionId }: ActionCardProps) {
  // Server first, then this session's memory. A refresh clears the map but not the row.
  const replayed = fromServer(proposal)
  const remembered = replayed
    ? { result: replayed, decision: proposal.decision!.decision }
    : recallDecision(proposal.id)
  const [status, setStatus] = useState<'proposed' | 'executing' | 'completed' | 'rejected' | 'failed' | 'running'>(
    () => (remembered ? statusOf(remembered.result) : 'proposed'))
  const [lastDecision, setLastDecision] = useState<'approved' | 'rejected' | null>(
    () => remembered?.decision ?? null)

  // Storing the full ActionResult preserves the discriminant ('type') for safe narrowing
  const [actionResponse, setActionResponse] = useState<ActionResult | null>(
    () => remembered?.result ?? null)
  const [error, setError] = useState<string | null>(null)

  const submitDecision = async (decision: 'approved' | 'rejected') => {
    setStatus('executing')
    setError(null)
    setLastDecision(decision)

    // 1. Construct the request strictly within the narrowing scope
    let requestBody: ActionRequest

    switch (proposal.type) {
      case 'create-task':
        requestBody = { actionId: proposal.id, sessionId, decision, type: 'create-task', payload: proposal.payload }
        break
      case 'summarize-document':
        requestBody = { actionId: proposal.id, sessionId, decision, type: 'summarize-document', payload: proposal.payload }
        break
      case 'lookup-knowledge':
        requestBody = { actionId: proposal.id, sessionId, decision, type: 'lookup-knowledge', payload: proposal.payload }
        break
    }

    try {
      const response = await apiFetch('/api/ai/actions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody)
      })

      if (!response.ok) throw new Error('Action execution failed')
      
      const data: ActionResult = await response.json()

      // THE REPORTED BUG. This was `else { setStatus('rejected') }`, which collapsed
      // `failed` into `rejected` — so approving an action that then failed told the user
      // they had rejected it, while the audit trail recorded `approved`. The two halves of
      // the product disagreed about what the user had just done.
      setActionResponse(data)
      // Survives this component being unmounted by navigation; see decidedActions.ts.
      rememberDecision(proposal.id, data, decision)
      if (data.status === 'completed') {
        setStatus('completed')
      } else if (data.status === 'rejected') {
        setStatus('rejected')
      } else if (data.status === 'running') {
        // V22: the DECISION is recorded and acknowledged; the work is still going. This is
        // not a pending spinner — there is nothing left for this card to wait for.
        setStatus('running')
      } else {
        setStatus('failed')
      }
    } catch (e) {
      setError('Could not process action.')
      setStatus('failed')
    }
  }

  // 2. Type-safe rendering of the proposal text
  const renderProposal = () => {
    switch (proposal.type) {
      case 'create-task':
        return `Create task: ${proposal.payload.title} (${proposal.payload.priority} priority)`
      case 'summarize-document':
        return `Summarize: ${proposal.payload.documentName}`
      case 'lookup-knowledge':
        return `Search knowledge: ${proposal.payload.query}`
    }
  }

  // A DECISION REPLAYED HAS NO RESULT TO SHOW for proposals decided before V21: the side
  // effect was not re-run and its output was never stored. "Already done" is the whole
  // truth available; inventing a summary by re-running would defeat idempotency.
  const alreadyDone = (
    <span className="action-muted"><Check size={14} /> Already done — this was decided earlier.</span>
  )

  // YOUR CLICK WAS NOT THE ONE THAT DECIDED THIS, and saying so is the entire point.
  // Reported: a user approved a create-task proposal, pressed Reject on the same card, and
  // the card answered "Task created: University admission policy." The server was right —
  // a proposal is decided once, and rejecting afterwards must not delete a task that
  // already exists — but reporting a creation as though Reject had caused it meant the
  // click vanished with no explanation.
  const stood = actionResponse?.replayedDecision ?? null
  const clickIgnored = stood !== null && lastDecision !== null && stood !== lastDecision

  // 3. Type-safe rendering of the result using the preserved discriminant.
  //    The null check lives INSIDE each branch so the discriminant keeps narrowing
  //    `result` to that branch's shape; checking it before the switch would widen it
  //    back to the union of all three and nothing would typecheck.
  const renderResult = () => {
    if (actionResponse?.status !== 'completed') return null

    // Narrowing natively unpacks the correct result shape without a single 'as' cast
    switch (actionResponse.type) {
      case 'create-task':
        return actionResponse.result
          ? <span><Check size={14} /> Task created: {actionResponse.result.title}</span>
          : alreadyDone
      case 'summarize-document':
        return actionResponse.result
          ? <p className="action-result-text">{actionResponse.result.summary}</p>
          : alreadyDone
      case 'lookup-knowledge':
        return actionResponse.result
          ? <p className="action-result-text">{actionResponse.result.snippets[0]}</p>
          : alreadyDone
    }
  }

  return (
    <div className={`action-card status-${status}`}>
      {status === 'proposed' && (
        <div className="action-proposal-content">
          <p className="action-label">{renderProposal()}</p>
          <div className="action-buttons">
            <button onClick={() => submitDecision('approved')} className="btn-action-approve">Approve</button>
            <button onClick={() => submitDecision('rejected')} className="btn-action-reject">Reject</button>
          </div>
        </div>
      )}
      
      {/* BRIEF SINCE V22. This used to carry an elapsed-seconds counter because the request
          itself blocked for 78-135 seconds while the model ran. The request now returns as
          soon as the decision is recorded, so this is one round trip — a counter here would
          be measuring nothing, and the explanation moved to the `running` state below. */}
      {status === 'executing' && (
        <div className="action-loading">
          <Loader2 className="animate-spin" size={16} /> Recording your decision…
        </div>
      )}
      
      {clickIgnored && (
        <p className="action-muted">
          <AlertCircle size={14} /> Already {stood} earlier — your{' '}
          {lastDecision === 'rejected' ? 'rejection' : 'approval'} was not applied. A
          proposal is decided once.
        </p>
      )}

      {status === 'completed' && !clickIgnored && (
        <div className="action-completed">{renderResult()}</div>
      )}
      
      {status === 'running' && (
        <div className="action-accepted">
          <Check size={14} /> Approved — working on it in the background.
          <p className="action-hint">
            It will appear in <Link to="/actions">Actions</Link> when it is done. This
            usually takes a minute or two; you do not need to wait here.
          </p>
        </div>
      )}

      {status === 'rejected' && !clickIgnored && (
        <p className="action-muted"><X size={14} /> Action rejected.</p>
      )}
      
      {status === 'failed' && (
        <div className="action-error">
          {/* The server's reason when it has one — "nothing in it was relevant enough to
              summarise" is actionable where a bare "failed" is not. `error` covers the
              case where the request never reached the server at all. */}
          <AlertCircle size={14} />{' '}
          {actionResponse?.failureReason ?? error ?? 'This action could not be completed.'}
          <button onClick={() => lastDecision && submitDecision(lastDecision)}>Retry</button>
        </div>
      )}
    </div>
  )
}

export default ActionCard