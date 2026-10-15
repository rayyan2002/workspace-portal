import { useEffect, useRef, useState } from 'react'
import { useParams, Link } from 'react-router'
import { ArrowLeft, Download, Eye, EyeOff, FileQuestion, FileText, Loader2, RefreshCw } from 'lucide-react'
import { useFetch } from '../hooks/useFetch'
import {
  downloadDocument,
  fetchDocumentObjectUrl,
  fetchDocumentText,
  previewKindFor,
} from '../api/openDocument'
import StatusBadge from '../components/StatusBadge'
import ErrorState from '../components/ErrorState'
import { formatBytes, formatDate } from '../utils/format'
import type { Document } from '../Type'
import '../styles/document-detail.css'

function DocumentDetailPage() {
  const { documentId } = useParams<{ documentId: string }>()

  // 'view' and 'download' are tracked separately so only the button actually
  // working shows a spinner.
  const [busy, setBusy] = useState<'view' | 'download' | null>(null)
  const [fileError, setFileError] = useState<string | null>(null)

  // Either an object URL (browser renders it) or decoded text (we render it) —
  // never both, so the two preview paths cannot get out of sync.
  const [preview, setPreview] = useState<
    { kind: 'embed'; url: string } | { kind: 'text'; content: string } | null
  >(null)

  // An object URL is a live handle into browser memory; without this it would leak
  // on unmount and on every re-preview.
  const previewRef = useRef(preview)
  useEffect(() => {
    previewRef.current = preview
  }, [preview])
  useEffect(() => () => {
    const current = previewRef.current
    if (current?.kind === 'embed') URL.revokeObjectURL(current.url)
  }, [])

  const closePreview = () => {
    if (preview?.kind === 'embed') URL.revokeObjectURL(preview.url)
    setPreview(null)
  }

  const togglePreview = async () => {
    if (!documentId || !document) return

    if (preview) {
      closePreview()
      return
    }

    setBusy('view')
    setFileError(null)
    try {
      if (previewKindFor(document.filename) === 'text') {
        setPreview({ kind: 'text', content: await fetchDocumentText(documentId) })
      } else {
        setPreview({ kind: 'embed', url: await fetchDocumentObjectUrl(documentId) })
      }
    } catch (err) {
      setFileError(err instanceof Error ? err.message : 'The original file could not be opened.')
    } finally {
      setBusy(null)
    }
  }

  const handleDownload = async () => {
    if (!documentId || !document) return

    setBusy('download')
    setFileError(null)
    try {
      await downloadDocument(documentId, document.filename)
    } catch (err) {
      setFileError(err instanceof Error ? err.message : 'The file could not be downloaded.')
    } finally {
      setBusy(null)
    }
  }
  
  // Destructured the 'refetch' function for the 500 error case
  const { data: document, loading, error, refetch } = useFetch<Document>(
    `/api/documents/${documentId}`,
    { 
      skip: !documentId, 
      deps: [documentId] 
    }
  )

  const previewKind = document ? previewKindFor(document.filename) : 'unsupported'
  const canPreview = previewKind !== 'unsupported'

  if (loading) {
    return (
      <div className="detail-viewport">
        <header className="detail-header">
           <div className="skeleton-bubble short-shimmer skeleton-breadcrumb" />
           <div className="skeleton-bubble short-shimmer skeleton-title" />
        </header>
        <div className="detail-card-surface state-wrapper-padded">
          <div className="skeleton-bubble long-shimmer skeleton-meta-label" />
          <div className="skeleton-bubble long-shimmer skeleton-line-full" />
          <div className="skeleton-bubble long-shimmer skeleton-line-med" />
          <div className="skeleton-bubble long-shimmer skeleton-line-long" />
        </div>
      </div>
    )
  }

  if (error || !document) {
    // Distinguish a 404 (Missing) from a 500 (Network/Server Crash)
    const isNotFound = !document || (error && error.toLowerCase().includes('not found'))
    
    return (
      <div className="detail-viewport">
        <ErrorState 
          title={isNotFound ? "Document not found" : "Failed to load document details"}
          message={error || 'The requested file metadata could not be retrieved.'}
          action={
            isNotFound ? (
              <Link to="/documents" className="detail-back-link">
                <ArrowLeft size={14} />
                <span>Return to documents</span>
              </Link>
            ) : (
              <button type="button" className="btn-action-primary" onClick={refetch}>
                <RefreshCw size={14} />
                <span>Try Again</span>
              </button>
            )
          }
        />
      </div>
    )
  }

  return (
    <div className="detail-viewport">
      {/* Navigation Breadcrumb Path */}
      <header className="detail-header">
        <Link to="/documents" className="detail-back-link">
          <ArrowLeft size={14} />
          <span>Back to documents</span>
        </Link>
        {/* Changed from 'File settings' to clear user-facing context */}
        <h1>Document details</h1>
        <p className="detail-breadcrumb">
          Workspace / Documents / <span className="breadcrumb-current">{document.filename}</span>
        </p>
      </header>

      {/*
        Two columns: metadata is a narrow fixed rail, the original file gets the rest.
        A single bounded card could not do both — the preview ended up under half the
        page width while the right side of the screen sat empty.
      */}
      <div className="detail-layout">
        <aside className="detail-side">
          <div className="detail-card-surface">
            <div className="detail-card-header">
              <div className="detail-card-title-block">
                <FileText className="detail-card-icon" size={18} />
                <h2 className="detail-card-filename" title={document.filename}>
                  {document.filename}
                </h2>
              </div>
              <StatusBadge status={document.status} />
            </div>

            {fileError && (
              <p className="detail-open-error" role="alert">{fileError}</p>
            )}

            {/* Hairline Divided Definition Rows */}
            <div className="property-ledger">
              <div className="property-row">
                <span className="property-label">System ID</span>
                <span className="property-value mono-text">
                  {document.id}
                </span>
              </div>

              <div className="property-row">
                <span className="property-label">Size</span>
                <span className="property-value">{formatBytes(document.sizeBytes)}</span>
              </div>

              <div className="property-row">
                <span className="property-label">Uploaded</span>
                <span className="property-value">{formatDate(document.uploadDate)}</span>
              </div>
            </div>

            {/* Actions sit in their own band rather than the header: at this column
                width they would crowd the filename off the row. */}
            <div className="detail-card-actions">
              {canPreview && (
                <button
                  type="button"
                  className="btn-open-original"
                  onClick={togglePreview}
                  disabled={busy !== null}
                  aria-expanded={preview !== null}
                >
                  {busy === 'view'
                    ? <Loader2 size={14} className="spin" />
                    : preview ? <EyeOff size={14} /> : <Eye size={14} />}
                  <span>
                    {busy === 'view' ? 'Opening…' : preview ? 'Hide original' : 'Open original'}
                  </span>
                </button>
              )}

              <button
                type="button"
                className="btn-download-original"
                onClick={handleDownload}
                disabled={busy !== null}
                title={`Download ${document.filename}`}
              >
                {busy === 'download' ? <Loader2 size={14} className="spin" /> : <Download size={14} />}
                <span>{busy === 'download' ? 'Saving…' : 'Download'}</span>
              </button>
            </div>

            {/* Contextual Action Layer: Show re-upload trigger only if pipeline broke */}
            {document.status === 'failed' && (
              <div className="detail-card-footer">
                <button type="button" className="btn-action-primary">
                  <RefreshCw size={12} />
                  <span>Re-process file</span>
                </button>
              </div>
            )}
          </div>
        </aside>

        <section className="detail-main">
          {preview ? (
            <div className="detail-card-surface preview-surface">
              <div className="preview-surface-header">
                <span className="preview-surface-label">Original file</span>
                <span className="preview-surface-name" title={document.filename}>
                  {document.filename}
                </span>
              </div>

              {preview.kind === 'embed' ? (
                <iframe
                  src={preview.url}
                  title={`Preview of ${document.filename}`}
                  className="document-preview-frame"
                />
              ) : (
                /* Rendered by us rather than handed to the browser: Chrome will not
                   display text/markdown or text/csv in a frame, it downloads them. */
                <pre className="document-preview-text">{preview.content}</pre>
              )}
            </div>
          ) : canPreview ? (
            <div className="detail-card-surface preview-placeholder">
              <FileText size={28} className="preview-placeholder-icon" />
              <p className="preview-placeholder-title">Preview the original file</p>
              <p className="preview-placeholder-hint">
                Open {document.filename} here without leaving the page.
              </p>
              <button
                type="button"
                className="btn-open-original"
                onClick={togglePreview}
                disabled={busy !== null}
              >
                {busy === 'view' ? <Loader2 size={14} className="spin" /> : <Eye size={14} />}
                <span>{busy === 'view' ? 'Opening…' : 'Open original'}</span>
              </button>
            </div>
          ) : (
            <div className="detail-card-surface preview-placeholder">
              <FileQuestion size={28} className="preview-placeholder-icon" />
              <p className="preview-placeholder-title">No in-page preview for this format</p>
              <p className="preview-placeholder-hint">
                Word and Excel files cannot be rendered by a browser. Download
                {' '}{document.filename} to open it in the right application.
              </p>
              <button
                type="button"
                className="btn-open-original"
                onClick={handleDownload}
                disabled={busy !== null}
              >
                {busy === 'download' ? <Loader2 size={14} className="spin" /> : <Download size={14} />}
                <span>{busy === 'download' ? 'Saving…' : 'Download'}</span>
              </button>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}

export default DocumentDetailPage
