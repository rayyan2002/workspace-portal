import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { MemoryRouter, Routes, Route } from 'react-router'
import { http, HttpResponse } from 'msw'
import { server } from '../test/setup'
import { AuthProvider } from '../context/AuthContext'
import LoginPage from './LoginPage'

function renderWithProviders(ui: React.ReactElement) {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route path="/login" element={ui} />
          <Route path="/dashboard" element={<div data-testid="dashboard-stub">Dashboard Success</div>} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>
  )
}

describe('LoginPage User Flows', () => {
  it('displays client-side validation errors when submitting blank fields', async () => {
    // 1. Genuinely enforce the client-side guard by spying on the network
    const networkSpy = vi.fn()
    server.use(
      http.post('/api/auth/login', () => {
        networkSpy()
        return HttpResponse.json({ token: 'fail' })
      })
    )

    renderWithProviders(<LoginPage />)
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: /sign in/i }))

    expect(screen.getByText('Email is required.')).toBeInTheDocument()
    expect(screen.getByText('Password is required.')).toBeInTheDocument()
    
    // Assert the guard held
    expect(networkSpy).not.toHaveBeenCalled()
  })

  it('displays a transient error banner on server rejection (401)', async () => {
    server.use(
      http.post('/api/auth/login', () => {
        return HttpResponse.json(
          { message: 'Invalid credentials. Please try again.' }, 
          { status: 401 }
        )
      })
    )

    renderWithProviders(<LoginPage />)
    const user = userEvent.setup()

    await user.type(screen.getByLabelText(/email address/i), 'wrong@example.com')
    // 2. Explicitly target the input, ignoring the toggle button's aria-label
    await user.type(screen.getByLabelText(/password/i, { selector: 'input' }), 'badpassword')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    const alertBanner = await screen.findByRole('alert')
    expect(alertBanner).toHaveTextContent(/invalid credentials/i)
  })

  it('navigates to the dashboard upon successful authentication', async () => {
    // 3. Removed the server override. We rely on the real handler to validate the demo credentials.
    
    renderWithProviders(<LoginPage />)
    const user = userEvent.setup()

    await user.type(screen.getByLabelText(/email address/i), 'developer@example.com')
    await user.type(screen.getByLabelText(/password/i, { selector: 'input' }), 'Password123!')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByTestId('dashboard-stub')).toBeInTheDocument()
  })
})