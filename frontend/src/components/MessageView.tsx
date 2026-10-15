import { useState, useEffect, useRef } from 'react'
import { Link, useNavigate } from 'react-router'
import { Send, AlertCircle, RefreshCw } from 'lucide-react'
import type { Message, APIError, ActionProposal, GenerationModel } from '../Type'
import MessageCitations from './MessageCitations'
import MessageActions from './MessageActions'
import ErrorState from './ErrorState'
import '../styles/chat.css'
import { apiFetch } from '../api/client'
import { readStoredModel, storeModel } from '../utils/modelPreference'

type UIMessage = Message & { 
  status?: 'sending' | 'failed'
  errorMessage?: string 
}

interface MessageViewProps {
  sessionId: string
  sessionTitle: string
  onSessionCreated?: (newSessionId: string) => void
}

/**
 * Action proposals, kept at module scope and keyed by message id.
 *
 * They are deliberately never persisted — the assistant proposes, the human decides,
 * and only an approval writes anything — so refetching history returns the message
 * WITHOUT them, and anything that refetches erases the proposal card.
 *
 * This lives outside the component on purpose. Navigating from /chat/new to
 * /chat/{id} remounts MessageView, which resets a useRef and loses the proposal
 * recorded microseconds earlier — that remount is exactly why the first message of a
 * conversation never showed its card while every later one did.
 */
const ephemeralActions = new Map<string, ActionProposal[]>()

function rememberActions(message: Message): Message {
  if (message.actions && message.actions.length > 0) {
    ephemeralActions.set(message.id, message.actions)
  }
  return message
}

function withEphemeralActions(message: Message): Message {
  const actions = ephemeralActions.get(message.id)
  return actions ? { ...message, actions } : message
}

