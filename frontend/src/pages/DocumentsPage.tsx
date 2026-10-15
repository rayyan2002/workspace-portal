import { useState } from 'react'
import { Link } from 'react-router'
import { FileText, Trash2, X, AlertCircle, Search, UploadCloud, RefreshCw } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { usePagedFetch } from '../hooks/usePagedFetch'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import Pagination from '../components/Pagination'
import StatusBadge from '../components/StatusBadge'
import UploadPanel from '../components/UploadPanel'
import ErrorState from '../components/ErrorState'
import EmptyState from '../components/EmptyState'
import { DeleteDocumentDialog } from '../components/DeleteDocumentDialog'
import { formatBytes, formatDate } from '../utils/format'
import type { Document, DocumentStatus, DocumentDeletionImpact } from '../Type'
import '../styles/documents.css'
import { apiFetch } from '../api/client'

const ACCEPTED_EXTENSIONS_TEXT = 'PDF, TXT, DOCX, MD, CSV, or XLSX'
const MAX_FILE_SIZE_TEXT = '10MB'

export default function DocumentsPage() {
  const { user } = useAuth()
  
  const [filterStatus, setFilterStatus] = useState<DocumentStatus | 'all'>('all')
  const [searchQuery, setSearchQuery] = useState('')

  // Typing shouldn't fire a request per keystroke.
  const debouncedSearch = useDebouncedValue(searchQuery, 300)

  /*
   * Filters travel to the SERVER now. Once the list is paged, filtering client-side
   * only searches whichever page happens to be loaded — a search box that silently
   * ignores 230 of 250 documents is worse than no search box at all.
   */
  const query = new URLSearchParams()
  if (filterStatus !== 'all') query.set('status', filterStatus)
  if (debouncedSearch.trim()) query.set('search', debouncedSearch.trim())
  const path = `/api/documents${query.toString() ? `?${query}` : ''}`

  const {
    items: documents, total, page, size, totalPages,
    loading, error, refetch, goToPage, setItems,
  } = usePagedFetch<Document>(path)
  const [confirmingId, setConfirmingId] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  // Set only when deleting would ALSO delete conversations. Null means the ordinary
  // inline confirm applies, so the simple case keeps its one-click flow.
  const [impact, setImpact] = useState<DocumentDeletionImpact | null>(null)
  const [impactBusy, setImpactBusy] = useState(false)

  const handleUploadSuccess = (newDoc: Document) => {
    setItems((prev) => [newDoc, ...prev])
  }

  /**
   * Asks the server what else would go before anything is destroyed.
   *
   * The delete used to be attempted optimistically and fail on a foreign key, which the
   * user saw as "Failed to delete … The document has been restored" — a true sentence that
   * named no cause. Now the impact is fetched first: no conversations, keep the one-click
   * confirm; some conversations, show them and let the user decide.
   */
  const requestDelete = async (id: string) => {
    setDeleteError(null)
    setImpactBusy(true)
    try {
      const response = await apiFetch(`/api/documents/${id}/deletion-impact`)
      if (!response.ok) throw new Error('Could not check what this delete would affect.')
      const found: DocumentDeletionImpact = await response.json()
      if (found.chats.length === 0) {
        await handleDelete(id, false)
      } else {
        setImpact(found)
      }
    } catch {
      setDeleteError('Could not check what deleting this document would affect. Nothing was deleted.')
      setTimeout(() => setDeleteError(null), 4000)
    } finally {
      setImpactBusy(false)
      setConfirmingId(null)
    }
  }

  const handleDelete = async (id: string, deleteLinkedChats: boolean) => {
    const originalIndex = documents.findIndex(d => d.id === id)
    const targetDoc = documents[originalIndex]

    if (!targetDoc) return 

    setConfirmingId(null)
    setDeleteError(null)

    setItems((prev) => prev.filter(d => d.id !== id))

    try {
      const query = deleteLinkedChats ? '?deleteLinkedChats=true' : ''
      const response = await apiFetch(`/api/documents/${id}${query}`, { method: 'DELETE' })
      if (!response.ok) throw new Error('Server rejected the deletion.')
      setImpact(null)
    } catch {
      setItems((prev) => {
        const copy = [...prev]
        copy.splice(originalIndex, 0, targetDoc) 
        return copy
      })
      
      setDeleteError(`Failed to delete "${targetDoc.filename}". The document has been restored.`)
      setTimeout(() => setDeleteError(null), 4000)
    }
  }

  // Already filtered by the server; the alias keeps the JSX below unchanged.
  const filteredDocuments = documents

  const documentsHeader = (
    <header className="documents-header">
      <p className="page-scope">{user?.name || 'User'} / Documents</p>
      <h1>Documents</h1>
      <p className="workspace-meta">Upload and manage the files in your knowledge base.</p>
    </header>
  )

  if (error) {
    return (
      <div className="documents-viewport">
        {documentsHeader}
        <ErrorState 
          title="Failed to load documents"
          message={error}
          action={
            <button type="button" className="btn-action-primary" onClick={refetch}>
              <RefreshCw size={14} />
              <span>Try Again</span>
            </button>
          }
        />
      </div>
    )
  }

  return (
    <div className="documents-viewport">
      {documentsHeader}

      {impact && (
        <DeleteDocumentDialog
          impact={impact}
          busy={impactBusy}
          onConfirm={() => handleDelete(impact.documentId, true)}
          onCancel={() => setImpact(null)}
        />
      )}

      {deleteError && (
        <div className="transient-error-banner">
          <AlertCircle size={16} />
          <span>{deleteError}</span>
        </div>
      )}

      <UploadPanel 
        onUploadSuccess={handleUploadSuccess} 
        acceptedExtensionsText={ACCEPTED_EXTENSIONS_TEXT}
        maxFileSizeText={MAX_FILE_SIZE_TEXT}
      />

      <div className="documents-toolbar">
       <div className="search-box">
          <Search size={16} />
          <input 
            type="text" 
            placeholder="Search documents..." 
            aria-label="Search documents"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
        <select
          className="filter-select-input"
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value as DocumentStatus | 'all')}
          aria-label="Filter by status"
        >
          <option value="all">All statuses</option>
          <option value="ready">Ready</option>
          <option value="processing">Processing</option>
          <option value="failed">Failed</option>
        </select>
      </div>

      {loading ? (
        <div className="table-card-surface state-wrapper-padded">
          {[1, 2, 3, 4].map(i => (
             <div key={i} className="skeleton-bubble long-shimmer skeleton-row" />
          ))}
        </div>
      ) : documents.length === 0 ? (
        <EmptyState
          icon={<UploadCloud size={32} />}
          title="No documents yet"
          message="Your knowledge base is empty. Drag and drop a file into the upload area above to get started."
        />
      ) : filteredDocuments.length === 0 ? (
        <div className="documents-empty-state">
          {searchQuery ? (
             <p>No documents match "{searchQuery}" with the current filters. Try adjusting your search.</p>
          ) : (
             <p>No documents found matching this status.</p>
          )}
        </div>
      ) : (
        <div className="table-card-surface">
          <table className="ledger-table-container">
            <thead>
              <tr>
                <th className="col-filename">Name</th>
                <th className="col-size">Size</th>
                <th className="col-date">Uploaded</th>
                <th className="col-status th-status">Status</th>
                <th className="col-actions" aria-label="Actions"></th> 
              </tr>
            </thead>
            <tbody>
              {filteredDocuments.map((doc) => (
                <tr key={doc.id} className="ledger-row-item">
                  <td className="col-filename">
                    <div className="row-file-leading">
                      <FileText className="row-file-icon" size={16} />
                      <Link to={`/documents/${doc.id}`} className="row-file-link">
                        {doc.filename}
                      </Link>
                    </div>
                  </td>
                  <td className="col-size" data-label="Size">{formatBytes(doc.sizeBytes)}</td>
                  <td className="col-date" data-label="Uploaded">{formatDate(doc.uploadDate)}</td>
                  <td className="col-status" data-label="Status">
                    <div className="row-status-alignment">
                      <StatusBadge status={doc.status} />
                    </div>
                  </td>
                  <td className="col-actions">
                    {confirmingId === doc.id ? (
                      <div className="confirm-delete-group">
                        <button className="btn-confirm-delete" disabled={impactBusy}
                                onClick={() => requestDelete(doc.id)}>
                          {impactBusy ? 'Checking…' : 'Confirm Delete'}
                        </button>
                        <button className="btn-cancel-delete" onClick={() => setConfirmingId(null)} title="Cancel">
                          <X size={14} />
                        </button>
                      </div>
                    ) : (
                      <button className="btn-icon-delete" onClick={() => setConfirmingId(doc.id)} title="Delete document">
                        <Trash2 size={16} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Pagination
        page={page}
        totalPages={totalPages}
        total={total}
        size={size}
        onChange={goToPage}
        label="documents"
      />
    </div>
  )
}