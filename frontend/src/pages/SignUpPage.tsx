import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { AlertCircle, LayoutGrid } from 'lucide-react'
import TextInput from '../components/TextInput'
import PasswordInput from '../components/PasswordInput'
import { apiFetch } from '../api/client'
import '../styles/login.css'

interface Fields {
  name: string
  email: string
  password: string
  confirmPassword: string
}

const EMPTY: Fields = { name: '', email: '', password: '', confirmPassword: '' }

/** Mirrors the backend's RegisterRequest constraints so the user is told before submitting. */
function validate(values: Fields): Partial<Record<keyof Fields, string>> {
  const errors: Partial<Record<keyof Fields, string>> = {}

  if (!values.name.trim()) errors.name = 'Name is required'

  if (!values.email.trim()) errors.email = 'Email is required'
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email)) errors.email = 'Enter a valid email address'

  if (!values.password) errors.password = 'Password is required'
  else if (values.password.length < 8) errors.password = 'Use at least 8 characters'
  // bcrypt ignores anything past 72 bytes, so a longer password is misleading, not stronger.
  else if (values.password.length > 72) errors.password = 'Use at most 72 characters'

  if (!values.confirmPassword) errors.confirmPassword = 'Confirm your password'
  else if (values.confirmPassword !== values.password) errors.confirmPassword = 'Passwords do not match'

  return errors
}

export default function SignUpPage() {
  const navigate = useNavigate()

  const [values, setValues] = useState<Fields>(EMPTY)
  const [touched, setTouched] = useState<Partial<Record<keyof Fields, boolean>>>({})
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const fieldErrors = validate(values)

  const handleChange = (field: keyof Fields, value: string) =>
    setValues((prev) => ({ ...prev, [field]: value }))

  const handleBlur = (field: keyof Fields) =>
    setTouched((prev) => ({ ...prev, [field]: true }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    setTouched({ name: true, email: true, password: true, confirmPassword: true })
    if (Object.keys(fieldErrors).length > 0) return

    setLoading(true)
    setError(null)
    try {
      const response = await apiFetch('/api/auth/register', {
        method: 'POST',
        body: JSON.stringify({
          name: values.name.trim(),
          email: values.email.trim(),
          password: values.password,
        }),
      })

      if (!response.ok) {
        const body = await response.json().catch(() => ({}))
        throw new Error(body.message || 'Could not create your account. Please try again.')
      }

      // Straight to sign-in rather than auto-authenticating: it keeps one place where
      // credentials become a session, and the new password gets proven immediately.
      navigate('/login', {
        replace: true,
        state: { notice: 'Account created. Sign in with your new credentials.' },
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create your account.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-viewport">
      <div className="login-card">
        <header className="login-header">
          <LayoutGrid className="login-brand-icon" size={32} />
          <h1 className="login-title">Create your account</h1>
          <p className="login-subtitle">Start your own workspace</p>
        </header>

        {error && (
          <div className="login-error-banner" role="alert">
            <AlertCircle className="login-error-icon" size={16} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="login-form">
          <TextInput
            label="Full name"
            id="name"
            type="text"
            value={values.name}
            onChange={(e) => handleChange('name', e.target.value)}
            onBlur={() => handleBlur('name')}
            error={touched.name ? fieldErrors.name : undefined}
            disabled={loading}
            autoComplete="name"
          />

          <TextInput
            label="Email address"
            id="email"
            type="email"
            value={values.email}
            onChange={(e) => handleChange('email', e.target.value)}
            onBlur={() => handleBlur('email')}
            error={touched.email ? fieldErrors.email : undefined}
            disabled={loading}
            autoComplete="email"
          />

          <PasswordInput
            label="Password"
            id="password"
            value={values.password}
            onChange={(e) => handleChange('password', e.target.value)}
            onBlur={() => handleBlur('password')}
            error={touched.password ? fieldErrors.password : undefined}
            disabled={loading}
            autoComplete="new-password"
          />

          <PasswordInput
            label="Confirm password"
            id="confirmPassword"
            value={values.confirmPassword}
            onChange={(e) => handleChange('confirmPassword', e.target.value)}
            onBlur={() => handleBlur('confirmPassword')}
            error={touched.confirmPassword ? fieldErrors.confirmPassword : undefined}
            disabled={loading}
            autoComplete="new-password"
          />

          <button type="submit" className="btn-login-submit" disabled={loading}>
            {loading ? 'Creating account...' : 'Create account'}
          </button>
        </form>

        <p className="login-alt-action">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  )
}
