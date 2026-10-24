import { useState } from 'react'
import { ShieldAlert, Users } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { usePagedFetch } from '../hooks/usePagedFetch'
import ErrorState from '../components/ErrorState'
import type { AdminUser } from '../Type'
import { apiFetch } from '../api/client'
import '../styles/settings.css'

/**
 * The UI for GET /api/admin/users.
 *
 * The endpoint has existed since the roles work and nothing could reach it — the
 * fifth instance this month of a backend capability with no path from the product.
 * The Day-21 audit is what surfaced it, by diffing served endpoints against called
 * ones rather than by anyone noticing.
 *
 * The route is guarded on the client for NAVIGATION only. The real enforcement is
 * server-side: /api/admin/** requires ROLE_ADMIN and answers 403 otherwise, so hiding
 * the link is a courtesy rather than a control. Both exist on purpose — a non-admin
 * should not see a door they cannot open, and should not get through it if they try.
 */
export default function AdminPage() {
  const { hasRole, user: currentUser } = useAuth()
  const { items: users, total, loading, error, refetch } = usePagedFetch<AdminUser>('/api/admin/users', 50)

  // Which row is mid-request, and what the server said if it refused. Keyed by user id so
  // two rows can never share a spinner or an error.
  const [busyId, setBusyId] = useState<string | null>(null)
  const [failure, setFailure] = useState<{ id: string; message: string } | null>(null)

  const setAdmin = async (user: AdminUser, makeAdmin: boolean) => {
    setBusyId(user.id)
    setFailure(null)
    try {
      const response = await apiFetch(`/api/admin/users/${user.id}/admin`, {
        method: makeAdmin ? 'PUT' : 'DELETE',
      })
      if (!response.ok) {
        // The server refuses two cases on purpose — removing your own access, and
        // removing the last administrator — and its wording explains which. Showing it
        // verbatim beats inventing a generic failure that hides the reason.
        const body = await response.json().catch(() => null)
        throw new Error(body?.message ?? 'The role could not be changed.')
      }
      await refetch()
    } catch (e) {
      setFailure({ id: user.id, message: e instanceof Error ? e.message : String(e) })
    } finally {
      setBusyId(null)
    }
  }

  if (!hasRole('ROLE_ADMIN')) {
    return (
      <div className="settings-page-wrapper">
        <div className="settings-header">
          <h1>Administration</h1>
        </div>
        <ErrorState
          title="Not available"
          message="This area requires an administrator role."
        />
      </div>
    )
  }

  return (
    <div className="settings-page-wrapper">
      <div className="settings-header">
        <h1>Administration</h1>
        <p>Accounts registered in this workspace.</p>
      </div>

      <div className="settings-grid">
        <div className="settings-card">
          <div className="settings-card-header">
            <Users size={18} className="settings-icon-user" />
            Users {total > 0 && <span className="settings-count">({total})</span>}
          </div>

          {loading ? (
            <div className="settings-card-body">Loading…</div>
          ) : error ? (
            <div className="settings-card-body">
              <ErrorState
                title="Could not load users"
                message={error}
                action={
                  <button type="button" className="btn-action-primary" onClick={refetch}>
                    Try again
                  </button>
                }
              />
            </div>
          ) : (
            <div className="settings-property-list">
              {users.map((u) => (
                <div className="settings-property-row" key={u.id}>
                  <div className="settings-property-label">
                    {u.name || 'Unnamed'}
                    {u.admin && <span className="admin-badge">admin</span>}
                  </div>
                  <div className="settings-property-value">
                    <span>{u.email}</span>
                    {/* YOUR OWN ROW IS DISABLED. The server refuses a self-revoke — the
                        endpoint that would put the role back is itself behind
                        hasRole('ADMIN') — so an enabled button here is a guaranteed error.
                        Saying why beats letting the user discover it by clicking. */}
                    <button
                      type="button"
                      className="btn-action-primary admin-role-button"
                      disabled={busyId === u.id || u.id === currentUser?.id}
                      title={u.id === currentUser?.id
                        ? 'You cannot change your own administrator access'
                        : undefined}
                      onClick={() => setAdmin(u, !u.admin)}
                    >
                      {busyId === u.id
                        ? 'Saving…'
                        : u.id === currentUser?.id ? 'You'
                        : u.admin ? 'Revoke admin' : 'Make admin'}
                    </button>
                  </div>
                  {failure?.id === u.id && (
                    <p className="admin-role-error">{failure.message}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="settings-card">
          <div className="settings-card-header">
            <ShieldAlert size={18} className="settings-icon-info" />
            Access
          </div>
          <div className="settings-card-body">
            <p className="settings-notice">
              This page is restricted to <code>ROLE_ADMIN</code>. The navigation link is
              hidden for other accounts, but the enforcement is on the server — the API
              returns 403 regardless of what the client shows.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
