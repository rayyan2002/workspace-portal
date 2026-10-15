import { useState } from 'react'
import { Link } from 'react-router'
import { AlertCircle, LayoutGrid, MailCheck } from 'lucide-react'
import TextInput from '../components/TextInput'
import { apiFetch } from '../api/client'
import '../styles/login.css'

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [touched, setTouched] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const fieldError = !email.trim()
    ? 'Email is required'
    : !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
      ? 'Enter a valid email address'
      : undefined

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    setTouched(true)
    if (fieldError) return

    setLoading(true)
    setError(null)
    try {
      const response = await apiFetch('/api/auth/forgot-password', {
        method: 'POST',
        body: JSON.stringify({ email: email.trim() }),
      })

      if (!response.ok) {
        throw new Error('Could not send the reset email. Please try again.')
      }

      setSent(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not send the reset email.')
    } finally {
      setLoading(false)
    }
  }

  if (sent) {
    return (
      <div className="login-viewport">
        <div className="login-card">
          <header className="login-header">
            <MailCheck className="login-brand-icon" size={32} />
            <h1 className="login-title">Check your email</h1>
            {/*
              Worded so it is true whether or not the address has an account. Saying
              "we sent it" only when the user exists would turn this screen into a way
              of discovering who is registered.
            */}
            <p className="login-subtitle">
              If an account exists for <strong>{email.trim()}</strong>, a reset link is on its way.
              It expires in 30 minutes.
            </p>
          </header>

          <p className="login-alt-action">
            <Link to="/login">Back to sign in</Link>
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
          <h1 className="login-title">Reset your password</h1>
          <p className="login-subtitle">We'll email you a link to choose a new one</p>
        </header>

        {error && (
          <div className="login-error-banner" role="alert">
            <AlertCircle className="login-error-icon" size={16} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="login-form">
          <TextInput
            label="Email address"
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onBlur={() => setTouched(true)}
            error={touched ? fieldError : undefined}
            disabled={loading}
            autoComplete="email"
          />

          <button type="submit" className="btn-login-submit" disabled={loading}>
            {loading ? 'Sending...' : 'Send reset link'}
          </button>
        </form>

        <p className="login-alt-action">
          Remembered it? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  )
}
