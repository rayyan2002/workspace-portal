/**
 * Where the token pair lives.
 *
 * <p>Kept in one module so that the storage keys are not spelled out across the app, and
 * so swapping localStorage for something better (an httpOnly cookie set by the backend)
 * is a change to this file alone.
 *
 * <p>localStorage is readable by any script on the page, so it is vulnerable to XSS —
 * a known demo-level tradeoff, not a recommendation.
 */
const ACCESS_TOKEN_KEY = 'accessToken'
const REFRESH_TOKEN_KEY = 'refreshToken'
const USER_KEY = 'user'

export const tokenStorage = {
  getAccessToken: () => localStorage.getItem(ACCESS_TOKEN_KEY),

  getRefreshToken: () => localStorage.getItem(REFRESH_TOKEN_KEY),

  setTokens(accessToken: string, refreshToken: string) {
    localStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
  },

  getStoredUser: () => localStorage.getItem(USER_KEY),

  setUser(user: unknown) {
    localStorage.setItem(USER_KEY, JSON.stringify(user))
  },

  clear() {
    localStorage.removeItem(ACCESS_TOKEN_KEY)
    localStorage.removeItem(REFRESH_TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  },
}
