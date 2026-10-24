import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, beforeEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../test/setup'
import ActionCard from '../components/ActionCard'
import { forgetAllDecisions } from '../utils/decidedActions'

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

// Wrapped in a router because the `running` state links to /actions — the card tells you
// where the background work will appear rather than making you hunt for it.
function renderCard() {
  return render(
    <MemoryRouter>
      <ActionCard proposal={proposal} sessionId="s-1" />
    </MemoryRouter>,
  )
}

describe('ActionCard decision states', () => {
  // The decided-proposal map is module state and every case here reuses the id 'act-1',
  // so without this the second test would find the first one's decision remembered and
  // never render a button. Leaking module state between cases is its own bug class.
  beforeEach(forgetAllDecisions)

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

  it('acknowledges an approval immediately instead of holding a spinner', async () => {
    // V22. The request used to run the whole summarise inside it — 134.9s measured — so the
    // card sat on a spinner long enough that users gave up and navigated away. The decision
    // is now acknowledged as soon as it is recorded and the work finishes in the background.
    server.use(
      http.post('/api/ai/actions', () => HttpResponse.json({
        actionId: 'act-1', status: 'running', type: 'summarize-document', result: null,
      })),
    )

    const user = userEvent.setup()
    renderCard()
    await user.click(screen.getByRole('button', { name: /approve/i }))

    expect(await screen.findByText(/working on it in the background/i)).toBeInTheDocument()
    // Not a failure, and emphatically not "rejected" — the thing that did happen.
    expect(screen.queryByText(/action rejected/i)).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /actions/i })).toBeInTheDocument()
  })

  it('says a rejection was ignored, instead of reporting a creation', async () => {
    // THE REPORTED BUG. Approve a create-task proposal, then press Reject on the same card,
    // and it answered "Task created: University admission policy." The server was right —
    // a proposal is decided once and rejecting afterwards must not delete the task — but
    // reporting a creation as though Reject caused it made the click vanish.
    server.use(
      http.post('/api/ai/actions', () => HttpResponse.json({
        actionId: 'act-1', status: 'completed', type: 'create-task',
        result: { title: 'University admission policy.' },
        replayedDecision: 'approved',
      })),
    )

    const user = userEvent.setup()
    renderCard()
    await user.click(screen.getByRole('button', { name: /reject/i }))

    expect(await screen.findByText(/already approved earlier/i)).toBeInTheDocument()
    expect(await screen.findByText(/rejection was not applied/i)).toBeInTheDocument()
    // The exact wording that was wrong.
    expect(screen.queryByText(/task created/i)).not.toBeInTheDocument()
  })

  it('still shows the result when the click is the one that decided it', async () => {
    // The other half: a first-time approval must not be mistaken for an ignored click.
    server.use(
      http.post('/api/ai/actions', () => HttpResponse.json({
        actionId: 'act-1', status: 'completed', type: 'create-task',
        result: { title: 'University admission policy.' }, replayedDecision: null,
      })),
    )

    const user = userEvent.setup()
    renderCard()
    await user.click(screen.getByRole('button', { name: /approve/i }))

    expect(await screen.findByText(/task created/i)).toBeInTheDocument()
    expect(screen.queryByText(/not applied/i)).not.toBeInTheDocument()
  })

  it('does not offer a decided proposal again after leaving and returning', async () => {
    // THE REPORTED BUG. Approve or reject, navigate to another chat, come back, and the
    // card was asking Approve/Reject again. Nothing ran twice — the server decides a
    // proposal once — but the UI was inviting a decision that had already been made, and
    // the user had no way to tell which click counted.
    //
    // Leaving the chat UNMOUNTS this component, and its state lived in useState.
    server.use(
      http.post('/api/ai/actions', () => HttpResponse.json({
        actionId: 'act-1', status: 'rejected', result: null,
      })),
    )

    const user = userEvent.setup()
    const first = renderCard()
    await user.click(screen.getByRole('button', { name: /reject/i }))
    expect(await screen.findByText(/action rejected/i)).toBeInTheDocument()

    first.unmount()            // navigating away
    renderCard()               // and coming back

    expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /reject/i })).not.toBeInTheDocument()
    expect(screen.getByText(/action rejected/i)).toBeInTheDocument()
  })

  it('renders a decision replayed by history, with no buttons and no request', async () => {
    // THE PERMANENT HALF. The in-memory map survives navigation inside the app but not a
    // refresh — and before V23 nothing else did either, because proposals were ephemeral
    // and history returned the assistant's text with no card at all. A decision a human
    // made left no trace in the conversation where they made it.
    //
    // History now replays the proposal WITH its outcome, so this renders decided on first
    // mount, having asked the server nothing.
    let called = false
    server.use(http.post('/api/ai/actions', () => { called = true; return HttpResponse.json({}) }))

    render(
      <MemoryRouter>
        <ActionCard
          proposal={{
            ...proposal,
            decision: {
              decision: 'rejected', status: 'rejected', result: null, failureReason: null,
            },
          }}
          sessionId="s-1"
        />
      </MemoryRouter>,
    )

    expect(screen.getByText(/action rejected/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument()
    expect(called).toBe(false)
  })

  it('replays a stored result rather than saying it was already decided', async () => {
    // V21: deciding twice returns the REAL answer. Before it, the second click got a shrug
    // and two minutes of completed work was unreachable.
    server.use(
      http.post('/api/ai/actions', () => HttpResponse.json({
        actionId: 'act-1', status: 'completed', type: 'summarize-document',
        result: { summary: 'The alignment problem, summarised.' },
      })),
    )

    const user = userEvent.setup()
    renderCard()
    await user.click(screen.getByRole('button', { name: /approve/i }))

    expect(await screen.findByText(/alignment problem, summarised/i)).toBeInTheDocument()
    expect(screen.queryByText(/already done/i)).not.toBeInTheDocument()
  })

  it('survives a completed result with no payload, as a replayed decision sends', async () => {
    // THE CRASH. Deciding the same proposal twice hits ActionService's idempotency branch,
    // which answers `completed` with a null result — the side effect is not re-run and its
    // output was never stored. `renderResult` dereferenced it and took the whole page down
    // with "Cannot read properties of null (reading 'summary')". The client's own type
    // declared `completed` to imply a result, so nothing caught it at compile time.
    server.use(
      http.post('/api/ai/actions', () => HttpResponse.json({
        actionId: 'act-1', status: 'completed', type: 'summarize-document', result: null,
      })),
    )

    const user = userEvent.setup()
    renderCard()
    await user.click(screen.getByRole('button', { name: /approve/i }))

    expect(await screen.findByText(/already done/i)).toBeInTheDocument()
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
