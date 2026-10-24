import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../test/setup'
import AdminPage from './AdminPage'

// useAuth is a hook, not an exported context, so the module is mocked rather than wrapped.
// The page gates NAVIGATION on it; the real enforcement is the server's 403.
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ hasRole: () => true, user: { id: 'u1', email: 'boss@example.com' } }),
}))

/**
 * An administrator can appoint another administrator.
 *
 * The page is guarded on the client for NAVIGATION only — /api/admin/** answers 403
 * regardless of what the client renders — so these tests cover the behaviour the user
 * sees, not the enforcement.
 */
const USERS = {
  items: [
    { id: 'u1', email: 'boss@example.com', name: 'Boss', admin: true },
    { id: 'u2', email: 'new@example.com', name: 'New Person', admin: false },
    { id: 'u3', email: 'other@example.com', name: 'Other Admin', admin: true },
  ],
  page: 0, size: 50, total: 2,
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AdminPage />
    </MemoryRouter>,
  )
}

describe('AdminPage role management', () => {
  it('offers to promote an ordinary user and marks existing admins', async () => {
    server.use(http.get('/api/admin/users', () => HttpResponse.json(USERS)))
    renderPage()

    expect(await screen.findByText('new@example.com')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /make admin/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /revoke admin/i })).toBeInTheDocument()
  })

  it('never offers "Make admin" to somebody who already is one', async () => {
    // Reported: every row said "Make admin", including accounts that already had it. The
    // cause was the server omitting the `admin` flag, but the label is asserted here so a
    // regression shows up as a test failure rather than as a confusing button.
    server.use(http.get('/api/admin/users', () => HttpResponse.json(USERS)))
    renderPage()

    await screen.findByText('new@example.com')
    const labels = screen.getAllByRole('button').map((b) => b.textContent)
    expect(labels.filter((l) => l === 'Make admin')).toHaveLength(1)   // only the non-admin
  })

  it('disables the row for your own account', async () => {
    // The server refuses a self-revoke, so an enabled button here is a guaranteed error.
    server.use(http.get('/api/admin/users', () => HttpResponse.json(USERS)))
    renderPage()

    const own = await screen.findByRole('button', { name: /you/i })
    expect(own).toBeDisabled()
  })

  it('shows the server refusal verbatim rather than a generic failure', async () => {
    // The server refuses two cases on purpose — your own access, and the last
    // administrator — and only its wording says which. Replacing it with "something went
    // wrong" would hide the one piece of information the user needs.
    server.use(
      http.get('/api/admin/users', () => HttpResponse.json(USERS)),
      http.delete('/api/admin/users/:id/admin', () => HttpResponse.json(
        { message: 'This is the only administrator. Promote somebody else first.' },
        { status: 400 })),
    )

    const user = userEvent.setup()
    renderPage()
    // u1 is the signed-in account and is disabled, so the revoke under test is u2's.
    await user.click(await screen.findByRole('button', { name: /revoke admin/i }))

    await waitFor(() => expect(
      screen.getByText(/only administrator/i)).toBeInTheDocument())
  })
})
