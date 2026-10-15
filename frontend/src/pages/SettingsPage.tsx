import { useState } from 'react'
import { User, Monitor, Moon, Sun, LogOut } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/theme-context'
import { apiFetch } from '../api/client'
import type { ThemePreference } from '../context/theme-context'
import '../styles/settings.css'

const THEME_OPTIONS: {
  value: ThemePreference
  label: string
  description: string
  icon: typeof Sun
}[] = [
  { value: 'light', label: 'Light', description: 'Always light', icon: Sun },
  { value: 'dark', label: 'Dark', description: 'Always dark', icon: Moon },
  { value: 'system', label: 'System', description: 'Match my device', icon: Monitor },
]

export default function SettingsPage() {
  const { user, roles, logout } = useAuth()
  const { preference, resolved, setPreference } = useTheme()

  const [signingOutEverywhere, setSigningOutEverywhere] = useState(false)
  const [signOutError, setSignOutError] = useState<string | null>(null)

  /**
   * POST /api/auth/logout-all — revokes every refresh token this account holds.
   *
   * The endpoint existed with nothing able to reach it. It matters precisely when a
   * user suspects someone else has their session: ordinary logout drops only the
   * token in this browser, which is no help at all if the concern is another device.
   */
  const handleSignOutEverywhere = async () => {
    setSigningOutEverywhere(true)
    setSignOutError(null)
    try {
      const response = await apiFetch('/api/auth/logout-all', { method: 'POST' })
      if (!response.ok) throw new Error('Could not sign out your other sessions.')
      // This session is revoked too, so end it locally rather than leaving the user
      // holding an access token that will die at its next refresh.
      logout()
    } catch (err) {
      setSignOutError(err instanceof Error ? err.message : 'Could not sign out everywhere.')
      setSigningOutEverywhere(false)
    }
  }

  return (
    <div className="settings-page-wrapper">
      <div className="settings-header">
        <h1>Settings &amp; Profile</h1>
        <p>Account details and appearance.</p>
      </div>

      <div className="settings-grid">
        <div className="settings-card">
          <div className="settings-card-header">
            <User size={18} className="settings-icon-user" />
            User Profile
          </div>
          <div className="settings-property-list">
            <div className="settings-property-row">
              <div className="settings-property-label">Name</div>
              <div className="settings-property-value">{user?.name || 'Unknown User'}</div>
            </div>
            <div className="settings-property-row">
              <div className="settings-property-label">Email</div>
              <div className="settings-property-value">{user?.email || 'Not provided'}</div>
            </div>
            <div className="settings-property-row">
              <div className="settings-property-label">Roles</div>
              <div className="settings-property-value">
                {roles.length > 0
                  ? roles.map((role) => role.replace('ROLE_', '')).join(', ')
                  : '—'}
              </div>
              
            </div>
          </div>
        </div>

        <div className="settings-card">
          <div className="settings-card-header">
            {resolved === 'dark' ? <Moon size={18} className="settings-icon-user" />
                                 : <Sun size={18} className="settings-icon-user" />}
            Appearance
          </div>

          <div className="settings-card-body">
            {/*
              A radiogroup rather than three buttons: arrow keys move between the
              options and a screen reader announces "2 of 3, selected", which a row
              of buttons does not.
            */}
            <div
              className="theme-options"
              role="radiogroup"
              aria-label="Colour theme"
            >
              {THEME_OPTIONS.map(({ value, label, description, icon: Icon }) => (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={preference === value}
                  className={`theme-option ${preference === value ? 'selected' : ''}`}
                  onClick={() => setPreference(value)}
                >
                  <Icon size={20} className="theme-option-icon" />
                  <span className="theme-option-label">{label}</span>
                  <span className="theme-option-description">{description}</span>
                </button>
              ))}
            </div>

            <p className="settings-notice">
              {preference === 'system'
                ? `Following your device, which is currently ${resolved}.`
                : `Always ${preference}, whatever your device is set to.`}
            </p>
          </div>
        </div>
        <div className="settings-card">
          <div className="settings-card-header">
            <LogOut size={18} className="settings-icon-user" />
            Security
          </div>
          <div className="settings-card-body">
            <p className="settings-notice">
              Signs you out of this browser and every other device. Use it if you think
              someone else has access — signing out normally only ends this session.
            </p>

            {signOutError && (
              <p className="detail-open-error" role="alert">{signOutError}</p>
            )}

            <button
              type="button"
              className="btn-download-original"
              onClick={handleSignOutEverywhere}
              disabled={signingOutEverywhere}
            >
              <LogOut size={14} />
              <span>{signingOutEverywhere ? 'Signing out…' : 'Sign out everywhere'}</span>
            </button>
            
              
          </div>
        </div>
      </div>
    </div>
  )
}
