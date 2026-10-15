import { tokenStorage } from './tokenStorage'

const BASE_URL = import.meta.env.VITE_USE_MOCK === 'true'
  ? ''
  : import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080'

/** Endpoints that must never trigger a refresh attempt — refreshing them is circular. */
const AUTH_ENDPOINTS = ['/api/auth/login', '/api/auth/refresh']

/**
 * A single in-flight refresh, shared by every caller.
 *
 * Without this, a page that fires several requests at once would see several 401s and
 * start several refreshes. Because rotation is single-use on the backend, the first
 * would succeed and the rest would present an already-spent token — which the backend
 * correctly treats as reuse and responds to by revoking the whole family, logging the
 * user out. Deduping is not an optimisation here; it is required for correctness.
 */
let refreshInFlight: Promise<string | null> | null = null

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = tokenStorage.getRefreshToken()
  if (!refreshToken) return null

  try {
    const response = await fetch(`${BASE_URL}/api/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refreshToken }),
    })

    if (!response.ok) return null

    const data = await response.json()
    tokenStorage.setTokens(data.accessToken, data.refreshToken)
    return data.accessToken as string
  } catch {
    // Network failure is not an auth failure; treat it as "could not refresh".
    return null
  }
}

function getRefreshedToken(): Promise<string | null> {
  refreshInFlight ??= refreshAccessToken().finally(() => {
    refreshInFlight = null
  })
  return refreshInFlight
}

/** Sends the session to a clean logged-out state and bounces to the login screen. */
function forceLogout() {
  tokenStorage.clear()
  if (window.location.pathname !== '/login') {
    window.location.assign('/login')
  }
}

function buildHeaders(options: RequestInit, token: string | null): Headers {
  const headers = new Headers(options.headers)

  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  return headers
}

/**
 * Authenticated fetch.
 *
 * Access tokens expire after 15 minutes, so a 401 is an ordinary, expected event rather
 * than an error: transparently refresh once and retry. Only a failed refresh means the
 * session is genuinely over.
 */
export async function apiFetch(endpoint: string, options: RequestInit = {}) {
  const isAuthEndpoint = AUTH_ENDPOINTS.some((path) => endpoint.startsWith(path))

  const response = await fetch(`${BASE_URL}${endpoint}`, {
    ...options,
    headers: buildHeaders(options, tokenStorage.getAccessToken()),
  })

  if (response.status !== 401 || isAuthEndpoint) {
    return response
  }

  const newAccessToken = await getRefreshedToken()

  if (!newAccessToken) {
    forceLogout()
    return response
  }

  // Retry exactly once. A second 401 means the problem is not an expired token.
  return fetch(`${BASE_URL}${endpoint}`, {
    ...options,
    headers: buildHeaders(options, newAccessToken),
  })
}
