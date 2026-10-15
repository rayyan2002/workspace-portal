import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { AlertCircle, LayoutGrid } from 'lucide-react'
import PasswordInput from '../components/PasswordInput'
import { apiFetch } from '../api/client'
import '../styles/login.css'

export default function ResetPasswordPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')

  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [touched, setTouched] = useState({ password: false, confirmPassword: false })
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const passwordError = !password
    ? 'Password is required'
    : password.length < 8
      ? 'Use at least 8 characters'
      : password.length > 72
        ? 'Use at most 72 characters'
        : undefined

  const confirmError = !confirmPassword
    ? 'Confirm your password'
    : confirmPassword !== password
      ? 'Passwords do not match'
      : undefined

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    setTouched({ password: true, confirmPassword: true })
    if (passwordError || confirmError || !token) return

    setLoading(true)
    setError(null)
    try {
      const response = await apiFetch('/api/auth/reset-password', {
        method: 'POST',
        body: JSON.stringify({ token, newPassword: password }),
      })

      if (!response.ok) {
        const body = await response.json().catch(() => ({}))
        throw new Error(body.message || 'This reset link is invalid or has expired.')
      }

      navigate('/login', {
        replace: true,
        state: { notice: 'Password updated. Sign in with your new password.' },
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not reset your password.')
    } finally {
      setLoading(false)
    }
  }

  // Reaching this page without a token means a mangled or hand-typed link. Say so
  // rather than presenting a form that cannot possibly succeed.
  if (!token) {
    return (
      <div className="login-viewport">
        <div className="login-card">
          <header className="login-header">
            <AlertCircle className="login-brand-icon" size={32} />
            <h1 className="login-title">Reset link not valid</h1>
            <p className="login-subtitle">
              This link is missing its reset token. Request a new one and use the most
              recent email.
            </p>
          </header>

          <p className="login-alt-action">
            <Link to="/forgot-password">Request a new link</Link>
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="login-viewport">
      <div className="login-card">
        <header className="login-header">
          <LayoutGrid className="login-brand-icon" size={32} />
          <h1 className="login-title">Choose a new password</h1>
          <p className="login-subtitle">You'll be signed out everywhere else</p>
        </header>

        {error && (
          <div className="login-error-banner" role="alert">
            <AlertCircle className="login-error-icon" size={16} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="login-form">
          <PasswordInput
            label="New password"
            id="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onBlur={() => setTouched((t) => ({ ...t, password: true }))}
            error={touched.password ? passwordError : undefined}
            disabled={loading}
            autoComplete="new-password"
          />

          <PasswordInput
            label="Confirm new password"
            id="confirmPassword"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            onBlur={() => setTouched((t) => ({ ...t, confirmPassword: true }))}
            error={touched.confirmPassword ? confirmError : undefined}
            disabled={loading}
            autoComplete="new-password"
          />

          <button type="submit" className="btn-login-submit" disabled={loading}>
            {loading ? 'Updating...' : 'Update password'}
          </button>
        </form>

        <p className="login-alt-action">
          <Link to="/login">Back to sign in</Link>
        </p>
      </div>
    </div>
  )
}
