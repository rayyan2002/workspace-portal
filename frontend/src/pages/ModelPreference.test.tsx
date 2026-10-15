import { render, screen, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, beforeEach } from 'vitest'
import { MemoryRouter, Routes, Route } from 'react-router'
import { http, HttpResponse } from 'msw'
import { server } from '../test/setup'
import ChatPage from './ChatPage'

/**
 * The model choice must outlive the component that shows it.
 *
 * It used to be `useState('local')` inside MessageView, so any remount silently reverted a
 * user who had deliberately chosen Cloud back to on-device — mid-conversation, with no
 * indication. The trace log caught it on real traffic: one conversation ran
 * `gemini (0 history) → local (2 history)` with no selector change.
 */
describe('the chosen model is remembered', () => {
  const sessions = {
    items: [{ id: 's1', title: 'a chat', lastMessagePreview: 'x', updatedAt: new Date().toISOString() }],
    total: 1, page: 0, size: 100,
  }

  beforeEach(() => localStorage.clear())

  function renderChat(at = '/chat/s1') {
    server.use(
      http.get('/api/chat/sessions*', () => HttpResponse.json(sessions)),
      http.get('/api/chat/s1/messages', () => HttpResponse.json([])),
      http.get('/api/chat/real-1/messages', () => HttpResponse.json([])),
    )
    return render(
      <MemoryRouter initialEntries={[at]}>
        <Routes>
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/:sessionId" element={<ChatPage />} />
        </Routes>
      </MemoryRouter>
    )
  }

  it('defaults to on-device for a user who has never chosen', async () => {
    renderChat()
    // The private option is what you get by not choosing. That part was always right.
    expect(await screen.findByLabelText('Which model answers')).toHaveValue('local')
  })

  it('survives a full remount, which is what the old version failed at', async () => {
    const user = userEvent.setup()
    renderChat()
    await user.selectOptions(await screen.findByLabelText('Which model answers'), 'gemini')

    // Unmount everything and mount it fresh — the harshest version of whatever was
    // remounting the component in the real app.
    cleanup()
    renderChat()

    expect(await screen.findByLabelText('Which model answers')).toHaveValue('gemini')
  })

  it('sends the remembered model on a follow-up message', async () => {
    const sent: string[] = []
    server.use(
      http.post('/api/chat/message', async ({ request }) => {
        const body = await request.json() as { model: string }
        sent.push(body.model)
        return HttpResponse.json({
          id: 'ai-1', content: 'an answer', sender: 'assistant',
          timestamp: new Date().toISOString(), citations: [], actions: [],
        })
      }),
    )
    const user = userEvent.setup()
    renderChat()
    await user.selectOptions(await screen.findByLabelText('Which model answers'), 'gemini')
    await user.type(screen.getByLabelText('Message AI'), 'hello')
    await user.click(screen.getByRole('button', { name: /send/i }))

    await screen.findByText('an answer')
    // The reported symptom was this going out as "local" on the second message.
    expect(sent).toEqual(['gemini'])
  })

  it('a changed choice replaces the old one rather than accumulating', async () => {
    const user = userEvent.setup()
    renderChat()
    const select = await screen.findByLabelText('Which model answers')
    await user.selectOptions(select, 'gemini')
    await user.selectOptions(select, 'local')

    cleanup()
    renderChat()
    expect(await screen.findByLabelText('Which model answers')).toHaveValue('local')
  })
})
