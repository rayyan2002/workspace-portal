import { ShieldAlert, Users } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { usePagedFetch } from '../hooks/usePagedFetch'
import ErrorState from '../components/ErrorState'
import type { User } from '../Type'
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
  const { hasRole } = useAuth()
  const { items: users, total, loading, error, refetch } = usePagedFetch<User>('/api/admin/users', 50)

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
                  <div className="settings-property-label">{u.name || 'Unnamed'}</div>
                  <div className="settings-property-value">{u.email}</div>
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
