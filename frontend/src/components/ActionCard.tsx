import { useState } from 'react'
import { AlertCircle, Check, X, Loader2 } from 'lucide-react'
import type { ActionProposal, ActionResult, ActionRequest } from '../Type'
import { apiFetch } from '../api/client'

interface ActionCardProps {
  proposal: ActionProposal
  sessionId: string
}

function ActionCard({ proposal, sessionId }: ActionCardProps) { // 1. ADD THE DELIBERATE CRASH HERE (Render-phase)
 

  const [status, setStatus] = useState<'proposed' | 'executing' | 'completed' | 'rejected' | 'failed'>('proposed')
  const [lastDecision, setLastDecision] = useState<'approved' | 'rejected' | null>(null)
  
  // Storing the full ActionResult preserves the discriminant ('type') for safe narrowing
  const [actionResponse, setActionResponse] = useState<ActionResult | null>(null)
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
      if (data.status === 'completed') {
        setStatus('completed')
      } else if (data.status === 'rejected') {
        setStatus('rejected')
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

  // 3. Type-safe rendering of the result using the preserved discriminant
  const renderResult = () => {
    if (actionResponse?.status !== 'completed') return null
    
    // Narrowing natively unpacks the correct result shape without a single 'as' cast
    switch (actionResponse.type) {
      case 'create-task':
        return <span><Check size={14} /> Task created: {actionResponse.result.title}</span>
      case 'summarize-document':
        return <p className="action-result-text">{actionResponse.result.summary}</p>
      case 'lookup-knowledge':
        return <p className="action-result-text">{actionResponse.result.snippets[0]}</p>
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
      
      {status === 'executing' && (
        <div className="action-loading">
          <Loader2 className="animate-spin" size={16} /> Processing...
        </div>
      )}
      
      {status === 'completed' && (
        <div className="action-completed">{renderResult()}</div>
      )}
      
      {status === 'rejected' && (
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