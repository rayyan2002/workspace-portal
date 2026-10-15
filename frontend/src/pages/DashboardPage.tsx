import { Link } from 'react-router'
import { Files, CheckCircle2, AlertTriangle, FileText, UploadCloud } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { usePagedFetch } from '../hooks/usePagedFetch'
import StatusBadge from '../components/StatusBadge'
import ErrorState from '../components/ErrorState'
import EmptyState from '../components/EmptyState'
import { formatBytes, formatDate } from '../utils/format'
import type { Document } from '../Type'
import '../styles/dashboard.css'

export default function DashboardPage() {
  const { user } = useAuth()
  
  /*
   * Four small requests instead of one large one.
   *
   * This page shows three recent documents and three counts, and used to fetch the
   * ENTIRE document list to compute them client-side — 250 rows and 39KB to render
   * six numbers and three filenames. Paging makes the honest version cheap: ask for
   * the three rows actually displayed, and read each count from the `total` of a
   * size-1 query. The counts are exact and the payload no longer grows with the
   * library.
   */
  const recent = usePagedFetch<Document>('/api/documents', 3)
  const all = usePagedFetch<Document>('/api/documents', 1)
  const ready = usePagedFetch<Document>('/api/documents?status=ready', 1)
  const failed = usePagedFetch<Document>('/api/documents?status=failed', 1)

  const loading = recent.loading || all.loading
  const error = recent.error || all.error
  const refetch = () => { recent.refetch(); all.refetch(); ready.refetch(); failed.refetch() }

  const totalCount = all.total
  const readyCount = ready.total
  const failedCount = failed.total

  // Already newest-first from the server, so no client-side sort is needed.
  const recentDocuments = recent.items
  const failedDocument = failed.items[0]

  const getGreeting = () => {
    const hours = new Date().getHours()
    if (hours < 12) return 'Good morning'
    if (hours < 18) return 'Good afternoon'
    return 'Good evening'
  }

  // Define the common header so it's not repeated or lost in states
  const dashboardHeader = (
    <header className="dashboard-header">
      <p className="workspace-scope">{user?.name || 'User'}'s workspace / Dashboard</p>
      <h1>
        {getGreeting()}, <span className="username-highlight">{user?.name || 'Developer'}</span>
      </h1>
      {!loading && !error && totalCount > 0 && (
        <p className="workspace-meta">
          {totalCount} {totalCount === 1 ? 'document' : 'documents'} total in your knowledge base
        </p>
      )}
    </header>
  )

  if (loading) {
    return (
      <div className="dashboard-viewport">
        {dashboardHeader}
        <div className="dashboard-section">
          <h2 className="section-label">Overview Metrics</h2>
          <div className="metrics-grid">
            <div className="skeleton-bubble long-shimmer skeleton-task-card" />
            <div className="skeleton-bubble long-shimmer skeleton-task-card" />
            <div className="skeleton-bubble long-shimmer skeleton-task-card" />
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="dashboard-viewport">
        {dashboardHeader}
        <ErrorState 
          title="Dashboard unavailable"
          message={error}
          action={
            <button type="button" className="btn-action-primary" onClick={refetch}>
              Try Again
            </button>
          }
        />
      </div>
    )
  }

  return (
    <div className="dashboard-viewport">
      {dashboardHeader}
      
      {totalCount === 0 ? (
        <EmptyState
          icon={<UploadCloud size={32} />}
          title="Welcome to your workspace"
          message="Your knowledge base is currently empty. Upload your first document to generate insights and track metrics."
          action={
            <Link to="/documents" className="btn-action-primary">
              Go to Documents
            </Link>
          }
        />
      ) : (
        <>
          <div className="dashboard-section">
            <h2 className="section-label">Overview Metrics</h2>
            <div className="metrics-grid">
              <div className="metric-card">
                <div className="metric-top-row">
                  <div className="metric-label-group">
                    <div className="metric-icon-circle total"><Files size={16} /></div>
                    <span className="metric-label-text">Total documents</span>
                  </div>
                </div>
                <div className="metric-middle-row"><span className="metric-value-text">{totalCount}</span></div>
                <div className="metric-bottom-row"><span>All pipeline ingestion states mapped</span></div>
              </div>

              <div className="metric-card">
                <div className="metric-top-row">
                  <div className="metric-label-group">
                    <div className="metric-icon-circle ready"><CheckCircle2 size={16} /></div>
                    <span className="metric-label-text">Ready to query</span>
                  </div>
                </div>
                <div className="metric-middle-row"><span className="metric-value-text">{readyCount}</span></div>
                <div className="metric-bottom-row"><span className="trend-text-green">✓ Active</span> · indexed and searchable</div>
              </div>

              <div className="metric-card">
                <div className="metric-top-row">
                  <div className="metric-label-group">
                    <div className={`metric-icon-circle ${failedCount > 0 ? 'attention' : 'total'}`}><AlertTriangle size={16} /></div>
                    <span className="metric-label-text">Need attention</span>
                  </div>
                </div>
                <div className="metric-middle-row"><span className="metric-value-text">{failedCount}</span></div>
                <div className="metric-bottom-row">
                  {failedCount === 0 ? (
                    <span>All core processing pipelines normal</span>
                  ) : (
                    <span><span className="trend-text-red">⚠ Attention required</span> · re-upload failed rows</span>
                  )}
                </div>
              </div>
            </div>
          </div>

          {failedDocument && (
            <div className="dashboard-alert-banner">
              <AlertTriangle className="alert-icon" size={16} />
              <p className="alert-text">
                <strong>{failedDocument.filename}</strong> failed to process. Re-upload to add it to your knowledge base.
              </p>
            </div>
          )}

          <div className="dashboard-section">
            <h2 className="section-label">Recent Uploaded Documents</h2>
            <div className="content-card-surface">
              <div className="recent-ledger-rows">
                {recentDocuments.map((doc) => (
                  <div key={doc.id} className="ledger-item-row">
                    <div className="ledger-item-leading">
                      <FileText className="file-icon" size={16} />
                      <div className="file-details">
                        <span className="file-name-text">{doc.filename}</span>
                        <span className="file-sub-meta">
                          {formatBytes(doc.sizeBytes)} · uploaded {formatDate(doc.uploadDate)}
                        </span>
                      </div>
                    </div>
                    <div className="ledger-item-trailing">
                      <StatusBadge status={doc.status} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}