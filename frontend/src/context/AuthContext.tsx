import { createContext, useContext, useState, useEffect } from 'react'
import type { ReactNode } from 'react'
import type { AuthResponse, User } from '../Type'
import { tokenStorage } from '../api/tokenStorage'
import { apiFetch } from '../api/client'

interface AuthContextValue {
  user: User | null
  roles: string[]
  loading: boolean
  login: (auth: AuthResponse) => void
  logout: () => void
  hasRole: (role: string) => boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)

const ROLES_KEY = 'roles'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [roles, setRoles] = useState<string[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const storedUser = tokenStorage.getStoredUser()

    // NOTE: Storing the user in localStorage is a demo shortcut.
    // Production should bootstrap identity from the token via a /me endpoint so the server stays the source-of-truth.
    if (tokenStorage.getAccessToken() && storedUser) {
      try {
        setUser(JSON.parse(storedUser))
        setRoles(JSON.parse(localStorage.getItem(ROLES_KEY) ?? '[]'))
      } catch {
        tokenStorage.clear()
        localStorage.removeItem(ROLES_KEY)
      }
    }
    setLoading(false)
  }, [])

  /** Takes the whole auth response, since a session is now a token PAIR plus roles. */
  const login = (auth: AuthResponse) => {
    setUser(auth.user)
    setRoles(auth.roles)
    tokenStorage.setTokens(auth.accessToken, auth.refreshToken)
    tokenStorage.setUser(auth.user)
    localStorage.setItem(ROLES_KEY, JSON.stringify(auth.roles))
  }

  const logout = () => {
    const refreshToken = tokenStorage.getRefreshToken()

    // Tell the backend to revoke the refresh token. Fire-and-forget: local state must be
    // cleared regardless, or a failed request would strand the user in a logged-in UI.
    if (refreshToken) {
      apiFetch('/api/auth/logout', {
        method: 'POST',
        body: JSON.stringify({ refreshToken }),
      }).catch(() => undefined)
    }

    setUser(null)
    setRoles([])
    tokenStorage.clear()
    localStorage.removeItem(ROLES_KEY)
  }

  const hasRole = (role: string) => roles.includes(role)

  return (
    <AuthContext.Provider value={{ user, roles, loading, login, logout, hasRole }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
