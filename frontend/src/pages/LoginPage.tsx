import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { LayoutGrid, AlertCircle, CheckCircle2 } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import TextInput from '../components/TextInput'
import PasswordInput from '../components/PasswordInput'
import { isValidEmail, isRequired } from '../utils/validators'
import '../styles/login.css'
import { apiFetch } from '../api/client'
import type { AuthResponse } from '../Type' // Adjust path as needed

export default function LoginPage() {
  // Sign-up and password-reset both land here with a one-off confirmation to show.
  const location = useLocation()
  const notice = (location.state as { notice?: string } | null)?.notice ?? null

  const [values, setValues] = useState({ email: '', password: '' })
  const [touched, setTouched] = useState({ email: false, password: false })
  
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  
  const { login } = useAuth()
  const navigate = useNavigate()

  // Derived validation state
  const fieldErrors = {
    email: !isRequired(values.email) 
      ? 'Email is required.' 
      : !isValidEmail(values.email) 
      ? 'Please enter a valid email address.' 
      : null,
    password: !isRequired(values.password) 
      ? 'Password is required.' 
      : null
  }

  const handleChange = (field: 'email' | 'password', val: string) => {
    setValues(prev => ({ ...prev, [field]: val }))
  }

  const handleBlur = (field: 'email' | 'password') => {
    setTouched(prev => ({ ...prev, [field]: true }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    
    // 1. Force all fields to touched to display pending errors
    setTouched({ email: true, password: true })

    // 2. Client-side guard
    if (fieldErrors.email || fieldErrors.password) {
      return
    }

    setLoading(true)
    try {
      const response = await apiFetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values)
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.message || 'Invalid credentials. Please try again.')
      }

      const data: AuthResponse = await response.json()
      login(data)
      navigate('/dashboard', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invalid credentials. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-viewport">
      <div className="login-card">
        
        <header className="login-header">
          <LayoutGrid className="login-brand-icon" size={32} />
          <h1 className="login-title">Workspace Portal</h1>
          <p className="login-subtitle">Sign in to continue</p>
        </header>

        {notice && !error && (
          <div className="login-notice-banner" role="status">
            <CheckCircle2 className="login-notice-icon" size={16} />
            <span>{notice}</span>
          </div>
        )}

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
            value={values.email}
            onChange={(e) => handleChange('email', e.target.value)}
            onBlur={() => handleBlur('email')}
            error={touched.email ? fieldErrors.email : undefined}
            disabled={loading}
            autoComplete="email"
          />

          <div className="login-password-block">
          <PasswordInput
            label="Password"
            id="password"
            value={values.password}
            onChange={(e) => handleChange('password', e.target.value)}
            onBlur={() => handleBlur('password')}
            error={touched.password ? fieldErrors.password : undefined}
            disabled={loading}
            autoComplete="current-password"
          />
            <Link to="/forgot-password" className="login-forgot-link">Forgot password?</Link>
          </div>

          <button 
            type="submit" 
            className="btn-login-submit"
            disabled={loading}
          >
            {loading ? 'Signing in...' : 'Sign in'}
          </button>
        </form>

        <p className="login-alt-action">
          Don't have an account? <Link to="/signup">Sign up</Link>
        </p>
      </div>
    </div>
  )
}