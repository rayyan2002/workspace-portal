import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../test/setup'
import ActionCard from '../components/ActionCard'

/**
 * Approving an action that then fails must not be reported as a rejection.
 *
 * THE REPORTED BUG. The card mapped anything that was not `completed` to `rejected`:
 *
 *     if (data.status === 'completed') { ... } else { setStatus('rejected') }
 *
 * So a user approved a summarize-document proposal, execution failed, and the UI told them
 * they had rejected it — the one thing that had definitively not happened — while the audit
 * trail recorded `approved`. Two halves of the product disagreeing about one click.
 */
const proposal = {
  id: 'act-1',
  type: 'summarize-document' as const,
  label: 'Summarize report.txt',
  payload: { documentId: 'doc-1', documentName: 'report.txt' },
}

function renderCard() {
  return render(<ActionCard proposal={proposal} sessionId="s-1" />)
}

describe('ActionCard decision states', () => {
  it('reports a failed execution as failed, not as rejected', async () => {
    server.use(
      http.post('/api/ai/actions', () => HttpResponse.json({
        actionId: 'act-1', status: 'failed', result: null,
        failureReason: 'This document could not be summarised: nothing in it was relevant enough to summarise.',
      })),
    )

    const user = userEvent.setup()
    renderCard()
    await user.click(screen.getByRole('button', { name: /approve/i }))

    expect(await screen.findByText(/could not be summarised/i)).toBeInTheDocument()
    // The exact wording the user saw, and must not see again after approving.
    expect(screen.queryByText(/action rejected/i)).not.toBeInTheDocument()
  })

  it('still reports an actual rejection as rejected', async () => {
    server.use(
      http.post('/api/ai/actions', () => HttpResponse.json({
        actionId: 'act-1', status: 'rejected', result: null,
      })),
    )

    const user = userEvent.setup()
    renderCard()
    await user.click(screen.getByRole('button', { name: /reject/i }))

    expect(await screen.findByText(/action rejected/i)).toBeInTheDocument()
  })

  it('falls back to its own wording when the server gives no reason', async () => {
    // A failure the server could not explain is still not a rejection.
    server.use(
      http.post('/api/ai/actions', () => HttpResponse.json({
        actionId: 'act-1', status: 'failed', result: null, failureReason: null,
      })),
    )

    const user = userEvent.setup()
    renderCard()
    await user.click(screen.getByRole('button', { name: /approve/i }))

    expect(await screen.findByText(/could not be completed/i)).toBeInTheDocument()
    expect(screen.queryByText(/action rejected/i)).not.toBeInTheDocument()
  })
})
