import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect } from 'vitest'
import { MemoryRouter } from 'react-router'
import { http, HttpResponse } from 'msw'
import { server } from '../test/setup'
import { AuthProvider } from '../context/AuthContext'
import DocumentsPage from './DocumentsPage'


/**
 * Contract revision #2 — list endpoints return { items, total, page, size }.
 *
 * These per-test overrides were a FOURTH hand-maintained copy of the contract,
 * alongside the backend DTOs, Type.ts and mocks/handlers.ts. All four drifted
 * independently; this one was the last to be found, because fixing the shared
 * handlers did not touch it.
 */
function paged<T>(items: T[]) {
  return { items, total: items.length, page: 0, size: 20 }
}

// Test fixture data matching the contract
const mockDocuments = [
  { 
    id: 'doc-1', 
    filename: 'Q3_Financials.pdf', 
    sizeBytes: 1048576, 
    uploadDate: new Date().toISOString(), 
    status: 'ready' 
  }
]

function renderWithProviders(ui: React.ReactElement) {
  return render(
    <AuthProvider>
      <MemoryRouter>
        {ui}
      </MemoryRouter>
    </AuthProvider>
  )
}

describe('DocumentsPage User Flows', () => {
  it('renders the populated document list after loading', async () => {
    server.use(
      http.get('/api/documents', () => HttpResponse.json(paged(mockDocuments)))
    )

    renderWithProviders(<DocumentsPage />)

    // findBy* waits for the loading skeleton to unmount and the fetch to resolve
    expect(await screen.findByText('Q3_Financials.pdf')).toBeInTheDocument()
  })

  it('displays the pure empty state when the user has zero documents', async () => {
    server.use(
      http.get('/api/documents', () => HttpResponse.json(paged([])))
    )

    renderWithProviders(<DocumentsPage />)

    // Assert the instructional empty state text from Day 17 renders
    expect(await screen.findByText('No documents yet')).toBeInTheDocument()
    expect(screen.getByText(/Your knowledge base is empty/i)).toBeInTheDocument()
  })

  it('displays a fetch error and recovers successfully when Retry is clicked', async () => {
    let attempts = 0
    server.use(
      http.get('/api/documents', () => {
        attempts++
        if (attempts === 1) return HttpResponse.error() 
        return HttpResponse.json(paged(mockDocuments)) 
      })
    )

    renderWithProviders(<DocumentsPage />)
    const user = userEvent.setup()

    // 1. Verify the ErrorState component mounted
    expect(await screen.findByText('Failed to load documents')).toBeInTheDocument()

    // 2. Click the universal retry button
    const retryBtn = screen.getByRole('button', { name: /try again/i })
    await user.click(retryBtn)

    // 3. Verify the network recovered and the data rendered
    expect(await screen.findByText('Q3_Financials.pdf')).toBeInTheDocument()
  })

  it('handles upload failures gracefully', async () => {
    server.use(
      http.get('/api/documents', () => HttpResponse.json(paged(mockDocuments))),
      // FIX: The endpoint is /api/documents/upload, not /api/documents!
      http.post('/api/documents/upload', () => {
        return HttpResponse.json({ message: 'Server rejected the file content' }, { status: 400 })
      })
    )

    renderWithProviders(<DocumentsPage />)
    const user = userEvent.setup()

    await screen.findByText('Q3_Financials.pdf')

    const file = new File(['dummy content'], 'corrupted_report.pdf', { type: 'application/pdf' })
    const fileInput = screen.getByLabelText(/browse files/i)
    await user.upload(fileInput, file)

    expect(await screen.findByText(/Server rejected the file content/i)).toBeInTheDocument()
  })

  /**
   * Deleting a document that conversations cite. Month 3, Day 19.
   *
   * `citations.document_id` is ON DELETE RESTRICT, so the delete used to fail on the
   * constraint and the user was shown "Failed to delete … The document has been restored" —
   * true, and naming no cause, so the document simply looked undeletable.
   */
  describe('deleting a document used by conversations', () => {
    const impactWithChats = {
      documentId: 'doc-1',
      filename: 'Q3_Financials.pdf',
      chats: [
        {
          id: 'chat-1', title: 'tell me about finance', messageCount: 10,
          otherDocuments: [
            { id: 'doc-9', filename: 'Budget_2026.xlsx' },
            { id: 'doc-8', filename: 'Audit_Notes.md' },
          ],
        },
        { id: 'chat-2', title: 'Follow up on finance', messageCount: 2, otherDocuments: [] },
      ],
    }

    async function openDeleteFor(filename: string) {
      const user = userEvent.setup()
      renderWithProviders(<DocumentsPage />)
      await screen.findByText(filename)
      await user.click(screen.getByTitle('Delete document'))
      await user.click(await screen.findByRole('button', { name: /confirm delete/i }))
      return user
    }

    it('names every conversation that would be deleted, and what is in it', async () => {
      server.use(
        http.get('/api/documents', () => HttpResponse.json(paged(mockDocuments))),
        http.get('/api/documents/doc-1/deletion-impact', () => HttpResponse.json(impactWithChats)),
      )

      await openDeleteFor('Q3_Financials.pdf')

      expect(await screen.findByRole('alertdialog')).toBeInTheDocument()
      expect(screen.getByText('tell me about finance')).toBeInTheDocument()
      expect(screen.getByText('Follow up on finance')).toBeInTheDocument()
      // The collateral a title alone would hide: this chat mostly concerns other documents,
      // and they are NAMED so the user can go and look rather than guess.
      expect(screen.getByRole('link', { name: /Budget_2026\.xlsx/ })).toBeInTheDocument()
      expect(screen.getByRole('link', { name: /Audit_Notes\.md/ })).toBeInTheDocument()
      expect(screen.getByText(/12 messages will be permanently deleted/i)).toBeInTheDocument()
    })

    it('links each conversation so it can be read before it is destroyed', async () => {
      server.use(
        http.get('/api/documents', () => HttpResponse.json(paged(mockDocuments))),
        http.get('/api/documents/doc-1/deletion-impact', () => HttpResponse.json(impactWithChats)),
      )

      await openDeleteFor('Q3_Financials.pdf')

      const chat = await screen.findByRole('link', { name: /tell me about finance/i })
      expect(chat).toHaveAttribute('href', '/chat/chat-1')
      // A new tab, or confirming would mean losing the dialog to navigate away.
      expect(chat).toHaveAttribute('target', '_blank')
    })

    it('links the other documents, which are NOT deleted', async () => {
      server.use(
        http.get('/api/documents', () => HttpResponse.json(paged(mockDocuments))),
        http.get('/api/documents/doc-1/deletion-impact', () => HttpResponse.json(impactWithChats)),
      )

      await openDeleteFor('Q3_Financials.pdf')

      expect(await screen.findByRole('link', { name: /Budget_2026\.xlsx/ }))
        .toHaveAttribute('href', '/documents/doc-9')
      // The question a user asks next, answered before they have to ask it. Matched on the
      // dialog's text as a whole because the sentence is split by a <strong>.
      const dialog = screen.getByRole('alertdialog')
      expect(dialog.textContent).toMatch(/other documents named above are not deleted/i)
    })

    it('deletes nothing when the dialog is cancelled', async () => {
      let deleteCalls = 0
      server.use(
        http.get('/api/documents', () => HttpResponse.json(paged(mockDocuments))),
        http.get('/api/documents/doc-1/deletion-impact', () => HttpResponse.json(impactWithChats)),
        http.delete('/api/documents/:id', () => { deleteCalls += 1; return new HttpResponse(null, { status: 204 }) }),
      )

      const user = await openDeleteFor('Q3_Financials.pdf')
      await user.click(await screen.findByRole('button', { name: /^cancel$/i }))

      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
      expect(deleteCalls).toBe(0)
      // And the document is still listed — nothing was optimistically removed.
      expect(screen.getByText('Q3_Financials.pdf')).toBeInTheDocument()
    })

    it('passes deleteLinkedChats only after the user confirms', async () => {
      const urls: string[] = []
      server.use(
        http.get('/api/documents', () => HttpResponse.json(paged(mockDocuments))),
        http.get('/api/documents/doc-1/deletion-impact', () => HttpResponse.json(impactWithChats)),
        http.delete('/api/documents/:id', ({ request }) => {
          urls.push(request.url)
          return new HttpResponse(null, { status: 204 })
        }),
      )

      const user = await openDeleteFor('Q3_Financials.pdf')
      await user.click(await screen.findByRole('button', { name: /delete document and 2 conversations/i }))

      expect(urls).toHaveLength(1)
      expect(urls[0]).toContain('deleteLinkedChats=true')
    })

    it('keeps the one-click flow when nothing cites the document', async () => {
      const urls: string[] = []
      server.use(
        http.get('/api/documents', () => HttpResponse.json(paged(mockDocuments))),
        http.get('/api/documents/doc-1/deletion-impact', () =>
          HttpResponse.json({ documentId: 'doc-1', filename: 'Q3_Financials.pdf', chats: [] })),
        http.delete('/api/documents/:id', ({ request }) => {
          urls.push(request.url)
          return new HttpResponse(null, { status: 204 })
        }),
      )

      await openDeleteFor('Q3_Financials.pdf')

      // No dialog for the simple case — it would be ceremony with nothing to report.
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
      expect(urls).toHaveLength(1)
      expect(urls[0]).not.toContain('deleteLinkedChats=true')
    })
  })
})