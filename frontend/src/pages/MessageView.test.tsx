import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect } from 'vitest'
import { MemoryRouter } from 'react-router'
import { http, HttpResponse, delay } from 'msw'
import { server } from '../test/setup'
import MessageView from '../components/MessageView'

// Note: In a production test suite, import your actual types here 
// e.g., import type { ActionProposal, ActionResult } from '../types'

describe('MessageView & Action Workflows', () => {
  
  it('sends a message optimistically and receives an AI response', async () => {
    server.use(
      http.get('/api/chat/test-session/messages', () => HttpResponse.json([])),
      http.post('/api/chat/message', async ({ request }) => {
        await delay(100) 
        
        const body = await request.json() as any
        return HttpResponse.json({
          id: `ai-${Date.now()}`,
          content: `AI confirms receipt of: ${body.content}`,
          sender: 'assistant',
          timestamp: new Date().toISOString(),
          citations: [],
          actions: []
        })
      })
    )

    render(
      <MemoryRouter>
        <MessageView sessionId="test-session" sessionTitle="Regression Chat" />
      </MemoryRouter>
    )
    const user = userEvent.setup()

    const input = await screen.findByLabelText('Message AI')
    const sendBtn = screen.getByRole('button', { name: /send/i })

    await user.type(input, 'Analyze the telemetry data')
    await user.click(sendBtn)

    expect(screen.getByText('Analyze the telemetry data')).toBeInTheDocument()
    expect(screen.getByText('Assistant is thinking...')).toBeInTheDocument()

    expect(await screen.findByText('AI confirms receipt of: Analyze the telemetry data')).toBeInTheDocument()
    expect(screen.queryByText('Assistant is thinking...')).not.toBeInTheDocument()
  })

  it('surfaces an action proposal and completes the approval flow', async () => {
    // 1. Enforce the exact ActionProposal contract
    const mockProposal = {
      id: 'act-1',
      type: 'create-task',
      label: 'Create follow-up task to generate a formal report.',
      payload: { 
        title: 'Generate formal report', 
        priority: 'medium' 
      }
    } // as ActionProposal

    // 2. Enforce the exact ActionResult contract
    const mockApprovalResult = {
      actionId: 'act-1',
      status: 'completed',
      type: 'create-task',
      result: { 
        id: 'task-1', 
        title: 'Generate formal report', 
        priority: 'medium', 
        status: 'todo', 
        createdAt: new Date().toISOString(), 
        sourceSessionId: 'action-session' 
      }
    } // as ActionResult

    server.use(
      http.get('/api/chat/action-session/messages', () => HttpResponse.json([])),
      http.post('/api/chat/message', () => {
        return HttpResponse.json({
          id: 'msg-action',
          content: 'I found an anomaly. Shall I generate a formal report?',
          sender: 'assistant',
          timestamp: new Date().toISOString(),
          citations: [],
          actions: [mockProposal]
        })
      }),
      // 3. Bind to the exact endpoint with the typed response
      http.post('/api/ai/actions', () => HttpResponse.json(mockApprovalResult))
    )

    render(
      <MemoryRouter>
        <MessageView sessionId="action-session" sessionTitle="Governance Chat" />
      </MemoryRouter>
    )
    const user = userEvent.setup()

    const input = await screen.findByLabelText('Message AI')
    await user.type(input, 'Scan logs')
    await user.click(screen.getByRole('button', { name: /send/i }))

    const approveBtn = await screen.findByRole('button', { name: /approve/i })
    expect(approveBtn).toBeInTheDocument()

    await user.click(approveBtn)

    // 4. Assert on the exact text rendered by the component's success branch
    expect(await screen.findByText('Task created: Generate formal report')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument()
  })
  /**
   * The user asked one thing and the search ran on another. Day 19.
   *
   * `tell me about ai saftey` retrieved nothing — one letter costs 0.177 against a 0.60
   * floor — so retrieval corrects the query and searches again. Answering the corrected
   * question without saying so would substitute the user's question for a different one.
   */
  it('tells the user when their spelling was corrected before searching', async () => {
    server.use(
      http.get('/api/chat/typo-session/messages', () => HttpResponse.json([])),
      http.post('/api/chat/message', () => HttpResponse.json({
        id: 'ai-1', content: 'AI safety concerns alignment.', sender: 'assistant',
        timestamp: new Date().toISOString(), citations: [], actions: [],
        corrections: [{ typed: 'saftey', used: 'safety' }],
      })),
    )

    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <MessageView sessionId="typo-session" sessionTitle="Typo" />
      </MemoryRouter>
    )
    await user.type(await screen.findByLabelText('Message AI'), 'tell me about ai saftey')
    await user.click(screen.getByRole('button', { name: /send/i }))

    await screen.findByText('AI safety concerns alignment.')
    expect(screen.getByText(/showing results for/i)).toBeInTheDocument()
    expect(screen.getByText('safety')).toBeInTheDocument()
    expect(screen.getByText('saftey')).toBeInTheDocument()
  })

  it('says nothing about spelling on an ordinary answer', async () => {
    server.use(
      http.get('/api/chat/plain-session/messages', () => HttpResponse.json([])),
      http.post('/api/chat/message', () => HttpResponse.json({
        id: 'ai-2', content: 'An ordinary answer.', sender: 'assistant',
        timestamp: new Date().toISOString(), citations: [], actions: [], corrections: [],
      })),
    )

    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <MessageView sessionId="plain-session" sessionTitle="Plain" />
      </MemoryRouter>
    )
    await user.type(await screen.findByLabelText('Message AI'), 'tell me about ai safety')
    await user.click(screen.getByRole('button', { name: /send/i }))

    await screen.findByText('An ordinary answer.')
    expect(screen.queryByText(/showing results for/i)).not.toBeInTheDocument()
  })
})
