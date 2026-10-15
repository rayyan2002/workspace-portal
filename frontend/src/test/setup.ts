import '@testing-library/jest-dom'
import { beforeAll, afterEach, afterAll, vi } from 'vitest' // <-- Add this import
import { setupServer } from 'msw/node'
import { handlers } from '../mocks/handlers'

// Set up the MSW node server using the same handlers as the browser
export const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
window.HTMLElement.prototype.scrollIntoView = vi.fn()