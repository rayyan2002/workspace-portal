import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router'
import { MessageSquare, RefreshCw, Trash2, X } from 'lucide-react'
import ErrorState from './ErrorState'
import EmptyState from './EmptyState'
import { formatDate } from '../utils/format'
import type { ChatSession, PageResponse } from '../Type'
import { apiFetch } from '../api/client'

interface SessionListProps {
  activeSessionId: string | null
  refreshKey: number
}

function SessionList({ activeSessionId, refreshKey }: SessionListProps) {
  const navigate = useNavigate()

  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [confirmingId, setConfirmingId] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const [retryTrigger, setRetryTrigger] = useState(0)

  useEffect(() => {
    async function fetchSessions() {
      setLoading(true) 
      setError(null) 

      try {
        // The sidebar takes a generous first page rather than a numbered pager: a
        // pager in a scrolling sidebar is the wrong control, and the envelope's
        // `total` is not surfaced here because the list is already scrollable.
        // Contract revision #2 — this endpoint returns { items, total, page, size }.
        const response = await apiFetch('/api/chat/sessions?page=0&size=100')
        if (!response.ok) {
          throw new Error('Failed to retrieve conversation lists.')
        }
        const body = (await response.json()) as PageResponse<ChatSession>
        setSessions(body.items)
      } catch {
        setError('Failed to sync conversation threads.')
      } finally {
        setLoading(false)
      }
    }
    fetchSessions()
  }, [refreshKey, retryTrigger]) 

  const handleDelete = async (session: ChatSession) => {
    const originalIndex = sessions.findIndex((s) => s.id === session.id)
    if (originalIndex === -1) return

    setConfirmingId(null)
    setDeleteError(null)

    // Optimistic removal, matching the Documents page idiom.
    setSessions((prev) => prev.filter((s) => s.id !== session.id))

    // Deleting the conversation you are currently reading would leave the route
    // pointing at a session that no longer exists, so step off it first.
    if (activeSessionId === session.id) {
      navigate('/chat', { replace: true })
    }

    try {
      const response = await apiFetch(`/api/chat/sessions/${session.id}`, { method: 'DELETE' })
      if (!response.ok) throw new Error('Server rejected the deletion.')
    } catch {
      setSessions((prev) => {
        const copy = [...prev]
        copy.splice(originalIndex, 0, session)
        return copy
      })

      setDeleteError(`Failed to delete "${session.title}". The conversation has been restored.`)
      setTimeout(() => setDeleteError(null), 4000)
    }
  }

  if (loading && sessions.length === 0) {
    return (
      <div style={{ padding: 'var(--space-md)' }}>
        {[1, 2, 3].map(i => (
          <div key={i} className="skeleton-bubble long-shimmer" style={{ height: '56px', marginBottom: '8px', borderRadius: 'var(--radius-sm)' }} />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ padding: 'var(--space-md)' }}>
         <ErrorState 
          title="Load failed"
          message={error}
          action={
            <button type="button" className="btn-action-primary" onClick={() => setRetryTrigger(c => c + 1)}>
              <RefreshCw size={14} />
              <span>Retry</span>
            </button>
          }
        />
      </div>
    )
  }

  return (
    <div className="sessions-list-scrollable">
      {deleteError && (
        <p className="session-delete-error" role="alert">{deleteError}</p>
      )}

      {/* Transient UI for when 'New Chat' is active */}
      {activeSessionId === 'new' && (
        <div className="session-item-row active">
          <div className="session-item-meta">
            <span className="session-item-title">New Conversation</span>
          </div>
        </div>
      )}

      {!loading && !error && sessions.length === 0 && activeSessionId !== 'new' && (
        <div style={{ padding: 'var(--space-md)' }}>
          <EmptyState 
            icon={<MessageSquare size={24} />}
            title="No history"
            message="Start a new chat to begin."
          />
        </div>
      )}

      {/* The row is a wrapper rather than the Link itself: a <button> nested inside an
          <a> is invalid HTML, and the click would navigate instead of deleting. */}
      {sessions.map((session) => (
        <div
          key={session.id}
          className={`session-item-wrapper ${session.id === activeSessionId ? 'active' : ''}`}
        >
          <Link
            to={`/chat/${session.id}`}
            className="session-item-row"
            style={{ textDecoration: 'none' }}
          >
            <div className="session-item-meta">
              <span className="session-item-title">{session.title}</span>
              <span className="session-item-date">{formatDate(session.updatedAt)}</span>
            </div>
            <p className="session-item-preview">{session.lastMessagePreview}</p>
          </Link>

          <div className="session-item-actions">
            {confirmingId === session.id ? (
              <div className="confirm-delete-group">
                <button
                  type="button"
                  className="btn-confirm-delete"
                  onClick={() => handleDelete(session)}
                >
                  Delete
                </button>
                <button
                  type="button"
                  className="btn-cancel-delete"
                  onClick={() => setConfirmingId(null)}
                  aria-label={`Cancel deleting ${session.title}`}
                >
                  <X size={14} />
                </button>
              </div>
            ) : (
              <button
                type="button"
                className="btn-icon-delete"
                onClick={() => setConfirmingId(session.id)}
                aria-label={`Delete conversation ${session.title}`}
              >
                <Trash2 size={15} />
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

export default SessionList