function MessageView({ sessionId, sessionTitle, onSessionCreated }: MessageViewProps) {
  const navigate = useNavigate()
  
  const [messages, setMessages] = useState<UIMessage[]>([])
  const [input, setInput] = useState('')
  // REMEMBERED, not per question. This was `useState('local')`, described as "per question,
  // not a saved preference" — but the effect was that any remount reverted a user who had
  // deliberately chosen Cloud back to on-device, mid-conversation, silently. The trace log
  // caught it: `gemini (0 history) -> local (2 history)` with no selector change. A decision
  // that has to outlive a component does not belong in component state.
  //
  // Still defaults to `local` for anyone who has never chosen. See utils/modelPreference.
  const [model, setModel] = useState<GenerationModel>(readStoredModel)

  const chooseModel = (next: GenerationModel) => {
    setModel(next)
    storeModel(next)
  }
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  
  const [isAwaitingResponse, setIsAwaitingResponse] = useState(false)
  const [retryTrigger, setRetryTrigger] = useState(0)

  const logEndAnchorRef = useRef<HTMLDivElement>(null)
  const scrollBehavior = useRef<ScrollBehavior>('auto')
  const prevSessionId = useRef<string>(sessionId)


  useEffect(() => {
    if (!sessionId || sessionId === 'new') {
      setMessages([])
      setLoading(false)
      setError(null)
      prevSessionId.current = sessionId 
      return
    }

    async function fetchMessages() {
      const isTransitionFromNew = prevSessionId.current === 'new'

      if (!isTransitionFromNew) {
        setLoading(true)
        setMessages([])
      }

      setError(null)

      try {
        const response = await apiFetch(`/api/chat/${sessionId}/messages`)
        
        if (!response.ok) {
          if (response.status === 404) {
            const errData = (await response.json()) as APIError
            throw new Error(errData.message || 'Thread history not found.')
          }
          throw new Error('Failed to retrieve thread history.')
        }

        const data = (await response.json()) as Message[]

        scrollBehavior.current = 'auto'
        setMessages(data.map(withEphemeralActions))
      } catch (err) {
        const message = err instanceof Error ? err.message : 'An error occurred.'
        setError(message)
      } finally {
        setLoading(false)
        prevSessionId.current = sessionId
      }
    }

    fetchMessages()
  }, [sessionId, retryTrigger]) 

  useEffect(() => {
    if (!loading && !error && messages.length > 0) {
      logEndAnchorRef.current?.scrollIntoView({ behavior: scrollBehavior.current })
    }
  }, [messages, loading, error])

  const processMessage = async (content: string, existingId?: string) => {
    const targetId = existingId || `temp-${Date.now()}`

    if (!existingId) {
      const optimisticMessage: UIMessage = {
        id: targetId,
        content,
        sender: 'user',
        timestamp: new Date().toISOString(),
        status: 'sending'
      }
      scrollBehavior.current = 'smooth'
      setMessages(prev => [...prev, optimisticMessage])
    } else {
      setMessages(prev => prev.map(m => 
        m.id === targetId ? { ...m, status: 'sending', errorMessage: undefined } : m
      ))
    }

    setIsAwaitingResponse(true)

    try {
      if (sessionId === 'new') {
        const response = await apiFetch('/api/chat/sessions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ initialMessage: content, model })
        })

        if (!response.ok) throw new Error('Failed to create new conversation.')

        const data = await response.json()

        // The assistant's reply travels with the create response, carrying its
        // citations AND any action proposal. Appending it here is what makes the
        // FIRST message of a conversation able to propose a task: proposals are
        // ephemeral, so refetching history would return the message without them.
        if (data.initialResponse) {
          // Recorded EAGERLY, not inside the updater below: React defers updater
          // functions, and the effect's refetch can resolve first — at which point
          // the ref would still be empty and the proposal lost.
          const initial = rememberActions(data.initialResponse as Message)

          setMessages(prev => [
            ...prev.map(m => m.id === targetId ? { ...m, status: undefined } : m),
            initial,
          ])
        }

        if (onSessionCreated) {
          onSessionCreated(data.id) // <-- FIXED
        }
        
        // Atomically replace the URL to swap out 'new' for the real ID without stacking browser history
        navigate(`/chat/${data.id}`, { replace: true }) // <-- FIXED
        return; 
      }

      const response = await apiFetch('/api/chat/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sessionId, content, model })
      })

      if (!response.ok) {
        const errData = await response.json().catch(() => ({})) as APIError
        throw new Error(errData.message || 'The server rejected the message.')
      }
      const aiMessage: Message = await response.json()

      setMessages(prev => {
        const updatedPrev = prev.map(m => 
          m.id === targetId ? { ...m, status: undefined, errorMessage: undefined } : m
        )
        return [...updatedPrev, rememberActions(aiMessage)]
      })
    } catch (err) {
      const actualError = err instanceof Error ? err.message : 'A network error occurred.'
      setMessages(prev => 
        prev.map(m => m.id === targetId ? { ...m, status: 'failed', errorMessage: actualError } : m)
      )
    } finally {
      setIsAwaitingResponse(false)
      scrollBehavior.current = 'smooth'
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const trimmedInput = input.trim()
    if (!trimmedInput || isAwaitingResponse) return

    setInput('')
    await processMessage(trimmedInput)
  }

  const handleRetry = (msg: UIMessage) => {
    if (isAwaitingResponse) return
    processMessage(msg.content, msg.id)
  }

  if (loading) {
    return (
      <div className="message-pane-wrapper">
        <div className="chat-pane-header">
          <Link to="/chat" className="btn-chat-back" aria-label="Back to sessions">
            <svg aria-hidden="true" className="lucide lucide-chevron-left" fill="none" height="20" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="20" xmlns="http://www.w3.org/2000/svg"><path d="m15 18-6-6 6-6"/></svg>
          </Link>
          <h1 className="chat-pane-title">{sessionTitle}</h1>
        </div>
        <div className="message-log-scrollable">
          <div className="skeleton-bubble-wrapper assistant-align">
            <div className="skeleton-bubble long-shimmer" />
          </div>
          <div className="skeleton-bubble-wrapper user-align">
            <div className="skeleton-bubble short-shimmer" />
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="message-pane-wrapper">
        <div className="chat-pane-header">
          <Link to="/chat" className="btn-chat-back" aria-label="Back to sessions">
            <svg aria-hidden="true" className="lucide lucide-chevron-left" fill="none" height="20" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="20" xmlns="http://www.w3.org/2000/svg"><path d="m15 18-6-6 6-6"/></svg>
          </Link>
          <h1 className="chat-pane-title">{sessionTitle}</h1>
        </div>
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <ErrorState 
            title="Failed to load conversation"
            message={error}
            action={
              <button type="button" className="btn-action-primary" onClick={() => setRetryTrigger(c => c + 1)}>
                <RefreshCw size={14} />
                <span>Try Again</span>
              </button>
            }
          />
        </div>
      </div>
    )
  }

  const isSubmitDisabled = isAwaitingResponse || !input.trim()

  return (
    <div className="message-pane-wrapper">
      <div className="chat-pane-header">
        <Link to="/chat" className="btn-chat-back" aria-label="Back to sessions">
          <svg aria-hidden="true" className="lucide lucide-chevron-left" fill="none" height="20" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="20" xmlns="http://www.w3.org/2000/svg"><path d="m15 18-6-6 6-6"/></svg>
        </Link>
        <h1 className="chat-pane-title">{sessionTitle}</h1>
      </div>

      <div className="message-log-scrollable">
        <div className="message-spacer" /> 
        
        {messages.map((msg: UIMessage) => {
          const isUser = msg.sender === 'user'
          
          let bubbleStateClass = ''
          if (msg.status === 'sending') bubbleStateClass = 'is-sending'
          if (msg.status === 'failed') bubbleStateClass = 'is-failed'

          return (
            <div
              key={msg.id}
              className={`message-bubble-wrapper ${isUser ? 'user-align' : 'assistant-align'}`}
            >
              <div className="message-content-group">
                <div className={`message-bubble ${isUser ? 'user-style' : 'assistant-style'} ${bubbleStateClass}`}>
                  <p className="message-text">{msg.content}</p>
                </div>

                {/*
                  ABOVE the sources, because it changes how the whole answer should be read.
                  The user typed one thing and the search ran on another; answering "ai
                  saftey" as "ai safety" without saying so substitutes their question. Shown
                  only when a correction actually fired, which is almost never.
                */}
                {!isUser && msg.corrections && msg.corrections.length > 0 && (
                  <p className="message-correction">
                    Showing results for{' '}
                    <strong>
                      {msg.corrections.map((c) => c.used).join(', ')}
                    </strong>
                    {' — you typed '}
                    <span className="message-correction-typed">
                      {msg.corrections.map((c) => c.typed).join(', ')}
                    </span>
                  </p>
                )}

                {!isUser && msg.citations && msg.citations.length > 0 && (
                  <MessageCitations citations={msg.citations} />
                )}

                {!isUser && msg.actions && msg.actions.length > 0 && (
                  <MessageActions actions={msg.actions} sessionId={sessionId} />
                )}

                {msg.status === 'failed' && (
                  <div className="message-error-container">
                    <AlertCircle size={14} />
                    <span>{msg.errorMessage}</span>
                    <button type="button" className="btn-retry-message" onClick={() => handleRetry(msg)}>
                      Retry
                    </button>
                  </div>
                )}
              </div>
            </div>
          )
        })}
        
        {isAwaitingResponse && (
          <div className="message-bubble-wrapper assistant-align">
            <div className="message-bubble assistant-style">
              <p className="message-text thinking-text">
                Assistant is thinking...
              </p>
            </div>
          </div>
        )}

        <div ref={logEndAnchorRef} />
      </div>

      <div className="message-input-footer">
        <form onSubmit={handleSubmit} className="message-input-form">
          {/*
            Named by WHERE THE DATA GOES, not by brand. "Gemini" alone tells a user nothing
            about the trade they are making; "Cloud" next to "On-device" does. The title
            attribute spells it out, and local is the default so the private option is what
            you get by not choosing.
          */}
          <select
            className="model-select"
            aria-label="Which model answers"
            title={model === 'local'
              ? 'On-device: your document text stays on the server. Slower, less accurate.'
              : 'Cloud (Gemini): your document text is sent to Google. Faster on hard questions, more accurate.'}
            value={model}
            onChange={(e) => chooseModel(e.target.value as GenerationModel)}
            disabled={isAwaitingResponse}
          >
            <option value="local">On-device</option>
            <option value="gemini">Cloud</option>
          </select>
          <input
            type="text"
            className="message-input-field"
            placeholder="Type a message..."
            aria-label="Message AI"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={isAwaitingResponse}
          />
          <button 
            type="submit" 
            className="btn-message-submit"
            disabled={isSubmitDisabled}
          >
            <Send size={14} />
            <span>Send</span>
          </button>
        </form>
      </div>
    </div>
  )
}

export default MessageView